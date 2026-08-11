from __future__ import annotations

from app.modules.live_call.turns import semantic


def test_complete_simple_statement():
    assert semantic.evaluate("Tomorrow evening.", language_code="en-IN").complete is True


def test_complete_question():
    result = semantic.evaluate("Root canal cost entha?", language_code="te-en-IN")
    assert result.complete is True
    assert result.reason == "ends_with_terminal_punctuation"


def test_incomplete_trailing_ellipsis():
    assert semantic.evaluate("Tomorrow...", language_code="en-IN").complete is False


def test_incomplete_trailing_continuation_marker_english():
    result = semantic.evaluate("I need root canal but", language_code="en-IN")
    assert result.complete is False
    assert result.reason == "trailing_continuation_marker"


def test_incomplete_trailing_continuation_marker_telugu():
    result = semantic.evaluate("Root canal ante", language_code="te-en-IN")
    assert result.complete is False


def test_incomplete_trailing_continuation_marker_hindi():
    result = semantic.evaluate("Mujhe lekin", language_code="hi-en-IN")
    assert result.complete is False


def test_complete_no_trailing_marker_no_punctuation_defaults_complete():
    # STT text commonly arrives with no punctuation at all — absence of a
    # period must never itself be treated as incompleteness evidence.
    result = semantic.evaluate("CSE kavali", language_code="te-en-IN")
    assert result.complete is True
    assert result.reason == "default_complete"


def test_empty_text_is_incomplete():
    assert semantic.evaluate("", language_code="en-IN").complete is False
    assert semantic.evaluate("   ", language_code="en-IN").complete is False


def test_number_sequence_pause_treated_as_incomplete():
    # "My rank is..." — spec §21/§22
    result = semantic.evaluate("My rank is...", language_code="en-IN")
    assert result.complete is False


def test_unrecognized_language_prefix_falls_back_to_english_markers():
    result = semantic.evaluate("Tomorrow but", language_code="xx-XX")
    assert result.complete is False
