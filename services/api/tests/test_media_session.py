from __future__ import annotations

import asyncio
import uuid

import pytest
from app.modules.live_call.transport.base import (
    AudioFrame,
    MediaSessionStatus,
    OutboundAudioChunk,
    PlaybackState,
)
from app.modules.live_call.transport.session import (
    InvalidSessionTransitionError,
    MediaSessionRegistry,
    RealtimeMediaSession,
)


def _session(**overrides) -> RealtimeMediaSession:
    defaults = dict(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    defaults.update(overrides)
    return RealtimeMediaSession(**defaults)


def _frame(data: bytes = b"\x00\x01" * 80) -> AudioFrame:
    return AudioFrame(data=data, codec="pcm16", sample_rate=8000, channels=1)


# --- state machine (spec §11, §53) -----------------------------------------------------


def test_normal_lifecycle_transitions():
    session = _session()
    assert session.status == MediaSessionStatus.CREATED
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    session.handle_twilio_start(stream_sid="MZ1", media_format={"encoding": "audio/x-mulaw", "sample_rate": 8000, "channels": 1})
    assert session.status == MediaSessionStatus.STREAMING
    assert session.twilio_stream_sid == "MZ1"


def test_invalid_transition_rejected():
    session = _session()
    with pytest.raises(InvalidSessionTransitionError):
        session.transition_to(MediaSessionStatus.STREAMING)  # can't skip straight from CREATED


def test_terminal_states_reject_every_transition():
    session = _session()
    session.close()
    assert session.status in (MediaSessionStatus.STOPPED, MediaSessionStatus.FAILED)
    with pytest.raises(InvalidSessionTransitionError):
        session.transition_to(MediaSessionStatus.CONNECTING)


# --- close() / idempotent cleanup (spec §34, §35, §37, §59, §61) -----------------------------------------------------


def test_close_from_streaming_reaches_stopped_via_closing():
    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    session.handle_twilio_start(stream_sid="MZ1", media_format={})
    assert session.close() is True
    assert session.status == MediaSessionStatus.STOPPED


def test_close_failed_reaches_failed_from_any_non_terminal_state():
    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    assert session.close(failed=True) is True
    assert session.status == MediaSessionStatus.FAILED


def test_close_before_ever_connecting_ends_in_failed_not_stuck():
    session = _session()
    assert session.close() is True
    assert session.status == MediaSessionStatus.FAILED  # no graceful path existed from CREATED


def test_close_is_idempotent_across_multiple_trigger_paths():
    # spec §61: stop event + socket close + explicit close() must only
    # produce ONE effective cleanup.
    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    first = session.close()  # e.g. the `stop` event handler
    second = session.close()  # e.g. the disconnect handler firing right after
    third = session.close()  # e.g. an explicit end-of-call path
    assert (first, second, third) == (True, False, False)


def test_close_cancels_all_registered_tasks():
    async def _run():
        session = _session()

        async def _never_ending():
            await asyncio.sleep(1000)

        task = asyncio.create_task(_never_ending())
        session.register_task(task)
        session.close()
        await asyncio.sleep(0)  # let cancellation propagate
        assert task.cancelled() or task.cancelling() > 0

    asyncio.run(_run())


# --- inbound audio / backpressure (spec §18, §19, §60) -----------------------------------------------------


def test_enqueue_and_dequeue_inbound_audio():
    async def _run():
        session = _session()
        frame = _frame()
        assert session.enqueue_inbound_audio(frame) is True
        got = await session.dequeue_inbound_audio()
        assert got is frame
        assert session.metrics.inbound_frames == 1
        assert session.metrics.inbound_bytes == len(frame.data)

    asyncio.run(_run())


def test_inbound_queue_backpressure_drops_rather_than_blocks():
    from app.modules.live_call.transport import session as session_module

    async def _run():
        session = _session()
        # Fill the queue completely without ever draining it.
        maxsize = session.inbound_audio_queue.maxsize
        for _ in range(maxsize):
            assert session.enqueue_inbound_audio(_frame()) is True
        # One more must be dropped, not block — this call must return
        # immediately (enqueue_inbound_audio is synchronous, not awaited).
        assert session.enqueue_inbound_audio(_frame()) is False
        assert session.metrics.dropped_inbound_frames == 1

    asyncio.run(_run())
    del session_module  # imported only to document where maxsize is configured; not otherwise used


# --- outbound audio / sequencing (spec §25, §55) -----------------------------------------------------


def test_response_sequence_ids_increment_chunk_index_and_reset_per_response():
    session = _session()
    seq1 = session.start_new_response_sequence()
    assert session.next_chunk_index() == 0
    assert session.next_chunk_index() == 1
    seq2 = session.start_new_response_sequence()
    assert seq2 != seq1
    assert session.next_chunk_index() == 0  # reset for the new response


def test_outbound_queue_round_trip():
    async def _run():
        session = _session()
        chunk = OutboundAudioChunk(response_sequence_id="resp_1", chunk_index=0, data=b"abc", sample_rate=8000)
        await session.enqueue_outbound_audio(chunk)
        got = await session.dequeue_outbound_audio()
        assert got is chunk

    asyncio.run(_run())


# --- marks / playback state (spec §26, §28, §56) -----------------------------------------------------


def test_mark_sent_and_acknowledged_tracked_separately():
    session = _session()
    name = session.next_mark_name()
    session.record_mark_sent(name)
    assert session.playback_state == PlaybackState.PLAYING
    assert name in session.metrics.marks_sent
    session.record_mark_acknowledged(name)
    assert session.playback_state == PlaybackState.IDLE
    assert name in session.metrics.marks_acknowledged


def test_mark_names_are_unique_per_session():
    session = _session()
    names = {session.next_mark_name() for _ in range(10)}
    assert len(names) == 10


# --- P6: wait_for_mark_ack (spec §59-61 closing-grace fix) -----------------------------------------------------


async def test_wait_for_mark_ack_returns_true_immediately_if_already_acknowledged():
    session = _session()
    name = session.next_mark_name()
    session.record_mark_sent(name)
    session.record_mark_acknowledged(name)
    result = await asyncio.wait_for(session.wait_for_mark_ack(name, timeout_seconds=1.0), timeout=1.0)
    assert result is True


async def test_wait_for_mark_ack_resolves_when_ack_arrives_later():
    session = _session()
    name = session.next_mark_name()
    session.record_mark_sent(name)

    async def ack_soon():
        await asyncio.sleep(0.02)
        session.record_mark_acknowledged(name)

    ack_task = asyncio.create_task(ack_soon())
    result = await session.wait_for_mark_ack(name, timeout_seconds=1.0)
    assert result is True
    await ack_task


async def test_wait_for_mark_ack_times_out_if_never_acknowledged():
    session = _session()
    name = session.next_mark_name()
    session.record_mark_sent(name)
    result = await session.wait_for_mark_ack(name, timeout_seconds=0.05)
    assert result is False


async def test_wait_for_mark_ack_cleans_up_pending_waiter_after_timeout():
    session = _session()
    name = session.next_mark_name()
    await session.wait_for_mark_ack(name, timeout_seconds=0.01)
    assert name not in session._mark_wait_events  # no leaked waiter state


async def test_wait_for_mark_ack_does_not_confuse_two_different_marks():
    session = _session()
    name_a, name_b = session.next_mark_name(), session.next_mark_name()
    session.record_mark_sent(name_a)
    session.record_mark_sent(name_b)
    session.record_mark_acknowledged(name_b)  # only B acked
    result_a = await session.wait_for_mark_ack(name_a, timeout_seconds=0.05)
    result_b = await session.wait_for_mark_ack(name_b, timeout_seconds=1.0)
    assert result_a is False
    assert result_b is True


# --- watchdog (spec §32) -----------------------------------------------------


def test_media_idle_detection():
    session = _session()
    assert session.is_media_idle(timeout_seconds=0.0) is False  # no media received yet at all -> not "idle", just never started
    session.touch_media()
    assert session.is_media_idle(timeout_seconds=1000.0) is False
    assert session.is_media_idle(timeout_seconds=-1.0) is True  # any positive elapsed time exceeds a negative timeout


# --- debug/observability (spec §43, §75) -----------------------------------------------------


def test_debug_dict_answers_the_required_observability_questions():
    session = _session()
    session.transition_to(MediaSessionStatus.CONNECTING)
    session.transition_to(MediaSessionStatus.CONNECTED)
    session.handle_twilio_start(stream_sid="MZ1", media_format={"encoding": "audio/x-mulaw", "sample_rate": 8000, "channels": 1})
    debug = session.to_debug_dict()
    for key in ("twilio_stream_sid", "status", "media_format", "connected_at", "inbound_frames", "outbound_frames", "dropped_inbound_frames", "marks_sent"):
        assert key in debug


# --- registry / session isolation (spec §62, §69) -----------------------------------------------------


def test_registry_add_get_remove():
    async def _run():
        registry = MediaSessionRegistry()
        session = _session()
        await registry.add(session)
        assert await registry.active_count() == 1
        fetched = await registry.get(session.call_session_id)
        assert fetched is session
        removed = await registry.remove(session.call_session_id)
        assert removed is session
        assert await registry.active_count() == 0

    asyncio.run(_run())


def test_two_concurrent_sessions_never_cross_queues():
    # spec §62: mandatory session isolation — call A's audio must never end
    # up in call B's queue.
    async def _run():
        registry = MediaSessionRegistry()
        session_a = _session()
        session_b = _session()
        await registry.add(session_a)
        await registry.add(session_b)

        frame_a = _frame(b"\xaa" * 160)
        frame_b = _frame(b"\xbb" * 160)
        session_a.enqueue_inbound_audio(frame_a)
        session_b.enqueue_inbound_audio(frame_b)

        got_a = await session_a.dequeue_inbound_audio()
        got_b = await session_b.dequeue_inbound_audio()
        assert got_a is frame_a
        assert got_b is frame_b
        assert session_a.inbound_audio_queue.empty()
        assert session_b.inbound_audio_queue.empty()

    asyncio.run(_run())
