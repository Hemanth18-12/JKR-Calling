# P9 — Replay Protection Architecture

See `docs/P9_REPLAY_PROTECTION_AUDIT.md` (what existed, what was found), `docs/RESPONSE_IDENTITY_MODEL.md`
(the identity model in depth), `docs/REALTIME_OUTPUT_INVARIANTS.md` (the invariants and vocabulary this
architecture enforces), and `docs/P9_REPLAY_PROTECTION_RESULTS.md` (what shipped, tested, honestly not
done).

## The one-sentence goal

**Only the current active response may produce customer-facing audio — and this must be true by
architecture, not merely likely because cancellation usually works in time.**

## The chain, and where each check lives

```
OpenAI SSE delta
  -> StreamingResponseAssembler.run()     [checks: ctx.cancellation_token.is_cancelled, every loop iteration]
  -> SpeakableChunk
  -> coordinator.submit_speakable_chunk() [checks: is_current(), assembler-generation consistency,
                                            chunk_index duplicate/conflict/gap]
  -> TTSResponseHandle.send_chunk()
  -> TTSStreamingSession._text_queue      [checks, at DEQUEUE: pending.event.is_set() — stale-at-dequeue]
  -> provider.send_text()
  -> provider audio event (TTSAudioChunk) [checks: pending.event.is_set(), audio_chunk_index duplicate/
                                            conflict/gap]
  -> OutboundAudioChunk (identity + playback_epoch attached here)
  -> RealtimeMediaSession.outbound_queue  [purged proactively on cancel/supersede/interrupt]
  -> _send_loop                           [THE OUTPUT GATE: coordinator.can_send_media(), immediately
                                            before websocket.send_json() — the single final boundary]
  -> Twilio WebSocket
```

Every arrow above is a boundary the audit traced individually (`docs/P9_REPLAY_PROTECTION_AUDIT.md`'s own
table). What's new in P9 is annotated in brackets; what's unannotated (provider audio's own
`pending.event.is_set()` guard, `PlaybackUnit` PLAYED/CLEARED accounting, duplicate-mark-ack idempotency)
was already correct from P6/P7/P8 and is unchanged.

## The output gate — `RealtimePipelineCoordinator.can_send_media()`

The single, final validation point, called from exactly one place (`twilio_media_stream.py`'s
`_send_loop`), immediately before `websocket.send_json()`:

```python
def can_send_media(self, chunk: OutboundAudioChunk) -> OutputGateDecision:
    if chunk.identity is None:
        return OutputGateDecision(True, "legacy_no_identity")
    if identity.call_id != self._call_session_id: -> "call_mismatch"
    if identity.response_id not in self._contexts: -> "unknown_response"
    if not self.is_identity_active(identity): -> "stale_response"
    if chunk.playback_epoch != self._clear_epoch: -> "playback_epoch_stale"
    if chunk.chunk_index in ctx.sent_media_chunk_indices: -> "duplicate_media"
    ctx.sent_media_chunk_indices.add(chunk.chunk_index)
    return OutputGateDecision(True, "ok")
```

**Deliberately kept even though every producer upstream already checks ownership** (spec §78, "defense in
depth... never remove it as redundant"). This is not decorative: it closes a real TOCTOU race the audit
found — `clear_agent_audio()` drains `outbound_queue` and flips `playback_state` *synchronously*, but
`_send_loop` is a concurrently-running task that could already have dequeued an item and be mid-send when
that happens. The gate re-checks with **live** coordinator state at the last possible moment, which a
queue-drain-time-only check structurally cannot do.

**No network call, no DB, no lock beyond plain dict/set membership** (spec §79-80) — everything it reads is
call-local, in-process state already sitting on the coordinator.

**The legacy-path exception is real and intentional, not a bypass** (spec §161): `chunk.identity is None`
only ever happens for the pure `TTS_MODE=batch` path (no coordinator, no ownership model exists to check
against). Every path that *does* have a coordinator — including the greeting, as of this phase (see below)
— always attaches an identity, so this branch is never reachable for a call that has replay protection
available to it in the first place.

## `OutboundAudioChunk` carries identity now

`base.py`'s `OutboundAudioChunk` gained two fields: `identity: ResponseIdentity | None = None` and
`playback_epoch: int = 0`. Deliberately **not** renamed to a new `OutboundAudioEnvelope` type (the spec's
own `§76` example) — this class already accurately describes what it is, and extending it in place avoided
touching every call site's type annotations for a purely cosmetic rename with no functional benefit. Two
producers exist, both now stamp identity when a coordinator is attached:

- **`tts_bridge.py`'s `_run_consumer`** — `TTSStreamingSession.begin_response()` now accepts
  `identity`/`playback_epoch`, stored on `_PendingResponse`, stamped onto every `OutboundAudioChunk` it
  builds.
- **`twilio_media_stream.py`'s `_send_pcm_reply`** — accepts the same two parameters (default `None`/`0`,
  preserving every existing call site unchanged); `speak_turn_reply()`'s own batch-fallback branch and the
  now-coordinator-routed greeting both pass them through when a coordinator response exists.

