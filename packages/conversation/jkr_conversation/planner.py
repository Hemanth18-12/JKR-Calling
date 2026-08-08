"""Deterministic next-action planner — pure Python, zero LLM calls, zero I/O.

This is deliberately NOT "ask the LLM what to do next": the priority ladder
below is what makes do-not-call, repeated-question prevention, and
question-before-qualification actually enforceable, rather than best-effort
model behavior. extractor.py decides WHAT the customer said; this module
decides WHAT HAPPENS NEXT; prompt_builder.py decides HOW TO PHRASE IT.

"Answer the customer's question" is deliberately a non-exclusive annotation
(`answer_question_first`/`rag_query`) layered onto whichever action wins,
not its own rung on the ladder — the existing mock engine already answers-
and-asks-the-next-question in the same turn (knowledge_prefix + question_text
in the old conversation_engine.py), and forcing "answer" into an exclusive
priority slot would regress to one thing per turn, working against the
max_turns ceiling instead of with it.
"""

from __future__ import annotations

from datetime import datetime

from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult, PlannerDecision
from jkr_conversation.state import compute_missing_optional_fields, compute_missing_required_fields

# A field asked (and left unanswered/unextracted) this many times is skipped
# rather than asked forever — protects against looping when a real customer
# is stubborn, or (today, since campaign-worker never sets an API key) a
# campaign's auto-played generic reply never maps onto any real field.
MAX_ASKS_PER_FIELD = 2

# Below this extraction confidence on a field just captured this turn, ask a
# clarification instead of silently trusting the value — conversation_policy's
# clarification_behavior == "ask_dont_guess" is the existing knob this gates on.
LOW_CONFIDENCE_THRESHOLD = 0.5


def decide(
    *, extraction: ExtractionResult, state: dict, conversation_policy: ConversationPolicySnapshot, now: datetime
) -> PlannerDecision:
    # 1. Safety stop — do-not-call/wrong-number always wins, regardless of
    # any other signal active in the same turn (policy.apply_backstop has
    # already forced these True on a keyword match even if the LLM missed it).
    if extraction.do_not_call:
        return PlannerDecision(action="SAFETY_STOP", reason="do_not_call_requested")
    if extraction.wrong_number:
        return PlannerDecision(action="SAFETY_STOP", reason="wrong_number")

    # Safety-net ceiling — a normal call should never reach this (it should
    # reach COMPLETE_OBJECTIVE on its own first); this exists so a stuck or
    # unusually long conversation still ends deterministically.
    turn_count = state.get("turn_count", 0)
    if turn_count >= conversation_policy.max_turns:
        return PlannerDecision(action="COMPLETE_OBJECTIVE", reason="max_turns_reached")
    started_at_raw = state.get("started_at")
    if started_at_raw:
        try:
            elapsed = (now - datetime.fromisoformat(started_at_raw)).total_seconds()
            if elapsed >= conversation_policy.max_call_duration_seconds:
                return PlannerDecision(action="COMPLETE_OBJECTIVE", reason="max_duration_reached")
        except ValueError:
            pass

    # 2. Explicit human request outranks everything below, including
    # answering a question the customer asked in the same breath.
    if extraction.wants_human and conversation_policy.human_transfer_enabled:
        return PlannerDecision(action="HUMAN_HANDOFF", reason="customer_requested_human")

    rag_query = extraction.rewritten_query if extraction.detected_question else None

    # 3. Clarify a field just captured with low confidence — "never silently
    # guess," per conversation_policy.clarification_behavior.
    if conversation_policy.clarification_behavior == "ask_dont_guess":
        low_confidence = [(f, c) for f, c in extraction.field_confidence.items() if c < LOW_CONFIDENCE_THRESHOLD]
        if low_confidence:
            target_field = low_confidence[0][0]
            return PlannerDecision(
                action="CLARIFY", reason="low_confidence_extraction", target_field=target_field,
                answer_question_first=bool(rag_query), rag_query=rag_query, objection=extraction.objection,
            )

    field_ask_counts = state.get("field_ask_counts", {})

    # 4. Ask the highest-priority still-missing required field, skipping any
    # that have already been asked past the cap without ever filling.
    askable_required = [f for f in compute_missing_required_fields(state) if field_ask_counts.get(f, 0) < MAX_ASKS_PER_FIELD]
    if askable_required:
        return PlannerDecision(
            action="ASK_FIELD", reason="missing_required_field", target_field=askable_required[0],
            answer_question_first=bool(rag_query), rag_query=rag_query, objection=extraction.objection,
        )

    # Optional fields rank below required ones, same ask-cap logic.
    askable_optional = [f for f in compute_missing_optional_fields(state) if field_ask_counts.get(f, 0) < MAX_ASKS_PER_FIELD]
    if askable_optional:
        return PlannerDecision(
            action="ASK_FIELD", reason="missing_optional_field", target_field=askable_optional[0],
            answer_question_first=bool(rag_query), rag_query=rag_query, objection=extraction.objection,
        )

    # 5. Every required (and askable optional) field is filled or exhausted
    # its ask-cap — the objective is as done as it's going to get.
    return PlannerDecision(
        action="COMPLETE_OBJECTIVE", reason="all_fields_collected",
        answer_question_first=bool(rag_query), rag_query=rag_query, objection=extraction.objection,
    )
