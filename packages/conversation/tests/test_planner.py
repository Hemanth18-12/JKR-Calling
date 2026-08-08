from datetime import UTC, datetime, timedelta

from jkr_conversation import planner
from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult
from jkr_conversation.state import new_conversation_state

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)


def _extraction(**overrides) -> ExtractionResult:
    defaults = dict(turn_intent="answer", is_mock=True)
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def _state(objective: str, language: str = "en-IN") -> dict:
    # new_conversation_state() stamps started_at with the REAL wall-clock
    # time, not the fixed NOW used throughout this file — pin it to NOW so
    # the duration-ceiling check in planner.decide() never spuriously
    # triggers depending on what time of day the suite happens to run.
    state = new_conversation_state(objective=objective, language=language)
    state["started_at"] = NOW.isoformat()
    return state


def test_do_not_call_beats_every_other_competing_signal():
    extraction = _extraction(do_not_call=True, wants_human=True, detected_question=True, rewritten_query="cost?")
    state = _state("book_appointment", "en-IN")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "SAFETY_STOP"
    assert decision.reason == "do_not_call_requested"


def test_wrong_number_also_triggers_safety_stop():
    extraction = _extraction(wrong_number=True)
    state = _state("book_appointment", "en-IN")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "SAFETY_STOP"
    assert decision.reason == "wrong_number"


def test_human_request_outranks_answering_a_question_asked_the_same_turn():
    extraction = _extraction(wants_human=True, detected_question=True, rewritten_query="do you have parking?")
    state = _state("book_appointment", "en-IN")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "HUMAN_HANDOFF"
    assert decision.answer_question_first is False  # the question does NOT get answered this turn


def test_question_priority_still_asks_the_next_field_but_answers_first():
    # Locks in the design: "answer the question" is an annotation on
    # ASK_FIELD, not its own exclusive rung — the flow doesn't stall.
    extraction = _extraction(detected_question=True, rewritten_query="hostel undha?")
    state = _state("book_appointment", "en-IN")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "ASK_FIELD"
    assert decision.answer_question_first is True
    assert decision.rag_query == "hostel undha?"
    assert decision.target_field == "reason_for_visit"  # first missing required field


def test_low_confidence_extraction_triggers_clarify_not_a_silent_guess():
    extraction = _extraction(
        extracted_fields={"reason_for_visit": "root canal maybe"},
        field_confidence={"reason_for_visit": 0.3},
        uncertain_fields={"reason_for_visit": ["root canal", "cleaning"]},
    )
    state = _state("book_appointment", "en-IN")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "CLARIFY"
    assert decision.target_field == "reason_for_visit"


def test_clarify_is_skipped_when_policy_disables_it():
    extraction = _extraction(
        extracted_fields={"reason_for_visit": "root canal maybe"}, field_confidence={"reason_for_visit": 0.3},
    )
    state = _state("book_appointment", "en-IN")
    policy = ConversationPolicySnapshot(clarification_behavior="accept_best_guess")
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=policy, now=NOW)
    assert decision.action != "CLARIFY"


def test_repeated_question_cap_skips_a_stuck_field():
    extraction = _extraction()  # no fields extracted this turn — customer didn't answer
    state = _state("book_appointment", "en-IN")
    state["field_ask_counts"] = {"reason_for_visit": planner.MAX_ASKS_PER_FIELD}  # already asked twice, still unknown
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "ASK_FIELD"
    assert decision.target_field == "preferred_date"  # skipped the stuck field, moved to the next one


def test_all_required_fields_exhausted_completes_objective():
    extraction = _extraction()
    state = _state("book_appointment", "en-IN")
    state["field_ask_counts"] = {
        "reason_for_visit": planner.MAX_ASKS_PER_FIELD,
        "preferred_date": planner.MAX_ASKS_PER_FIELD,
        "preferred_time": planner.MAX_ASKS_PER_FIELD,
    }
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "COMPLETE_OBJECTIVE"


def test_optional_field_asked_after_all_required_fields_known():
    extraction = _extraction()
    state = _state("collect_feedback", "en-IN")
    state["known_fields"] = {"satisfaction": "great"}
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "ASK_FIELD"
    assert decision.target_field == "improvement_area"


def test_completes_when_required_and_askable_optional_fields_are_all_known():
    extraction = _extraction()
    state = _state("collect_feedback", "en-IN")
    state["known_fields"] = {"satisfaction": "great", "improvement_area": "nothing"}
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=ConversationPolicySnapshot(), now=NOW)
    assert decision.action == "COMPLETE_OBJECTIVE"


def test_max_turns_ceiling_forces_completion_even_mid_objective():
    extraction = _extraction()
    state = _state("book_appointment", "en-IN")
    state["turn_count"] = 30
    policy = ConversationPolicySnapshot(max_turns=30)
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=policy, now=NOW)
    assert decision.action == "COMPLETE_OBJECTIVE"
    assert decision.reason == "max_turns_reached"


def test_max_duration_ceiling_forces_completion():
    extraction = _extraction()
    state = _state("book_appointment", "en-IN")
    state["started_at"] = (NOW - timedelta(seconds=400)).isoformat()
    policy = ConversationPolicySnapshot(max_call_duration_seconds=300)
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=policy, now=NOW)
    assert decision.action == "COMPLETE_OBJECTIVE"
    assert decision.reason == "max_duration_reached"


def test_ceiling_does_not_trigger_before_the_limit():
    extraction = _extraction()
    state = _state("book_appointment", "en-IN")
    state["turn_count"] = 5
    state["started_at"] = NOW.isoformat()
    policy = ConversationPolicySnapshot(max_turns=30, max_call_duration_seconds=300)
    decision = planner.decide(extraction=extraction, state=state, conversation_policy=policy, now=NOW)
    assert decision.action == "ASK_FIELD"  # normal flow, ceiling not reached
