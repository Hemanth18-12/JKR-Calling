from datetime import UTC, datetime

from jkr_db.tools_engine import REAL_SIDE_EFFECT_TOOLS, parse_fuzzy_datetime

# A fixed Monday for deterministic day-of-week math.
_MONDAY = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def test_parse_fuzzy_datetime_recognizes_tomorrow():
    result = parse_fuzzy_datetime("tomorrow", None, now=_MONDAY)
    assert result.date() == datetime(2026, 8, 4, tzinfo=UTC).date()


def test_parse_fuzzy_datetime_recognizes_day_name():
    result = parse_fuzzy_datetime("Saturday works for me", None, now=_MONDAY)
    assert result.weekday() == 5  # Saturday


def test_parse_fuzzy_datetime_recognizes_time_of_day_word():
    result = parse_fuzzy_datetime("tomorrow", "morning", now=_MONDAY)
    assert result.hour == 10


def test_parse_fuzzy_datetime_recognizes_explicit_hour():
    result = parse_fuzzy_datetime("tomorrow", "3pm works", now=_MONDAY)
    assert result.hour == 15


def test_parse_fuzzy_datetime_falls_back_on_unparseable_text():
    result = parse_fuzzy_datetime("Sure, tell me more about that.", None, now=_MONDAY)
    assert result.date() == datetime(2026, 8, 6, tzinfo=UTC).date()
    assert result.hour == 11


def test_parse_fuzzy_datetime_handles_none_input():
    result = parse_fuzzy_datetime(None, None, now=_MONDAY)
    assert result > _MONDAY


def test_real_side_effect_tools_matches_documented_set():
    assert REAL_SIDE_EFFECT_TOOLS == {
        "book_appointment", "reschedule_appointment", "cancel_appointment",
        "create_human_callback", "send_whatsapp", "send_sms",
    }
