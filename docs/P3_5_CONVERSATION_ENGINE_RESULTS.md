# P3.5 — ConversationEngine Latency Optimization: Results

See `docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md` for the full pre-work audit (real call graph, why
several of this phase's assumed inefficiencies turned out not to exist, and the scope decisions this
made). This doc is the after-the-fact results: what shipped, what it measured at against the real,
configured OpenAI API (never mocked — see §92's own requirement), what didn't ship, and why.

## BEFORE (P3 diagnostic call, `0066d4d3-...`, real phone call)

| Stage | Avg | Max |
|---|---|---|
| `engine_extraction` | 1993ms | 2701ms |
| `engine_rag` | 1679ms | 2233ms (only 2/6 turns — already conditional pre-P3.5) |
| `engine_generation` | 726ms | 1295ms |
| `engine_domain_vocabulary` | 9ms | 20ms |
| `engine_planning` | 0ms | 0ms |

## AFTER — real provider measurements, four scenarios, `engine_mode="legacy"` vs `"fast"`

Run against the actual configured OpenAI API from this machine (`OPENAI_API_KEY` set, real
`gpt-4o-mini` calls, real `text-embedding-3-small` calls, real Postgres/pgvector) — not a unit test,
not a mocked client, matching §92's explicit requirement that latency claims come only from real
provider measurements.

| Scenario | Legacy total | Fast total | What changed |
|---|---|---|---|
| "please do not call again" | 5395ms | **0ms** | FastTurnRouter — zero LLM calls |
| "hmm" (acknowledgement) | 2461ms | **0ms** | FastTurnRouter — zero LLM calls |
| topic field answer (triggers RAG) | 5433ms | 2334ms | generation call skipped (~1090ms); RAG portion varies, see below |
| multi-field, no fast_router match | 3819ms | 2980ms | generation call skipped (~949ms); RAG portion varies |

**What's a real, reliable, attributable-to-P3.5 saving**:
- **FastTurnRouter-eligible turns (do-not-call, wrong-number, human-handoff, pending-confirmation
  yes/no, acknowledgement-only): 100% of extraction + generation latency eliminated.** These are not
  edge cases — do-not-call, "hmm"/"okay" acknowledgements, and "yes"/"no" confirmation replies are
  common in real calls (the P2/P3 diagnostic call itself had at least one acknowledgement-shaped turn:
  "Hello చెప్పు చెప్పు").
- **Every ASK_FIELD/CLARIFY/CONFIRM_FIELD/DEFER_QUESTION turn saves the entire response-generation
  call** — consistently 700-1100ms across all three measured cases where it applied, using the
  already-tested canned templates directly instead of a second LLM round-trip.

**What is real but NOT attributable to P3.5 — stated plainly, not folded into the headline number**:
the RAG portion (`rag_embedding` specifically) varied 453ms-2374ms across these runs, in both legacy
and fast mode equally — P3.5 did not change how RAG works (same `embed_text()`/pgvector call either
way), so this variance is the embedding endpoint's own tail latency (consistent with
`docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md` §3's own probe showing the same spread). Where the two
scenario totals above show more than the generation-call saving would explain on its own, that gap is
this variance, not a P3.5 optimization — reported honestly rather than claimed as a win.

## Engineering goals from the original spec — measured against real data

> Turns requiring NO RAG: P50 < 700-900ms, P95 < 1,500ms. Turns requiring RAG: P50 < 1,200-1,500ms,
> P95 < 2,000ms.

**Not claimed as met.** Four data points is not a P50/P95 — this doc reports what was actually
measured (above), not a statistical claim it can't back up (§91: "do not claim them unless
measured"). What the four points show directionally: FastTurnRouter-eligible turns are now
effectively free (0ms engine-side, well under any target). ASK_FIELD-shaped no-RAG turns landed at
~2000-3000ms in these runs — **above** the original 700-900ms P50 target, because the single
remaining extraction call itself costs ~1.9-2.1s on this network path regardless of any change made
this phase (see the audit's §3 connection-reuse experiment — that's provider/network latency, not
something P3.5's scope changed). Meeting the original target for these turns would require either a
faster model for the extraction call specifically (now configurable via `TURN_UNDERSTANDING_MODEL`,
not changed by default this pass) or eliminating the extraction call itself for more turn shapes than
FastTurnRouter currently covers (see "not built" below) — both explicitly out of this pass's
delivered scope, not silently claimed as done.

## What shipped

- **`docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md`** — real call graph traced from the actual code,
  correcting several assumptions the original request made (no separate planner/query-rewrite/
  reranking LLM calls exist; RAG was already conditional).
- **Fine-grained RAG instrumentation** (`jkr_conversation/rag.py::search_knowledge_with_timing`) —
  `rag_embedding_ms`/`rag_vector_search_ms` as separate `CallLatencyMetric` rows, not one opaque `rag`
  number. Backward-compatible `search_knowledge()` kept for the one other caller (services/api's
  manual knowledge-search endpoint).
- **Connection reuse fixed** (`jkr_conversation/llm_client.py`, `jkr_db/embeddings.py`,
  `services/api/app/live_providers/{sarvam_stt,sarvam_tts}.py` via a new shared
  `_shared_http.py` helper) — one process-lifetime `httpx.AsyncClient` instead of one per call. Real,
  free correctness fix; measured as a modest, not dominant, effect (audit §3).
- **`FastTurnRouter`** (`jkr_conversation/fast_router.py`) — deterministic, zero-LLM, zero-I/O
  classification for do-not-call, wrong-number, human-handoff, pending-confirmation yes/no, and
  acknowledgement-only turns, reusing `policy.py`'s existing keyword detectors (the same ones already
  trusted as a post-hoc safety backstop) run *before* the LLM call instead of only after paying for it.
- **Fast canned-response path** (`jkr_conversation/prompt_builder.py`) — ASK_FIELD/CLARIFY/
  CONFIRM_FIELD/DEFER_QUESTION reuse the already-tested `_fallback_text()` templates directly under
  `engine_mode="fast"`, skipping the second LLM call. Deliberately not the spec's literal suggestion
  of an LLM-co-produced draft in the same call as extraction — see the audit doc §4 for why a
  templates-first design was chosen instead (the deterministic planner's decision isn't known until
  after extraction runs, so an extraction-time draft can't reliably target it).
- **`CONVERSATION_ENGINE_MODE=legacy|fast`** (`services/api/app/config.py`, threaded through all
  three real `process_turn()` call sites: `service.py` ×2 for `<Record>` mode,
  `transitional_bridge.py`/`streaming_bridge.py` for Media Streams) — default `legacy`, per this
  phase's own recommendation, confirmed byte-identical to pre-P3.5 behavior (existing 106
  `packages/conversation` tests passed unmodified before any new test was added).
- **Configurable model names** (`TURN_UNDERSTANDING_MODEL`, `CONVERSATION_RESPONSE_MODEL` env vars) —
  both default to the existing `gpt-4o-mini`, nothing changes silently.
- **`turn_path` observability** (`ExtractionResult.turn_path`: `"llm"`/`"mock"`/`"fast_path"`,
  surfaced in `state["last_turn_debug"]` alongside a new `rag_ran` flag) — answers "what actually
  drove cost on this turn" per-call without a new dashboard.

## What did NOT ship, and why (restated from the audit doc, for the final-report requirement)

- **A separate consolidated "TurnUnderstanding" model call replacing extraction** — extraction
  already consolidates field extraction + intent + question detection + objection + safety flags +
  confirmation classification into one call; the planner is already free. Building a parallel
  structured-output pipeline to replace something already ~80% consolidated would add real weight
  (new prompt, new schema, new fallback path, new parity surface) for a smaller marginal win than
  assumed going in.
- **Deterministic parsers for typed field values** (date/time/phone/rank/amount, spec §20) — real
  misparse risk across 5 languages and code-mixed speech; the spec's own §21 explicitly warns against
  building this casually. Every such turn still goes through real extraction.
- **L1 FAQ/lexical cache with knowledge-version invalidation** — a genuinely separate, substantial
  feature (new cache storage, invalidation logic, structured FAQ index) on the scale of the earlier
  domain-vocabulary work. Well-specified as a follow-up, not attempted given everything else in this
  pass.
- **Live shadow-mode dual-execution on real calls** — deferred in favor of the deterministic,
  reproducible scenario tests below, which achieve the same "don't ship a silent correctness
  regression" goal without new dual-execution infrastructure.
- **Per-call domain-vocabulary caching** — investigated (spec §35/36); found to be a deliberate
  existing decision (a code comment in `domain_vocabulary.py` already explains why: an agent's
  vocabulary assignment can change between calls, so cross-call caching risks staleness), and its
  actual cost is 9ms/turn — negligible next to the 700-2000ms LLM/embedding calls. Not implemented;
  the added JSON-serialization complexity (UUID fields in `DomainTermSnapshot`) wasn't justified by
  the size of the win.
- **Reranking removal/measurement** — moot; no reranker exists in this codebase.
- **Partial-STT speculative RAG prefetch** — explicitly optional per the original spec; not built.
- **`spoken_response_draft` validation pipeline** (spec §44) — not needed under the templates-first
  design actually shipped: the canned templates are safe by construction (same ones mock mode has
  used unconditionally all along), so there's no freshly-generated text requiring runtime validation.

## Tests

21 new tests, all using real infrastructure (Postgres, or the same `_FakeLLMClient`/
`_CountingLLMClient` pattern already established in this test suite — mocked only at the LLM network
boundary, never at the engine/DB level):

- `test_fast_router.py` (10) — every FastTurnRouter category, plus the negative cases (ambiguous
  confirmation replies and ordinary substantive utterances correctly fall through to real
  understanding, never guessed at).
- `test_prompt_builder.py` (+5) — fast mode skips the LLM for all four eligible actions; legacy mode
  still calls it for the identical decision (proves the flag actually gates behavior); SAFETY_STOP/
  HUMAN_HANDOFF/COMPLETE_OBJECTIVE remain canned-only in both modes (pre-existing property, confirmed
  not regressed).
- `test_engine.py` (+6), against a real Postgres database: a do-not-call turn touches the LLM client
  **zero** times under fast mode (proven via a call-counting fake, not inferred from timing); RAG
  stays conditional under fast mode (a no-question turn never calls it); a real question still
  triggers real RAG and gets answered from real approved knowledge under fast mode; an ASK_FIELD turn
  still makes exactly one LLM call (extraction) instead of two under fast mode; the real-call domain-
  mistranscription fix ("fruit canals" → flagged for confirmation, not silently trusted) survives fast
  mode unchanged; legacy mode (the default) is unaffected by FastTurnRouter's mere existence.

Full suite: **127 passing in `packages/conversation`** (106 pre-P3.5 + 21 new, zero regressions),
**118 passing in `services/api`** (unchanged count from P3 — P3.5 touched connection reuse and config
wiring there, not new test-covered features), **32 in `packages/db`**, zero regressions anywhere.

## Real-call verification — not done

No real phone call has been placed with `CONVERSATION_ENGINE_MODE=fast` set. The measurements above
are real (real API, real DB) but from a script, not a live Twilio call. `.env` still has
`CONVERSATION_ENGINE_MODE` unset (defaults to `legacy`) — this was a deliberate choice given the
scope of what changed in the actual decision-making path (skipping LLM calls entirely for some
turns), matching this session's established pattern of not silently flipping a real-call-affecting
flag without the user's own test.
