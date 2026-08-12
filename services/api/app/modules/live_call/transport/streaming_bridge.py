"""P3 — persistent Sarvam Realtime streaming STT bridge. Replaces
transitional_bridge.py's trailing-silence turn-buffer + per-turn batch
REST call with one continuous WebSocket connection per call: audio is
forwarded to Sarvam the instant it arrives (silence included — the
provider's own server-side VAD needs a continuous stream to detect speech
boundaries), and a `FinalTranscript` event IS the turn boundary, replacing
`TurnBuffer.is_turn_complete()` entirely for STT_MODE=streaming.

Everything after a transcript exists — persist, ConversationEngine,
domain correction, RAG, planning, generation, tool execution, closing —
is completely unchanged: `transitional_bridge.process_known_transcript_turn()`
is the single shared implementation, called here exactly as it's called
from the batch path. This module owns ONLY the STT session lifecycle
(connect, forward audio, consume events, reconnect) and the same
grace-period/closing state machine `_run_batch_turn_loop` already proved
out in P2 — reimplemented here rather than shared, deliberately: the two
loops react to different event sources (STT events vs. a polled
TurnBuffer) and P2's own precedent is to keep transport-mode code paths
isolated rather than force a shared abstraction that would risk the
already-proven batch path.

Reconnect model (see docs/SARVAM_STREAMING_STT_CONTRACT.md — Sarvam's
protocol has no session-resume): each reconnect starts a brand-new
`SarvamStreamingSTT` instance and a brand-new pair of (audio-forward,
event-consume) tasks; the previous generation's tasks are always fully
torn down before the next one starts, so generations never run
concurrently — this is *how* stale-generation events are structurally
impossible here, not a runtime tag check on every event. Whatever audio
was in flight to a dropped connection during the reconnect gap is lost —
a documented limitation (no recovery buffer in this pass), not a silent
one.
"""

from __future__ import annotations

import asyncio
import time
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, cast

from jkr_db.models.calls import CallEvent, CallSession
from jkr_db.session import workspace_scoped_session
from sqlalchemy import select

from app.config import Settings
from app.live_providers.sarvam_streaming_stt import SarvamStreamingSTT
from app.live_providers.streaming_stt import (
    FinalTranscript,
    StreamingSTTConfig,
    STTError,
    STTEvent,
    STTSessionEnded,
    STTSessionStarted,
)
from app.modules.live_call.transport.coordinator import (
    InterruptionSnapshot,
    ResponseState,
    begin_response_feed,
)
from app.modules.live_call.transport.events import (
    BARGE_IN_BACKCHANNEL,
    BARGE_IN_CANDIDATE,
    BARGE_IN_CONFIRMED,
    BARGE_IN_RECOVERY_COMPLETED,
    BARGE_IN_RECOVERY_STARTED,
    BARGE_IN_TURN_COMMITTED,
    log_event,
)
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.transitional_bridge import (
    process_known_transcript_turn,
    speak_turn_reply,
)
from app.modules.live_call.transport.twilio_media_stream import (
    GRACE_SAFETY_MARGIN_SECONDS,
    _grace_deadline_after_playback,
    _save_redis_state,
)
from app.modules.live_call.turns import interruption_policy
from app.modules.live_call.turns import policies as turn_policies
from app.modules.live_call.turns.barge_in_metrics import metrics as barge_in_metrics
from app.modules.live_call.turns.manager import TurnManager
from app.modules.live_call.turns.signals import TurnSignal, TurnSignalType
from app.modules.live_call.turns.state import TurnDecision, UserTurnCommitted
from app.modules.live_call.turns.vad import EnergyVAD

FRAME_WAIT_TIMEOUT_SECONDS = 1.0  # provider mode / grace-check cadence — matches twilio_media_stream.py's batch-loop cadence
# P4 — vad/hybrid modes need a much tighter poll so TurnManager's
# min/max-endpoint-delay budgets (as small as ~150ms for the FAST preset)
# are actually honored; provider mode never needs this since it commits
# synchronously inside on_signal(), not via on_timer_tick().
TURN_TIMER_POLL_SECONDS = 0.1
MAX_RECONNECT_ATTEMPTS = 3
_RECONNECT_BACKOFF_SECONDS = (0.5, 1.5, 3.0)
# P7 — found unbounded during the pipeline audit (docs/P7_REALTIME_PIPELINE_AUDIT.md):
# this queue carries STT events (partial/final transcripts, session
# markers), which arrive per-utterance, not per-audio-frame, so 100 is a
# generous defensive ceiling rather than a value expected to actually be
# approached — a stalled poll loop should surface as backpressure on
# _drain_stt_events's queue.put() (which then stalls the STT websocket's
# own recv loop) rather than growing this queue without bound.
STT_EVENT_QUEUE_MAXSIZE = 100


@dataclass
class _TurnTrackingState:
    """Carried across reconnects within one call — grace-period state must
    survive a reconnect (a customer who spoke right as the connection
    dropped shouldn't lose their place in the closing flow)."""

    in_grace_period: bool = False
    grace_deadline: float = 0.0
    turn_start_monotonic: float | None = None
    first_partial_logged_this_turn: bool = False
    last_final_utterance_idx: int | None = None
    last_final_text_normalized: str | None = None
    # Most recent FinalTranscript's own per-segment metadata — a P4-
    # coalesced commit may span several finals, so this is a "most recent
    # evidence" proxy for the whole committed turn, not silently dropped.
    last_detected_language_code: str | None = None
    last_language_probability: float | None = None
    generation_id: int = 0

    # P8 — background-response-task bookkeeping. Only ever populated when
    # settings.effective_barge_in_enabled; _dispatch_commit's inline-await
    # branch (barge-in off, the default) never touches any of these, so
    # existing behavior is byte-identical when the flag is off. See
    # docs/BARGE_IN_ARCHITECTURE.md.
    active_response_task: asyncio.Task | None = None
    active_response_recent_turns_len_before: int = 0
    active_response_committed_text: str = ""
    last_response_outcome: object = None
    interruption_candidate: _InterruptionCandidate | None = None
    pending_interruption: interruption_policy.InterruptionDecision | None = None
    recent_interrupt_count: int = 0
    awaiting_recovery_response: bool = False
    recovery_started_at: float | None = None
    # P9 §64-66 — defense in depth: the most recently committed turn_id
    # ever handed to _dispatch_commit. TurnManager's own serialized signal
    # processing (one commit fully resolved before the next signal can even
    # be evaluated — see manager.py) and _dispatch_commit's own safety net
    # (a still-active previous response is always resolved before a new one
    # starts, when barge-in is on) already make an out-of-order commit
    # structurally unreachable in this codebase's current call patterns
    # (see docs/P9_REPLAY_PROTECTION_AUDIT.md's own honest conclusion) —
    # this is an explicit, cheap, tested invariant rather than an implicit
    # one that could silently stop holding if the surrounding code changes.
    latest_committed_turn_sequence: int = -1


