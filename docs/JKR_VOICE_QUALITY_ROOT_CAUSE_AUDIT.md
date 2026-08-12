# JKR Voice Quality — Root Cause Audit

Ranked, code-grounded findings on why a real JKR AI call might feel slow, robotic, inaccurate, or repetitive — and, separately, why it currently has no live interruption handling at all. Every item below was traced to specific code, then independently spot-checked for this document (not taken on faith from a single research pass). This was diagnosis-only at the time of writing; **items #1, #3, and #8 have since been fixed — see the "Stage 2 update" notes inline and `docs/STAGE2_REAL_CALL_FIXES.md` for full detail.** Everything else below is unchanged and still accurate.

---

## Top 10 quality risks, ranked

### 1. [BLOCKER] `book_appointment` silently fails on every real call
**[FIXED — Stage 2, see `docs/STAGE2_REAL_CALL_FIXES.md` Fix 1]** `_get_or_create_contact()` now resolves/creates a real `Contact` at call creation and `CallSession.contact_id` is populated for every real call; `execute_tool()` at both webhook call sites now passes it through. The spoken reply is now conditioned on actual tool outcome — a truthful fallback (te/hi/en) is spoken instead of the canned success line whenever a real-side-effect tool fails. Regression-tested (13 new tests). The paragraph below is the original finding, left for historical/diagnostic reference.

**Evidence**: `packages/db/jkr_db/tools_engine.py:189-190` — `_run_book_appointment` raises `ToolInputError` if `contact_id is None`. `services/api/app/modules/live_call/service.py` — a repo-wide grep for `contact_id` in this file returns **zero matches**; `CallSession` is created without one and `execute_tool()` is called at all 3 sites with the default `contact_id=None`.
**Customer symptom**: the agent says "Great, I've noted your appointment details, our team will confirm" — and no `Appointment` row is ever created. This is exactly the P10 benchmark doc's own definition of a BLOCKER ("false tool success").
**Root cause**: BUG. The seeded flagship demo agent (Aaha Dental Care) has `primary_objective="book_appointment"`, so this fires on essentially every complete demo call.
**Smallest fix**: attach/create a `Contact` for Live Test Call sessions (even a synthetic one keyed to the dialed number), pass `contact_id` through the 3 `execute_tool()` call sites, and — separately — make the spoken closing text conditional on tool outcome rather than generated before the tool even runs.
**Expected impact**: removes a silent, compliance-relevant false-confirmation bug in the single most important demo path.

### 2. [HIGH] Barge-in does not exist on a real call today
**Evidence**: `effective_barge_in_enabled` (`config.py:201-217`) requires `barge_in_enabled=True` AND `effective_stt_mode=="streaming"` AND `effective_tts_mode=="streaming"` AND `effective_turn_detection_mode in ("vad","hybrid")` — all four are false/unset in `.env`. The code that would even evaluate an interruption (`streaming_bridge.py`) is unreachable under `effective_stt_mode="batch"`.
**Customer symptom**: talking over the agent does nothing; it keeps speaking until its current reply finishes.
**Root cause**: CONFIGURATION, not a bug or missing code — `InterruptionPolicy`, `RealtimePipelineCoordinator`, and the replay-protection output gate are fully built and unit-tested.
**Smallest fix**: staged single-flag activation (see Recommended Next Actions #4).
**Expected impact**: HIGH, but only after a deliberate, measured rollout — this is the P10 doc's own explicit "must be validated on a real call before shipping" item, not a flip to make casually.

### 3. [HIGH] The prompt forbids "Sure"/"Okay" openers; the pipeline force-prepends exactly that, every turn
**[FIXED — Stage 2, see `docs/STAGE2_REAL_CALL_FIXES.md` Fix 2]** `engine.py` now seeds `SpokenResponseFormatter` with `_last_acknowledgement=new_state.get("last_acknowledgement")` and writes the chosen acknowledgement back into `new_state` after formatting — the rotation now survives across turns of one call via `CallSession.state` (the same call-scoped, DB-persisted dict `known_fields`/etc. already use), exactly the fix this finding recommended. Regression-tested across `ASK_FIELD`→`CLARIFY`→`ASK_FIELD` and `CONFIRM_FIELD`→`ASK_FIELD` sequences, plus cross-call isolation. The paragraph below is the original finding, left for historical/diagnostic reference.

**Evidence**: `prompt_builder.py:188-190` explicitly instructs the LLM never to open with "Sure"/"Okay"/"Absolutely" (citing a real prior failure probe). `engine.py:375-378` unconditionally prepends an acknowledgement for every `ASK_FIELD`/`CLARIFY`/`CONFIRM_FIELD` turn via a **freshly-constructed** `SpokenResponseFormatter` each time — `pick_acknowledgement()`'s dedup logic compares against `self._last_acknowledgement`, which starts `None` every turn, so `candidates[0]` (the first item in the language's list, e.g. "సరే అండి."/"Sure.") wins deterministically, every single time. **Spot-checked directly**: confirmed by reading `engine.py:375` and `formatter.py:108-113` — the existing unit test passes only because it reuses one formatter instance across its loop, masking this exact bug.
**Customer symptom**: the same filler opener on every field-question/clarify/confirm turn of the call — a mechanical, deterministic (not probabilistic-LLM) source of "robotic and repetitive."
**Root cause**: BUG — one-line fix (carry acknowledgement state across turns via the existing per-call state dict, or simply randomize the pick).
**Expected impact**: MEDIUM-HIGH, disproportionate to its fix cost — this affects the most common non-terminal turn types in any call.

