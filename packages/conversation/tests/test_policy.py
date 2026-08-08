from jkr_conversation.policy import apply_backstop, fallback_text
from jkr_conversation.schemas import ExtractionResult


def _extraction(**overrides) -> ExtractionResult:
    defaults = dict(turn_intent="answer", is_mock=False)
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def test_backstop_overrides_a_wrong_llm_classification():
    # The LLM (or a fake standing in for it in this test) says do_not_call=False
    # despite the customer's actual words — the keyword backstop must catch
    # this regardless, since this is what makes "the LLM cannot override
    # do-not-call" literally true rather than a hopeful prompt instruction.
    wrong_extraction = _extraction(do_not_call=False)
    result = apply_backstop(wrong_extraction, raw_text="please do not call again")
    assert result.do_not_call is True


def test_backstop_is_a_noop_when_extraction_already_agrees():
    correct = _extraction(do_not_call=True)
    result = apply_backstop(correct, raw_text="please do not call again")
    assert result is correct  # no unnecessary copy when nothing changed


def test_backstop_catches_wrong_number_missed_by_extraction():
    wrong_extraction = _extraction(wrong_number=False)
    result = apply_backstop(wrong_extraction, raw_text="wrong number, sorry")
    assert result.wrong_number is True


def test_backstop_catches_human_handoff_missed_by_extraction():
    wrong_extraction = _extraction(wants_human=False)
    result = apply_backstop(wrong_extraction, raw_text="I want to speak to a real person please")
    assert result.wants_human is True


def test_backstop_does_not_touch_unrelated_fields():
    original = _extraction(extracted_fields={"reason_for_visit": "root canal"})
    result = apply_backstop(original, raw_text="just a normal answer")
    assert result.extracted_fields == {"reason_for_visit": "root canal"}


def test_fallback_text_per_language():
    te = fallback_text(kind="do_not_call", language="te-IN")
    hi = fallback_text(kind="do_not_call", language="hi-IN")
    en = fallback_text(kind="do_not_call", language="en-IN")
    assert te != hi != en
    assert "మళ్ళీ కాల్" in te or "కాల్" in te
