"""P9 — TTSStreamingSession's own replay-protection boundaries: stale text
dropped at dequeue (not just at enqueue), duplicate/conflicting
TTSAudioChunk.audio_chunk_index detection, and identity/playback_epoch
correctly stamped onto every OutboundAudioChunk it produces. See
docs/P9_REPLAY_PROTECTION_AUDIT.md §23-30, docs/REALTIME_OUTPUT_INVARIANTS.md.
"""

from __future__ import annotations

import asyncio
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
)
from app.modules.live_call.transport.identity import ResponseIdentity
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession


class _ScriptedProvider:
    """A provider whose events() the test controls directly by pushing onto
    an internal queue, rather than reacting to send_text()/flush() calls —
    needed here because these tests specifically construct malformed
    (duplicate/conflicting/never-actually-sent) provider events."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.sent_texts: list[str] = []
        self.cancelled: list[str] = []

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        self.sent_texts.append(text)

    async def flush(self, *, response_id):
        pass

    async def cancel(self, response_id):
        self.cancelled.append(response_id)

    async def close(self):
        pass

    async def push(self, event) -> None:
        await self._queue.put(event)

    async def events(self):
        while True:
            yield await self._queue.get()


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


def _identity(call_id: uuid.UUID, response_id: str) -> ResponseIdentity:
    return ResponseIdentity(call_id=call_id, turn_id="t1", response_id=response_id, generation_id="gen_1", sequence_id=response_id, epoch=1)


async def _started_session(provider: _ScriptedProvider, media_session: RealtimeMediaSession) -> TTSStreamingSession:
    session = TTSStreamingSession(provider=provider, media_session=media_session)
    await session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    return session


async def test_stale_text_queued_before_cancel_is_purged_and_never_sent():
    """Enqueue-then-cancel with no await in between — the item is still
    sitting in _text_queue when cancel_response() marks the response
    resolved. The PROACTIVE PURGE (added alongside the dequeue-time check
    — see the next test) is what actually removes it here, before
    _run_sender ever gets a chance to dequeue it at all."""
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)

    handle = session.begin_response("resp_1")
    await session._enqueue_text(response_id="resp_1", chunk_index=0, text="This should never be spoken.")  # noqa: SLF001
    before = replay_metrics.queue_stale_items_purged_total
    await session.cancel_response("resp_1", reason="test")
    await asyncio.sleep(0.05)  # let _run_sender run, in case anything survived the purge

    assert "This should never be spoken." not in provider.sent_texts
    assert replay_metrics.queue_stale_items_purged_total > before
    del handle
    await session.close()


async def test_stale_text_arriving_after_cancel_is_dropped_at_dequeue():
    """The SECOND, independent guard (spec §23-24: "validate again at
    dequeue, a chunk may be active at enqueue time but stale by dequeue
    time"): a text item for an ALREADY-cancelled response, enqueued after
    the proactive purge already ran (so the purge can't be what catches
    this one), must still never reach provider.send_text() — _run_sender's
    own dequeue-time check is what's actually being proven here."""
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)

    session.begin_response("resp_1")
    await session.cancel_response("resp_1", reason="test")  # nothing queued yet — purge is a no-op
    before = replay_metrics.stale_tts_text_dropped_total
    await session._enqueue_text(response_id="resp_1", chunk_index=0, text="Late text for a dead response.")  # noqa: SLF001
    await asyncio.sleep(0.05)

    assert "Late text for a dead response." not in provider.sent_texts
    assert replay_metrics.stale_tts_text_dropped_total > before
    await session.close()


async def test_duplicate_audio_chunk_index_is_dropped_not_forwarded_twice():
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)
    identity = _identity(media_session.call_session_id, "resp_1")

    session.begin_response("resp_1", identity=identity, playback_epoch=0)
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))  # exact duplicate
    await asyncio.sleep(0.05)

    assert media_session.outbound_queue.qsize() == 1
    await session.close()


async def test_conflicting_audio_chunk_index_fails_the_response():
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)
    identity = _identity(media_session.call_session_id, "resp_1")

    handle = session.begin_response("resp_1", identity=identity, playback_epoch=0)
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\x11" * 400, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))  # same index, different bytes
    await asyncio.sleep(0.05)

    assert media_session.outbound_queue.qsize() == 1  # only the first, genuine chunk ever forwarded
    outcome = await handle.finish()
    assert outcome.failed is True
    assert outcome.failure_message is not None and "conflict" in outcome.failure_message
    await session.close()


async def test_audio_chunk_gap_fails_the_response_without_forwarding_out_of_order():
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)
    identity = _identity(media_session.call_session_id, "resp_1")

    handle = session.begin_response("resp_1", identity=identity, playback_epoch=0)
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=5, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))  # gap: skips 1-4
    await asyncio.sleep(0.05)

    assert media_session.outbound_queue.qsize() == 1  # index 5 never forwarded
    outcome = await handle.finish()
    assert outcome.failed is True
    await session.close()


async def test_outbound_chunk_carries_identity_and_playback_epoch():
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)
    identity = _identity(media_session.call_session_id, "resp_1")

    session.begin_response("resp_1", identity=identity, playback_epoch=3)
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))
    await asyncio.sleep(0.05)

    chunk = media_session.outbound_queue.get_nowait()
    assert chunk.identity == identity
    assert chunk.playback_epoch == 3
    await session.close()


async def test_no_identity_configured_falls_back_to_legacy_none():
    """begin_response() without identity/playback_epoch (every P6/P7-era
    test construction, and any call site that hasn't been updated) must
    keep working exactly as before — identity=None, the documented legacy
    path, not an error."""
    provider = _ScriptedProvider()
    media_session = _media_session()
    session = await _started_session(provider, media_session)

    session.begin_response("resp_1")
    await provider.push(TTSAudioChunk(response_id="resp_1", audio_chunk_index=0, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000))
    await asyncio.sleep(0.05)

    chunk = media_session.outbound_queue.get_nowait()
    assert chunk.identity is None
    assert chunk.playback_epoch == 0
    await session.close()