### 4. [HIGH] Flat, untuned 4.0-second silence wait before the agent starts processing at all
**Evidence**: `transitional_bridge.py` `TurnBuffer`: `TRAILING_SILENCE_SECONDS=4.0`, `SILENCE_RMS_THRESHOLD=300` — both explicitly flagged in the module's own docstring as "not tuned against real phone-line audio." This is slower than even the dormant hybrid mode's FAST (1.7s) and BALANCED (2.9s) presets.
**Customer symptom**: a long, dead pause after every single thing the customer says, before the agent even begins working on a reply.
**Root cause**: TUNING/CONFIGURATION — a real, measurable, directly-fixable number, independent of any LLM/TTS latency.
**Smallest fix**: lower the threshold (e.g. to ~2.0-2.5s) as an immediate low-risk change, even before considering a move to streaming/hybrid mode.
**Expected impact**: HIGH and immediate — this is pure dead air on every turn of every call.

### 5. [HIGH] Fully sequential, blocking per-turn pipeline
**Evidence**: `_run_batch_turn_loop` awaits the entire chain — batch STT REST call → extraction LLM call → (conditional) RAG embedding + pgvector → response-generation LLM call → batch TTS REST call — inline, synchronously, one `_processing_loop` task per call, before any more audio is even read.
**Customer symptom**: total turnaround time is the sum of every stage with zero overlap; a RAG-answering turn pays STT + 2 LLM calls + embedding + TTS end-to-end serially.
**Root cause**: CONFIGURATION — `LLM_RESPONSE_MODE=streaming` and `TTS_MODE=streaming` exist specifically to let TTS start on the first sentence instead of waiting for the whole reply; both are off.
**Smallest fix**: same staged rollout as #2 — `LLM_RESPONSE_MODE=streaming` is a smaller, more isolated first step than the full barge-in stack.
**Expected impact**: HIGH, compounds directly with #4 as the dominant total-latency contributor.

### 6. [MEDIUM-HIGH] The field catalog has no vertical-specific slots at all
**Evidence**: `objectives.py` defines exactly 5 generic objectives with generic fields (`topic`, `interest_detail`, `timeline`, `reason_for_visit`, `preferred_date`/`time`, `satisfaction`) — nothing dental- or education-specific. "CSE kavali, rank 28 thousand, hostel kuda kavali" has no field to extract "rank" or "hostel" into; at best it's mashed into a generic field, at worst dropped.
**Customer symptom**: the conversation feels like generic form-filling, and concrete facts the customer volunteers get lost or misfiled.
**Root cause**: MISSING PRODUCT SCOPE, not a bug — the extraction/planning machinery is generic by design; nobody has yet authored vertical-specific objective definitions.
**Expected impact**: MEDIUM-HIGH, directly explains a recurring class of complaint ("doesn't feel like it understood my specific situation").

### 7. [MEDIUM] Domain-vocabulary correction has a narrower blast radius than the bug it was built to fix
**Evidence**: `domain_normalizer.normalize()` only rewrites values the extraction LLM already placed into `extracted_fields` — the raw transcript stored in `recent_turns`/`CallTurn` is never rewritten, and `rag.py`'s `rewritten_query` is passed to vector search with **no normalization pass at all** (`planner.py:68` → `engine.py:294-297`).
**Customer symptom**: a mis-transcribed factual question (e.g. "root canal cost" garbled the same way the field-value fix targets) can still retrieve wrong/no knowledge-base chunks, even in a workspace where the exact alias is seeded.
**Root cause**: ARCHITECTURE gap — the mechanism works exactly as designed for what it covers; its coverage is just narrower than "fixes STT garbling," which is what it's colloquially understood to do.
**Expected impact**: MEDIUM — specifically affects business-question turns, which is a core value-driving interaction.

