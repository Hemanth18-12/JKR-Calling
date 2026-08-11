"""P8 — RealtimePipelineCoordinator.interrupt_active_response(): the
cancellation order, idempotency, late-audio dropping, PLAYED-vs-CLEARED
accounting under an interruption specifically (test_coordinator.py already
covers the ordinary non-interruption clear case), conservative delivered-
text derivation, and the non-interruptible/DNC-override rule. See
docs/BARGE_IN_ARCHITECTURE.md, docs/INTERRUPTED_RESPONSE_HISTORY.md.
"""

from __future__ import annotations

import asyncio
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
    TTSGenerationCompleted,
)
from app.modules.live_call.transport.coordinator import (
    PlaybackUnitState,
    RealtimePipelineCoordinator,
    ResponseState,
)
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession
from jkr_conversation.streaming_response import SpeakableChunk


class _FakeTTSProvider:
    """Produces audio as each send_text() arrives — matching the REAL,
    live-verified Sarvam behavior (docs/SARVAM_STREAMING_TTS_CONTRACT.md),
    same shape test_p7_pipeline_integration.py's own fake already
    established. This matters specifically for this file's
    delivered-text tests: they depend on each chunk's audio actually being
    produced (and therefore its PlaybackUnit.sent_at recorded) shortly
    after that chunk's own text was submitted — a provider that only ever
    produces audio in one batch at flush() would make every chunk look
    equally "delivered," which is not how the real provider behaves."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.cancelled: list[str] = []
        self._audio_chunk_index: dict[str, int] = {}
        self._cancelled_response_ids: set[str] = set()

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        if response_id in self._cancelled_response_ids:
            return
        index = self._audio_chunk_index.get(response_id, 0)
        self._audio_chunk_index[response_id] = index + 1
        await self._queue.put(
            TTSAudioChunk(response_id=response_id, audio_chunk_index=index, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)
        )

    async def flush(self, *, response_id):
        if response_id in self._cancelled_response_ids:
            return
        await self._queue.put(TTSGenerationCompleted(response_id=response_id))

    async def cancel(self, response_id):
        self.cancelled.append(response_id)
        self._cancelled_response_ids.add(response_id)

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


def _chunk(response_id: str, generation_id: str, index: int, text: str) -> SpeakableChunk:
    return SpeakableChunk(response_id=response_id, generation_id=generation_id, chunk_index=index, text=text, is_final=True, created_at=0.0)


def _wire_fake_clear(media_session: RealtimeMediaSession) -> list[str]:
    """A real send_twilio_clear callback drives session.request_clear_playback()
    (same as the real clear_agent_audio() does) so the coordinator's own
    _on_playback_clear hook actually fires and units flip to CLEARED —
    exercising the real accounting path, not a bare recorder."""
    calls: list[str] = []

    async def _send_clear() -> None:
        calls.append("cleared")
        media_session.request_clear_playback()

    media_session.send_twilio_clear = _send_clear
    return calls


async def _make_coordinator(provider: _FakeTTSProvider, media_session: RealtimeMediaSession) -> tuple[RealtimePipelineCoordinator, TTSStreamingSession]:
    tts_session = TTSStreamingSession(provider=provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    coordinator.attach_tts_session(tts_session)
    return coordinator, tts_session


# --- interrupting a response still in flight (TTS actively generating,
# nothing sent to Twilio yet) -------------------------------------------


async def test_interrupt_mid_generation_cancels_the_tts_provider_and_needs_no_clear():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    clear_calls = _wire_fake_clear(media_session)
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    # Deliberately never call complete_generation() — this response is
    # still an in-flight generation when the customer barges in.

    snapshot = await coordinator.interrupt_active_response(reason="customer_barge_in")

    assert snapshot is not None
    assert snapshot.had_sent_audio is False
    assert clear_calls == []  # nothing was ever sent to Twilio — nothing to clear
    assert ctx.state == ResponseState.INTERRUPTED
    await tts_session.close()


async def test_interrupt_mid_generation_stops_the_tts_provider_after_first_chunk():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Root canal cost case batti vary avutundi andi."))
    await asyncio.sleep(0.02)  # let _run_sender/_run_consumer actually process the chunk before interrupting mid-stream

    await coordinator.interrupt_active_response(reason="customer_barge_in")

    assert provider.cancelled == [ctx.response_id]
    await tts_session.close()


# --- idempotency --------------------------------------------------------


async def test_concurrent_interrupt_calls_only_run_the_sequence_once():
    """Simulates VAD-start and provider-SpeechStarted both confirming an
    interruption within the same event-loop tick — must produce exactly one
    cancellation/clear, not two."""
    provider = _FakeTTSProvider()
    media_session = _media_session()
    clear_calls = _wire_fake_clear(media_session)
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await asyncio.sleep(0.02)

    results = await asyncio.gather(
        coordinator.interrupt_active_response(reason="vad_start"),
        coordinator.interrupt_active_response(reason="provider_speech_start"),
    )

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1
    assert provider.cancelled == [ctx.response_id]  # cancelled exactly once, not twice
    assert clear_calls == []  # nothing was sent to Twilio in this scenario yet — but if it had been, this must be length 1, never 2
    await tts_session.close()


async def test_second_interrupt_after_first_completes_is_a_no_op():
    provider = _FakeTTSProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await asyncio.sleep(0.02)

    first = await coordinator.interrupt_active_response(reason="first")
    second = await coordinator.interrupt_active_response(reason="second")

    assert first is not None
    assert second is None
    assert provider.cancelled == [ctx.response_id]
    await tts_session.close()


# --- late-event dropping (proves what tts_bridge.py already does, per the
# audit — this is the regression test, not a new mechanism) -----------------


async def test_late_audio_chunk_after_interrupt_never_reaches_outbound_queue():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Root canal cost case batti vary avutundi andi."))
    await asyncio.sleep(0.02)

    await coordinator.interrupt_active_response(reason="customer_barge_in")
    before = media_session.outbound_queue.qsize()

    # A slow provider that kept producing after cancel was requested — the
    # fake's own cancel() already suppresses further send_text() output
    # (matching the real SarvamStreamingTTS's _cancelled_response_ids), so
    # this directly injects a late event to prove the CONSUMER side (not
    # just the producer side) also drops it, matching the real
    # pending.event.is_set() guard in tts_bridge._run_consumer.
    await provider._queue.put(  # noqa: SLF001 — direct queue injection to simulate a late provider event
        TTSAudioChunk(response_id=ctx.response_id, audio_chunk_index=99, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)
    )
    await asyncio.sleep(0.02)
    assert media_session.outbound_queue.qsize() == before
    await tts_session.close()


# --- PLAYED vs CLEARED accounting under an interruption specifically -------


async def test_interrupt_after_partial_playback_marks_pending_units_cleared_not_acknowledged():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    _wire_fake_clear(media_session)
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Root canal cost case batti vary avutundi andi."))
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 1, "Exact amount doctor confirm chestharu."))
    await coordinator.complete_generation(ctx.response_id)
    assert len(ctx.playback_units) == 2

    # Only the FIRST unit's mark is acknowledged before the customer barges in.
    media_session.record_mark_acknowledged(ctx.playback_units[0].mark_name)

    snapshot = await coordinator.interrupt_active_response(reason="customer_barge_in")

    assert snapshot is not None
    assert ctx.playback_units[0].state == PlaybackUnitState.ACKNOWLEDGED
    assert ctx.playback_units[1].state == PlaybackUnitState.CLEARED
    assert snapshot.audio_acknowledged_ms == 100
    # A late ack for the cleared unit must never flip it back.
    media_session.record_mark_acknowledged(ctx.playback_units[1].mark_name)
    assert ctx.playback_units[1].state == PlaybackUnitState.CLEARED
    await tts_session.close()


async def test_delivered_text_only_includes_chunks_submitted_before_last_acknowledged_unit():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    _wire_fake_clear(media_session)
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Root canal cost case batti vary avutundi andi."))
    await asyncio.sleep(0.02)  # let the first chunk's audio actually get produced/sent before the second is submitted
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 1, "Exact amount doctor confirm chestharu."))
    await coordinator.complete_generation(ctx.response_id)
    assert len(ctx.playback_units) == 2

    media_session.record_mark_acknowledged(ctx.playback_units[0].mark_name)
    snapshot = await coordinator.interrupt_active_response(reason="customer_barge_in")

    assert snapshot is not None
    # Both chunks were fully generated/committed, but only the first is
    # conservatively "known delivered" — never the full generated text.
    assert snapshot.generated_text == "Root canal cost case batti vary avutundi andi.Exact amount doctor confirm chestharu."
    assert snapshot.delivered_text == "Root canal cost case batti vary avutundi andi."
    assert snapshot.delivered_text != snapshot.generated_text
    await tts_session.close()


async def test_delivered_text_is_empty_when_nothing_was_ever_acknowledged():
    provider = _FakeTTSProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi there."))
    await coordinator.complete_generation(ctx.response_id)

    snapshot = await coordinator.interrupt_active_response(reason="customer_barge_in")

    assert snapshot is not None
    assert snapshot.delivered_text == ""  # never fabricated — no positive evidence anything was heard
    await tts_session.close()


# --- non-interruptible / DNC override ---------------------------------------


async def test_non_interruptible_response_can_still_be_interrupted_directly():
    """interrupt_active_response() itself has no opinion about
    interruptible — that gate belongs to InterruptionPolicy (the caller);
    the coordinator's job is only to carry out a confirmed interruption
    correctly regardless of why it was confirmed (e.g. spec's DNC-always-
    overrides rule is enforced by the policy deciding to call this at all)."""
    provider = _FakeTTSProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1", interruptible=False)
    assert ctx.interruptible is False
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "This call may be recorded."))
    await coordinator.complete_generation(ctx.response_id)

    snapshot = await coordinator.interrupt_active_response(reason="do_not_call_override")

    assert snapshot is not None
    assert ctx.state == ResponseState.INTERRUPTED
    await tts_session.close()


async def test_interrupt_with_no_active_response_still_returns_none():
    provider = _FakeTTSProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    assert await coordinator.interrupt_active_response(reason="nothing_active") is None
    await tts_session.close()
