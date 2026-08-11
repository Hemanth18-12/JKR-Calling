"""RealtimeMediaSession — the single stateful object one Twilio Media
Stream WebSocket connection maps to, and MediaSessionRegistry, the
encapsulated in-memory table of currently-active sessions on this process.

Deliberately holds state + queues + transition rules only, not the actual
asyncio receive/process/send loop tasks themselves — those are created and
owned by the WebSocket handler function in twilio_media_stream.py (spec
§17's Task 1-4 separation), which registers them here via `register_task()`
so `close()` has one authoritative place to cancel everything regardless of
which path triggered the close (stop event, disconnect, watchdog, an
explicit call-ended-elsewhere check — spec §34-37).

Single-process, in-memory registry — a known, documented limitation (spec
§70/§71), not an oversight: a Media Stream WebSocket is inherently
stateful for its connection's lifetime, and distributing an active
connection across processes is explicitly out of scope for P2. Durable
business state (CallSession.state, conversation_state) already lives in
Postgres/Redis via the same path the <Record> transport uses — only the
live audio plumbing itself is process-local.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.live_call.transport.base import (
    VALID_STATUS_TRANSITIONS,
    AudioFrame,
    MediaSessionStatus,
    OutboundAudioChunk,
    PlaybackState,
)
from app.modules.live_call.transport.events import SessionMetrics, log_event
from app.modules.live_call.transport.events import metrics as global_metrics

if TYPE_CHECKING:
    from app.modules.live_call.transport.coordinator import RealtimePipelineCoordinator
    from app.modules.live_call.transport.tts_bridge import TTSStreamingSession

# Sized in audio-duration terms, per spec §18 — 8kHz mono 16-bit PCM is
# 16,000 bytes/sec; ~250 frames of Twilio's ~20ms chunks is ~5 seconds of
# audio, a generous buffer against a momentarily slow consumer without
# risking unbounded memory growth if the consumer stalls entirely.
DEFAULT_INBOUND_QUEUE_MAXSIZE = 250
DEFAULT_OUTBOUND_QUEUE_MAXSIZE = 250

DEFAULT_MEDIA_IDLE_TIMEOUT_SECONDS = 30.0  # spec §33 — no inbound media at all for this long => watchdog flags it
DEFAULT_INITIAL_CONNECT_TIMEOUT_SECONDS = 15.0  # spec §33 — no Twilio `start` event within this long after WS connect


class InvalidSessionTransitionError(Exception):
    pass


@dataclass
class RealtimeMediaSession:
    call_session_id: uuid.UUID
    workspace_id: uuid.UUID
    twilio_call_sid: str
    agent_id: uuid.UUID | None = None

    twilio_stream_sid: str | None = None
    status: MediaSessionStatus = MediaSessionStatus.CREATED
    playback_state: PlaybackState = PlaybackState.IDLE

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    connected_at: datetime | None = None
    last_twilio_event_at: float | None = None  # time.monotonic() — for the watchdog, never wall-clock (spec §39)
    last_media_at: float | None = None

    current_response_sequence_id: str | None = None
    current_response_chunk_index: int = 0

    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    media_format: dict | None = None  # start.mediaFormat, captured verbatim for debugging (§43)

    inbound_audio_queue: asyncio.Queue[AudioFrame] = field(default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_INBOUND_QUEUE_MAXSIZE))
    outbound_queue: asyncio.Queue[OutboundAudioChunk] = field(default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_OUTBOUND_QUEUE_MAXSIZE))

    _tasks: list[asyncio.Task] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)
    _mark_counter: int = field(default=0, repr=False)
    # P6 — one Event per mark someone is actively waiting on, so a caller
    # (the closing-grace path) can await "has THIS specific mark actually
    # played" instead of polling playback_state or a fixed timer. Not a
    # dict of every mark ever sent (unbounded growth over a long call) —
    # entries are created lazily by wait_for_mark_ack() and popped once
    # resolved, in both the ack and the timeout path.
    _mark_wait_events: dict[str, asyncio.Event] = field(default_factory=dict, repr=False)
    # P6 — set by _processing_loop when TTS_MODE=streaming and a
    # connection was established for this call; the main WebSocket handler
    # closes it in its own finally block (session.close() only cancels
    # tasks, it doesn't know how to close a provider connection). None
    # under TTS_MODE=batch, or if the streaming connection failed to
    # establish (falls back to batch for the whole call rather than
    # failing call setup over it).
    tts_streaming_session: TTSStreamingSession | None = field(default=None, repr=False)
    # P7 — always created alongside tts_streaming_session (never on its
    # own); None under TTS_MODE=batch, matching tts_streaming_session's
    # own lifecycle exactly.
    pipeline_coordinator: RealtimePipelineCoordinator | None = field(default=None, repr=False)
    # P7 — optional observer hooks so RealtimePipelineCoordinator can build
    # PlaybackUnit accounting (spec §25-31) without RealtimeMediaSession
    # needing to know the coordinator exists. Both fire AFTER this class's
    # own bookkeeping (marks_acknowledged/playback_state) is already
    # updated, so a coordinator reading self.metrics inside its own
    # handler always sees consistent state. None (the default) means no
    # coordinator is attached — every P6 call path keeps working exactly
    # as before.
    on_mark_acknowledged: Callable[[str], None] | None = field(default=None, repr=False)
    on_playback_clear: Callable[[], None] | None = field(default=None, repr=False)
    # P8 — the inverse decoupling: clear_agent_audio() needs a WebSocket
    # reference, which only the top-level twilio_media_stream_websocket()
    # handler has (see docs/P8_BARGE_IN_AUDIT.md §6). Set once, there, to a
    # closure over that handler's own `websocket`, so RealtimePipelineCoordinator
    # can trigger a real Twilio clear without needing a WebSocket itself.
    # None under TTS_MODE=batch or before the handler has wired it up —
    # interrupt_active_response() treats that as "nothing to clear."
    send_twilio_clear: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)

    # --- state machine -----------------------------------------------------

    def transition_to(self, new_status: MediaSessionStatus) -> None:
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidSessionTransitionError(f"{self.status} -> {new_status} is not a valid transition")
        self.status = new_status
        if new_status == MediaSessionStatus.CONNECTED and self.connected_at is None:
            self.connected_at = datetime.now(UTC)
        log_event("media_session_status_changed", call_session_id=self.call_session_id, status=new_status.value)

    # --- lifecycle -----------------------------------------------------

    def register_task(self, task: asyncio.Task) -> None:
        self._tasks.append(task)

    def touch_twilio_event(self) -> None:
        self.last_twilio_event_at = time.monotonic()

    def touch_media(self) -> None:
        self.last_media_at = time.monotonic()

    def handle_twilio_start(self, *, stream_sid: str, media_format: dict) -> None:
        self.twilio_stream_sid = stream_sid
        self.media_format = media_format
        self.transition_to(MediaSessionStatus.STREAMING)
        log_event("media_stream_started", call_session_id=self.call_session_id, stream_sid=stream_sid, **media_format)

    # --- inbound audio -----------------------------------------------------

    def enqueue_inbound_audio(self, frame: AudioFrame) -> bool:
        """Never blocks the caller (the WebSocket receive loop must never
        stall — spec §16) — a full queue means downstream processing has
        fallen behind, and the correct response is a controlled, counted
        drop (spec §19), not backpressure that freezes media reception
        entirely (which would also break stop-event handling)."""
        self.touch_media()
        try:
            self.inbound_audio_queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.metrics.dropped_inbound_frames += 1
            global_metrics.record_dropped_inbound_frame()
            log_event(
                "inbound_media_backpressure", call_session_id=self.call_session_id,
                queue_depth=self.inbound_audio_queue.qsize(), dropped_total=self.metrics.dropped_inbound_frames,
            )
            return False
        self.metrics.inbound_frames += 1
        self.metrics.inbound_bytes += len(frame.data)
        global_metrics.record_inbound_frame(len(frame.data))
        return True

    async def dequeue_inbound_audio(self) -> AudioFrame:
        return await self.inbound_audio_queue.get()

    # --- outbound audio -----------------------------------------------------

    async def enqueue_outbound_audio(self, chunk: OutboundAudioChunk) -> None:
        """Blocking put is deliberate here (unlike inbound): the producer
        is our own TTS/transitional-bridge code, not an external network
        receive loop, so backpressure against it is safe and desired — it
        naturally slows generation to match what the send loop can
        actually push to Twilio, rather than needing a separate drop policy."""
        await self.outbound_queue.put(chunk)

    async def dequeue_outbound_audio(self) -> OutboundAudioChunk:
        return await self.outbound_queue.get()

    def purge_outbound_for_response(self, response_id: str) -> int:
        """P9 §85-89 — proactively drains stale items for one response out
        of outbound_queue at invalidation time, rather than only relying on
        the output gate to drop them lazily as each is eventually dequeued
        (spec §85: "reduces memory/backlog"). Matches on
        `response_sequence_id`, present on every chunk regardless of
        whether it also carries a full P9 `identity` (works for both the
        streaming and legacy/batch paths) — never touches items belonging
        to any OTHER response (spec §86). Synchronous and non-blocking:
        `get_nowait()`/`put_nowait()` over whatever is currently buffered,
        no await, safe to call from the coordinator's own synchronous
        bookkeeping. Returns the count purged, for the
        `queue_stale_items_purged_total` metric."""
        kept: list[OutboundAudioChunk] = []
        purged = 0
        while True:
            try:
                chunk = self.outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if chunk.response_sequence_id == response_id:
                purged += 1
            else:
                kept.append(chunk)
        for chunk in kept:
            self.outbound_queue.put_nowait(chunk)
        return purged

    def start_new_response_sequence(self) -> str:
        """Foundation for P9's full replay protection — every logical agent
        response gets its own id, chunk_index resets to 0. Not yet enforced
        against stale/duplicate playback here (that's P9's job); just
        established so nothing downstream needs retrofitting."""
        self.current_response_sequence_id = f"resp_{uuid.uuid4().hex[:12]}"
        self.current_response_chunk_index = 0
        return self.current_response_sequence_id

    def next_chunk_index(self) -> int:
        index = self.current_response_chunk_index
        self.current_response_chunk_index += 1
        return index

    # --- marks / playback -----------------------------------------------------

    def next_mark_name(self) -> str:
        self._mark_counter += 1
        return f"jkr-mark-{self._mark_counter}"

    def record_mark_sent(self, name: str) -> None:
        self.metrics.marks_sent.append(name)
        self.playback_state = PlaybackState.PLAYING
        log_event("media_mark_sent", call_session_id=self.call_session_id, mark_name=name)

    def record_mark_acknowledged(self, name: str) -> None:
        self.metrics.marks_acknowledged.append(name)
        if self.playback_state == PlaybackState.PLAYING:
            self.playback_state = PlaybackState.IDLE
        waiter = self._mark_wait_events.get(name)
        if waiter is not None:
            waiter.set()
        log_event("media_mark_received", call_session_id=self.call_session_id, mark_name=name)
        if self.on_mark_acknowledged is not None:
            self.on_mark_acknowledged(name)

    async def wait_for_mark_ack(self, mark_name: str, *, timeout_seconds: float) -> bool:
        """P6 — the real fix for "closing grace started before playback
        actually finished" (spec §59-61): a caller enqueues a chunk with a
        known mark_name, then awaits this instead of starting a fixed grace
        timer immediately. Returns True if the mark was (or already had
        been, by the time this was called) acknowledged; False on timeout —
        the caller decides the safe fallback then (closing.py's callers
        treat a timeout as "assume playback finished," never as "wait
        forever," since a lost mark message must not hang a call shut)."""
        if mark_name in self.metrics.marks_acknowledged:
            return True
        event = self._mark_wait_events.setdefault(mark_name, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False
        finally:
            self._mark_wait_events.pop(mark_name, None)

    def request_clear_playback(self) -> None:
        self.playback_state = PlaybackState.CLEARING
        log_event("media_playback_clear", call_session_id=self.call_session_id)
        if self.on_playback_clear is not None:
            self.on_playback_clear()

    # --- watchdog -----------------------------------------------------

    def seconds_since_last_media(self) -> float | None:
        if self.last_media_at is None:
            return None
        return time.monotonic() - self.last_media_at

    def is_media_idle(self, *, timeout_seconds: float = DEFAULT_MEDIA_IDLE_TIMEOUT_SECONDS) -> bool:
        elapsed = self.seconds_since_last_media()
        return elapsed is not None and elapsed > timeout_seconds

    # --- cleanup -----------------------------------------------------

    def close(self, *, failed: bool = False) -> bool:
        """Idempotent — safe to call from the `stop` event handler, an
        unexpected disconnect handler, the watchdog, and an explicit
        end-of-call path, in any order or combination (spec §34/§35/§37).
        Returns False (a no-op) if already closed, so a caller can tell
        whether IT was the one that actually finalized the session.

        Walks the state machine one valid hop at a time rather than
        jumping straight to the target — STREAMING/CONNECTED can't go
        directly to STOPPED (only via CLOSING first), so a normal close()
        from STREAMING (the common case: the `stop` event arrives
        mid-conversation) does STREAMING -> CLOSING -> STOPPED as two
        transitions in this one call. FAILED is reachable in a single hop
        from every non-terminal status, so close(failed=True) always
        succeeds directly. A close() before the session ever reached
        CONNECTED (no path to a graceful STOPPED exists) ends in FAILED
        instead — more honest than silently staying non-terminal."""
        if self._closed:
            return False
        self._closed = True
        for task in self._tasks:
            if not task.done():
                task.cancel()

        target = MediaSessionStatus.FAILED if failed else MediaSessionStatus.STOPPED
        if target == MediaSessionStatus.STOPPED and self.status != MediaSessionStatus.CLOSING:
            if MediaSessionStatus.CLOSING in VALID_STATUS_TRANSITIONS.get(self.status, frozenset()):
                self.transition_to(MediaSessionStatus.CLOSING)
            else:
                target = MediaSessionStatus.FAILED

        if target in VALID_STATUS_TRANSITIONS.get(self.status, frozenset()):
            self.transition_to(target)
        # else: already terminal — the _closed guard above should make this
        # unreachable in practice, but close() must never raise regardless.

        failed_outcome = target == MediaSessionStatus.FAILED
        global_metrics.record_disconnect(failed=failed_outcome)
        log_event(
            "media_stream_failed" if failed_outcome else "media_stream_stopped",
            call_session_id=self.call_session_id, inbound_frames=self.metrics.inbound_frames,
            outbound_frames=self.metrics.outbound_frames, dropped_inbound_frames=self.metrics.dropped_inbound_frames,
        )
        return True

    @property
    def is_closed(self) -> bool:
        return self._closed

    def to_debug_dict(self) -> dict:
        """spec §43 — enough to answer §75's observability questions for
        one call without building a full dashboard in this pass."""
        return {
            "call_session_id": str(self.call_session_id),
            "twilio_call_sid": self.twilio_call_sid,
            "twilio_stream_sid": self.twilio_stream_sid,
            "status": self.status.value,
            "playback_state": self.playback_state.value,
            "media_format": self.media_format,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "seconds_since_last_media": self.seconds_since_last_media(),
            "inbound_frames": self.metrics.inbound_frames,
            "outbound_frames": self.metrics.outbound_frames,
            "inbound_bytes": self.metrics.inbound_bytes,
            "outbound_bytes": self.metrics.outbound_bytes,
            "dropped_inbound_frames": self.metrics.dropped_inbound_frames,
            "inbound_queue_depth": self.inbound_audio_queue.qsize(),
            "outbound_queue_depth": self.outbound_queue.qsize(),
            "marks_sent": len(self.metrics.marks_sent),
            "marks_acknowledged": len(self.metrics.marks_acknowledged),
            "is_closed": self._closed,
        }


class MediaSessionRegistry:
    """Encapsulated in-memory session table — no module exposes a raw
    global dict for other code to mutate directly (spec §69)."""

    def __init__(self) -> None:
        self._sessions: dict[str, RealtimeMediaSession] = {}
        self._lock = asyncio.Lock()

    async def add(self, session: RealtimeMediaSession) -> None:
        async with self._lock:
            self._sessions[str(session.call_session_id)] = session
        global_metrics.record_connect()

    async def get(self, call_session_id: uuid.UUID | str) -> RealtimeMediaSession | None:
        async with self._lock:
            return self._sessions.get(str(call_session_id))

    async def remove(self, call_session_id: uuid.UUID | str) -> RealtimeMediaSession | None:
        async with self._lock:
            return self._sessions.pop(str(call_session_id), None)

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._sessions)

    async def all_sessions(self) -> list[RealtimeMediaSession]:
        async with self._lock:
            return list(self._sessions.values())


# One process-wide registry, mirroring services/voice-worker/app/session_registry.py's
# existing module-level-singleton pattern for exactly this kind of
# in-memory, per-process call state.
registry = MediaSessionRegistry()
