# P8 — Automatic Barge-In: Results & Verification Status

See `docs/P8_BARGE_IN_AUDIT.md` (what existed before P8), `docs/BARGE_IN_ARCHITECTURE.md` (the full
design), `docs/INTERRUPTION_POLICY.md` (the decision function), `docs/INTERRUPTED_RESPONSE_HISTORY.md`
(conversation-history repair). This doc states what has and hasn't been verified, honestly — same practice
as every previous phase.

## Real phone baseline

**NOT TESTED.** This environment cannot place an actual authorized Twilio phone call (no interactive
telephony access). `BARGE_IN_ENABLED` defaults to `false` and must stay `false` until an authorized real
call validates it — this is this phase's own explicit instruction, not a note added after the fact. See
"Manual verification plan" below for what the user should run.

## P7 baseline — result

497 tests confirmed passing repo-wide before any P8 code was written.

## What shipped

- **`InterruptionPolicy`** (`turns/interruption_policy.py`) — pure, synchronous, no-LLM, fake-clock-
  testable decision function. Reuses `backchannel.classify()` (P4) and the existing DNC/wrong-number/
  human-handoff keyword backstop (`jkr_conversation.policy`) rather than rebuilding either. New:
  language-aware high-priority cue detection ("stop"/"wait"/"one minute"/"no"/"actually", English/Telugu/
  Hindi, English always checked in addition to the language-specific list since every profile here is
  code-mixed by default).
- **`ResponseState.INTERRUPTED`** — a new terminal state, distinct from `CANCELLED`/`SUPERSEDED`/`FAILED`
  (P7 anticipated this exact addition and left the enum room for it).
- **Hardened `RealtimePipelineCoordinator.interrupt_active_response()`** — the single orchestration point
  every interruption path now goes through. Idempotency guard (an interruption sequence can only ever run
  once per response, even under concurrent triggers), TTS cancel + Twilio clear run concurrently (never
  one blocking the other), both bounded by `INTERRUPTION_CANCEL_TIMEOUT_SECONDS` so a hung provider call
  can never hang the interruption itself, and a conservative `InterruptionSnapshot` (`delivered_text`,
  `interruption_id`, `reason`, `had_sent_audio` — genuinely new fields, not just the P7 snapshot renamed).
- **A background-task restructure of the streaming turn loop** (`_dispatch_commit()` in
  `streaming_bridge.py`) — the mechanical precondition for provider-signal-based interruption detection to
  be possible at all (the pre-P8 loop was fully serialized; see the audit). Gated entirely behind
  `settings.effective_barge_in_enabled` — the inline-await path used when it's off (the default) is
  byte-identical to pre-P8 behavior.
- **Conservative conversation-history repair** (`docs/INTERRUPTED_RESPONSE_HISTORY.md`) —
  `ActiveResponseContext.chunk_log` + `_conservative_delivered_text()` + `_repair_interrupted_turn_
  history()`. An interrupted response's entry in `redis_state["recent_turns"]` reflects only what was
  conservatively known-delivered, with an `interrupted: true` marker, or is removed entirely if nothing
  was ever acknowledged — never the full generated text.
- **The `expecting_confirmation` wiring gap the audit found** — `TurnManager.expecting_confirmation` was
  never actually set from `redis_state["pending_confirmation"]` in production, meaning confirmation-aware
  backchannel classification was dead code. `InterruptionPolicy` needs the identical signal, so this got
  fixed as part of P8's wiring (both consumers now read the same `redis_state["pending_confirmation"]`
  value).
- **`send_twilio_clear` callback** on `RealtimeMediaSession` — the decoupling fix so
  `interrupt_active_response()` can trigger a real Twilio clear without needing a `WebSocket` reference,
  mirroring the existing `on_mark_acknowledged`/`on_playback_clear` pattern in the other direction.
