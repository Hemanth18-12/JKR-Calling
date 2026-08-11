# P8 — Automatic Barge-In Architecture

See `docs/P8_BARGE_IN_AUDIT.md` (what P8 found and reused before writing anything new),
`docs/INTERRUPTION_POLICY.md` (the decision function in depth), `docs/INTERRUPTED_RESPONSE_HISTORY.md`
(conversation-history repair), and `docs/P8_BARGE_IN_RESULTS.md` (what shipped, tested, honestly not done).

## The rejected approach, and why

The naive version of this feature is `USER_SPEECH_STARTED → coordinator.interrupt_active_response()`. This
phase's own spec explicitly rejects that: it can't distinguish "hmm" from "one minute, wait" from a cough,
it fires just as eagerly while the agent is still thinking (`GENERATING_TEXT`, no audio yet) as it does
mid-sentence, and it has no idea whether the agent's own question ("Saturday or Sunday?") is what's being
answered. What shipped instead is the twelve-step lifecycle the spec describes: customer speech evidence →
local/provider signals → backchannel+context classification → interruption policy → confirmed barge-in →
invalidate old response ownership → cancel LLM → cancel TTS → clear Twilio buffer → account for
played/cleared audio → continue listening → commit the new customer turn through the *normal* pipeline.

## Two pre-existing gaps this phase had to close before any of that could work

Documented in full in the audit; summarized here because they're structural, not incidental:

1. **The turn loop was fully serialized.** `streaming_bridge.py`'s main loop awaited response generation +
   TTS + playback inline, so it never returned to `event_queue.get()` while a response was in flight —
   meaning provider-signal-based interruption evidence (`SpeechStarted`, partial transcripts) physically
   could not be observed until the old response finished on its own. Local VAD worked anyway (it's a
   separate concurrent task), but that's only one of the three signal channels the spec requires reusing.
   **Fixed**: `_dispatch_commit()` runs response generation as a background `asyncio.Task` instead of an
   inline await — *only* when `settings.effective_barge_in_enabled` (the inline, byte-identical-to-pre-P8
   path is untouched when barge-in is off, which is the default).
2. **No path from the turn loop to a real Twilio clear.** `clear_agent_audio()` needs a `WebSocket`, which
   only the top-level connection handler has. **Fixed**: a new decoupled callback,
   `RealtimeMediaSession.send_twilio_clear`, set once by the handler (mirrors the existing
   `on_mark_acknowledged`/`on_playback_clear` pattern, just in the other direction), so
   `RealtimePipelineCoordinator.interrupt_active_response()` can trigger a real clear without a `WebSocket`
   reference.

## The pieces, and who owns what

```
turns/vad.py, streaming_stt events        -- unchanged, reused (P4)
        |
        v
turns/backchannel.py.classify()           -- unchanged, reused (P4) for context-aware filler detection
        |
        v
turns/interruption_policy.py.decide()     -- NEW, pure, no I/O, no LLM (see INTERRUPTION_POLICY.md)
        |
        v  (IGNORE/BACKCHANNEL/MONITOR: no-op.  INTERRUPT/INTERRUPT_CRITICAL: →)
transport/streaming_bridge.py             -- NEW glue: candidate tracking, background task, dispatch
        |
        v
transport/coordinator.py                  -- interrupt_active_response(), extended (P7 → P8)
        |
        v
transport/tts_bridge.py.cancel_response() -- unchanged, reused (P6/P7)
transport/twilio_media_stream.py.clear_agent_audio() -- unchanged, reused (P2), reached via the new callback
```

Nothing about `TurnManager`, `backchannel.classify()`, `EnergyVAD`, or `RealtimePipelineCoordinator`'s
existing ownership/accounting machinery needed to change to add interruption *classification* — only
`interrupt_active_response()` itself was hardened to actually orchestrate a full cancellation, and one real
gap (`expecting_confirmation` never being set — see the audit) was fixed along the way, since
`InterruptionPolicy` needs the exact same signal `backchannel.classify()` already expected but never
received in production.

## Candidate tracking (streaming_bridge.py)

`_InterruptionCandidate(started_at, local_vad_speech, provider_speech, partial_text)` — mutable, one per
customer-speech burst, held on `_TurnTrackingState` (the same per-call object that already carries grace-
period and dedup state across STT reconnects). `_update_interruption_candidate()` is the single entry
point every signal source calls:

- `_forward_audio_to_stt()` (local VAD transitions) — synchronous, same task that already forwards audio,
  adds no meaningful latency (per interruption_policy.py's own no-I/O contract).
- `_handle_stt_event()`'s `SpeechStarted`/`SpeechEnded`/`PartialTranscript` branches — now actually
  reachable during an active response thanks to the background-task fix above.
- `_handle_final_transcript()` — feeds the strongest evidence (a real STT final) before TurnManager even
  decides whether to commit it as a turn.

`_update_interruption_candidate()` is itself synchronous and only *decides* (calls
`interruption_policy.decide()` and either clears the candidate, leaves it pending, or sets
`turn_state.pending_interruption`). The actual async cancellation work never happens inline from a signal
handler — it's picked up once per main-loop iteration, matching the same "poll a flag, act in the main
loop" pattern `_check_grace_expiry()` already used pre-P8.

## Cancellation order (`RealtimePipelineCoordinator.interrupt_active_response()`)

1. **Idempotency guard** — `response_id in self._interrupting` (set/checked synchronously, no `await`
   between check and set) plus the existing `is_terminal()` check. Two triggers arriving in the same
   event-loop tick (VAD start and a provider `SpeechStarted` both firing) produce exactly one sequence.
2. **`_stop_response(target_state=INTERRUPTED)`** — reuses the exact TTS-ownership-sync path
   `cancel_response()`/`supersede_response()` already share (the P7 "two sources of truth" fix); sets
   `ctx.state = INTERRUPTED` *synchronously*, before ever awaiting the provider.
3. **A real Twilio clear**, concurrently with step 2's provider-cancel await (never serialized behind it —
   the spec is explicit that clearing must not wait on an LLM/TTS cancellation ack) — only if this response
   had actually sent audio (`had_sent_audio`).
