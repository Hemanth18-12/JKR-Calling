"""RealtimePipelineCoordinator — response lifecycle, ownership,
supersession, playback-unit/mark/clear accounting, InterruptionSnapshot,
backpressure, dead-air classification, and two-call isolation. See
docs/REALTIME_PIPELINE_COORDINATOR.md.
"""

from __future__ import annotations

import asyncio
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
    DeadAirLevel,
    PlaybackUnitState,
    RealtimePipelineCoordinator,
    ResponseState,
    begin_response_feed,
    classify_dead_air,
)
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession
from jkr_conversation.streaming_response import SpeakableChunk


class _FakeProvider:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.cancelled: list[str] = []
        self._scripts: dict[str, list] = {}

    def script(self, response_id: str, events: list) -> None:
        self._scripts[response_id] = events

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        pass

    async def flush(self, *, response_id):
        for event in self._scripts.get(response_id, [TTSGenerationCompleted(response_id=response_id)]):
            await self._queue.put(event)

    async def cancel(self, response_id):
        self.cancelled.append(response_id)

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


def _audio(response_id: str, index: int, data: bytes = b"\xff" * 800) -> TTSAudioChunk:
    return TTSAudioChunk(response_id=response_id, audio_chunk_index=index, data=data, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


def _chunk(response_id: str, generation_id: str, index: int, text: str) -> SpeakableChunk:
    return SpeakableChunk(response_id=response_id, generation_id=generation_id, chunk_index=index, text=text, is_final=True, created_at=0.0)


async def _make_coordinator(provider: _FakeProvider, media_session: RealtimeMediaSession) -> tuple[RealtimePipelineCoordinator, TTSStreamingSession]:
    tts_session = TTSStreamingSession(provider=provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    coordinator.attach_tts_session(tts_session)
    return coordinator, tts_session


# --- lifecycle ---------------------------------------------------------


async def test_begin_response_starts_in_generating_text_state():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    assert ctx.state == ResponseState.GENERATING_TEXT
    assert ctx.call_id == coordinator._call_session_id  # noqa: SLF001 — test-only introspection
    await tts_session.close()


async def test_submit_speakable_chunk_advances_state_and_accumulates_text():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")

    ok = await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hello."))
    assert ok is True
    assert ctx.state == ResponseState.TTS_STREAMING
    assert ctx.text_generated == "Hello."
    assert ctx.text_committed_to_tts == "Hello."
    assert ctx.text_chunks_created == 1
    assert ctx.text_chunks_sent_to_tts == 1
    await tts_session.close()


async def test_complete_generation_builds_playback_units_and_transitions_state():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [TTSFirstAudio(response_id=ctx.response_id), _audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hello."))

    result = await coordinator.complete_generation(ctx.response_id)

    assert result.state == ResponseState.GENERATION_COMPLETE
    assert result.failed is False
    assert len(result.playback_units) == 1
    assert result.playback_units[0].audio_duration_ms == 100  # 800 bytes mulaw @ 8kHz
    assert result.audio_ms_generated == 100
    assert result.first_audio_ms is not None
    await tts_session.close()


async def test_wait_playback_complete_transitions_to_playback_complete():
    provider = _FakeProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)

    media_session.record_mark_sent(ctx.playback_units[0].mark_name)
    media_session.record_mark_acknowledged(ctx.playback_units[0].mark_name)

    acked = await coordinator.wait_playback_complete(ctx.response_id, timeout_seconds=1.0)
    assert acked is True
    assert ctx.state == ResponseState.PLAYBACK_COMPLETE
    await tts_session.close()


async def test_wait_playback_complete_with_no_units_sent_returns_true_trivially():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    acked = await coordinator.wait_playback_complete(ctx.response_id, timeout_seconds=0.2)
    assert acked is True
    await tts_session.close()


# --- ownership -----------------------------------------------------------


async def test_is_current_true_only_for_the_active_nonterminal_response():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    assert coordinator.is_current(ctx.response_id) is True
    assert coordinator.is_current("resp_never_existed") is False
    await tts_session.close()


async def test_submit_speakable_chunk_dropped_for_non_current_response():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    await coordinator.begin_response(turn_id="t1")

    accepted = await coordinator.submit_speakable_chunk("some-other-response-id", _chunk("some-other-response-id", "g", 0, "stale"))
    assert accepted is False
    await tts_session.close()


# --- supersede / cancel -----------------------------------------------------


async def test_begin_response_supersedes_unfinished_previous_response():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx1 = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx1.response_id, _chunk(ctx1.response_id, ctx1.generation_id, 0, "never finishes"))

    ctx2 = await coordinator.begin_response(turn_id="t2")

    assert ctx1.state == ResponseState.SUPERSEDED
    assert ctx1.superseded is True
    assert ctx2.state == ResponseState.GENERATING_TEXT
    assert provider.cancelled == [ctx1.response_id]
    await tts_session.close()


async def test_superseded_response_chunk_submission_is_dropped():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx1 = await coordinator.begin_response(turn_id="t1")
    await coordinator.begin_response(turn_id="t2")  # supersedes ctx1

    accepted = await coordinator.submit_speakable_chunk(ctx1.response_id, _chunk(ctx1.response_id, ctx1.generation_id, 1, "stale"))
    assert accepted is False
    await tts_session.close()


async def test_cancel_response_directly():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")

    await coordinator.cancel_response(ctx.response_id, reason="test_cancel")

    assert ctx.state == ResponseState.CANCELLED
    assert ctx.cancelled is True
    assert coordinator.active_response is None
    await tts_session.close()


async def test_cancel_already_terminal_response_is_a_noop():
    provider = _FakeProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)
    media_session.record_mark_sent(ctx.playback_units[0].mark_name)
    media_session.record_mark_acknowledged(ctx.playback_units[0].mark_name)
    await coordinator.wait_playback_complete(ctx.response_id, timeout_seconds=0.1)
    assert ctx.state == ResponseState.PLAYBACK_COMPLETE  # genuinely terminal now

    await coordinator.cancel_response(ctx.response_id, reason="too_late")
    assert ctx.state == ResponseState.PLAYBACK_COMPLETE  # unchanged — cancel on a terminal response is a no-op
    await tts_session.close()


