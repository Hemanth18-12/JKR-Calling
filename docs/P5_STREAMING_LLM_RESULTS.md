# P5 — Streaming LLM Response: Results & Verification Status

See `docs/P5_STREAMING_LLM_AUDIT.md` (what P5 replaces, and the P4 verification-gate bug fixed first,
per this phase's own opening instruction) and `docs/STREAMING_LLM_ARCHITECTURE.md` (what shipped and
why) for full context. This doc states what has and hasn't been verified, honestly — same practice
every phase this session has followed, most recently `docs/P4_TURN_DETECTION_RESULTS.md`.

## P4 verification gate — result

Docker was available this session. Ran the full DB-backed suite before writing any P5 code, per the
spec's own explicit instruction. Found and fixed one real, pre-existing bug (not previously visible):
`asyncio.wait_for(anext(async_generator), timeout=...)` permanently kills the generator if the timeout
fires while it's suspended mid-body. Full detail in the audit doc. **Verified baseline after the fix:
353 tests passing repo-wide**, zero failures — this is the number P5 is measured against.

## What shipped

- `packages/conversation/jkr_conversation/_shared_http.py` — shared `httpx.AsyncClient` singleton,
  extracted so `llm_client.py` and `streaming_llm.py` can both depend on it without an import cycle.
- `streaming_llm.py` — `StreamingLLMProvider` protocol, `LLMStreamEvent` union, and
  `stream_openai_chat_completion()` — hand-rolled SSE parsing matching OpenAI's contract, verified live
  against the real API (not guessed), never raises, classifies every failure mode.
- `speakable_chunker.py` — `SpeakableChunker`: content-driven (never timing-driven) chunk boundaries at
  real sentence/clause characters, language-agnostic (`.?!;।`), with a bounded-length forced-cut
  fallback for runaway sentences.
- `streaming_response.py` — `StreamingResponseAssembler`, `SpeakableChunk`, `CancellationToken`,
  `StreamingGenerationResult` — full timing (`ttft_ms`/`first_speakable_chunk_ms`/
  `full_generation_ms`)/usage/cancellation tracking, an `on_chunk` callback invoked in real time during
  generation (not just at the end), guaranteed `gen.aclose()` cleanup on every exit path.
- `formatter.py::strip_for_streaming_chunk()` — the per-fragment-safe subset of the full formatter.
- `llm_client.py::OpenAILLMClient.stream_text()` — the streaming counterpart to the existing
  `complete_text()`.
- `prompt_builder.py::generate()` — `response_mode`/`on_speakable_chunk`/`latency_sink`/
  `cancellation_token`, all additive and no-op unless `response_mode="streaming"`; return type stays
  `str`, zero breaking changes to any of the ~15 existing tests asserting that.
- `engine.py::process_turn()` — forwards the same four params, threading streaming latency into the
  existing `latency_ms` dict (same additive-keys pattern `rag_embedding`/`rag_vector_search` already
  use).
- `services/api/app/config.py::Settings.llm_response_mode` (`"complete"` default) — wired into both
  `live_call/service.py` `process_turn()` call sites and `transport/transitional_bridge.py`'s one.
  `services/voice-worker`'s Test Lab call site is untouched (same precedent P3.5's `engine_mode` set).
- A real prompt fix: `_build_prompt()`'s SPEECH STYLE instruction now explicitly forbids generic
  English fillers ("Sure", "Okay", "Absolutely", "I understand", "I'd be happy to help") before the
  actual answer — directly motivated by a real bug caught live during this phase's own benchmarking
  (see below), not a hypothetical.

## Verified — unit and DB-integration tests, all real, all passing

**184 tests in `packages/conversation`** (127 baseline + 57 new), **160 in `services/api`** (unchanged
count — no new API-level tests needed; the flag threading is exercised through the existing suite plus
the new engine-level tests below), **10 in `services/voice-worker`**, **32 in `packages/db`**, **13 in
`services/campaign-worker`**, **11 in `services/intelligence-worker`** — **410 tests passing
repo-wide, zero failures.**

The 57 new tests, by file:
- `test_speakable_chunker.py` (11) — no-emit-until-boundary, no-emit-on-pause (spec §16, proven by
  construction), multi-boundary-in-one-delta, below-`min_chunk_chars` accumulation,
  `flush()` returning a short leftover regardless of the threshold (spec §17), Devanagari danda,
  the exact Telugu-English worked example from spec §59, forced-cut-at-clause-boundary, forced-cut
  with no boundary at all (hard cut).
