# Real-Time Voice Engine Migration — Audit & Baseline

Phase 1 of the real-time voice engine upgrade: trace the current live-call pipeline exactly as it
exists in the repository today, measure real (not estimated) latency from an actual phone call,
and assess what should be reused vs. replaced before any migration code is written. No behavior
changes are in this document except the one regression fix in §4 (found *because of* this audit's
baseline call and fixed immediately since it was actively dropping calls).

## 1. Current pipeline, traced

```text
Twilio phone call
  → POST /webhooks/twilio/voice/{token}         (handle_voice_webhook)
  → <Play> pre-synthesized greeting              (Sarvam TTS, done during dialing — see §6)
  → <Record timeout="4" maxLength="20" playBeep="true">
  → [customer speaks; Twilio waits for `timeout` seconds of silence]
  → POST /webhooks/twilio/recording/{token}      (handle_recording_webhook)
      → fetch_recording()                        Twilio REST, downloads the .wav file
      → SarvamSTT.transcribe()                   Sarvam REST /speech-to-text, whole file at once
      → process_turn()                           packages/conversation — extraction, domain
                                                  normalization, planning, RAG (conditional),
                                                  response generation
      → execute_tool() per tool call requested
      → _speak() → SarvamTTS.synthesize()         Sarvam REST /text-to-speech, whole reply at once
      → <Play> reply, <Record> again — loop
  → on a terminal decision: <Play> closing, <Record timeout="4" maxLength="6"> (grace window)
  → POST /webhooks/twilio/closing-grace/{token}  (handle_closing_grace_webhook)
      → silence → real finalize, <Hangup/>
      → speech, do_not_call/wrong_number → acknowledge, still <Hangup/>
      → speech, otherwise → reopen state, process_turn() again, resume the loop above
```

All code: `services/api/app/modules/live_call/service.py` (869 lines — `handle_voice_webhook`,
`handle_recording_webhook`, `handle_closing_grace_webhook`, `handle_status_webhook`).
Twilio REST client and signature validation: `services/api/app/live_providers/twilio_telephony.py`.
Sarvam clients: `services/api/app/live_providers/sarvam_stt.py`, `sarvam_tts.py`.

**Test Lab (mock calls) uses a structurally different transport** but the *same* conversation
brain: `services/voice-worker/app/conversation_engine.py`'s `submit_user_turn()` calls the
identical `jkr_conversation.engine.process_turn()` that live calls use — see §5. Test Lab has no
real audio at all (`MockSTT`/`MockTTS`, text in/text out, simulated timing via `TurnManager`,
`services/voice-worker/app/turn_manager.py`).

## 2. Every blocking operation / network round-trip, per turn

| # | Operation | Type | File:function |
|---|---|---|---|
| 1 | Twilio waits `timeout` seconds of silence | dead air, no network | Twilio-side, `<Record timeout>` |
| 2 | Fetch recording | HTTP GET, Twilio | `twilio_telephony.py:fetch_recording` |
| 3 | STT transcription | HTTP POST, Sarvam, **whole file** | `sarvam_stt.py:SarvamSTT.transcribe` |
| 4 | Domain vocabulary load | DB query | `jkr_conversation/domain_vocabulary.py` |
| 5 | Field extraction | HTTP POST, OpenAI, **full completion awaited** | `jkr_conversation/extractor.py:extract` |
| 6 | Planning | pure Python, in-process | `jkr_conversation/planner.py` — not a bottleneck |
| 7 | RAG (conditional) | OpenAI embedding + pgvector query | `jkr_conversation/rag.py:search_knowledge` |
| 8 | Response generation | HTTP POST, OpenAI, **full completion awaited** | `jkr_conversation/prompt_builder.py:generate` |
| 9 | TTS synthesis | HTTP POST, Sarvam, **whole reply text at once** | `sarvam_tts.py:SarvamTTS.synthesize` |
| 10 | Twilio fetches reply audio | HTTP GET, Twilio, our own `/audio/{id}.wav` | `service.py:_audio_url` + Twilio's `<Play>` fetch |

Steps 2 → 9 are **strictly sequential** — nothing starts until the previous step fully completes.
Zero streaming, zero pipelining, zero speculative/concurrent work anywhere in this chain. The
*only* concurrency in the entire live-call path today is the greeting TTS running in parallel with
`telephony.create_call()` during dialing (§6) — everything else is one blocking call after another.

## 3. Real observed latency — from an actual call, not an estimate

Call `6eac981f-1513-48af-b7e3-4f00337fd2e8` (`aaha-dentalcare`, 2026-08-08 20:21 UTC), instrumented
via the `CallLatencyMetric` table this audit added (`is_simulated=False`, real per-stage timing —
see `service.py:_record_latency`, called from `handle_recording_webhook`). Customer said "చెప్పు"
("go ahead") in reply to the greeting:

| Stage | Duration |
|---|---|
| Twilio recording fetch | 390ms |
| STT transcribe | 268ms |
| Domain vocabulary load | 22ms |
| Extraction (LLM call) | **1,864ms** |
| Planning | 0ms |
| RAG | **2,735ms** |
| Generation (LLM call) | **1,017ms** |
| TTS synthesize | **2,768ms** |
| **Total backend processing** | **9,098ms** |

That's **9.1 seconds of backend processing alone**, on top of the `timeout` seconds of silence
Twilio already waited, on top of Twilio then fetching the reply audio afterward. Two findings this
directly surfaces, both already predicted by the migration spec and now confirmed with evidence
rather than assumed:

- **Two fully serial LLM calls per turn** (extraction, then generation) — 2.9 seconds combined,
  never overlapping. A real target for combining into one structured call (spec §46).
- **RAG took 2.7 seconds and probably shouldn't have run at all** — "చెప్పు" is not a question. The
  real-mode extractor's LLM likely misclassified `detected_question=True` for an ambiguous short
  imperative. `raw_model_output` isn't persisted anywhere queryable today (`ExtractionResult` holds
  it only in-memory for the one turn — `jkr_conversation/schemas.py`), so this can't be
  root-caused retroactively; it needs either persisting that field for future turns or a
  conditional-RAG fast path (spec §32) that doesn't fully trust the classification for short
  utterances.

## 4. A real regression this audit's baseline call caught and fixed

The **second** turn of the same call failed completely: the agent asked an open-ended question
("describe your issue"), and Twilio's recording came back with STT successfully executed but
returning empty text — not a network failure, an empty capture. `handle_recording_webhook`'s
`if not speech_result:` branch fired, and the call was abandoned with "We seem to have lost your
response."

