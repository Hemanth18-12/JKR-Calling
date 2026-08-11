# ConversationEngine Latency Audit (P3.5)

Written before any optimization code was changed, per this phase's own "measure before changing"
requirement. Two kinds of measurement are used and kept explicitly separate, per this phase's own
§92 warning: (1) real `call_latency_metrics` rows from an actual phone call (P3's diagnostic call,
also cited in `docs/REALTIME_VOICE_MIGRATION_AUDIT.md` §12.2), and (2) direct probes against the
real, configured OpenAI endpoints run from this machine during this audit (not a mocked client, not
a unit test — see §3). Only these two sources back any latency claim below.

## 1. The real call graph, traced from `packages/conversation/jkr_conversation/engine.py::process_turn()`

```
process_turn()
  ├─ domain_vocabulary.load_domain_terms(db)         [DB query]           ~9ms  (real data)
  ├─ extractor.extract()                             [1 LLM call, JSON]   ~2000ms (real data)
  │    └─ policy.apply_backstop()                     pure Python, 0 I/O
  │    └─ _annotate_domain_candidates()                pure Python (difflib), 0 I/O
  ├─ fold extraction into state                        pure Python, 0 I/O
  ├─ planner.decide()                                 [0 LLM calls]        0ms   (real data — confirmed pure Python)
  ├─ rag.search_knowledge()  — ONLY IF decision.rag_query is set
  │    ├─ embed_text()                               [1 embedding call]   dominant cost, see §3
  │    └─ pgvector similarity search                 [1 DB query]         fast, see §3
  ├─ prompt_builder.generate()                        [0 or 1 LLM call]   ~700ms (real data) — 0 for
  │                                                                        SAFETY_STOP/HUMAN_HANDOFF/
  │                                                                        COMPLETE_OBJECTIVE (already
  │                                                                        canned, pre-existing)
  └─ formatter.format()                                pure Python, 0 I/O
```

**This is a materially simpler graph than this phase's own spec assumed**, and that matters for
scoping what's actually worth building:

- There is **no separate dialogue-act/question-detection LLM call** — `extractor.extract()`'s one
  JSON-mode call already returns `turn_intent`, `detected_question`, `rewritten_query`, `objection`,
  `wants_human`, `wrong_number`, `do_not_call`, `sentiment`, and `confirmation_response` together.
  Much of what a consolidated "TurnUnderstanding" call would add is already consolidated here.
- There is **no separate planner LLM call** — `planner.decide()` is pure Python (confirmed both by
  reading it and by the real `engine_planning: 0ms` measurement). The priority ladder (safety →
  human-handoff → clarify-low-confidence → pending-confirmation → ask-required-field →
  ask-optional-field → complete) is deterministic and free today.
- There is **no separate query-rewrite LLM call** — `rewritten_query` is produced inside the same
  extraction call, not a second call.
- There is **no reranking step at all** — `rag.search_knowledge()` does embed → pgvector
  `ORDER BY cosine_distance LIMIT top_k` → return. No LLM reranker exists in this codebase to
  measure or remove.
- **RAG is already conditional**, not unconditional — `engine.py` only calls
  `rag.search_knowledge()` `if decision.rag_query:`, and `planner.py` only sets `rag_query` when
  `extraction.detected_question` is true. The real call's own data (RAG on 2 of 6 turns) already
  demonstrates this — it was never the "always calls it" black box this phase's spec assumed.

**What genuinely is missing**, confirmed by reading the code, not assumed:
- No deterministic pre-LLM fast path — a do-not-call phrase, a "yes"/"no" confirmation reply, or
  "tomorrow evening" for a pending field all currently pay for the full extraction LLM call before
  `policy.apply_backstop()` (a pure-Python safety net) even runs.
- Every non-terminal action (`ASK_FIELD`, `CLARIFY`, `CONFIRM_FIELD`, `DEFER_QUESTION`) always calls
  the LLM for response generation when a real client is configured — even though a tested, natural,
  already-used-in-mock-mode canned template exists for every one of them
  (`prompt_builder._fallback_text()`).
- `OpenAILLMClient.complete_json`/`complete_text` and `embeddings.py::_openai_embed` each open a
  brand-new `httpx.AsyncClient()` (and therefore a brand-new TCP+TLS connection) per call — see §3
  for whether this actually matters here.

## 2. Real call data (the P3 diagnostic call, `0066d4d3-...`)

