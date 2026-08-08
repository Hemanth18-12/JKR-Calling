import uuid

from app.turn_manager import InterruptionClassification, TurnManager, estimate_speaking_duration_ms


def make_manager(**kwargs) -> TurnManager:
    defaults = {
        "call_id": uuid.uuid4(),
        "accidental_interruption_phrases": ["hmm", "okay", "haa", "అవును", "right"],
        "min_interruption_ms": 250,
    }
    defaults.update(kwargs)
    return TurnManager(**defaults)


def test_no_agent_turn_in_flight_is_not_an_interruption():
    tm = make_manager()
    result = tm.handle_user_utterance("hello", now=0.0)
    assert result.classification == InterruptionClassification.NONE
    assert result.stop_latency_ms is None


def test_short_acknowledgement_during_agent_speech_is_false_positive():
    tm = make_manager()
    tm.start_agent_turn("This is a fairly long sentence that will take a while to say out loud.", now=0.0)
    # Well within the speaking window (duration for this text is > 1s).
    result = tm.handle_user_utterance("okay", now=0.3)
    assert result.classification == InterruptionClassification.FALSE_POSITIVE
    assert tm.agent_speaking is True  # agent keeps "speaking" — not cancelled
    assert tm.false_interruption_count == 1
    assert tm.user_interruption_count == 0


def test_real_utterance_during_agent_speech_is_meaningful_interruption():
    tm = make_manager()
    turn = tm.start_agent_turn("This is a fairly long sentence that will take a while to say out loud.", now=0.0)
    result = tm.handle_user_utterance("wait, I have a different question", now=0.5)
    assert result.classification == InterruptionClassification.MEANINGFUL
    assert result.cancelled_sequence_id == turn.sequence_id
    assert result.stop_latency_ms is not None
    assert result.stop_latency_ms < 300  # spec §11: stop should be near-instant
    assert tm.agent_speaking is False
    assert tm.user_interruption_count == 1


def test_utterance_after_agent_naturally_finished_is_not_an_interruption():
    tm = make_manager()
    tm.start_agent_turn("Short.", now=0.0)
    duration_s = estimate_speaking_duration_ms("Short.") / 1000
    result = tm.handle_user_utterance("okay now my turn", now=duration_s + 1.0)
    assert result.classification == InterruptionClassification.NONE
    assert tm.agent_speaking is False


def test_below_min_interruption_ms_is_treated_as_false_positive_even_if_not_a_known_phrase():
    tm = make_manager(min_interruption_ms=500)
    tm.start_agent_turn("A reasonably long sentence to give us time to interrupt mid-flight.", now=0.0)
    # "wait what" is not in the phrase list but arrives too fast (100ms) to
    # plausibly be a real barge-in rather than audio-timing noise.
    result = tm.handle_user_utterance("wait what", now=0.1)
    assert result.classification == InterruptionClassification.FALSE_POSITIVE


def test_turn_refs_increment_and_are_unique():
    tm = make_manager()
    refs = {tm.next_turn_ref("agent") for _ in range(5)}
    assert len(refs) == 5


def test_estimate_speaking_duration_scales_with_text_length():
    short = estimate_speaking_duration_ms("Hi")
    long = estimate_speaking_duration_ms("This is a much longer sentence with many more characters in it.")
    assert long > short
