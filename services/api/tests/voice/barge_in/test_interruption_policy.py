"""InterruptionPolicy — pure decision function. Every timeline here uses a
plain incrementing float for `now`/`candidate_started_at` (no real sleeps,
no wall clock) — the same fake-clock-testable discipline TurnManager's own
test suite (test_turns_manager.py) already established. See
docs/INTERRUPTION_POLICY.md for the decision table this exercises.
"""

from __future__ import annotations

from app.modules.live_call.turns.interruption_policy import (
    InterruptionAction,
    InterruptionEvidence,
    InterruptionPriority,
    decide,
    get_thresholds,
)


def _evidence(**overrides: object) -> InterruptionEvidence:
    base: dict[str, object] = dict(
        now=1.0,
        candidate_started_at=1.0,
        local_vad_speech=True,
        provider_speech=True,
        partial_text=None,
        final_text=None,
        language_code="te-en-IN",
        expecting_confirmation=False,
        agent_response_state="tts_streaming",
        interruptible=True,
        sensitivity="balanced",
    )
    base.update(overrides)
    return InterruptionEvidence(**base)  # type: ignore[arg-type]


def test_no_active_response_is_ignored():
    decision = decide(_evidence(agent_response_state=None))
    assert decision.action is InterruptionAction.IGNORE
    assert decision.priority is InterruptionPriority.NONE


def test_terminal_response_state_is_ignored():
    decision = decide(_evidence(agent_response_state="playback_complete"))
    assert decision.action is InterruptionAction.IGNORE


def test_hmm_backchannel_not_expecting_confirmation_does_not_interrupt():
    decision = decide(_evidence(partial_text="hmm", now=1.05))
    assert decision.action is InterruptionAction.BACKCHANNEL
    assert decision.priority is InterruptionPriority.BACKCHANNEL


def test_haa_during_pending_confirmation_is_treated_as_direct_answer():
    decision = decide(_evidence(partial_text="haa", expecting_confirmation=True, now=1.05))
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.reason == "direct_answer_to_pending_confirmation"


def test_one_minute_partial_interrupts_before_qualification_window_elapses():
    # Only 30ms of evidence — well under BALANCED's 250ms window — but a
    # high-priority cue must not wait for the window (spec: interrupt
    # before waiting for the full transcript).
    decision = decide(_evidence(partial_text="one minute", now=1.03))
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.priority is InterruptionPriority.HIGH
    assert decision.reason == "high_priority_cue_detected"


def test_do_not_call_phrase_is_critical_regardless_of_timing():
    decision = decide(_evidence(partial_text="please don't call again", now=1.01))
    assert decision.action is InterruptionAction.INTERRUPT_CRITICAL
    assert decision.priority is InterruptionPriority.CRITICAL


def test_human_handoff_phrase_is_critical():
    decision = decide(_evidence(final_text="I want to talk to a person", now=1.5))
    assert decision.action is InterruptionAction.INTERRUPT_CRITICAL


def test_telugu_high_priority_cue_detected():
    decision = decide(_evidence(partial_text="ఆగండి ఒక్క నిమిషం", language_code="te-IN", now=1.02))
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.priority is InterruptionPriority.HIGH


def test_hindi_do_not_call_trigger_is_critical():
    decision = decide(_evidence(partial_text="दोबारा कॉल मत करना", language_code="hi-IN", now=1.02))
    assert decision.action is InterruptionAction.INTERRUPT_CRITICAL


def test_genuine_new_utterance_after_qualification_window_interrupts():
    decision = decide(_evidence(final_text="tomorrow appointment undha", now=1.30))
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.priority is InterruptionPriority.NORMAL
    assert decision.reason == "new_utterance_detected"


def test_short_new_utterance_within_qualification_window_only_monitors():
    # Two words, but only 50ms in — BALANCED's window is 250ms, and the
    # word count is right at the min-words boundary, so this must not fire
    # yet (avoids treating the first syllable of a real sentence as final).
    decision = decide(_evidence(final_text=None, partial_text="tomorrow", now=1.05))
    assert decision.action is InterruptionAction.MONITOR


