from jkr_conversation import closing
from jkr_conversation.objectives import get_objective


def _objective(objective_id: str = "qualify_lead"):
    return get_objective(objective_id)


def test_objective_completed_uses_objective_closing_text_and_has_finality():
    for lang in ("te-en-IN", "hi-en-IN", "en-IN"):
        text = closing.build_closing_text(closing.OBJECTIVE_COMPLETED, objective=_objective(), language=lang)
        assert closing.has_finality_marker(text)


def test_unrecognized_reason_falls_back_to_objective_closing_text():
    # Any reason string the caller might pass that isn't one of the five
    # named constants must still produce a safe, final closing — never an
    # empty or half-formed reply.
    text = closing.build_closing_text("some_future_reason_not_yet_defined", objective=_objective(), language="en-IN")
    assert text == _objective().closing_text["en"]
    assert closing.has_finality_marker(text)


def test_do_not_call_and_wrong_number_route_through_policy_fallback_text():
    from jkr_conversation import policy

    dnc = closing.build_closing_text(closing.DO_NOT_CALL, objective=_objective(), language="te-IN")
    assert dnc == policy.fallback_text(kind="do_not_call", language="te-IN")

    wrong_number = closing.build_closing_text(closing.WRONG_NUMBER, objective=_objective(), language="hi-IN")
    assert wrong_number == policy.fallback_text(kind="wrong_number", language="hi-IN")


def test_human_handoff_and_call_time_limit_have_finality_in_every_language():
    for reason in (closing.HUMAN_HANDOFF, closing.CALL_TIME_LIMIT):
        for lang in ("te-IN", "hi-IN", "en-IN"):
            text = closing.build_closing_text(reason, objective=_objective(), language=lang)
            assert closing.has_finality_marker(text), f"{reason}/{lang} missing a finality phrase: {text!r}"


def test_call_time_limit_fills_in_callback_note_from_known_fields():
    state = {"known_fields": {"preferred_callback_time": "tomorrow evening"}}
    context = closing.build_context(state)
    text = closing.build_closing_text(closing.CALL_TIME_LIMIT, objective=_objective(), language="en-IN", context=context)
    assert "tomorrow evening" in text
    assert "{callback_note}" not in text


def test_call_time_limit_omits_callback_note_when_not_known():
    context = closing.build_context({"known_fields": {}})
    text = closing.build_closing_text(closing.CALL_TIME_LIMIT, objective=_objective(), language="en-IN", context=context)
    assert "{callback_note}" not in text


def test_has_finality_marker_rejects_non_final_text():
    assert not closing.has_finality_marker("if tomorrow morning works, I can reinstate it")


def test_reopened_reaffirm_has_finality_but_is_shorter_than_the_full_closing():
    # Real-call bug: a customer speaking again right after the closing
    # played (grace-period reopen) got the IDENTICAL full closing script
    # repeated verbatim when the objective re-completed with nothing new —
    # reads as a broken robot. The reaffirm text must still be final, but
    # deliberately short, not a repeat of the full objective closing.
    for lang in ("te-IN", "hi-IN", "en-IN"):
        reaffirm = closing.build_closing_text(closing.REOPENED_REAFFIRM, objective=_objective(), language=lang)
        full = closing.build_closing_text(closing.OBJECTIVE_COMPLETED, objective=_objective(), language=lang)
        assert closing.has_finality_marker(reaffirm)
        assert reaffirm != full
        assert len(reaffirm) < len(full)