- **Metrics** (`turns/barge_in_metrics.py`): `barge_in_candidates_total`, `barge_in_confirmed_total`,
  `backchannels_ignored_total`, `barge_in_during_generation/tts/playback/closing_total`,
  `barge_in_recovery_success_total`. Latency numbers (`barge_in_decision_latency_ms`,
  `barge_in_local_stop_latency_ms`, `barge_in_clear_latency_ms`, `barge_in_recovery_latency_ms`) are
  emitted as structured `log_event()` fields rather than aggregated histograms — no such aggregation
  infrastructure exists anywhere else in this codebase either (see the module's own docstring).
  `barge_in_false_positive_total`/`barge_in_false_negative_total` exist as manual-flagging counters for a
  future human-QA path; nothing calls them automatically (this process has no way to know a customer's
  true intent).
- **Event model**: `barge_in_candidate`, `barge_in_backchannel`, `barge_in_confirmed`,
  `barge_in_clear_sent`, `barge_in_response_cancelled` (`BARGE_IN_RESPONSE_CANCELLED` — coordinator-level),
  `barge_in_turn_committed`, `barge_in_recovery_started`, `barge_in_recovery_completed` — logical lifecycle
  events, never per-signal spam.
- **A real, found-and-fixed bug**: the background response *task* and the coordinator's
  `ActiveResponseContext` have different lifetimes — the task finishes once generation and the initial
  audio hand-off to Twilio are done; the response stays audibly active until its audio has actually
  finished playing out. The first implementation gated interruption on `task.done()`, silently doing
  nothing once the task had already finished — exactly the ordinary "customer interrupts mid-sentence,
  audio already sent but unacknowledged" case. **Caught by this phase's own end-to-end integration test
  failing** (`pipeline_response_superseded` where `pipeline_response_interrupted` was expected), not by
  inspection. Fixed by gating both `_execute_pending_interruption()` and `_dispatch_commit()`'s guards on
  the coordinator's active-response state instead of the task's own `.done()`.

## Verified — unit, targeted, and real end-to-end integration tests, all real, all passing

**537 tests passing repo-wide, zero failures** (497 baseline + 40 net new, all in `services/api`):
184 `packages/conversation` + 32 `packages/db` + 287 `services/api` + 10 `services/voice-worker` + 13
`services/campaign-worker` + 11 `services/intelligence-worker`.

The 40 net-new tests, by file (`tests/voice/barge_in/`):

- **`test_interruption_policy.py` (23)** — no active response, terminal response state, "hmm" backchannel
  not expecting confirmation (no interrupt), "haa" during a pending confirmation (treated as a direct
  answer), "one minute" partial interrupting before the qualification window elapses, DNC/human-handoff
  critical cues (English and Telugu/Hindi), a genuine new utterance after the window, the word-count-vs-
  window interaction (both the "wait for it" and "don't wait, already enough evidence" branches), a noise
  burst that ends before qualification, sustained speech past the escalation threshold with no transcript
  ever produced, non-interruptible response never interrupting on ordinary speech but DNC still
  overriding it, the no-audio-yet halved-window behavior, sensitivity presets producing different
  outcomes for identical evidence, and a correction-shaped utterance landing at HIGH-or-above priority.
- **`test_coordinator_interruption.py` (10)** — landing on `INTERRUPTED` not `CANCELLED`, TTS provider
  actually cancelled mid-generation, a real Twilio clear sent only when audio was actually sent (and not
  sent when nothing was), concurrent interrupt triggers producing exactly one cancellation/clear
  (idempotency), a second interrupt after the first completes being a no-op, late audio for an interrupted
  response never reaching the outbound queue (the late-event-dropping proof), PLAYED-vs-CLEARED accounting
  specifically under an interruption (including a late ack for the cleared unit provably not resurrecting
  it), conservative delivered-text only including chunks submitted before the last acknowledged unit
  (never the full generated text), delivered-text being empty (not fabricated) when nothing was ever
  acknowledged, and a non-interruptible response still being interruptible via a direct call (the
  DNC-override path the policy layer would use).
- **`test_barge_in_pipeline_integration.py` (2)** — the real end-to-end proofs, same established pattern as
  `test_turn_detection_integration.py`/`test_p7_pipeline_integration.py` (real WebSocket →
  `RealtimeMediaSession` → `RealtimePipelineCoordinator` → `TurnManager` → `ConversationEngine` → real
  Postgres/Redis, only the two external provider network boundaries faked): (1) a high-priority
  interruption cue ("wait one minute") arriving mid-reply actually stops the original response, sends a
  real Twilio `clear` message, and produces a correct second reply to the new question — this is the test
  that caught the task-vs-response-lifetime bug above; (2) a mere backchannel ("hmm") during the same
  scenario produces neither a clear nor a second committed customer turn.
- **`test_config.py` (+5)** — `barge_in_enabled`/`barge_in_sensitivity` defaults, and
  `effective_barge_in_enabled`'s full cascading-gate matrix (requires streaming STT + streaming TTS +
  vad/hybrid turn detection all together; off if any one is missing; off if the flag itself is off).

