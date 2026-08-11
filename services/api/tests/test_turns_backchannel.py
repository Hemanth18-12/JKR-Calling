from __future__ import annotations

from app.modules.live_call.turns import backchannel


def test_short_phrase_not_expecting_confirmation_is_backchannel_but_not_answer():
    result = backchannel.classify("hmm", expecting_confirmation=False)
    assert result.is_backchannel_shaped is True
    assert result.likely_real_answer is False


def test_short_phrase_expecting_confirmation_is_real_answer():
    result = backchannel.classify("haa", expecting_confirmation=True)
    assert result.is_backchannel_shaped is True
    assert result.likely_real_answer is True


def test_ordinary_sentence_is_not_backchannel_shaped():
    result = backchannel.classify("I need root canal treatment tomorrow", expecting_confirmation=False)
    assert result.is_backchannel_shaped is False
    assert result.likely_real_answer is False


def test_empty_text_is_not_backchannel_shaped():
    result = backchannel.classify("", expecting_confirmation=True)
    assert result.is_backchannel_shaped is False


def test_case_and_whitespace_insensitive():
    result = backchannel.classify("  Avunu  ", expecting_confirmation=True)
    assert result.is_backchannel_shaped is True
    assert result.likely_real_answer is True


def test_no_expecting_confirmation_kwarg_required_explicitly():
    # Regression guard: a caller that forgets to pass expecting_confirmation
    # should get a TypeError, not a silent wrong default in production code
    # (backchannel.classify has no default — always explicit at call sites).
    import pytest

    with pytest.raises(TypeError):
        backchannel.classify("haa")  # type: ignore[call-arg]
