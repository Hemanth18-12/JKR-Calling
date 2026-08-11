# P4 — Turn Detection: Results & Verification Status

See `docs/P4_TURN_DETECTION_AUDIT.md` (what P4 replaces) and
`docs/TURN_DETECTION_ARCHITECTURE.md` (what shipped and why) for full context. This doc is
deliberately explicit about what has and hasn't been verified — per this phase's own §118 instruction
not to claim P50/P95 from a handful of measurements, and this session's established practice of
never claiming a real-call result that wasn't actually run.

## What shipped

- `services/api/app/modules/live_call/turns/` — a provider-neutral `TurnManager`, an explicit turn
  state machine, a normalized signal model, a rule-based `SemanticCompletenessEvaluator`, a
  context-aware `BackchannelClassifier`, a local `EnergyVAD` (RMS-energy, zero new dependencies —
  no Silero/ONNX/LiveKit package exists anywhere in this repo, confirmed before writing any code),
  and process-wide metrics.
- `streaming_bridge.py` rewired so a Sarvam `FinalTranscript` no longer directly invokes
  `ConversationEngine` — it becomes an `STT_FINAL` signal to `TurnManager`; only a `COMMIT_TURN`
  decision reaches `_commit_turn_to_engine()`. `provider` mode (default) reproduces this
  synchronously, every time, so behavior is byte-identical to P3.
- Also fixed while wiring this in: Sarvam's `SpeechEnded` event was previously received and silently
  dropped (confirmed in the audit) — now feeds `TurnManager` as `PROVIDER_SPEECH_END`.
- `TURN_DETECTION_MODE=provider|vad|hybrid`, `TURN_PROFILE=fast|balanced|patient`,
  `LOCAL_VAD_ENABLED` — all default to pre-P4 behavior (`provider`), never auto-enabled.

## Verified so far (unit level — real, deterministic, fake-clock, no DB needed)

68 new tests, all passing:

- `test_turns_semantic.py` (10) — every completeness rule, including the "no punctuation ≠
  incomplete" default-direction guard.
- `test_turns_backchannel.py` (6) — context-aware classification both ways.
- `test_turns_vad.py` (6) — `EnergyVAD` state-transition-only signal emission, no duplicate starts
  while continuously speaking, reset behavior.
- `test_turns_manager.py` (18) — the full state machine: provider-mode immediate commit (2), thinking-
  pause coalescing (spec §58), incomplete-clause patience (§59), prompt commit on a complete question
  (§60), number-sequence and code-mix pause coalescing (§61/§62), max-endpoint-timeout forced commit
  (§69), user-resume cancels a pending commit (§70), two genuinely separate turns not over-coalesced
  after a commit (§71), backchannel context-awareness both directions (§64/§65), empty-final and
  VAD-silence-with-no-transcript handling (§42/§43/§66), fragment coalescing across a short gap and
  NOT coalescing across a large one (§67/§26/§71), and the anchor-independence check proving
  `max_endpoint_delay` is measured from the *first* possible-end, not the most recent final.
- `test_streaming_bridge.py`/`test_sarvam_streaming_stt.py` (68 total across both, re-run after the
  rewrite) — zero regressions in the P2/P3 reconnect/failure-policy/dedup logic this phase built on.

A real design bug was caught and fixed *during* this verification, not before it: an early version of
`on_timer_tick` had `min_endpoint_delay`, `max_endpoint_delay`, and `thinking_pause_extension` as
three independently-competing commit triggers — `thinking_pause_extension` (smaller in every preset)
always fired first, making `max_endpoint_delay` dead code. Three of the first 40 unit tests failed
against this, which is what surfaced it. Fixed to the additive model documented in
`TURN_DETECTION_ARCHITECTURE.md`'s "Timing model" section — this is exactly the kind of thing
fake-clock unit tests are for, and it worked as intended.

## NOT yet verified — Docker was unavailable for this pass

`services/api/tests/test_turn_detection_integration.py` was written (two tests: hybrid-mode
thinking-pause coalescing produces exactly one `CallTurn` end-to-end through the real WebSocket →
`RealtimeMediaSession` → `TurnManager` → `ConversationEngine` pipeline; provider-mode default is
unaffected) but **could not be run** — the Docker daemon was not running on this machine during this
session (confirmed via `docker compose ps` failing with "Cannot connect to the Docker daemon", not a
container-level issue). The equivalent P3 integration tests (`test_streaming_stt_integration.py`,
`test_twilio_media_stream_integration.py`) also failed for the same reason when re-run, confirming
this is an environment gap, not a P4 regression.

**This must be run before P4 is considered verified.** Once Docker is available:

```bash
docker compose up -d postgres redis minio
PYTHONPATH=services/api uv run --package jkr-api pytest services/api/tests -q
```

All 68 new unit tests plus the full existing 311+ should pass; the two new integration tests are the
direct proof of the coalescing behavior working through the real stack, not just in isolation.

