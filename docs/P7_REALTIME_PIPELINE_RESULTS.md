# P7 — Realtime Pipeline Coordination: Results & Verification Status

See `docs/P7_REALTIME_PIPELINE_AUDIT.md`, `docs/REALTIME_PIPELINE_COORDINATOR.md`, `docs/
PLAYBACK_ACCOUNTING.md`, `docs/BACKPRESSURE_ARCHITECTURE.md`. This doc states what has and hasn't been
verified, honestly — same practice as every previous phase.

## Real phone baseline

**NOT TESTED.** This environment cannot place an actual authorized Twilio phone call (no interactive
telephony access). Stated plainly per this phase's own explicit instruction for this exact situation,
rather than invented. See "Manual verification plan" below for what the user should run.

## P6 baseline — result

463 tests confirmed passing repo-wide before any P7 code was written.

## What shipped

- **`RealtimePipelineCoordinator`** (`transport/coordinator.py`) — one per call, the single authority
  for which response owns the call's audio. `ResponseState` lifecycle (11 states, 4 terminal),
  `ActiveResponseContext` (distinct generated/committed/sent/acknowledged tracking, never one ambiguous
  boolean), ownership-checked `submit_speakable_chunk()`, automatic supersede-on-`begin_response()`,
  explicit `cancel_response()`/`supersede_response()` with the CANCEL-vs-SUPERSEDE distinction spec §11
  asks for.
- **`PlaybackUnit`** model — one per audio chunk actually sent to Twilio (the precisely-trackable
  granularity; see `docs/PLAYBACK_ACCOUNTING.md` for why this differs from the spec's literal
  per-SpeakableChunk framing), mapped to marks, with a genuine **PLAYED vs. CLEARED** distinction backed
  by real clear-epoch bookkeeping — not just an enum value that's never actually differentiated.
- **`InterruptionSnapshot`** + `interrupt_active_response()` — the clean P8 entry point, tested and
  working today, wired to nothing automatic yet.
- **`begin_response_feed()`/`CoordinatedResponseHandle`** — every streaming response (LLM-generated or
  locally-chunked canned/fast-path text) now routes through the coordinator; `speak_turn_reply()`
  (P6) needed zero changes because the new handle is duck-type-compatible with the old one.
- **A real, found-and-fixed ownership desync bug**: the coordinator's first implementation reached
  directly into `TTSStreamingSession`'s private provider, bypassing its own bookkeeping — fixed by
  extracting `TTSStreamingSession.cancel_response()` as a proper shared method both layers call.
- **A real, found-and-fixed double-counting bug**: `_on_mark_acknowledged` only guarded against a
  CLEARED unit, not an already-ACKNOWLEDGED one — a redelivered mark event would have double-counted
  `audio_ms_acknowledged`. Fixed, with a regression test.
- **Bounded TTS reconnect between responses** (`TTSStreamingSession`) — idle-only (never mid-response,
  spec §144), generation-isolated (a fresh provider instance per attempt, `_connection_generation`
  incremented on success), with both a per-cycle attempt cap (`MAX_TTS_RECONNECT_ATTEMPTS=2`) **and** an
  overall cycle cap (`MAX_TTS_RECONNECT_CYCLES=3`).
- **A real, found-and-fixed infinite-loop bug**: the first reconnect implementation only bounded
  attempts *within* one reconnect cycle — a provider that connects successfully but whose connection
  immediately drops again would trigger unbounded successful-reconnect-then-immediate-failure cycles.
  Caught by the test suite hanging (not by inspection), fixed with the overall cycle cap, verified by
  `test_reconnect_cycles_are_bounded_not_infinite`.
