# JKR AI Calling — Complete System Context

**A forensic, code-grounded onboarding document for a senior voice engineer joining today.**

Methodology: every claim below was derived by reading the actual code at `/Users/siva/jkrAICalling` (branch `main`, HEAD `8d65d26`, clean working tree, audited 2026-08-11), not from specs or prior planning docs. Where documentation disagrees with code, **code wins**, and the discrepancy is called out explicitly. Priority order used throughout: **CODE > TESTS > RUNTIME CONFIG (`.env`) > DOCS > old prompts/specs.**

Companion documents:
- [`JKR_RUNTIME_CONFIG_MATRIX.md`](./JKR_RUNTIME_CONFIG_MATRIX.md) — the full feature-flag table and current effective configuration
- [`JKR_REAL_CALL_SEQUENCE.md`](./JKR_REAL_CALL_SEQUENCE.md) — narrated call lifecycle + sequence diagrams
- [`JKR_VOICE_QUALITY_ROOT_CAUSE_AUDIT.md`](./JKR_VOICE_QUALITY_ROOT_CAUSE_AUDIT.md) — ranked quality issues and recommendations

---

## 1. Product purpose

JKR AI Calling is an India-first, multilingual (Telugu / Hindi / English, code-switched) multi-tenant AI calling platform. It makes and receives calls, qualifies leads, answers from business-approved knowledge, books appointments, hands off to humans, and reports business outcomes. Target businesses in the seed data: dental (Aaha Dental Care), education (Adarsh Educational Institutions), and creative services (JKR Creatives).

## 2. Repository map

```
apps/web/                    Next.js frontend — the only UI surface
services/api/                FastAPI — the only backend surface the browser talks to;
                              ALSO owns the entire real-call Twilio/Media-Streams pipeline
services/voice-worker/       FastAPI — a TEXT-TURN session API (not real audio), used by
                              campaign-worker and Test Lab; shares the jkr_conversation engine
services/campaign-worker/    Dramatiq worker — dials campaign contacts (currently mock-only,
                              see §4)
services/intelligence-worker/ Dramatiq worker — post-call pipeline (transcript validation,
                              outcome classification, summary, quality eval, follow-ups)
services/integration-worker/ Not yet built (no code)
packages/conversation/       jkr_conversation — the SHARED conversation-intelligence engine
                              used by both real Twilio calls and voice-worker's text sessions
packages/db/                 jkr_db — SQLAlchemy models, Alembic migrations, seed data,
                              embeddings, tools engine, webhook engine
packages/messaging/          Redis client + Dramatiq broker wrapper
infra/docker/                EMPTY — the app-service Dockerfiles referenced by docker-compose.yml
                              don't exist yet; only postgres/redis/minio/livekit run via Docker
docs/                        Per-phase architecture docs (P2–P10) — useful as documented
                              INTENT, not as proof of current runtime behavior (see §5)
```

## 3. Call entry points — all of them, verified

There are **four** distinct ways a "call" can start in this codebase, and they are not interchangeable:

| Entry point | Route | Backing service | Real Twilio audio? |
|---|---|---|---|
| **Live Test Call** | `POST /api/v1/live-call` | `services/api/app/modules/live_call/` (self-contained) | **Yes** — the only path that places a real PSTN call |
| **Test Lab** | `POST /api/v1/calls/test` | → HTTP → `services/voice-worker` `/sessions` | No — text-turn simulation only |
| **Campaign dialing** | `services/campaign-worker/app/dialer.py` | → HTTP → `services/voice-worker` `/sessions` | **No — see §4, this is a hard finding** |
| **Inbound (customer calls the business)** | — | — | **Does not exist.** No route, no webhook, nothing. `CallSession.direction` is hardcoded `"outbound"` everywhere it's constructed. |

## 4. The central architectural fact: two unrelated "calling" systems share one brain

