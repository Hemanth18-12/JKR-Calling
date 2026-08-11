# P10 — Real-Call Quality Benchmark Harness

This is a measurement phase, not an architecture phase. P0–P9 built the structural realtime voice stack
(587 tests passing); P10's job is to point that stack at a real phone call, measure what actually happens,
and tune only what the evidence proves is weak. This doc is the harness: what to capture, how, and in what
order — the checklist every real test call should follow. See `docs/P10_REAL_CALL_ISSUES.md` (the issue
ledger), `docs/P10_REAL_CALL_RESULTS.md` and `docs/TROIKA_PARITY_RESULTS.md` (the result templates, filled
in after real calls happen).

**This environment cannot place a real phone call.** Everything in this document that requires listening
to real audio, judging real Telugu naturalness, or measuring real PSTN latency is written as instructions
for the user to execute, not as invented results. Nothing in `docs/P10_REAL_CALL_RESULTS.md` or
`docs/TROIKA_PARITY_RESULTS.md` is populated yet — both are explicitly marked NOT YET RUN.

## Ground rules (read before touching anything)

1. **Measure first, tune second.** Do not change the LLM model, STT provider, TTS provider, VAD
   architecture, RAG architecture, or ConversationEngine architecture before collecting real call data.
2. **One variable at a time.** If tuning `TurnManager`'s endpoint delay, don't also switch the voice or
   pace in the same test call — the result becomes unattributable.
3. **Every change needs evidence**: observed problem → evidence (call ID, turn, trace) → root cause →
   smallest fix → before/after result. No speculative refactors.