@dataclass
class _InterruptionCandidate:
    """Evidence accumulated for one customer-speech burst while the agent
    has an active response — mutable, caller-owned (interruption_policy.py
    itself stays pure/stateless; this is the state TurnManager-equivalent
    object the turn loop threads across repeated decide() calls for the
    same burst)."""

    started_at: float
    local_vad_speech: bool = False
    provider_speech: bool = False
    partial_text: str | None = None


_CALL_ENDED = object()
_CONTINUE = object()


def _turn_sequence_number(turn_id: str) -> int:
    """turn_id is minted as f"turn_{call_session_id}_{n}" by TurnManager
    (manager.py) — n is a per-call monotonic counter. Best-effort parse
    (never raises) used only for the P9 out-of-order-commit guard in
    _dispatch_commit — an unparseable turn_id (e.g. the "greeting" turn_id
    used outside the normal TurnManager flow, or a future format change)
    falls back to -1, which never blocks a legitimate commit since real
    turn_ids always parse to >= 0."""
    try:
        return int(turn_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return -1


_STILL_PRODUCING_STATES = frozenset({
    ResponseState.CREATED, ResponseState.GENERATING_TEXT, ResponseState.TEXT_STREAMING, ResponseState.TTS_STREAMING,
})


def _agent_active_response(session: RealtimeMediaSession):
    """None whenever there is nothing an interruption could apply to —
    either no coordinator (TTS_MODE=batch — barge-in's own config gate
    already prevents this combination, but this stays defensive), no
    currently-active/non-terminal response, or (P9) a response that's
    non-terminal only because this implementation never advances an
    ordinary response's formal state past GENERATION_COMPLETE (see
    docs/BARGE_IN_ARCHITECTURE.md) but has, in practice, already finished
    speaking — every chunk it sent has already been acknowledged and
    nothing more is being generated. Without this second check, a response
    whose audio finished playing minutes ago (the greeting, most commonly,
    once P9 routed it through the coordinator too) would be treated as
    "still active" forever, and the customer's own NEXT, unrelated
    utterance would be misclassified as interrupting it — found during
    this phase's own testing, not by inspection."""
    coordinator = session.pipeline_coordinator
    if coordinator is None:
        return None
    ctx = coordinator.active_response
    if ctx is None or ctx.is_terminal():
        return None
    still_producing = ctx.state in _STILL_PRODUCING_STATES
    has_unacknowledged_audio = ctx.audio_ms_acknowledged < ctx.audio_ms_sent
    if not still_producing and not has_unacknowledged_audio:
        return None
    return ctx


def _update_interruption_candidate(
    turn_state: _TurnTrackingState, *, session: RealtimeMediaSession, settings: Settings, redis_state: dict,
    language_code: str, now: float, local_vad_speech: bool | None = None, provider_speech: bool | None = None,
    partial_text: str | None = None, final_text: str | None = None,
) -> None:
    """The one place every real-time customer-speech signal (local VAD
    transitions, provider SpeechStarted/SpeechEnded, STT partials/finals)
    feeds InterruptionPolicy — pure/cheap/no-LLM per interruption_policy.py's
    own contract, so calling this from a hot signal path (a VAD frame
    transition) adds no meaningful latency. Only ever DECIDES; the actual
    async cancellation sequence is carried out later, by the main loop
    polling turn_state.pending_interruption (see _execute_pending_interruption)
    — never from here, since this function must stay synchronous."""
    if not settings.effective_barge_in_enabled:
        return
    ctx = _agent_active_response(session)
    if ctx is None:
        turn_state.interruption_candidate = None
        return

    candidate = turn_state.interruption_candidate
    if candidate is None:
        candidate = _InterruptionCandidate(started_at=now)
        turn_state.interruption_candidate = candidate
        barge_in_metrics.record_candidate()
        log_event(BARGE_IN_CANDIDATE, call_session_id=session.call_session_id, response_id=ctx.response_id)
    if local_vad_speech is not None:
        candidate.local_vad_speech = local_vad_speech
    if provider_speech is not None:
        candidate.provider_speech = provider_speech
    if partial_text is not None:
        candidate.partial_text = partial_text

    pending_confirmation = redis_state.get("pending_confirmation")
    evidence = interruption_policy.InterruptionEvidence(
        now=now, candidate_started_at=candidate.started_at, local_vad_speech=candidate.local_vad_speech,
        provider_speech=candidate.provider_speech, partial_text=candidate.partial_text, final_text=final_text,
        language_code=language_code, expecting_confirmation=pending_confirmation is not None,
        agent_response_state=ctx.state.value, interruptible=ctx.interruptible, sensitivity=settings.barge_in_sensitivity,
    )
    decision = interruption_policy.decide(evidence)

    if decision.action is interruption_policy.InterruptionAction.BACKCHANNEL:
        barge_in_metrics.record_backchannel_ignored()
        log_event(BARGE_IN_BACKCHANNEL, call_session_id=session.call_session_id, response_id=ctx.response_id, reason=decision.reason)
        turn_state.interruption_candidate = None
    elif decision.action is interruption_policy.InterruptionAction.IGNORE:
        turn_state.interruption_candidate = None
    elif decision.action in (interruption_policy.InterruptionAction.INTERRUPT, interruption_policy.InterruptionAction.INTERRUPT_CRITICAL):
        turn_state.pending_interruption = decision
    # MONITOR / WAIT_FOR_MORE_AUDIO: keep the candidate: decide again on the
    # next signal for the same burst.


def _repair_interrupted_turn_history(
    *, redis_state: dict, committed_text: str, recent_turns_len_before: int, snapshot: InterruptionSnapshot | None,
) -> None:
    """Spec — never store the full generated response as if it were fully
    delivered. `recent_turns_len_before` was captured right before this
    response's background task started; process_known_transcript_turn()
    appends the customer+agent pair together, synchronously, with no await
    in between (see transitional_bridge.py) — so the length delta tells us
    precisely which of two cases happened, no guessing required:
      - both entries present (+2): process_turn() had already returned
        before the interruption landed — repair the agent entry to the
        conservative delivered_text, or drop it entirely if nothing was
        ever acknowledged (never leave a fabricated empty turn).
      - neither entry present (+0): the LLM generation itself was cut off
        before producing anything — no reply text exists to repair, but the
        customer's own words must not simply vanish from context."""
    recent_turns = redis_state.get("recent_turns")
    if recent_turns is None:
        return
    if len(recent_turns) == recent_turns_len_before + 2:
        agent_entry = recent_turns[-1]
        if isinstance(agent_entry, dict) and agent_entry.get("speaker") == "agent":
            delivered = snapshot.delivered_text if snapshot is not None else ""
            if delivered:
                agent_entry["text"] = delivered
                agent_entry["interrupted"] = True
            else:
                recent_turns.pop()
    elif len(recent_turns) == recent_turns_len_before and committed_text:
        recent_turns.append({"speaker": "customer", "text": committed_text})


async def _execute_pending_interruption(
    *, session: RealtimeMediaSession, turn_state: _TurnTrackingState, workspace_id: uuid.UUID, call_session_id: uuid.UUID,
    redis_state: dict, redis: Any, redis_state_token: str,
) -> None:
    """The only place the actual (async) interruption sequence runs —
    cancel the background response task (if one is still actually running
    — see below), then route everything else through
    RealtimePipelineCoordinator.interrupt_active_response() (never
    LLM.cancel()/TTS.cancel()/Twilio.clear() independently). Called from
    the main loop whenever turn_state.pending_interruption is set, and
    defensively from _dispatch_commit if a NEW turn commits while a
    previous response is still active (spec: no leaked tasks across rapid
    interruptions).

    Deliberately gated on the COORDINATOR's active-response state, not on
    whether turn_state.active_response_task is still running — those are
    different lifetimes. The background task finishes once generation and
    the initial hand-off of audio to Twilio are done; the response stays
    audibly "active" (interruptible) until its audio has actually finished
    PLAYING OUT over the call, tracked separately via marks. A response
    whose task already completed but whose audio is still unacknowledged
    is exactly the common "customer interrupts while the agent is
    mid-sentence" case and must still be interrupted here — the task-cancel
    step below just becomes a no-op in that case."""
    from app.modules.live_call.service import _reopen_conversation_state

    decision = turn_state.pending_interruption
    turn_state.pending_interruption = None
    candidate = turn_state.interruption_candidate
    turn_state.interruption_candidate = None
    if decision is None:
        return
    if _agent_active_response(session) is None:
        return  # already resolved on its own (race) — nothing left to interrupt
    coordinator = session.pipeline_coordinator
    assert coordinator is not None  # guaranteed by _agent_active_response's own check above

    task = turn_state.active_response_task
    recent_turns_len_before = turn_state.active_response_recent_turns_len_before
    committed_text = turn_state.active_response_committed_text
    turn_state.recent_interrupt_count += 1
    redis_state["recent_interrupt_count"] = turn_state.recent_interrupt_count
    # spec — barge_in_decision_latency_ms: how long from the first evidence
    # of this speech burst to the confirmed interrupt decision. None for the
    # "new_turn_committed_while_responding" safety-net case (synthesized in
    # _dispatch_commit — there was never a tracked candidate for it).
    decision_latency_ms = int((time.monotonic() - candidate.started_at) * 1000) if candidate is not None else None
    log_event(
        BARGE_IN_CONFIRMED, call_session_id=call_session_id, reason=decision.reason,
        priority=decision.priority.value, confidence=decision.confidence, barge_in_decision_latency_ms=decision_latency_ms,
    )

    local_stop_t0 = time.monotonic()
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001 — a failure in the now-abandoned response task must never crash the turn loop
            log_event("streaming_response_task_failed_during_interrupt", call_session_id=call_session_id, error=str(exc))
    log_event(
        "barge_in_local_stop", call_session_id=call_session_id,
        barge_in_local_stop_latency_ms=int((time.monotonic() - local_stop_t0) * 1000),
    )

    snapshot = await coordinator.interrupt_active_response(reason=decision.reason)
    _repair_interrupted_turn_history(
        redis_state=redis_state, committed_text=committed_text, recent_turns_len_before=recent_turns_len_before, snapshot=snapshot,
    )
    await _save_redis_state(redis, redis_state_token, redis_state)

    # Defensive: a response on its way to a closing/objective-complete
    # decision may have already written that decision into
    # call_session.state before being cut off mid-flight — reopen it the
    # same way the existing grace-period-resume path already does (spec:
    # interrupting CLOSING_PLAYING reopens the call), so the NEXT turn's
    # process_turn() doesn't immediately re-trigger a close just because a
    # half-finished state mutation persisted.
    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call_session = result.scalar_one_or_none()
        if call_session is not None and call_session.state:
            call_session.state = _reopen_conversation_state(dict(call_session.state))
    turn_state.in_grace_period = False

    turn_state.awaiting_recovery_response = True
    turn_state.recovery_started_at = time.monotonic()
    log_event(BARGE_IN_RECOVERY_STARTED, call_session_id=call_session_id, reason=decision.reason)


async def _dispatch_commit(
    committed: UserTurnCommitted, *, session: RealtimeMediaSession, turn_state: _TurnTrackingState, workspace_id: uuid.UUID,
    call_session_id: uuid.UUID, agent_id: uuid.UUID | None, redis_state: dict, settings: Settings, redis: Any,
    redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> object:
    """Routes a freshly committed turn into _commit_turn_to_engine —
    inline (awaited, blocking this loop exactly as before P8) when barge-in
    is off, or as a background task when it's on, so the main loop keeps
    draining STT events (and therefore keeps detecting provider-signal-based
    interruptions) while a response is still in flight. See
    docs/P8_BARGE_IN_AUDIT.md §5 for why the inline path cannot support
    automatic barge-in via provider-only signals, and docs/
    BARGE_IN_ARCHITECTURE.md for the full design."""
    turn_sequence = _turn_sequence_number(committed.turn_id)
    if turn_sequence <= turn_state.latest_committed_turn_sequence:
        # P9 §64-66 — an out-of-order/stale turn result: never create a
        # response for it. Structurally unreachable today (see
        # _TurnTrackingState.latest_committed_turn_sequence's own
        # docstring) — this is the explicit, fail-closed backstop, not the
        # primary mechanism.
        replay_metrics.record_blocked("stale_turn_result_dropped_total")
        log_event(
            "stale_turn_result_dropped", call_session_id=call_session_id, turn_id=committed.turn_id,
            turn_sequence=turn_sequence, latest_known_sequence=turn_state.latest_committed_turn_sequence,
        )
        return _CONTINUE
    turn_state.latest_committed_turn_sequence = turn_sequence

    if not settings.effective_barge_in_enabled:
        return await _commit_turn_to_engine(
            committed, session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
            agent_id=agent_id, redis_state=redis_state, settings=settings, redis=redis, redis_state_token=redis_state_token,
            language_code=language_code, tts_speaker=tts_speaker,
        )

    # A genuinely still-RUNNING previous response task must never be left
    # to keep going once a new turn is about to start (spec: no leaked
    # tasks/stale replays across rapid interruptions) — force it through
    # the full interruption sequence first, synthesizing a decision if
    # InterruptionPolicy never explicitly confirmed one (e.g. LOW
    # sensitivity leaving a candidate in MONITOR while TurnManager's own
    # independent endpoint logic still reached COMMIT_TURN on its own).
    #
    # Deliberately gated on the TASK's own done-state here, NOT on whether
    # the coordinator's response is merely non-terminal (unlike
    # _execute_pending_interruption's own, different, gate) — a response
    # whose task already finished (all text generated, all audio already
    # handed to Twilio) but whose marks simply haven't returned yet is the
    # ORDINARY next-turn-replaces-the-previous-one case, not a barge-in:
    # begin_response()'s own auto-supersede already handles that correctly
    # and harmlessly (no forced Twilio clear needed or wanted — clearing
    # audio that's already fully delivered/in-flight to the phone for no
    # reason risks audibly cutting the customer off mid-word for nothing).
    # This exact distinction is what the coordinator-routed greeting
    # surfaced during this phase's own testing: without it, the ordinary
    # "greeting finished, customer's first turn begins" transition was
    # being misidentified as an interruption of the greeting. If
    # InterruptionPolicy DID already confirm a genuine interruption (the
    # customer actually barged in) but the task happened to finish a moment
    # later on its own, the second branch below still honors it.
    if turn_state.active_response_task is not None and not turn_state.active_response_task.done():
        if turn_state.pending_interruption is None:
            turn_state.pending_interruption = interruption_policy.InterruptionDecision(
                action=interruption_policy.InterruptionAction.INTERRUPT, priority=interruption_policy.InterruptionPriority.NORMAL,
                confidence=1.0, reason="new_turn_committed_while_responding",
            )
        await _execute_pending_interruption(
            session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
            redis_state=redis_state, redis=redis, redis_state_token=redis_state_token,
        )
    elif turn_state.pending_interruption is not None:
        await _execute_pending_interruption(
            session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
            redis_state=redis_state, redis=redis, redis_state_token=redis_state_token,
        )

    if turn_state.awaiting_recovery_response:
        log_event(BARGE_IN_TURN_COMMITTED, call_session_id=call_session_id, turn_id=committed.turn_id)

    turn_state.active_response_recent_turns_len_before = len(redis_state.get("recent_turns", []))
    turn_state.active_response_committed_text = committed.text

    async def _run() -> object:
        return await _commit_turn_to_engine(
            committed, session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
            agent_id=agent_id, redis_state=redis_state, settings=settings, redis=redis, redis_state_token=redis_state_token,
            language_code=language_code, tts_speaker=tts_speaker,
        )

    task = asyncio.create_task(_run())
    turn_state.active_response_task = task
    session.register_task(task)

    def _on_done(t: asyncio.Task) -> None:
        if turn_state.active_response_task is not t:
            return  # superseded/interrupted already — a stale callback, ignore
        turn_state.active_response_task = None
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log_event("streaming_response_task_failed", call_session_id=call_session_id, error=str(exc))
            return
        turn_state.last_response_outcome = t.result()
        if turn_state.awaiting_recovery_response:
            turn_state.awaiting_recovery_response = False
            recovery_latency_ms = (
                int((time.monotonic() - turn_state.recovery_started_at) * 1000) if turn_state.recovery_started_at is not None else None
            )
            turn_state.recovery_started_at = None
            log_event(
                BARGE_IN_RECOVERY_COMPLETED, call_session_id=call_session_id, turn_id=committed.turn_id,
                barge_in_recovery_latency_ms=recovery_latency_ms,
            )
            barge_in_metrics.record_recovery_success()

    task.add_done_callback(_on_done)
    return _CONTINUE


def _normalize_for_dedup(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().lower()


def _is_duplicate_final(turn_state: _TurnTrackingState, *, utterance_idx: int | None, normalized_text: str) -> bool:
    """A duplicate is the same utterance_idx AND the same normalized text —
    utterance_idx alone isn't enough (Sarvam could in principle re-send a
    corrected final for the same utterance) and text alone isn't enough
    (two genuinely different utterances can share identical text, e.g. the
    customer saying "yes" twice — those get distinct utterance_idx values
    and must NOT be deduped away)."""
    return (
        turn_state.last_final_text_normalized is not None
        and _normalize_for_dedup(normalized_text) == turn_state.last_final_text_normalized
        and utterance_idx == turn_state.last_final_utterance_idx
    )


async def _forward_audio_to_stt(
    session: RealtimeMediaSession, stt: SarvamStreamingSTT, *, turn_manager: TurnManager, vad: EnergyVAD | None,
    turn_state: _TurnTrackingState, settings: Settings, redis_state: dict, language_code: str,
) -> None:
    """Runs for the lifetime of one generation — cancelled by
    _run_one_streaming_generation's teardown, never returns on its own.

    P4: when `vad` is configured (TURN_DETECTION_MODE in {"vad","hybrid"}
    AND LOCAL_VAD_ENABLED=true), every inbound frame is also run through
    EnergyVAD synchronously before being forwarded — sub-millisecond pure
    arithmetic (see vad.py's own docstring), so this never meaningfully
    delays send_audio(). TurnManager.on_signal() is itself synchronous too
    (see manager.py), so calling it directly from this task — concurrently
    with the STT-event-consuming task also calling it — is safe: neither
    call ever yields control mid-method, so they can't interleave.

    P8: local VAD is the one signal channel that already reacts in real
    time regardless of what the main loop is doing (see
    docs/P8_BARGE_IN_AUDIT.md §5) — _update_interruption_candidate() is
    synchronous/pure-cheap (no LLM, no I/O) so calling it here adds no
    meaningful latency to send_audio()."""
    while True:
        frame = await session.dequeue_inbound_audio()
        await stt.send_audio(frame.data)
        if vad is not None:
            vad_signal = vad.process_frame(frame.data, sample_rate=frame.sample_rate, now=time.monotonic())
            if vad_signal is not None:
                turn_manager.on_signal(vad_signal)
                _update_interruption_candidate(
                    turn_state, session=session, settings=settings, redis_state=redis_state, language_code=language_code,
                    now=vad_signal.timestamp, local_vad_speech=vad_signal.type is TurnSignalType.LOCAL_VAD_SPEECH_START,
                )


async def _finalize_call_from_grace_expiry(
    *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, redis_state: dict, language_code: str, session: RealtimeMediaSession,
) -> None:
    from app.modules.live_call.service import _finalize_call

    async with workspace_scoped_session(workspace_id) as db:
        await _finalize_call(
            db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
            end_reason=redis_state.get("pending_end_reason", "completed"), had_exchange=True, language_code=language_code,
        )
    session.close()


async def _commit_turn_to_engine(
    committed: UserTurnCommitted, *, session: RealtimeMediaSession, turn_state: _TurnTrackingState, workspace_id: uuid.UUID,
    call_session_id: uuid.UUID, agent_id: uuid.UUID | None, redis_state: dict, settings: Settings, redis: Any,
    redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> object:
    """The one place a TurnManager-committed turn reaches ConversationEngine
    (spec §34/§91) — called either immediately (provider mode's on_signal()
    returns COMMIT_TURN synchronously) or later, from a timer tick
    (vad/hybrid mode, once TurnManager decides the customer is actually
    done). Everything below this point is unchanged from P3: persist,
    ConversationEngine, TTS, grace-period bookkeeping."""
    from app.modules.live_call.service import _reopen_conversation_state

    stt_metadata = {
        # Most recent segment's own detected-language evidence — see
        # _TurnTrackingState's own docstring for why this is a "most
        # recent evidence" proxy once a commit can coalesce multiple finals.
        "stt_detected_language_code": turn_state.last_detected_language_code,
        "stt_language_probability": turn_state.last_language_probability,
        "stt_requested_language_code": language_code,
        "stt_mode": "streaming",
        "stt_endpoint_reason": committed.endpoint_reason,
        "stt_endpoint_confidence": committed.endpoint_confidence,
        "stt_segment_count": len(committed.final_segments),
    }

    async with workspace_scoped_session(workspace_id) as db:
        if turn_state.in_grace_period:
            session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
            call_session = session_result.scalar_one_or_none()
            if call_session is not None and call_session.state:
                call_session.state = _reopen_conversation_state(dict(call_session.state))

        feed = await begin_response_feed(session.pipeline_coordinator, turn_id=committed.turn_id)
        turn_result = await process_known_transcript_turn(
            db, workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id,
            speech_result=committed.text, stt_metadata=stt_metadata, redis_state=redis_state, settings=settings,
            on_speakable_chunk=feed.on_chunk, cancellation_token=feed.cancellation_token,
        )
    await _save_redis_state(redis, redis_state_token, redis_state)

    mark_name = None
    if turn_result.reply_text:
        spoken = await speak_turn_reply(
            reply_text=turn_result.reply_text, session=session, language_code=language_code, settings=settings,
            speaker=tts_speaker, response_handle=feed.handle, callback_fired=feed.callback_fired(),
        )
        if spoken.fatal_failure:
            if turn_state.in_grace_period:
                pass  # already closing; a failed TTS on a reaffirm isn't fatal — just end the call below via grace expiry next tick
            else:
                log_event("media_stream_failed", call_session_id=call_session_id, reason="reply_tts_failed")
                session.close(failed=True)
                return _CALL_ENDED
        else:
            mark_name = spoken.mark_name
            if spoken.first_audio_ms is not None:
                # P10 — closes a real gap the benchmark harness found: this
                # value was already computed (tts_bridge.py's own
                # _finish_response) but previously discarded at the
                # speak_turn_reply() boundary, never persisted. See
                # docs/P10_REAL_CALL_BENCHMARK.md's turn waterfall.
                from app.modules.live_call.service import _record_latency

                async with workspace_scoped_session(workspace_id) as latency_db:
                    await _record_latency(
                        latency_db, workspace_id=workspace_id, call_session_id=call_session_id,
                        stage="tts_stream_first_audio", duration_ms=spoken.first_audio_ms, provider="sarvam",
                    )

    if turn_result.force_close:
        turn_state.in_grace_period = True
        # spec §59-61 — wait for this reply's own final mark to actually be
        # acknowledged before starting the grace clock, not the instant the
        # audio was merely enqueued (see twilio_media_stream.py's
        # _grace_deadline_after_playback for the full reasoning).
        turn_state.grace_deadline = await _grace_deadline_after_playback(session, mark_name)
    else:
        turn_state.in_grace_period = False
    return _CONTINUE


async def _handle_final_transcript(
    event: FinalTranscript, *, session: RealtimeMediaSession, turn_state: _TurnTrackingState, turn_manager: TurnManager,
    workspace_id: uuid.UUID, call_session_id: uuid.UUID, agent_id: uuid.UUID | None, redis_state: dict, settings: Settings,
    redis: Any, redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> object:
    """Dedup + latency bookkeeping (unchanged from P3), then hands the
    genuinely-new final to TurnManager as a signal (spec §91: Sarvam's
    FinalTranscript no longer directly triggers ConversationEngine).
    `provider` mode's policy always returns COMMIT_TURN synchronously here
    — this is what makes TURN_DETECTION_MODE=provider byte-behavior-
    identical to pre-P4 (same dedup, same immediate-commit timing, same
    metadata). vad/hybrid modes may return MAYBE_END instead, in which
    case no engine call happens yet — see _run_one_streaming_generation's
    on_timer_tick loop for where a delayed commit actually fires."""
    from app.modules.live_call.service import _record_latency

    normalized = event.text.strip()
    if not normalized:
        log_event("stt_stream_empty_transcript_dropped", call_session_id=call_session_id, utterance_idx=event.utterance_idx)
        turn_manager.on_signal(TurnSignal(type=TurnSignalType.STT_FINAL, timestamp=time.monotonic(), text="", utterance_idx=event.utterance_idx))
        return _CONTINUE

    if _is_duplicate_final(turn_state, utterance_idx=event.utterance_idx, normalized_text=normalized):
        log_event("stt_stream_duplicate_final_dropped", call_session_id=call_session_id, utterance_idx=event.utterance_idx)
        return _CONTINUE
    turn_state.last_final_utterance_idx = event.utterance_idx
    turn_state.last_final_text_normalized = _normalize_for_dedup(normalized)
    turn_state.last_detected_language_code = event.detected_language_code
    turn_state.last_language_probability = event.language_probability

    if turn_state.turn_start_monotonic is not None:
        finalize_latency_ms = int((time.monotonic() - turn_state.turn_start_monotonic) * 1000)
        async with workspace_scoped_session(workspace_id) as db:
            await _record_latency(
                db, workspace_id=workspace_id, call_session_id=call_session_id, stage="stt_stream_finalize",
                duration_ms=finalize_latency_ms, provider="sarvam",
            )
    turn_state.turn_start_monotonic = None
    turn_state.first_partial_logged_this_turn = False

    _update_interruption_candidate(
        turn_state, session=session, settings=settings, redis_state=redis_state, language_code=language_code,
        now=time.monotonic(), final_text=normalized,
    )

    decision = turn_manager.on_signal(
        TurnSignal(type=TurnSignalType.STT_FINAL, timestamp=time.monotonic(), text=normalized, utterance_idx=event.utterance_idx)
    )
    if decision != TurnDecision.COMMIT_TURN:
        return _CONTINUE

    committed = turn_manager.take_committed_turn()
    if committed is None:
        return _CONTINUE
    return await _dispatch_commit(
        committed, session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
        agent_id=agent_id, redis_state=redis_state, settings=settings, redis=redis, redis_state_token=redis_state_token,
        language_code=language_code, tts_speaker=tts_speaker,
    )


async def _check_grace_expiry(
    *, turn_state: _TurnTrackingState, session: RealtimeMediaSession, workspace_id: uuid.UUID, call_session_id: uuid.UUID,
    redis_state: dict, language_code: str,
) -> object:
    if not turn_state.in_grace_period or time.monotonic() < turn_state.grace_deadline:
        return _CONTINUE
    recent = session.seconds_since_last_media()
    if recent is not None and recent < GRACE_SAFETY_MARGIN_SECONDS:
        turn_state.grace_deadline = time.monotonic() + GRACE_SAFETY_MARGIN_SECONDS
        return _CONTINUE
    await _finalize_call_from_grace_expiry(
        workspace_id=workspace_id, call_session_id=call_session_id, redis_state=redis_state,
        language_code=language_code, session=session,
    )
    return _CALL_ENDED


async def _handle_stt_event(
    event: STTEvent, *, session: RealtimeMediaSession, turn_state: _TurnTrackingState, turn_manager: TurnManager,
    workspace_id: uuid.UUID, call_session_id: uuid.UUID, agent_id: uuid.UUID | None, redis_state: dict, settings: Settings,
    redis: Any, redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> object:
    from app.modules.live_call.service import _record_latency

    if isinstance(event, STTSessionStarted):
        log_event("stt_stream_session_started", call_session_id=call_session_id, request_id=event.request_id)
        return _CONTINUE
    if isinstance(event, STTSessionEnded):
        log_event(
            "stt_stream_session_ended", call_session_id=call_session_id, request_id=event.request_id,
            audio_duration_s=event.audio_duration_s, total_utterances=event.total_utterances,
        )
        return _CONTINUE
    if isinstance(event, STTError):
        log_event(
            "stt_stream_error", call_session_id=call_session_id, code=event.code, message=event.message,
            is_fatal=event.is_fatal, status_code=event.status_code,
        )
        if event.is_fatal:
            await _persist_stt_lifecycle_event(
                workspace_id=workspace_id, call_session_id=call_session_id, event_type="stt_stream_fatal_error",
                payload={"code": event.code, "message": event.message, "status_code": event.status_code},
            )
        return _CONTINUE  # non-fatal errors don't interrupt the call; fatal ones surface as a dropped connection, handled by the reconnect loop

    # Anything that marks the start of a new utterance resets the
    # first-partial timer used for the stt_stream_first_partial latency
    # metric — speech_start if VAD events are enabled, otherwise the first
    # partial/final itself. Also feeds TurnManager PROVIDER_SPEECH_START/
    # END (spec §32/§33) — P4 fixes the audit-identified gap where
    # SpeechEnded was previously received and silently dropped entirely.
    event_type_name = type(event).__name__
    if event_type_name == "SpeechStarted":
        if turn_state.turn_start_monotonic is None:
            turn_state.turn_start_monotonic = time.monotonic()
        turn_manager.on_signal(TurnSignal(type=TurnSignalType.PROVIDER_SPEECH_START, timestamp=time.monotonic(), source="sarvam"))
        _update_interruption_candidate(
            turn_state, session=session, settings=settings, redis_state=redis_state, language_code=language_code,
            now=time.monotonic(), provider_speech=True,
        )
        return _CONTINUE
    if event_type_name == "SpeechEnded":
        turn_manager.on_signal(TurnSignal(type=TurnSignalType.PROVIDER_SPEECH_END, timestamp=time.monotonic(), source="sarvam"))
        _update_interruption_candidate(
            turn_state, session=session, settings=settings, redis_state=redis_state, language_code=language_code,
            now=time.monotonic(), provider_speech=False,
        )
        return _CONTINUE
    if event_type_name == "PartialTranscript":
        if turn_state.turn_start_monotonic is None:
            turn_state.turn_start_monotonic = time.monotonic()
        elif not turn_state.first_partial_logged_this_turn:
            turn_state.first_partial_logged_this_turn = True
            first_partial_latency_ms = int((time.monotonic() - turn_state.turn_start_monotonic) * 1000)
            async with workspace_scoped_session(workspace_id) as db:
                await _record_latency(
                    db, workspace_id=workspace_id, call_session_id=call_session_id, stage="stt_stream_first_partial",
                    duration_ms=first_partial_latency_ms, provider="sarvam",
                )
        partial_text = getattr(event, "text", None)
        turn_manager.on_signal(TurnSignal(type=TurnSignalType.STT_PARTIAL, timestamp=time.monotonic(), text=partial_text))
        if partial_text:
            _update_interruption_candidate(
                turn_state, session=session, settings=settings, redis_state=redis_state, language_code=language_code,
                now=time.monotonic(), partial_text=partial_text,
            )
        return _CONTINUE
    if isinstance(event, FinalTranscript):
        if turn_state.turn_start_monotonic is None:
            turn_state.turn_start_monotonic = time.monotonic()
        return await _handle_final_transcript(
            event, session=session, turn_state=turn_state, turn_manager=turn_manager, workspace_id=workspace_id,
            call_session_id=call_session_id, agent_id=agent_id, redis_state=redis_state, settings=settings, redis=redis,
            redis_state_token=redis_state_token, language_code=language_code, tts_speaker=tts_speaker,
        )
    return _CONTINUE


_STT_STREAM_ENDED = object()  # sentinel: _drain_stt_events finished (cleanly or via error) — this generation should reconnect


async def _drain_stt_events(stt: SarvamStreamingSTT, queue: asyncio.Queue[object]) -> None:
    """Continuously consumes stt.events() into a queue, uninterrupted by
    any outer timeout. This exists specifically because `asyncio.wait_for`
    applied *directly* to `anext()` of an async generator is unsafe: if the
    timeout fires while the generator is suspended mid-body (e.g. awaiting
    the next websocket frame), the cancellation `wait_for` injects
    propagates into the generator's own suspended await — and once a
    `CancelledError` unwinds out of an async generator frame uncaught, the
    generator is permanently closed (confirmed empirically: a generator
    cancelled while inside `asyncio.sleep()` never yields again — every
    subsequent `anext()` raises `StopAsyncIteration` immediately, even
    though more real items existed). `_run_one_streaming_generation` needs
    a tight, timeout-bounded poll (P4's TURN_TIMER_POLL_SECONDS, as low as
    0.1s) to keep TurnManager's endpoint timers responsive; the STT
    connection's own event cadence is unrelated to that poll interval and
    must never be torn down by it. Polling a plain `asyncio.Queue` with a
    timeout is always safe to cancel — it never touches this task's
    internal state — so the timeout lives on the queue read here, never on
    the generator itself."""
    try:
        async for event in stt.events():
            await queue.put(event)
    except Exception:  # noqa: BLE001 — any provider-side error while draining also means "this connection is done"; the reconnect loop handles it
        pass
    finally:
        await queue.put(_STT_STREAM_ENDED)


async def _run_one_streaming_generation(
    session: RealtimeMediaSession, stt: SarvamStreamingSTT, *, turn_state: _TurnTrackingState, turn_manager: TurnManager,
    vad: EnergyVAD | None, workspace_id: uuid.UUID, call_session_id: uuid.UUID, agent_id: uuid.UUID | None,
    redis_state: dict, settings: Settings, redis: Any, redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> bool:
    """Runs one connection's lifetime. Returns True if the call legitimately
    ended while this generation was active (grace expired -> finalized, or
    a fatal reply-TTS failure closed the session) — the caller should stop.
    Returns False if the STT connection itself ended (server closed the
    socket, or events() raised) without the call itself ending — the
    caller should reconnect.

    P4: also polls `turn_manager.on_timer_tick()` every iteration — the
    only place a vad/hybrid-mode delayed commit (min/max endpoint delay,
    thinking-pause extension) actually fires, since TurnManager itself
    never sleeps or reads the clock. `provider` mode never produces a
    timer-driven commit (on_signal() already committed synchronously), so
    the poll interval only needs to be tight for the other two modes."""
    forward_task = asyncio.create_task(
        _forward_audio_to_stt(
            session, stt, turn_manager=turn_manager, vad=vad, turn_state=turn_state, settings=settings,
            redis_state=redis_state, language_code=language_code,
        )
    )
    session.register_task(forward_task)
    event_queue: asyncio.Queue[object] = asyncio.Queue(maxsize=STT_EVENT_QUEUE_MAXSIZE)
    drain_task = asyncio.create_task(_drain_stt_events(stt, event_queue))
    session.register_task(drain_task)
    poll_timeout = FRAME_WAIT_TIMEOUT_SECONDS if turn_manager.policy.mode == "provider" else TURN_TIMER_POLL_SECONDS
    try:
        while not session.is_closed:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=poll_timeout)
            except TimeoutError:
                event = None
            if event is _STT_STREAM_ENDED:
                return False

            if event is not None:
                # event_queue is typed as object (it also carries the
                # _STT_STREAM_ENDED sentinel) — already ruled out above, so
                # anything left really is an STTEvent from _drain_stt_events.
                outcome = await _handle_stt_event(
                    cast(STTEvent, event), session=session, turn_state=turn_state, turn_manager=turn_manager,
                    workspace_id=workspace_id, call_session_id=call_session_id, agent_id=agent_id, redis_state=redis_state,
                    settings=settings, redis=redis, redis_state_token=redis_state_token, language_code=language_code,
                    tts_speaker=tts_speaker,
                )
                if outcome is _CALL_ENDED:
                    return True

            if turn_manager.policy.mode != "provider":
                timer_decision = turn_manager.on_timer_tick(now=time.monotonic())
                if timer_decision == TurnDecision.COMMIT_TURN:
                    committed = turn_manager.take_committed_turn()
                    if committed is not None:
                        commit_outcome = await _dispatch_commit(
                            committed, session=session, turn_state=turn_state, workspace_id=workspace_id,
                            call_session_id=call_session_id, agent_id=agent_id, redis_state=redis_state, settings=settings,
                            redis=redis, redis_state_token=redis_state_token, language_code=language_code, tts_speaker=tts_speaker,
                        )
                        if commit_outcome is _CALL_ENDED:
                            return True

            # P8 — a confirmed interruption (from local VAD, a provider
            # signal, or a partial/final transcript — any of which may have
            # fired from a concurrently-running task, or from the event/
            # timer-tick handling just above) is acted on here, once per
            # iteration, never inline from the signal-producing site itself.
            if turn_state.pending_interruption is not None:
                await _execute_pending_interruption(
                    session=session, turn_state=turn_state, workspace_id=workspace_id, call_session_id=call_session_id,
                    redis_state=redis_state, redis=redis, redis_state_token=redis_state_token,
                )

            if turn_state.last_response_outcome is not None:
                response_outcome = turn_state.last_response_outcome
                turn_state.last_response_outcome = None
                if response_outcome is _CALL_ENDED:
                    return True

            grace_outcome = await _check_grace_expiry(
                turn_state=turn_state, session=session, workspace_id=workspace_id, call_session_id=call_session_id,
                redis_state=redis_state, language_code=language_code,
            )
            if grace_outcome is _CALL_ENDED:
                return True
        return True  # session closed elsewhere (Twilio stop event / disconnect) — not this generation's problem to reconnect
    finally:
        # Deliberately does NOT cancel turn_state.active_response_task here:
        # this generation ending can mean either the call is truly over
        # (session.close() was already called by whatever produced the
        # _CALL_ENDED/loop-exit path above, which already cancels every
        # session.register_task()-registered task, including the response
        # task — no need to duplicate that) OR the STT connection merely
        # needs to reconnect (return False) — a case where an in-flight
        # agent response must be allowed to keep running unaffected,
        # exactly as it already could pre-P8 (STT reconnects and response
        # generation were always independent concerns).
        forward_task.cancel()
        drain_task.cancel()


async def run_streaming_turn_loop(
    session: RealtimeMediaSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, agent_id: uuid.UUID | None,
    redis_state: dict, settings: Settings, redis: Any, redis_state_token: str, language_code: str, tts_speaker: str | None,
) -> bool:
    """Entry point called from twilio_media_stream.py's _processing_loop.
    Owns the persistent Sarvam streaming STT connection for the rest of
    this call, including a bounded reconnect loop. Returns True if the
    caller should fall back to _run_batch_turn_loop (only when
    settings.stt_stream_failure_policy == "batch_next_turn" and reconnects
    were exhausted); False if the call was already fully handled (ended
    normally, or the session was closed/failed directly).

    P4: one TurnManager (and one EnergyVAD, if enabled) for the whole call,
    created once here and reused across reconnects — a reconnect only
    replaces the STT connection itself; whatever turn was in progress
    keeps its accumulated segments/state (see manager.py's own reasoning
    for why this is safer than resetting on every reconnect)."""
    turn_state = _TurnTrackingState()
    turn_policy = turn_policies.get_policy(mode=settings.effective_turn_detection_mode, profile=settings.turn_profile, language_code=language_code)
    turn_manager = TurnManager(call_session_id=call_session_id, language_code=language_code, policy=turn_policy)
    vad = EnergyVAD() if settings.local_vad_enabled and turn_policy.mode != "provider" else None
    reconnect_attempts = 0
    config = StreamingSTTConfig(language_code=language_code)

    while not session.is_closed:
        turn_state.generation_id += 1
        api_key = settings.sarvam_api_key or settings.sarvam_tts_api_key
        stt = SarvamStreamingSTT(api_key=api_key, config=config)
        try:
            await stt.connect()
        except Exception as exc:  # noqa: BLE001 — connect failures come from the network/provider, never re-raised past this boundary
            log_event(
                "stt_stream_connect_failed", call_session_id=call_session_id, generation_id=turn_state.generation_id,
                error=str(exc),
            )
            reconnect_attempts += 1
            if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                return await _give_up_on_streaming(session, settings=settings, workspace_id=workspace_id, call_session_id=call_session_id)
            await asyncio.sleep(_RECONNECT_BACKOFF_SECONDS[min(reconnect_attempts - 1, len(_RECONNECT_BACKOFF_SECONDS) - 1)])
            continue

        log_event("stt_stream_connected", call_session_id=call_session_id, generation_id=turn_state.generation_id)
        try:
            ended_cleanly = await _run_one_streaming_generation(
                session, stt, turn_state=turn_state, turn_manager=turn_manager, vad=vad, workspace_id=workspace_id,
                call_session_id=call_session_id, agent_id=agent_id, redis_state=redis_state, settings=settings, redis=redis,
                redis_state_token=redis_state_token, language_code=language_code, tts_speaker=tts_speaker,
            )
        finally:
            await stt.close()

        if ended_cleanly or session.is_closed:
            return False

        reconnect_attempts += 1
        log_event(
            "stt_stream_reconnecting", call_session_id=call_session_id, attempt=reconnect_attempts,
            max_attempts=MAX_RECONNECT_ATTEMPTS,
        )
        if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
            return await _give_up_on_streaming(session, settings=settings, workspace_id=workspace_id, call_session_id=call_session_id)
        await asyncio.sleep(_RECONNECT_BACKOFF_SECONDS[min(reconnect_attempts - 1, len(_RECONNECT_BACKOFF_SECONDS) - 1)])

    return False


async def _persist_stt_lifecycle_event(
    *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, event_type: str, payload: dict
) -> None:
    """Real-call forensics finding: a fatal provider error (e.g. Sarvam
    quota_exceeded/402) or a give-up-after-exhausted-reconnects previously
    left ZERO durable trace anywhere — log_event() alone is invisible unless
    someone is watching that exact process's stdout at that exact moment,
    and every other per-call table (CallTurn, CallLatencyMetric) stays empty
    too since no turn ever gets that far. A real incident took a live
    out-of-band provider probe to diagnose for exactly this reason. This is
    the minimal fix: persist it as a CallEvent, the same durable per-call
    trail every other lifecycle moment already uses, queryable via the
    RLS-safe report tool. A separate function (not inlined) specifically so
    unit tests exercising run_streaming_turn_loop's failure-policy branching
    with synthetic/non-persisted workspace_id and call_session_id values
    (see test_streaming_bridge.py) can monkeypatch this one DB-touching
    seam, the same way that file already monkeypatches
    _finalize_call_from_grace_expiry — everything else in this module stays
    exercised for real."""
    async with workspace_scoped_session(workspace_id) as db:
        db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type=event_type, payload=payload))


async def _give_up_on_streaming(
    session: RealtimeMediaSession, *, settings: Settings, workspace_id: uuid.UUID, call_session_id: uuid.UUID
) -> bool:
    log_event(
        "stt_stream_failed", call_session_id=call_session_id, reason="reconnect_attempts_exhausted",
        failure_policy=settings.stt_stream_failure_policy,
    )
    await _persist_stt_lifecycle_event(
        workspace_id=workspace_id, call_session_id=call_session_id, event_type="stt_stream_gave_up",
        payload={"reason": "reconnect_attempts_exhausted", "failure_policy": settings.stt_stream_failure_policy},
    )
    if settings.stt_stream_failure_policy == "batch_next_turn":
        return True
    session.close(failed=True)
    return False