# --- mark / clear accounting (PLAYED vs CLEARED) ----------------------------


async def test_mark_acknowledged_updates_unit_state_and_acknowledged_ms():
    provider = _FakeProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)

    unit = ctx.playback_units[0]
    assert unit.state == PlaybackUnitState.SENT
    media_session.record_mark_sent(unit.mark_name)
    media_session.record_mark_acknowledged(unit.mark_name)

    assert unit.state == PlaybackUnitState.ACKNOWLEDGED
    assert unit.mark_acknowledged_at is not None
    assert ctx.audio_ms_acknowledged == 100
    await tts_session.close()


async def test_duplicate_mark_ack_does_not_double_count():
    provider = _FakeProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)

    unit = ctx.playback_units[0]
    media_session.record_mark_sent(unit.mark_name)
    media_session.record_mark_acknowledged(unit.mark_name)
    media_session.record_mark_acknowledged(unit.mark_name)  # Twilio (or a bug) redelivers the same mark event

    assert ctx.audio_ms_acknowledged == 100  # not 200 — idempotent
    await tts_session.close()


async def test_clear_marks_pending_units_cleared_not_acknowledged():
    provider = _FakeProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), _audio(ctx.response_id, 1), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Two units."))
    await coordinator.complete_generation(ctx.response_id)

    unit0, unit1 = ctx.playback_units
    media_session.record_mark_sent(unit0.mark_name)
    media_session.record_mark_acknowledged(unit0.mark_name)  # unit0 genuinely played
    media_session.record_mark_sent(unit1.mark_name)
    media_session.request_clear_playback()  # unit1's mark never arrives before this — barge-in-style clear

    assert unit0.state == PlaybackUnitState.ACKNOWLEDGED
    assert unit1.state == PlaybackUnitState.CLEARED

    # a late mark for unit1 must NOT flip it back to ACKNOWLEDGED
    media_session.record_mark_acknowledged(unit1.mark_name)
    assert unit1.state == PlaybackUnitState.CLEARED
    assert ctx.audio_ms_acknowledged == 100  # only unit0's duration ever counted
    await tts_session.close()


# --- InterruptionSnapshot / P8 readiness ------------------------------------


async def test_interrupt_active_response_returns_snapshot_and_cancels():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)

    snapshot = await coordinator.interrupt_active_response(reason="test_interrupt")

    assert snapshot is not None
    assert snapshot.response_id == ctx.response_id
    assert snapshot.audio_generated_ms == 100
    assert snapshot.pending_playback_ms == 100  # sent but never acknowledged
    assert len(snapshot.playback_units) == 1
    # P8 — a customer-caused interruption lands on the distinct INTERRUPTED
    # terminal state, not CANCELLED (see coordinator.py's ResponseState).
    assert ctx.state == ResponseState.INTERRUPTED
    assert coordinator.active_response is None
    await tts_session.close()


async def test_interrupt_with_no_active_response_returns_none():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    snapshot = await coordinator.interrupt_active_response(reason="nothing_active")
    assert snapshot is None
    await tts_session.close()


# --- backpressure / dead-air -------------------------------------------------


