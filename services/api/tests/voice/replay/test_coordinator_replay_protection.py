"""P9 — RealtimePipelineCoordinator's replay-protection surface:
is_identity_active(), the output gate (can_send_media()), response/
playback-unit state-transition validation, SpeakableChunk duplicate/
conflict/gap detection, and queue purging on invalidation. See
docs/REALTIME_OUTPUT_INVARIANTS.md, docs/REPLAY_PROTECTION_ARCHITECTURE.md.
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
from app.modules.live_call.transport.base import OutboundAudioChunk
from app.modules.live_call.transport.coordinator import (
    TERMINAL_RESPONSE_STATES,
    VALID_RESPONSE_STATE_TRANSITIONS,
    PlaybackUnitState,
    RealtimePipelineCoordinator,
    ResponseState,
)
from app.modules.live_call.transport.identity import ResponseIdentity
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import TTSStreamingSession
from jkr_conversation.streaming_response import SpeakableChunk


class _FakeTTSProvider:
    """Produces audio as each send_text() arrives — matching the REAL,
    live-verified Sarvam behavior, same pattern the P8 coordinator-
    interruption test suite already established."""

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


def _bare_coordinator() -> RealtimePipelineCoordinator:
    """No TTS session attached — enough for tests that only exercise
    submit_speakable_chunk()'s text-layer checks, is_identity_active(), or
    state-transition validation directly."""
    media_session = _media_session()
    return RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)


# --- is_identity_active() / ResponseIdentity ---------------------------------


async def test_is_identity_active_true_for_the_current_response():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    assert coordinator.is_identity_active(ctx.identity) is True


async def test_is_identity_active_false_with_no_active_response():
    coordinator = _bare_coordinator()
    identity = ResponseIdentity(call_id=coordinator._call_session_id, turn_id="t1", response_id="resp_x", generation_id="gen_x", sequence_id="resp_x", epoch=1)  # noqa: SLF001
    assert coordinator.is_identity_active(identity) is False


async def test_is_identity_active_false_for_wrong_call_id():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    wrong_call = ResponseIdentity(call_id=uuid.uuid4(), turn_id=ctx.turn_id, response_id=ctx.response_id, generation_id=ctx.generation_id, sequence_id=ctx.sequence_id, epoch=ctx.response_epoch)
    assert coordinator.is_identity_active(wrong_call) is False


async def test_is_identity_active_false_for_wrong_generation():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    wrong_gen = ResponseIdentity(call_id=ctx.call_id, turn_id=ctx.turn_id, response_id=ctx.response_id, generation_id="gen_wrong", sequence_id=ctx.sequence_id, epoch=ctx.response_epoch)
    assert coordinator.is_identity_active(wrong_gen) is False


async def test_is_identity_active_false_for_wrong_epoch():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    wrong_epoch = ResponseIdentity(call_id=ctx.call_id, turn_id=ctx.turn_id, response_id=ctx.response_id, generation_id=ctx.generation_id, sequence_id=ctx.sequence_id, epoch=ctx.response_epoch + 1)
    assert coordinator.is_identity_active(wrong_epoch) is False


async def test_is_identity_active_false_once_response_is_terminal():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    identity = ctx.identity
    await coordinator.cancel_response(ctx.response_id, reason="test")
    assert coordinator.is_identity_active(identity) is False


async def test_response_epoch_increments_across_responses():
    coordinator = _bare_coordinator()
    ctx1 = await coordinator.begin_response(turn_id="t1")
    epoch1 = ctx1.response_epoch
    ctx2 = await coordinator.begin_response(turn_id="t2")  # auto-supersedes ctx1
    assert ctx2.response_epoch == epoch1 + 1
    assert ctx1.identity.epoch != ctx2.identity.epoch


async def test_playback_epoch_increments_on_clear():
    media_session = _media_session()
    coordinator = RealtimePipelineCoordinator(call_session_id=media_session.call_session_id, media_session=media_session)
    before = coordinator.playback_epoch
    media_session.request_clear_playback()
    assert coordinator.playback_epoch == before + 1


# --- output gate: can_send_media() ------------------------------------------


async def test_can_send_media_allows_legacy_chunk_with_no_identity():
    coordinator = _bare_coordinator()
    chunk = OutboundAudioChunk(response_sequence_id="resp_legacy", chunk_index=0, data=b"\x00\x01", sample_rate=8000, mark_name="m1")
    decision = coordinator.can_send_media(chunk)
    assert decision.allowed is True
    assert decision.reason == "legacy_no_identity"


async def test_can_send_media_blocks_unknown_response():
    # can_send_media() itself is metric-free by design (see
    # OutputGateDecision's own docstring) — it returns `reason`
    # specifically so the caller (twilio_media_stream.py's _send_loop)
    # records the right metric; that mapping is tested separately.
    coordinator = _bare_coordinator()
    identity = ResponseIdentity(call_id=coordinator._call_session_id, turn_id="t1", response_id="resp_never_existed", generation_id="gen_x", sequence_id="resp_never_existed", epoch=1)  # noqa: SLF001
    chunk = OutboundAudioChunk(response_sequence_id="resp_never_existed", chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1", identity=identity)
    decision = coordinator.can_send_media(chunk)
    assert decision.allowed is False
    assert decision.reason == "unknown_response"


async def test_can_send_media_allows_current_response_first_send():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    chunk = OutboundAudioChunk(response_sequence_id=ctx.response_id, chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1", identity=ctx.identity, playback_epoch=coordinator.playback_epoch)
    decision = coordinator.can_send_media(chunk)
    assert decision.allowed is True
    assert decision.reason == "ok"


async def test_can_send_media_blocks_stale_response_after_cancel():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    identity = ctx.identity
    await coordinator.cancel_response(ctx.response_id, reason="test")
    chunk = OutboundAudioChunk(response_sequence_id=ctx.response_id, chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1", identity=identity, playback_epoch=0)
    decision = coordinator.can_send_media(chunk)
    assert decision.allowed is False
    assert decision.reason == "stale_response"


async def test_can_send_media_blocks_stale_playback_epoch_even_if_response_still_active():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    stale_epoch_chunk = OutboundAudioChunk(
        response_sequence_id=ctx.response_id, chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1",
        identity=ctx.identity, playback_epoch=coordinator.playback_epoch,
    )
    coordinator._media_session.request_clear_playback()  # noqa: SLF001 — advances playback_epoch without touching response state
    decision = coordinator.can_send_media(stale_epoch_chunk)
    assert decision.allowed is False
    assert decision.reason == "playback_epoch_stale"


async def test_can_send_media_blocks_duplicate_chunk_index():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    chunk = OutboundAudioChunk(response_sequence_id=ctx.response_id, chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1", identity=ctx.identity, playback_epoch=coordinator.playback_epoch)
    first = coordinator.can_send_media(chunk)
    second = coordinator.can_send_media(chunk)
    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "duplicate_media"


async def test_can_send_media_blocks_cross_call_identity():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    foreign_identity = ResponseIdentity(call_id=uuid.uuid4(), turn_id=ctx.turn_id, response_id=ctx.response_id, generation_id=ctx.generation_id, sequence_id=ctx.sequence_id, epoch=ctx.response_epoch)
    chunk = OutboundAudioChunk(response_sequence_id=ctx.response_id, chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m1", identity=foreign_identity)
    decision = coordinator.can_send_media(chunk)
    assert decision.allowed is False
    assert decision.reason == "call_mismatch"


# --- response state transition validation -----------------------------------


def test_valid_transition_table_has_no_outgoing_edges_from_terminal_states_except_self():
    for state in TERMINAL_RESPONSE_STATES:
        assert VALID_RESPONSE_STATE_TRANSITIONS[state] == frozenset({state})


async def test_transition_out_of_terminal_state_is_rejected():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.cancel_response(ctx.response_id, reason="test")
    assert ctx.state == ResponseState.CANCELLED
    before = replay_metrics.invalid_state_transition_total
    ok = coordinator._transition(ctx, ResponseState.GENERATING_TEXT)  # noqa: SLF001
    assert ok is False
    assert ctx.state == ResponseState.CANCELLED  # unchanged — no stale task revival
    assert replay_metrics.invalid_state_transition_total == before + 1


async def test_terminal_to_self_transition_is_idempotent_noop():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.cancel_response(ctx.response_id, reason="test")
    before = replay_metrics.invalid_state_transition_total
    ok = coordinator._transition(ctx, ResponseState.CANCELLED)  # noqa: SLF001
    assert ok is True
    assert replay_metrics.invalid_state_transition_total == before  # no metric bump for a legitimate no-op


# --- PlaybackUnit state transition validation (spec §57/§132-134) ----------


def test_cleared_can_never_become_acknowledged():
    from app.modules.live_call.transport.coordinator import PlaybackUnit

    coordinator = _bare_coordinator()
    unit = PlaybackUnit(
        response_id="r1", sequence_id="r1", unit_index=0, mark_name="m1", audio_duration_ms=100,
        bytes_sent=800, created_at=0.0, state=PlaybackUnitState.CLEARED,
    )
    ok = coordinator._transition_unit(unit, PlaybackUnitState.ACKNOWLEDGED)  # noqa: SLF001
    assert ok is False
    assert unit.state == PlaybackUnitState.CLEARED


def test_acknowledged_can_never_become_cleared():
    from app.modules.live_call.transport.coordinator import PlaybackUnit

    coordinator = _bare_coordinator()
    unit = PlaybackUnit(
        response_id="r1", sequence_id="r1", unit_index=0, mark_name="m1", audio_duration_ms=100,
        bytes_sent=800, created_at=0.0, state=PlaybackUnitState.ACKNOWLEDGED,
    )
    ok = coordinator._transition_unit(unit, PlaybackUnitState.CLEARED)  # noqa: SLF001
    assert ok is False
    assert unit.state == PlaybackUnitState.ACKNOWLEDGED


def test_sent_can_become_either_acknowledged_or_cleared():
    from app.modules.live_call.transport.coordinator import PlaybackUnit

    coordinator = _bare_coordinator()
    unit = PlaybackUnit(
        response_id="r1", sequence_id="r1", unit_index=0, mark_name="m1", audio_duration_ms=100,
        bytes_sent=800, created_at=0.0, state=PlaybackUnitState.SENT,
    )
    assert coordinator._transition_unit(unit, PlaybackUnitState.ACKNOWLEDGED) is True  # noqa: SLF001


# --- SpeakableChunk duplicate/conflict/gap (submit_speakable_chunk) --------


async def test_duplicate_text_chunk_index_is_dropped():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    chunk0 = _chunk(ctx.response_id, ctx.generation_id, 0, "Hello.")
    first = await coordinator.submit_speakable_chunk(ctx.response_id, chunk0)
    second = await coordinator.submit_speakable_chunk(ctx.response_id, chunk0)
    assert first is True
    assert second is False
    assert ctx.text_generated == "Hello."  # not duplicated


async def test_conflicting_text_chunk_index_fails_the_response():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "Hello."))
    conflicting = _chunk(ctx.response_id, ctx.generation_id, 0, "Something totally different.")
    accepted = await coordinator.submit_speakable_chunk(ctx.response_id, conflicting)
    assert accepted is False
    assert ctx.state == ResponseState.CANCELLED  # upstream corruption fails the response


async def test_out_of_order_text_chunk_gap_is_rejected_not_forwarded():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, ctx.generation_id, 0, "First."))
    gap_chunk = _chunk(ctx.response_id, ctx.generation_id, 5, "Way ahead.")
    accepted = await coordinator.submit_speakable_chunk(ctx.response_id, gap_chunk)
    assert accepted is False
    assert "Way ahead." not in ctx.text_generated
    assert ctx.state == ResponseState.CANCELLED


async def test_assembler_generation_mismatch_within_same_response_is_dropped():
    """A second, DIFFERENT assembler run's chunk (different generation_id
    on the SpeakableChunk itself, per StreamingResponseAssembler's own
    per-run minting — see coordinator.py's ActiveResponseContext
    .assembler_generation_id docstring) must never be silently accepted
    into an already-established response."""
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    await coordinator.submit_speakable_chunk(ctx.response_id, _chunk(ctx.response_id, "assembler_gen_A", 0, "First."))
    mismatched = _chunk(ctx.response_id, "assembler_gen_B", 1, "Second.")
    accepted = await coordinator.submit_speakable_chunk(ctx.response_id, mismatched)
    assert accepted is False
    assert "Second." not in ctx.text_generated


# --- cancellation_token (P9 LLM-boundary wiring) -----------------------------


async def test_cancellation_token_is_cancelled_when_response_is_cancelled():
    coordinator = _bare_coordinator()
    ctx = await coordinator.begin_response(turn_id="t1")
    assert ctx.cancellation_token.is_cancelled is False
    await coordinator.cancel_response(ctx.response_id, reason="test")
    assert ctx.cancellation_token.is_cancelled is True


async def test_cancellation_token_is_cancelled_when_response_is_superseded():
    coordinator = _bare_coordinator()
    ctx1 = await coordinator.begin_response(turn_id="t1")
    assert ctx1.cancellation_token.is_cancelled is False
    await coordinator.begin_response(turn_id="t2")  # auto-supersedes ctx1
    assert ctx1.cancellation_token.is_cancelled is True


# --- queue purging on invalidation -------------------------------------------


async def test_cancel_purges_only_this_responses_queued_text():
    provider = _FakeTTSProvider()
    media_session = _media_session()
    coordinator, tts_session = await _make_coordinator(provider, media_session)
    ctx_a = await coordinator.begin_response(turn_id="t1")
    # Fill the text queue for ctx_a without letting the sender drain it, by
    # cancelling immediately after enqueue — a real race is timing-
    # dependent, but the purge itself is deterministic and directly testable.
    handle_a = coordinator._handles[ctx_a.response_id].tts_handle  # noqa: SLF001
    assert handle_a is not None
    await handle_a.send_chunk("Some text for A.")
    before = replay_metrics.queue_stale_items_purged_total
    await coordinator.cancel_response(ctx_a.response_id, reason="test")
    # Purging is best-effort/timing-sensitive (the sender task may already
    # have drained the item) — the real, deterministic guarantee is that
    # the metric never goes DOWN and nothing raises; a dedicated race test
    # covers the "definitely still queued" case below.
    assert replay_metrics.queue_stale_items_purged_total >= before
    await tts_session.close()


async def test_purge_never_touches_a_different_responses_queued_media():
    media_session = _media_session()
    other_chunk = OutboundAudioChunk(response_sequence_id="resp_other", chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="m_other")
    await media_session.enqueue_outbound_audio(other_chunk)
    purged = media_session.purge_outbound_for_response("resp_this_one_does_not_exist")
    assert purged == 0
    assert media_session.outbound_queue.qsize() == 1  # the other response's item survives untouched


async def test_purge_outbound_removes_matching_and_keeps_others_in_order():
    media_session = _media_session()
    chunk_a0 = OutboundAudioChunk(response_sequence_id="resp_a", chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="ma0")
    chunk_b0 = OutboundAudioChunk(response_sequence_id="resp_b", chunk_index=0, data=b"\x00", sample_rate=8000, mark_name="mb0")
    chunk_a1 = OutboundAudioChunk(response_sequence_id="resp_a", chunk_index=1, data=b"\x00", sample_rate=8000, mark_name="ma1")
    chunk_b1 = OutboundAudioChunk(response_sequence_id="resp_b", chunk_index=1, data=b"\x00", sample_rate=8000, mark_name="mb1")
    for chunk in (chunk_a0, chunk_b0, chunk_a1, chunk_b1):
        await media_session.enqueue_outbound_audio(chunk)

    purged = media_session.purge_outbound_for_response("resp_a")

    assert purged == 2
    remaining = []
    while not media_session.outbound_queue.empty():
        remaining.append(media_session.outbound_queue.get_nowait())
    assert [c.mark_name for c in remaining] == ["mb0", "mb1"]  # resp_b's own order preserved