4. **Every real bug fix gets a regression test.** This has already caught genuine bugs in every phase from
   P5 through P9 (see each phase's own results doc) — keep doing it.
5. **Do not invent call results.** If a call hasn't been placed, say so. If a number can't be measured
   without a real call, leave it blank with a note, never a plausible-looking guess.

## Entry gate (run before any live test)

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run --package jkr-conversation pytest packages/conversation -q      # expect 189 passed
uv run --package jkr-db pytest packages/db -q                          # expect 32 passed
PYTHONPATH=services/api uv run --package jkr-api pytest services/api/tests -q               # expect 337 passed
PYTHONPATH=services/voice-worker uv run --package jkr-voice-worker pytest services/voice-worker/tests -q       # expect 10 passed
PYTHONPATH=services/campaign-worker uv run --package jkr-campaign-worker pytest services/campaign-worker/tests -q  # expect 13 passed
PYTHONPATH=services/intelligence-worker uv run --package jkr-intelligence-worker pytest services/intelligence-worker/tests -q # expect 11 passed
```

**Total: 592 tests** (587 P9 baseline + 5 new adaptive-brevity tests added this phase — see below).
Confirmed passing as of this document being written. `uvx ruff check` is clean on every file touched this
phase; a pre-existing, unrelated `ruff`/`mypy` debt exists in two places not touched by P5–P10 (an Alembic
migration's `Union[...]` typing style, and a `**dict` unpacking pattern in
`packages/conversation/tests/test_prompt_builder.py`'s pre-existing `_extraction()` test helper) — noted
honestly, not fixed, since both predate this phase and are out of its scope.

**If your baseline differs from 592: stop and investigate before continuing.** Do not tune product
behavior on top of a broken test baseline.

## Source control safety — read this before aggressive experimentation

As of this phase, the working tree contains **all of P5 through P9 uncommitted** — the entire streaming
realtime pipeline (streaming STT/LLM/TTS, the pipeline coordinator, automatic barge-in, replay protection).
`git status` shows 28 modified + roughly 85 untracked files; the last commit is still
`"Checkpoint before STT accuracy / domain understanding / safe-closing upgrade"`. This is now a large,
valuable amount of work sitting only in the local working tree, with no recovery point more recent than
that checkpoint.

**Recommendation, not an action taken automatically**: before any aggressive real-call tuning session
(the kind where you might try several TurnManager/barge-in/prompt tweaks back to back), create a commit
checkpoint. This tool will not commit without being explicitly asked — but you should ask for one, or run
it yourself, before P10-B tuning begins.

## What P10 added this pass (harness + one justified code change)

- **`tests/tools/real_call_quality_report.py`** — a developer tool that takes a `call_session_id` and
  produces the turn waterfall (from `CallLatencyMetric`), the transcript (from `CallTurn`), coarse call
  events (from `CallEvent`), and integrity/quality flags, after a real call has happened. See "The report
  tool" below for exact usage and its honest limitations.
- **`tts_stream_first_audio_ms` latency instrumentation** — a real, small gap this phase's own audit found:
  `TTSTurnOutcome.first_audio_ms` was already computed (P6) but silently discarded at the
  `speak_turn_reply()` boundary, never persisted. Now threaded through `SpokenReplyOutcome` and persisted
  as a `CallLatencyMetric` row, closing part of the turn-waterfall gap `§9` asks for. See "Turn waterfall:
  what's actually captured" below for what's still log-only.
- **Adaptive brevity, wired** (spec §42) — `packages/conversation/jkr_conversation/prompt_builder.py`'s
  `_brevity_instruction()`: once `recent_interrupt_count >= ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD` (2, a
  starting point not a measured-optimal value — same honest framing every other tunable constant in this
  codebase carries), the system prompt's existing SPEECH STYLE section gets one appended sentence asking
  for shorter, more direct answers. Never touches RAG facts, tool behavior, or safety rules — those live in
  separate, untouched prompt sections. `redis_state["recent_interrupt_count"]` (P8, already tracked, was
  previously unconsumed) is the source; threaded through `process_known_transcript_turn()` →
  `process_turn()` → `prompt_builder.generate()`. 5 new tests
  (`packages/conversation/tests/test_prompt_builder.py`), all passing. Zero effect on any existing call
  site (default `recent_interrupt_count=0`, below threshold).

No other code changes were made this pass. Per the phase's own instruction, no LLM/STT/TTS/VAD/RAG/engine
architecture was touched.

## Per-workspace/agent/number scoping — audited, not built

The spec asks (§5) to scope the full streaming-flag rollout to one test workspace/agent/number "if the
architecture supports it." **It currently does not**: `TWILIO_VOICE_TRANSPORT`, `STT_MODE`,
`TURN_DETECTION_MODE`, `CONVERSATION_ENGINE_MODE`, `LLM_RESPONSE_MODE`, `TTS_MODE`, `BARGE_IN_ENABLED`, and
`BARGE_IN_SENSITIVITY` are all plain fields on the single process-wide `Settings` object
(`services/api/app/config.py`), read once via `@lru_cache def get_settings()` — they apply identically to
every call the process handles, for the lifetime of that process. There is no `workspace_id`/`agent_id`
column or override path anywhere in `config.py`, and neither the `Agent` nor `Workspace` model has any
per-entity feature-flag column.

**Not built this pass, deliberately**: adding real per-workspace/agent config scoping would itself be a new
piece of architecture — exactly what this phase's own first rule says not to do before real call evidence
justifies it. The practical scoping that already exists and is sufficient for a first real call:

1. **`AUTHORIZED_TEST_NUMBERS`** — already enforced, unconditionally, in `start_live_test_call()`
   (`services/api/app/modules/live_call/service.py`) before any dialing happens. Only E.164 numbers in this
   comma-separated env var can ever be called via the test-call endpoint. This is the real safety boundary,
   not a per-workspace flag.
2. **One test workspace already exists** — see below. Since these flags are process-wide anyway, running
   the real-call test server as a dedicated process (pointed only at the one seeded test workspace, one
   seeded test agent, dialing only your own authorized number) achieves the *effect* of scoping without
   needing new code.

If real-call evidence later shows a genuine need to run production campaign traffic and P10-style
experimental traffic from the same process concurrently, *that* would be the evidence-based justification
for building per-workspace scoping — not before.

## The P10 test agent — already seeded, verified, not rebuilt

`packages/db/jkr_db/seed.py` already defines exactly the Aaha-Dental-style scenario §7 asks for:

- **Workspace**: `"Aaha Dental Care"` (slug `aaha-dental-care`), `default_language="te-en-IN"`,
  `timezone="Asia/Kolkata"`.
- **Agent**: `"Front Desk Assistant"`, `business_identity="Aaha Dental Care"`,
  `primary_language="te-en-IN"`, `primary_objective="book_appointment"`, `personality="warm_receptionist"`,
  `response_length="short"`.
- **AI disclosure**: `"నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని."`
- **Greeting**: `"నమస్కారం {name} గారు, నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని. మీ
  అపాయింట్‌మెంట్ గురించి ఒక నిమిషం మాట్లాడొచ్చా?"`
- **Domain vocabulary**: `"Dental Procedures"`, 4 terms, including the exact `"ఫ్రూట్ కెనాల్స్"` →
  `"root canal treatment"` alias that fixes the original mis-transcription bug this whole domain-
  normalization system was built around.
- **Knowledge base (RAG)**: one approved `KnowledgeDocument`, `"Aaha Dental Care — Pricing & Hours FAQ"`,
  real seeded pricing (root canal ₹3000–8000, cleaning/scaling ₹800), timings (Mon–Sat 9AM–8PM, closed
  Sunday), an emergency contact number, chunked and embedded (`approval_state="approved"` throughout — no
  fake/placeholder prices, per this phase's own instruction).

**One real gap found and worth fixing before a real call**: the seeded `VoicePersona` only sets
`language=agent_spec["primary_language"]` — `provider`, `voice_id`, `speaking_speed` all fall back to model
defaults, and the default `provider` is `ProviderName.MOCK`. **Before placing a real call, update this
agent's `VoicePersona` to a real Sarvam `voice_id`** (via the admin UI or a direct DB update) — otherwise
`_resolve_tts_speaker()`/`_resolve_tts_pace()`'s own existing "only for a persona actually configured for a
real provider" gating means the streaming TTS path may not pick up the intended speaker/pace at all. This
is a one-time setup step, not a code change.

## Turn waterfall: what's actually captured, honestly

Spec §9 wants: `USER_SPEECH_STARTED → USER_SPEECH_ENDED → TURN_COMMITTED → ENGINE_STARTED → ENGINE_COMPLETED
→ RAG_STARTED → RAG_COMPLETED → LLM_STARTED → LLM_FIRST_TOKEN → LLM_FIRST_SPEAKABLE_CHUNK → TTS_TEXT_SENT →
TTS_FIRST_AUDIO → TWILIO_FIRST_MEDIA_SENT → PLAYBACK_MARK_ACK`.

**What's persisted to the database** (`CallLatencyMetric.stage`, queryable after the call via
`_record_latency()` call sites in `services/api/app/modules/live_call/`):

```
stt_transcribe                    (batch STT mode)
stt_stream_finalize               (streaming STT mode — turn commit → final transcript resolved)
stt_stream_first_partial          (streaming STT mode — first partial transcript)
engine_fast_router
engine_domain_vocabulary
engine_extraction
engine_planning
engine_rag_embedding
engine_rag_vector_search
engine_rag
engine_generation
engine_llm_ttft
engine_llm_first_speakable_chunk
engine_llm_full_generation
tts_synthesize                    (batch TTS mode)
tts_stream_first_audio            (streaming TTS mode — NEW this phase, see above)
turn_total_backend
```

**What's only in structured process logs, not the database** (every P7/P8/P9 `log_event()` call —
`pipeline_response_begin`, `barge_in_candidate`, `barge_in_confirmed`, `stale_audio_blocked`,
`tts_stream_connected`, etc.): `transport/events.py`'s `log_event()` is a plain structured Python logger
call (`logger.log(level, payload)`) — it does **not** write to `CallEvent`. Only three event types are
ever persisted as `CallEvent` rows: `call_started`, `{speaker}_turn`, `call_ended`. This means the detailed
barge-in/replay/dead-air trace only exists in the server's own log output during the call, not
retroactively queryable from Postgres afterward.