`services/voice-worker` is **not** a real-time audio/Twilio service. It's a text-in/text-out session API: `POST /sessions`, `POST /sessions/{id}/user-turn` (takes a `text` field, not audio), `POST /sessions/{id}/end`. Its own `turn_manager.py` is explicitly commented: *"Real-time audio would drive this off VAD frames; the text-simulated transport... drives it off wall-clock time instead."* `services/voice-worker/app/providers/` contains only `base.py` (Protocol interfaces) and `mock.py` — **no real telephony/STT/TTS adapter file exists in that service at all.**

`services/campaign-worker/app/dialer.py`'s own module docstring states outright: *"this pass has no real telephony adapter wired into voice-worker at all... every dispatch this loop performs is a mock call."* Whether a contact "answers" is a SHA256 hash-based dice roll (`simulate_connect_outcome`, 80% answered / 10% no-answer / 6% busy / 4% provider-error), and the "customer" side of the conversation is a round-robin canned-reply generator playing both parts automatically.

**Conclusion, stated plainly: campaign-triggered calling never places a real phone call, structurally, today.** It is a fully simulated conversation between the real `jkr_conversation` engine and a scripted fake customer.

The **only** path that touches a real phone is `/api/v1/live-call` → `services/api/app/modules/live_call/`, which is entirely self-contained inside `services/api` (its own webhooks, its own Media Streams transport, its own duplicated invocation of the shared engine) and never calls out to `voice-worker` at all.

What **is** genuinely shared between the two systems: the core `jkr_conversation.engine.process_turn()` — extraction, RAG, planning, response generation. Everything about how a "turn" gets *into* that function (real audio + STT + turn detection vs. a typed string) is completely different and non-shared.

## 5. Current effective runtime architecture — verified, not assumed

See [`JKR_RUNTIME_CONFIG_MATRIX.md`](./JKR_RUNTIME_CONFIG_MATRIX.md) for the full table. The one-paragraph version:

`.env` sets `TWILIO_VOICE_TRANSPORT=media_stream` (a persistent WebSocket instead of Twilio's `<Record>` webhook loop) but leaves every other P3–P9 flag (`STT_MODE`, `TTS_MODE`, `TURN_DETECTION_MODE`, `CONVERSATION_ENGINE_MODE`, `LLM_RESPONSE_MODE`, `BARGE_IN_ENABLED`) unset, so each falls back to its conservative code default (`batch`, `batch`, `provider`, `legacy`, `complete`, `False` respectively). Because `config.py`'s `effective_*` properties cascade-gate the advanced code paths behind *both* the flag *and* the transport, the net effect is: the WebSocket carries batch-STT, batch-TTS, no-turn-manager, no-coordinator, no-barge-in traffic. The code that actually executes on a real call today is `services/api/app/modules/live_call/transport/transitional_bridge.py` — explicitly documented in its own module docstring as the intended **permanent** implementation for `STT_MODE=batch`, not a stepping-stone.

## 6. Outbound call setup (Live Test Call — the only real path)

Full trace, `services/api/app/modules/live_call/service.py::start_live_test_call`:

1. `enable_live_calls` check (403 if off) — `service.py:209-210`
2. Phone normalization to E.164 — `service.py:212-215`
3. `authorized_test_numbers_list` check (403 if not authorized) — `service.py:217-221`
4. Agent + published `AgentVersion` lookup — `service.py:223-233`
5. `ConversationPolicy` + `VoicePersona` load, TTS speaker/pace resolution — `service.py:235-259`
6. `TwilioClient` construction (503 if creds blank) — `service.py:261-266`
7. `CallSession(direction="outbound", status="queued", is_mock=False, ...)` + `CallParticipant` rows + `call_started` `CallEvent` — `service.py:286-315`
8. Greeting text assembly (canned, see §22) — `service.py:317-322`
9. Webhook URL construction: `{PUBLIC_WEBHOOK_BASE_URL or API_BASE_URL}/api/v1/live-call/webhooks/twilio/{voice|status|recording|closing-grace}/{token}` — `service.py:324-325`
10. **Concurrent** greeting-TTS synthesis + `telephony.create_call()` (real Twilio API POST) via `asyncio.gather` — `service.py:334-346`
11. Redis session-state cache under `jkr:live_call:{token}`, TTL 1800s — `service.py:348-368`
12. Final DB update: `status="dialing"` — `service.py:370-377`

**[Stage 2 update]** `CallSession.contact_id` is now set in this flow — `_get_or_create_contact()` resolves/creates a `Contact` for the dialed number before `CallSession` is created. See `docs/STAGE2_REAL_CALL_FIXES.md` Fix 1. (Original note, now superseded: "`CallSession.contact_id` is never set" — this had a direct, severe consequence for tool execution, §15.)

## 7. Twilio Media Streams — TwiML and transport

Branch point: `service.py::handle_voice_webhook`, `if settings.twilio_voice_transport == "media_stream"`.

- **`record`** (code default, not active today): returns `<Response><Play>{greeting_audio}</Play><Record action="{recording_url}" maxLength="20" timeout="4" trim="trim-silence"/><Say>...no response...</Say><Hangup/></Response>`. Every turn is a fresh, stateless webhook POST — no barge-in, no duplex audio, by design (module docstring says so explicitly).
- **`media_stream`** (`.env` value, active today): returns `<Response><Connect><Stream url="wss://.../api/v1/live-call/ws/twilio/media/{token}"/></Connect></Response>`. Everything after that happens over the persistent WebSocket.

**If you start the app right now without changing `.env`: `media_stream` runs** (explicit `.env:92` override of the `record` code default).

## 8. Audio flow — the active path

Twilio's wire format is fixed: mu-law, 8000Hz, mono. Inbound: `decode_twilio_media_payload()` → PCM16. Outbound: `encode_twilio_media_payload()` → resample via `audioop.ratecv()` if source isn't already 8kHz → `audioop.lin2ulaw()` → base64. `RealtimeMediaSession` (`transport/session.py`) holds two `asyncio.Queue(maxsize=250)` queues (~5s of audio): **inbound** uses non-blocking `put_nowait` and drops-and-counts on overflow (never stalls the Twilio receive loop); **outbound** uses blocking `put` (deliberate backpressure). Watchdogs: 30s media-idle timeout, 15s initial-connect timeout.

**Does the receive loop ever wait on STT/LLM/TTS/DB?** Yes, structurally, under the active batch path: `_run_batch_turn_loop` (`transport/twilio_media_stream.py:319-405`) awaits the *entire* turn pipeline (STT REST call → `process_turn()` → tool execution → TTS synthesis) **inline**, synchronously, before reading more audio into a new turn. There is exactly one `_processing_loop` task per call; no background task, no concurrency. This is a genuine realtime risk under the current architecture — flagged in the quality audit.

## 9. STT

**Active**: `services/api/app/live_providers/sarvam_stt.py` — one batch REST POST per turn to `https://api.sarvam.ai/speech-to-text`, `model="saaras:v4"`, `mode="codemix"`. No session lifecycle, no partial transcripts, no confidence score (Sarvam never returns one), no reconnect logic (irrelevant — it's not a persistent connection).

**Language code resolution** (`live_call/service.py:100-110`, `_sarvam_language_code()`): collapses `primary_language` to exactly one of `te-IN`/`hi-IN`/`en-IN` — **the compound tags `te-en-IN`/`hi-en-IN` are never sent to Sarvam.** Code-switching is expressed only via the separate `mode="codemix"` parameter layered on top of the collapsed base language. Same collapsed code is reused for both STT and TTS.

**Dormant**: `sarvam_streaming_stt.py` — persistent WS to `wss://api.sarvam.ai/speech-to-text-realtime/ws`, `model="saaras:v3-realtime"`, `endpointing="vad"`, `threshold=0.3`, `prefix_padding_ms=300`, `silence_duration_ms=500`, `min_speech_duration_ms=250`. Full `SpeechStarted`/`PartialTranscript`/`FinalTranscript`/`SpeechEnded` event stream, bounded reconnect (3 attempts, 0.5/1.5/3.0s backoff). Only runs under `STT_MODE=streaming`.

## 10. TurnManager / turn detection

**Active today: not `TurnManager` at all.** The real turn-boundary logic is `transitional_bridge.TurnBuffer` — a flat trailing-silence energy buffer, unrelated to the `turns/` package: `SILENCE_RMS_THRESHOLD=300` (`audioop.rms()`, explicitly flagged in its own docstring as "not tuned against real phone-line audio"), `TRAILING_SILENCE_SECONDS=4.0`, `MIN_SPEECH_MS_TO_COUNT=300`, `MAX_TURN_SECONDS=20.0`. Turn commits when `speech_ms >= 300` AND `trailing_silence_ms >= 4000` — a flat **4.0-second** wait, semantics-blind, no thinking-pause awareness.

**Dormant**: the entire `turns/` package (`TurnManager`, `EnergyVAD`, `turns/semantic.py`, `turns/backchannel.py`, `turns/interruption_policy.py`, `turns/policies.py`) is wired exclusively into `streaming_bridge.py`, which never executes under `effective_stt_mode="batch"`. `TurnManager(` has exactly one non-test construction site (`streaming_bridge.py:970`). Presets: FAST (150/1200/500/900ms), BALANCED (300/2000/900/1500ms), PATIENT (500/3000/1400/2200ms) — all faster than the active 4.0s buffer.

## 11. ConversationEngine

`packages/conversation/jkr_conversation/engine.py::process_turn()` — shared by both real calls and text-simulated sessions. Call graph (legacy mode, the active default):

```
process_turn()
├─ fast_router.route()          SKIPPED under conversation_engine_mode="legacy"
├─ domain_vocabulary.load_domain_terms()   DB read, EVERY turn, no caching
├─ extractor.extract()          LLM call — gpt-4o-mini, JSON mode, temp 0.2, max_tokens=400
├─ policy.apply_backstop()      pure Python
├─ fold extraction → state      pure Python
├─ planner.decide()             pure Python, zero I/O, zero LLM
├─ rag.search_knowledge_with_timing()   ONLY if a question was detected — embedding API + pgvector
├─ prompt_builder.generate()    LLM call — gpt-4o-mini, max_tokens=150 (unless action is
│                                canned/fast-eligible — see §16)
├─ formatter.SpokenResponseFormatter.format()   pure Python, truncates to max_sentences=3
└─ returns ConversationTurnResult
```

## 12. State

`state.py::new_conversation_state()`: `objective`, `language`, `intent`, `sentiment`, `known_fields` (dict), `missing_fields`, `uncertain_fields`, `risk_flags`, `customer_requested_human`, `do_not_call`, `wrong_number`, `next_best_action`, `objective_status`, `asked_count`, `awaiting_field`, `field_confidence`, `field_ask_counts`, `tool_results`, `turn_count`, `pending_confirmation` (at most one at a time). **No customer-question queue exists** — a detected question lives only for the single turn it's generated on.

## 13. Planner

`planner.py::decide()` — pure Python, zero LLM, zero I/O. Priority ladder: `SAFETY_STOP` (DNC/wrong-number) → `COMPLETE_OBJECTIVE` safety-net ceilings (max turns/duration) → `HUMAN_HANDOFF` → `CLARIFY` (low-confidence field) → `CONFIRM_FIELD` (pending, capped at `MAX_ASKS_PER_FIELD=2`) → `ASK_FIELD` (required, then optional) → `COMPLETE_OBJECTIVE`. "Answer the customer's question" is **not** an exclusive priority rung — it's a non-exclusive annotation (`answer_question_first`) layered onto whichever action wins above.

**Known gap**: `detected_question=True` and `rewritten_query=None` are not schema-coupled — if the model sets one without the other, the question is silently dropped with no RAG search and no answer surfaced at all (`planner.py:68`, `engine.py:294`).

## 14. RAG

Full pipeline: ingest (`knowledge/service.py`) → chunk (`chunk_text`, max 800 chars, 100 overlap) → embed (`embed_text`, `text-embedding-3-small` if `OPENAI_API_KEY` reachable, else deterministic hash-based mock) → approve (workflow flips `KnowledgeDocument` + all child chunks together) → store (pgvector `Vector(1536)` column) → retrieve (`rag.py::search_knowledge_with_timing`: embed query → `cosine_distance` `ORDER BY ... LIMIT top_k`, threshold `0.4`, log a `RetrievalEvent` every time, hit or miss).

**Scope: workspace-wide, not agent-specific.** `KnowledgeChunk`/`KnowledgeDocument` extend only `TenantMixin` (`workspace_id`) — no `agent_id` column exists anywhere in the knowledge schema.

**No vector index** (`ivfflat`/`hnsw`) exists in any migration — every RAG query is a full sequential scan + sort. Fine at demo scale, a real landmine as knowledge bases grow.

**Failure/hallucination**: on a miss, the planner force-overrides to `DEFER_QUESTION`, and the prompt inserts a fixed "not fully sure, team will confirm" fallback ahead of the LLM's own text. But this is prompt-level discouragement, not a post-hoc fact-check — a real LLM call with retrieved-but-imperfect context has no mechanical guardrail against paraphrasing beyond what it was given.

## 15. Tools

10-tool catalog (`tools_engine.py`). Genuinely wired to fire mid-call: `book_appointment` (on `COMPLETE_OBJECTIVE` for the `book_appointment` objective) and `create_human_callback` (on `HUMAN_HANDOFF`). **[Stage 2 update, see `docs/STAGE2_REAL_CALL_FIXES.md` Fix 1]** `book_appointment` now receives a real `contact_id` (resolved at call creation), and the spoken reply is now conditioned on actual tool outcome — a truthful fallback is spoken instead of the canned success line if the tool fails. (Original finding, now fixed: "`book_appointment` requires `contact_id`, which `live_call` never sets or passes... the customer still hears the canned 'I've noted your appointment' closing text... because the spoken reply is generated before the tool actually executes and is never conditioned on its outcome.")

`send_whatsapp`/`send_sms` write a DB row only — **no real WhatsApp/SMS provider adapter exists anywhere in the repo** (`WHATSAPP_PROVIDER=mock`, no real alternative). `check_calendar_slots`/`create_crm_lead`/`update_crm_stage`/`send_email` are explicitly mock-only. DNC is not a tool — it's a state flag; the actual `SuppressionEntry` write only happens **after** the call ends, in the async post-call pipeline, so nothing prevents the same number being redialed mid-window.

## 16. Streaming LLM

`llm_response_mode="complete"` (active default) → `prompt_builder.py` calls `llm_client.complete_text()` and blocks for the entire response. Dormant `streaming` path: `StreamingResponseAssembler` consumes OpenAI SSE deltas, feeds `SpeakableChunker`, fires `on_chunk` mid-stream — first chunk available at first sentence boundary, not full completion.

**Structural finding**: under `conversation_engine_mode="fast"`, the response-generation LLM call is *unreachable* — `PlannerDecision.action`'s 7 possible values split exactly into 3 always-canned actions and 4 that exactly match `_FAST_RESPONSE_ELIGIBLE_ACTIONS`. There is no action value that reaches `complete_text`/`stream_text` in fast mode.

## 17. SpeakableChunker

Sentence boundaries `.?!;।`, clause fallback `,`/`:`, `MIN_CHUNK_CHARS=4`, `MAX_CHUNK_CHARS=220` (force-cut backward to nearest boundary). Punctuation-driven, script-agnostic — chunks a code-switched sentence identically to a monolingual one as long as terminal punctuation is present. **Not invoked at all today** since neither streaming LLM nor streaming TTS is active.

## 18. Streaming TTS

**Active**: `sarvam_tts.py` — one batch REST POST per turn to `https://api.sarvam.ai/text-to-speech`, payload `{text, language_code, speaker, model="bulbul:v3", pace}`. **[Stage 2 update, see `docs/STAGE2_REAL_CALL_FIXES.md` Fix 3]** `pace` was added to this payload and is now forwarded from `_resolve_tts_pace()` at all 7 `_speak()` call sites — previously computed and cached in Redis state but never actually sent. (Original finding, now fixed: "No pace/speed field exists in this payload's schema at all.")

**Voice actually used, resolved definitively**: the seeded `VoicePersona.provider` defaults to `MOCK` (both the DB model default and current `seed.py`, unfixed since the P10 doc flagged it — **still true**, this half of the finding was not addressed in Stage 2, which touched no seed data). `_resolve_tts_speaker()` correctly refuses to pass the bogus `voice_id` to Sarvam, returning `None` — which means `SarvamTTS`'s own hardcoded default (`speaker="priya"`) silently takes over. **The customer hears a real Sarvam voice — not mock/fake audio — but it's Sarvam's generic default, not anything actually configured for the tenant, and there is no log signal distinguishing "intended" from "fell back."** `_resolve_tts_pace()`'s result now reaches Sarvam on the active batch path too, not just the dormant streaming path — **speaking speed is configurable wherever a real `VoicePersona.provider=sarvam_tts` is actually configured** (still moot for today's mock-default seed data, per the paragraph above).

Dormant: `sarvam_streaming_tts.py` — persistent WS, requests `output_audio_codec="mulaw"`/`speech_sample_rate="8000"` (bypasses PCM resampling entirely), honors `VoicePersona.speaking_speed` via `pace`.

## 19. Pipeline Coordinator

`RealtimePipelineCoordinator` (`transport/coordinator.py`) — **never constructed on a real call today** (`session.pipeline_coordinator` stays `None` all call, since it's only built inside the dormant `_connect_streaming_tts`). When it exists: mints a `ResponseIdentity` per response attempt (`call_id, turn_id, response_id, generation_id, sequence_id, epoch`), drives a validated state machine (`GENERATING_TEXT → ... → PLAYBACK_COMPLETE`, with `CANCEL_PENDING/SUPERSEDED/INTERRUPTED` off-ramps), and tracks `PlaybackUnit`s (`CREATED → SENT → ACKNOWLEDGED | CLEARED`) per audio chunk actually sent to Twilio.

## 20. Barge-in

**Confirmed off, by four independent gates, not just its own flag.** `effective_barge_in_enabled` requires `barge_in_enabled=True` AND streaming STT AND streaming TTS AND vad/hybrid turn detection — all four currently false. More fundamentally, the code path that would even *evaluate* an interruption (`streaming_bridge.py`) is unreachable under batch STT. **On a real call today, a customer interruption does nothing — the agent talks over them until its batch TTS reply finishes.**

If active: `InterruptionPolicy.decide()` (pure, deterministic) — critical cues (DNC/wrong-number/human-handoff phrases) bypass everything at confidence 0.95; high-priority cues ("stop", "wait", "actually", "no ") bypass the qualification window at 0.85; backchannels ("hmm", "okay", ≤3 words, exact match) are ignored unless a confirmation is pending; everything else needs ≥2 words or the 250ms qualification window to elapse. **Known gaps**: bare "human" (without "agent"/"person") never hits the critical-cue list; bare unpunctuated "no" (no trailing space/comma) misses the high-priority list and depends on confirmation context.

## 21. Replay protection

`ResponseIdentity` + `can_send_media()` (the `CustomerFacingOutputGate`) — 5-layer defense: atomic local invalidation → proactive queue purge → dequeue-time re-check → provider-event re-check → final gate immediately before the WebSocket send, checking `call_id`/`response_id`/`generation_id`/`sequence_id`/`epoch`/`clear_epoch` all match live state. Fully built and tested. **Effectively inert today** in the sense that there's only ever one response in flight (no coordinator, no barge-in) — nothing to replay-protect against yet, but the mechanism is real and ready for when streaming/barge-in activate.

## 22. Greeting

Canned, never LLM-generated: `AgentVersion.greeting_text` (plain DB string column), string-concatenated with `ai_disclosure_text` (deduped if already the leading sentence). Seeded Aaha Dental Care text: *"నమస్కారం {name} గారు, నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని. మీ అపాయింట్‌మెంట్ గురించి ఒక నిమిషం మాట్లాడొచ్చా?"* — 3 short sentences, self-identifies as AI upfront, ends in a yes/no question. Synthesized concurrently with the Twilio dial itself. Not interruptible even under `media_stream` transport (explicit code comment; moot anyway since barge-in is off).

## 23. Closing

Fully deterministic — `SAFETY_STOP`/`HUMAN_HANDOFF`/`COMPLETE_OBJECTIVE` all return canned text before any free-generation branch. Grace period: **4.0 seconds** (both transports), clock starts only after Twilio confirms the closing audio actually finished playing (`mark` ack), not when it was enqueued. Reopen: verified correct — real speech during grace flips `objective_status` back to `in_progress` and resumes the turn loop, with a correctly-guarded exception (DNC/wrong-number closes never reopen). Duplicate-goodbye protection exists for the `COMPLETE_OBJECTIVE→reopen→re-complete` case (shortened "noted, thank you" reaffirm) but **not** for a `SAFETY_STOP`/`HUMAN_HANDOFF` determination reached during grace — that plays a full second finality phrase.

## 24. Post-call

Enqueued from `_finalize_call()` → Dramatiq `intelligence` queue → `services/intelligence-worker/app/pipeline.py::run_post_call_pipeline`, all rule-based (no LLM): extraction validation, outcome (re-)classification, structured (not LLM-prose) summary, quality evaluation, follow-up dispatch (WhatsApp/callback/suppression tools — `reminder`/`close` channels are no-ops, no scheduler exists), generic outbound webhook delivery (HMAC-signed, best-effort, no retry queue).

**Not implemented**: recording storage to S3/MinIO. `CallRecording` model exists but is never instantiated anywhere in the codebase — Twilio recordings are fetched transiently to feed STT and then discarded.

## 25. Database interactions during a live call

Per-turn: `CallSession` state load (always) → **domain vocabulary reload, unconditionally, every single turn, with no caching** (`domain_vocabulary.load_domain_terms`, 2 SELECTs) → pgvector RAG search (conditional) → tool-execution selects (conditional, on completion/handoff) → `CallTurn`/`CallEvent`/`CallLatencyMetric` inserts (always). `recent_turns` for prompt context correctly comes from Redis, not a DB reload — no "reload full transcript every turn" antipattern. The two structurally suspicious items are the uncached domain-vocabulary reload and the missing pgvector index (§14).

## 26. Redis

Minimal, well-scoped: session-state cache (`jkr:live_call:{token}`, TTL 1800s) and a short-lived audio-blob cache for the greeting's `<Play>` fetch (TTL 300s). No pub/sub, no distributed locks, no rate limiting inside the live-call path itself (those exist separately in campaign-worker's dispatch logic).

## 27. External providers, latency waterfall

| Provider | Purpose | When | Blocking? |
|---|---|---|---|
| Twilio | Call placement, media transport | Call start, every audio frame | Yes — the whole call rides on it |
| Sarvam STT (batch) | Transcription | Every turn | Yes — inline await |
| Sarvam TTS (batch) | Speech synthesis | Every turn | Yes — inline await |
| OpenAI (`gpt-4o-mini`) | Extraction + response generation | Every non-canned turn | Yes — up to 2 sequential LLM calls per turn |
| OpenAI embeddings | RAG query embedding | Only when a question is detected | Yes, historically shown to dominate measured RAG latency (old data, see §14) |

No current-environment real-call latency measurements exist — `docs/P10_REAL_CALL_RESULTS.md` is explicitly marked NOT YET RUN. Any specific millisecond figures found in older docs (e.g. `CONVERSATION_ENGINE_LATENCY_AUDIT.md`) are historical/indicative from a single P3 diagnostic call, not current fact.

## 28–30. Quality risks, dead/unwired code, recommended next steps

See [`JKR_VOICE_QUALITY_ROOT_CAUSE_AUDIT.md`](./JKR_VOICE_QUALITY_ROOT_CAUSE_AUDIT.md) for the full ranked treatment of these three sections — they're substantial enough to warrant their own document rather than a summary here.