Root cause: `<Record timeout>` had been tuned down to 2 seconds in an earlier latency pass. Twilio
docs confirm this single timer governs *both* "how long to wait for speech to start" and "how long
to wait after speech ends" — there's no way to configure these separately via `<Record>`. "చెప్పు"
was an instant reflex reply so it survived fine; the follow-up open-ended question needed genuine
thinking time, exceeded 2 seconds before the customer started talking at all, and Twilio ended the
recording on pure silence.

Fixed in this pass: `RECORD_SILENCE_TIMEOUT_SECONDS` raised from 2 to 4
(`service.py`, near the top of the file) — prioritizing never silently dropping a real reply over
shaving off dead-air, since an abandoned call is a categorically worse outcome than an extra
second of gap. **This entire class of bug is structural to `<Record>`** — a real streaming VAD
(§8) tracks "still thinking" separately from "done talking," so it doesn't exist once the
migration lands. It is not fully fixable by threshold-tuning `<Record>` alone.

## 5. What's already "streaming" — and what genuinely isn't

**Nothing on the audio path streams today.** The one piece of real concurrency in the whole
system: `start_live_test_call()` synthesizes the greeting via Sarvam TTS *in parallel* with
`telephony.create_call()` (`asyncio.gather`, `service.py`), so the greeting is ready before the
customer picks up instead of being synthesized after. That's the full extent of it.

Everything else — STT, extraction, RAG, generation, TTS — is one REST call per turn, fully
awaited, batch in and batch out. `<Record>` itself is definitionally batch: it can't hand
anything to us until the whole utterance is captured as a file.

## 6. What can be reused as-is

The entire conversation intelligence layer needs **zero rewrite** for this migration — it already
has no dependency on how audio gets in or out:

- `jkr_conversation.engine.process_turn()` — the single shared entrypoint both Test Lab and real
  calls already use. This is exactly the seam the migration should build on top of, not around.
- Extraction, domain normalization (`domain_normalizer.py`), multi-dimensional confidence,
  confirmation-policy enforcement, closing system (`closing.py`), DEFER_QUESTION,
  acknowledgement detection — all pure/DB-backed logic, transport-agnostic already.
- RAG (`rag.py`) — logic is fine; latency is the issue (§3), not architecture.
- `ConversationPolicy.min_interruption_ms` / `accidental_interruption_phrases` — already exist in
  the DB schema (`packages/db/jkr_db/models/agents.py`), already used by
  `services/voice-worker/app/turn_manager.py`'s interruption classification (phrase-list +
  word-count + timing). That classification *logic* is directly reusable; only its input
  (currently simulated wall-clock timing, not real VAD frames) needs to change. Real backchannel
  vs. interruption detection can build on this rather than starting from nothing.
- `CallLatencyMetric` / `InterruptionEvent` tables — already exist, already used by voice-worker's
  simulated path, now also used by this audit's real instrumentation (§3). No new schema needed
  for basic per-stage timing or interruption logging.
- Twilio signature validation (`validate_twilio_signature`) — correct and reusable for any
  webhook that stays HTTP; note in §9 on what changes for the WebSocket upgrade request itself.

## 7. What needs replacement

- **`<Record>` as the primary transport** — replace with Twilio Media Streams
  (`<Connect><Stream>`, bidirectional WebSocket) for the live-call path. `TwilioClient` in
  `twilio_telephony.py` only knows how to place a call with a plain webhook URL today; it has no
  Media Streams support at all.
- **Batch STT/TTS REST calls** — Sarvam has real streaming WebSocket APIs for both (STT: Saaras
  v3 realtime, partial + final transcripts; TTS: Bulbul v3, audio streamed as text is fed in) that
  the current `sarvam_stt.py`/`sarvam_tts.py` don't use at all. This is a smaller lift than
  switching vendors — same provider, different endpoint.
- **Two serial LLM calls per turn** — combine extraction + next-action classification into one
  structured call where possible (spec §46); confirmed costly in §3's real data (2.9s combined).
- **Fixed-timer turn detection** — `<Record timeout>` replaced by real VAD-based endpointing
  once on Media Streams; directly closes the §4 regression class.
- **Unconditional/uncached RAG on every question-shaped turn** — needs a fast path for
  non-knowledge turns and a semantic cache for repeat FAQs (spec §32-34); §3 shows a single RAG
  call costing 2.7s uncached.
- **No barge-in / interruption anywhere in the real-call path** — `<Record>` fundamentally cannot
  support it; needs Media Streams' bidirectional audio plus playback cancellation.

## 8. What voice-worker's `TurnManager` shows about the target design — and its limit

`services/voice-worker/app/turn_manager.py` already implements the *decision logic* for
interruption classification (meaningful vs. false-positive/backchannel) using a phrase list, word
count, and elapsed time against an *estimated* agent-speaking window
(`estimate_speaking_duration_ms`, ~55ms/char). This is real, working classification logic — it
just runs on simulated timing (`docs/DECISIONS/0002-voice-runtime.md`'s explicit, deliberate
choice) rather than real audio/VAD frames. The real-time migration's turn detector should port this
classification logic, not discard it, and feed it real VAD/STT timing instead of a text-length
estimate.

## 9. Migration risks

- **WebSocket auth differs from the current REST webhook pattern.** `validate_twilio_signature`
  (HMAC over the exact URL + sorted POST params) applies to Twilio's REST-style webhooks; the
  Media Streams WebSocket upgrade request is a distinct connection type. Twilio does sign the
  initial HTTP upgrade request the same way, but this needs explicit verification against current
  Twilio docs before relying on it — do not assume the existing helper covers the socket without
  checking (spec §95 flags this correctly).
- **`docker-compose.yml` already has a `livekit` service** (dev-mode container, `--dev --bind
  0.0.0.0`) and `services/voice-worker/app/providers/base.py` defines a `MediaRuntime` Protocol —
  but there is **no actual LiveKit adapter implementation anywhere in the codebase**; `mock.py`'s
  `MockMediaRuntime` is the only implementation of that Protocol. LiveKit is real infrastructure
  and a real interface with zero real logic behind either — worth knowing before assuming it's
  further along than it is.
- **Single-process dev deployment.** `docker-compose.yml`'s `api` service runs one uvicorn process,
  no visible multi-worker/replica config. Persistent per-call WebSocket state (session objects,
  provider connections) has no cross-process/session-affinity concern *yet* — but this becomes a
  real design question the moment `api` is horizontally scaled, and should be designed for from
  the start rather than retrofitted.
- **Sequential-call-history/idempotency assumptions.** `_persist_turn`'s `next_sequence_index`
  counter and the Redis-cached call `state` dict (`_redis_key`) assume one webhook in flight at a
  time per call. A real-time session with concurrent partial-transcript/speculative-RAG/streaming-
  generation work needs explicit turn/sequence IDs (spec §27-30) before any of that concurrency is
  safe — this is not optional plumbing, it's what prevents replayed/stale audio and race-condition
  replies once work is actually happening in parallel.
