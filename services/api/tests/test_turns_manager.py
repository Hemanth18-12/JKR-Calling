"""Fake-clock, deterministic tests for TurnManager — every timestamp is an
explicit float passed by the test, nothing sleeps for real (spec §110-111).
"""

from __future__ import annotations

import uuid

from app.modules.live_call.turns import policies
from app.modules.live_call.turns.manager import TurnManager
from app.modules.live_call.turns.signals import TurnSignal, TurnSignalType
from app.modules.live_call.turns.state import TurnDecision, TurnState

CALL_ID = uuid.uuid4()


def _final(text: str, *, t: float, idx: int = 0) -> TurnSignal:
    return TurnSignal(type=TurnSignalType.STT_FINAL, timestamp=t, text=text, utterance_idx=idx)


def _speech_start(*, t: float, source: str = "energy_vad") -> TurnSignal:
    return TurnSignal(type=TurnSignalType.LOCAL_VAD_SPEECH_START, timestamp=t, source=source)


def _manager(mode: str = "hybrid", profile: str = "balanced") -> TurnManager:
    policy = policies.get_policy(mode=mode, profile=profile)
    return TurnManager(call_session_id=CALL_ID, language_code="en-IN", policy=policy)


# --- provider mode: byte-identical to pre-P4 -------------------------------


def test_provider_mode_commits_immediately_on_first_final():
    tm = _manager(mode="provider")
    decision = tm.on_signal(_final("Tomorrow evening.", t=0.0))
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed is not None
    assert committed.text == "Tomorrow evening."
    assert committed.endpoint_reason == "provider_only"


def test_provider_mode_ignores_semantic_incompleteness():
    # Even an obviously-incomplete utterance commits immediately under
    # provider mode — this is the whole point of the backward-compat mode.
    tm = _manager(mode="provider")
    decision = tm.on_signal(_final("I need root canal but", t=0.0))
    assert decision == TurnDecision.COMMIT_TURN


# --- spec §57: normal complete turn -----------------------------------------


def test_complete_turn_commits_after_min_delay_not_before():
    tm = _manager(mode="hybrid", profile="balanced")  # min_endpoint_delay_ms=300
    assert tm.on_signal(_final("Tomorrow evening.", t=0.0)) == TurnDecision.MAYBE_END
    assert tm.state == TurnState.POSSIBLE_END
    # Before min_endpoint_delay elapses: must not commit yet.
    assert tm.on_timer_tick(now=0.1) == TurnDecision.WAIT
    # After min_endpoint_delay, semantically complete -> commits.
    decision = tm.on_timer_tick(now=0.35)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "Tomorrow evening."
    assert committed.endpoint_reason == "semantic_complete"


# --- spec §58: thinking pause -> ONE committed turn -------------------------


def test_thinking_pause_coalesces_into_one_turn():
    tm = _manager(mode="hybrid", profile="balanced")
    assert tm.on_signal(_final("Tomorrow but", t=0.0)) == TurnDecision.MAYBE_END
    # Not yet complete ("but" is a trailing continuation marker) -> keep waiting.
    assert tm.on_timer_tick(now=0.4) == TurnDecision.WAIT
    assert tm.state == TurnState.WAITING_FOR_CONTINUATION
    # Continuation arrives before max delay.
    assert tm.on_signal(_final("actually evening better", t=0.9, idx=1)) == TurnDecision.MAYBE_END
    decision = tm.on_timer_tick(now=1.25)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "Tomorrow but actually evening better"
    assert len(committed.final_segments) == 2


# --- spec §59: incomplete clause does not commit immediately ----------------


def test_incomplete_clause_does_not_commit_before_max_delay():
    tm = _manager(mode="hybrid", profile="balanced")  # max_endpoint_delay_ms=2000
    tm.on_signal(_final("I need root canal but", t=0.0))
    # Well within max delay, still incomplete -> must not commit.
    assert tm.on_timer_tick(now=1.0) == TurnDecision.WAIT
    assert tm.state == TurnState.WAITING_FOR_CONTINUATION


# --- spec §60: complete question commits promptly ---------------------------


def test_complete_question_commits_promptly():
    tm = _manager(mode="hybrid", profile="fast")  # min_endpoint_delay_ms=150
    tm.on_signal(_final("Root canal cost entha?", t=0.0))
    decision = tm.on_timer_tick(now=0.16)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.endpoint_reason == "semantic_complete"


# --- spec §61/§62: number pause and code-mix pause coalesce -----------------


def test_number_sequence_pause_coalesces():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.on_signal(_final("My rank is...", t=0.0))
    assert tm.on_timer_tick(now=0.4) == TurnDecision.WAIT
    tm.on_signal(_final("twenty eight thousand.", t=0.8, idx=1))
    decision = tm.on_timer_tick(now=1.15)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "My rank is... twenty eight thousand."


def test_code_mix_pause_coalesces():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.language_code = "te-en-IN"
    # Ends with "kani" (Telugu "but/however") — a genuine trailing
    # continuation marker, not a synthetic "..." STT wouldn't actually emit.
    tm.on_signal(_final("Weekend kani", t=0.0))
    assert tm.on_timer_tick(now=0.4) == TurnDecision.WAIT
    tm.on_signal(_final("Sunday అయితే better.", t=0.8, idx=1))
    decision = tm.on_timer_tick(now=1.15)
    assert decision == TurnDecision.COMMIT_TURN


# --- spec §69: max endpoint timeout — never wait forever --------------------


