from app.pipeline import _build_summary, _classify_outcome, _evaluate_quality


def test_classify_outcome_appointment_booked():
    category, lead_score, reasons = _classify_outcome(
        objective="book_appointment", objective_status="completed",
        known_fields={"reason_for_visit": "root canal", "preferred_date": "tomorrow"},
        transcript_text="",
    )
    assert category == "appointment_booked"
    assert lead_score == "hot"
    assert reasons


def test_classify_outcome_do_not_call_overrides_everything():
    category, lead_score, _ = _classify_outcome(
        objective="book_appointment", objective_status="completed",
        known_fields={"reason_for_visit": "x"}, transcript_text="please do not call again",
    )
    assert category == "do_not_call"
    assert lead_score == "not_qualified"


def test_classify_outcome_unreachable_when_nothing_collected():
    category, lead_score, _ = _classify_outcome(
        objective="book_appointment", objective_status="in_progress", known_fields={}, transcript_text="",
    )
    assert category == "unreachable"
    assert lead_score == "not_qualified"


def test_classify_outcome_interested_when_partial_progress():
    category, _, _ = _classify_outcome(
        objective="book_appointment", objective_status="in_progress",
        known_fields={"reason_for_visit": "cleaning"}, transcript_text="",
    )
    assert category == "interested"


def test_build_summary_includes_known_fields():
    summary = _build_summary(objective="book_appointment", objective_status="completed", known_fields={"preferred_date": "tomorrow"})
    assert "tomorrow" in summary
    assert "completed" in summary


def test_build_summary_handles_no_fields():
    summary = _build_summary(objective="qualify_lead", objective_status="in_progress", known_fields={})
    assert "No information was collected" in summary


class _FakeTurn:
    def __init__(self, text, started_at=None, speaker="agent"):
        self.text = text
        self.started_at = started_at
        self.speaker = speaker


def test_evaluate_quality_flags_disclosure_present():
    agent_turns = [_FakeTurn("నేను AI assistantని.")]
    quality = _evaluate_quality(
        agent_turns=agent_turns, customer_turns=[], meaningful_interruptions=[], total_interruptions=0,
        objective_status="completed", knowledge_events=[], transcript_text="",
    )
    assert quality["disclosure_present"] is True
    assert quality["objective_completed"] is True


def test_evaluate_quality_flags_missing_disclosure():
    agent_turns = [_FakeTurn("Hello, how can I help you today?")]
    quality = _evaluate_quality(
        agent_turns=agent_turns, customer_turns=[], meaningful_interruptions=[], total_interruptions=0,
        objective_status="in_progress", knowledge_events=[], transcript_text="",
    )
    assert quality["disclosure_present"] is False
    assert quality["needs_human_review"] is True


def test_evaluate_quality_detects_repetition():
    agent_turns = [_FakeTurn("Same question again?"), _FakeTurn("Same question again?")]
    quality = _evaluate_quality(
        agent_turns=agent_turns, customer_turns=[], meaningful_interruptions=[], total_interruptions=0,
        objective_status="in_progress", knowledge_events=[], transcript_text="",
    )
    assert quality["repetition_flag"] is True


def test_evaluate_quality_detects_frustration():
    quality = _evaluate_quality(
        agent_turns=[_FakeTurn("AI here")], customer_turns=[], meaningful_interruptions=[], total_interruptions=0,
        objective_status="in_progress", knowledge_events=[], transcript_text="this is such a waste of my time",
    )
    assert quality["customer_frustration_flag"] is True
    assert quality["tone_score"] < 0.5


def test_evaluate_quality_knowledge_grounding_score_from_events():
    class _FakeEvent:
        def __init__(self, matched):
            self.payload = {"matched": matched}

    quality = _evaluate_quality(
        agent_turns=[_FakeTurn("AI assistant here")], customer_turns=[], meaningful_interruptions=[],
        total_interruptions=0, objective_status="in_progress",
        knowledge_events=[_FakeEvent(True), _FakeEvent(False)], transcript_text="",
    )
    assert quality["knowledge_grounding_score"] == 0.5
