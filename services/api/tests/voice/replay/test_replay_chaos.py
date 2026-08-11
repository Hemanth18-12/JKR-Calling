"""P9 §124-128 — chaos/property tests: randomized event ordering and rapid
repeated interruption cycles through the REAL RealtimePipelineCoordinator +
TTSStreamingSession + RealtimeMediaSession pipeline (only the provider
network boundary faked), asserting the one property that matters most:

    Every outbound Twilio media envelope must belong to the active valid
    sequence at send time (spec §128) — and stale_audio_sent_total, the
    zero-leak metric, must stay 0 no matter how aggressively responses are
    interrupted, superseded, or overlapped.

See docs/REALTIME_OUTPUT_INVARIANTS.md, docs/P9_REPLAY_PROTECTION_RESULTS.md.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
    TTSGenerationCompleted,
)
from app.modules.live_call.transport.coordinator import RealtimePipelineCoordinator
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession
from jkr_conversation.streaming_response import SpeakableChunk


class _FakeTTSProvider:
    """Produces audio as each send_text() arrives (matches the real,
    verified Sarvam behavior — same pattern used throughout P7/P8/P9's own
    test suites)."""

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


async def _make_coordinator(provider: _FakeTTSProvider, media_session: RealtimeMediaSession) -> tuple[RealtimePipelineCoordinator, TTSStreamingSession]:
    tts_session = TTSStreamingSession(provider=provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    coordinator.attach_tts_session(tts_session)
    return coordinator, tts_session


def _drain_through_output_gate(coordinator: RealtimePipelineCoordinator, media_session: RealtimeMediaSession) -> tuple[int, int]:
    """Simulates exactly what twilio_media_stream.py's _send_loop does for
    every queued chunk — the same final gate, called from the same single
    place a real send loop would call it. Returns (allowed_count,
    blocked_count); a chunk that would have been genuinely sent to a real
    Twilio socket is never actually sent here (no real websocket in this
    test), but the DECISION is the real one, from the real coordinator."""
    allowed = 0
    blocked = 0
    while not media_session.outbound_queue.empty():
        chunk = media_session.outbound_queue.get_nowait()
        decision = coordinator.can_send_media(chunk)
        if decision.allowed:
            allowed += 1
        else:
            blocked += 1
    return allowed, blocked


async def test_randomized_rapid_response_churn_never_leaks_stale_audio():
    """Spec §127-128 — randomized interleaving of begin_response, chunk
    submission, interrupt, cancel, and normal completion, run through the
    real pipeline. Fixed seed: deterministic and reproducible if it ever
    fails, not flaky."""
    random.seed(20260810)
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)

    total_allowed = 0
    total_blocked = 0
    for cycle in range(40):
        ctx = await coordinator.begin_response(turn_id=f"t{cycle}")
        for i in range(random.randint(1, 3)):
            await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, i, f"chunk {i} of cycle {cycle}"))
        await asyncio.sleep(0)  # let the sender/consumer tasks actually run this cycle's work

        action = random.choice(["interrupt", "cancel", "complete", "supersede_via_next", "clear_then_complete"])
        if action == "interrupt":
            await coordinator.interrupt_active_response(reason="chaos")
        elif action == "cancel":
            await coordinator.cancel_response(ctx.response_id, reason="chaos")
        elif action == "complete":
            await coordinator.complete_generation(ctx.response_id)
        elif action == "clear_then_complete":
            media_session.request_clear_playback()
            await coordinator.complete_generation(ctx.response_id)
        # "supersede_via_next": left active — the NEXT cycle's begin_response() auto-supersedes it

        allowed, blocked = _drain_through_output_gate(coordinator, media_session)
        total_allowed += allowed
        total_blocked += blocked

    # The property that actually matters (spec §97/§150-151): no matter how
    # aggressively responses churned, nothing stale ever reached the point
    # where it would have been sent to a real Twilio socket.
    assert replay_metrics.stale_audio_sent_total == 0
    # Sanity: the chaos actually exercised both outcomes, not just one.
    assert total_allowed > 0
    assert total_blocked > 0
    await tts_session.close()


async def test_ten_rapid_interruptions_no_leaked_provider_cancels_no_stale_audio():
    """Spec §124 — response/interrupt/response/interrupt.../ 10 times in a
    row, back to back. No stale audio, and exactly one provider cancel()
    call per genuinely-interrupted response (never zero, never doubled)."""
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)

    response_ids: list[str] = []
    for cycle in range(10):
        ctx = await coordinator.begin_response(turn_id=f"t{cycle}")
        response_ids.append(ctx.response_id)
        await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, f"Reply number {cycle}."))
        await asyncio.sleep(0)
        snapshot = await coordinator.interrupt_active_response(reason=f"chaos_interrupt_{cycle}")
        assert snapshot is not None
        assert snapshot.response_id == ctx.response_id
        _drain_through_output_gate(coordinator, media_session)

    assert len(set(response_ids)) == 10  # every cycle minted a genuinely fresh response_id — never reused
    assert sorted(provider.cancelled) == sorted(set(response_ids))  # exactly one cancel per response, no leaks, no duplicates
    assert replay_metrics.stale_audio_sent_total == 0
    await tts_session.close()


async def test_hundred_rapid_supersessions_context_growth_is_linear_not_exponential():
    """Spec §125/§136 — a cheap proxy for "no runaway memory growth": 100
    back-to-back begin_response() calls (each auto-superseding the last)
    must leave the coordinator with exactly 100 tracked contexts — one per
    response, never more (no duplication, no accidental fan-out) — and
    every earlier one correctly terminal."""
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)

    for cycle in range(100):
        await coordinator.begin_response(turn_id=f"t{cycle}")

    assert len(coordinator._contexts) == 100  # noqa: SLF001 — introspection to prove bounded, exactly-once growth
    terminal_count = sum(1 for ctx in coordinator._contexts.values() if ctx.is_terminal())  # noqa: SLF001
    assert terminal_count == 99  # every one except the current, still-active last response
    assert replay_metrics.stale_audio_sent_total == 0
    await tts_session.close()
