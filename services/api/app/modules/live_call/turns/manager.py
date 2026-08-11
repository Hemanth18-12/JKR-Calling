"""P4 — TurnManager: the single authority for conversational turn
boundaries (spec §1/§34). Nothing outside this module decides when a
customer's turn is "done" once TURN_DETECTION_MODE != "provider" — see
docs/TURN_DETECTION_ARCHITECTURE.md.

Deliberately pure and synchronous: every method takes an explicit `now`
(caller-supplied monotonic seconds) and does no I/O, no asyncio, no clock
reads of its own. This is what makes it fake-clock-testable (spec §110-111)
without sleeping in tests, and what makes it safe to call from two
different asyncio tasks (the audio-forward loop feeding VAD signals, the
STT-event loop feeding provider signals) without a lock — a synchronous
call never yields control mid-method, so two calls can never interleave
inside one process's single-threaded event loop.

`SEMANTIC_COMPLETE`/`SEMANTIC_INCOMPLETE`/`BACKCHANNEL` are NOT fed in
externally via `on_signal` — TurnManager computes them itself (calling
semantic.py/backchannel.py directly) as part of handling an STT_FINAL or a
timer tick, and records them into the debug trace (spec §51's own example
trace shows exactly this: "720ms SEMANTIC_INCOMPLETE" as a trace line, not
an external event). `CUSTOMER_RESUMED`/`SILENCE_TIMER`/`MAX_ENDPOINT_WAIT`
are similarly internal — the only externally-fed signal types are
LOCAL_VAD_*, PROVIDER_*, and STT_*.

`provider` mode (the default) reproduces P3's exact pre-P4 behavior: an
STT_FINAL commits immediately, no delay, no semantic gating, no
coalescing wait — this is what makes TURN_DETECTION_MODE=provider
byte-behavior-identical to before this phase (spec §75/§107).
"""

from __future__ import annotations

import uuid

from app.modules.live_call.turns import backchannel, semantic
from app.modules.live_call.turns import metrics as metrics_module
from app.modules.live_call.turns.policies import TurnPolicy
from app.modules.live_call.turns.signals import TurnSignal, TurnSignalType
from app.modules.live_call.turns.state import (
    ENDPOINT_REASON_MAX_TIMEOUT,
    ENDPOINT_REASON_PROVIDER_ONLY,
    ENDPOINT_REASON_SEMANTIC_COMPLETE,
    ENDPOINT_REASON_VAD_SILENCE_COMPLETE,
    TranscriptSegment,
    TurnDebugTrace,
    TurnDecision,
    TurnState,
    UserTurnCommitted,
)

# Resuming speech within this long after a commit suggests the commit may
# have been premature (spec §47) — a heuristic threshold, not a hard rule;
# never used to block or undo an already-committed turn, only to count it.
_PROBABLE_PREMATURE_COMMIT_WINDOW_S = 0.3


