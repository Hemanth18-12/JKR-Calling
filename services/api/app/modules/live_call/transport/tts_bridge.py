"""P6 — streaming TTS bridge. Owns ONE persistent StreamingTTSProvider
connection for a call's lifetime (spec §14/§48), an ordered text-send
worker (spec §22-23: strict ordering, by construction — one FIFO queue,
one consumer), and an audio-consumer that turns provider audio events into
OutboundAudioChunks on the RealtimeMediaSession's existing outbound queue
(spec §38 — never bypasses the P2 sender architecture).

Two ways text reaches this bridge, both ending up in the same ordered
queue:
1. `TTSResponseHandle.send_chunk()` called from an `on_speakable_chunk`
   callback DURING `process_turn(response_mode="streaming")` — the real
   LLM/TTS overlap this phase exists for.
2. `chunk_text_for_tts()` + `send_chunk()` called AFTER `process_turn()`
   returns, for any reply that was never LLM-streamed (canned, fast-path,
   COMPLETE_OBJECTIVE, or LLM_RESPONSE_MODE=complete) — these still get
   the "audio starts before the whole utterance is synthesized" benefit
   (spec §62-64), just without the LLM-generation overlap (there's nothing
   to overlap with — the text was already fully known).

Deliberately NOT wired: the acknowledgement prefix / max_response_sentences
truncation SpokenResponseFormatter.format() applies. Those need whole-
response context available only AFTER generate() returns — by which point,
for an LLM-streamed reply, audio may already be playing (spec §70: once
SpeakableChunk 0 has reached TTS it's effectively committed). Canned/
fast-path/complete-mode replies are unaffected: they always chunk the
ALREADY-FORMATTED result.reply_text, so they keep today's formatting
behavior exactly. See docs/STREAMING_TTS_ARCHITECTURE.md.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from jkr_conversation.speakable_chunker import SpeakableChunker

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    StreamingTTSProvider,
    TTSAudioChunk,
    TTSCallContext,
    TTSFirstAudio,
    TTSGenerationCompleted,
    TTSStreamCancelled,
    TTSStreamFailed,
)
from app.modules.live_call.transport.audio_codec import audio_duration_ms
from app.modules.live_call.transport.base import OutboundAudioChunk
from app.modules.live_call.transport.events import log_event
from app.modules.live_call.transport.identity import (
    ChunkCheckResult,
    ResponseIdentity,
    check_chunk_index,
)
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession

TEXT_QUEUE_MAXSIZE = 64  # bounded — spec §21/§53: a stalled TTS connection must slow the feeder, never grow unbounded
RESPONSE_COMPLETION_TIMEOUT_SECONDS = 30.0  # generous upper bound — real measured Sarvam throughput is faster than real-time (see contract doc)
MAX_TTS_RECONNECT_ATTEMPTS = 2  # spec §141 — bounded, not an indefinite retry loop, PER reconnect cycle
TTS_RECONNECT_BACKOFF_SECONDS = (0.5, 1.5)
# A cap on how many times _run_consumer_with_reconnect will start a whole
# NEW reconnect cycle over this session's lifetime — MAX_TTS_RECONNECT_ATTEMPTS
# alone only bounds attempts WITHIN one cycle; without this, a connection
# that succeeds its handshake but then immediately drops (e.g. a
# misconfigured provider that accepts auth and closes) would trigger an
# unbounded sequence of successful-reconnect-then-immediate-failure cycles.
MAX_TTS_RECONNECT_CYCLES = 3


@dataclass(frozen=True)
class SentAudioChunkInfo:
    """P7 — one record per audio chunk actually enqueued to Twilio, enough
    for RealtimePipelineCoordinator to build a PlaybackUnit per chunk
    without tts_bridge.py needing to know PlaybackUnit exists. Built once,
    in _run_consumer, where mark_name/bytes/duration are already being
    computed anyway — not a second pass over anything."""

    mark_name: str
    audio_chunk_index: int
    bytes_sent: int
    duration_ms: int
    sent_at: float


@dataclass(frozen=True)
class TTSTurnOutcome:
    response_id: str
    failed: bool
    failure_message: str | None
    chunks_sent: int
    bytes_sent: int
    final_mark_name: str | None
    first_audio_ms: int | None
    chunks: tuple[SentAudioChunkInfo, ...] = ()


@dataclass
class _PendingResponse:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    failed: bool = False
    failure_message: str | None = None
    chunks_sent: int = 0
    bytes_sent: int = 0
    first_audio_at: float | None = None
    started_at: float = field(default_factory=time.monotonic)
    sent_chunks: list[SentAudioChunkInfo] = field(default_factory=list)
    # P9 — the coordinator-minted identity for this response, attached at
    # begin_response() time and stamped onto every OutboundAudioChunk this
    # response produces (see docs/RESPONSE_IDENTITY_MODEL.md). None when no
    # coordinator is attached (TTS_MODE=streaming with no coordinator is not
    # a real configuration in this codebase, but tests construct
    # TTSStreamingSession directly without one) — the legacy-path exception,
    # not a bypass (see base.py's OutboundAudioChunk docstring).
    identity: ResponseIdentity | None = None
    playback_epoch: int = 0
    # P9 — duplicate/conflict/gap detection for TTSAudioChunk.audio_chunk_index
    # (see identity.check_chunk_index()) — independent of, and upstream from,
    # the SEPARATE duplicate check the coordinator's output gate performs on
    # the same numeric value once it reaches OutboundAudioChunk.chunk_index
    # (defense in depth at two distinct boundaries, spec §27-28 vs §36-37).
    next_expected_audio_chunk_index: int = 0
    audio_chunk_fingerprint_by_index: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _TextQueueItem:
    kind: str  # "text" | "flush"
    response_id: str
    chunk_index: int = 0
    text: str = ""


class TTSResponseHandle:
    """One per logical agent response — returned by
    TTSStreamingSession.begin_response(), never constructed directly."""

    def __init__(self, session: TTSStreamingSession, *, response_id: str) -> None:
        self._session = session
        self.response_id = response_id
        self._chunk_index = 0

    async def send_chunk(self, text: str) -> None:
        if not text.strip():
            return
        await self._session._enqueue_text(response_id=self.response_id, chunk_index=self._chunk_index, text=text)
        self._chunk_index += 1

    async def finish(self) -> TTSTurnOutcome:
        return await self._session._finish_response(self.response_id)


class TTSStreamingSession:
    def __init__(
        self, *, provider: StreamingTTSProvider, media_session: RealtimeMediaSession,
        provider_factory: Callable[[], StreamingTTSProvider] | None = None,
    ):
        self._provider = provider
        self._media_session = media_session
        # P7 §82 — only used for the idle-between-responses reconnect
        # (see _run_consumer_with_reconnect); None (the default, and what
        # every P6-era construction still uses) means "reconnect not
        # configured for this session," preserving exact pre-P7 behavior —
        # a dead connection just stops delivering audio, same as before.
        self._provider_factory = provider_factory
        self._config: StreamingTTSConfig | None = None
        self._context: TTSCallContext | None = None
        self._connection_generation = 0
        self._reconnect_cycles = 0
        self.reconnect_attempts = 0
        self.reconnect_successes = 0
        self.reconnect_failures = 0
        self._text_queue: asyncio.Queue[_TextQueueItem] = asyncio.Queue(maxsize=TEXT_QUEUE_MAXSIZE)
        self._pending: dict[str, _PendingResponse] = {}
        self._last_mark_name_by_response: dict[str, str] = {}
        # spec §50-51 — minimal generation ownership: at most one response
        # is "active" at a time; starting a new one before the previous
        # finished supersedes it rather than letting two audio streams
        # mix. NOT full P9 stale-replay protection (spec §78) — just
        # enough to prevent an obvious cross-response mixing bug. In
        # normal P6 operation (no barge-in wired yet — that's P8) this
        # path is never actually exercised: process_known_transcript_turn
        # always awaits one response's finish() before the next customer
        # turn can start a new one.
        self._active_response_id: str | None = None
        self._sender_task: asyncio.Task | None = None
        self._consumer_task: asyncio.Task | None = None
        self._closed = False

    async def start(self, *, config: StreamingTTSConfig, context: TTSCallContext) -> None:
        self._config = config
        self._context = context
        await self._provider.connect(config=config, context=context)
        self._sender_task = asyncio.create_task(self._run_sender())
        self._consumer_task = asyncio.create_task(self._run_consumer_with_reconnect())

    def begin_response(
        self, response_id: str | None = None, *, identity: ResponseIdentity | None = None, playback_epoch: int = 0,
    ) -> TTSResponseHandle:
        response_id = response_id or f"resp_{uuid.uuid4().hex[:12]}"
        previous_id = self._active_response_id
        if previous_id is not None and previous_id != response_id:
            # The local bookkeeping (failed/event.set()) happens
            # SYNCHRONOUSLY here, not inside a background task — this is
            # what makes it safe against a race with that same response's
            # own flush-triggered completion event arriving moments later
            # (see cancel_response()'s docstring for the bug this fixes).
            # Only the actual provider network call is backgrounded.
            if self._mark_pending_cancelled(previous_id, reason="superseded_by_new_response"):
                asyncio.create_task(self._provider.cancel(previous_id))
        self._active_response_id = response_id
        self._pending[response_id] = _PendingResponse(identity=identity, playback_epoch=playback_epoch)
        return TTSResponseHandle(self, response_id=response_id)

    def _mark_pending_cancelled(self, response_id: str, *, reason: str) -> bool:
        """Returns True if this call actually resolved the response (False
        if it was unknown or already resolved by something else — e.g. a
        completion event that raced ahead of an explicit cancel)."""
        pending = self._pending.get(response_id)
        if pending is None or pending.event.is_set():
            return False
        log_event(
            "tts_response_cancelled", call_session_id=self._media_session.call_session_id,
            response_id=response_id, reason=reason,
        )
        pending.failed = True
        pending.failure_message = reason
        pending.event.set()
        if self._active_response_id == response_id:
            self._active_response_id = None
        purged = self._purge_text_queue_for_response(response_id)
        if purged:
            replay_metrics.queue_stale_items_purged_total += purged
            log_event(
                "stale_tts_text_purged", call_session_id=self._media_session.call_session_id,
                response_id=response_id, count=purged,
            )
        return True

    def _purge_text_queue_for_response(self, response_id: str) -> int:
        """P9 §87/§89 — proactively drains queued-but-not-yet-sent text for
        one response out of _text_queue at cancellation time (same
        reasoning as RealtimeMediaSession.purge_outbound_for_response()) —
        synchronous, non-blocking, never touches another response's items."""
        kept: list[_TextQueueItem] = []
        purged = 0
        while True:
            try:
                item = self._text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item.response_id == response_id:
                purged += 1
            else:
                kept.append(item)
        for item in kept:
            self._text_queue.put_nowait(item)
        return purged

    async def cancel_response(self, response_id: str, *, reason: str = "cancelled") -> None:
        """P7 — the awaited counterpart to begin_response()'s own inline
        supersede: RealtimePipelineCoordinator calls this directly (rather
        than reaching into self._provider) so both layers' bookkeeping
        always agrees about whether a response is still live. Marks the
        response cancelled SYNCHRONOUSLY (via _mark_pending_cancelled)
        before awaiting the provider call — awaiting the provider call
        first would let a same-response completion/failure event delivered
        by _run_consumer in the meantime race ahead and resolve the
        response on its own, silently swallowing the cancellation."""
        if self._mark_pending_cancelled(response_id, reason=reason):
            await self._provider.cancel(response_id)

    async def _enqueue_text(self, *, response_id: str, chunk_index: int, text: str) -> None:
        await self._text_queue.put(_TextQueueItem(kind="text", response_id=response_id, chunk_index=chunk_index, text=text))

    async def _finish_response(self, response_id: str) -> TTSTurnOutcome:
        await self._text_queue.put(_TextQueueItem(kind="flush", response_id=response_id))
        pending = self._pending.get(response_id)
        if pending is None:
            return TTSTurnOutcome(
                response_id=response_id, failed=True, failure_message="unknown_response",
                chunks_sent=0, bytes_sent=0, final_mark_name=None, first_audio_ms=None,
            )
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=RESPONSE_COMPLETION_TIMEOUT_SECONDS)
        except TimeoutError:
            # The connection died (or the provider silently stopped sending
            # events) without ever producing a completion/failure event of
            # its own — _run_consumer's `async for event in provider.
            # events()` would otherwise leave this coroutine waiting
            # forever. Treated exactly like a provider-reported failure so
            # the same chunks_sent==0-vs->0 fallback policy applies; never
            # a silent hang (spec §72's "do not leave the caller in
            # silence indefinitely" principle, applied to this failure mode).
            if not pending.event.is_set():
                pending.failed = True
                pending.failure_message = "timeout_waiting_for_completion"
                pending.event.set()
        first_audio_ms = int((pending.first_audio_at - pending.started_at) * 1000) if pending.first_audio_at else None
        return TTSTurnOutcome(
            response_id=response_id, failed=pending.failed, failure_message=pending.failure_message,
            chunks_sent=pending.chunks_sent, bytes_sent=pending.bytes_sent,
            final_mark_name=self._last_mark_name_by_response.get(response_id), first_audio_ms=first_audio_ms,
            chunks=tuple(pending.sent_chunks),
        )

    async def _run_sender(self) -> None:
        """The one and only writer to the provider connection — ordering
        guarantee by construction (spec §22-23): a single FIFO queue with a
        single consumer can never reorder what enters it, regardless of how
        out-of-order the producers (an LLM callback vs. a locally-chunked
        canned reply) happened to call send_chunk().

        P9 §23-24 — a text item is validated again HERE, at dequeue, not
        just at enqueue: a response cancelled/superseded/interrupted after
        its text was already queued (but before this loop reached it) must
        never have that text reach the provider. This is a real gap P9's
        own audit found — _run_sender previously sent whatever it dequeued
        unconditionally."""
        while True:
            item = await self._text_queue.get()
            pending = self._pending.get(item.response_id)
            if pending is None or pending.event.is_set():
                replay_metrics.record_blocked("stale_tts_text_dropped_total")
                log_event(
                    "stale_tts_text_dropped", call_session_id=self._media_session.call_session_id,
                    response_id=item.response_id, reason="response_resolved_before_dequeue",
                )
                continue
            try:
                if item.kind == "text":
                    await self._provider.send_text(text=item.text, response_id=item.response_id, chunk_index=item.chunk_index)
                else:
                    await self._provider.flush(response_id=item.response_id)
            except Exception as exc:  # noqa: BLE001 — a provider send failure surfaces via the pending response, never crashes this task
                if not pending.event.is_set():
                    pending.failed = True
                    pending.failure_message = str(exc)
                    pending.event.set()

    async def _run_consumer(self) -> None:
        async for event in self._provider.events():
            if isinstance(event, TTSFirstAudio):
                pending = self._pending.get(event.response_id)
                if pending is not None and pending.first_audio_at is None:
                    pending.first_audio_at = time.monotonic()
            elif isinstance(event, TTSAudioChunk):
                pending = self._pending.get(event.response_id)
                if pending is None or pending.event.is_set():
                    replay_metrics.record_blocked("stale_tts_audio_dropped_total")
                    log_event(
                        "stale_tts_audio_dropped", call_session_id=self._media_session.call_session_id,
                        response_id=event.response_id, audio_chunk_index=event.audio_chunk_index,
                    )
                    continue  # stale/superseded/already-finished response — drop, never forward (spec §77/§102/§103)

                # P9 §27-30 — duplicate/conflict/gap detection, before this
                # chunk is allowed to become an OutboundAudioChunk at all.
                # Non-cryptographic content fingerprint (spec §29 explicitly
                # warns against cryptographic hashing on this hot path).
                fingerprint = hash((len(event.data), event.data[:32], event.data[-32:])) if event.data else 0
                check = check_chunk_index(
                    index=event.audio_chunk_index, fingerprint=fingerprint,
                    next_expected=pending.next_expected_audio_chunk_index,
                    fingerprints_by_index=pending.audio_chunk_fingerprint_by_index,
                )
                if check is ChunkCheckResult.DUPLICATE:
                    replay_metrics.record_blocked("duplicate_tts_audio_dropped_total")
                    log_event(
                        "duplicate_tts_audio_dropped", call_session_id=self._media_session.call_session_id,
                        response_id=event.response_id, audio_chunk_index=event.audio_chunk_index,
                    )
                    continue
                if check in (ChunkCheckResult.CONFLICT, ChunkCheckResult.GAP):
                    replay_metrics.record_blocked("audio_identity_conflict_total")
                    log_event(
                        "audio_identity_conflict", call_session_id=self._media_session.call_session_id,
                        response_id=event.response_id, audio_chunk_index=event.audio_chunk_index, check=check.value, severity="high",
                    )
                    # Upstream corruption (spec §20/§30) — fail this response
                    # rather than risk forwarding audio in the wrong order or
                    # silently accepting conflicting bytes for the same index.
                    if not pending.event.is_set():
                        pending.failed = True
                        pending.failure_message = f"audio_identity_{check.value}"
                        pending.event.set()
                    continue
                pending.audio_chunk_fingerprint_by_index[event.audio_chunk_index] = fingerprint
                pending.next_expected_audio_chunk_index = max(pending.next_expected_audio_chunk_index, event.audio_chunk_index + 1)

                mark_name = self._media_session.next_mark_name()
                self._last_mark_name_by_response[event.response_id] = mark_name
                pending.chunks_sent += 1
                pending.bytes_sent += len(event.data)
                duration_ms = audio_duration_ms(byte_length=len(event.data), codec=event.codec or "mulaw", sample_rate=event.sample_rate or 8000)
                pending.sent_chunks.append(
                    SentAudioChunkInfo(
                        mark_name=mark_name, audio_chunk_index=event.audio_chunk_index,
                        bytes_sent=len(event.data), duration_ms=duration_ms, sent_at=time.monotonic(),
                    )
                )
                chunk = OutboundAudioChunk(
                    response_sequence_id=event.response_id, chunk_index=event.audio_chunk_index,
                    data=event.data, sample_rate=event.sample_rate or 8000, mark_name=mark_name, audio_is_mulaw_8k=True,
                    identity=pending.identity, playback_epoch=pending.playback_epoch,
                )
                await self._media_session.enqueue_outbound_audio(chunk)
            elif isinstance(event, TTSGenerationCompleted):
                self._resolve(event.response_id, failed=False)
            elif isinstance(event, TTSStreamFailed):
                if event.response_id is not None:
                    self._resolve(event.response_id, failed=True, message=f"{event.failure_class.value}: {event.message}")
            elif isinstance(event, TTSStreamCancelled):
                self._resolve(event.response_id, failed=False)

    def _resolve(self, response_id: str, *, failed: bool, message: str | None = None) -> None:
        pending = self._pending.get(response_id)
        if pending is not None and not pending.event.is_set():
            pending.failed = failed
            pending.failure_message = message
            pending.event.set()
        if self._active_response_id == response_id:
            self._active_response_id = None

    async def _run_consumer_with_reconnect(self) -> None:
        """P7 §82-83 — _run_consumer() returns when self._provider.events()
        ends (the connection closed, cleanly or not). If that happens while
        no response is active, attempt a bounded reconnect and resume
        consuming from the NEW provider instance; if it happens mid-
        response, do NOT reconnect here — spec §144's "no mid-response
        blind replay" — the already-in-flight _finish_response() call's own
        RESPONSE_COMPLETION_TIMEOUT_SECONDS handles that case by resolving
        the response as failed, which then follows the ordinary chunks-
        sent-zero-vs-nonzero fallback policy."""
        while True:
            await self._run_consumer()
            if self._closed:
                return
            if self._active_response_id is not None:
                log_event(
                    "tts_connection_lost_mid_response", call_session_id=self._media_session.call_session_id,
                    response_id=self._active_response_id,
                )
                return
            if self._provider_factory is None:
                return  # reconnect not configured for this session — pre-P7 behavior
            self._reconnect_cycles += 1
            if self._reconnect_cycles > MAX_TTS_RECONNECT_CYCLES:
                log_event(
                    "tts_reconnect_cycles_exhausted", call_session_id=self._media_session.call_session_id,
                    cycles=self._reconnect_cycles,
                )
                return
            if not await self._attempt_reconnect():
                return

    async def _attempt_reconnect(self) -> bool:
        assert self._provider_factory is not None  # only called when set — see _run_consumer_with_reconnect
        assert self._config is not None and self._context is not None  # only reachable after start()
        for attempt, backoff in enumerate(TTS_RECONNECT_BACKOFF_SECONDS[:MAX_TTS_RECONNECT_ATTEMPTS], start=1):
            self.reconnect_attempts += 1
            try:
                new_provider = self._provider_factory()
                await new_provider.connect(config=self._config, context=self._context)
            except Exception as exc:  # noqa: BLE001 — a failed reconnect attempt is retried/logged, never raised into the consumer task
                self.reconnect_failures += 1
                log_event(
                    "tts_reconnect_attempt_failed", call_session_id=self._media_session.call_session_id,
                    attempt=attempt, error=str(exc),
                )
                await asyncio.sleep(backoff)
                continue
            self._provider = new_provider
            self._connection_generation += 1
            self.reconnect_successes += 1
            log_event(
                "tts_reconnect_succeeded", call_session_id=self._media_session.call_session_id,
                attempt=attempt, connection_generation=self._connection_generation,
            )
            return True
        log_event(
            "tts_reconnect_exhausted", call_session_id=self._media_session.call_session_id,
            attempts=self.reconnect_attempts,
        )
        return False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._sender_task is not None:
            self._sender_task.cancel()
        if self._consumer_task is not None:
            self._consumer_task.cancel()
        await self._provider.close()


def chunk_text_for_tts(text: str) -> list[str]:
    """For any reply that was never LLM-streamed — see module docstring
    point 2. Reuses P5's own SpeakableChunker rather than a second
    chunking implementation; a fresh instance per call since this is
    always the entire already-known text in one shot, never fed
    incrementally."""
    chunker = SpeakableChunker()
    chunks = chunker.feed(text)
    leftover = chunker.flush()
    if leftover:
        chunks.append(leftover)
    return chunks