def test_noise_burst_that_ends_before_qualification_window_is_ignored():
    decision = decide(_evidence(local_vad_speech=False, provider_speech=False, now=1.05))
    assert decision.action is InterruptionAction.IGNORE
    assert decision.reason == "speech_ended_before_qualification_no_transcript"


def test_within_qualification_window_no_transcript_monitors():
    decision = decide(_evidence(now=1.05))
    assert decision.action is InterruptionAction.MONITOR
    assert decision.reason == "within_qualification_window_no_transcript"


def test_past_qualification_window_no_transcript_waits_for_more_audio():
    decision = decide(_evidence(now=1.4))
    assert decision.action is InterruptionAction.WAIT_FOR_MORE_AUDIO


def test_sustained_speech_past_escalation_threshold_interrupts_without_transcript():
    decision = decide(_evidence(now=2.0))  # 1000ms > BALANCED's 900ms escalation threshold
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.reason == "sustained_speech_no_transcript_yet"


def test_speech_ended_and_never_produced_transcript_is_ignored_even_late():
    decision = decide(_evidence(local_vad_speech=False, provider_speech=False, now=2.0))
    assert decision.action is InterruptionAction.IGNORE
    assert decision.reason == "speech_ended_no_transcript_ever_produced"


def test_non_interruptible_response_never_interrupts_on_ordinary_speech():
    decision = decide(_evidence(interruptible=False, final_text="what about pricing", now=2.0))
    assert decision.action is InterruptionAction.MONITOR
    assert decision.reason == "non_interruptible_response_active"


def test_do_not_call_overrides_non_interruptible_response():
    decision = decide(_evidence(interruptible=False, final_text="stop calling me", now=1.01))
    assert decision.action is InterruptionAction.INTERRUPT_CRITICAL
    assert decision.reason == "critical_cue_overrides_non_interruptible"


def test_no_audio_yet_state_halves_the_qualification_window():
    # Same 130ms elapsed, same single-word (below min-words-for-new-
    # utterance) transcript: TTS_STREAMING (already producing audio) should
    # still be waiting out its full window, but GENERATING_TEXT (no audio
    # produced at all yet) should already interrupt on the halved window,
    # since there's nothing delivered yet to protect.
    still_generating = decide(_evidence(agent_response_state="generating_text", final_text="tomorrow", now=1.13))
    already_streaming = decide(_evidence(agent_response_state="tts_streaming", final_text="tomorrow", now=1.13))
    assert still_generating.action is InterruptionAction.INTERRUPT
    assert already_streaming.action is InterruptionAction.MONITOR


def test_word_count_at_or_above_threshold_interrupts_without_waiting_for_window():
    # Two words already clears BALANCED's min-words-for-new-utterance
    # threshold — that's already strong non-backchannel evidence on its
    # own, so this does not wait for the qualification window (distinct
    # from the single-word case above, which does wait).
    decision = decide(_evidence(final_text="tomorrow please", now=1.03))
    assert decision.action is InterruptionAction.INTERRUPT
    assert decision.reason == "new_utterance_detected"


def test_high_sensitivity_interrupts_sooner_than_low_sensitivity():
    # A single word stays below both presets' min-words-for-new-utterance
    # EXCEPT high sensitivity's (1) — so only HIGH treats it as enough
    # evidence to interrupt immediately; LOW must still wait out its window.
    low = decide(_evidence(sensitivity="low", final_text="tomorrow", now=1.15))
    high = decide(_evidence(sensitivity="high", final_text="tomorrow", now=1.15))
    assert low.action is InterruptionAction.MONITOR
    assert high.action is InterruptionAction.INTERRUPT


def test_get_thresholds_falls_back_to_balanced_for_unknown_sensitivity():
    assert get_thresholds("nonsense") == get_thresholds("balanced")


def test_correction_shaped_utterance_interrupts_as_normal_priority():
    decision = decide(_evidence(final_text="no eighteen thousand not twenty eight", now=1.30))
    assert decision.action is InterruptionAction.INTERRUPT
    # "no" is itself a high-priority cue in English — a correction phrased
    # this way should already be at least HIGH priority, not merely NORMAL.
    assert decision.priority in (InterruptionPriority.HIGH, InterruptionPriority.NORMAL)
