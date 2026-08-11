# P8 — Barge-In Audit: Every Existing Interruption-Related Primitive

Written before any P8 code, per this phase's own instruction ("audit before modifying"). Baseline: **497
tests passing repo-wide** (184 `packages/conversation` + 32 `packages/db` + 247 `services/api` + 10
`services/voice-worker` + 13 `services/campaign-worker` + 11 `services/intelligence-worker`), confirmed
before this doc was written.

## 1. Speech-detection signals (P4, `services/api/app/modules/live_call/turns/`)

- **`signals.py`** — `TurnSignalType`: `LOCAL_VAD_SPEECH_START`/`END`, `PROVIDER_SPEECH_START`/`END`,
  `STT_PARTIAL`, `STT_FINAL`, `SEMANTIC_COMPLETE`/`INCOMPLETE`, `BACKCHANNEL`, `CUSTOMER_RESUMED`,
  `SILENCE_TIMER`, `MAX_ENDPOINT_WAIT`. `TurnSignal(type, timestamp, confidence, source, text,
  utterance_idx)` — frozen dataclass. This is the complete signal vocabulary P8 must reuse; no new signal
  type is needed for barge-in detection itself.
- **`vad.py`** — `EnergyVAD.process_frame()` is synchronous, pure arithmetic (RMS threshold), returns a
  signal only on state transition. Called directly from `streaming_bridge._forward_audio_to_stt`, which
  runs as its own asyncio task **concurrently** with everything else in a call — this is the one channel
  that already fires in real time regardless of what the main turn loop is doing (see §5 for why that
  matters).
- **`backchannel.py`** — `classify(text, *, expecting_confirmation) -> BackchannelClassification
  (is_backchannel_shaped, likely_real_answer)`. Exactly the context-aware backchannel/answer distinction
  P8's spec asks for (§ "haa during a yes/no question is a real answer, not a backchannel"). **Reused
  directly by `InterruptionPolicy`, not rebuilt** — this is the single source of truth for "is this
  short utterance a filler or a real reply," now used for two different downstream decisions (turn
  completion in `TurnManager`, interruption confidence in the new policy).