**Practical consequence for real-call testing**: capture the server's stdout/log output to a timestamped
file for the duration of every real test call (e.g. `uvicorn ... 2>&1 | tee call_$(date +%s).log`), and
keep it alongside the `call_session_id`. The report tool (below) reads the DB for turns/latency/coarse
events; grep the log file (`grep <call_session_id> call_*.log`) for the barge-in/replay event trace.

**Not every stage exists on every turn** — a fast-path turn (`ASK_FIELD`/`CLARIFY`/`CONFIRM_FIELD`/
`DEFER_QUESTION` under `CONVERSATION_ENGINE_MODE=fast`) skips `engine_generation`/`engine_llm_*`/
`engine_rag*` entirely (canned template, no LLM call — see `prompt_builder.py`'s
`_FAST_RESPONSE_ELIGIBLE_ACTIONS`). Represent this as "skipped," not a missing/broken measurement, in any
report.

## Core latency KPIs

- **`speech_end_to_first_audio_ms`** = `USER_SPEECH_ENDED → TWILIO_FIRST_MEDIA_SENT`. The best
  application-level approximation of perceived response-start latency. Not directly persisted as one
  number today — compute it from `CallLatencyMetric` rows: `stt_stream_finalize` (or the STT-final
  timestamp) through `tts_stream_first_audio`, plus whatever `turn_total_backend` reports as the full
  backend span.