| Stage | Avg | Max | Calls |
|---|---|---|---|
| `engine_extraction` | 1993ms | 2701ms | 6/6 turns |
| `engine_rag` | 1679ms | 2233ms | 2/6 turns (only when a question was detected) |
| `engine_generation` | 726ms | 1295ms | 6/6 turns (varies — 0 internally for canned-only actions, not reflected as a separate row since `_record_latency` isn't called when generate() short-circuits before any timed work — this average is pulled up by turns that did call the LLM) |
| `engine_domain_vocabulary` | 9ms | 20ms | 6/6 turns |
| `engine_planning` | 0ms | 0ms | 6/6 turns |

## 3. Direct probes — isolating what "RAG = 1.7s" and "extraction = 2s" actually are

Run from this machine against the real, configured OpenAI endpoints (not mocked), during this audit:

**Connection reuse experiment** (toy "say hi" completion, `max_tokens=5`):
```
cold (new client per call):      1745ms, 948ms
shared client, 1st call:          793ms
shared client, subsequent calls:  953ms, 915ms, 667ms, 693ms
```
**Extraction-shaped call** (real system+user prompt from `extractor.py::_build_prompt`, JSON mode,
`max_tokens=400`, 241 prompt tokens / 127 completion tokens on this exact payload):
```
warm-connection call #1:  1772ms
warm-connection call #2:  1631ms
warm-connection call #3:  2009ms
fresh-client call (matches production code path today): 1924ms
```
**Embedding call** (`text-embedding-3-small`, one short query):
```
warm-connection call #1: 2227ms
warm-connection call #2:  543ms
```

**Conclusion, stated plainly**: connection reuse makes essentially **no measurable difference** for
the realistic extraction-shaped call — 1631-2009ms warm vs. 1924ms fresh, well within normal
variance. The ~1.7-2s cost is the OpenAI API round-trip itself (network RTT to a US endpoint from
wherever this server runs + queueing + inference + JSON-mode generation of ~127 tokens), not TCP/TLS
handshake overhead. This directly contradicts the natural assumption that connection pooling would
be the fix — **it is still implemented in this phase (§5) because it's correct, free, and this
phase's spec explicitly asks for it, but it is documented here as a minor, not the primary, lever.**

The embedding call's own variance (543ms-2227ms across two calls) suggests the embedding endpoint
specifically has more inconsistent tail latency than chat completions on this network path — still
not conclusively a connection-reuse artifact given the "warm" first call was the *worse* of the two.

**What this means for where the real leverage is**: given every LLM call to this specific provider
from this specific network path costs roughly 700ms-2s regardless of connection state, **the highest-
leverage, most reliable optimization is not making the calls faster — it's making fewer of them.**
That is what this phase's actual code changes (§4/§5 below) focus on: a deterministic pre-LLM fast
path (zero calls for safe, high-confidence turns) and reusing the existing canned-response templates
for the second call (response generation) instead of a first-principles rewrite of how the extraction
call itself works.

## 4. Scope decisions made from this audit (and why)

**Built this phase** (see `docs/P3_5_CONVERSATION_ENGINE_RESULTS.md` for what actually shipped):
connection reuse (correctness fix, modest measured benefit), fine-grained RAG sub-stage timing,
a deterministic `FastTurnRouter` (real zero-LLM win for safety/confirmation/handoff/acknowledgement
turns), a fast canned-response path reusing the *already-tested* `_fallback_text()` templates for
safe non-terminal actions (real one-call win, no new generation-quality risk since nothing new is
being generated), per-call domain-vocabulary caching (real but small — 9ms/turn), and configurable
model names.

**Deliberately not built this phase, with reasons** (not silently dropped):
- **A separate consolidated "TurnUnderstanding" model call replacing extraction** — the audit above
  shows extraction already consolidates field extraction + intent + question detection + objection +
  safety flags + confirmation classification into one call, and the planner is already free. Building
  a second, parallel structured-output pipeline to replace something that's already ~80% consolidated
  would add real engineering weight (a new prompt, a new schema, a new failure-fallback path, a new
  parity-testing surface) for a smaller marginal win than the numbers here suggested going in.
- **LLM-co-produced `spoken_response_draft` in the extraction call itself** — the same call cannot
  know the planner's decision (which field to ask, whether RAG is above threshold) since the
  deterministic planner runs *after* extraction; asking the model to *also* predict `next_action`
  would mean re-deriving, in a probabilistic call, logic the free deterministic planner already gets
  exactly right. Implemented instead as reusing the already-existing, already-natural canned
  templates for the *actual* decision the real planner made (§5) — same latency outcome for the
  common case, without a second source of next-action truth.
- **Live "shadow mode" dual-execution on real calls** — deferred in favor of deterministic,
  reproducible scenario tests (this phase's §required tests) for the same "don't ship silent
  correctness regressions" goal, without needing new dual-execution infrastructure that didn't exist
  before. A real-call shadow comparison is a reasonable later hardening step once `fast` mode is
  closer to being the default, not before.
- **L1 FAQ/lexical cache with knowledge-version invalidation** — a genuinely separate, substantial
  feature (new cache storage, invalidation-on-knowledge-change, a structured FAQ index format) on the
  scale of the domain-vocabulary work from the previous session phase. Well-specified as a follow-up,
  not attempted here given the size of everything else in this pass.
- **Reranking removal/measurement** — moot; no reranker exists in this codebase to remove or measure.
- **Partial-STT speculative RAG prefetch** — explicitly optional per this phase's own spec; not built.
