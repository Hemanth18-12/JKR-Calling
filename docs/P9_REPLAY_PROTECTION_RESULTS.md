# P9 — Strict Stale-Audio, Duplicate-Packet & Replay-Protection Hardening: Results

See `docs/P9_REPLAY_PROTECTION_AUDIT.md` (what existed before P9), `docs/RESPONSE_IDENTITY_MODEL.md` (the
identity model), `docs/REPLAY_PROTECTION_ARCHITECTURE.md` (the full design),
`docs/REALTIME_OUTPUT_INVARIANTS.md` (the eight invariants and the metric/event vocabulary). This doc
states what has and hasn't been verified, honestly — same practice as every previous phase.

## Baseline

**537 tests confirmed passing repo-wide** before any P9 code was written.

## Identity model

`ResponseIdentity` (`call_id`, `turn_id`, `response_id`, `generation_id`, `sequence_id`, `epoch`) — one
canonical, immutable structure, constructed on demand from `ActiveResponseContext`'s own fields (never
stored separately, can never drift). Two epochs, kept distinct: `response_epoch` (which generation is this
from) and `playback_epoch` (has a clear happened since — the formal name for P7's own `_clear_epoch`). See
`docs/RESPONSE_IDENTITY_MODEL.md` for the full reasoning, including why `sequence_id == response_id` and
why connection-generation identity (Sarvam's `request_id`, TTS reconnect generation) is deliberately kept
separate from response identity.

## The output gate

`RealtimePipelineCoordinator.can_send_media()` — the single final validation point, called from exactly one
place (`twilio_media_stream.py`'s `_send_loop`) immediately before every `websocket.send_json()`. Checks
call/response/generation/sequence/epoch/playback-epoch/duplicate-index, in that order, fails closed on any
unknown or mismatched identity, allows `identity=None` chunks (the documented legacy/batch-mode exception).
No network/DB call, no lock beyond plain dict/set membership. Kept as a genuine additional check even
though every producer upstream already validates ownership (defense in depth) — it closes a real TOCTOU
race the audit found between `clear_agent_audio()`'s synchronous queue-drain and `_send_loop`'s
concurrently-running dequeue.

## Stale protection, by boundary

| Boundary | Mechanism | Status |
|---|---|---|
| LLM delta | `StreamingResponseAssembler`'s `cancellation_token.is_cancelled` check (P5), now actually constructed/threaded end to end (was dormant before P9) | **Done, wired, tested** |
| LLM completion | Same token; a late completion for a cancelled generation can't reach `on_chunk` since the assembler loop already exited | **Done by construction** |
| `SpeakableChunk` | `is_current()` + assembler-generation consistency + chunk-index dup/conflict/gap | **Done, tested** (8 tests) |
| TTS text queue | Validated at enqueue (existing) AND at dequeue (new — `_run_sender`'s own stale check, a real gap the audit found and this phase fixed) | **Done, tested** (2 tests) |
| TTS send | Covered by the dequeue-time check immediately above (nothing enters `provider.send_text()` for a resolved response) | **Done, tested** |
| TTS audio | `pending.event.is_set()` (P6/P7, unchanged) + new audio_chunk_index dup/conflict/gap | **Done, tested** (4 tests) |
| TTS audio queue | Covered by the output gate at final dequeue | **Done, tested** |
| Twilio media envelope | `identity`/`playback_epoch` now present on every `OutboundAudioChunk` from a coordinator-owned path | **Done, tested** |
| Twilio queue enqueue | Existing ownership checks upstream already prevent enqueueing stale chunks in the normal case | **Done** (unchanged from P6/P7) |
| Twilio queue dequeue | The output gate — the most important boundary, see above | **Done, tested** |
| Marks | Duplicate-ack idempotency (P7) and stale-mark-ignored (CLEARED units never resurrected) generalized through `_transition_unit()` | **Done, tested** |
| Tool results | Traced in full; no independent async re-entry point exists in this codebase — structurally not applicable | **N/A, documented** |
| Engine results (stale turn) | `latest_committed_turn_sequence` guard in `_dispatch_commit()` | **Done** — defense in depth for a scenario the surrounding architecture already prevents structurally; not independently reproducible as a failing-without-the-fix test, honestly noted |
| RAG results | No speculative/prefetch mechanism exists in this codebase to have a staleness problem | **N/A, documented** |

## Duplicate protection

Text (`SpeakableChunk.chunk_index`), audio (`TTSAudioChunk.audio_chunk_index`), and Twilio media
(`OutboundAudioChunk.chunk_index`, at the output gate) each have their **own, independent** duplicate-index
tracking — three separate checks at three separate boundaries, not one check relied upon everywhere (spec's
own "defense in depth" framing, applied consistently). All three share the same pure, dependency-free
`identity.check_chunk_index()` function and the same documented policy: duplicate (same index, same
content fingerprint) is dropped silently and counted; conflict (same index, different fingerprint) and gap
(index ahead of expected) both fail the response rather than guess or reorder, since this implementation's
single-producer-per-generation design makes either scenario structurally anomalous, not a normal race.

## Clear epoch / PLAYED vs. CLEARED

Unchanged from P7, formalized: `playback_epoch` is the public name for `_clear_epoch`. `_on_playback_clear()`
increments it and flips every `SENT` unit to `CLEARED`; `_on_mark_acknowledged()`'s guard (now routed
through the same `_transition_unit()` every other playback-unit change goes through) makes a `CLEARED` unit
provably unable to become `ACKNOWLEDGED` later, and vice versa — both directions now enforced by an
explicit state table (`VALID_PLAYBACK_UNIT_TRANSITIONS`), not just by the two methods' own individual
guards.

## The greeting

**Now coordinator/output-gate controlled.** `_processing_loop`'s greeting-sending code routes through
`begin_response_feed()` + `speak_turn_reply()` — the identical path every other turn's reply already uses
— instead of calling the batch synthesis/send functions directly. This closes the one deliberate bypass
P8's own results doc flagged. The batch-fallback behavior (`TTS_MODE=batch`, no coordinator) is unchanged,
so cached-greeting latency is not regressed for that configuration.

## Chaos / property testing

`tests/voice/replay/test_replay_chaos.py`:
- **Randomized churn** (fixed seed, 40 cycles: begin_response → submit chunks → randomly interrupt/cancel/
  complete/supersede/clear-then-complete → drain every chunk through the real output gate) —
  `stale_audio_sent_total == 0` throughout, with both allowed and blocked sends genuinely exercised (not a
  vacuous pass).
- **Ten rapid interruptions back to back** — exactly one provider `cancel()` per response, ten genuinely
  fresh `response_id`s (never reused), zero stale sends.
- **A hundred rapid supersessions** — exactly 100 tracked contexts, 99 correctly terminal, no runaway
  fan-out — the cheap proxy for "no leaked state" this environment can run without a dedicated load-testing
  setup (a full concurrent-call load test remains out of scope, same honest gap P7 already flagged and this
  phase does not attempt to close).

## Real bugs found and fixed during this phase's own development (not by inspection)

1. **`SpeakableChunk.generation_id` vs. `ctx.generation_id`** — the first version of the chunk-identity
   check compared these directly and rejected every genuine LLM-streamed chunk, since
   `StreamingResponseAssembler` mints its own, unrelated `generation_id` per run. Caught by
   `test_p7_pipeline_integration.py`'s own concurrency-proof tests failing immediately. Fixed by tracking
   `ActiveResponseContext.assembler_generation_id` (first-seen-chunk consistency) instead of a direct
   cross-namespace comparison.
2. **The greeting-under-coordinator false interruption** — once the greeting became a real, always-present
   coordinator response, the customer's own first, unrelated utterance was being misclassified as
   "interrupting the greeting," because this implementation never advances an ordinary response's formal
   state past `GENERATION_COMPLETE` even after every chunk is acknowledged. Caught by
   `test_barge_in_pipeline_integration.py`'s existing end-to-end tests failing with an unexpected `clear`
   event. Fixed by refining `_agent_active_response()` to also check for outstanding unacknowledged audio
   or genuinely-still-producing state, not just "not terminal."

Both are documented in full in `docs/REPLAY_PROTECTION_ARCHITECTURE.md`'s own narrative, not just listed
here.

## Tests

**587 tests passing repo-wide, zero failures** (537 baseline + 50 net new, all in `services/api`):
184 `packages/conversation` + 32 `packages/db` + 337 `services/api` + 10 `services/voice-worker` + 13
`services/campaign-worker` + 11 `services/intelligence-worker`.

The 50 net-new tests, in `tests/voice/replay/`:
- `test_identity.py` (10) — `ResponseIdentity` immutability/equality, `check_chunk_index()`'s full decision
  table (accept/duplicate/conflict/gap, including the defensive "index below expected but never recorded"
  case).
- `test_coordinator_replay_protection.py` (30) — `is_identity_active()`'s full match/mismatch matrix
  (call/generation/epoch/terminal), `response_epoch`/`playback_epoch` incrementing correctly, the output
  gate's full decision table (legacy/unknown/current/stale/epoch-stale/duplicate/cross-call), response and
  playback-unit state-transition validation (including the terminal-states-only-self-loop table check),
  `SpeakableChunk` duplicate/conflict/gap/assembler-mismatch handling, `cancellation_token` cancellation on
  cancel/supersede, and queue-purge correctness (matching items removed, other responses' items untouched
  and reordered correctly).
- `test_tts_bridge_replay_protection.py` (7) — stale text purged proactively vs. dropped at dequeue (two
  independent guards, tested independently), duplicate/conflicting/gapped `TTSAudioChunk` handling,
  identity/playback_epoch correctly stamped, the `identity=None` legacy fallback.
- `test_replay_chaos.py` (3) — the randomized-churn, rapid-interruption, and rapid-supersession property
  tests described above.

Also extended: `test_barge_in_pipeline_integration.py`'s existing real end-to-end WebSocket interruption
test now also asserts `stale_audio_sent_total == 0`, tying the coordinator-level unit-test guarantees to
the actual `_send_loop` wiring through a real (simulated) Twilio connection.

## Real phone status

**NOT TESTED.** This environment cannot place an actual authorized Twilio phone call. `BARGE_IN_ENABLED`
remains `false` by default (unchanged from P8) — P9 does not change this. Replay-protection guards
themselves (the output gate, duplicate/conflict detection) are **always-on**, not gated behind any flag,
per this phase's own explicit instruction (§152-153: "stale output guards are correctness safeguards...
should become always-on," "always block stale output... debug flag controls raise/assert only"). No
`STRICT_REALTIME_INVARIANTS` assertion-mode flag was added this pass — every violation found is logged and
counted, never raised, in every environment including tests; this satisfies the spec's own "block + log +
metric, don't crash production" default without needing a separate flag to toggle between two behaviors
that were never actually built to differ.

## Remaining limitations, stated explicitly

- **No dedicated `STRICT_REALTIME_INVARIANTS` assertion-mode flag.** All violations are logged/counted,
  never raised, in every environment. Spec allows this as the default and only asks for an *optional*
  stricter dev/test mode — not built this pass since every test already asserts on the counters/log events
  directly, which serves the same verification purpose without a second code path to keep in sync.
- **No dedicated replay-debug UI panel.** The event log (`docs/REALTIME_OUTPUT_INVARIANTS.md`'s vocabulary)
  is the trace, same posture P8 already took for its own barge-in observability.
- **No real concurrent-call load test** (20-50 simulated calls under chaos injection, spec §135). The
  three-test chaos suite proves the invariant holds under randomized single-call churn; a genuine
  multi-call, multi-connection load test remains the same honest gap P7's own results doc already flagged
  and P9 does not attempt to close.
- **`stale_turn_result_dropped` is unverified by a dedicated failing-without-the-fix test** — the scenario
  it guards against is not constructible given this codebase's current, fully-synchronized call patterns
  (see the audit's own conclusion). The guard exists and is cheap; its necessity is currently theoretical.
- **No Twilio-stream-generation counter** — no reconnect-to-a-new-Twilio-stream mechanism exists in this
  architecture to protect against; not fabricated for a hypothetical.
- **Tool/RAG staleness guards were not built** — traced in full and found structurally not applicable
  (neither has an independent async re-entry point today); a future phase that adds speculative/background
  tool or RAG execution must add this guard itself.

## Definition-of-done, honestly marked

Every numbered item in the spec's own 63-point definition-of-done (§178) that describes a mechanism this
codebase's architecture can currently exercise is **done and tested**: canonical immutable
`ResponseIdentity`, ownership on every artifact that can carry it, call/generation/sequence/connection-
generation enforcement, response and playback-clear epochs, LLM/SpeakableChunk/TTS-text/TTS-audio/Twilio-
media stale and duplicate checks at enqueue AND dequeue where applicable, the single final output gate
fail-closed on unknown identity, playback-unit identity scoping, duplicate-mark idempotency, clear-epoch
cross-response protection, terminal-response/monotonic-state enforcement, the greeting brought under
ownership, purge-on-invalidation with metrics, the full metrics/event vocabulary, randomized and repeated-
interruption tests, bounded-growth verification, hot-path-cheap validation (no network/DB in
`can_send_media()`), and a clean 587-test/ruff/mypy sweep. Items describing mechanisms that don't exist in
this codebase (tool/RAG speculative staleness, Twilio stream reconnection, a real multi-call load test) are
marked N/A or explicitly deferred above, not silently claimed done. No automatic git commit occurred.