Also updated: `test_coordinator.py`'s existing `test_interrupt_active_response_returns_snapshot_and_cancels`
now asserts `ResponseState.INTERRUPTED` instead of `CANCELLED` — the deliberate P8 behavior change P7's own
docs anticipated ("P8 will care about this distinction; P7 just preserves it").

## Classification examples (from the actual test suite, not invented)

| Input | Response state | Decision |
|---|---|---|
| "hmm" (30ms in, not expecting confirmation) | `tts_streaming` | `BACKCHANNEL` — no interrupt |
| "haa" (30ms in, pending confirmation active) | `tts_streaming` | `INTERRUPT` (`NORMAL`) — direct answer |
| "one minute" (30ms in) | `tts_streaming` | `INTERRUPT` (`HIGH`) — bypasses the qualification window |
| "please don't call again" | `tts_streaming` | `INTERRUPT_CRITICAL` — DNC override |
| "tomorrow appointment undha" (300ms in) | `tts_streaming` | `INTERRUPT` (`NORMAL`) — genuine new utterance |
| cough/noise ending before the window, no transcript | `tts_streaming` | `IGNORE` |
| "this call may be recorded" (`interruptible=False`) + "what about pricing" | `tts_streaming` | `MONITOR` — never interrupts |
| same, + "stop calling me" | `tts_streaming` | `INTERRUPT_CRITICAL` — DNC always overrides |

## Cancellation report