`mark_name` doubles as this chunk's `playback_unit_id` (spec §41/§76) — already unique per call, already
assigned before enqueue (P6), no second ID was minted.

## Duplicate/conflict/gap detection — one shared, pure function

`identity.check_chunk_index()` — shared by the `SpeakableChunk` boundary (`coordinator.py`'s
`submit_speakable_chunk`) and the `TTSAudioChunk` boundary (`tts_bridge.py`'s `_run_consumer`), same shape,
written once:

- **DUPLICATE** (same index, same content fingerprint) → dropped silently, counted, benign.
- **CONFLICT** (same index, different fingerprint) → upstream corruption. The response is failed
  (`coordinator.cancel_response()` for text; `pending.failed = True` for audio) rather than guessing which
  copy is real.
- **GAP** (index ahead of what's expected) → also treated as corruption and fails the response, not
  buffered for reordering. This implementation's single-producer-per-generation design (both
  `SpeakableChunk.chunk_index` and `TTSAudioChunk.audio_chunk_index` are self-assigned, strictly
  sequential counters — see the audit) makes a genuine gap structurally anomalous, not a normal race; a
  reorder buffer for a scenario that cannot occur in normal operation would be complexity with no payoff.
  Documented choice, not an oversight (spec §21-22 explicitly allows either strategy as long as it's
  written down).

Fingerprints are cheap and non-cryptographic: `hash(text)` for text, `(len(data), first/last 32 bytes)`
hashed together for audio — spec §29's own explicit caution against cryptographic hashing on this hot path.

**A real bug found here during development**: the first version compared `SpeakableChunk.generation_id`
directly against the coordinator's own `ctx.generation_id` and rejected every mismatch — but
`SpeakableChunk.generation_id` is minted by `StreamingResponseAssembler.run()` itself, a completely
different namespace, *never* equal to the coordinator's `generation_id` by design. This silently dropped
**every genuine LLM-streamed chunk**, caught immediately by `test_p7_pipeline_integration.py`'s own
concurrency-proof tests failing. Fixed by tracking `ActiveResponseContext.assembler_generation_id`
(recorded from the *first* accepted chunk, checked for consistency on every later one) instead — which
still catches a genuine "two different assembler runs' chunks got mixed into one response" bug, without the
wrong assumption. See `docs/P9_REPLAY_PROTECTION_RESULTS.md` for the full incident writeup.

## Response/playback-unit state transitions are now centrally validated

`VALID_RESPONSE_STATE_TRANSITIONS` / `VALID_PLAYBACK_UNIT_TRANSITIONS` — explicit tables, same pattern
`base.py`'s `MediaSessionStatus` already used for the Twilio protocol state machine. Every `ctx.state = X`
assignment in `coordinator.py` now goes through `_transition()`, which checks the table: a transition out
of any terminal state is rejected (logged, counted, **never raised** — spec §93, a production call must
never crash over an invariant violation) except the idempotent self-loop (`INTERRUPTED -> INTERRUPTED`
is a no-op, not an error — spec §58). This is what makes "no stale task revival" (spec §55) a checked
invariant rather than an implicit property of "every call site happens to already do the right thing."

## Atomic invalidation, and the `CancellationToken` wiring

`_stop_response()` (the shared plumbing `cancel_response()`/`supersede_response()`/
`interrupt_active_response()` all funnel through) does two things **synchronously, before any `await`**:
transitions `ctx.state` to the target terminal state, and calls `ctx.cancellation_token.cancel()`. Spec
§10's "atomic invalidation" made literal — not after provider cancellation finishes, not after queues
drain.

`CancellationToken` (P5) was a genuinely dormant primitive before this phase — built, checked every loop
iteration inside `StreamingResponseAssembler.run()`, but **never constructed or passed by `services/api`
at all**. `ActiveResponseContext` now owns one (`field(default_factory=CancellationToken)`); `ResponseFeed`
exposes it; `transitional_bridge.py`'s `process_known_transcript_turn()`/`process_transitional_turn()` and
every one of their call sites now thread it into `process_turn(cancellation_token=...)`. In practice, P8's
own task-cancellation already stops LLM consumption at the next `await` point in the common case — this
wiring is genuine defense in depth (an explicit, checked-every-iteration flag, independent of whether the
surrounding asyncio task is ever literally cancelled), closing a "primitive exists, nothing calls it" gap
of exactly the kind P7→P8 already closed once for `interrupt_active_response()`.

## Proactive queue purging

Spec §85-89. On every `_stop_response()` call: `RealtimeMediaSession.purge_outbound_for_response()` drains
`outbound_queue`, removes items matching the stopped response's `response_sequence_id`, and puts everything
else back in order — synchronous, non-blocking, never touches another response's items
(`test_purge_outbound_removes_matching_and_keeps_others_in_order`). `TTSStreamingSession` does the
equivalent for `_text_queue` inside `_mark_pending_cancelled()`. Both purges are a memory/backlog
optimization on top of the already-authoritative lazy checks (the output gate, the dequeue-time text
check) — never the only thing standing between a stale item and Twilio.

## The greeting is now coordinator-owned

Spec §70-72/§154-155. `_processing_loop`'s greeting-sending code now calls `begin_response_feed()` +
`speak_turn_reply()` — the exact same path every other turn's reply already uses — instead of calling
`synthesize_for_stream()`/`_send_pcm_reply()` directly. This closes the one deliberate bypass P8's own
results doc flagged. Reusing `speak_turn_reply()` unchanged means the batch-fallback branch (no coordinator,
`TTS_MODE=batch`) keeps working exactly as before — no latency regression for that configuration, and no
new code path to get wrong.

**A second, more subtle bug this surfaced and fixed**: `streaming_bridge.py`'s `_agent_active_response()`
(the gate for whether customer speech should even be evaluated as a potential interruption) originally
returned "active" for any non-terminal response — but this implementation never advances an *ordinary*
(non-closing) response's formal state past `GENERATION_COMPLETE`, even once every chunk has been
acknowledged. Once the greeting became a real, always-present coordinator response, this meant the
customer's own first, completely unrelated utterance was being misclassified as "interrupting the
greeting" — caught by this phase's own end-to-end WebSocket integration test failing (a real `clear` event
firing where none should), not by inspection. Fixed by additionally checking whether the response is
genuinely still producing (`_STILL_PRODUCING_STATES`) or has unacknowledged audio outstanding
(`audio_ms_acknowledged < audio_ms_sent`) before treating it as "still active" for interruption-candidate
purposes. See `docs/P9_REPLAY_PROTECTION_RESULTS.md` for the full incident writeup — this is the second of
two real bugs this phase's own testing caught, not invented after the fact.

## Turn-level staleness

`_dispatch_commit()` now tracks `latest_committed_turn_sequence` and rejects (logs, counts) any commit for
an older turn than one already processed. Documented honestly as **defense in depth for a scenario already
structurally prevented** by `TurnManager`'s own serialized signal processing and `_dispatch_commit`'s
existing safety net (a still-running previous response task is always resolved before a new one starts,
when barge-in is on) — not a mechanism this codebase's actual call patterns can currently exercise, per the
audit's own honest conclusion.

## What's explicitly out of scope, and why

- **Tool/RAG result staleness** (spec §67-68/§118/§120) — traced in full in the audit; neither has an
  independent async re-entry point in this codebase (both are awaited inline within the same `process_turn()`
  call that uses their output). Structurally not applicable, not silently skipped.
- **Twilio stream reconnection generation** (spec §62) — no such reconnect mechanism exists for the Twilio
  leg in this architecture (unlike STT/TTS, which do reconnect independently and already have their own
  generation isolation). Not fabricated for a mechanism that doesn't exist.
- **Adaptive brevity, goodbye-during-closing** (spec §73-74) — explicitly out of P9's own scope per the
  spec itself; untouched.