- **`turn_commit_to_first_audio_ms`** — the same span, starting from `TURN_COMMITTED` instead, isolating
  response processing from endpointing. Compute as `engine_* + tts_stream_first_audio` (endpointing/STT
  finalization excluded).
- **Target** (long-term, not yet measured): P50 ≈ 700–1200ms for straightforward no-RAG turns, if provider
  conditions permit. Do not fabricate this number for a call that hasn't happened — it's a target, not a
  result, until real data exists.

## Root-cause discipline

For every slow turn, attribute the delay to exactly one dominant stage — never say "the AI is slow."

```
Example (LLM-dominant):
  Endpoint 350ms | Engine 280ms | RAG 0ms | LLM first chunk 1100ms | TTS 220ms | Media 20ms
  → LLM first chunk dominates. Do NOT retune VAD.

Example (RAG-dominant):
  Endpoint 300ms | Engine 250ms | RAG 1400ms | LLM 800ms | TTS 220ms
  → RAG is the target. Not TTS.

Example (endpoint-dominant):
  Endpoint 1000ms | Engine 200ms | LLM 700ms | TTS 200ms
  → Tune TurnManager (P4). Not the LLM.
```

## Test categories (single-turn scripts)

| # | Category | Customer says | Expect |
|---|---|---|---|
| A | Fast turn | "Yes." (to a yes/no question) | FastTurnRouter, no RAG, no LLM, very low latency |
| B | Simple field | "Tomorrow evening." | Field captured, no repeat question |
| C | Multi-field | "Root canal కావాలి, tomorrow evening వస్తాను." | Both fields captured, neither re-asked |
| D | Business question | "Root canal cost entha?" | RAG/tool used, answer leads with the actual info, no generic opener |
| E | Question + field | "Tomorrow వస్తాను. Consultation fee entha?" | Field captured AND the question answered first |
| F | Thinking pause | "Tomorrow…" [pause] "actually evening better." | ONE logical turn, no premature response |
| G | Correction | Agent: "Tomorrow morning…" / Customer: "No, afternoon." | Agent stops quickly, no replay, time corrected |
| H | Barge-in question | Agent explaining / "One minute, cost entha?" | Old audio stops, new question answered |
| I | Backchannel | Agent explaining / "hmm" | Agent continues normally, no false barge-in |
| J | Short direct answer | Agent: "Saturday better aa, Sunday better aa?" / Customer interrupts: "Sunday." | Agent stops, `preferred_day=Sunday`, no continuation of the old question |
| K | DNC | "Don't call me again." | Immediate stop, suppression, polite close, no further sales speech |
| L | Human request | "Human tho మాట్లాడాలి." | Immediate stop, handoff/callback path |
| M | Closing reopen | Agent closing / "Actually one more question." | Closing interrupted, call returns ACTIVE, no duplicated goodbye |
| N | Language switch | "Telugu lo cheppandi." then later "English is okay." | Future responses shift both times, no voice-identity change unless provider requires it |
| O | Pure Telugu | (configure `te-IN`) | No unnecessary English fillers, natural spoken Telugu |
| P | Telugu + English | (configure `te-en-IN`) | Natural Andhra/Telangana-style code-mix, not maximal English mixing |
| Q | Pure English | (configure `en-IN`) | Stays English unless customer requests a switch |

## Ten-call test plan (multi-turn scripts)

1. **Normal conversation** (2–3 min, no intentional attack) — the most important call; scripted stress
   tests alone distort behavior.
2. **Interruption-heavy** — "hmm", "one minute", "wait", "no", "actually", "Sunday", "cost entha?" during
   agent speech. Evaluates P8/P9 together.
