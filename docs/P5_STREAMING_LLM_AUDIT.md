# P5 — Streaming LLM Response Audit

## P4 verification gate (run before this audit, per P5's own instruction)

Docker was available this session. Ran the full DB-backed suite and found one real, pre-existing bug
(not previously visible): `asyncio.wait_for(anext(async_generator), timeout=...)` permanently kills
the generator if the timeout fires while it's suspended mid-body — confirmed empirically with a
minimal repro. This was dormant in P2/P3's original 1.0s poll cadence but became reliably reproducible
once P4 introduced a 0.1s poll for hybrid-mode responsiveness. Fixed by decoupling STT-event
consumption (a dedicated task, never subject to the poll timeout) from the poll itself (reads a plain
`asyncio.Queue`, safe to cancel) — see `streaming_bridge.py`'s `_drain_stt_events`. This also means the
bug could have silently caused unnecessary reconnects on any real call with more than ~1s of customer
silence, prior to this fix, unrelated to anything P4 was specifically testing for.

**Verified baseline after the fix: 353 tests passing repo-wide** (127 `packages/conversation` + 160
`services/api` + 32 `packages/db` + 10 voice-worker + 13 campaign-worker + 11 intelligence-worker),
zero failures. This is the real number P5 is measured against, not the earlier "311" figure quoted
before this session's Docker outage.

## Current response-generation path, traced

```
engine.process_turn()
  └─ prompt_builder.generate(decision, extraction, state, rag_chunks, ..., engine_mode)
       ├─ SAFETY_STOP / HUMAN_HANDOFF / COMPLETE_OBJECTIVE → canned text (closing.py/policy.py), ZERO LLM calls, always
       ├─ llm_client is None (mock mode) → _fallback_text() (canned), ZERO LLM calls
       ├─ engine_mode=="fast" AND action in {ASK_FIELD, CLARIFY, CONFIRM_FIELD, DEFER_QUESTION} → _fallback_text() (canned), ZERO LLM calls (P3.5)
       └─ otherwise → _build_prompt() → llm_client.complete_text(system, user, max_tokens=150) → ONE non-streaming LLM call
```

`OpenAILLMClient.complete_text()` (`packages/conversation/jkr_conversation/llm_client.py`) is the
**only** call site that reaches a real LLM for response generation. It does a plain
`POST https://api.openai.com/v1/chat/completions` with no `stream` parameter — the entire response
body is buffered by `httpx` before `response.json()` is even called. There is **no partial support of
any kind today** — no `stream=True` anywhere in this codebase, no SSE parsing, no chunk handling.

## Which response paths call the LLM, which don't

| Path | Calls LLM? |
|---|---|
| `SAFETY_STOP` | No — `policy.fallback_text()` |
| `HUMAN_HANDOFF` | No — `policy.fallback_text()` |
| `COMPLETE_OBJECTIVE` (any reason) | No — `closing.build_closing_text()`, always canned (this was P0's own fix for the abrupt-hangup bug) |
| `ASK_FIELD`/`CLARIFY`/`CONFIRM_FIELD`/`DEFER_QUESTION`, `engine_mode="fast"` | No — P3.5's fast canned-response path |
| `ASK_FIELD`/`CLARIFY`/`CONFIRM_FIELD`/`DEFER_QUESTION`, `engine_mode="legacy"`, real client configured | **Yes** — one `complete_text()` call |
| Any action with `mock` client (no `OPENAI_API_KEY`) | No — `_fallback_text()` |

So the LLM-required response path this phase targets is specifically: legacy-mode non-terminal
actions with a real client configured — the same call P3.5 already made conditional and provably
skippable for the *fast* path; P5's job is to make the cases that genuinely still need it faster to
start speaking from, not to touch the cases that already don't need it.

There is **no "fast response draft" field anywhere in `ExtractionResult` or the extraction prompt** —
P3.5's own audit doc explicitly documented choosing *not* to build one (the deterministic planner
decides `target_field`/`rag_query` *after* extraction runs, so an extraction-time draft can't reliably
target the real decision). P5's spec §26 references this as something that "if it exists" should be
used — it doesn't exist, and P5 doesn't change that; nothing in P5 needs it to exist.

