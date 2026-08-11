"""process_turn() — the one entrypoint both services/voice-worker's
conversation_engine.py and services/api's live_call/service.py call. Pure
orchestration: extract -> backstop -> fold-into-state (incl. domain
confirmation resolution) -> plan -> retrieve-if-needed -> generate ->
format. Never persists CallTurn/CallEvent/tool executions itself (the
caller already owns that, with its own transport-specific timing/DB-session
needs) — this function only decides what should happen and returns it. It
DOES stage TranscriptCorrectionEvent rows on the passed-in `db` session
(the caller's existing transaction), same as rag.py already touches `db`
for retrieval — correction telemetry has nowhere else to be written from.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

from jkr_db.models.calls import TranscriptCorrectionEvent
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_conversation import (
    domain_vocabulary,
    extractor,
    fast_router,
    formatter,
    objectives,
    planner,
    policy,
    prompt_builder,
    rag,
)
from jkr_conversation.llm_client import LLMClient, get_default_client
from jkr_conversation.schemas import (
    ConversationPolicySnapshot,
    ConversationTurnResult,
    DomainTermSnapshot,
    FieldExtraction,
    ToolCallRequest,
)
from jkr_conversation.streaming_response import CancellationToken, SpeakableChunk

# Actions that mean the call is over — engine-level, not caller-specific.
# HUMAN_HANDOFF is deliberately NOT here: the mock/Test Lab path continues
# the session after an acknowledged handoff (matching today's behavior,
# where submit_user_turn returns but the call stays in_progress); a caller
# without real warm-transfer capability (live_call) can choose to treat
# planner_action == "human_handoff" as a close on its own, which is exactly
# what it does — see services/api/app/modules/live_call/service.py.
# CONFIRM_FIELD and DEFER_QUESTION are both, by construction, never
# terminal — they exist specifically to keep the conversation open.
_TERMINAL_ACTIONS = {"SAFETY_STOP", "COMPLETE_OBJECTIVE"}

_END_REASON_BY_PLANNER_REASON = {
    "do_not_call_requested": "do_not_call",
    "wrong_number": "wrong_number",
    "all_fields_collected": "objective_completed",
    "max_turns_reached": "max_turns_reached",
    "max_duration_reached": "max_duration_reached",
}

# A domain-normalization ratio at/above this is trusted as "clearly the
# right term" under confirm_low_confidence — below it, confirm even if the
# field isn't flagged critical. Deliberately the same bar domain_normalizer
# itself doesn't apply (that module only decides "is this candidate worth
# surfacing at all," not "is it good enough to trust silently").
STRONG_MATCH_THRESHOLD = 0.93


def _requires_confirmation(behavior: str, *, criticality: str, semantic_confidence: float | None) -> bool:
    """Crosses ConversationPolicy.confirmation_behavior (packages/db/jkr_db/
    models/agents.py's enum) against one field's own criticality/match-
    quality. Called once per domain-matched field, every turn — this is
    what makes confirmation_behavior an actually-enforced setting instead
    of a DB column nothing reads."""
    if behavior == "confirm_none":
        return False
    if behavior == "confirm_all":
        return True
    if behavior == "confirm_low_confidence":
        return semantic_confidence is not None and semantic_confidence < STRONG_MATCH_THRESHOLD
    # "confirm_critical" (the DB default) and any unrecognized value both
    # fall back to this — the safest behavior for an unknown future enum value.
    return criticality == "critical"


def _record_correction_event(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    call_session_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    domain_term_id: uuid.UUID | None,
    raw_value: str,
    candidate_value: str | None,
    correction_method: str | None,
    semantic_confidence: float | None,
    sequence_index: int,
    customer_confirmed: bool | None,
    accepted_term: str | None,
) -> None:
    db.add(
        TranscriptCorrectionEvent(
            workspace_id=workspace_id,
            call_session_id=call_session_id,
            agent_id=agent_id,
            domain_term_id=domain_term_id,
            sequence_index=sequence_index,
            raw_text=raw_value,
            raw_term=raw_value,
            candidate_term=candidate_value,
            accepted_term=accepted_term,
            correction_method=correction_method or "fuzzy_alias_match",
            confidence=semantic_confidence,
            customer_confirmed=customer_confirmed,
        )
    )


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
    agent_id: uuid.UUID | None = None,
    now: datetime | None = None,
    engine_mode: str = "legacy",  # P3.5 — "legacy" | "fast"; see docs/P3_5_CONVERSATION_ENGINE_RESULTS.md
    # P5 — "complete" (default) is byte-identical to pre-P5 behavior; see
    # prompt_builder.generate()'s own docstring-level comment on these same
    # four params for why each is a no-op unless response_mode=="streaming".
    response_mode: str = "complete",  # "complete" | "streaming"
    on_speakable_chunk: Callable[[SpeakableChunk], Awaitable[None] | None] | None = None,
    cancellation_token: CancellationToken | None = None,
    # P10 §42 — threaded straight through to prompt_builder.generate()'s own
    # response-style hint; see that module's _brevity_instruction(). Zero
    # effect below this codebase's ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD, so
    # every existing call site (which never passes this) is unaffected.
    recent_interrupt_count: int = 0,
) -> ConversationTurnResult:
    now = now or datetime.now(UTC)
    client = llm_client if llm_client is not None else get_default_client()
    latency_ms: dict[str, int] = {}
    new_state = dict(state)
    new_state["turn_count"] = new_state.get("turn_count", 0) + 1
    sequence_index = new_state["turn_count"]

    # P3.5 fast path: a small set of high-confidence, zero-LLM turns (do-not-
    # call, wrong-number, human-handoff, pending-confirmation yes/no,
    # acknowledgement-only) never reach extractor.extract() at all when
    # engine_mode=="fast" — see fast_router.py for exactly which cases and
    # why the rest deliberately fall through to real extraction. engine_mode
    # defaults to "legacy", under which fast_router is never even imported-
    # from at runtime here, so behavior is byte-identical to before this phase.
    t0 = time.perf_counter()
    extraction = fast_router.route(customer_utterance=customer_utterance, state=new_state, conversation_policy=conversation_policy) if engine_mode == "fast" else None
    fast_path_hit = extraction is not None
    latency_ms["fast_router"] = int((time.perf_counter() - t0) * 1000)

    domain_terms: list[DomainTermSnapshot] = []
    if fast_path_hit:
        latency_ms["domain_vocabulary"] = 0
        latency_ms["extraction"] = 0
    else:
        t0 = time.perf_counter()
        if agent_id is not None:
            domain_terms = await domain_vocabulary.load_domain_terms(db, workspace_id=workspace_id, agent_id=agent_id)
        latency_ms["domain_vocabulary"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        extraction = await extractor.extract(
            customer_utterance=customer_utterance,
            state=new_state,
            llm_client=client,
            domain_terms=domain_terms,
            acknowledgement_phrases=conversation_policy.accidental_interruption_phrases,
        )
        latency_ms["extraction"] = int((time.perf_counter() - t0) * 1000)

    assert extraction is not None  # guaranteed by the if/else above; narrows for mypy
    extraction = policy.apply_backstop(extraction, raw_text=customer_utterance)

    # --- fold extraction results into state -------------------------------
    known_fields = dict(new_state.get("known_fields", {}))
    field_confidence = dict(new_state.get("field_confidence", {}))
    uncertain = set(new_state.get("uncertain_fields", []))

    # 1. Resolve a field that was already pending confirmation before this
    # turn started (staged on a prior turn, below). The customer's reply
    # this turn (extraction.confirmation_response, resolved deterministically
    # in extractor.py) always settles it one way or another — confirm writes
    # the candidate value; reject/correction both leave it unwritten (still
    # "missing"), and a correction's actual new value flows through the
    # per-field loop below like anything else stated this turn.
    pending = new_state.get("pending_confirmation")
    if pending:
        field = pending.get("field")
        response = extraction.confirmation_response or "correction"
        is_real_correction = pending.get("raw_value") != pending.get("candidate_value")
        if response == "confirm":
            accepted = pending.get("candidate_value") or pending.get("raw_value")
            known_fields[field] = accepted
            field_confidence[field] = 0.95  # explicitly confirmed by the customer
            if is_real_correction:
                _record_correction_event(
                    db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
                    domain_term_id=pending.get("domain_term_id"), raw_value=pending.get("raw_value", ""),
                    candidate_value=pending.get("candidate_value"), correction_method=pending.get("correction_method"),
                    semantic_confidence=pending.get("semantic_confidence"), sequence_index=sequence_index,
                    customer_confirmed=True, accepted_term=accepted,
                )
        elif is_real_correction:  # "reject" or "correction" — original candidate not accepted as-is
            _record_correction_event(
                db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
                domain_term_id=pending.get("domain_term_id"), raw_value=pending.get("raw_value", ""),
                candidate_value=pending.get("candidate_value"), correction_method=pending.get("correction_method"),
                semantic_confidence=pending.get("semantic_confidence"), sequence_index=sequence_index,
                customer_confirmed=False, accepted_term=None,
            )
        new_state["pending_confirmation"] = None

    # 2. Fold every field extracted this turn (including a just-resolved
    # correction's new value) — running each domain-matched one through the
    # confirmation decision table. At most one field can be pending
    # confirmation at a time; a second one this same turn is simply left
    # unwritten (still "missing") and resurfaces on a later turn.
    new_pending: dict | None = None
    for key, value in extraction.extracted_fields.items():
        field_extraction: FieldExtraction | None = extraction.field_extractions.get(key)
        if field_extraction is not None and field_extraction.criticality is not None:
            needs_confirmation = _requires_confirmation(
                conversation_policy.confirmation_behavior,
                criticality=field_extraction.criticality,
                semantic_confidence=field_extraction.semantic_confidence,
            )
            if needs_confirmation:
                if new_pending is None:
                    new_pending = {
                        "field": key,
                        "raw_value": field_extraction.raw_value,
                        "candidate_value": field_extraction.candidate_value or field_extraction.raw_value,
                        "semantic_confidence": field_extraction.semantic_confidence,
                        "domain_term_id": field_extraction.domain_term_id,
                        "correction_method": field_extraction.correction_method,
                    }
                continue  # not written to known_fields yet — correctly stays "missing" until resolved
            accepted_value = field_extraction.candidate_value or value
            known_fields[key] = accepted_value
            field_confidence[key] = extraction.field_confidence.get(key, field_extraction.confidence)
            if field_extraction.candidate_value is not None:
                _record_correction_event(
                    db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
                    domain_term_id=field_extraction.domain_term_id, raw_value=field_extraction.raw_value,
                    candidate_value=field_extraction.candidate_value, correction_method=field_extraction.correction_method,
                    semantic_confidence=field_extraction.semantic_confidence, sequence_index=sequence_index,
                    customer_confirmed=None, accepted_term=accepted_value,
                )
        else:
            known_fields[key] = value
            field_confidence[key] = extraction.field_confidence.get(key, 0.75)

    if new_pending is not None:
        new_state["pending_confirmation"] = new_pending

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
    rag_above_threshold = False
    if decision.rag_query:
        rag_chunks, rag_above_threshold, rag_timing = await rag.search_knowledge_with_timing(
            db, workspace_id=workspace_id, query=decision.rag_query, call_session_id=call_session_id
        )
        # P3.5 §6: fine-grained breakdown, not one opaque "rag" number — a
        # direct provider probe (docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md
        # §3) showed the embedding call, not pgvector, dominates this.
        latency_ms["rag_embedding"] = rag_timing.embedding_ms
        latency_ms["rag_vector_search"] = rag_timing.vector_search_ms
        latency_ms["rag"] = rag_timing.total_ms

    # An objective that would otherwise be done, but the customer asked
    # something this turn that couldn't be answered from real knowledge —
    # defer instead of closing, rather than ending the call mid-question.
    # Deliberately gated on rag_above_threshold, not just `rag_chunks` being
    # non-empty: search_knowledge always returns its top-k nearest chunks
    # regardless of match quality (a workspace with any knowledge at all
    # would otherwise make this check never fire) — above_threshold is the
    # real "was this actually a good answer" signal.
    if decision.action == "COMPLETE_OBJECTIVE" and decision.rag_query and not rag_above_threshold:
        decision = replace(decision, action="DEFER_QUESTION", reason="unanswered_question_before_close")

    # --- translate the decision into state transitions --------------------
    field_ask_counts = dict(new_state.get("field_ask_counts", {}))
    if decision.action in ("ASK_FIELD", "CLARIFY", "CONFIRM_FIELD") and decision.target_field:
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
    elif decision.action == "CONFIRM_FIELD":
        new_state["awaiting_field"] = decision.target_field
        new_state["next_best_action"] = "confirm_field"
    elif decision.action == "ASK_FIELD":
        new_state["awaiting_field"] = decision.target_field
        new_state["asked_count"] = new_state.get("asked_count", 0) + 1
        new_state["next_best_action"] = "ask_question"
    elif decision.action == "DEFER_QUESTION":
        new_state["awaiting_field"] = None
        new_state["next_best_action"] = "defer_question"
    elif decision.action == "COMPLETE_OBJECTIVE":
        new_state["awaiting_field"] = None
        new_state["objective_status"] = "completed"
        new_state["next_best_action"] = "close_conversation"

    # Ask-cap exhaustion safety net: a pending confirmation still unresolved
    # by the time the planner has moved on to something other than
    # CONFIRM_FIELD for it only happens because its ask-cap is exhausted
    # (see planner.py's step 3b) — accept it at its raw value rather than
    # leaving it stuck forever. Same "ask twice, then accept what was
    # literally said" philosophy as the ask-cap everywhere else.
    if new_state.get("pending_confirmation") and decision.action != "CONFIRM_FIELD":
        stuck = new_state["pending_confirmation"]
        known_fields[stuck["field"]] = stuck.get("raw_value")
        field_confidence[stuck["field"]] = 0.5
        new_state["known_fields"] = known_fields
        new_state["field_confidence"] = field_confidence
        new_state["missing_fields"] = [f for f in objectives.all_field_keys(new_state.get("objective", "")) if f not in known_fields]
        new_state["pending_confirmation"] = None

    t0 = time.perf_counter()
    raw_reply = await prompt_builder.generate(
        decision=decision, extraction=extraction, state=new_state, rag_chunks=rag_chunks,
        conversation_policy=conversation_policy, business_identity=business_identity,
        language=new_state.get("language", "en-IN"), recent_turns=recent_turns, llm_client=client,
        engine_mode=engine_mode, response_mode=response_mode, on_speakable_chunk=on_speakable_chunk,
        latency_sink=latency_ms, cancellation_token=cancellation_token, recent_interrupt_count=recent_interrupt_count,
    )
    latency_ms["generation"] = int((time.perf_counter() - t0) * 1000)

    prepend_ack = decision.action in ("ASK_FIELD", "CLARIFY", "CONFIRM_FIELD")
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
        "confirmation_response": extraction.confirmation_response,
        # P3.5 §72 observability: "deterministic" (FastTurnRouter),
        # "mock"/"llm" (extractor.py), further qualified by whether RAG ran
        # and whether generation used the canned fast-response path — see
        # docs/P3_5_CONVERSATION_ENGINE_RESULTS.md for the turn_path
        # distribution this enables measuring.
        "turn_path": extraction.turn_path,
        "rag_ran": bool(decision.rag_query),
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