3. **Thinking/pause-heavy** — natural hesitation, e.g. "Actually… root canal… last week నుంచి pain ఉంది…".
   Evaluates P4.
4. **Business knowledge** — pricing, timings, services, location, availability, policy. Evaluates RAG vs.
   live-tool distinction.
5. **Telugu-only**.
6. **Telugu-English** — should be a primary benchmark call.
7. **Fast speaker**.
8. **Slow speaker** (longer pauses).
9. **Noisy environment** (moderate fan/road/background noise — no unsafe driving test). Evaluates false
   VAD/barge-in.
10. **Closing** — let the agent close, then interrupt ("Actually one more thing…"), then close naturally.

## Call scorecard (fill in per call)

```
Call:                    ________________
Overall:                 __ / 10
Latency:                 __ / 10
Understanding:           __ / 10
Telugu:                  __ / 10
Naturalness:             __ / 10
Voice:                   __ / 10
Turn-taking:             __ / 10
Barge-in:                __ / 10
RAG:                     __ / 10
Business usefulness:     __ / 10
Notes:                   ________________________________________
```

## Troika-style human quality score (per call, 1–5 each)

```
Responsiveness | Understanding | Naturalness | Context retention | Question relevance
Barge-in | Voice quality | Language quality | Business usefulness | Trustworthiness
Overall call quality: __ / 5
```

## Audio QA checklist (cannot be inferred from logs — human listening required)

Voice naturalness · Pronunciation · Prosody · Pace · Volume · Chunk seams · Audio clipping · Audio gaps ·
Code-mixed pronunciation · Response-start smoothness.

## Pronunciation test list

`Aaha Dental` · `root canal` · `RCT` · `crown` · `implant` · `Kakinada` · `Rajahmundry` · `Peddapuram` ·
`EAPCET` · `CSE` · `ECE` · ₹ amounts · dates · times. Document every mispronunciation with the exact audio
timestamp. **Confirm the original "fruit canal" mis-transcription is now handled** (the seeded domain
vocabulary alias exists — a real call is the only way to confirm it actually fires end to end).

**Fix order for a pronunciation problem** (spec §49): `SpokenResponseFormatter` wording first, TTS
pronunciation dictionary/provider settings second, wording change third. Never fix a TTS pronunciation
problem by changing STT vocabulary — those are different layers with different jobs.

## Automated quality metrics to track per call

```
repeated_question_count          known_field_reasked_count
customer_correction_count        unnecessary_paraphrase_count
clarification_count              generic_opener_count
false_barge_in_count             semantic_repetition_count
confirmed_barge_in_count         long_response_count
customer_question_ignored_count  empty_response_count
acknowledgement_repetition_count RAG_unknown_count
                                  unsafe_claim_count
```