### 8. [MEDIUM] Seeded voice persona silently falls back to a generic, unconfigured voice with no pace control
**[PARTIALLY FIXED — Stage 2, see `docs/STAGE2_REAL_CALL_FIXES.md` Fix 3]** The "no pace control" half is fixed: `SarvamTTS` now accepts and sends `pace`, and all 7 `_speak()` call sites in the batch `<Record>` path forward `_resolve_tts_pace()`'s result — previously computed and cached but never actually sent to Sarvam. Regression-tested against two real agents with different `speaking_speed` values resolving to different effective pace. The "generic voice" half is **still open**: seeded `VoicePersona.provider` still defaults to `MOCK` in `seed.py`/the DB model default — that's a demo-data completeness gap, not code, and was left as-is (out of scope for a stage that touches no seed data). The paragraph below is the original finding, left for historical/diagnostic reference; its pace-related claims are now superseded.

**Evidence**: `VoicePersona.provider` defaults to `MOCK` in both the DB model and current seed data (still unfixed since flagged in `docs/P10_REAL_CALL_BENCHMARK.md`); `_resolve_tts_speaker()` correctly avoids passing the bogus placeholder to Sarvam, so `SarvamTTS`'s own default (`speaker="priya"`) silently takes over. The active batch TTS payload has no `pace`/speed field in its schema at all — `VoicePersona.speaking_speed` only reaches Sarvam via the dormant streaming path.
**Customer symptom**: every workspace's agent sounds identical (Sarvam's generic default voice), regardless of any voice configuration attempted in the DB/UI, and speaking speed can't be adjusted at all today.
**Root cause**: CONFIGURATION / missing one-time setup step, not a code defect — this is a real gap in demo-data completeness, flagged and not yet closed.
**Expected impact**: MEDIUM — affects perceived brand fit and naturalness, not correctness.

### 9. [MEDIUM] `.env.example` documents none of the P3–P9 flags
**Evidence**: repo-wide grep across `.env.example` for every flag in the config matrix returns zero matches.
**Customer symptom**: none directly, but this is exactly *why* the P2-P9 architecture has silently sat dormant — nobody bootstrapping from the example file would discover these knobs exist at all.
**Root cause**: DOCUMENTATION / CONFIGURATION drift.
**Expected impact**: MEDIUM, indirect — this is a process risk that perpetuates finding #2/#5 staying invisible.

### 10. [LOW→MEDIUM as scale grows] Uncached per-turn DB reload + no vector index
**Evidence**: `domain_vocabulary.load_domain_terms()` re-queries the full vocabulary every single turn with no caching, despite the assignment being fixed for the call's lifetime and other per-call data already living in the Redis state blob. No `ivfflat`/`hnsw` index exists on `knowledge_chunks.embedding` in any migration — every RAG query is a full sequential scan + sort.
**Customer symptom**: none noticeable today at demo scale; a genuine latency landmine once vocabularies/knowledge bases grow.
**Root cause**: EFFICIENCY / INFRASTRUCTURE, not urgent yet.
**Expected impact**: LOW today, rising with scale — worth a ticket, not a fire drill.

---

## Classification (architecture vs. configuration vs. bug vs. everything else)

| # | Issue | Class |
|---|---|---|
| 1 | `book_appointment` contact_id gap | **BUG — FIXED (Stage 2)** |
| 2 | Barge-in fully dormant | **CONFIGURATION** (code is architecturally sound) |
| 3 | Acknowledgement never rotates | **BUG — FIXED (Stage 2)** |
| 4 | Flat 4.0s silence wait | **TUNING** |
| 5 | Sequential blocking pipeline | **CONFIGURATION** |
| 6 | No vertical-specific fields | **MISSING PRODUCT SCOPE** |
| 7 | Domain correction narrow blast radius | **ARCHITECTURE** (scoped, not broken) |
| 8 | Generic fallback voice, no pace | **CONFIGURATION** (missing setup data) — pace-forwarding half **FIXED (Stage 2)**; generic-voice half still open |
| 9 | `.env.example` gaps | **DOCUMENTATION** |
| 10 | Uncached reload, no vector index | **INFRASTRUCTURE / EFFICIENCY** |
| — | `OPENAI_API_KEY` native-startup plumbing (reads `os.environ`, not `Settings`; no confirmed re-export step in the native `uv run` path) | **VERIFY OPERATIONALLY** — not confirmed broken, but not confirmed working either; resolve before trusting any "is this using real AI" assumption |
| — | The Twilio "application error" incident from earlier this session | Traced to `p10_call_1.log` showing only a `status` webhook callback, no `voice`/`recording` webhook line — consistent with (not proof of) an unreachable `PUBLIC_WEBHOOK_BASE_URL` at call time. **INFRASTRUCTURE**, already resolved this session by restarting the ngrok tunnel; worth confirming against Twilio's own console call log for that `CallSid` if it recurs. |