- `test_streaming_llm.py` (13) — happy-path event ordering, request-body shape
  (`stream: true`/`stream_options.include_usage`), all six HTTP-status → `LLMFailureClass` mappings,
  `httpx.TimeoutException`/`httpx.ConnectError`/generic-exception classification (never raises),
  malformed-JSON-line and non-`data:`-line tolerance.
- `test_streaming_response.py` (13) — happy-path assembly, chunk/response/generation id tagging,
  leftover-buffer flush marked final, failure before vs. after the first chunk (partial text
  preserved), `gen.aclose()` proven to actually run on early cancellation (not just that the loop
  stops), late-delta-after-cancellation discarded, `on_chunk` fired in real time for both async and
  plain sync callables (including the trailing flush chunk), TTFT measured strictly before
  first-speakable-chunk time, two independent runs never sharing ids.
- `test_formatter.py` (+4) — `strip_for_streaming_chunk()` markdown/URL stripping, whitespace
  collapsing, per-fragment safety, header/bullet stripping.
- `test_prompt_builder.py` (+10) — streaming success returns the assembled text, `latency_sink`
  populated, `on_speakable_chunk` invoked in order, stream failure falls back to canned text,
  pre-cancelled falls back, a client lacking `stream_text` degrades gracefully to `complete_text()`,
  and — the structural-safety proof — `SAFETY_STOP`/`COMPLETE_OBJECTIVE`/fast-path-eligible actions
  never call `stream_text` even when `response_mode="streaming"` is explicitly requested.
- `test_engine.py` (+6, real Postgres, no mocked DB) — `process_turn(response_mode="streaming")`
  produces a real reply and populates `llm_ttft`/`llm_first_speakable_chunk`/`llm_full_generation` in
  `latency_ms`; `on_speakable_chunk` fires through the real engine, not just the unit layer; **RAG
  genuinely completes before streaming starts** (spec §23-24) — proven by asserting the retrieved
  evidence's own figures appear in the system prompt actually handed to `stream_text()`, which could
  only happen if RAG had already run; canned do-not-call and objective-completion turns never touch
  `stream_text` even under `response_mode="streaming"`; **two-call isolation** (spec §105) — two
  independently seeded call sessions streamed through the same chunk collector produce disjoint
  `generation_id` sets.

## Real-provider benchmark — 10 streaming runs + 5 complete-mode runs, live OpenAI API

Ran through the actual production code (`OpenAILLMClient.stream_text()` →
`stream_openai_chat_completion()` → `StreamingResponseAssembler`, and `OpenAILLMClient.complete_text()`
for the comparison), `gpt-4o-mini`, `max_tokens=150`, across five realistic response-generation
categories — no-RAG field-ask (Telugu-English and Hindi-English), a RAG-grounded pricing answer
(English), an objection response (Telugu-English), and a multi-intent question answer (Hindi-English).
Two full passes over all five categories = 10 streaming samples, meeting the spec's own "10+ turns
before any P50/P95 claim" bar; one pass in complete mode (5 samples) for direct comparison.

| Metric | n | min | P50 | P95 | max | avg |
|---|---|---|---|---|---|---|
| Streaming TTFT | 10 | 651ms | 855ms | 1429ms | 1672ms | 936ms |
| Streaming first-speakable-chunk | 10 | 849ms | 1069ms | 1610ms | 1835ms | 1106ms |
| Streaming full generation | 10 | 850ms | 1091ms | 1650ms | 1853ms | 1164ms |
| Complete-mode full (comparison) | 5 | 843ms | — | — | 1333ms | 988ms |

(P50/P95 omitted for the 5-sample complete-mode row — not enough samples to make that claim honestly;
min/max/avg are reported instead.)

**Findings, stated plainly:**
- TTFT and first-speakable-chunk time track each other closely (median gap ~214ms) — for these
  categories, the *first* text delta usually already contains a sentence boundary, so there's rarely a
  long wait between "the model started responding" and "there's something speakable." This is a
  property of these particular prompts (short, direct instructions) more than a general guarantee — a
  response that opens with a long clause before its first period would show a bigger gap, which is
  exactly the max-length forced-cut path `SpeakableChunker` exists for.
- Streaming's full-generation time (avg 1164ms) and complete-mode's full time (avg 988ms) are in the
  same range — consistent with the audit doc's earlier 3-run finding: streaming isn't a slower way to
  get the same answer, it's the same generation with intermediate results exposed.
- **No generic-opener regressions observed in this run** — across all 10 streaming samples, first
  chunks started directly with the answer/action, none with a bare "Sure!"/"Okay" filler. This is
  evidence the prompt fix holds under broader sampling than the original 1-in-3 failure that motivated
  it (see the audit doc), not proof it's unbreakable — a prompt instruction is not a structural
  guarantee, and this should keep being watched on real calls.

