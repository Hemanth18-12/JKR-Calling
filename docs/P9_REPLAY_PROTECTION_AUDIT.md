# P9 — Replay Protection Audit: Every Boundary That Produces or Transports Customer-Facing Audio

Written before any P9 code, per this phase's own instruction. Baseline: **537 tests passing repo-wide**
(184 `packages/conversation` + 32 `packages/db` + 287 `services/api` + 10 `services/voice-worker` + 13
`services/campaign-worker` + 11 `services/intelligence-worker`), confirmed before this doc was written.

## The chain, traced end to end

```
OpenAI SSE delta
  -> StreamingResponseAssembler.run()          (jkr_conversation/streaming_response.py)
  -> SpeakableChunk                             (response_id, generation_id, chunk_index — self-assigned, len(chunks))
  -> on_speakable_chunk callback                 = CoordinatedResponseHandle.send_chunk() / begin_response_feed()'s on_chunk
  -> RealtimePipelineCoordinator.submit_speakable_chunk(response_id, chunk)
  -> TTSResponseHandle.send_chunk()              (tts_bridge.py)
  -> TTSStreamingSession._text_queue             (bounded, TEXT_QUEUE_MAXSIZE=64)
  -> TTSStreamingSession._run_sender()           -> provider.send_text(text, response_id, chunk_index)
  -> SarvamStreamingTTS receive loop             -> TTSAudioChunk(response_id, audio_chunk_index — self-assigned per response_id)
  -> TTSStreamingSession._run_consumer()         -> OutboundAudioChunk (base.py)
  -> RealtimeMediaSession.outbound_queue         (bounded, DEFAULT_OUTBOUND_QUEUE_MAXSIZE)
  -> _send_loop()                                -> websocket.send_json() (Twilio)
```

## Boundary table

