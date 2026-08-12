from __future__ import annotations

import time
import uuid

from app.config import Settings
from app.modules.live_call.transport import streaming_bridge
from app.modules.live_call.transport.base import MediaSessionStatus
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.streaming_bridge import (
    _CALL_ENDED,
    _CONTINUE,
    _check_grace_expiry,
    _is_duplicate_final,
    _normalize_for_dedup,
    _TurnTrackingState,
)


def _session(**overrides) -> RealtimeMediaSession:
    defaults = dict(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    defaults.update(overrides)
    return RealtimeMediaSession(**defaults)


# --- _normalize_for_dedup / _is_duplicate_final -----------------------------


def test_normalize_for_dedup_is_case_and_whitespace_insensitive():
    assert _normalize_for_dedup("  Root Canal  ") == _normalize_for_dedup("root canal")


def test_is_duplicate_final_true_for_same_utterance_idx_and_text():
    state = _TurnTrackingState(last_final_utterance_idx=0, last_final_text_normalized="root canal")
    assert _is_duplicate_final(state, utterance_idx=0, normalized_text="Root Canal") is True


def test_is_duplicate_final_false_for_different_utterance_idx_even_with_identical_text():
    # Two genuinely different utterances can share identical text (customer
    # saying "yes" twice) — must NOT be deduped away.
    state = _TurnTrackingState(last_final_utterance_idx=0, last_final_text_normalized="yes")
    assert _is_duplicate_final(state, utterance_idx=1, normalized_text="yes") is False


def test_is_duplicate_final_false_for_different_text_even_with_same_utterance_idx():
    state = _TurnTrackingState(last_final_utterance_idx=0, last_final_text_normalized="root canal")
    assert _is_duplicate_final(state, utterance_idx=0, normalized_text="tomorrow") is False


def test_is_duplicate_final_false_when_nothing_seen_yet():
    state = _TurnTrackingState()
    assert _is_duplicate_final(state, utterance_idx=0, normalized_text="hello") is False


# --- _check_grace_expiry -----------------------------------------------------


async def test_check_grace_expiry_continues_when_not_in_grace_period():
    state = _TurnTrackingState(in_grace_period=False)
    session = _session()
    outcome = await _check_grace_expiry(
        turn_state=state, session=session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(),
        redis_state={}, language_code="en-IN",
    )
    assert outcome is _CONTINUE


async def test_check_grace_expiry_continues_when_deadline_not_yet_reached():
    state = _TurnTrackingState(in_grace_period=True, grace_deadline=time.monotonic() + 60.0)
    session = _session()
    outcome = await _check_grace_expiry(
        turn_state=state, session=session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(),
        redis_state={}, language_code="en-IN",
    )
    assert outcome is _CONTINUE


async def test_check_grace_expiry_extends_deadline_if_media_arrived_very_recently():
    # Never hang up while the customer might still be mid-speech, even if
    # the nominal grace deadline has technically passed.
    state = _TurnTrackingState(in_grace_period=True, grace_deadline=time.monotonic() - 1.0)
    session = _session()
    session.touch_media()  # media "just" arrived
    original_deadline = state.grace_deadline
    outcome = await _check_grace_expiry(
        turn_state=state, session=session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(),
        redis_state={}, language_code="en-IN",
    )
    assert outcome is _CONTINUE
    assert state.grace_deadline > original_deadline


async def test_check_grace_expiry_finalizes_call_when_truly_expired(monkeypatch):
    finalized = {}

    async def fake_finalize(*, workspace_id, call_session_id, redis_state, language_code, session):
        finalized["called"] = True
        session.close()

    monkeypatch.setattr(streaming_bridge, "_finalize_call_from_grace_expiry", fake_finalize)

    state = _TurnTrackingState(in_grace_period=True, grace_deadline=time.monotonic() - 100.0)
    session = _session()
    # No media touched recently, and last_media_at is None -> seconds_since_last_media() is None,
    # which is treated as "not recent" (the `is not None and < margin` check short-circuits).
    outcome = await _check_grace_expiry(
        turn_state=state, session=session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(),
        redis_state={}, language_code="en-IN",
    )
    assert outcome is _CALL_ENDED
    assert finalized.get("called") is True


# --- run_streaming_turn_loop reconnect/failure-policy (no DB touched: connect() always fails) ---


class _AlwaysFailsToConnect:
    def __init__(self, *, api_key, config):
        pass

    async def connect(self):
        raise ConnectionRefusedError("simulated connect failure")


async def _noop_persist_stt_lifecycle_event(*, workspace_id, call_session_id, event_type, payload) -> None:
    pass


async def test_run_streaming_turn_loop_gives_up_and_closes_session_on_fail_policy(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _AlwaysFailsToConnect)
    monkeypatch.setattr(streaming_bridge, "_RECONNECT_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    # Real-call forensics fix: give-up now persists a CallEvent — this test
    # uses synthetic, never-persisted workspace_id/call_session_id values
    # (see this file's own docstring: "no DB touched"), so that one
    # DB-touching seam is monkeypatched away here, exactly like
    # _finalize_call_from_grace_expiry already is in the tests above; the
    # real DB write is proven separately in
    # test_streaming_stt_integration.py::test_fatal_stt_error_and_give_up_are_persisted_as_call_events.
    monkeypatch.setattr(streaming_bridge, "_persist_stt_lifecycle_event", _noop_persist_stt_lifecycle_event)

    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    session.transition_to(MediaSessionStatus.STREAMING)

    settings = Settings(stt_stream_failure_policy="fail")
    fell_back = await streaming_bridge.run_streaming_turn_loop(
        session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(), agent_id=None,
        redis_state={"recent_turns": []}, settings=settings, redis=None, redis_state_token="tok",
        language_code="en-IN", tts_speaker=None,
    )
    assert fell_back is False
    assert session.is_closed is True
    assert session.status == MediaSessionStatus.FAILED


async def test_run_streaming_turn_loop_falls_back_to_batch_on_batch_next_turn_policy(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _AlwaysFailsToConnect)
    monkeypatch.setattr(streaming_bridge, "_RECONNECT_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(streaming_bridge, "_persist_stt_lifecycle_event", _noop_persist_stt_lifecycle_event)

    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    session.transition_to(MediaSessionStatus.STREAMING)

    settings = Settings(stt_stream_failure_policy="batch_next_turn")
    fell_back = await streaming_bridge.run_streaming_turn_loop(
        session, workspace_id=uuid.uuid4(), call_session_id=uuid.uuid4(), agent_id=None,
        redis_state={"recent_turns": []}, settings=settings, redis=None, redis_state_token="tok",
        language_code="en-IN", tts_speaker=None,
    )
    assert fell_back is True
    # session itself is left open — the caller (_processing_loop) continues on the batch path
    assert session.is_closed is False