def test_classify_dead_air_boundaries():
    assert classify_dead_air(0) == DeadAirLevel.OK
    assert classify_dead_air(1499) == DeadAirLevel.OK
    assert classify_dead_air(1500) == DeadAirLevel.WARNING
    assert classify_dead_air(3999) == DeadAirLevel.WARNING
    assert classify_dead_air(4000) == DeadAirLevel.FATAL
    assert classify_dead_air(10000) == DeadAirLevel.FATAL


async def test_dead_air_status_reports_stage_and_elapsed():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")

    status = coordinator.dead_air_status(now=ctx.created_at + 2.0)  # +2000ms
    assert status is not None
    assert status.level == DeadAirLevel.WARNING
    assert status.stage == ResponseState.GENERATING_TEXT.value
    assert status.elapsed_ms >= 1999
    await tts_session.close()


async def test_dead_air_status_none_when_nothing_active():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    assert coordinator.dead_air_status() is None
    await tts_session.close()


async def test_backpressure_snapshot_reports_pending_audio_and_queue_depth():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())
    ctx = await coordinator.begin_response(turn_id="t1")
    provider.script(ctx.response_id, [_audio(ctx.response_id, 0), TTSGenerationCompleted(response_id=ctx.response_id)])
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hi."))
    await coordinator.complete_generation(ctx.response_id)

    snapshot = coordinator.backpressure_snapshot()
    assert snapshot["twilio_outbound_queue_depth"] == 1
    assert snapshot["twilio_playback_backlog_ms"] == 100
    assert snapshot["active_response_id"] == ctx.response_id
    assert snapshot["active_response_state"] == ResponseState.GENERATION_COMPLETE.value
    await tts_session.close()


# --- begin_response_feed ----------------------------------------------------


async def test_begin_response_feed_none_coordinator_returns_noop_feed():
    feed = await begin_response_feed(None, turn_id="t1")
    assert feed.handle is None
    assert feed.on_chunk is None
    assert feed.callback_fired() is False


async def test_begin_response_feed_wires_callback_through_coordinator():
    provider = _FakeProvider()
    coordinator, tts_session = await _make_coordinator(provider, _media_session())

    feed = await begin_response_feed(coordinator, turn_id="t1")
    assert feed.callback_fired() is False
    assert feed.handle is not None

    await feed.on_chunk(SpeakableChunk(response_id="whatever", generation_id="g", chunk_index=0, text="hello", is_final=True, created_at=0.0))
    assert feed.callback_fired() is True
    outcome = await feed.handle.finish()
    assert outcome.failed is False
    await tts_session.close()


# --- two-call isolation ------------------------------------------------------


async def test_two_coordinators_never_share_active_response_or_playback_units():
    provider_a, provider_b = _FakeProvider(), _FakeProvider()
    media_a, media_b = _media_session(), _media_session()
    coordinator_a, tts_a = await _make_coordinator(provider_a, media_a)
    coordinator_b, tts_b = await _make_coordinator(provider_b, media_b)

    ctx_a = await coordinator_a.begin_response(turn_id="ta")
    ctx_b = await coordinator_b.begin_response(turn_id="tb")
    provider_a.script(ctx_a.response_id, [_audio(ctx_a.response_id, 0, data=b"\x01" * 800), TTSGenerationCompleted(response_id=ctx_a.response_id)])
    provider_b.script(ctx_b.response_id, [_audio(ctx_b.response_id, 0, data=b"\x02" * 800), TTSGenerationCompleted(response_id=ctx_b.response_id)])
    await coordinator_a.submit_speakable_chunk(ctx_a.response_id, _chunk(ctx_a.response_id, ctx_a.generation_id, 0, "A"))
    await coordinator_b.submit_speakable_chunk(ctx_b.response_id, _chunk(ctx_b.response_id, ctx_b.generation_id, 0, "B"))
    await coordinator_a.complete_generation(ctx_a.response_id)
    await coordinator_b.complete_generation(ctx_b.response_id)

    assert coordinator_a.active_response.response_id == ctx_a.response_id
    assert coordinator_b.active_response.response_id == ctx_b.response_id
    # Mark names are only unique WITHIN one call's own media session (each
    # RealtimeMediaSession has its own independent counter) — two separate
    # calls legitimately both producing "jkr-mark-1" is expected, not a
    # collision. What must never happen is acking one call's mark
    # affecting the other call's accounting, checked below.
    assert ctx_a.playback_units[0].response_id != ctx_b.playback_units[0].response_id
    # acking a mark on call A must never affect call B's units
    media_a.record_mark_sent(ctx_a.playback_units[0].mark_name)
    media_a.record_mark_acknowledged(ctx_a.playback_units[0].mark_name)
    assert ctx_a.audio_ms_acknowledged == 100
    assert ctx_b.audio_ms_acknowledged == 0
    await tts_a.close()
    await tts_b.close()