## Formatter

`jkr_conversation/formatter.py::SpokenResponseFormatter.format()` operates on a **complete** string:
strips markdown/URLs, expands abbreviations, normalizes rupee amounts, splits into sentences and caps
at `max_sentences`, optionally prepends a rotating acknowledgement phrase. Every step needs the whole
text except markdown/URL stripping and whitespace normalization, which are safe per-fragment. This is
exactly what P5's own spec (§29-31) anticipates: a lightweight streaming-safe subset now, full
validation still happens on the assembled complete text.

## Verified: OpenAI's streaming SSE contract (real request against the live API, today)

No `openai` Python SDK is installed anywhere in this workspace (checked `uv.lock` — absent). Every
existing provider integration in this codebase (Sarvam STT/TTS/streaming-STT, OpenAI batch chat,
OpenAI embeddings) hand-rolls raw `httpx` calls — no SDK, by consistent established convention. P5
continues that pattern rather than introducing a new dependency this codebase has never used.

Live request with `"stream": true` confirmed the exact format:
```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"gpt-4o-mini-2024-07-18",
       "choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}],"usage":null}

data: {...,"choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}],"usage":null}

... (one line per token/content-fragment) ...

data: {...,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":null}

data: {...,"choices":[],"usage":{"prompt_tokens":24,"completion_tokens":42,"total_tokens":66}}

data: [DONE]
```
- One JSON object per `data:` line; `choices[0].delta.content` is the text fragment (absent/empty on
  the first and last content-bearing lines).
- `finish_reason` becomes non-null (`"stop"` normally) on the final content chunk, `delta` empty.
- With `"stream_options": {"include_usage": true}` in the request, one extra line arrives *after* the
  finish-reason line with `choices: []` and a populated `usage` object — this is the only place usage
  data appears in streaming mode (never mid-stream).
- Terminated by the literal line `data: [DONE]`.
- An `obfuscation` field is present on every chunk (anti-scraping noise) — ignored, not part of the
  contract.

## Real measured latency: streaming vs. complete, same prompt (not simulated)

Three runs each, real API, realistic response-generation prompt (Telugu-English, RAG evidence present,
`max_tokens=150`):

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Streaming TTFT | 1148ms | 892ms | 663ms |
| Streaming full completion | 1363ms | 1052ms | 833ms |
| Non-streaming (complete) full | 1209ms | 1088ms | 1395ms |

**Findings, stated honestly (three samples, not a P50/P95 claim)**:
- Streaming's TTFT (~900ms average) is meaningfully earlier than either streaming's own full
  completion (~1083ms) or non-streaming's full completion (~1231ms) — roughly a 200-300ms head start
  on when *something* is available, consistent with the spec's own expectation.
- Streaming's full-completion time and non-streaming's full-completion time are comparable (same
  underlying generation, streaming just doesn't buffer) — streaming isn't slower, and the real win is
  specifically in *when partial content becomes usable*, not in total generation time.
- **A real instance of the exact problem spec §21/§53 warns about was observed live**: 2 of 3 streamed
  responses opened with a generic "Sure!" in English before the useful content, even though the
  language policy is Telugu-English code-mixed — this is not a hypothetical risk, it happened on the
  very first real test. This directly motivates the prompt-instruction fix in
  `docs/STREAMING_LLM_ARCHITECTURE.md`.

## What P5 builds on top of this

Everything above is unchanged: `FastTurnRouter`, extraction, the planner, RAG, domain correction,
confirmation rules, tools, `ClosingManager`, `TurnManager`. P5 only changes what happens inside the one
remaining LLM-required branch of `prompt_builder.generate()` — replacing the single buffered
`complete_text()` call with a streamed one, decomposed into a provider-neutral event stream → an
assembler → a chunker → a lightweight formatter, landing on a `SpeakableChunk` the future P6 will hand
to streaming TTS. `LLM_RESPONSE_MODE=complete` (default) keeps today's exact behavior; `=streaming`
opts into the new path.