class TurnManager:
    def __init__(
        self, *, call_session_id: uuid.UUID, language_code: str, policy: TurnPolicy,
    ) -> None:
        self.call_session_id = call_session_id
        self.language_code = language_code
        self.policy = policy
        self.state = TurnState.IDLE
        self.expecting_confirmation = False  # caller sets this from pending_confirmation state before feeding signals

        self._segments: list[TranscriptSegment] = []
        self._speech_started_at: float | None = None
        self._possible_end_at: float | None = None  # when we FIRST entered possible-end — anchors max_endpoint_delay_ms
        self._last_final_at: float | None = None  # most recent final's arrival — anchors thinking_pause_extension_ms
        self._last_commit_at: float | None = None
        self._pending_commit: UserTurnCommitted | None = None
        self._turn_counter = 0

        self.trace = TurnDebugTrace()
        self.metrics = metrics_module.metrics  # process-wide singleton; call-local trace above is what's per-call

    # --- external signal entry points -----------------------------------

    def on_signal(self, signal: TurnSignal) -> TurnDecision:
        if signal.type in (TurnSignalType.LOCAL_VAD_SPEECH_START, TurnSignalType.PROVIDER_SPEECH_START):
            return self._on_speech_start(signal)
        if signal.type in (TurnSignalType.LOCAL_VAD_SPEECH_END, TurnSignalType.PROVIDER_SPEECH_END):
            return self._on_speech_end_candidate(signal)
        if signal.type == TurnSignalType.STT_PARTIAL:
            return self._on_partial(signal)
        if signal.type == TurnSignalType.STT_FINAL:
            return self._on_final(signal)
        return TurnDecision.WAIT

    def on_timer_tick(self, now: float) -> TurnDecision:
        if self.state not in (TurnState.POSSIBLE_END, TurnState.WAITING_FOR_CONTINUATION):
            return TurnDecision.WAIT
        if not self._segments or self._possible_end_at is None or self._last_final_at is None:
            return TurnDecision.WAIT

        # Two genuinely distinct budgets (spec §15/§20/§41), not three
        # competing ones: min_endpoint_delay is the floor below which
        # nothing ever commits; the ceiling is max_endpoint_delay normally,
        # but EXTENDED by thinking_pause_extension_ms specifically while the
        # text still looks incomplete — "give a slower/thinking speaker
        # genuinely more room," not a second, smaller, competing deadline.
        # fragment_coalesce_ms is a separate, structural concept (see
        # _on_final) — whether a NEW final joins the current turn at all,
        # not a timer threshold.
        elapsed_since_last_final = now - self._last_final_at
        elapsed_since_possible_end = now - self._possible_end_at
        min_delay_s = self.policy.min_endpoint_delay_ms / 1000
        max_delay_s = self.policy.max_endpoint_delay_ms / 1000
        thinking_extension_s = self.policy.thinking_pause_extension_ms / 1000

        if elapsed_since_last_final < min_delay_s:
            return TurnDecision.WAIT

        coalesced_text = self._coalesced_text()
        is_complete, semantic_reason = self._evaluate_completeness(coalesced_text, now=now)
        effective_max_delay_s = max_delay_s if is_complete else max_delay_s + thinking_extension_s
        absolute_max_exceeded = elapsed_since_possible_end >= effective_max_delay_s

        if is_complete or absolute_max_exceeded:
            if absolute_max_exceeded and not is_complete:
                self.trace.record("MAX_ENDPOINT_WAIT", now=now)
                self.metrics.record_endpoint_max_timeout()
                reason = ENDPOINT_REASON_MAX_TIMEOUT
            elif self.policy.mode == "hybrid":
                reason = ENDPOINT_REASON_SEMANTIC_COMPLETE
            else:
                reason = ENDPOINT_REASON_VAD_SILENCE_COMPLETE
            self._commit(now=now, reason=reason, confidence=self._endpoint_confidence(is_complete=is_complete))
            return TurnDecision.COMMIT_TURN

        if self.state != TurnState.WAITING_FOR_CONTINUATION:
            self.state = TurnState.WAITING_FOR_CONTINUATION
            self.trace.record("WAITING_FOR_CONTINUATION", now=now, detail=semantic_reason)
        return TurnDecision.WAIT

    def to_debug_dict(self) -> dict:
        """Spec §51/§53/§98 — "make these metrics queryable and visible in
        developer debugging... no full polished analytics dashboard
        necessary in P4." Same role as
        transport.session.RealtimeMediaSession.to_debug_dict(): enough to
        answer "what is this call's turn detection doing right now" without
        building a UI. Wiring this into an actual HTTP debug endpoint or a
        Test Lab visualizer is a frontend task explicitly out of this
        backend pass's scope."""
        return {
            "call_session_id": str(self.call_session_id),
            "mode": self.policy.mode,
            "profile": self.policy.profile,
            "state": self.state.value,
            "segment_count": len(self._segments),
            "coalesced_text_so_far": self._coalesced_text(),
            "expecting_confirmation": self.expecting_confirmation,
            "trace": self.trace.render(),
        }

    def take_committed_turn(self) -> UserTurnCommitted | None:
        """Call after a COMMIT_TURN decision to retrieve (and clear) the
        payload — mirrors OutboundAudioChunk-style "decision, then fetch
        the data" separation already used elsewhere in this transport."""
        committed = self._pending_commit
        self._pending_commit = None
        return committed

    def flush(self, now: float) -> UserTurnCommitted | None:
        """Force-commit whatever's pending, if anything — spec §73's "call
        ends mid-turn" case. Not automatically wired to every close path in
        this pass; available for a caller that wants to finalize on hangup
        rather than discard in-flight speech. Returns None if there's
        nothing to commit."""
        if self.state not in (TurnState.POSSIBLE_END, TurnState.WAITING_FOR_CONTINUATION) or not self._segments:
            return None
        self._commit(now=now, reason="call_ending", confidence=self._endpoint_confidence(is_complete=False))
        return self.take_committed_turn()

    # --- internal signal handlers -----------------------------------------

    def _on_speech_start(self, signal: TurnSignal) -> TurnDecision:
        if self.state in (TurnState.POSSIBLE_END, TurnState.WAITING_FOR_CONTINUATION):
            # Customer resumed before we committed — cancel the pending
            # commit and go back to active speech (spec §70).
            self.state = TurnState.USER_SPEAKING
            self._possible_end_at = None
            self.trace.record("CUSTOMER_RESUMED", now=signal.timestamp, detail=signal.source)
            return TurnDecision.CANCEL_PENDING_COMMIT
        if self.state == TurnState.IDLE:
            self.state = TurnState.USER_SPEECH_STARTING
            self._speech_started_at = signal.timestamp
            self.metrics.record_speech_burst()
            self.trace.record("USER_SPEECH_STARTED", now=signal.timestamp, detail=signal.source)
            return TurnDecision.USER_STARTED
        return TurnDecision.WAIT

    def _on_speech_end_candidate(self, signal: TurnSignal) -> TurnDecision:
        if self.state in (TurnState.USER_SPEECH_STARTING, TurnState.USER_SPEAKING):
            if not self._segments:
                # Speech-shaped audio with no transcript at all yet —
                # genuinely might just be noise (spec §42/§43/§66). Don't
                # commit to USER_PAUSED forever; if no final ever arrives,
                # the caller's own idle/grace handling covers total silence.
                self.state = TurnState.USER_PAUSED
                self.trace.record("VAD_SILENCE_NO_TRANSCRIPT", now=signal.timestamp, detail=signal.source)
                return TurnDecision.WAIT
            self.state = TurnState.USER_PAUSED
            self.trace.record("VAD_SILENCE", now=signal.timestamp, detail=signal.source)
        return TurnDecision.WAIT

    def _on_partial(self, signal: TurnSignal) -> TurnDecision:
        if self.state == TurnState.IDLE:
            self.state = TurnState.USER_SPEECH_STARTING
            self._speech_started_at = signal.timestamp
        elif self.state == TurnState.USER_SPEECH_STARTING:
            self.state = TurnState.USER_SPEAKING
        self.trace.record("PARTIAL", now=signal.timestamp, detail=(signal.text or "")[:60])
        return TurnDecision.WAIT

    def _on_final(self, signal: TurnSignal) -> TurnDecision:
        text = (signal.text or "").strip()
        if not text:
            if not self._segments:
                self.metrics.record_empty_speech_burst()
                self.trace.record("EMPTY_FINAL", now=signal.timestamp)
                self.state = TurnState.IDLE
                self._speech_started_at = None
            return TurnDecision.WAIT

        if self.policy.mode != "provider" and self._segments and self._last_final_at is not None:
            gap_ms = (signal.timestamp - self._last_final_at) * 1000
            if gap_ms > self.policy.fragment_coalesce_ms:
                # Too much time passed since the last fragment — structurally
                # not a continuation of the same logical turn (spec §26/§71).
                # In practice max_endpoint_delay/thinking_pause_extension
                # would normally have already forced a commit before this
                # can happen; this is a defensive fallback for a policy
                # where fragment_coalesce_ms is tuned tighter than those.
                self.trace.record("FRAGMENT_GAP_TOO_LARGE_STARTING_NEW_TURN", now=signal.timestamp, detail=f"gap_ms={gap_ms:.0f}")
                self._segments = []
                self._speech_started_at = None
                self._possible_end_at = None

        if self._speech_started_at is None:
            self._speech_started_at = signal.timestamp
        self._segments.append(TranscriptSegment(text=text, utterance_idx=signal.utterance_idx, received_at=signal.timestamp))
        self._last_final_at = signal.timestamp
        self.trace.record("FINAL", now=signal.timestamp, detail=text[:60])
        if len(self._segments) > 1:
            self.metrics.record_fragment_coalesced()

        if self.policy.mode == "provider":
            self._commit(now=signal.timestamp, reason=ENDPOINT_REASON_PROVIDER_ONLY, confidence=1.0)
            return TurnDecision.COMMIT_TURN

        self.state = TurnState.POSSIBLE_END
        if self._possible_end_at is None:
            self._possible_end_at = signal.timestamp
        return TurnDecision.MAYBE_END

    # --- helpers -----------------------------------------------------

    def _coalesced_text(self) -> str:
        return " ".join(s.text for s in self._segments).strip()

    def _evaluate_completeness(self, coalesced_text: str, *, now: float) -> tuple[bool, str]:
        if self.policy.mode != "hybrid":
            # vad mode: silence timing alone decides once min_delay has
            # passed — no semantic gating, deliberately, for benchmark
            # comparison against hybrid mode (spec §76/§100).
            return True, "vad_mode_no_semantic_gate"

        backchannel_result = backchannel.classify(coalesced_text, expecting_confirmation=self.expecting_confirmation)
        if backchannel_result.is_backchannel_shaped:
            self.metrics.record_backchannel_detected()
            self.trace.record("BACKCHANNEL", now=now, detail=f"likely_real_answer={backchannel_result.likely_real_answer}")
            if not backchannel_result.likely_real_answer:
                # Filler-shaped and not a direct answer to a pending
                # question — treat cautiously (spec §29/§30), not as
                # confidently complete as ordinary speech.
                return False, "backchannel_not_expected_as_answer"

        completeness = semantic.evaluate(coalesced_text, language_code=self.language_code)
        self.trace.record(
            "SEMANTIC_COMPLETE" if completeness.complete else "SEMANTIC_INCOMPLETE", now=now, detail=completeness.reason,
        )
        return completeness.complete, completeness.reason

    def _endpoint_confidence(self, *, is_complete: bool) -> float:
        """An engineering score derived from signals actually present this
        turn, never an LLM-asked probability (spec §37)."""
        confidence = 0.5
        if self.state in (TurnState.POSSIBLE_END, TurnState.WAITING_FOR_CONTINUATION):
            confidence += 0.2  # we had explicit possible-end evidence (a provider final)
        if is_complete:
            confidence += 0.2
        if len(self._segments) == 1:
            confidence += 0.1  # a single clean segment is stronger evidence than a coalesced multi-fragment guess
        return min(1.0, confidence)

    def _commit(self, *, now: float, reason: str, confidence: float) -> None:
        self._turn_counter += 1
        turn_id = f"turn_{self.call_session_id}_{self._turn_counter}"
        text = self._coalesced_text()

        if self._last_commit_at is not None and (now - self._last_commit_at) < _PROBABLE_PREMATURE_COMMIT_WINDOW_S:
            self.metrics.record_probable_premature_commit()

        self.trace.record("TURN_COMMITTED", now=now, detail=f"reason={reason} text={text[:60]!r}")
        self.metrics.record_turn_committed()

        self._pending_commit = UserTurnCommitted(
            call_session_id=self.call_session_id, turn_id=turn_id, text=text, language_code=self.language_code,
            speech_started_at=self._speech_started_at, speech_ended_at=self._possible_end_at, committed_at=now,
            final_segments=list(self._segments), endpoint_reason=reason, endpoint_confidence=confidence,
        )
        self._last_commit_at = now
        self.state = TurnState.IDLE
        self._segments = []
        self._speech_started_at = None
        self._possible_end_at = None
        self._last_final_at = None
        self.trace.reset()