4. Both awaits are bounded by `INTERRUPTION_CANCEL_TIMEOUT_SECONDS` (2.0s default,
   `INTERRUPTION_CANCEL_TIMEOUT_MS` config) — a hung provider/websocket call resolves the local state
   transition regardless and is logged (`pipeline_interruption_cancel_timeout`,
   `pipeline_interruption_cancel_failed`), never raised into the turn loop.
5. Build the conservative `InterruptionSnapshot` (see `INTERRUPTED_RESPONSE_HISTORY.md`) and return it.

**Late-event dropping was already true before P8** — `tts_bridge.py`'s `_run_consumer` drops any audio
chunk for a response whose `pending.event` is already set, and `submit_speakable_chunk()`'s `is_current()`
check drops any stale `SpeakableChunk`. P8 didn't need to build this; `test_late_audio_chunk_after_interrupt_
never_reaches_outbound_queue` (in `tests/voice/barge_in/test_coordinator_interruption.py`) proves it.

## Two lifetimes, not one — the bug this phase found and fixed

The background response *task* (the Python coroutine driving `process_turn()` + TTS forwarding) and the
coordinator's `ActiveResponseContext` (the customer-facing *response*, "active" until its audio finishes
playing out over the call) have different lifetimes. The task typically finishes fast — generation and
handing audio off to Twilio takes milliseconds in this codebase's mock/fast paths, real API latency
aside — while the response stays "active" (interruptible) until Twilio has actually played it and every
`PlaybackUnit` is acknowledged.

The first version of `_execute_pending_interruption()` gated on `task.done()`: if the task had already
finished, it silently did nothing, assuming "nothing to interrupt." This is wrong — a response whose task
finished but whose audio is still `SENT` (unacknowledged) is exactly the ordinary "customer interrupts
mid-sentence" case, and it needs a real Twilio clear just as much as one still mid-generation. Caught by
this phase's own end-to-end integration test (`test_barge_in_pipeline_integration.py`) failing with
`pipeline_response_superseded` where `pipeline_response_interrupted`/`BARGE_IN_CONFIRMED` were expected —
not by inspection. **Fixed**: both `_execute_pending_interruption()`'s and `_dispatch_commit()`'s guards now
key off `coordinator.active_response` (non-`None`, non-terminal), not the task's own `.done()` state; task
cancellation becomes a no-op when there's nothing left to cancel, but the coordinator-level interrupt
(clear, state transition, snapshot) still runs.

## Safety net: a new commit always wins

`_dispatch_commit()` checks, before starting a new response, whether the coordinator still has an active
response. If so, it synthesizes an `InterruptionDecision(reason="new_turn_committed_while_responding")` and
runs the full interruption sequence *before* starting the new one — even if `InterruptionPolicy` never
explicitly confirmed an early interrupt (e.g. under `LOW` sensitivity, or a policy edge case). This is what
makes "no leaked tasks/stale replays across rapid interruptions" true regardless of sensitivity tuning:
`RealtimePipelineCoordinator` already enforces "at most one active response," but without this guard the
*background task* driving the old one could keep running (still burning generation work, still trying to
speak) after the coordinator silently auto-superseded it.

## Config

```
barge_in_enabled: bool = False           # BARGE_IN_ENABLED — stays False until a real call validates it
barge_in_sensitivity: str = "balanced"   # BARGE_IN_SENSITIVITY — "low" | "balanced" | "high"
interruption_cancel_timeout_ms: int = 2000
```

`Settings.effective_barge_in_enabled` — the same cascading-gate pattern as `effective_stt_mode`/
`effective_tts_mode`/`effective_turn_detection_mode`: `barge_in_enabled` only has any effect when
`effective_stt_mode == "streaming"`, `effective_tts_mode == "streaming"`, and
`effective_turn_detection_mode in ("vad", "hybrid")` are *all* already true — barge-in has no meaning
without a persistent connection, streamed audio to interrupt, and real-time turn signals.

## What's honestly out of scope this pass

- **The greeting is not routed through `RealtimePipelineCoordinator`** — it's always sent via the pre-P6
  batch PCM path (`_send_pcm_reply`), unconditionally, regardless of `TTS_MODE`. Automatic barge-in
  therefore does not cover the greeting; "AI disclosure preserved after an interrupted greeting" is not
  implemented. A real gap, not silently skipped — see `P8_BARGE_IN_RESULTS.md`.
- **Non-interruptible compliance units**: the capability exists and is tested
  (`ActiveResponseContext.interruptible`, `begin_response(interruptible=False)`, DNC-always-overrides in
  `InterruptionPolicy.decide()`) but no call site in this codebase currently constructs a "legally-required
  compliance notice" response, so nothing sets `interruptible=False` in production yet.
- **"Okay bye" during closing may not require a full reopen** (spec's own "may not" — an explicit
  refinement, not a hard requirement) is not implemented; every confirmed interruption of a closing
  response reopens the call unconditionally via the same general mechanism.
- **Adaptive brevity**: `turn_state.recent_interrupt_count` is tracked and persisted to
  `redis_state["recent_interrupt_count"]`, but nothing reads it yet — `prompt_builder.py`/the formatter do
  not shorten responses based on it this pass.
- **No real phone call.** See `P8_BARGE_IN_RESULTS.md`.
