from jkr_conversation.state import (
    classify_provisional_outcome,
    compute_missing_optional_fields,
    compute_missing_required_fields,
    new_conversation_state,
)


def test_new_state_shape_is_backward_compatible():
    # services/intelligence-worker/app/pipeline.py and
    # services/campaign-worker/app/dialer.py read known_fields/objective_status/
    # objective/next_best_action by these exact names — must never change.
    s = new_conversation_state(objective="book_appointment", language="te-en-IN")
    assert s["known_fields"] == {}
    assert s["objective_status"] == "in_progress"
    assert s["objective"] == "book_appointment"
    assert s["next_best_action"] == "ask_question"
    assert s["awaiting_field"] == "reason_for_visit"  # pre-seeded to the first field


def test_new_state_has_additive_fields():
    s = new_conversation_state(objective="qualify_lead", language="en-IN")
    for key in ("field_confidence", "field_ask_counts", "tool_results", "turn_count", "started_at", "wrong_number"):
        assert key in s


def test_compute_missing_required_fields_excludes_known():
    s = new_conversation_state(objective="book_appointment", language="en-IN")
    s["known_fields"]["reason_for_visit"] = "root canal"
    assert compute_missing_required_fields(s) == ["preferred_date", "preferred_time"]


def test_compute_missing_optional_fields():
    s = new_conversation_state(objective="collect_feedback", language="en-IN")
    assert compute_missing_optional_fields(s) == ["improvement_area"]
    s["known_fields"]["improvement_area"] = "faster follow-up"
    assert compute_missing_optional_fields(s) == []


def test_classify_outcome_do_not_call_beats_everything():
    s = new_conversation_state(objective="book_appointment", language="en-IN")
    s["known_fields"] = {"reason_for_visit": "root canal"}
    s["objective_status"] = "completed"
    s["do_not_call"] = True
    assert classify_provisional_outcome(s) == ("do_not_call", "not_qualified")


def test_classify_outcome_wrong_number():
    s = new_conversation_state(objective="book_appointment", language="en-IN")
    s["wrong_number"] = True
    assert classify_provisional_outcome(s) == ("wrong_number", "not_qualified")


def test_classify_outcome_appointment_booked():
    s = new_conversation_state(objective="book_appointment", language="en-IN")
    s["known_fields"] = {"reason_for_visit": "x", "preferred_date": "y", "preferred_time": "z"}
    s["objective_status"] = "completed"
    assert classify_provisional_outcome(s) == ("appointment_booked", "hot")


def test_classify_outcome_qualified_non_appointment_objective():
    s = new_conversation_state(objective="qualify_lead", language="en-IN")
    s["known_fields"] = {"interest_detail": "x"}
    s["objective_status"] = "completed"
    assert classify_provisional_outcome(s) == ("qualified", "warm")


def test_classify_outcome_interested_when_incomplete_but_has_fields():
    s = new_conversation_state(objective="qualify_lead", language="en-IN")
    s["known_fields"] = {"interest_detail": "x"}
    assert classify_provisional_outcome(s) == ("interested", "warm")


def test_classify_outcome_unreachable_when_nothing_collected():
    s = new_conversation_state(objective="qualify_lead", language="en-IN")
    assert classify_provisional_outcome(s) == ("unreachable", "not_qualified")


def test_classify_outcome_needs_human():
    s = new_conversation_state(objective="qualify_lead", language="en-IN")
    s["objective_status"] = "needs_human"
    s["known_fields"] = {"interest_detail": "x"}
    assert classify_provisional_outcome(s) == ("needs_human", "warm")