| Boundary | Identity present today | Validation today | Duplicate guard | Stale guard | Risk |
|---|---|---|---|---|---|
| LLM delta → assembler | `response_id`, `generation_id` (constructor args to `stream_openai_chat_completion`) | `CancellationToken.is_cancelled` check exists in `StreamingResponseAssembler.run()`'s loop | none | **`cancellation_token` is never constructed or passed from `services/api` at all** — dormant since P5, exactly like `interrupt_active_response()` was dormant pre-P8 | Medium — task cancellation (P8) already stops consumption at the next await point in practice, but no defense-in-depth if that's ever insufficient |
| Assembler → `SpeakableChunk` | `response_id`, `generation_id`, `chunk_index` (self-assigned, `len(chunks)`, always monotonic per assembler instance) | none | n/a (self-assigned, structurally can't duplicate within one assembler run) | none | Low — a single assembler instance can't produce a duplicate/out-of-order index; risk is entirely about a *stale generation's* chunks reaching the coordinator, not index corruption |
| `on_chunk` → `coordinator.submit_speakable_chunk()` | `response_id`, `generation_id`, `chunk_index` all present on `SpeakableChunk` | **only `response_id`** checked, via `is_current()` | none | `is_current()` (response_id + non-terminal) | **Real gap**: `generation_id` on the chunk is never actually compared against `ctx.generation_id` — a same-response-id-but-different-generation chunk (not reachable today, but not structurally prevented either) would pass |
| `submit_speakable_chunk` → `TTSResponseHandle.send_chunk()` | response_id only (chunk text forwarded, index not passed to the provider layer in a way `tts_bridge.py` cross-checks) | none additional | none | none | Low today (already gated upstream), but no second gate |
| Text → `_text_queue` (enqueue) | response_id (`_TextQueueItem.response_id`) | none at enqueue | none | none | **Real gap** (spec §23): a chunk can be legitimately queued while its response is active, then become stale before `_run_sender` dequeues it — nothing re-validates at dequeue |
| `_text_queue` dequeue → `provider.send_text()` | response_id | none | none | none | Same gap, one level deeper — no check immediately before the provider call either |
| Provider audio → `TTSAudioChunk` | `response_id`, `audio_chunk_index` (self-assigned per response_id, per provider instance) | none at receipt | none | none | Low in isolation (self-assigned, monotonic per instance) |
| `TTSAudioChunk` → `_run_consumer` | response_id | **`pending.event.is_set()`** — already drops audio for a resolved/cancelled response (P6/P7, verified in P8's own tests) | none | Effectively yes, via the pending-event guard | **Already protected** — P9's job here is to add the duplicate-index safety net, not rebuild the stale guard |
| `_run_consumer` → `OutboundAudioChunk` | `response_sequence_id` = `TTSAudioChunk.response_id` | none | none | none | **Real gap**: the chunk built here carries no `ResponseIdentity`, no `generation_id`, no epoch — `_send_loop` (the very last hop) has nothing response-specific to check |
| `OutboundAudioChunk` → `outbound_queue` (enqueue) | as above | none | none | none | Same gap |
| `outbound_queue` dequeue → `_send_loop` → `websocket.send_json()` | **only `session.playback_state == PlaybackState.CLEARING`**, a session-wide boolean, not response-scoped | none response-specific | none | Weak — a TOCTOU race exists: `clear_agent_audio()` drains the queue and flips `playback_state` synchronously, but `_send_loop` is a concurrently-running task that could have already dequeued an item and be mid-send when the drain happens | **The most important gap** (matches spec's own §34 emphasis) — this is the true last-chance point before a customer hears something, and today it has no per-response ownership check at all, only a session-wide flag |
| `clear_agent_audio()` → Twilio `clear` message | n/a (control message) | n/a | n/a | n/a | None — already correct, drains queue + flips flag + sends clear synchronously |
| Mark ack → `PlaybackUnit` accounting | `mark_name` (unique per session, assigned at enqueue) | `_on_mark_acknowledged`'s CLEARED/ACKNOWLEDGED guard (P7, regression-tested) | Yes — duplicate-ack idempotency already fixed in P7 | Yes — a cleared unit can never be resurrected to ACKNOWLEDGED (P7, regression-tested) | **Already protected** — nothing to add here beyond confirming it under a P9-specific test |
| Clear → epoch | `self._clear_epoch` (P7) | increments on every clear, existing `PlaybackUnit`s flip SENT→CLEARED | n/a | Already correct for units that exist at clear time | Gap: nothing *before* `_apply_outcome()` runs (i.e., audio not yet turned into a `PlaybackUnit`) carries an epoch snapshot to compare against — see `OutboundAudioChunk` gap above |
| Greeting | **none at all** | **Not routed through the coordinator** — sent via `_send_pcm_reply()` directly from `_processing_loop`, unconditionally, regardless of `TTS_MODE` | none | none | **Confirmed, real bypass** — exactly the gap P8's own results doc flagged. This is the one deliberate hole in "every customer-facing audio boundary has ownership" |
| Batch-fallback reply (`speak_turn_reply`'s non-streaming path) | none | none | none | none | Low risk in practice (batch mode is non-interruptible, no coordinator exists in pure-batch calls) but no identity attached even when a coordinator *does* exist (streaming mode, TTS failed before any audio sent) |
| Closing response | Routes through the normal coordinator response path (`speak_turn_reply` with a `response_handle`) — **already covered** by whatever general protection P9 adds, no special-casing needed | — | — | — | Low — same mechanism as any other response; verified with a dedicated test rather than assumed |
| Stale `process_turn()` result (old turn) | `turn_id` exists on `UserTurnCommitted` and is threaded into `begin_response_feed(turn_id=...)` | **Not validated** — nothing checks "is this still the current turn" before a response is created from a completed `process_turn()` call | none | none | **Real gap** (spec §64-66): a slow/late engine result for a superseded turn could still create a new coordinator response today. In practice this requires the *previous* response's background task to still be running when a *second* commit fires — P8's own `_dispatch_commit()` safety net already interrupts a still-active previous response before starting a new one, which limits (but does not structurally prove) this |
| Tool result | `idempotency_key` includes `call_session_id` + a tool-call-specific suffix, but no `turn_id`/generation validation before its output is folded into `result.state` | none | n/a (tool execution itself is not replayed) | none | Low likelihood today (tool calls execute synchronously within one `process_turn()` invocation, no independent async re-entry point exists for a stale tool result to arrive out of band) — documented as structurally safe by construction, not defended by an explicit check |
| RAG result | Retrieval happens synchronously inside `process_turn()`, no speculative/prefetch-ahead-of-turn mechanism exists in this codebase | n/a | n/a | n/a | None — the spec's concern (speculative RAG contaminating a later turn) does not apply; no such mechanism exists to audit |

## What's already immutable / already correct (do not rebuild)

- `ActiveResponseContext.response_id`/`generation_id`/`sequence_id` — minted once in `begin_response()`,
  never reassigned for the lifetime of that context (confirmed by reading every mutation site in
  `coordinator.py`).
- `PlaybackUnit` PLAYED-vs-CLEARED accounting, duplicate-mark-ack idempotency, late-ack-after-clear
  rejection — all P7, all regression-tested, all correct today.
- Late TTS audio for an interrupted response never reaching `outbound_queue` — P6/P7's
  `pending.event.is_set()` guard, proven by P8's own `test_late_audio_chunk_after_interrupt_never_reaches_
  outbound_queue`.
- `submit_speakable_chunk()`'s `response_id`-based ownership check — correct as far as it goes; P9 extends
  it to also check `generation_id`, it doesn't replace it.
- Two-call isolation — each `RealtimePipelineCoordinator`/`RealtimeMediaSession` pair is a wholly separate
  object with its own dicts/counters; nothing today shares state across calls. P9 adds an explicit test
  proving this rather than assuming it.
- `session.close()` already cancels every `session.register_task()`-registered task, including P8's
  background response task — late-arriving async work after a call ends already can't resume a finished
  session's state machine (`InvalidSessionTransitionError` would raise on any attempted transition).

## What's genuinely new / the real gaps this phase closes

1. **No canonical `ResponseIdentity`** — five loose values (`call_id`, `turn_id`, `response_id`,
   `generation_id`, `sequence_id`) exist as separate fields on `ActiveResponseContext`, never bundled.
2. **`CancellationToken` is dormant in production** — built in P5, never constructed or passed by
   `services/api`. Exactly the "primitive exists, nothing calls it" pattern P7→P8 already went through once
   for `interrupt_active_response()`.
3. **`OutboundAudioChunk` carries no response identity or epoch** — the single most important gap. The
   final hop before a customer hears audio (`_send_loop`) has no response-specific ownership check, only a
   session-wide `playback_state` flag with a real TOCTOU race against the concurrent draining `clear_agent_
   audio()` performs.
4. **No output gate** — no single, final, centralized validation point immediately before
   `websocket.send_json()`. Today's only guard at that exact point is the `PlaybackState.CLEARING` check.
5. **No duplicate-chunk/duplicate-audio tracking** — self-assigned indices make accidental duplication
   unlikely in the current single-instance-per-response design, but nothing structurally prevents or even
   detects it if it ever happened (a provider bug, a future reconnect-mid-response change, etc.).
6. **No monotonic response/playback-unit state-transition table** — `ResponseState`/`PlaybackUnitState`
   transitions are enforced only by the specific methods that happen to set them today (e.g.,
   `_stop_response()` always sets a terminal state correctly), not by a centralized, independently-checked
   transition table the way `MediaSessionStatus` already has in `base.py`.
7. **No bounded terminal-response cache** — `coordinator._contexts` keeps every `ActiveResponseContext` for
   the life of the call (unbounded growth over a long call, though bounded by call duration/turn count —
   P7's own docs already flagged this as "not actively pruned this pass"). An artifact referencing a
   response ID that was *never* in `_contexts` at all (truly unknown, not just terminal) is currently
   indistinguishable from one that's simply stale — both get dropped the same way today via `is_current()`
   returning False for an unknown key, which is actually already fail-closed-correct; P9 formalizes this
   and adds explicit metrics distinguishing "known-stale" from "unknown."
8. **Greeting bypasses the coordinator entirely** — confirmed above, matches P8's own honest gap report.
9. **No `turn_id` staleness check before response creation** — `begin_response_feed(turn_id=...)` receives
   a turn_id but nothing validates it's still the call's current turn before creating a new response.
10. **No metrics for any of the above** — no `stale_*_dropped`, `duplicate_*_dropped`,
    `replay_attempt_blocked`, or `stale_audio_sent_total` counters exist yet.

## Scope note on tool/RAG staleness (spec §67-68, §118, §120)

Traced both execution paths in full: `execute_tool()` (called synchronously inside
`process_known_transcript_turn()`/`service.py`'s `handle_recording_webhook`, always awaited before the
turn's reply is computed) and RAG retrieval (also synchronous, inside `process_turn()`). **Neither has an
independent async re-entry point** — there is no code path in this repository where a tool result or RAG
result can arrive *after* the turn that requested it has already been superseded, because both are awaited
inline within the same `process_turn()` call that will use their output. The scenario the spec describes
(§67: "checking Sunday... customer changes to Monday... old Sunday tool result must not produce speech
automatically") would require a tool call that outlives its own turn — which does not exist in this
codebase today (no background/speculative tool prefetching, no async tool queue). This is documented here
as **structurally not applicable**, not silently skipped — if a future phase adds speculative/background
tool or RAG execution, *that* phase must add the staleness check this audit describes; P9 does not need to
build a guard for a mechanism that doesn't exist yet.

The one turn-level staleness gap that *is* real and addressed by P9: a **whole `process_turn()` call**
(not just its tool/RAG sub-steps) for an old, superseded turn returning late and creating a new response —
see gap #9 above.
