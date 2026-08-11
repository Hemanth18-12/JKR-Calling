"""P7 §149-150 — full realtime pipeline integration test: real
jkr_conversation streaming primitives (StreamingResponseAssembler,
SpeakableChunker) driving a real RealtimePipelineCoordinator and real
TTSStreamingSession against a real RealtimeMediaSession's real outbound
queue, with ONLY the two external provider network boundaries faked (the
LLM token stream, the Sarvam TTS WebSocket) — exactly the "mock external
provider network boundaries, use real internal modules" instruction.

The concurrency proof (spec §150): the LLM fake is built to take
measurably longer to finish producing ALL of its text than the TTS fake
takes to produce audio for the FIRST chunk — if the pipeline were secretly
serialized (collect all chunks, then start TTS), the first Twilio media
enqueue would only ever happen after the LLM's own full completion time.
Proving it happens strictly BEFORE is the actual concurrency proof, not a
sequence-of-calls approximation.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
    TTSFirstAudio,
    TTSGenerationCompleted,
)
from app.modules.live_call.transport.coordinator import (
    RealtimePipelineCoordinator,
    ResponseState,
    begin_response_feed,
)
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession
from jkr_conversation.streaming_llm import LLMResponseCompleted, LLMResponseStarted, TextDelta
from jkr_conversation.streaming_response import StreamingResponseAssembler


class _FakeTTSProvider:
    """Produces audio as each send_text() arrives — matching the REAL,
    live-verified Sarvam behavior (docs/SARVAM_STREAMING_TTS_CONTRACT.md:
    "audio is emitted automatically once the buffer crosses ~50 chars,
    with no flush needed at all"), not just at flush() time. Near-instant
    turnaround per chunk (matching P6's real measured TTFB ~200ms, far
    faster than this test's deliberately-slow multi-second LLM fake) — this
    asymmetry is what makes the concurrency proof meaningful rather than
    trivial: if TTS only ever responded at flush() (end of response), no
    implementation could pass the "before LLM finishes" assertion below."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.send_text_calls: list[str] = []
        self._audio_chunk_index = 0

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        self.send_text_calls.append(text)
        if self._audio_chunk_index == 0:
            await self._queue.put(TTSFirstAudio(response_id=response_id))
        await self._queue.put(
            TTSAudioChunk(response_id=response_id, audio_chunk_index=self._audio_chunk_index, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)
        )
        self._audio_chunk_index += 1

    async def flush(self, *, response_id):
        await self._queue.put(TTSGenerationCompleted(response_id=response_id))

    async def cancel(self, response_id):
        pass

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


async def _slow_llm_stream():
    """Three sentence-ending chunks, each separated by a real delay — the
    stream doesn't finish (LLMResponseCompleted) until ~350ms after it
    started, giving plenty of room to observe whether TTS/Twilio received
    the first chunk well before that."""
    yield LLMResponseStarted(request_id="r1")
    await asyncio.sleep(0.05)
    yield TextDelta(text="First sentence.")
    await asyncio.sleep(0.15)
    yield TextDelta(text=" Second sentence.")
    await asyncio.sleep(0.15)
    yield TextDelta(text=" Third sentence.")
    yield LLMResponseCompleted(full_text="First sentence. Second sentence. Third sentence.")


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def test_speakable_chunks_reach_tts_and_twilio_before_llm_generation_completes():
    """The decisive concurrency proof: the first chunk reaches TTS (and
    produces a real Twilio-outbound audio chunk) strictly BEFORE the LLM
    stream's own full-generation time — proving the pipeline does NOT wait
    for the whole LLM response before starting TTS (spec §44/§93/§150)."""
    tts_provider = _FakeTTSProvider()
    media_session = _media_session()
    tts_session = TTSStreamingSession(provider=tts_provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    coordinator.attach_tts_session(tts_session)

    feed = await begin_response_feed(coordinator, turn_id="turn-1")
    assert feed.on_chunk is not None

    t0 = time.monotonic()
    first_media_enqueued_at: float | None = None

    async def tracking_on_chunk(chunk):
        nonlocal first_media_enqueued_at
        await feed.on_chunk(chunk)
        if first_media_enqueued_at is None and media_session.outbound_queue.qsize() > 0:
            first_media_enqueued_at = time.monotonic() - t0

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_slow_llm_stream(), on_chunk=tracking_on_chunk)
    llm_full_generation_s = result.full_generation_ms / 1000

    assert result.full_text == "First sentence. Second sentence. Third sentence."
    assert first_media_enqueued_at is not None, "no audio ever reached Twilio's outbound queue"
    # The real proof: first Twilio-bound audio arrived measurably before
    # the LLM finished producing the ENTIRE response (~350ms) — with real
    # overlap margin, not just "happened to be equal or less."
    assert first_media_enqueued_at < llm_full_generation_s - 0.1, (
        f"first_media_enqueued_at={first_media_enqueued_at:.3f}s was not meaningfully "
        f"before llm_full_generation={llm_full_generation_s:.3f}s — pipeline may be serialized"
    )

    outcome = await feed.handle.finish()
    assert outcome.failed is False
    assert coordinator.active_response.state in (ResponseState.GENERATION_COMPLETE,)
    await tts_session.close()


async def test_llm_and_tts_and_twilio_all_active_at_the_same_instant():
    """A second, more direct proof: sample the pipeline's own state WHILE
    the LLM stream is still between chunks 2 and 3 — at that exact
    instant, TTS should already have produced audio in Twilio's outbound
    queue for chunk 0, and the coordinator's response should already be in
    TTS_STREAMING, not still waiting on the LLM."""
    tts_provider = _FakeTTSProvider()
    media_session = _media_session()
    tts_session = TTSStreamingSession(provider=tts_provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    coordinator.attach_tts_session(tts_session)

    feed = await begin_response_feed(coordinator, turn_id="turn-1")
    assembler = StreamingResponseAssembler()

    run_task = asyncio.create_task(assembler.run(_slow_llm_stream(), on_chunk=feed.on_chunk))
    # The LLM stream sleeps 0.05s then 0.15s between its first two chunks —
    # sampling at 0.12s lands strictly between chunk 0 arriving (~0.05s)
    # and chunk 1 arriving (~0.2s), while the LLM task is still running.
    await asyncio.sleep(0.12)

    assert not run_task.done(), "LLM stream finished before the sample point — test's timing assumption is invalid"
    assert media_session.outbound_queue.qsize() >= 1, "TTS/Twilio had not produced audio yet, despite the LLM still mid-stream"
    assert coordinator.active_response is not None
    assert coordinator.active_response.state == ResponseState.TTS_STREAMING

    result = await run_task
    assert result.full_text == "First sentence. Second sentence. Third sentence."
    await feed.handle.finish()
    await tts_session.close()