- **Cost model changes.** Streaming STT/TTS and a persistent Media Streams connection bill
  differently than today's discrete REST calls. Track `cost_per_completed_minute` (spec §75)
  before defaulting the new path on for all traffic.

## 10. Rollout strategy

Keep the current batch pipeline as the default and only fallback until the new path has real-call
parity — this document's own §4 is a concrete example of why: real phone calls surface failure
modes (a customer's natural thinking pause) that don't show up in code review or unit tests.
Feature-flagged, phased, in this order (mirrors the migration spec's own §111):

1. Media Streams transport (keep batch Sarvam STT/TTS initially, to isolate the transport change)
2. Streaming Sarvam STT + real VAD/endpointing (replaces the `<Record timeout>` failure class
   directly — §4)
3. Streaming LLM + sentence-boundary chunking
4. Streaming Sarvam TTS, playback starting on the first chunk
5. Full pipeline concurrency + barge-in + sequence-ID replay protection
6. RAG fast-path/caching, combined extraction+planning call

Each phase behind its own flag (`VOICE_TRANSPORT_MODE`, `STT_MODE`, `TTS_MODE`), each verified
against a real call with the same per-stage `CallLatencyMetric` instrumentation this audit
introduced, before being promoted to default. Do not remove `<Record>`-based handling until the
new path has been proven on real calls, not just passing tests — exactly as this audit's own
baseline call demonstrated is necessary.

## 11. P2 — Twilio Media Streams migration (completed)

Full detail: `docs/TWILIO_MEDIA_STREAMS.md`. Summary of what changed relative to §10's plan:

- **Transport implemented, behind `TWILIO_VOICE_TRANSPORT=media_stream`** (default remains
  `record` — zero behavior change for any environment that doesn't opt in). New module tree:
  `services/api/app/modules/live_call/transport/` (`base.py`, `media_tokens.py`, `schemas.py`,
  `audio_codec.py`, `events.py`, `session.py`, `transitional_bridge.py`, `twilio_media_stream.py`).
  `service.py`'s only change is one additive branch in `handle_voice_webhook`; every existing
  `<Record>`-mode function is untouched.
- **STT/TTS deliberately stayed batch in this phase**, exactly as §10 planned — Sarvam calls are
  triggered by a transitional trailing-silence turn buffer instead of a `<Record>` callback, but
  are otherwise the identical `SarvamSTT.transcribe()`/`SarvamTTS.synthesize()` calls `<Record>`
  mode already used. This directly proves the transport layer in isolation, per §10's stated
  reasoning for sequencing it first.
- **Housed in `services/api`, not `services/voice-worker`** — a deliberate deviation from the
  original migration spec's suggested default, justified because `services/api` already runs as a
  persistent (non-serverless) process and already owns all real-call Twilio/Sarvam integration;
  see `docs/TWILIO_MEDIA_STREAMS.md` §2 for the full reasoning.
- **Verified**: 257 tests passing repo-wide (88 in `services/api`, up from 41 — 47 new, zero
  regressions), including a real end-to-end integration test (real Postgres `CallSession`, real
  Redis state, a real WebSocket connection via FastAPI's `TestClient`, real
  `jkr_conversation.engine.process_turn()` — only Sarvam's network calls mocked) proving a
  simulated call's greeting, transcription, engine turn, and reply all actually flow through the
  new transport correctly. Not yet verified against a real Twilio phone call — that requires the
  user's own test call against a running server, same as every other phase in this project.
- **Known, documented gaps** (not silently absent): no real VAD (P4), no barge-in (P8, though
  `clear_agent_audio()` exists and is tested as a primitive), no streaming STT/TTS (P3/P6), no
  sequence-ID replay enforcement (P9, though the `response_sequence_id`/`chunk_index` fields
  P9 needs already exist on every outbound chunk), no TTS-failure fallback mid-stream (`<Record>`
  mode falls back to Twilio's own `<Say>`; Media Stream mode has no further TwiML round-trip to
  fall back into once the stream is active), `TWILIO_MEDIA_STREAM_FAILURE_POLICY=fallback_record`
  is a defined setting with no implementation behind it yet. Full list:
  `docs/TWILIO_MEDIA_STREAMS.md` §9.

**Recommended next phase: P3** — Sarvam's real streaming STT (partial + final transcripts),
replacing `transitional_bridge.py`'s trailing-silence heuristic entirely, per §10's own sequencing.

## 12. P3 — audit of the path being replaced, and real-call latency evidence

Before writing any streaming code, this section traces the exact current flow and records real
measurements from a live test call (`0066d4d3-edcb-4066-ba45-5a8bf825a92e`, 2026-08-08, media_stream
transport) that motivated P3, so the "why" is grounded in data, not assumption.

### 12.1 Current flow, traced exactly

1. `twilio_media_stream.py::_receive_loop` decodes each inbound Twilio `media` event (base64
   mu-law → PCM16, `audio_codec.decode_twilio_media_payload`) and calls
   `session.enqueue_inbound_audio(frame)` — non-blocking, bounded queue, never does STT work inline.
2. `twilio_media_stream.py::_processing_loop` dequeues frames and feeds each one to
   `transitional_bridge.TurnBuffer.add_frame()`, which runs `audioop.rms()` per frame to classify it
   as speech or silence and accumulates `trailing_silence_ms`/`speech_ms`/`total_ms`.
3. Once `TurnBuffer.is_turn_complete()` (≥4.0s trailing silence after ≥300ms of detected speech, or
   the 20s hard cap), the processing loop calls `turn_buffer.build_wav()` — the ENTIRE buffered turn
   is packaged into one in-memory WAV file — and hands it to
   `transitional_bridge.process_transitional_turn()`.
4. `process_transitional_turn()` makes one blocking REST call: `SarvamSTT.transcribe()` →
   `POST https://api.sarvam.ai/speech-to-text` (multipart file upload, `model="saaras:v4"`,
   `mode="codemix"`, pinned `language_code`) and awaits the full response before doing anything else.
5. Only after that REST round-trip completes does `jkr_conversation.engine.process_turn()` run
   (extraction → domain normalization → RAG → planning → generation), then tool execution, then
   `_persist_turn()`, then `synthesize_for_stream()` (another blocking REST call to Sarvam TTS).

This means: **the customer's audio is invisible to any transcription process until they stop
talking for 4 full seconds** — nothing streams, nothing is incremental, and the entire STT step is a
single request-response REST call sized to the whole utterance. This is the exact thing P3 replaces.

### 12.2 What the real call's numbers actually show

Per-turn latency, averaged across the 6 customer turns of that call (from `call_latency_metrics`):

| Stage | Avg | Max | What it is |
|---|---|---|---|
| `stt_transcribe` | 439ms | 590ms | The batch Sarvam REST call §12.1 step 4 |
| `engine_extraction` | 1993ms | 2701ms | LLM call inside `process_turn()` |
| `engine_rag` | 1679ms | 2233ms | LLM/embedding call, only some turns |
| `engine_generation` | 726ms | 1295ms | LLM call producing the spoken reply |
| `engine_domain_vocabulary` | 9ms | 20ms | Negligible |
| `engine_planning` | 0ms | 0ms | Negligible |

Two findings that directly shape P3's priority and its honest limits:

- **STT is not the dominant cost** — it's roughly 10-15% of the ~3.1-4.8s a turn takes end to end.
  The bulk is the sequential LLM chain (extraction → RAG → generation) inside `ConversationEngine`,
  which is explicitly out of scope for P3 (that's `packages/conversation` engine work, not a
  transport/STT concern). **Streaming STT will shave real time off the critical path** — mainly by
  overlapping transcription with the tail of the customer's speech instead of waiting 4s of silence
  plus a full REST round-trip after they finish — but it will not, by itself, fully resolve the "so
  much lag" experience the user reported. That requires a separate pass at the engine's LLM chain
  (parallelizing extraction/RAG, or streaming generation) — noted here as a follow-on, not started.
- **The apparent conversational "desync"** in that same call (an English-only reply mid-Telugu
  conversation; the closing text repeating verbatim after a grace-period reopen) was **not** state
  corruption — both were explainable, narrower bugs, root-caused directly against this call's
  `call_events` rows and fixed in this same pass: the code-mixed language instruction in
  `jkr_conversation/prompt_builder.py::_language_instruction()` allowed a fully English sentence
  (now forbidden explicitly); and `_reopen_conversation_state()` had no way to signal "this
  completion is a re-affirmation, not a fresh close" to `prompt_builder.generate()`, so it replayed
  the identical closing script (now uses `closing.REOPENED_REAFFIRM`, a short distinct line, when
  `state["reopened_from_closing"]` is set). Both fixes are in `packages/conversation`, both are
  transport-independent, and both apply to `<Record>` mode too.

### 12.3 What P3 replaces

`transitional_bridge.py`'s `TurnBuffer` (energy-based turn segmentation) and its one-shot
`SarvamSTT.transcribe()` call are the target. `jkr_conversation.engine.process_turn()` and everything
downstream of it (extraction, domain correction, RAG, planning, generation, closing) stays completely
unchanged — P3 only changes how a final transcript *arrives*, never what happens once it does.

## 13. P3 — Sarvam streaming STT migration (completed, real-call verification pending)

Full detail: `docs/SARVAM_STREAMING_STT_CONTRACT.md` (researched provider contract),
`docs/TWILIO_MEDIA_STREAMS.md` §15 (architecture as shipped),
`docs/P3_STREAMING_STT_RESULTS.md` (verification status and the explicit real-call plan). Summary:

- **`STT_MODE=streaming` implemented against Sarvam's Realtime API** (`saaras:v3-realtime`),
  selected over the Legacy Streaming API specifically because it's the only one with native 8kHz
  mu-law/PCM16 support, true partial transcripts, and mid-call reconfiguration — verified via raw
  AsyncAPI spec research and the installed `sarvamai` SDK source, not guessed from the P3 prompt's
  own example schemas.
- **`transitional_bridge.TurnBuffer` was not deleted** — it remains the permanent `STT_MODE=batch`
  implementation and the `STT_STREAM_FAILURE_POLICY=batch_next_turn` fallback, a deliberate
  deviation from this doc's earlier §7 statement that P3 would delete it outright (that statement
  predated the decision to keep batch as an explicit, first-class fallback rather than an emergency
  patch).
- **`process_known_transcript_turn()` extracted** so the persist → `ConversationEngine` → tools →
  reply pipeline is shared, byte-for-byte, between batch and streaming STT — proven via an
  integration test asserting exactly one `CallTurn` row per `FinalTranscript` event.
- **Two real-call bugs fixed in this same pass**, both transport-independent (§12.2 above):
  the code-mixed language instruction now forbids a fully-English reply mid-Telugu conversation, and
  a grace-period reopen that re-completes the objective now gets a short reaffirmation instead of
  the full closing script repeated verbatim (`closing.REOPENED_REAFFIRM`).
- **Verified**: 290 tests passing repo-wide (118 in `services/api`, up from 88 — 30 new, zero
  regressions), including an integration test proving real audio frames flowing through the real
  receive-loop trigger the real engine exactly once per utterance, and a second integration test
  proving the `batch_next_turn` failure policy keeps a call alive when the streaming connection
  can't be established.
- **Not verified**: any real connection to Sarvam's Realtime STT endpoint. Sarvam's own
  documentation gives an ambiguous beta-access signal for this specific endpoint; this project's API
  key has never actually opened a connection to it. No streaming-vs-batch latency comparison exists
  yet — only the P2 batch baseline (§12.2) is real. `docs/P3_STREAMING_STT_RESULTS.md` has the full,
  explicit real-call verification plan.
- **Known finding carried forward, not resolved by P3**: STT was never the dominant latency cost
  (§12.2) — the `ConversationEngine`'s sequential extraction/RAG/generation LLM chain is 5-10x
  larger. Streaming STT is real, correct, and worth having, but will not by itself resolve the "so
  much lag" complaint that motivated this phase.

**Recommended next steps**: (1) place a real call with `STT_MODE=streaming` to confirm Sarvam
Realtime API access and capture real latency numbers; (2) a separate pass at the
`ConversationEngine`'s LLM chain latency (parallelizing extraction/RAG, or streaming generation),
which the P2/P3 real-call data both point to as the larger lever; (3) P4 (true turn detection) once
either or both of the above are in place.

## 14. P3.5 — ConversationEngine latency optimization (completed)

Full detail: `docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md`, `docs/P3_5_CONVERSATION_ENGINE_RESULTS.md`.
Direct provider probes (not mocks) showed the engine was already more consolidated than assumed
(extraction already combines field-extraction/intent/question-detection/safety-flags into one call;
the planner is pure Python, 0ms; RAG was already conditional) and that raw OpenAI API latency from
this network path (~1.6-2s per call) dominates over connection-reuse overhead. Shipped: a
deterministic `FastTurnRouter` (zero-LLM handling for do-not-call/wrong-number/human-handoff/
confirmation-yes-no/acknowledgement-only — measured 100% LLM elimination on those turns), a fast
canned-response path reusing already-tested templates for safe ASK_FIELD/CLARIFY/CONFIRM_FIELD/
DEFER_QUESTION turns (measured 700-1100ms saved per turn), connection-reuse fixes, fine-grained RAG
timing, `CONVERSATION_ENGINE_MODE=legacy|fast` (default `legacy`). 127 tests in
`packages/conversation` (106 + 21 new), zero regressions.

## 15. P4 — Turn detection, VAD & endpointing (completed, DB-integration verification pending)

Full detail: `docs/P4_TURN_DETECTION_AUDIT.md`, `docs/TURN_DETECTION_ARCHITECTURE.md`,
`docs/P4_TURN_DETECTION_RESULTS.md`. The audit found Sarvam's `FinalTranscript` was directly
triggering `ConversationEngine.process_turn()` with zero coalescing/semantic gating (a "Tomorrow" /
"actually evening better" thinking pause would have produced two separate engine calls), and that
Sarvam's own `SpeechEnded` event was received and silently dropped entirely.

Shipped: a new provider-neutral `services/api/app/modules/live_call/turns/` package — `TurnManager`
(pure, synchronous, fake-clock-testable), an explicit turn state machine, a normalized signal model,
a rule-based `SemanticCompletenessEvaluator` (no LLM call, per this phase's own explicit warning not
to reopen P3.5's latency work), a context-aware `BackchannelClassifier`, and a local `EnergyVAD`
(RMS-energy — no Silero/ONNX/LiveKit dependency exists anywhere in this repo, confirmed before
writing code, so none was added speculatively). `streaming_bridge.py` rewired so only a
`TurnManager`-issued `COMMIT_TURN` decision reaches the engine; `TURN_DETECTION_MODE=provider`
(default) reproduces the exact pre-P4 immediate-commit behavior. `vad`/`hybrid` modes exist behind
the same flag, never auto-enabled.

**Verified**: 68 new unit tests (deterministic, fake-clock, no DB), zero regressions in P2/P3's
existing reconnect/dedup/failure-policy tests. A real design bug (three commit-timing budgets
competing rather than composing) was caught and fixed by these tests before ever reaching an
integration test. **Not verified**: two new integration tests
(`test_turn_detection_integration.py`) were written but could not be run — the Docker daemon was
unavailable on this machine for this entire session (confirmed via `docker compose ps` failing to
even reach the daemon, not a container-level issue affecting only this phase). No real phone call has
been placed with `TURN_DETECTION_MODE=hybrid`.

**Recommended next steps**: (1) start Docker and run the full test suite including the two new
integration tests — this is the single most important remaining step, more urgent than a real call;
(2) once green, place a real call per `docs/P4_TURN_DETECTION_RESULTS.md`'s manual verification plan
and compare `provider` vs `hybrid` mode on the same scripted utterances; (3) P5/P6 (streaming
generation/TTS) or P8 (barge-in, now that `TurnManager` reliably produces `USER_SPEECH_STARTED`)
after that.

## 16. P5 — Streaming LLM response generation (completed, real-call verification pending)

Full detail: `docs/P5_STREAMING_LLM_AUDIT.md`, `docs/STREAMING_LLM_ARCHITECTURE.md`,
`docs/P5_STREAMING_LLM_RESULTS.md`. Before writing any P5 code, ran the P4 DB verification gate this
phase's own spec required and found a real, previously-invisible bug: `asyncio.wait_for(anext(async_
generator), timeout=...)` permanently kills the generator if the timeout fires mid-body — dormant since
P2/P3's 1.0s poll, made reliably reproducible by P4's 0.1s hybrid-mode poll. Fixed via a dedicated
drain task feeding a plain `asyncio.Queue`, timeout applied only to the safe-to-cancel queue read.
353 tests confirmed passing repo-wide before any P5 change — the real baseline this phase is measured
against, superseding the earlier "311" figure quoted before this session's Docker outage.

The audit found the entire response-generation path was a single buffered
`OpenAILLMClient.complete_text()` call — no `stream=True` anywhere in the codebase, the full response
body buffered by `httpx` before any of it was usable. No `openai` SDK is installed (confirmed via
`uv.lock`); every provider integration here hand-rolls raw `httpx`, so P5 continued that convention
rather than adding a new dependency. Verified OpenAI's actual SSE contract live against the real API
before writing the parser (documented with the raw example lines in the audit doc).

Shipped: `streaming_llm.py` (`StreamingLLMProvider` protocol, never-raising SSE parser with full
failure classification), `speakable_chunker.py` (`SpeakableChunker` — chunk boundaries are
content-driven, never timing-driven, by construction), `streaming_response.py`
(`StreamingResponseAssembler` — ties provider events to the chunker to a streaming-safe formatter,
full timing/usage/cancellation tracking, a real-time `on_chunk` callback, guaranteed generator cleanup
on every exit path), `_shared_http.py` (breaking a circular-import risk between `llm_client.py` and
`streaming_llm.py`), `OpenAILLMClient.stream_text()`, and four new additive, no-op-by-default keyword
params on `prompt_builder.generate()` (`response_mode`/`on_speakable_chunk`/`latency_sink`/
`cancellation_token`) threaded through `engine.process_turn()` into the same `latency_ms` breakdown
`rag_embedding`/`rag_vector_search` already populate. `LLM_RESPONSE_MODE=complete` (default) reproduces
the exact pre-P5 behavior; `=streaming` opts in, wired into both real-call `process_turn()` sites in
`services/api`. TTS stays batch either way — P5 does not touch the customer-audible path.

A real bug was caught live during this phase's own benchmarking, not hypothesized: 2 of 3 initial
streamed responses opened with a bare English "Sure!" before the actual Telugu-English/Hindi-English
content, despite the language policy. Fixed via an explicit "never open with a generic filler" prompt
instruction — re-confirmed clean across a broader 10-run benchmark afterward.

**Verified**: 410 tests passing repo-wide (353 baseline + 57 new: chunker boundary tests, SSE-parsing
and failure-classification tests, assembler tests including a proof that `gen.aclose()` actually runs
on early cancellation, prompt-builder tests proving canned/fast-path actions structurally never reach
streaming, and real-Postgres engine-level tests proving RAG-before-streaming ordering and two-call
generation-id isolation). A real-provider benchmark (10 streaming + 5 complete-mode runs, live OpenAI
API, five categories spanning Telugu-English/Hindi-English/English, RAG/no-RAG/objection/multi-intent)
found streaming TTFT P50 855ms / P95 1429ms, first-speakable-chunk P50 1069ms / P95 1610ms, full
generation comparable to complete mode (~1.0-1.2s either way) — streaming exposes an earlier partial
result without being slower overall, consistent with the audit doc's earlier 3-run finding.

**Not verified**: no real phone call has been placed with `LLM_RESPONSE_MODE=streaming` — `.env` has it
unset (default `complete`), consistent with every previous phase's policy of never flipping a
response-path-changing flag live without the user's own test call. No streaming TTS, LLM→TTS
concurrency, generation-ownership lock, backpressure observation, or debug-trace UI exposure — all
explicitly scoped out or deferred to P6/P8/P9, not silently claimed done.

**Recommended next steps**: (1) place a real call with `LLM_RESPONSE_MODE=streaming` per
`docs/P5_STREAMING_LLM_RESULTS.md`'s manual verification plan and compare against `complete` mode on
the same scripted turns; (2) P6 (streaming TTS — the first phase that makes any of P5's chunking
actually audible to a customer); (3) P8 (barge-in, now that both `TurnManager` and
`CancellationToken` exist as the two halves that phase will connect).

## 17. P6 — Streaming TTS (completed, real-call verification pending)

Full detail: `docs/P6_STREAMING_TTS_AUDIT.md`, `docs/SARVAM_STREAMING_TTS_CONTRACT.md`, `docs/
STREAMING_TTS_ARCHITECTURE.md`, `docs/P6_STREAMING_TTS_RESULTS.md`. The audit found the entire TTS path
was a single blocking REST call per turn — `SarvamTTS.synthesize()` on the complete reply text, base64
WAV decoded in full before any audio reached Twilio — and that P5's `on_speakable_chunk` hook, though it
existed, was never actually wired to anything in `services/api`. It also found a real, if
rarely-triggered, closing-grace bug: both turn loops started the grace-period timer the instant a
reply's audio was *enqueued*, not once Twilio had actually finished *playing* it.

Verified Sarvam's streaming TTS WebSocket contract live before writing any provider code, because the
docs themselves turned out to be stale (claiming "MP3 only, currently supported" for
`output_audio_codec`). Live probes found `output_audio_codec=mulaw` + `speech_sample_rate=8000` returns
raw, headerless audio in Twilio's *exact* wire format — no resampling, no re-encoding, no container
parsing needed for the common case. Also found live: Sarvam's `request_id` is scoped to the whole
connection, not per-response, so this codebase's own `response_id` bookkeeping (reusing P5's
`SpeakableChunk.response_id` end-to-end) is the only way to correlate audio with the turn it belongs to.

Shipped: a provider-neutral `StreamingTTSProvider` abstraction + the real `SarvamStreamingTTS` client;
`TTSStreamingSession` (one persistent connection per call, connected early — before the greeting, not
after the first real turn — so handshake latency is paid once, never per-turn), an ordered text-sender
task, and an audio-consumer task; `TTSResponseHandle`/`begin_response_feed()` so BOTH an LLM-streamed
response (fed via `on_speakable_chunk`, wired into `process_turn()` for real this time) and an
already-fully-known response (canned/fast-path/complete-mode text, locally chunked via P5's own
`SpeakableChunker`) get the same early-audio treatment; `speak_turn_reply()` unifying both turn loops'
reply-to-audio logic with a streaming-with-batch-fallback policy (fall back to batch only if literally
no audio was ever sent for a response; never an automatic replay once some audio already played); the
real closing-grace fix via a new `RealtimeMediaSession.wait_for_mark_ack()` and enqueue-time mark-name
assignment; a minimal generation-ownership lock (supersede, not full P9 replay protection); and a
dead-connection timeout found and fixed while building this (a stalled TTS connection with no completion
event would otherwise have hung a turn forever). `TTS_MODE=batch` (default) reproduces pre-P6 behavior
exactly; `=streaming` opts in, gated on `TWILIO_VOICE_TRANSPORT=media_stream` the same way every other
transport-dependent flag in this codebase already is.

**Verified**: 463 tests passing repo-wide (410 baseline + 53 new, all in `services/api`) — provider wire
format, strict text/audio ordering, the exact failure-before-vs-after-audio fallback distinction,
generation-ownership supersede, two-call isolation, mark-wait timing (including cleanup and
never-confusing-two-different-marks), and — directly, at the byte level — that a streamed audio chunk
reaches Twilio with **no RIFF/WAVE/ID3 header** and uses the mark name assigned at enqueue time. A
real-provider benchmark (10 live connections, same five categories P5's own benchmark used) measured TTS
connect P50 140ms / P95 169ms and first-audio P50 218ms / P95 238ms, zero failures — combined with P5's
own first-speakable-chunk numbers, this estimates turn-committed-to-first-audio-ready at roughly 1.3s
(P50) / 1.85s (P95), the first concrete end-to-end figure this migration has produced.

**Not verified**: no real phone call has been placed with `TTS_MODE=streaming`. No full DB-backed
integration test (real engine + real TurnManager + mocked provider network boundary only) was written —
every layer is unit-tested independently, but not stitched into one combined real-time assertion. No
audio-quality/prosody/chunk-seam human listening review (cannot be done inside this session). TTS
WebSocket reconnect is not implemented (a dropped connection mid-call isn't re-established for later
turns, though the dead-connection timeout prevents a hang on the current one). `VoicePersona.
speaking_speed` still isn't wired into the pace parameter — the same pre-existing gap the batch path
already had.

**Recommended next steps**: (1) place a real call with `TTS_MODE=streaming` per `docs/
P6_STREAMING_TTS_RESULTS.md`'s manual verification plan and actually listen to it, comparing against
`TTS_MODE=batch` on the same script; (2) P8 (barge-in) — `TurnManager`'s `USER_SPEECH_STARTED`,
`CancellationToken`, and `StreamingTTSProvider.cancel()` all now exist as independent, tested primitives;
P8's job is wiring them together, not building them from scratch; (3) TTS WebSocket reconnect, if real
calls show it's needed in practice.

## 18. P7 — Realtime pipeline coordination, backpressure & playback accounting (completed, real-call verification pending)

Full detail: `docs/P7_REALTIME_PIPELINE_AUDIT.md`, `docs/REALTIME_PIPELINE_COORDINATOR.md`, `docs/
PLAYBACK_ACCOUNTING.md`, `docs/BACKPRESSURE_ARCHITECTURE.md`, `docs/P7_REALTIME_PIPELINE_RESULTS.md`.
P7 is not another provider migration — every major realtime component (streaming STT, `TurnManager`,
`ConversationEngine`, streaming LLM, streaming TTS) already worked independently by P6; the problem P7
solves is that "which response owns the call's audio right now" was answered differently, and
separately, by three different pieces of state (`RealtimeMediaSession`'s own response-sequence counter,
`TTSStreamingSession`'s own `_active_response_id`, and nothing at all above the TTS layer).

Shipped a single call-scoped `RealtimePipelineCoordinator`: an explicit `ResponseState` lifecycle (11
states, 4 terminal), an `ActiveResponseContext` that tracks generated/committed-to-TTS/sent/acknowledged
text and audio as genuinely distinct quantities (never one ambiguous `response_completed` boolean), a
`PlaybackUnit` model (one per audio chunk actually sent to Twilio — the precisely-trackable granularity,
not the spec's literal per-LLM-chunk framing, which Sarvam's own buffering doesn't actually preserve)
with a real PLAYED-vs-CLEARED distinction backed by clear-epoch bookkeeping, and an `InterruptionSnapshot`
+ `interrupt_active_response()` primitive for P8 to call later (not wired to anything automatic yet).
Every streaming response — LLM-generated or locally-chunked canned/fast-path text — now routes through
`begin_response_feed()`/`CoordinatedResponseHandle`, which P6's `speak_turn_reply()` accepts unchanged
thanks to duck-typing. Also shipped: bounded TTS reconnect between responses (idle-only, generation-
isolated, never mid-response), `VoicePersona.speaking_speed` finally wired to Sarvam's `pace` parameter
(clamped to `bulbul:v3`'s verified range), a fix for the one unbounded hot-path queue the audit found
(streaming-STT's event queue), and process-wide event-loop lag monitoring exposed on `/health`.

Three real bugs were found and fixed *during* this phase's own development, not by inspection:
(1) the coordinator's first implementation reached directly into `TTSStreamingSession`'s private
provider for cancellation, letting the two layers' bookkeeping disagree — fixed by extracting a shared
`TTSStreamingSession.cancel_response()` method both now call; (2) mark-acknowledgement handling only
guarded against a CLEARED unit, not an already-ACKNOWLEDGED one, so a redelivered mark event would have
double-counted acknowledged audio — fixed and regression-tested; (3) the first TTS reconnect
implementation only bounded attempts *within* one reconnect cycle, not the total number of cycles — a
connection that succeeds its handshake but immediately drops again would have spun forever; caught when
it hung the test suite, fixed with an overall cycle cap.

**Verified**: 497 tests passing repo-wide (463 baseline + 34 net new, all in `services/api`) — response
lifecycle and ownership, supersede vs. cancel, duplicate mark-ack idempotency, the PLAYED/CLEARED
distinction (including a late ack after clear provably not resurrecting a cleared unit), `Interruption
Snapshot` correctness, bounded TTS reconnect (idle succeeds, mid-response correctly does NOT reconnect,
cycles are bounded, all-attempts-failure gives up cleanly), event-loop lag detection (a deliberate
synchronous block produces a measurable spike), two-call isolation, and — the concurrency proof spec
§149-150 asked for — a real integration test combining real `StreamingResponseAssembler` + real
`SpeakableChunker` + real `RealtimePipelineCoordinator` + real `TTSStreamingSession` + a real
`RealtimeMediaSession`'s real outbound queue (only the LLM token stream and the Sarvam WebSocket faked)
proving the first Twilio-bound audio chunk arrives, and the coordinator has already transitioned to
`TTS_STREAMING`, measurably *before* the LLM's own full-generation time — not a sequence-of-calls
approximation.

**Not verified**: no real phone call has been placed with the coordinator active. No load test (1/10/25/
50/100 concurrent simulated calls) — this environment has no realistic way to generate meaningful
concurrent-call load. No repeated create/destroy orphan-task/memory-leak test. Playback lookahead is
*measured* (`twilio_playback_backlog_ms` is real and tested) but not *enforced* — nothing yet pauses
TTS→Twilio forwarding when the backlog grows large. Dead-air classification is a real, tested, on-demand
function; no live polling/alerting task calls it periodically yet.

**Recommended next steps**: (1) place a real call with the P7 coordinator active (no new flag required —
it activates automatically alongside `TTS_MODE=streaming`) and confirm the event log shows exactly one
`pipeline_response_begin` per turn with no unexpected supersessions; (2) P8 (barge-in) — `TurnManager`'s
`USER_SPEECH_STARTED`, `CancellationToken`, `StreamingTTSProvider.cancel()`, and now `interrupt_active
_response()`/`InterruptionSnapshot` all exist as independent, tested primitives; P8's entire job is
wiring a real interruption *policy* on top of them, not building new primitives; (3) playback-lookahead
enforcement and a real concurrent-call load test, both explicitly deferred this phase.

## 19. P8 — Automatic barge-in, interruption classification & natural recovery (completed, real-call verification pending)

Full detail: `docs/P8_BARGE_IN_AUDIT.md`, `docs/BARGE_IN_ARCHITECTURE.md`, `docs/INTERRUPTION_POLICY.md`,
`docs/INTERRUPTED_RESPONSE_HISTORY.md`, `docs/P8_BARGE_IN_RESULTS.md`.

P8's job, exactly as P7 left it: wire a real interruption *policy* on top of primitives that already
existed and worked (`interrupt_active_response()`, `TurnManager`'s speech signals,
`backchannel.classify()`) — not build new primitives from scratch. What the audit found instead was two
structural gaps that had to close first before any policy could act automatically: (1) the streaming
turn loop was fully serialized — it awaited response generation + TTS + playback inline, so provider-
signal-based interruption evidence (`SpeechStarted`, partial transcripts) physically could not be
observed while a response was in flight; (2) no path existed from the turn loop to a real Twilio clear
(`clear_agent_audio()` needs a `WebSocket`, which only the top-level connection handler has).

Shipped: `InterruptionPolicy` (`turns/interruption_policy.py`) — a pure, synchronous, no-LLM decision
function (`IGNORE`/`MONITOR`/`WAIT_FOR_MORE_AUDIO`/`BACKCHANNEL`/`INTERRUPT`/`INTERRUPT_CRITICAL`) reusing
`backchannel.classify()` and the existing DNC/wrong-number/human-handoff keyword backstop rather than
rebuilding either. A new `ResponseState.INTERRUPTED` terminal state, distinct from `CANCELLED`/
`SUPERSEDED`/`FAILED`. A hardened `interrupt_active_response()` implementing the full cancellation order
(idempotency guard → TTS cancel + Twilio clear concurrently, both timeout-bounded → `INTERRUPTED`
transition → conservative `InterruptionSnapshot`). A background-task restructure of the streaming turn
loop (`_dispatch_commit()`), gated entirely behind `BARGE_IN_ENABLED` so the inline-await path stays
byte-identical when it's off (the default). Conservative conversation-history repair
(`ActiveResponseContext.chunk_log` + `_conservative_delivered_text()`) so an interrupted response's entry
in `recent_turns` reflects only what was conservatively known-delivered, never the full generated text.
`BARGE_IN_ENABLED=false`/`BARGE_IN_SENSITIVITY=balanced` config, gated by the same cascading-
`effective_*` pattern every other realtime flag uses.

A real bug found and fixed during this phase's own development, by its own end-to-end integration test
failing (not by inspection): the background response *task* and the coordinator's `ActiveResponseContext`
have different lifetimes — the task finishes once generation and the initial audio hand-off to Twilio are
done, but the response stays audibly "active" until its audio actually finishes playing out over the
call. The first implementation gated interruption on `task.done()`, silently doing nothing once the task
had already finished — exactly the common "customer interrupts while the agent is mid-sentence, audio
already sent but not yet acknowledged" case. Fixed by gating on the coordinator's own active-response
state instead.

**Verified**: 537 tests passing repo-wide (497 baseline + 40 net new: 23 `InterruptionPolicy` unit tests,
10 coordinator interruption tests, 2 real end-to-end WebSocket integration tests, 5 config tests) — see
`docs/P8_BARGE_IN_RESULTS.md` for the full breakdown, including the two real end-to-end proofs (a
high-priority-cue interruption actually stops a streaming reply, sends a real Twilio clear, and answers
the new question; a mere backchannel does neither).

**Not verified**: no real phone call — `BARGE_IN_ENABLED` stays `false` until one validates it, per this
phase's own explicit instruction. Greeting playback is not routed through the coordinator, so barge-in
does not yet cover the greeting. Non-interruptible compliance-unit support exists and is tested but has
no real call site yet. Adaptive brevity is tracked (`recent_interrupt_count`) but not yet consumed by the
prompt/formatter. "Okay bye during closing may not require a full reopen" (an explicit spec "may not," not
a hard requirement) is not implemented — every confirmed closing interruption reopens unconditionally.

**Recommended next steps**: (1) place a real call with the staging flags
(`TWILIO_VOICE_TRANSPORT=media_stream`, `STT_MODE=streaming`, `TURN_DETECTION_MODE=hybrid`,
`CONVERSATION_ENGINE_MODE=fast`, `LLM_RESPONSE_MODE=streaming`, `TTS_MODE=streaming`, `BARGE_IN_ENABLED=
true`, `BARGE_IN_SENSITIVITY=balanced`) and run this phase's own 6-scenario script; (2) route the greeting
through the coordinator so barge-in can cover it too; (3) P9 — strict sequence/replay validation beyond
`is_current()`'s response-id check remains not started.

## 20. P9 — Strict stale-audio, duplicate-packet & replay-protection hardening (completed, real-call verification pending)

Full detail: `docs/P9_REPLAY_PROTECTION_AUDIT.md`, `docs/RESPONSE_IDENTITY_MODEL.md`,
`docs/REPLAY_PROTECTION_ARCHITECTURE.md`, `docs/REALTIME_OUTPUT_INVARIANTS.md`,
`docs/P9_REPLAY_PROTECTION_RESULTS.md`.

P9's own recommended next step from P8 ("route the greeting through the coordinator") and P7's own
"P9 — strict sequence/replay validation... remains not started" are both addressed. This was a
correctness/invariants phase, not new functionality: the goal was making stale or duplicated
customer-facing output structurally impossible, not adding a new conversational capability.

Shipped: a canonical, immutable `ResponseIdentity` (`call_id`/`turn_id`/`response_id`/`generation_id`/
`sequence_id`/`epoch`) every customer-facing artifact now carries; a call-scoped `response_epoch`
alongside the formalized `playback_epoch` (P7's own `_clear_epoch`, exposed under its P9 name); a single
final `CustomerFacingOutputGate` (`RealtimePipelineCoordinator.can_send_media()`) called from exactly one
place immediately before every real Twilio send; duplicate/conflict/gap detection at three independent
boundaries (`SpeakableChunk`, `TTSAudioChunk`, the output gate itself) sharing one pure decision function;
centrally-validated, monotonic response and playback-unit state transitions; the previously-dormant P5
`CancellationToken` actually wired end to end; proactive queue purging on invalidation; and — closing the
one bypass P8's own results doc flagged — the greeting now routed through the same coordinator/output-gate
ownership model as every other response.

Two real bugs were found and fixed during this phase's own development, both by tests failing, not by
inspection: (1) an early version of the `SpeakableChunk` identity check compared the assembler's own
internally-minted `generation_id` directly against the coordinator's unrelated one, silently rejecting
every genuine LLM-streamed chunk; (2) routing the greeting through the coordinator surfaced a real false-
positive in P8's own interruption-candidate logic (a response that finished generating but never formally
reaches a terminal state was being treated as "still active" forever, so the customer's first, unrelated
utterance was misclassified as barging in on the greeting) — fixed by checking for genuinely-still-
producing state or outstanding unacknowledged audio, not just "not terminal."

**Verified**: 587 tests passing repo-wide (537 baseline + 50 net new, all in `services/api`,
`tests/voice/replay/`) — including three chaos/property tests (randomized response churn, ten rapid
interruptions, a hundred rapid supersessions) all asserting `stale_audio_sent_total == 0`, and an extension
to P8's own real end-to-end WebSocket interruption test asserting the same zero-leak metric through the
actual `_send_loop` wiring, not just coordinator-level unit tests.

**Not verified**: no real phone call — replay-protection guards are always-on regardless (never gated
behind a flag, per this phase's own instruction), so this doesn't block anything, but real-call PSTN/
provider behavior under load is still unobserved. No genuine multi-call concurrent load test (same honest
gap P7 already flagged, not closed here). Tool/RAG speculative-staleness guards were not built — traced in
full and found structurally not applicable to this codebase's current fully-synchronous call patterns; a
future phase adding speculative/background tool or RAG execution must add that guard itself. No dedicated
`STRICT_REALTIME_INVARIANTS` assertion-mode flag (violations are logged/counted, never raised, everywhere
— already satisfies the spec's own "don't crash production" default).

**Recommended next steps**: (1) place a real authorized call with `BARGE_IN_ENABLED=true` and confirm
`stale_audio_sent_total`/`replay_attempt_blocked_total` behave as expected against real PSTN timing and
provider behavior (automated tests cannot exercise real network jitter or provider-side reordering); (2) a
genuine concurrent-call load/chaos test, if a future phase has the infrastructure for it; (3) the
underlying voice pipeline (P2 through P9) is now structurally complete — per this phase's own instruction,
the next stage should be real-call quality optimization (Telugu naturalness, turn-endpoint timing, barge-in
threshold tuning against real false-interruption data, RAG/LLM/TTS latency, prosody, business relevance),
not new infrastructure, until real-call measurement proves another architectural gap.
