"""P7 — RealtimePipelineCoordinator: the single authority for "which
response owns this call's audio right now," replacing several
independently-correct-but-uncoordinated pieces of state
(RealtimeMediaSession's own response-sequence counter used only by the
batch path, TTSStreamingSession's response_id tracking used only by the
streaming path, no LLM-generation-level ownership check at all) with one
call-scoped object every streaming response goes through.

Deliberately NOT a rewrite of P6: TTSStreamingSession still owns the
provider connection, the ordered text queue, and the audio-consumer loop
— this module orchestrates it, observes it (via TTSTurnOutcome.chunks and
the RealtimeMediaSession.on_mark_acknowledged/on_playback_clear hooks),
and adds the response-lifecycle/ownership/playback-accounting layer on
top. See docs/REALTIME_PIPELINE_COORDINATOR.md.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from jkr_conversation.streaming_response import CancellationToken, SpeakableChunk

from app.modules.live_call.transport.base import OutboundAudioChunk
from app.modules.live_call.transport.events import (
    BARGE_IN_CLEAR_SENT,
    BARGE_IN_RESPONSE_CANCELLED,
    log_event,
)
from app.modules.live_call.transport.identity import (
    ChunkCheckResult,
    OutputGateDecision,
    ResponseIdentity,
    check_chunk_index,
)
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import (
    TTSResponseHandle,
    TTSStreamingSession,
    TTSTurnOutcome,
)
from app.modules.live_call.turns.barge_in_metrics import metrics as barge_in_metrics

# Spec — provider cancellation must never hang the interruption flow.
# Conservative starting point (see docs/BARGE_IN_ARCHITECTURE.md); real-call
# tuning is still outstanding, same honest framing every other timing
# constant in this module already carries.
INTERRUPTION_CANCEL_TIMEOUT_SECONDS = 2.0


class DeadAirLevel(StrEnum):
    OK = "ok"
    WARNING = "warning"
    FATAL = "fatal"


# Spec §52/§109 — configurable, not one generic timeout reused everywhere
# (spec §109 explicitly warns against that). These are conservative
# starting points, not measured-optimal values — real-call tuning is
# still pending (see docs/P7_REALTIME_PIPELINE_RESULTS.md).
DEAD_AIR_WARNING_MS = 1500
DEAD_AIR_FATAL_MS = 4000


def classify_dead_air(elapsed_ms: float, *, warning_ms: int = DEAD_AIR_WARNING_MS, fatal_ms: int = DEAD_AIR_FATAL_MS) -> DeadAirLevel:
    if elapsed_ms >= fatal_ms:
        return DeadAirLevel.FATAL
    if elapsed_ms >= warning_ms:
        return DeadAirLevel.WARNING
    return DeadAirLevel.OK


@dataclass(frozen=True)
class DeadAirStatus:
    level: DeadAirLevel
    elapsed_ms: int
    stage: str | None


class ResponseState(StrEnum):
    CREATED = "created"
    GENERATING_TEXT = "generating_text"
    TEXT_STREAMING = "text_streaming"
    TTS_STREAMING = "tts_streaming"
    GENERATION_COMPLETE = "generation_complete"
    PLAYBACK_PENDING = "playback_pending"
    PLAYBACK_COMPLETE = "playback_complete"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    # P8 — distinct from CANCELLED: customer speech caused this response to
    # stop, not a system decision (a new response replacing an unfinished
    # one is SUPERSEDED; an internal failure is FAILED/CANCELLED). Kept
    # separate specifically so downstream consumers (conversation-history
    # repair, metrics, the debug trace) can tell "the customer interrupted
    # me" apart from "I cancelled myself" without re-deriving it from reason
    # strings.
    INTERRUPTED = "interrupted"


# Spec §6/§86 — only these release call-level ownership. Everything else is
# still "in flight" and continues to own the call's audio.
TERMINAL_RESPONSE_STATES = frozenset({
    ResponseState.PLAYBACK_COMPLETE, ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED,
    ResponseState.INTERRUPTED,
})

# P9 — spec §56-58: response state transitions must be monotonic and
# centrally validated, not just "correct because every call site happens to
# set the right value today." Every `ctx.state = X` assignment in this file
# goes through _transition() below, which checks this table. A terminal
# state transitioning to ITSELF is always allowed (idempotent no-op, spec
# §58 — a repeated INTERRUPTED->INTERRUPTED must not error); a terminal
# state transitioning to anything else is always rejected (spec §55: "no
# stale task revival" — a late callback can never move a response backward
# out of a terminal state).
VALID_RESPONSE_STATE_TRANSITIONS: dict[ResponseState, frozenset[ResponseState]] = {
    ResponseState.CREATED: frozenset({
        ResponseState.GENERATING_TEXT, ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.GENERATING_TEXT: frozenset({
        ResponseState.TEXT_STREAMING, ResponseState.GENERATION_COMPLETE, ResponseState.CANCEL_PENDING,
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.TEXT_STREAMING: frozenset({
        ResponseState.TTS_STREAMING, ResponseState.GENERATION_COMPLETE, ResponseState.CANCEL_PENDING,
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.TTS_STREAMING: frozenset({
        ResponseState.TEXT_STREAMING, ResponseState.GENERATION_COMPLETE, ResponseState.PLAYBACK_PENDING, ResponseState.CANCEL_PENDING,
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.GENERATION_COMPLETE: frozenset({
        ResponseState.PLAYBACK_PENDING, ResponseState.PLAYBACK_COMPLETE, ResponseState.CANCEL_PENDING,
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.PLAYBACK_PENDING: frozenset({
        ResponseState.PLAYBACK_COMPLETE, ResponseState.CANCEL_PENDING,
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.CANCEL_PENDING: frozenset({
        ResponseState.CANCELLED, ResponseState.SUPERSEDED, ResponseState.FAILED, ResponseState.INTERRUPTED,
    }),
    ResponseState.PLAYBACK_COMPLETE: frozenset({ResponseState.PLAYBACK_COMPLETE}),
    ResponseState.CANCELLED: frozenset({ResponseState.CANCELLED}),
    ResponseState.SUPERSEDED: frozenset({ResponseState.SUPERSEDED}),
    ResponseState.FAILED: frozenset({ResponseState.FAILED}),
    ResponseState.INTERRUPTED: frozenset({ResponseState.INTERRUPTED}),
}


class PlaybackUnitState(StrEnum):
    CREATED = "created"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"
    CANCELLED = "cancelled"


# P9 — spec §57/§132-134: CLEARED can never later become ACKNOWLEDGED (a
# cleared unit is never retroactively "heard" — already enforced by
# _on_mark_acknowledged's own guard, P7); ACKNOWLEDGED can never later
# become CLEARED (if it was already played, a later clear cannot retroactively
# un-play it — already true because _on_playback_clear only touches SENT
# units). This table formalizes both as an explicit, centrally-checked
# invariant rather than leaving it implicit in two separate methods' own
# guards.
VALID_PLAYBACK_UNIT_TRANSITIONS: dict[PlaybackUnitState, frozenset[PlaybackUnitState]] = {
    PlaybackUnitState.CREATED: frozenset({PlaybackUnitState.SENT, PlaybackUnitState.CANCELLED}),
    PlaybackUnitState.SENT: frozenset({PlaybackUnitState.ACKNOWLEDGED, PlaybackUnitState.CLEARED, PlaybackUnitState.CANCELLED}),
    PlaybackUnitState.ACKNOWLEDGED: frozenset({PlaybackUnitState.ACKNOWLEDGED}),
    PlaybackUnitState.CLEARED: frozenset({PlaybackUnitState.CLEARED}),
    PlaybackUnitState.CANCELLED: frozenset({PlaybackUnitState.CANCELLED}),
}


@dataclass
class PlaybackUnit:
    """One per audio chunk actually enqueued to Twilio — the finest
    granularity this pipeline has PRECISE (not approximate) tracking for:
    we assign the mark, we know exactly when it's sent, and Twilio's own
    mark event tells us exactly when it's acknowledged. Spec §24 describes
    a playback unit as "one SpeakableChunk -> TTS -> audio" — that mapping
    is only approximate in practice (Sarvam's own internal buffering does
    not preserve a 1:1 text-chunk-to-audio-chunk boundary; see
    docs/SARVAM_STREAMING_TTS_CONTRACT.md), so `text` here is left
    unset rather than asserting a precision this pipeline doesn't have
    (spec §158's own caution against false precision)."""

    response_id: str
    sequence_id: str
    unit_index: int
    mark_name: str
    audio_duration_ms: int
    bytes_sent: int
    created_at: float
    sent_at: float | None = None
    mark_acknowledged_at: float | None = None
    state: PlaybackUnitState = PlaybackUnitState.CREATED
    clear_epoch_at_creation: int = 0


@dataclass
class ActiveResponseContext:
    call_id: uuid.UUID
    turn_id: str
    response_id: str
    generation_id: str
    sequence_id: str
    state: ResponseState = ResponseState.CREATED
    created_at: float = field(default_factory=time.monotonic)

    # spec §17-23 — deliberately distinct, never collapsed into one
    # ambiguous "response_completed" flag.
    text_generated: str = ""
    text_committed_to_tts: str = ""
    text_chunks_created: int = 0
    text_chunks_sent_to_tts: int = 0
    audio_chunks_received: int = 0
    audio_ms_generated: int = 0
    audio_ms_sent: int = 0
    audio_ms_acknowledged: int = 0
    first_audio_ms: int | None = None

    playback_units: list[PlaybackUnit] = field(default_factory=list)

    cancelled: bool = False
    superseded: bool = False
    failed: bool = False
    failure_stage: str | None = None
    failure_message: str | None = None

    # spec §88-90 — barge-in readiness signals, recorded but not acted on.
    customer_spoke_during_generation: bool = False
    customer_spoke_during_playback: bool = False

    # P8 — legally-required compliance notices only (never normal business
    # speech, per spec's own caution); DNC/human-handoff always overrides
    # this at the InterruptionPolicy layer regardless of its value here.
    interruptible: bool = True
    # P8 — (text, submitted_at) per chunk actually forwarded to TTS, in
    # submit_speakable_chunk() order. This is what makes conservative
    # interrupted-response history repair possible without inventing a
    # word-boundary PlaybackUnit.text was deliberately never given (see
    # docs/PLAYBACK_ACCOUNTING.md) — see _conservative_delivered_text().
    chunk_log: list[tuple[str, float]] = field(default_factory=list)

    # P9 — the call-scoped response_epoch captured at mint time (see
    # docs/RESPONSE_IDENTITY_MODEL.md); part of this response's ResponseIdentity.
    response_epoch: int = 0
    # P9 — threaded into process_turn() so a stale generation's own LLM
    # consumption loop stops itself (StreamingResponseAssembler already
    # checks this every iteration, P5) — not just relying on the
    # surrounding asyncio task being cancelled (P8). See
    # docs/REPLAY_PROTECTION_ARCHITECTURE.md.
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    # P9 — duplicate/conflict/gap detection for SpeakableChunk.chunk_index,
    # scoped to this response (see identity.check_chunk_index()).
    next_expected_text_chunk_index: int = 0
    text_chunk_fingerprint_by_index: dict[int, int] = field(default_factory=dict)
    # P9 — SpeakableChunk.generation_id is minted by StreamingResponseAssembler
    # itself (one fresh uuid per assembler.run() call) — a DIFFERENT namespace
    # from this context's own `generation_id` (minted by begin_response());
    # the two were never meant to be equal, comparing them directly would
    # reject every genuine LLM-streamed chunk (a real bug caught by
    # test_p7_pipeline_integration.py failing during this phase's own
    # development — see docs/P9_REPLAY_PROTECTION_RESULTS.md). What's
    # actually worth validating is CONSISTENCY: every chunk accepted for
    # this response must come from the SAME assembler run — recorded on the
    # first accepted chunk, checked against on every subsequent one.
    assembler_generation_id: str | None = None
    # P9 — duplicate-send detection at the FINAL Twilio output-gate boundary
    # (can_send_media()) — independent of, and in addition to, the earlier
    # TTS-audio-received duplicate check in tts_bridge.py (defense in depth
    # at two separate boundaries, spec §27-28 vs §36-37).
    sent_media_chunk_indices: set[int] = field(default_factory=set)

    @property
    def identity(self) -> ResponseIdentity:
        """Constructed on demand from this context's own fields — never
        stored separately, so it can never drift out of sync with the
        context it describes (spec §4-5: one canonical identity, immutable,
        never five loose strings threaded independently)."""
        return ResponseIdentity(
            call_id=self.call_id, turn_id=self.turn_id, response_id=self.response_id,
            generation_id=self.generation_id, sequence_id=self.sequence_id, epoch=self.response_epoch,
        )

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_RESPONSE_STATES

    def is_current_and_active(self) -> bool:
        return not self.is_terminal()


@dataclass(frozen=True)
class InterruptionSnapshot:
    """The payload interrupt_active_response() returns once a barge-in is
    confirmed and acted on. `delivered_text` is deliberately NOT
    `generated_text` or `tts_committed_text` — see
    docs/INTERRUPTED_RESPONSE_HISTORY.md for why those must never be
    treated as "what the customer heard," and _conservative_delivered_text()
    for how this conservative value is actually derived."""

    response_id: str
    generated_text: str
    tts_committed_text: str
    delivered_text: str
    audio_generated_ms: int
    audio_sent_ms: int
    audio_acknowledged_ms: int
    pending_playback_ms: int
    playback_units: tuple[PlaybackUnit, ...]
    interruption_id: str
    reason: str
    had_sent_audio: bool


@dataclass
class _Handles:
    context: ActiveResponseContext
    tts_handle: TTSResponseHandle | None


class RealtimePipelineCoordinator:
    """One instance per call. Constructed alongside RealtimeMediaSession;
    `attach_tts_session()` wires it to the call's TTSStreamingSession once
    that connects (which may be later, or never, under TTS_MODE=batch)."""

    def __init__(
        self, *, call_session_id: uuid.UUID, media_session: RealtimeMediaSession,
        interruption_cancel_timeout_seconds: float = INTERRUPTION_CANCEL_TIMEOUT_SECONDS,
    ):
        self._call_session_id = call_session_id
        self._media_session = media_session
        self._interruption_cancel_timeout_seconds = interruption_cancel_timeout_seconds
        self._tts_session: TTSStreamingSession | None = None
        self._active: ActiveResponseContext | None = None
        self._contexts: dict[str, ActiveResponseContext] = {}
        self._handles: dict[str, _Handles] = {}
        self._units_by_mark: dict[str, PlaybackUnit] = {}
        self._clear_epoch = 0
        self._closed = False
        # P9 — call-scoped, monotonically increasing, incremented once per
        # begin_response() (see docs/RESPONSE_IDENTITY_MODEL.md). A cheap
        # integer fast-check that a given ResponseIdentity really is from
        # the CURRENT response generation, independent of (never a
        # replacement for) the response_id/generation_id/sequence_id string
        # comparisons is_identity_active() also performs.
        self._response_epoch = 0
        # P8 — idempotency guard: set synchronously (no await in between
        # check and set) so two interruption triggers arriving in the same
        # event-loop tick (e.g. local VAD start and a provider SpeechStarted
        # both firing) can only ever run the cancellation sequence once.
        # See interrupt_active_response().
        self._interrupting: set[str] = set()

        media_session.on_mark_acknowledged = self._on_mark_acknowledged
        media_session.on_playback_clear = self._on_playback_clear

    def attach_tts_session(self, tts_session: TTSStreamingSession | None) -> None:
        self._tts_session = tts_session

    @property
    def active_response(self) -> ActiveResponseContext | None:
        return self._active

    def is_current(self, response_id: str) -> bool:
        """Spec §12-16 — the one ownership check every layer (LLM callback,
        SpeakableChunk feed, TTS text send) is expected to perform before
        producing customer-facing output."""
        return self._active is not None and self._active.response_id == response_id and not self._active.is_terminal()

    @property
    def playback_epoch(self) -> int:
        """P9 — the formal name for what P7 already tracked as
        `_clear_epoch`: every Twilio clear increments it (see
        _on_playback_clear()); any audio minted before the current value
        belongs to a stale epoch. Kept as an alias over the existing
        internal field rather than renamed, to avoid touching P7's own
        already-tested `clear_epoch_at_creation` bookkeeping for a purely
        cosmetic rename."""
        return self._clear_epoch

    def is_identity_active(self, identity: ResponseIdentity) -> bool:
        """P9 — the complete ownership check (spec §8): call, response,
        generation, sequence, and epoch must ALL match the currently active
        response, which must itself not be terminal. Strictly stronger than
        is_current() (which only checks response_id) — is_current() is kept
        for the existing call sites that only ever had a bare response_id
        available; new P9 boundaries that have a full ResponseIdentity use
        this instead. Fails closed: any missing/unmatched piece is `False`,
        never a best guess (spec §140-141)."""
        if identity.call_id != self._call_session_id:
            return False
        if self._active is None or self._active.is_terminal():
            return False
        return (
            identity.response_id == self._active.response_id
            and identity.generation_id == self._active.generation_id
            and identity.sequence_id == self._active.sequence_id
            and identity.epoch == self._active.response_epoch
        )

    def _transition(self, ctx: ActiveResponseContext, new_state: ResponseState) -> bool:
        """P9 — the one place ctx.state is ever assigned (spec §56-58).
        Idempotent no-op for a terminal state transitioning to itself;
        rejects (logs + counts, does NOT raise — spec §93: never crash a
        production call over an invariant violation) anything not in
        VALID_RESPONSE_STATE_TRANSITIONS, most importantly any attempt to
        move OUT of a terminal state (spec §55: no stale task revival)."""
        if ctx.state == new_state:
            return True
        allowed = VALID_RESPONSE_STATE_TRANSITIONS.get(ctx.state, frozenset())
        if new_state not in allowed:
            replay_metrics.invalid_state_transition_total += 1
            log_event(
                "invalid_response_state_transition", call_session_id=self._call_session_id, response_id=ctx.response_id,
                from_state=ctx.state.value, to_state=new_state.value,
            )
            return False
        ctx.state = new_state
        return True

    def _transition_unit(self, unit: PlaybackUnit, new_state: PlaybackUnitState) -> bool:
        """Same reasoning as _transition(), for PlaybackUnitState (spec
        §57/§132-134)."""
        if unit.state == new_state:
            return True
        allowed = VALID_PLAYBACK_UNIT_TRANSITIONS.get(unit.state, frozenset())
        if new_state not in allowed:
            replay_metrics.invalid_state_transition_total += 1
            log_event(
                "invalid_playback_unit_state_transition", call_session_id=self._call_session_id, mark_name=unit.mark_name,
                from_state=unit.state.value, to_state=new_state.value,
            )
            return False
        unit.state = new_state
        return True

    def can_send_media(self, chunk: OutboundAudioChunk) -> OutputGateDecision:
        """P9 — the CustomerFacingOutputGate (spec §75-79): the single,
        final validation point called from exactly one place
        (twilio_media_stream.py's _send_loop) immediately before
        `websocket.send_json()`. Defense in depth (spec §78) — every
        producer upstream already checks ownership before enqueueing, this
        re-checks with LIVE state at the last possible moment, closing the
        TOCTOU race a queue-drain-time-only check can't (see
        docs/P9_REPLAY_PROTECTION_AUDIT.md's own analysis of that race).

        `chunk.identity is None` is the deliberate legacy-path exception
        (spec §161) — a call with no coordinator/ownership model at all
        (pure TTS_MODE=batch) has nothing to validate against, so it's
        always allowed. Every other check fails closed (spec §140): unknown
        response, wrong generation/sequence/epoch, stale playback epoch, or
        an already-sent chunk_index all block the send. No network/DB call,
        no lock beyond plain dict/set membership (spec §79-80)."""
        if chunk.identity is None:
            return OutputGateDecision(True, "legacy_no_identity")
        identity = chunk.identity
        if identity.call_id != self._call_session_id:
            return OutputGateDecision(False, "call_mismatch")
        ctx = self._contexts.get(identity.response_id)
        if ctx is None:
            return OutputGateDecision(False, "unknown_response")
        if not self.is_identity_active(identity):
            return OutputGateDecision(False, "stale_response")
        if chunk.playback_epoch != self._clear_epoch:
            return OutputGateDecision(False, "playback_epoch_stale")
        if chunk.chunk_index in ctx.sent_media_chunk_indices:
            return OutputGateDecision(False, "duplicate_media")
        ctx.sent_media_chunk_indices.add(chunk.chunk_index)
        return OutputGateDecision(True, "ok")

    # --- lifecycle -----------------------------------------------------

    async def begin_response(self, *, turn_id: str, interruptible: bool = True) -> ActiveResponseContext:
        """Spec §9-10 — at most one active customer-facing response per
        call. Superseding an unfinished previous one is automatic here
        (matches TTSStreamingSession's own P6 precedent) rather than
        requiring every caller to remember to call supersede_response()
        first.

        P8 — `interruptible=False` is for legally-required compliance
        notices only (never normal business speech, per this phase's own
        caution) — every other call site keeps the default. DNC/wrong-
        number/human-handoff still always override it; that's enforced at
        the InterruptionPolicy layer (interruption_policy.py), not here —
        this flag only says whether *ordinary* speech may interrupt."""
        if self._active is not None and not self._active.is_terminal():
            await self.supersede_response(self._active.response_id, reason="new_response_started")

        # P9 — globally/randomly unique per spec §7 ("do not use 1, 2, 3
        # alone if reconnections/resets could make ambiguity possible") —
        # uuid4 already gives this; a reconnect or a new call never risks
        # colliding with a prior response_id/generation_id.
        response_id = f"resp_{uuid.uuid4().hex[:12]}"
        generation_id = f"gen_{uuid.uuid4().hex[:12]}"
        self._response_epoch += 1
        ctx = ActiveResponseContext(
            call_id=self._call_session_id, turn_id=turn_id, response_id=response_id,
            generation_id=generation_id, sequence_id=response_id, state=ResponseState.GENERATING_TEXT,
            interruptible=interruptible, response_epoch=self._response_epoch,
        )
        self._active = ctx
        self._contexts[response_id] = ctx
        tts_handle = (
            self._tts_session.begin_response(response_id, identity=ctx.identity, playback_epoch=self._clear_epoch)
            if self._tts_session is not None else None
        )
        self._handles[response_id] = _Handles(context=ctx, tts_handle=tts_handle)
        log_event("pipeline_response_begin", call_session_id=self._call_session_id, response_id=response_id, turn_id=turn_id)
        return ctx

    async def submit_speakable_chunk(self, response_id: str, chunk: SpeakableChunk) -> bool:
        """Spec §12-14/§16-20 — text/generation ownership check before an
        LLM-streamed chunk is allowed to become customer-facing audio, PLUS
        duplicate/conflict/gap detection on chunk_index (spec §18-20).
        Returns False (dropped, never forwarded) if this response is no
        longer the active/current one, or if the chunk fails identity/index
        validation.

        `chunk.generation_id` is NOT compared against `ctx.generation_id`
        directly — they are different namespaces by design.
        `SpeakableChunk.generation_id` is minted once per
        StreamingResponseAssembler.run() call (jkr_conversation), entirely
        independent of this coordinator's own generation_id (minted in
        begin_response()); comparing them directly would reject every
        genuine LLM-streamed chunk (this was a real bug during this phase's
        own development — see docs/P9_REPLAY_PROTECTION_RESULTS.md). What's
        actually validated instead is CROSS-CHUNK CONSISTENCY: every chunk
        accepted for this response must carry the SAME generation_id as the
        first one that was (whichever value that happens to be) — this
        still catches a genuine "two different assembler runs' chunks got
        mixed into the same response" bug, without the wrong assumption."""
        if not self.is_current(response_id):
            replay_metrics.record_blocked("stale_speakable_chunk_dropped_total")
            log_event("pipeline_chunk_dropped_stale", call_session_id=self._call_session_id, response_id=response_id, reason="not_current_response")
            return False
        ctx = self._contexts[response_id]
        if ctx.assembler_generation_id is None:
            ctx.assembler_generation_id = chunk.generation_id
        elif chunk.generation_id != ctx.assembler_generation_id:
            replay_metrics.record_blocked("stale_speakable_chunk_dropped_total")
            log_event(
                "pipeline_chunk_dropped_stale", call_session_id=self._call_session_id, response_id=response_id,
                reason="assembler_generation_mismatch", chunk_generation_id=chunk.generation_id, expected_generation_id=ctx.assembler_generation_id,
            )
            return False

        fingerprint = hash(chunk.text)
        check = check_chunk_index(
            index=chunk.chunk_index, fingerprint=fingerprint, next_expected=ctx.next_expected_text_chunk_index,
            fingerprints_by_index=ctx.text_chunk_fingerprint_by_index,
        )
        if check is ChunkCheckResult.DUPLICATE:
            replay_metrics.record_blocked("duplicate_speakable_chunk_dropped_total")
            log_event("duplicate_speakable_chunk_dropped", call_session_id=self._call_session_id, response_id=response_id, chunk_index=chunk.chunk_index)
            return False
        if check in (ChunkCheckResult.CONFLICT, ChunkCheckResult.GAP):
            replay_metrics.record_blocked("chunk_identity_conflict_total")
            log_event(
                "chunk_identity_conflict", call_session_id=self._call_session_id, response_id=response_id,
                chunk_index=chunk.chunk_index, check=check.value, severity="high",
            )
            # Upstream corruption (spec §20) — fail the response rather than
            # risk sending text to TTS out of order or silently accepting a
            # conflicting duplicate.
            await self.cancel_response(response_id, reason=f"chunk_identity_{check.value}")
            return False
        ctx.text_chunk_fingerprint_by_index[chunk.chunk_index] = fingerprint
        ctx.next_expected_text_chunk_index = max(ctx.next_expected_text_chunk_index, chunk.chunk_index + 1)

        ctx.text_generated += chunk.text
        ctx.text_chunks_created += 1
        self._transition(ctx, ResponseState.TEXT_STREAMING)
        handle = self._handles[response_id].tts_handle
        if handle is not None:
            await handle.send_chunk(chunk.text)
            ctx.text_committed_to_tts += chunk.text
            ctx.text_chunks_sent_to_tts += 1
            ctx.chunk_log.append((chunk.text, time.monotonic()))
            self._transition(ctx, ResponseState.TTS_STREAMING)
        return True

    async def complete_generation(self, response_id: str) -> ActiveResponseContext:
        """Spec §61 — TEXT_GENERATION_COMPLETE / TTS_GENERATION_COMPLETE are
        distinct from PLAYBACK_COMPLETE: this only resolves once TTS has
        finished producing (and this coordinator has finished forwarding)
        all audio for the response — Twilio may still be playing it out
        for a while after this returns. Builds PlaybackUnits from
        TTSTurnOutcome.chunks (§25 mapping)."""
        ctx = self._contexts[response_id]
        handle = self._handles[response_id].tts_handle
        if handle is None:
            if not ctx.is_terminal():
                self._transition(ctx, ResponseState.GENERATION_COMPLETE)
            return ctx

        outcome: TTSTurnOutcome = await handle.finish()
        self._apply_outcome(ctx, outcome)
        if not ctx.is_terminal():
            self._transition(ctx, ResponseState.FAILED if outcome.failed else ResponseState.GENERATION_COMPLETE)
            ctx.failed = outcome.failed
            if outcome.failed:
                ctx.failure_stage = "tts"
                ctx.failure_message = outcome.failure_message
        return ctx

    def _apply_outcome(self, ctx: ActiveResponseContext, outcome: TTSTurnOutcome) -> None:
        if outcome.first_audio_ms is not None:
            ctx.first_audio_ms = outcome.first_audio_ms
        for info in outcome.chunks:
            unit = PlaybackUnit(
                response_id=ctx.response_id, sequence_id=ctx.sequence_id, unit_index=info.audio_chunk_index,
                mark_name=info.mark_name, audio_duration_ms=info.duration_ms, bytes_sent=info.bytes_sent,
                created_at=info.sent_at, sent_at=info.sent_at, state=PlaybackUnitState.SENT,
                clear_epoch_at_creation=self._clear_epoch,
            )
            ctx.playback_units.append(unit)
            self._units_by_mark[info.mark_name] = unit
            ctx.audio_chunks_received += 1
            ctx.audio_ms_generated += info.duration_ms
            ctx.audio_ms_sent += info.duration_ms

    async def wait_playback_complete(self, response_id: str, *, timeout_seconds: float) -> bool:
        """Spec §62 — ClosingManager (and any force-close reply) must wait
        for this, not GENERATION_COMPLETE. Delegates to
        RealtimeMediaSession.wait_for_mark_ack() on the LAST playback
        unit's mark — marks arrive in the order they were sent (a single
        Twilio Media Stream connection, one send loop), so the final
        unit's ack implies every earlier one already resolved, the same
        assumption P6's own closing-grace fix already relied on."""
        ctx = self._contexts.get(response_id)
        if ctx is None or not ctx.playback_units:
            return True  # nothing was ever sent for this response — trivially "complete"
        last_unit = ctx.playback_units[-1]
        acked = await self._media_session.wait_for_mark_ack(last_unit.mark_name, timeout_seconds=timeout_seconds)
        if not ctx.is_terminal():
            self._transition(ctx, ResponseState.PLAYBACK_COMPLETE)
        return acked

    async def cancel_response(self, response_id: str, *, reason: str) -> None:
        """Spec §11 — CANCEL: the response should stop; no replacement
        necessarily exists. Distinct from supersede_response (§11)."""
        await self._stop_response(response_id, target_state=ResponseState.CANCELLED, reason=reason)
        ctx = self._contexts.get(response_id)
        if ctx is not None:
            ctx.cancelled = True
        log_event("pipeline_response_cancelled", call_session_id=self._call_session_id, response_id=response_id, reason=reason)

    async def supersede_response(self, response_id: str, *, reason: str) -> None:
        """Spec §11 — SUPERSEDE: the response loses ownership because a
        newer one replaces it. begin_response() calls this automatically
        for an unfinished previous response; also callable directly."""
        await self._stop_response(response_id, target_state=ResponseState.SUPERSEDED, reason=reason)
        ctx = self._contexts.get(response_id)
        if ctx is not None:
            ctx.superseded = True
        log_event("pipeline_response_superseded", call_session_id=self._call_session_id, response_id=response_id, reason=reason)

    async def _stop_response(self, response_id: str, *, target_state: ResponseState, reason: str) -> None:
        """Shared plumbing for cancel/supersede: delegates the actual TTS-
        layer stop to TTSStreamingSession.cancel_response() (the same
        primitive TTSStreamingSession's own begin_response() uses
        internally) rather than reaching into its provider directly —
        keeps the coordinator's ActiveResponseContext and
        TTSStreamingSession's own _pending bookkeeping from ever
        disagreeing about whether a response is still live."""
        ctx = self._contexts.get(response_id)
        if ctx is None or ctx.is_terminal():
            return
        # P9 §10 — ATOMIC INVALIDATION: both the state transition and the
        # cancellation token flip happen HERE, synchronously, before any
        # await — not after provider cancellation finishes, not after
        # queues drain. StreamingResponseAssembler (P5) already checks this
        # token every loop iteration, so a still-in-flight LLM stream for
        # this generation starts rejecting its own further deltas the very
        # next time it's scheduled, independent of whether the surrounding
        # asyncio task is ever explicitly cancelled (P8's own mechanism).
        self._transition(ctx, target_state)
        ctx.cancellation_token.cancel()
        # P9 §85-89 — proactively purge this response's own not-yet-sent
        # audio out of the local Twilio outbound queue now, rather than
        # relying solely on the output gate to drop it lazily whenever
        # _send_loop happens to dequeue it (still the authoritative,
        # never-removed backstop — this purge is purely a memory/backlog
        # optimization, spec §85).
        purged = self._media_session.purge_outbound_for_response(response_id)
        if purged:
            replay_metrics.queue_stale_items_purged_total += purged
            log_event(
                "stale_twilio_media_purged", call_session_id=self._call_session_id, response_id=response_id, count=purged,
            )
        if self._tts_session is not None:
            await self._tts_session.cancel_response(response_id, reason=reason)
        if self._active is not None and self._active.response_id == response_id:
            self._active = None

    # --- P8 readiness ----------------------------------------------------

    def note_customer_speech(self, *, during_generation: bool = False, during_playback: bool = False) -> None:
        """Spec §88-91 — recorded for observability only; P7 never acts on
        this. Called by the turn loop when TurnManager emits
        USER_SPEECH_STARTED while a response is in flight."""
        if self._active is None:
            return
        if during_generation:
            self._active.customer_spoke_during_generation = True
        if during_playback:
            self._active.customer_spoke_during_playback = True

    def _conservative_delivered_text(self, ctx: ActiveResponseContext) -> str:
        """The one honest answer to "what did the customer conservatively
        hear" this pipeline's tracking granularity supports (see
        docs/INTERRUPTED_RESPONSE_HISTORY.md for the full reasoning): every
        chunk submitted to TTS at or before the moment the LAST
        acknowledged PlaybackUnit was sent. A chunk submitted after that
        point cannot possibly be reflected in audio we know played, so it's
        excluded — never guessed at a word boundary. Empty (not fabricated)
        if no unit was ever acknowledged, which is the correct, safe answer
        when we have no positive evidence anything was heard."""
        acknowledged_sent_ats = [u.sent_at for u in ctx.playback_units if u.state == PlaybackUnitState.ACKNOWLEDGED and u.sent_at is not None]
        if not acknowledged_sent_ats:
            return ""
        last_ack_sent_at = max(acknowledged_sent_ats)
        return "".join(text for text, submitted_at in ctx.chunk_log if submitted_at <= last_ack_sent_at)

    async def interrupt_active_response(self, *, reason: str, clear_playback: bool = True) -> InterruptionSnapshot | None:
        """P8 — the single orchestration point every interruption path
        (a confirmed InterruptionPolicy decision, a future manual admin
        action, a test) must call — never LLM.cancel()/TTS.cancel()/
        Twilio.clear() independently from scattered call sites (this
        phase's own explicit instruction). Implements the cancellation
        order docs/P8_BARGE_IN_AUDIT.md settled on:

          1. idempotency guard (below) — at most one interruption sequence
             per response_id ever actually runs.
          2. `_stop_response(..., target_state=INTERRUPTED)` — reuses the
             exact already-fixed-and-tested TTS-ownership-sync path
             cancel_response()/supersede_response() already share (P7's own
             "two sources of truth" bug fix); sets ctx.state=INTERRUPTED
             SYNCHRONOUSLY before ever awaiting the provider, so a second
             concurrent caller sees a terminal context immediately.
          3. a real Twilio clear, IF this response had already sent audio —
             run CONCURRENTLY with step 2's provider-cancel await (spec:
             never wait for LLM/TTS cancellation ack before clearing
             Twilio), both bounded by INTERRUPTION_CANCEL_TIMEOUT_SECONDS so
             a hung provider/websocket call can never hang the interruption
             itself (failures are logged and swallowed here, never raised —
             the local state transition above already happened regardless
             of whether the remote cancel/clear succeeded).
          4. build the conservative InterruptionSnapshot and return it.

        Idempotent: a response_id already mid-interruption, or already
        terminal, returns None rather than double-cancelling/double-
        clearing."""
        ctx = self._active
        if ctx is None or ctx.is_terminal() or ctx.response_id in self._interrupting:
            return None
        self._interrupting.add(ctx.response_id)
        interruption_id = f"intr_{uuid.uuid4().hex[:12]}"
        response_state_at_interrupt = ctx.state.value
        t0 = time.monotonic()
        try:
            had_sent_audio = ctx.audio_ms_sent > 0
            clear_requested = clear_playback and had_sent_audio and self._media_session.send_twilio_clear is not None
            awaitables: list[Awaitable[None]] = [self._stop_response(ctx.response_id, target_state=ResponseState.INTERRUPTED, reason=reason)]
            if clear_requested:
                assert self._media_session.send_twilio_clear is not None  # narrowed by clear_requested above
                awaitables.append(self._media_session.send_twilio_clear())
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*awaitables, return_exceptions=True), timeout=self._interruption_cancel_timeout_seconds,
                )
                for outcome in results:
                    if isinstance(outcome, Exception):
                        log_event(
                            "pipeline_interruption_cancel_failed", call_session_id=self._call_session_id,
                            response_id=ctx.response_id, error=str(outcome),
                        )
            except TimeoutError:
                log_event(
                    "pipeline_interruption_cancel_timeout", call_session_id=self._call_session_id,
                    response_id=ctx.response_id, reason=reason, timeout_seconds=self._interruption_cancel_timeout_seconds,
                )
                if not ctx.is_terminal():
                    self._transition(ctx, ResponseState.INTERRUPTED)  # local state must still resolve even if the provider call hung
                ctx.cancellation_token.cancel()

            if clear_requested:
                log_event(BARGE_IN_CLEAR_SENT, call_session_id=self._call_session_id, response_id=ctx.response_id, interruption_id=interruption_id)
            log_event(
                BARGE_IN_RESPONSE_CANCELLED, call_session_id=self._call_session_id, response_id=ctx.response_id,
                interruption_id=interruption_id, reason=reason, response_state_at_interrupt=response_state_at_interrupt,
            )
            barge_in_metrics.record_confirmed(response_state=response_state_at_interrupt)

            pending_ms = sum(u.audio_duration_ms for u in ctx.playback_units if u.state == PlaybackUnitState.SENT)
            snapshot = InterruptionSnapshot(
                response_id=ctx.response_id, generated_text=ctx.text_generated, tts_committed_text=ctx.text_committed_to_tts,
                delivered_text=self._conservative_delivered_text(ctx), audio_generated_ms=ctx.audio_ms_generated,
                audio_sent_ms=ctx.audio_ms_sent, audio_acknowledged_ms=ctx.audio_ms_acknowledged,
                pending_playback_ms=pending_ms, playback_units=tuple(ctx.playback_units),
                interruption_id=interruption_id, reason=reason, had_sent_audio=had_sent_audio,
            )
            log_event(
                "pipeline_response_interrupted", call_session_id=self._call_session_id, response_id=ctx.response_id,
                interruption_id=interruption_id, reason=reason, clear_sent=clear_requested,
                audio_sent_ms=ctx.audio_ms_sent, audio_acknowledged_ms=ctx.audio_ms_acknowledged,
                barge_in_clear_latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return snapshot
        finally:
            self._interrupting.discard(ctx.response_id)

    # --- mark / clear observers (wired to RealtimeMediaSession) ------------

    def _on_mark_acknowledged(self, mark_name: str) -> None:
        """Spec §43-44 — duplicate-ack idempotency (P7) generalized: a
        redelivered ack for an already-ACKNOWLEDGED unit is a duplicate
        (metric only, benign); an ack for a CLEARED unit is a stale ack
        (never resurrects it — spec §30/§132). Note mark_name -> PlaybackUnit
        is a call-scoped, never-reused mapping (session.next_mark_name() is
        a simple incrementing counter) — an old response's mark can
        therefore structurally never be confused with a new response's
        unit; "map by playback unit identity" (spec §44) is true by
        construction here, not by an extra check."""
        unit = self._units_by_mark.get(mark_name)
        if unit is None:
            replay_metrics.record_blocked("unknown_response_artifact_dropped_total")
            return
        if unit.state == PlaybackUnitState.ACKNOWLEDGED:
            replay_metrics.duplicate_mark_ignored_total += 1
            return
        if unit.state == PlaybackUnitState.CLEARED:
            replay_metrics.stale_mark_ignored_total += 1
            return
        if not self._transition_unit(unit, PlaybackUnitState.ACKNOWLEDGED):
            return
        unit.mark_acknowledged_at = time.monotonic()
        ctx = self._contexts.get(unit.response_id)
        if ctx is not None:
            ctx.audio_ms_acknowledged += unit.audio_duration_ms

    def _on_playback_clear(self) -> None:
        """Spec §30-31/§45 — every unit sent but not yet acknowledged at the
        moment a clear is requested is classified CLEARED, not left
        pending — a mark that returns later for one of these must never
        flip it to ACKNOWLEDGED (_on_mark_acknowledged's own guard above
        enforces that). playback_epoch (== _clear_epoch) increments so
        future units/audio can be told apart from ones that existed before
        this clear — the invariant the output gate's own playback_epoch
        check (can_send_media()) depends on."""
        self._clear_epoch += 1
        for unit in self._units_by_mark.values():
            if unit.state == PlaybackUnitState.SENT:
                self._transition_unit(unit, PlaybackUnitState.CLEARED)

    # --- observability -----------------------------------------------------

    def dead_air_status(self, *, now: float | None = None) -> DeadAirStatus | None:
        """Spec §52-55 — elapsed time since the active response began
        (begin_response() is called immediately once a turn is committed
        and process_turn() starts, so ActiveResponseContext.created_at is
        the practical proxy for USER_TURN_COMMITTED — spec §59's own
        TURN_COMMIT_TO_FIRST_MEDIA_MS metric uses the same anchor),
        classified against configurable thresholds, with the current
        pipeline stage for root-cause debugging (spec §53) — never
        anything auto-injected into the call (spec §54/§112: classification
        and stage reporting only). None if no response is currently
        awaiting playback completion."""
        ctx = self._active
        if ctx is None or ctx.state == ResponseState.PLAYBACK_COMPLETE:
            return None
        elapsed_ms = ((now if now is not None else time.monotonic()) - ctx.created_at) * 1000
        return DeadAirStatus(level=classify_dead_air(elapsed_ms), elapsed_ms=int(elapsed_ms), stage=ctx.state.value)

    def backpressure_snapshot(self) -> dict:
        """Spec §47 — queue depths + estimated backlog ms, computed on
        demand rather than maintained as separately-updated running
        counters (fewer places to get out of sync)."""
        ctx = self._active
        pending_audio_ms = 0
        if ctx is not None:
            pending_audio_ms = sum(u.audio_duration_ms for u in ctx.playback_units if u.state == PlaybackUnitState.SENT)
        return {
            "twilio_outbound_queue_depth": self._media_session.outbound_queue.qsize(),
            "twilio_playback_backlog_ms": pending_audio_ms,
            "active_response_id": ctx.response_id if ctx is not None else None,
            "active_response_state": ctx.state.value if ctx is not None else None,
        }

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._active is not None and not self._active.is_terminal():
            await self.cancel_response(self._active.response_id, reason="call_ending")
        self._media_session.on_mark_acknowledged = None
        self._media_session.on_playback_clear = None


class CoordinatedResponseHandle:
    """P7 — the coordinator-routed counterpart to tts_bridge.py's
    TTSResponseHandle, same duck-typed shape (`send_chunk`/`finish`) so
    speak_turn_reply() needs zero changes to route every streaming
    response through RealtimePipelineCoordinator's ownership/lifecycle/
    playback-accounting instead of talking to TTSStreamingSession
    directly (spec §92-94: "everything audible goes through coordinator").
    Never constructed directly — see begin_response_feed()."""

    def __init__(self, coordinator: RealtimePipelineCoordinator, ctx: ActiveResponseContext):
        self._coordinator = coordinator
        self._ctx = ctx

    async def send_chunk(self, text: str) -> None:
        if not text.strip():
            return
        chunk = SpeakableChunk(
            response_id=self._ctx.response_id, generation_id=self._ctx.generation_id,
            chunk_index=self._ctx.text_chunks_created, text=text, is_final=False, created_at=time.monotonic(),
        )
        await self._coordinator.submit_speakable_chunk(self._ctx.response_id, chunk)

    async def finish(self) -> TTSTurnOutcome:
        ctx = await self._coordinator.complete_generation(self._ctx.response_id)
        return TTSTurnOutcome(
            response_id=ctx.response_id, failed=ctx.failed, failure_message=ctx.failure_message,
            chunks_sent=len(ctx.playback_units), bytes_sent=sum(u.bytes_sent for u in ctx.playback_units),
            final_mark_name=ctx.playback_units[-1].mark_name if ctx.playback_units else None,
            first_audio_ms=ctx.first_audio_ms,
        )


@dataclass(frozen=True)
class ResponseFeed:
    """Bundles what every turn loop needs to drive one response through the
    coordinator: the handle itself (None when no coordinator is attached to
    this call — TTS_MODE=batch — callers pass this straight through to
    speak_turn_reply's response_handle param unchanged), the
    on_speakable_chunk callback to hand process_turn() (also None in that
    case), a zero-arg getter for whether the callback ever actually fired,
    and (P9) this response's own CancellationToken — threaded into
    process_turn(cancellation_token=...) so StreamingResponseAssembler
    stops consuming a stale generation's own LLM stream the moment this
    response is cancelled/superseded/interrupted (see
    docs/REPLAY_PROTECTION_ARCHITECTURE.md), independent of P8's own
    task-cancellation mechanism."""

    handle: CoordinatedResponseHandle | None
    on_chunk: Callable[[SpeakableChunk], Awaitable[None]] | None
    callback_fired: Callable[[], bool]
    cancellation_token: CancellationToken | None = None


async def begin_response_feed(coordinator: RealtimePipelineCoordinator | None, *, turn_id: str) -> ResponseFeed:
    if coordinator is None:
        return ResponseFeed(handle=None, on_chunk=None, callback_fired=lambda: False, cancellation_token=None)

    ctx = await coordinator.begin_response(turn_id=turn_id)
    handle = CoordinatedResponseHandle(coordinator, ctx)
    state = {"fired": False}

    async def on_chunk(chunk: SpeakableChunk) -> None:
        state["fired"] = True
        await coordinator.submit_speakable_chunk(ctx.response_id, chunk)

    return ResponseFeed(handle=handle, on_chunk=on_chunk, callback_fired=lambda: state["fired"], cancellation_token=ctx.cancellation_token)