None of these have automated detectors built this pass (would require call-transcript NLP analysis this
phase's own "measure first" rule argues against building before real data justifies the investment) — score
them by manual transcript review for the first real calls, per the ledger in
`docs/P10_REAL_CALL_ISSUES.md`. If manual review across several calls shows a specific metric is
consistently the top issue, *that* is the evidence to justify building an automated detector for it.

## The absolute integrity KPI

`replay_metrics.stale_audio_sent_total` (P9) **must equal 0 for every real call.** If it's ever greater
than 0: **stop rollout immediately, do not tune naturalness first.** This is the one number that overrides
every other priority in the fix-order list below. There is no code path in this implementation that
increments it except the (should-be-unreachable) output-gate-bypass branch — a nonzero value means the gate
itself has a real hole.

During every interruption test, also listen specifically for: old sentence resuming, duplicate word,
duplicate sentence, old goodbye, old question remainder. Any of these is severity **BLOCKER** regardless of
what `stale_audio_sent_total` reports (a duplicate that only ever crossed the LOCAL queue and never reached
Twilio wouldn't increment that counter, but is still a real customer-facing bug worth its own severity).

## Fix-order priority

```
1. Safety/integrity (replay, wrong facts, DNC ignored, hangup mid-speech, cross-call audio, false tool success)
2. Understanding
3. Conversation relevance
4. Latency
5. Turn-taking
6. Voice naturalness
7. Cosmetic language polish
```

Do not fix minor pronunciation before a major intent bug.

## Severity definitions

- **BLOCKER**: replay, wrong business fact, call hangup mid-customer-speech, DNC ignored, cross-call audio,
  tool false confirmation.
- **HIGH**: 4-second unnecessary silence, customer question ignored, major STT misunderstanding.
- **MEDIUM**: awkward phrasing, repeated acknowledgement.
- **LOW**: everything else worth noting but not urgent.

## The report tool

`tests/tools/real_call_quality_report.py` — given a `call_session_id` (and a workspace-scoped DB
connection), prints:

- Call metadata (agent, language, started/ended, duration, status, end reason).
- The full turn transcript in order (speaker, text, timestamps, `is_interrupted`).
- The latency waterfall per stage, grouped, with a computed `speech_end_to_first_audio_ms` where the
  relevant stages exist for that turn.
- Coarse call events (`call_started`/`*_turn`/`call_ended`).
- A reminder to cross-reference the captured log file for the barge-in/replay/dead-air trace, since that
  data is not in the database (see above).

Usage:

```bash
PYTHONPATH=services/api uv run --package jkr-api python tests/tools/real_call_quality_report.py <call_session_id>
```

This tool has been tested against seeded/synthetic data in this environment (see its own test coverage) —
**it has not yet been run against a real call's data**, because no real call has been placed in this
environment. Running it against your first real `call_session_id` is the natural next step once you have
one.

## Staging configuration for the real call

```env
TWILIO_VOICE_TRANSPORT=media_stream
STT_MODE=streaming
TURN_DETECTION_MODE=hybrid
CONVERSATION_ENGINE_MODE=fast
LLM_RESPONSE_MODE=streaming
TTS_MODE=streaming
BARGE_IN_ENABLED=true
BARGE_IN_SENSITIVITY=balanced
AUTHORIZED_TEST_NUMBERS=<your own verified E.164 number>
```

(`REALTIME_COORDINATOR_ENABLED` from the spec's own env block is not a real flag in this codebase — the
coordinator activates automatically whenever `TTS_MODE=streaming` is active, per P7's own design; nothing
to set separately.)

## Step-by-step: placing the call yourself

1. Confirm `docker compose up -d postgres redis minio` is running and seed data is loaded
   (`make seed` or the repo's equivalent) so the Aaha Dental Care workspace/agent exist.
2. Update the seeded agent's `VoicePersona` to a real Sarvam voice (see "The P10 test agent" above) —
   one-time setup.
3. Set the env block above in your `.env` (or process environment), restart the API server, and capture its
   stdout to a log file for the session (`... 2>&1 | tee p10_call_<n>.log`).
4. Add your own phone number to `AUTHORIZED_TEST_NUMBERS`.
5. Call `POST /api/v1/live-call` with `{"agent_id": <Aaha Dental Care agent id>, "to_number": "<your E.164 number>"}`
   (via the admin UI, or `curl`/`httpie` with a valid session) — this dials **you**, so you play the
   customer role and hear the agent live.
6. Run through Test Call 1 (normal conversation) first. Then, across subsequent calls, work through Test
   Calls 2–10 and the single-turn categories A–Q as time allows — one variable at a time (see "Ground
   rules").
7. After each call, note the `call_session_id` (visible in the API response / DB), run the report tool
   against it, and fill in one row per issue found in `docs/P10_REAL_CALL_ISSUES.md`.
8. Once you have enough calls for a first real assessment, fill in `docs/P10_REAL_CALL_RESULTS.md` and
   `docs/TROIKA_PARITY_RESULTS.md` honestly — including the categories that are still weak.

## What NOT to do yet

- Do not enable these flags for campaign/production traffic — this stays scoped to the one authorized test
  number until real-call evidence says otherwise.
- Do not run concurrent-call load testing before single-call quality is good (spec §107-110: "one excellent
  call before 100 mediocre concurrent calls").
- Do not build the developer-only call-QA analytics UI page (spec §92-93) before real calls prove which
  parts of the waterfall actually need a visual tool versus what the text report above already answers —
  not built this pass, deliberately, pending that evidence.
- Do not implement playback-lookahead enforcement (P7's own deferred item) unless real
  `twilio_playback_backlog_ms` values from an actual call show it's needed.
- Do not build an FAQ/embedding cache (spec §87-88) unless real calls show RAG latency is a genuine,
  repeated bottleneck.