def test_max_endpoint_timeout_forces_commit_even_if_incomplete():
    # FAST preset: max_endpoint_delay_ms=1200, thinking_pause_extension_ms=500
    # -> effective incomplete ceiling is 1200+500=1700ms from possible_end.
    tm = _manager(mode="hybrid", profile="fast")
    tm.on_signal(_final("I need root canal but", t=0.0))
    tm.on_timer_tick(now=0.5)
    assert tm.on_timer_tick(now=1.4) == TurnDecision.WAIT  # still within the extended ceiling
    decision = tm.on_timer_tick(now=1.75)  # past the extended ceiling
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.endpoint_reason == "max_endpoint_timeout"


# --- spec §70: user resumes during pending commit → cancel ------------------


def test_user_resumes_before_commit_cancels_pending_commit():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.on_signal(_final("Tomorrow", t=0.0))
    assert tm.state == TurnState.POSSIBLE_END
    decision = tm.on_signal(_speech_start(t=0.1))
    assert decision == TurnDecision.CANCEL_PENDING_COMMIT
    assert tm.state == TurnState.USER_SPEAKING
    # Nothing committed yet.
    assert tm.take_committed_turn() is None


# --- spec §71: two genuinely separate turns are not over-coalesced ----------


def test_two_separate_turns_are_not_coalesced_after_a_commit():
    tm = _manager(mode="hybrid", profile="fast")
    tm.on_signal(_final("Yes.", t=0.0))
    assert tm.on_timer_tick(now=0.2) == TurnDecision.COMMIT_TURN
    first = tm.take_committed_turn()
    assert first.text == "Yes."
    # A later, unrelated turn starts completely fresh.
    tm.on_signal(_final("What about price?", t=5.0, idx=5))
    assert tm.on_timer_tick(now=5.2) == TurnDecision.COMMIT_TURN
    second = tm.take_committed_turn()
    assert second.text == "What about price?"
    assert second.final_segments != first.final_segments


# --- spec §64/§65: backchannel context-awareness ----------------------------


def test_backchannel_in_confirmation_context_commits_as_real_answer():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.expecting_confirmation = True
    tm.on_signal(_final("haa", t=0.0))
    decision = tm.on_timer_tick(now=0.35)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "haa"


def test_backchannel_without_expected_confirmation_waits_longer():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.expecting_confirmation = False
    tm.on_signal(_final("hmm", t=0.0))
    # Not treated as confidently complete — stays waiting past min_delay.
    decision = tm.on_timer_tick(now=0.35)
    assert decision == TurnDecision.WAIT
    assert tm.state == TurnState.WAITING_FOR_CONTINUATION


# --- spec §42/§43/§66: noise / empty speech ---------------------------------


def test_empty_final_with_no_segments_never_commits():
    tm = _manager(mode="hybrid", profile="balanced")
    decision = tm.on_signal(_final("", t=0.0))
    assert decision == TurnDecision.WAIT
    assert tm.state == TurnState.IDLE
    assert tm.take_committed_turn() is None


def test_vad_speech_end_with_no_transcript_returns_to_idle_style_wait():
    tm = _manager(mode="hybrid", profile="balanced")
    tm.on_signal(_speech_start(t=0.0))
    assert tm.state == TurnState.USER_SPEECH_STARTING
    decision = tm.on_signal(TurnSignal(type=TurnSignalType.LOCAL_VAD_SPEECH_END, timestamp=0.3, source="energy_vad"))
    assert decision == TurnDecision.WAIT
    # No transcript ever arrived — no turn should ever be committed from this.
    assert tm.take_committed_turn() is None


# --- spec §67/§68: fragmentation and duplicate protection -------------------


def test_provider_fragmentation_coalesces_short_gap():
    tm = _manager(mode="hybrid", profile="balanced")  # fragment_coalesce_ms=1500
    tm.on_signal(_final("Tomorrow", t=0.0))
    tm.on_signal(_final("evening", t=0.5, idx=1))  # well within fragment_coalesce_ms
    decision = tm.on_timer_tick(now=0.85)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "Tomorrow evening"
    assert len(committed.final_segments) == 2


def test_large_gap_between_finals_starts_a_new_turn_not_a_coalesce():
    tm = _manager(mode="hybrid", profile="fast")  # fragment_coalesce_ms=900
    tm.on_signal(_final("Tomorrow", t=0.0))
    # A gap far larger than fragment_coalesce_ms — treated as a new turn.
    tm.on_signal(_final("What about price", t=5.0, idx=7))
    decision = tm.on_timer_tick(now=5.2)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.text == "What about price"  # "Tomorrow" was dropped, not concatenated


# --- max_endpoint_delay is an absolute ceiling, independent of resumed waits ---


def test_max_endpoint_delay_anchored_to_first_possible_end_not_last_final():
    # FAST preset: max_endpoint_delay_ms=1200, thinking_pause_extension_ms=500
    # -> effective incomplete ceiling = 1700ms, anchored to the FIRST
    # possible_end (t=0.0), not the most recent final's arrival.
    tm = _manager(mode="hybrid", profile="fast")
    tm.on_signal(_final("I need root canal but", t=0.0))  # incomplete
    tm.on_timer_tick(now=0.5)
    tm.on_signal(_final("actually", t=0.85, idx=1))  # still incomplete-shaped continuation
    tm.on_timer_tick(now=1.2)
    # By t=1.75, elapsed since the FIRST possible_end (t=0.0) is 1750ms,
    # past the 1700ms effective ceiling, even though the last final (0.85)
    # was much more recent — the absolute ceiling must still fire.
    decision = tm.on_timer_tick(now=1.75)
    assert decision == TurnDecision.COMMIT_TURN
    committed = tm.take_committed_turn()
    assert committed.endpoint_reason == "max_endpoint_timeout"