Verified paths (per `test_coordinator_interruption.py`): mid-generation (TTS provider `cancel()` actually
called, no Twilio clear needed since nothing was sent), post-generation/mid-playback (provider cancel is a
no-op since generation already resolved, but a real Twilio clear IS sent since audio is unacknowledged),
and the idempotency guard preventing a double-execution when two triggers arrive concurrently. Late audio
for an interrupted response never reaches `RealtimeMediaSession.outbound_queue` — this was already true
before P8 (`tts_bridge.py`'s existing `pending.event.is_set()` guard); P8 added the regression test, not
the mechanism.

## Playback accounting report

`PlaybackUnit` PLAYED-vs-CLEARED accounting, already correct from P7, verified again specifically under an
interruption: a unit acknowledged before the clear stays `ACKNOWLEDGED`; a unit still `SENT` at clear time
becomes `CLEARED`; a late ack for a cleared unit is provably ignored. `InterruptionSnapshot.delivered_text`
is the new P8 addition on top of that — conservative, chunk-timestamp-derived, empty rather than guessed
when there's no positive evidence (`docs/INTERRUPTED_RESPONSE_HISTORY.md`).

## Metrics

See "What shipped" above for the full list. Not implemented: aggregated latency histograms/percentiles (no
precedent for this anywhere in the codebase; per-event structured fields used instead) and automatic false-
positive/false-negative detection (fundamentally requires ground truth this process doesn't have — manual-
flagging counters exist for a future human-QA integration).

## Real-phone validation status

**NOT TESTED**, stated plainly rather than invented. `BARGE_IN_ENABLED` defaults to `false`.

## Known risks / honest gaps

- **Greeting not covered.** The greeting is always sent via the pre-P6 batch PCM path regardless of
  `TTS_MODE`, never through the coordinator — barge-in cannot currently interrupt it, and "AI disclosure
  preserved after an interrupted greeting" is not implemented.
- **Non-interruptible compliance units**: the capability is real and tested (`interruptible=False`,
  DNC-always-overrides), but no call site in this codebase constructs such a response yet — nothing sets
  it in production today.
- **"Okay bye" during closing may not require a full reopen** — an explicit spec "may not," not a hard
  requirement — is not implemented; every confirmed interruption of a closing response reopens the call
  unconditionally via the same general mechanism used for any other response.
- **Adaptive brevity is tracked, not consumed.** `recent_interrupt_count` is incremented and persisted to
  `redis_state["recent_interrupt_count"]`, but `prompt_builder.py`/the formatter do not read it this pass.
- **Sensitivity presets are conservative starting points**, explicitly not measured-optimal — same honest
  framing every prior phase's own tunable constants carry. Real-call benchmarking is still outstanding.
- **`INTERRUPTION_CANCEL_TIMEOUT_SECONDS` (2.0s default)** is a conservative starting point, not measured
  against real provider cancellation latency.

## P9 boundary

P8 verifies stale old work is rejected after an interruption (late TTS audio dropped, stale
`SpeakableChunk`s dropped via `is_current()`) — this was already true pre-P8 and is regression-tested here,
not newly built. **P9 remains NOT DONE**: strict sequence validation, duplicate/late-packet rejection
beyond `is_current()`'s response-id check, and comprehensive replay prevention are out of scope for this
phase, exactly as P7's own docs already stated.

## Manual verification plan (once the user is ready)

1. Staging flags: `TWILIO_VOICE_TRANSPORT=media_stream`, `STT_MODE=streaming`,
   `TURN_DETECTION_MODE=hybrid`, `CONVERSATION_ENGINE_MODE=fast`, `LLM_RESPONSE_MODE=streaming`,
   `TTS_MODE=streaming`, `BARGE_IN_ENABLED=true`, `BARGE_IN_SENSITIVITY=balanced`.
2. Run this phase's own 6-scenario script: (a) "hmm" during an explanation → agent continues uninterrupted;
   (b) "one minute, price entha?" mid-sentence → agent stops quickly, answers the new question; (c) a
   direct Saturday/Sunday answer to the agent's own question → stops, accepts the answer; (d) a rank
   correction (28k→18k) → stops, corrects; (e) a human-handoff request → immediate stop; (f) closing +
   "one more question" → call reopens.
3. Score against the human QA rubric: stop responsiveness, false-interruption rate, backchannel handling,
   recovery naturalness (no "sorry for interrupting" unless genuinely warranted, no "as I was saying"
   unless the customer explicitly returns to the old topic), repetition-after-interruption, new-answer
   relevance.
4. Pull the `barge_in_*` event log for the call and confirm: exactly one `barge_in_confirmed` per genuine
   interruption (not two, from a VAD+provider double-trigger), a `barge_in_clear_sent` only when audio was
   actually playing, and `barge_in_recovery_completed` following each one.

## Definition-of-done, honestly marked

`InterruptionPolicy` pure decision function — **done, tested**. Reuse of P4 signals/`backchannel.classify()`
and the existing DNC/handoff backstop rather than rebuilding — **done**. Interruption lifecycle
(`ResponseState.INTERRUPTED`, idempotent `interrupt_active_response()`) — **done, tested**. Cancellation
order (LLM/TTS cancel concurrent with Twilio clear, timeout-bounded, never independent scattered calls) —
**done, tested**. Conservative generated-vs-committed-vs-delivered text tracking — **done, tested**.
Conversation-history repair — **done, tested**. Natural recovery (no default "sorry for the interruption")
— **done by construction**: the interrupting utterance flows through the completely normal
`TurnManager → ConversationEngine → process_turn()` pipeline with no interruption-specific business logic
or canned apology anywhere in this module. Closing barge-in reopens the call — **done**; the "okay bye may
skip reopening" refinement — **not done**. Greeting interruption / disclosure preservation — **not done**
(greeting not yet coordinator-routed). Non-interruptible compliance units — **capability done, tested; no
production call site**. Priority levels, idempotency, late-event dropping, fresh IDs per response, clear-
epoch correctness — **all done, tested** (fresh IDs and clear-epoch correctness were already true from P7;
regression-tested again here under an interruption specifically). Metrics — **done** (counters +
structured-log latencies; no aggregation infra, consistent with the rest of the codebase). No LLM in the
interrupt hot path — **done by construction** (`interruption_policy.py` has zero I/O). Adaptive brevity —
**tracked, not consumed**. Sensitivity config — **done**, defaults to `balanced`, `high` never auto-
defaulted. Feature flags default disabled — **done, honored**. Required test scenarios — **the core ~20
covered directly** (see the test list above); a few of the ~30 named scenarios (multi-call isolation under
barge-in specifically, TTS-reconnecting-during-interrupt, interrupt during a tool-wait bridge phrase) were
not independently re-tested this pass — the underlying mechanisms they'd exercise (two-call isolation,
bounded TTS reconnect, ownership checks) are already covered by P6/P7's own test suites and were not
touched by P8's changes, but a dedicated P8-specific test for each was not written. Real phone call —
**not done**, `BARGE_IN_ENABLED` stays `false`. P9 — **not done**, as stated above. Ruff/mypy — **clean**
on every touched/new file. No automatic git commit — **honored**.