## NOT done — real-call verification

No real phone call has been placed with `TURN_DETECTION_MODE=hybrid`. No latency numbers (`vad_start_
latency_ms`, `turn_commit_latency_ms`), no premature-split rate, no Telugu/Hindi/English benchmark
results exist. `docs/P4_TURN_DETECTION_AUDIT.md`'s "current endpoint delay" baseline (Sarvam's own
`silence_duration_ms=500` default, unmeasured against real PSTN audio) has not been compared against
a hybrid-mode measurement on a real call. `.env` has `TURN_DETECTION_MODE` unset (defaults to
`provider`) — not flipped live, same reasoning as every previous phase: this changes the actual
decision path for when the agent responds, and shouldn't be enabled without the user's own test call.

**Manual verification plan** (per spec §115-116, to run once Docker/DB are back and this has been
smoke-tested with a real call):
1. Set `TWILIO_VOICE_TRANSPORT=media_stream`, `STT_MODE=streaming`, `TURN_DETECTION_MODE=hybrid`,
   `TURN_PROFILE=balanced` in `.env`.
2. Place one authorized test call. Say, in order: "Tomorrow evening." / "Tomorrow... actually evening
   better." / "Root canal... actually crown." / "My rank is... twenty eight thousand." / "Root canal
   cost entha?" / a short yes/no reply to a confirmation question.
3. For each utterance, pull `call_events`/`call_latency_metrics` for that call (same diagnostic
   pattern used for every previous real-call issue this session) and report: number of Sarvam finals
   received, whether they were coalesced, `stt_stream_finalize` latency, and whether the agent's
   reply actually matched what the customer said (not a truncated fragment).
4. Compare against a second call with `TURN_DETECTION_MODE=provider` (the P3 baseline) on the same
   scripted utterances to see the actual before/after, not just theory.

## Telugu-first requirement (spec §79) — status

The semantic evaluator's continuation-marker list includes Telugu-script and romanized forms
(`ante`, `kani`, `inka`, `మరి`, `కానీ`, `ఇంకా`) alongside English/Hindi ones, and none of the
architecture is English/Hindi-specific — no external semantic/audio turn detector was integrated at
all (spec §11/§78 explicitly permits and this pass follows: "the entire product must work without an
English/Hindi-specific turn model"). But the marker list itself is a small, curated starting set, not
validated against real Telugu/Telugu-English speech patterns — that validation is part of the
manual real-call plan above, not yet performed.

## Definition-of-done checklist (spec §119), honestly marked

Items 1-19, 21-28 (TurnManager exists, state machine exists, signals flow, one turn can span multiple
finals, thinking pauses preserved, semantic gating works, number/code-mix pauses handled, backchannel
classification exists and is context-aware, noise bursts don't create turns, duplicate-final
protection preserved, user-resume cancels pending commits, max timeout exists, endpoint reason/latency
observable, call-level config is available via `Settings`, `ConversationEngine`/fast-path/RAG/domain-
correction/closing all unchanged) — **done, unit-verified**.

Item 20 (provider/vad/hybrid comparable) — **architecturally done** (all three modes exist and are
switchable via one flag); **not yet benchmark-compared** against each other on real or even simulated
audio beyond the two integration tests' specific scenarios.

Item 22 (call-level config snapshot) — **not implemented this pass**. `Settings` already carries the
active mode/profile, but nothing persists a per-call snapshot of it (e.g. into `redis_state` or
`CallSession.state`) for later reproducibility analysis. A real, scoped-out gap, not silently claimed.

Items 29 (Test Lab exposes turn state) — **not implemented**. `TurnManager.to_debug_dict()` exists
(same role as `RealtimeMediaSession.to_debug_dict()`) but nothing wires it into an HTTP endpoint or
the `apps/web` frontend — spec §98 explicitly permits scoping the UI down to backend-queryable data
only for this phase ("no full polished analytics dashboard is necessary in P4... make these metrics
queryable and visible in developer debugging"), which is what shipped.

Items 30-31 (311 old tests + new tests pass) — **310 confirmed** (the DB-dependent integration suite
couldn't run this session, see above) + all new unit tests passing.

Items 32-33 (lint/mypy pass) — **done**, `ruff check`/`mypy` clean on every touched/new file.

Item 34 (no automatic git commit) — **honored**, nothing committed.

## What's still unfinished after P4 (spec §120, restated)

- Streaming response generation: not yet — P5.
- Streaming TTS: not yet — P6.
- Full pipeline concurrency: later.
- Automatic barge-in: not yet — P8. `TurnManager` reliably produces `USER_SPEECH_STARTED` during any
  state (including while the agent might conceptually be speaking, once that state exists), which is
  the exact signal P8 needs — nothing consumes it to interrupt playback yet.
- Strict stale-audio rejection: not yet — P9.
- Speculative/preemptive generation on `TURN_LIKELY_COMPLETE`-shaped signals: not yet.
