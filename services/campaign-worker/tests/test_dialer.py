import uuid

from app.dialer import (
    clamp_seconds,
    next_retry_delay_minutes,
    pick_customer_reply,
    retry_reason_for_outcome,
    should_stop_conversation,
    simulate_connect_outcome,
)

# Fixed, not uuid.uuid4() — the function is documented as deterministic
# specifically so tests are reproducible; a random contact_id here would
# make test_simulate_connect_outcome_varies_by_attempt_number genuinely
# flaky (an ~0.15% chance per run of landing in the "answered" bucket all
# 29 times, since that bucket is 80% wide) — caught live via a real CI-style
# flake, not reasoned out in advance. See docs/IMPLEMENTATION_CHECKLIST.md.
_CONTACT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def test_simulate_connect_outcome_is_deterministic():
    first = simulate_connect_outcome(_CONTACT_ID, 1)
    second = simulate_connect_outcome(_CONTACT_ID, 1)
    assert first == second


def test_simulate_connect_outcome_varies_by_attempt_number():
    outcomes = {simulate_connect_outcome(_CONTACT_ID, n) for n in range(1, 100)}
    # Not every attempt should land the same bucket — proves attempt_number
    # actually participates in the hash rather than being ignored. Range
    # widened to 100 (0.8^100 is negligible) rather than relying on a
    # specific contact_id alone to rule out flakiness.
    assert len(outcomes) > 1


def test_simulate_connect_outcome_only_valid_values():
    for n in range(1, 50):
        assert simulate_connect_outcome(_CONTACT_ID, n) in {"answered", "no_answer", "busy", "provider_error"}


def test_simulate_connect_outcome_mostly_answered():
    outcomes = [simulate_connect_outcome(_CONTACT_ID, n) for n in range(1, 200)]
    answered_ratio = outcomes.count("answered") / len(outcomes)
    assert answered_ratio > 0.6


def test_retry_reason_for_outcome_maps_known_values():
    assert retry_reason_for_outcome("no_answer") == "no_answer"
    assert retry_reason_for_outcome("busy") == "busy"
    assert retry_reason_for_outcome("provider_error") == "provider_error"


def test_retry_reason_for_outcome_defaults_to_provider_error():
    assert retry_reason_for_outcome("something_unexpected") == "provider_error"


def test_next_retry_delay_minutes_uses_backoff_schedule():
    backoff = [30, 120, 480]
    assert next_retry_delay_minutes(1, backoff) == 30
    assert next_retry_delay_minutes(2, backoff) == 120
    assert next_retry_delay_minutes(3, backoff) == 480


def test_next_retry_delay_minutes_clamps_beyond_schedule_length():
    backoff = [30, 120]
    assert next_retry_delay_minutes(5, backoff) == 120


def test_next_retry_delay_minutes_falls_back_when_empty():
    assert next_retry_delay_minutes(1, []) == 30


def test_pick_customer_reply_round_robins():
    replies = [pick_customer_reply(i) for i in range(12)]
    assert replies[0] == replies[6]
    assert len(set(replies)) > 1


def test_should_stop_conversation_true_on_close_action():
    assert should_stop_conversation({"next_best_action": "close_conversation"}) is True


def test_should_stop_conversation_false_otherwise():
    assert should_stop_conversation({"next_best_action": "ask_question"}) is False
    assert should_stop_conversation({}) is False


def test_clamp_seconds_respects_bounds():
    assert clamp_seconds(1) == 5
    assert clamp_seconds(10_000) == 300
    assert clamp_seconds(60) == 60
