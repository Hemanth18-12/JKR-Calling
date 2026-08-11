"""P6 — the outbound send loop must forward Sarvam's direct mu-law/8kHz
streaming output byte-for-byte (no re-resample/re-encode, no container
header ever reaching Twilio — spec §29/§34/§96), while the existing PCM16
batch path keeps going through encode_twilio_media_payload() unchanged.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import uuid

from app.config import Settings
from app.modules.live_call.transport.audio_codec import encode_twilio_media_payload
from app.modules.live_call.transport.base import OutboundAudioChunk
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.twilio_media_stream import _send_loop


class _FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


def _session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def _run_send_loop_briefly(ws: _FakeWebSocket, session: RealtimeMediaSession, settings: Settings) -> None:
    task = asyncio.create_task(_send_loop(ws, session, settings))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_mulaw_chunk_is_sent_as_raw_base64_passthrough():
    session = _session()
    ws = _FakeWebSocket()
    raw_mulaw = b"\xff\xfe\xfd\xfc\x80\x81"
    chunk = OutboundAudioChunk(
        response_sequence_id="r1", chunk_index=0, data=raw_mulaw, sample_rate=8000,
        mark_name="jkr-mark-1", audio_is_mulaw_8k=True,
    )
    await session.enqueue_outbound_audio(chunk)

    await _run_send_loop_briefly(ws, session, Settings())

    media_messages = [m for m in ws.sent if m["event"] == "media"]
    assert len(media_messages) == 1
    payload = base64.b64decode(media_messages[0]["media"]["payload"])
    assert payload == raw_mulaw  # byte-for-byte, no resample/re-encode
    assert not payload.startswith(b"RIFF")
    assert not payload.startswith(b"WAVE")
    assert not payload.startswith(b"ID3")


async def test_mulaw_chunk_uses_the_mark_name_assigned_at_enqueue_time():
    session = _session()
    ws = _FakeWebSocket()
    chunk = OutboundAudioChunk(
        response_sequence_id="r1", chunk_index=0, data=b"\xff\xfe", sample_rate=8000,
        mark_name="jkr-mark-42", audio_is_mulaw_8k=True,
    )
    await session.enqueue_outbound_audio(chunk)

    await _run_send_loop_briefly(ws, session, Settings())

    mark_messages = [m for m in ws.sent if m["event"] == "mark"]
    assert len(mark_messages) == 1
    assert mark_messages[0]["mark"]["name"] == "jkr-mark-42"
    assert "jkr-mark-42" in session.metrics.marks_sent


async def test_pcm16_batch_chunk_still_goes_through_encode_twilio_media_payload():
    session = _session()
    ws = _FakeWebSocket()
    pcm16_silence = b"\x00\x00" * 100
    chunk = OutboundAudioChunk(
        response_sequence_id="r1", chunk_index=0, data=pcm16_silence, sample_rate=8000,
        mark_name="jkr-mark-1", audio_is_mulaw_8k=False,
    )
    await session.enqueue_outbound_audio(chunk)

    await _run_send_loop_briefly(ws, session, Settings())

    media_messages = [m for m in ws.sent if m["event"] == "media"]
    assert len(media_messages) == 1
    expected = encode_twilio_media_payload(pcm16_silence, sample_rate=8000)
    assert media_messages[0]["media"]["payload"] == expected


async def test_legacy_chunk_without_mark_name_still_gets_a_generated_one():
    # OutboundAudioChunk.mark_name defaults to "" for backward-compatible
    # construction — _send_loop must still assign a real mark in that case.
    session = _session()
    ws = _FakeWebSocket()
    chunk = OutboundAudioChunk(response_sequence_id="r1", chunk_index=0, data=b"\x00\x00", sample_rate=8000)
    await session.enqueue_outbound_audio(chunk)

    await _run_send_loop_briefly(ws, session, Settings())

    mark_messages = [m for m in ws.sent if m["event"] == "mark"]
    assert len(mark_messages) == 1
    assert mark_messages[0]["mark"]["name"]  # non-empty, generated on the fly