No provider-quality issue was found (Sarvam/OpenAI themselves aren't implicated in anything above) and no LLM-prompt-content contradiction survived scrutiny at the language-instruction level — the one real prompt-layer bug (#3) is a code/formatter issue, not a prompt-wording issue.

---

## What is already good — do not rewrite

- **`ResponseIdentity` + the replay-protection output gate (`can_send_media()`)** — a genuine 5-layer defense (atomic local invalidation → queue purge → dequeue re-check → provider-event re-check → final live-state gate), well-tested, ready to protect the moment streaming/barge-in activate. This is exactly the kind of reliability complexity that should stay.
- **`RealtimePipelineCoordinator`'s state machines** — both `ResponseState` and `PlaybackUnitState` transitions are centrally validated against explicit allow-lists; terminal states can never be revived. Sound design.
- **`InterruptionPolicy`'s classification structure** (critical → high-priority → backchannel → generic) — the tiered design is correct; only two narrow phrase-list gaps need fixing (bare "human", bare "no"), not a redesign.
- **`SpeakableChunker`** — simple, punctuation-driven, script-agnostic, correctly handles the code-switched example tested. No changes needed.
- **Backpressure design in `transport/session.py`** — non-blocking drop-and-count on inbound, blocking backpressure on outbound. Correct real-time engineering judgment.
- **The planner's safety-first priority ladder** (DNC/wrong-number always outrank everything) and **the closing grace-period reopen logic** (verified correct, including the DNC-never-reopens compliance guard) — both are subtle, well-reasoned, and already correct. Leave them alone.
- **The domain-vocabulary correction mechanism itself** — the fuzzy-match-against-curated-aliases design is sound and genuinely workspace/agent-scoped, not hardcoded to one demo string. Its gap (#7) is coverage, not design — extend it, don't replace it.

## Do-not-touch list

> These are not the bottleneck. Don't rewrite them without new evidence: the replay-protection gate, the pipeline coordinator's state machines, the interruption-policy tiering structure, the speakable chunker, the transport backpressure design, the planner's priority ordering, the closing/grace-period logic, the domain-vocabulary matching algorithm.

---

## Have we over-engineered anything?

Mostly no. The P7–P9 machinery (coordinator, replay protection) looks complex but each piece maps to a real correctness requirement (no stale audio, no lost cancellation) that a phone call genuinely needs once streaming is live — this is necessary reliability complexity, not unnecessary live-path complexity. The one place complexity *is* currently disproportionate to what's running: maintaining two entirely separate real-call code paths (`transitional_bridge.py` batch and `streaming_bridge.py` streaming) inside the same transport module, when only one has ever been exercised against a real caller. That's not wasted engineering — it's a real fallback path — but it does mean the "simple" active path and the "sophisticated" dormant path both need to be understood and maintained simultaneously, which is a genuine ongoing cost.

---

## Recommended next actions (ranked, maximum 8, no implementation yet)

### 1. Fix the `book_appointment` contact_id bug — **DONE (Stage 2)**
Why: a silent false-confirmation bug in the flagship demo path, BLOCKER severity per the project's own severity table, low implementation risk.

### 2. Fix the acknowledgement-rotation bug — **DONE (Stage 2)**
Why: one of the highest impact-per-line-of-code fixes available — directly undoes the prompt's own explicit anti-filler-opener instruction, on the most common turn types in any call.

### 3. Lower the `TurnBuffer` silence threshold from 4.0s
Why: immediate, low-risk, measurable latency win, independent of any larger architectural decision.

### 4. Stage a single-flag-at-a-time activation of the real-time stack on one test agent, `STT_MODE=streaming` first
Why: this is the P10 benchmark doc's own prescribed method ("one variable at a time," use the existing report tool to measure before/after). Unlocks better endpointing and partial transcripts before touching TTS or barge-in.

### 5. Fix the seeded `VoicePersona` (real `provider`/`voice_id`/`speaking_speed`) — **pace-forwarding half DONE (Stage 2); provider/voice_id seed data still open**
Why: one-time data fix, zero code risk, removes an entire class of "wrong/generic voice" confusion immediately.

### 6. Extend domain-vocabulary correction to the RAG query path (and ideally transcript history)
Why: closes the gap where the exact class of bug this system was built to fix (STT mis-transcription of domain terms) can still slip through on business-question turns specifically.

### 7. Author vertical-specific objective fields for at least the dental and education demo verticals
Why: directly addresses the "feels like form-filling" complaint and the concrete lost-information cases found (rank, hostel, procedure names).

### 8. Document the P3–P9 flags in `.env.example` and resolve the `OPENAI_API_KEY`/native-startup ambiguity
Why: cheap, prevents this exact class of "we built it but it's silently off" gap from recurring, and removes uncertainty about whether real AI calls are even firing under native (non-Docker) startup.