**First-chunk examples, by category (real model output, not fabricated):**

| Category | First speakable chunk |
|---|---|
| Telugu-English, no-RAG field ask | *"Root canal treatment ki appointment kaani, eppudu vachhe date meeku suit avuthundi?"* |
| Hindi-English, no-RAG field ask | *"Aapko appointment ke liye kaunsa time theek rahega?"* |
| English, RAG-grounded pricing | *"Root canal treatment costs between 8000 and 12000 rupees, depending on the complexity."* |
| Telugu-English, objection response | *"We have a payment plan that lets you split the cost across 3 months with no extra charge."* |
| Hindi-English, multi-intent answer | *"Basement mein free parking available hai."* |

## NOT done — real-call verification

No real phone call has been placed with `LLM_RESPONSE_MODE=streaming`. `.env` has it unset (defaults to
`complete`) — not flipped live, same reasoning as every previous phase: this changes the actual
response-generation path on a live call and shouldn't be enabled without the user's own test call. The
benchmark above is a real-API, real-code-path measurement, but it drives `prompt_builder`-shaped
prompts directly, not a full real call through Twilio/Sarvam STT/`TurnManager`/`ConversationEngine`.

**Manual verification plan**, once the user is ready:
1. Set `LLM_RESPONSE_MODE=streaming` in `.env` (works under either `TWILIO_VOICE_TRANSPORT` setting —
   streaming response generation doesn't depend on streaming STT or Media Streams).
2. Place one authorized test call covering: a plain field-ask turn, a question the agent should answer
   from real knowledge (RAG), an objection, and a turn in each of Telugu-English/Hindi-English/English.
3. Pull `call_latency_metrics` for that call (`engine_llm_ttft`/`engine_llm_first_speakable_chunk`/
   `engine_llm_full_generation`, persisted automatically via the existing `for stage, duration_ms in
   result.latency_ms.items()` loop — no new persistence code needed for this) and compare against the
   same scripted turns with `LLM_RESPONSE_MODE=complete`.
4. Confirm no generic-opener regression and no formatting artifact (raw markdown, a URL) ever reaches
   what the customer actually hears — the batch TTS step still runs on the fully assembled, fully
   formatted text either way, so P5 alone should be inaudible to the customer today; this step is
   really about confirming the metrics are sane on real audio, not about a perceptible behavior change.

## What's still unfinished after P5 (restated, honestly)

- **Streaming TTS**: not yet — P6. `SpeakableChunk`s exist, are tested, and can be produced in real
  time via `on_speakable_chunk`, but nothing in the real-call path synthesizes speech from them today.
  The customer-facing audio path is unchanged by P5.
- **Full LLM→TTS pipeline concurrency**: not yet. No production call site passes an `on_speakable_chunk`
  callback yet — there's no live consumer to hand chunks to until P6 exists.
- **Automatic barge-in**: not yet — P8. `CancellationToken` is the primitive P8 will call; nothing
  calls `cancel()` in this phase.
- **Strict stale-audio rejection**: not yet — P9.
- **Speculative/preemptive generation before a turn is committed**: not started; P5's boundary is still
  `USER_TURN_COMMITTED`, same as every prior phase.
- **Generation-ownership lock across concurrent turns on one call** (spec §92): not implemented this
  pass — `process_turn()` is already only ever called sequentially per call (confirmed by the existing
  transport code's own turn-taking), so there's no live race today, but nothing yet actively rejects a
  second concurrent generation attempt if one were ever introduced.
- **Bounded response-chunk queue / backpressure**: not implemented; spec explicitly scoped this down to
  observational-only for P5, and even that wasn't added — there's no live queue to observe yet since
  nothing consumes chunks in real time in production.
- **Debug-trace / Test Lab exposure of streaming state**: not implemented. No `to_debug_dict()`-style
  method or HTTP endpoint surfaces `StreamingGenerationResult`/chunk timing to the frontend — same
  scope-down the spec explicitly permits (P4 set this same precedent for `TurnManager`), just not
  picked up this pass.

## Definition-of-done, honestly marked

Provider abstraction, stream lifecycle, first-token timing, `SpeakableChunker`, multilingual chunking,
cancellation primitive, generation ids, failure handling, usage accounting — **done, tested**.
Real-provider benchmark with 10+ streaming samples — **done**, see above. Engine-level integration
proving RAG-before-streaming ordering and two-call isolation — **done**, DB-backed, not simulated.
Debugging/Test Lab exposure — **not done**, explicitly scoped out per spec's own permission to do so.
Generation-ownership lock and bounded-queue backpressure — **not done**, real gaps, not silently
claimed. Lint/mypy — **clean** on every touched/new file. No automatic git commit — **honored**.