- **`semantic.py`** — `evaluate(text, *, language_code) -> SemanticCompleteness`. Rule-based, sub-
  millisecond, zero network calls. Not directly needed for interruption classification (it answers "is
  this utterance grammatically finished," a turn-completion question) but its *style* — local string
  inspection only, curated per-language marker lists via `lang_prefix()` — is the template P8's own
  critical-phrase detector follows.
- **`policies.py`** — `TurnPolicy(mode, profile, min/max_endpoint_delay_ms, thinking_pause_extension_ms,
  fragment_coalesce_ms)`. No interruption-specific tunables exist yet; P8 adds its own
  `interruption_sensitivity` config rather than overloading this dataclass, since barge-in timing and
  turn-endpoint timing are different concerns.
- **`state.py`** — `TurnState`, `TurnDecision` (`WAIT`/`USER_STARTED`/`USER_CONTINUING`/`MAYBE_END`/
  `COMMIT_TURN`/`CANCEL_PENDING_COMMIT`), `TranscriptSegment`, `UserTurnCommitted`,
  `ENDPOINT_REASON_*`, `TurnDebugTrace` (in-memory, per-call, reset after every commit — never
  persisted). **`TurnDecision.USER_STARTED`** (from `_on_speech_start`, state transition IDLE →
  `USER_SPEECH_STARTING`) is the existing, already-fired signal for "customer just started talking" —
  P8's interruption check hooks onto this decision, not a new detector.
- **`manager.py`** (`TurnManager`) — pure/synchronous, fake-clock-testable (`on_signal(signal) ->
  TurnDecision`, `on_timer_tick(now) -> TurnDecision`), one instance per call, reused across STT
  reconnects. **Confirmed: `TurnManager` has zero concept of "is the agent currently speaking."** It
  reacts to customer speech signals identically whether the agent is silent, generating, or mid-
  playback. Agent-speaking state must be sourced externally, from `RealtimePipelineCoordinator`.
  `_on_speech_start()` already handles "customer resumed before a pending commit" (→
  `CANCEL_PENDING_COMMIT`) — a related but distinct concern from P8's own "customer interrupts agent
  mid-playback" (the former is about the *customer's own* turn boundary; the latter is about the
  *agent's* response ownership).
  `_evaluate_completeness()` already calls `backchannel.classify()` to decide whether a backchannel-
  shaped utterance should be allowed to close a turn — the direct precedent for `InterruptionPolicy`
  calling the same classifier for a different decision.
  **Gap found**: `TurnManager.expecting_confirmation` (constructor default `False`) is a plain attribute
  the caller is documented to set "from `pending_confirmation` state before feeding signals" — but
  **no call site in `streaming_bridge.py` or `twilio_media_stream.py` ever sets it.** In production today,
  confirmation-aware backchannel classification is dead code — `expecting_confirmation` is always
  `False`. This matters for P8 because the same signal (`redis_state["pending_confirmation"]`) is exactly
  what `InterruptionPolicy` needs for "haa during an explicit yes/no question is a genuine answer, not a
  backchannel" (spec requirement). **Fixed as part of P8's wiring** (see `BARGE_IN_ARCHITECTURE.md`) —
  both `TurnManager.expecting_confirmation` and `InterruptionPolicy`'s own input are now set from the same
  `redis_state["pending_confirmation"]` value at the top of each event-processing iteration.

## 2. Local business-rule detectors already reusable for critical-cue classification

`packages/conversation/jkr_conversation/policy.py` — `detect_do_not_call()`, `detect_wrong_number()`,
`detect_human_handoff()`: pure, local, keyword-list-based (English/Telugu/Hindi), zero network calls,
already the enforced backstop for `ExtractionResult` (`apply_backstop()`). **Reused directly** as the
CRITICAL-priority interruption cue detector for DNC/human-handoff/wrong-number, rather than duplicating
a second keyword list — one list to maintain, not two that can drift (the exact problem this module's own
docstring says it was created to prevent).

No existing generic "stop / wait / one minute / no / actually" interruption-urgency phrase list exists
anywhere in the repo — this is genuinely new for P8 (`interruption_policy.py`'s own
`_HIGH_PRIORITY_CUES`), modeled on `semantic.py`'s existing per-language-prefix marker table style.

No dialogue-act classifier exists. P8 does not add an LLM-based one (spec explicitly forbids LLM in the
interrupt hot path) — "dialogue act" as a policy input is derived locally: DNC/handoff detection (above),
a direct-answer-to-pending-question heuristic (reuses `expecting_confirmation`/`pending_confirmation`
exactly as `backchannel.classify()` does), and otherwise treated as an ordinary new utterance.

## 3. `RealtimePipelineCoordinator` (P7, `transport/coordinator.py`) — the ownership/lifecycle authority

- `ResponseState` (11 values, 4 terminal: `PLAYBACK_COMPLETE`/`CANCELLED`/`SUPERSEDED`/`FAILED`).
  **No `INTERRUPTED` state exists yet** — today, an interruption would be indistinguishable from an
  ordinary system cancellation in the state value itself (both land on `CANCELLED`). P8 adds it.
- `ActiveResponseContext` — already tracks `text_generated`/`text_committed_to_tts` (distinct from each
  other) and `audio_ms_generated`/`audio_ms_sent`/`audio_ms_acknowledged` (three distinct counters, never
  one ambiguous "sent" boolean) and `playback_units: list[PlaybackUnit]`. Already has
  `customer_spoke_during_generation`/`customer_spoke_during_playback` booleans, set only by
  `note_customer_speech()` — **recorded, never acted on** (P7's own docs are explicit: "that's P8's job").
  **No per-chunk text/timestamp log exists** — `text_committed_to_tts` is a flat concatenated string with
  chunk boundaries lost, which is a problem for P8's "conservatively-known-delivered text" requirement
  (see §7 below for the fix).
- `PlaybackUnit` — one per audio chunk actually enqueued to Twilio (not one per `SpeakableChunk` — see
  `PLAYBACK_ACCOUNTING.md`), states `CREATED`/`SENT`/`ACKNOWLEDGED`/`CLEARED`/`CANCELLED`. **Deliberately
  no `.text` field** (Sarvam's own buffering doesn't preserve a 1:1 text-chunk-to-audio-chunk boundary).
  At our tracked granularity a unit is binary — fully `ACKNOWLEDGED` or `CLEARED` before ack — there is no
  genuinely "half-played" unit to represent, which simplifies P8's "partial unit unknown" requirement
  (see §7).
- `is_current(response_id)` — the ownership check every chunk-emitting layer already performs before
  producing customer-facing output; a stale/interrupted response's chunks are already dropped by this,
  today, for free.
- `interrupt_active_response(*, reason) -> InterruptionSnapshot | None` — **exists, works, tested
  (`test_interrupt_active_response_returns_snapshot_and_cancels`), called from nowhere automatically.**
  Currently: builds a snapshot, then calls `cancel_response()` (→ `ResponseState.CANCELLED`, not a
  distinct interrupted state). This is the method P8 hardens into the real 9-step orchestrator, per this
  phase's own explicit instruction to "evolve cleanly" rather than add a parallel mechanism.
- `cancel_response()`/`supersede_response()` both delegate to `_stop_response()` →
  `TTSStreamingSession.cancel_response()` — the single, already-correct place a response's TTS/ownership
  gets stopped (P7 fixed a real "two sources of truth" bug here; P8 must not reintroduce it by reaching
  around this method).
- `_on_mark_acknowledged`/`_on_playback_clear` — the real PLAYED-vs-CLEARED mechanism, clear-epoch
  bookkeeping, duplicate-ack idempotency already fixed and tested. **Directly reusable, unchanged** — P8's
  clear step needs no new accounting primitive, just needs to actually be called from an automatic
  trigger.
- **No idempotency guard against concurrent interruption triggers exists** — `interrupt_active_response()`
  can be called twice in overlapping event-loop turns (e.g. VAD start and a provider `SpeechStarted` both
  arriving within the same tick) with no lock; today this is a non-issue only because nothing calls it
  automatically. P8 must add one (see §7).

## 4. TTS-layer cancellation (P6/P7, `transport/tts_bridge.py`)

- `TTSStreamingSession.cancel_response(response_id, *, reason)` — public, awaited, marks the pending
  response failed *synchronously* (`_mark_pending_cancelled`) before awaiting `provider.cancel()`, so a
  same-response completion event racing in from `_run_consumer` can never silently swallow the
  cancellation (the exact P7 bug this fixes, regression-tested).
- **Late TTS audio is already dropped, today, for free**: `_run_consumer`'s `TTSAudioChunk` branch checks
  `pending.event.is_set()` before forwarding any audio chunk to `enqueue_outbound_audio()` — once
  `cancel_response()` sets that event, every subsequent audio chunk for that `response_id` is silently
  dropped, never reaching the outbound queue. This is exactly P8's "late TTS audio for an old sequence_id
  must never reach Twilio" requirement — **already true, P8 only needs to prove it with a test**, not
  build a new mechanism.
- **What `cancel_response()` does NOT do**: anything already sitting in `RealtimeMediaSession
  .outbound_queue` (enqueued before the cancel) is untouched by it — that's `_send_loop`'s own
  `PlaybackState.CLEARING` check (existing P2 logic: `if session.playback_state == CLEARING: continue`),
  which only activates once something calls `session.request_clear_playback()` /
  `clear_agent_audio()`. **Two separate stop mechanisms, both needed**: TTS-side cancel stops *future*
  audio from being produced/queued; Twilio-side clear stops *already-queued-or-sent* audio from being
  played. P8's cancellation order must do both, in the right sequence (see `BARGE_IN_ARCHITECTURE.md`).

## 5. The turn loop itself (`transport/streaming_bridge.py`) — the central architectural gap

`_run_one_streaming_generation`'s main loop is a single `while` loop that, on receiving a committed turn
(`STT_FINAL` → `TurnDecision.COMMIT_TURN`), **awaits `_commit_turn_to_engine()` inline** — which itself
awaits `process_known_transcript_turn()` (LLM generation, possibly full round-trip) and then
`speak_turn_reply()` (TTS streaming through to the last mark). While that await is in flight, the loop
does not advance to its next iteration — meaning:

- **Local VAD signals still fire in real time** — `_forward_audio_to_stt` is a *separate* concurrent
  asyncio task (started once per generation, alongside the main loop) that calls
  `turn_manager.on_signal(vad_signal)` directly and synchronously, completely independent of what the main
  loop is doing. This channel already works today for detecting "customer started talking" during agent
  playback, with no changes needed.
- **Provider-side signals (`SpeechStarted`, `PartialTranscript`, `SpeechEnded`, `FinalTranscript`) do
  NOT** — they arrive via `_drain_stt_events` into `event_queue`, but `event_queue.get()` is only polled
  once per outer-loop iteration, and the outer loop is blocked inside `_commit_turn_to_engine()` for the
  full duration of response generation + playback. In today's (pre-P8) code this is harmless because
  nothing consumes those signals for interruption purposes anyway. **For P8, this is a real gap**: under
  `LOCAL_VAD_ENABLED=false` (provider-only signal mode), an interrupting customer's provider-reported
  `SpeechStarted`/partial transcript would sit unprocessed in `event_queue` until the agent's entire
  response finishes — i.e., no barge-in would be observable at all through that channel alone.

**Fix required and made as part of P8** (see `BARGE_IN_ARCHITECTURE.md` for the full design): the
response-generation-and-playback work (`_commit_turn_to_engine`) must run as a **background task**, not an
inline await, so the main loop keeps draining `event_queue` (and therefore keeps calling
`turn_manager.on_signal()` for provider events) throughout. This is not a cosmetic change — it is the
mechanical precondition for "automatic" barge-in to be possible via provider-only signals at all. Local-
VAD-only interruption detection would have worked without this change; full spec compliance (reusing
*all* of "local VAD, provider speech events, transcript partials/finals") requires it.

## 6. No direct path from the turn loop to a real Twilio clear

`clear_agent_audio(websocket, session)` (`twilio_media_stream.py`) is the real primitive — sends Twilio's
`clear` message and drains `session.outbound_queue` — but it requires a `WebSocket` object, which is only
in scope inside `twilio_media_stream_websocket()`'s own handler and the functions it calls directly
(`_receive_loop`, `_send_loop`). **Neither `streaming_bridge.run_streaming_turn_loop` nor
`RealtimePipelineCoordinator` has access to it.** `RealtimeMediaSession.request_clear_playback()` exists
and *does* flip `playback_state` to `CLEARING` (which makes `_send_loop` drop still-queued chunks) and
fires the `on_playback_clear` hook (which the coordinator already uses to mark `PlaybackUnit`s `CLEARED`)
— but it does **not** send the actual Twilio `clear` WebSocket message, so audio already transmitted to
Twilio would keep playing on the real call without that message. **P8 adds a thin session-level callback**
(`RealtimeMediaSession.send_twilio_clear`, same decoupling pattern as the existing
`on_mark_acknowledged`/`on_playback_clear` hooks), set once by the websocket handler, so the coordinator
can trigger a real clear without needing a `WebSocket` reference itself.

## 7. Conversation-history / "what did the customer actually hear" gap

`transitional_bridge.process_known_transcript_turn()` appends `{"speaker": "agent", "text": reply}` (the
**full** generated reply) to `redis_state["recent_turns"]` **immediately after `process_turn()` returns**
— before TTS/playback has even started, let alone finished. If a response is later interrupted mid-
playback, `recent_turns` (which is what gets fed back into the next turn's LLM context via
`process_turn(recent_turns=...)`) already contains the full, possibly-never-fully-heard text, with no
`interrupted` marker. This is exactly the bug P8's "do not store full generated text as spoken" and
"conversation history repair" sections describe.

Fixing this precisely requires knowing which *portion* of the generated text was conservatively-known to
have been delivered — but as noted in §3, `ActiveResponseContext` has no per-chunk text/timestamp log
today. **P8 adds one** (`ActiveResponseContext.chunk_log: list[tuple[str, float]]`, populated in
`submit_speakable_chunk()` at zero extra cost — the text and a monotonic timestamp are already available
there) so that, at interruption time, "delivered text" can be conservatively computed as: every submitted
chunk whose submission timestamp is `<=` the `sent_at` of the last **ACKNOWLEDGED** `PlaybackUnit` — never
guessed at a word boundary, and empty (not fabricated) if no unit was ever acknowledged. See
`INTERRUPTED_RESPONSE_HISTORY.md`.

## 8. Config flags — none exist yet for P8

`services/api/app/config.py` has the established `effective_*` cascading-gate pattern (`effective_stt_mode`,
`effective_tts_mode`, `effective_turn_detection_mode` — each silently degrades to the safe/legacy value
under a configuration combination nothing implements). No `barge_in_*` field exists. P8 adds
`barge_in_enabled: bool = False`, `barge_in_sensitivity: str = "balanced"`, an `effective_barge_in_enabled`
property gated on streaming STT + streaming TTS + `vad`/`hybrid` turn detection all being active (barge-in
has no meaning without a persistent audio connection and real-time turn signals — same reasoning as every
other `effective_*` property), and `interruption_cancel_timeout_ms`.

## 9. Metrics / events — none exist yet for P8

`turns/metrics.py` (`TurnMetrics`, process-wide singleton, `record_*()` methods) and
`transport/events.py` (string constants + `log_event()`) are the two established patterns. No barge-in
counters or event names exist yet. P8 adds both, following the same shape (see
`BARGE_IN_ARCHITECTURE.md` for the full list) rather than inventing a third observability mechanism.

## Summary — what P8 reuses vs. what is genuinely new

**Reused, unchanged**: `TurnSignal`/`TurnSignalType`, `EnergyVAD`, `backchannel.classify()`,
`TurnManager.on_signal()`/`on_timer_tick()`, `policy.detect_do_not_call/wrong_number/human_handoff()`,
`RealtimePipelineCoordinator`'s ownership/accounting machinery (`is_current`, `PlaybackUnit`,
`_on_mark_acknowledged`/`_on_playback_clear`), `TTSStreamingSession.cancel_response()` and its existing
late-audio-drop behavior, `clear_agent_audio()`'s existing clear+drain logic.

**Genuinely new**: `InterruptionPolicy` (pure decision function), `ResponseState.INTERRUPTED`,
interruption-id-based idempotency lock on the coordinator, a hardened `interrupt_active_response()`
implementing the full cancellation order, a background-task restructure of the streaming turn loop's
response handling (the mechanical fix for §5), a session-level `send_twilio_clear` callback (§6), per-
chunk text/timestamp logging for conservative history repair (§7), the `expecting_confirmation` wiring fix
(§1), config flags, metrics, events.
