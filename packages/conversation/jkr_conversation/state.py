"""Canonical ConversationState shape — the single source of truth for what
gets persisted to CallSession.state (JSONB, packages/db/jkr_db/models/calls.py).

A superset of the dict services/voice-worker/app/conversation_engine.py has
built by hand until now: every key that services/intelligence-worker/app/pipeline.py
and services/campaign-worker/app/dialer.py already read (`known_fields`,
`objective_status`, `objective`, `next_best_action`) keeps its exact name and
semantics — this refactor must not require touching those two files' field
names, only (for pipeline.py) how confidence is looked up (see
jkr_conversation/README notes in the plan doc).
"""

from __future__ import annotations

from datetime import UTC, datetime

from jkr_conversation import objectives

TERMINAL_OBJECTIVE_STATUSES = {"completed", "needs_human", "do_not_call", "wrong_number", "declined"}


def new_conversation_state(*, objective: str, language: str) -> dict:
    """Used by BOTH services/voice-worker's start_session and services/api's
    start_live_test_call, so both call paths write the identical shape into
    CallSession.state from turn zero — today only the mock path does this at
    all."""
    field_keys = objectives.all_field_keys(objective)
    return {
        # --- unchanged names/semantics from the pre-refactor mock engine ---
        "objective": objective,
        "language": language,
        "intent": None,
        "sentiment": "neutral",
        "known_fields": {},
        "missing_fields": list(field_keys),
        "uncertain_fields": [],
        "risk_flags": [],
        "customer_requested_human": False,
        "do_not_call": False,
        "next_best_action": "ask_question",
        "objective_status": "in_progress",
        "asked_count": 0,
        "awaiting_field": field_keys[0] if field_keys else None,
        # --- new, additive ---
        "field_confidence": {},
        "field_ask_counts": {},
        "tool_results": {},
        "turn_count": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "wrong_number": False,
        "last_turn_debug": None,
        # {"field": str, "raw_value": str, "candidate_value": str, "semantic_confidence": float} | None —
        # at most one field pending confirmation at a time, mirroring the
        # existing single-target-field pattern already used by CLARIFY/ASK_FIELD.
        "pending_confirmation": None,
    }


def compute_missing_required_fields(state: dict) -> list[str]:
    """Recomputed fresh from known_fields + the objective definition, rather
    than trusting state["missing_fields"] blindly — that key is kept for
    backward-compatible display purposes but must never drift from this as
    the source of truth for planning decisions."""
    objective = state.get("objective", objectives.DEFAULT_OBJECTIVE_ID)
    required = objectives.required_field_keys(objective)
    known = state.get("known_fields", {})
    return [f for f in required if f not in known]


def compute_missing_optional_fields(state: dict) -> list[str]:
    objective_id = state.get("objective", objectives.DEFAULT_OBJECTIVE_ID)
    all_fields = objectives.get_objective(objective_id).fields
    known = state.get("known_fields", {})
    return [f.key for f in all_fields if not f.required and f.key not in known]


def classify_provisional_outcome(state: dict) -> tuple[str, str]:
    """Returns (category, lead_score) matching CallOutcomeCategory's real enum
    values. Consolidates the near-duplicate if/elif ladder that used to live
    separately in conversation_engine.py::end_session() and (a cruder version
    of it) in live_call/service.py::_finalize_call() — do-not-call/wrong-number
    checked first now that state carries a real signal for both, not a
    post-hoc keyword scan over the transcript."""
    if state.get("do_not_call"):
        return "do_not_call", "not_qualified"
    if state.get("wrong_number"):
        return "wrong_number", "not_qualified"

    objective_status = state.get("objective_status", "in_progress")
    objective = state.get("objective", "")
    known_fields = state.get("known_fields", {})

    if objective_status == "needs_human":
        return "needs_human", "warm" if known_fields else "not_qualified"
    if objective_status == "completed" and objective == "book_appointment":
        return "appointment_booked", "hot"
    if objective_status == "completed" and known_fields:
        return "qualified", "warm"
    if known_fields:
        return "interested", "warm"
    return "unreachable", "not_qualified"
