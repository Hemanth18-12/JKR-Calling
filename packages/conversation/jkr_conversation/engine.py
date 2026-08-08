"""process_turn() — the one entrypoint both services/voice-worker's
conversation_engine.py and services/api's live_call/service.py call. Pure
orchestration: extract -> backstop -> plan -> retrieve-if-needed -> generate
-> format. Never persists CallTurn/CallEvent/tool executions itself (the
caller already owns that, with its own transport-specific timing/DB-session
needs) — this function only decides what should happen and returns it.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jkr_conversation import extractor, formatter, objectives, planner, policy, prompt_builder, rag
from jkr_conversation.llm_client import LLMClient, get_default_client
from jkr_conversation.schemas import (
    ConversationPolicySnapshot,
    ConversationTurnResult,
    ToolCallRequest,
)

# Actions that mean the call is over — engine-level, not caller-specific.
# HUMAN_HANDOFF is deliberately NOT here: the mock/Test Lab path continues
# the session after an acknowledged handoff (matching today's behavior,
# where submit_user_turn returns but the call stays in_progress); a caller
# without real warm-transfer capability (live_call) can choose to treat
# planner_action == "human_handoff" as a close on its own, which is exactly
# what it does — see services/api/app/modules/live_call/service.py.
_TERMINAL_ACTIONS = {"SAFETY_STOP", "COMPLETE_OBJECTIVE"}

_END_REASON_BY_PLANNER_REASON = {
    "do_not_call_requested": "do_not_call",
    "wrong_number": "wrong_number",
    "all_fields_collected": "objective_completed",
    "max_turns_reached": "max_turns_reached",
    "max_duration_reached": "max_duration_reached",
}


async def process_turn(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    call_session_id: uuid.UUID,
    state: dict,
    customer_utterance: str,
    conversation_policy: ConversationPolicySnapshot,
    business_identity: str = "",
    transcript_confidence: float | None = None,
    recent_turns: list[dict] | None = None,
    llm_client: LLMClient | None = None,
    now: datetime | None = None,
) -> ConversationTurnResult:
    now = now or datetime.now(UTC)
    client = llm_client if llm_client is not None else get_default_client()
    latency_ms: dict[str, int] = {}
    new_state = dict(state)
    new_state["turn_count"] = new_state.get("turn_count", 0) + 1

    t0 = time.perf_counter()
    extraction = await extractor.extract(customer_utterance=customer_utterance, state=new_state, llm_client=client)
    extraction = policy.apply_backstop(extraction, raw_text=customer_utterance)
    latency_ms["extraction"] = int((time.perf_counter() - t0) * 1000)

    # --- fold extraction results into state -------------------------------
    known_fields = dict(new_state.get("known_fields", {}))
    field_confidence = dict(new_state.get("field_confidence", {}))
    uncertain = set(new_state.get("uncertain_fields", []))
    for key, value in extraction.extracted_fields.items():
        known_fields[key] = value
        field_confidence[key] = extraction.field_confidence.get(key, 0.75)
    for key in extraction.uncertain_fields:
        uncertain.add(key)
    new_state["known_fields"] = known_fields
    new_state["field_confidence"] = field_confidence
    new_state["uncertain_fields"] = sorted(uncertain)
    new_state["missing_fields"] = [f for f in objectives.all_field_keys(new_state.get("objective", "")) if f not in known_fields]
    new_state["intent"] = extraction.turn_intent
    new_state["sentiment"] = extraction.sentiment
    if extraction.do_not_call:
        new_state["do_not_call"] = True
    if extraction.wrong_number:
        new_state["wrong_number"] = True
    if extraction.wants_human:
        new_state["customer_requested_human"] = True

    t0 = time.perf_counter()
    decision = planner.decide(extraction=extraction, state=new_state, conversation_policy=conversation_policy, now=now)
    latency_ms["planning"] = int((time.perf_counter() - t0) * 1000)

    rag_chunks: list = []
    if decision.rag_query:
        t0 = time.perf_counter()
        rag_chunks, _above_threshold = await rag.search_knowledge(
            db, workspace_id=workspace_id, query=decision.rag_query, call_session_id=call_session_id
        )
        latency_ms["rag"] = int((time.perf_counter() - t0) * 1000)

    # --- translate the decision into state transitions --------------------
    field_ask_counts = dict(new_state.get("field_ask_counts", {}))
    if decision.action in ("ASK_FIELD", "CLARIFY") and decision.target_field:
        field_ask_counts[decision.target_field] = field_ask_counts.get(decision.target_field, 0) + 1
    new_state["field_ask_counts"] = field_ask_counts

    if decision.action == "SAFETY_STOP":
        new_state["awaiting_field"] = None
        new_state["objective_status"] = "do_not_call" if extraction.do_not_call else "wrong_number"
        new_state["next_best_action"] = "add_do_not_call" if extraction.do_not_call else "end_wrong_number_call"
        new_state["risk_flags"] = sorted(set(new_state.get("risk_flags", [])) | {decision.reason})
    elif decision.action == "HUMAN_HANDOFF":
        new_state["awaiting_field"] = None
        new_state["objective_status"] = "needs_human"
        new_state["next_best_action"] = "human_handoff"
    elif decision.action == "CLARIFY":
        new_state["awaiting_field"] = decision.target_field
        new_state["next_best_action"] = "clarify"
    elif decision.action == "ASK_FIELD":
        new_state["awaiting_field"] = decision.target_field
        new_state["asked_count"] = new_state.get("asked_count", 0) + 1
        new_state["next_best_action"] = "ask_question"
    elif decision.action == "COMPLETE_OBJECTIVE":
        new_state["awaiting_field"] = None
        new_state["objective_status"] = "completed"
        new_state["next_best_action"] = "close_conversation"

    t0 = time.perf_counter()
    raw_reply = await prompt_builder.generate(
        decision=decision, extraction=extraction, state=new_state, rag_chunks=rag_chunks,
        conversation_policy=conversation_policy, business_identity=business_identity,
        language=new_state.get("language", "en-IN"), recent_turns=recent_turns, llm_client=client,
    )
    latency_ms["generation"] = int((time.perf_counter() - t0) * 1000)

    prepend_ack = decision.action in ("ASK_FIELD", "CLARIFY")
    fmt = formatter.SpokenResponseFormatter(
        language=new_state.get("language", "en-IN"), max_sentences=conversation_policy.max_response_sentences
    )
    formatted = fmt.format(raw_reply, prepend_acknowledgement=prepend_ack)

    tool_calls: list[ToolCallRequest] = []
    if decision.action == "HUMAN_HANDOFF":
        tool_calls.append(
            ToolCallRequest(
                tool_name="create_human_callback",
                tool_input={"reason": "customer_requested", "packet": {"known_fields": known_fields, "last_customer_utterance": customer_utterance}},
                idempotency_suffix="human_handoff",
            )
        )
    elif decision.action == "COMPLETE_OBJECTIVE":
        objective = objectives.get_objective(new_state.get("objective", objectives.DEFAULT_OBJECTIVE_ID))
        if objective.tool_on_completion and known_fields:
            tool_calls.append(
                ToolCallRequest(tool_name=objective.tool_on_completion, tool_input=known_fields, idempotency_suffix=objective.tool_on_completion)
            )

    call_should_end = decision.action in _TERMINAL_ACTIONS
    end_reason = _END_REASON_BY_PLANNER_REASON.get(decision.reason) if call_should_end else None

    new_state["last_turn_debug"] = {
        "planner_action": decision.action,
        "planner_reason": decision.reason,
        "detected_question": extraction.detected_question,
        "rag_query": decision.rag_query,
        "rag_hit": bool(rag_chunks),
        "is_mock": extraction.is_mock,
    }

    return ConversationTurnResult(
        reply_text=formatted.text,
        formatted=formatted,
        state=new_state,
        planner_action=decision.action,
        planner_reason=decision.reason,
        extraction=extraction,
        rag_chunks=rag_chunks,
        call_should_end=call_should_end,
        end_reason=end_reason,
        tool_calls_requested=tool_calls,
        latency_ms=latency_ms,
    )