- **`VoicePersona.speaking_speed` → Sarvam `pace`** — resolved via a new `_resolve_tts_pace()` (mirrors
  `_resolve_tts_speaker()`'s existing gating: only for a persona actually configured for Sarvam),
  clamped to `bulbul:v3`'s verified 0.5-2.0 range, threaded through `redis_state["tts_pace"]` exactly
  like `tts_speaker` already is.
- **Fixed the one unbounded hot-path queue found in the audit**: the streaming-STT event queue in
  `streaming_bridge.py` had no `maxsize` — given a defensive 100-item bound.
- **Event-loop lag monitoring** (`event_loop_lag.py`) — process-wide, started via FastAPI's `lifespan`,
  exposed on `/health`.
- **Dead-air classification** (`classify_dead_air()`, `coordinator.dead_air_status()`) — pure,
  on-demand, stage-reporting; no automatic filler injection, no live polling task wired up yet (see
  `docs/BACKPRESSURE_ARCHITECTURE.md`'s honest scoping note).

## Verified — unit and targeted integration tests, all real, all passing

**247 tests in `services/api`** (213 baseline + 34 net new), unchanged elsewhere (184
`packages/conversation` + 32 `packages/db` + 10 `services/voice-worker` + 13 `services/campaign-worker` +
11 `services/intelligence-worker`) — **497 tests passing repo-wide, zero failures.**

The 34 net-new tests, by file:
- `test_coordinator.py` (23) — lifecycle state transitions, ownership (current vs. stale response
  dropped), supersede (auto and explicit, provider cancel actually fired), cancel (direct, and
  correctly a no-op once terminal), mark-ack accounting (state + `audio_ms_acknowledged`), **duplicate
  mark-ack idempotency** (the bug above), **clear vs. played** (the core PLAYED/CLEARED distinction,
  including a late ack after clear provably not flipping the state back), `InterruptionSnapshot`
  correctness, dead-air boundary classification + stage reporting, backpressure snapshot, `begin_response
  _feed()` wiring, and two-coordinator isolation (mark names legitimately collide across calls — each
  session has its own counter — but accounting never leaks between them).
- `test_tts_reconnect.py` (6) — no-factory-configured means no reconnect attempted (pre-P7 behavior
  preserved exactly), successful idle reconnect resumes from the new provider, connection-generation
  counter increments, **no reconnect attempted mid-response** (spec §144), **bounded cycles, not
  infinite** (the bug above — this test would have hung the suite before the fix), all-attempts-fail
  gives up cleanly.
- `test_event_loop_lag.py` (5) — zero baseline, samples collected once started, idempotent start,
  safe stop-before-start, and a deliberate synchronous block produces a measurable lag spike.
- `test_p7_pipeline_integration.py` (2) — the concurrency proof (spec §149-150): real
  `StreamingResponseAssembler` + real `SpeakableChunker` + real `RealtimePipelineCoordinator` + real
  `TTSStreamingSession` + a real `RealtimeMediaSession`'s real outbound queue, with only the LLM token
  stream and the Sarvam TTS WebSocket faked. One test measures that the first Twilio-bound audio arrives
  measurably *before* the LLM's own full-generation time; the other samples the pipeline's live state
  mid-LLM-stream and asserts TTS has *already* produced Twilio-bound audio and the coordinator is
  already in `TTS_STREAMING` — not still waiting on the LLM. **Both fake providers in this test
  themselves needed two real fixes during development** (the fake TTS provider only produced audio on
  `flush()`, not `send_text()`, contradicting Sarvam's actual verified behavior; and it never emitted a
  completion event at all, which would have hung on the real 30s timeout) — left as a reminder that even
  test doubles benefit from checking them against the verified contract, not just "does it look
  plausible."

Net test delta accounts for removing 2 tests from `test_tts_bridge.py` that tested the OLD (pre-move)
`begin_response_feed()` location, superseded by the more thorough coordinator-level tests above.

## What is honestly NOT done

- **No real phone call.** See above.
- **Playback lookahead is measured, not enforced** — `twilio_playback_backlog_ms` is a real, tested
  number; nothing currently pauses TTS→Twilio forwarding when it gets large. See `docs/
  BACKPRESSURE_ARCHITECTURE.md`.
- **No live dead-air polling/alerting task** — the classification function and on-demand check are real
  and tested; nothing calls them periodically or surfaces a warning automatically yet.
- **No load test** (spec §117-119: 1/10/25/50/100 concurrent simulated calls, artificially slowed
  consumers). This environment has no realistic way to generate meaningful concurrent-call load or
  measure resource behavior under it beyond what the unit/integration suite already exercises
  single-call. A real gap, not attempted this pass rather than faked.
- **No orphan-task/memory-leak repeated create/destroy test** (spec §115-116) — plausible given `close()`
  cancels all registered tasks and the coordinator's own `close()` cancels the active response, but not
  independently verified via a repeated-cycle test.
- **P8/P9 remain not started** — `interrupt_active_response()` exists and works; nothing calls it
  automatically. Stale/duplicate-sequence rejection beyond `is_current()`'s response-id check does not
  exist.

## Manual verification plan (once the user is ready)

1. Use the staging flags: `TWILIO_VOICE_TRANSPORT=media_stream`, `STT_MODE=streaming`,
   `TURN_DETECTION_MODE=hybrid`, `CONVERSATION_ENGINE_MODE=fast`, `LLM_RESPONSE_MODE=streaming`,
   `TTS_MODE=streaming` — unchanged from P6's own recommended combination; P7 adds no new required flag
   (the coordinator activates automatically whenever `TTSStreamingSession` does).
2. Place one authorized test call through the full scripted sequence from this phase's own spec
   (`"Root canal cost entha?"`, a mid-sentence correction, a language switch, etc.) and pull the
   `pipeline_response_*`/`tts_response_*`/`tts_reconnect_*` event log for that call.
3. Confirm: exactly one `pipeline_response_begin` per customer turn, no unexpected
   `pipeline_response_superseded` events (would indicate two responses racing — shouldn't happen in
   normal single-turn-at-a-time operation), and `/health`'s `event_loop_lag_ms` stays low throughout.
4. Listen for the same things P6's own plan asked for (dead air, chunk seams, closing behavior) — P7
   should not perceptibly change audio quality or timing versus P6, since it adds accounting/ownership,
   not new audio processing.

## Definition-of-done, honestly marked

Coordinator exists and is the single ownership authority — **done**. Response lifecycle, LLM/TTS/media
ownership centralized — **done**. `PlaybackUnit` model, marks mapped to units, clear correctly
classified — **done, tested**. Generated/sent/acknowledged distinct — **done**. Queue inventory, bounded
hot-path queues — **done** (the one gap found is fixed). Text/audio backlog measurable — **done**.
Twilio playback backlog *estimated* — **done**; lookahead *enforcement* — **not done**. Backpressure
behavior explicit for the queues that exist — **done**; a formal `BLOCK`/`PAUSE_UPSTREAM`/`DROP_STALE`/
`FAIL_RESPONSE` policy table per queue — implicit in the queue inventory table, not a separate enum in
code. Dead-air classification exists and is observable — **done**; automatic polling — **not done**.
Event-loop lag measured — **done**. Call disconnect cancels active pipeline work, idempotent — **done**
(`RealtimePipelineCoordinator.close()` + existing `RealtimeMediaSession.close()`). TTS idle reconnect +
generation isolation — **done, tested**, including catching and fixing a real infinite-loop bug.
`speaking_speed` wired — **done, tested**. Closing waits for playback completion, duplicate-closing fix
preserved — **done** (unchanged from P6, `wait_playback_complete()` is additive). Multi-call isolation —
**tested**. Slow-TTS/slow-Twilio/mark-delay/manual-clear/supersede/cancel-before/cancel-after tests —
**done**. Full realtime integration test with a genuine concurrency proof — **done**. Load test, orphan-
task test — **not done**, explicit gaps. Ruff/mypy — **clean** on every touched/new file. No automatic
git commit — **honored**.

## What's still unfinished after P7 (restated, per spec §160)

```
P3:   Streaming STT                        — DONE
P3.5: Conversation fast paths               — DONE
P4:   Turn detection                        — DONE
P5:   Streaming LLM                         — DONE
P6:   Streaming TTS                         — DONE
P7:   Pipeline coordination/backpressure    — DONE (coordination/accounting layer; lookahead
                                                enforcement and load testing explicitly not done)
P8:   Automatic barge-in                    — NOT DONE (interrupt_active_response() exists as the
                                                primitive; nothing calls it from user speech yet)
P9:   Strict replay/stale-audio enforcement — NOT DONE (is_current() ownership checks exist; no
                                                cryptographic/sequence-based rejection beyond that)
```
