"""speak_turn_reply() — the single place a turn's reply text becomes audio,
shared by both turn loops since P6. Covers the streaming/batch-fallback
policy (spec §71/§72): batch fallback only when NO streamed audio was ever
delivered; never an automatic replay once some audio has already played.
"""

from __future__ import annotations

import uuid

from app.config import Settings
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.transitional_bridge import speak_turn_reply
from app.modules.live_call.transport.tts_bridge import TTSTurnOutcome


class _FakeHandle:
    def __init__(self, outcome: TTSTurnOutcome):
        self._outcome = outcome
        self.sent_chunks: list[str] = []

    async def send_chunk(self, text: str) -> None:
        self.sent_chunks.append(text)

    async def finish(self) -> TTSTurnOutcome:
        return self._outcome


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def test_empty_reply_text_is_a_no_op():
    result = await speak_turn_reply(
        reply_text="", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=None, callback_fired=False,
    )
    assert result.mark_name is None
    assert result.fatal_failure is False


async def test_callback_fired_skips_local_chunking():
    outcome = TTSTurnOutcome(response_id="r1", failed=False, failure_message=None, chunks_sent=2, bytes_sent=100, final_mark_name="m1", first_audio_ms=50)
    handle = _FakeHandle(outcome)
    result = await speak_turn_reply(
        reply_text="Already spoken via streaming.", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=handle, callback_fired=True,
    )
    assert handle.sent_chunks == []  # never fed again — would double-speak
    assert result.mark_name == "m1"
    assert result.fatal_failure is False
    # P10 — TTSTurnOutcome.first_audio_ms must survive this boundary
    # (previously silently discarded) so the real-call benchmark harness
    # can persist it as part of the turn latency waterfall.
    assert result.first_audio_ms == 50


async def test_callback_not_fired_chunks_reply_text_locally():
    outcome = TTSTurnOutcome(response_id="r1", failed=False, failure_message=None, chunks_sent=2, bytes_sent=100, final_mark_name="m1", first_audio_ms=50)
    handle = _FakeHandle(outcome)
    result = await speak_turn_reply(
        reply_text="First sentence. Second sentence.", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=handle, callback_fired=False,
    )
    assert handle.sent_chunks == ["First sentence.", "Second sentence."]
    assert result.mark_name == "m1"


async def test_falls_back_to_batch_when_no_streamed_audio_was_sent(monkeypatch):
    outcome = TTSTurnOutcome(response_id="r1", failed=True, failure_message="provider_internal: down", chunks_sent=0, bytes_sent=0, final_mark_name=None, first_audio_ms=None)
    handle = _FakeHandle(outcome)

    import app.modules.live_call.transport.transitional_bridge as bridge_mod
    import app.modules.live_call.transport.twilio_media_stream as tms_mod

    async def fake_synthesize(text, *, language_code, settings, speaker):
        return b"\x00\x01", 8000

    async def fake_send_pcm_reply(session, *, pcm16_bytes, sample_rate):
        return "batch-mark-1"

    monkeypatch.setattr(bridge_mod, "synthesize_for_stream", fake_synthesize)
    monkeypatch.setattr(tms_mod, "_send_pcm_reply", fake_send_pcm_reply)

    result = await speak_turn_reply(
        reply_text="Some reply.", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=handle, callback_fired=False,
    )
    assert result.fatal_failure is False
    assert result.mark_name == "batch-mark-1"


async def test_no_fallback_attempted_when_partial_audio_already_delivered(monkeypatch):
    outcome = TTSTurnOutcome(response_id="r1", failed=True, failure_message="stream_interrupted: dropped", chunks_sent=3, bytes_sent=900, final_mark_name="m-partial", first_audio_ms=80)
    handle = _FakeHandle(outcome)

    import app.modules.live_call.transport.transitional_bridge as bridge_mod

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("synthesize_for_stream must not be called when audio was already partially delivered")

    monkeypatch.setattr(bridge_mod, "synthesize_for_stream", fail_if_called)

    result = await speak_turn_reply(
        reply_text="Some reply that was mostly spoken already.", session=_media_session(), language_code="en-IN",
        settings=Settings(), speaker=None, response_handle=handle, callback_fired=False,
    )
    assert result.fatal_failure is False
    assert result.mark_name == "m-partial"  # whatever was last actually spoken, not re-derived


async def test_fatal_when_streaming_and_batch_fallback_both_fail(monkeypatch):
    outcome = TTSTurnOutcome(response_id="r1", failed=True, failure_message="connection_error: down", chunks_sent=0, bytes_sent=0, final_mark_name=None, first_audio_ms=None)
    handle = _FakeHandle(outcome)

    import app.modules.live_call.transport.transitional_bridge as bridge_mod

    async def fake_synthesize_fails(text, *, language_code, settings, speaker):
        return None

    monkeypatch.setattr(bridge_mod, "synthesize_for_stream", fake_synthesize_fails)

    result = await speak_turn_reply(
        reply_text="Some reply.", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=handle, callback_fired=False,
    )
    assert result.fatal_failure is True
    assert result.mark_name is None


async def test_batch_mode_no_handle_uses_batch_path_directly(monkeypatch):
    import app.modules.live_call.transport.transitional_bridge as bridge_mod
    import app.modules.live_call.transport.twilio_media_stream as tms_mod

    calls = []

    async def fake_synthesize(text, *, language_code, settings, speaker):
        calls.append(text)
        return b"\x00\x01", 8000

    async def fake_send_pcm_reply(session, *, pcm16_bytes, sample_rate):
        return "batch-mark"

    monkeypatch.setattr(bridge_mod, "synthesize_for_stream", fake_synthesize)
    monkeypatch.setattr(tms_mod, "_send_pcm_reply", fake_send_pcm_reply)

    result = await speak_turn_reply(
        reply_text="Plain batch reply.", session=_media_session(), language_code="en-IN", settings=Settings(),
        speaker=None, response_handle=None, callback_fired=False,
    )
    assert calls == ["Plain batch reply."]
    assert result.mark_name == "batch-mark"
    assert result.fatal_failure is False
