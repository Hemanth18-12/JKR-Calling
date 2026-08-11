# P5 — Streaming LLM Response Architecture

See `docs/P5_STREAMING_LLM_AUDIT.md` (what P5 replaces, and the pre-existing bug fixed as its own
gate) and `docs/P5_STREAMING_LLM_RESULTS.md` (what shipped, verified, and measured) for the rest of
the picture. This doc is the "what it is and why," parallel to `docs/TURN_DETECTION_ARCHITECTURE.md`.

## Where it lives

Everything new is in `packages/conversation/jkr_conversation/` — response generation is a shared
engine concern (both the real Twilio call path and Test Lab go through `prompt_builder.generate()`),
not a `services/api`-specific one, same reasoning `OpenAILLMClient` itself already follows.

- `_shared_http.py` — a process-lifetime `httpx.AsyncClient` singleton shared by `llm_client.py`'s
  batch calls and `streaming_llm.py`'s streamed calls, extracted into its own module so neither of
  those two depends on the other (avoids the import cycle `OpenAILLMClient.stream_text()` would
  otherwise create).
- `streaming_llm.py` — `StreamingLLMProvider` protocol, the `LLMStreamEvent` union
  (`LLMResponseStarted` / `TextDelta` / `LLMUsage` / `LLMResponseCompleted` / `LLMResponseFailed`), and
  `stream_openai_chat_completion()` — a hand-rolled SSE parser matching OpenAI's actual wire format
  (verified live, see the audit doc), never raising, classifying every failure into an
  `LLMFailureClass`.
- `speakable_chunker.py` — `SpeakableChunker`, pure and stateful, turns a delta stream into
  speakable-sized text chunks at real sentence/clause boundaries.
- `streaming_response.py` — `StreamingResponseAssembler`, `SpeakableChunk`, `CancellationToken`,
  `StreamingGenerationResult` — ties the provider event stream to the chunker to the streaming-safe
  formatter, tracking timing/usage/cancellation.
- `formatter.py::strip_for_streaming_chunk()` — the per-fragment-safe subset of
  `SpokenResponseFormatter.format()` (markdown/URL stripping, whitespace normalization); sentence-count
  enforcement and acknowledgement-prepending stay whole-response-only, applied once on the fully
  assembled text exactly as before.
- `llm_client.py::OpenAILLMClient.stream_text()` — the streaming counterpart to the existing
  `complete_text()`, delegating to `streaming_llm.stream_openai_chat_completion()`.
- `prompt_builder.py::generate()` — four new optional keyword params (`response_mode`,
  `on_speakable_chunk`, `latency_sink`, `cancellation_token`), all no-ops unless
  `response_mode="streaming"`; return type stays plain `str`, unchanged for every existing caller.
- `engine.py::process_turn()` — forwards the same four params through to `generate()`, threading
  `latency_ms` in as the sink so `llm_ttft`/`llm_first_speakable_chunk`/`llm_full_generation` land in
  the same per-turn latency breakdown `rag_embedding`/`rag_vector_search`/`generation` already use.

## The core design decision: content-driven chunking, not timing-driven

`SpeakableChunker.feed()` only ever returns a completed chunk when an actual boundary character
(`.?!;।`) has arrived in the buffer — never because the token stream paused. There is no
timer/debounce logic anywhere in it. This satisfies the spec's "punctuation may arrive late — do not
emit early merely because the stream paused" requirement *by construction*, not by tuning a threshold:
there's no threshold to tune. `flush()` is the only place a chunk can be returned without a boundary
character, and it only runs once, when the underlying stream has genuinely ended.

Below `min_chunk_chars` (4 by default — low enough that "Yes." or "అవునండి." still qualify on their
own), a boundary character is not treated as a stopping point; it stays in the buffer and gets folded
into whatever chunk eventually does clear the threshold. Above `max_chunk_chars` (220 — the upper end
of a roughly 1.5-5 spoken-second chunk) with no sentence boundary in sight at all, `_force_cut_at_max()`
searches backward for the nearest clause boundary (`,` or `:`) before falling back to a hard character
cut — a long run-on sentence still gets split somewhere reasonable to say out loud, rather than
growing without bound.

## Event flow

```
OpenAILLMClient.stream_text(system, user, max_tokens)
  └─ streaming_llm.stream_openai_chat_completion(...)   — raw httpx SSE parsing, never raises
       yields: LLMResponseStarted → TextDelta* → LLMUsage? → LLMResponseCompleted | LLMResponseFailed

StreamingResponseAssembler.run(event_stream, cancellation_token=..., on_chunk=...)
  for each event:
    - cancellation_token.is_cancelled checked BEFORE processing (synchronous flag, no yield-point race —
      same reasoning TurnManager's own synchronous-by-design safety already relies on)
    - TextDelta → SpeakableChunker.feed(text) → 0+ raw chunks → strip_for_streaming_chunk() → SpeakableChunk
    - each new SpeakableChunk: appended to the result AND (if given) on_chunk(chunk) invoked immediately,
      DURING this coroutine's run — not after it returns. A future TTS consumer (P6) can start speaking
      the first chunk without waiting for the whole generation to finish; P5 itself has no live consumer
      of this yet (TTS stays batch), but the plumbing is real and tested, not stubbed.
    - LLMUsage → input_tokens/output_tokens captured
    - LLMResponseFailed → failed=True, loop stops; whatever chunks/text were already produced are kept,
      not discarded
  finally: gen.aclose() — always, on every exit path (normal completion, cancellation, or failure) —
  proper async-generator cleanup so a cancelled stream doesn't leak a live HTTP connection mid-response.
  after the loop (if not cancelled/failed): chunker.flush() picks up any leftover buffered text as a
  final chunk, or the last already-emitted chunk is marked is_final=True in place.

returns StreamingGenerationResult(full_text, chunks, ttft_ms, first_speakable_chunk_ms,
                                   full_generation_ms, input_tokens, output_tokens, cancelled, failed, ...)
```

`prompt_builder._generate_streaming()` wraps this in its own `try/except` (a client that violates its
own "never raise" contract mid-stream must still fall back to canned text, same guarantee the
complete-mode branch already has) and returns `result.full_text if result.full_text else fallback` —
so a stream that fails before producing anything degrades to exactly the same canned fallback text
`generate()` already falls back to when `llm_client is None` or `complete_text()` returns `None`.

## Structural safety — unchanged from before P5, verified to still hold

`prompt_builder.generate()`'s existing early-return structure means `response_mode="streaming"` is
read for the first time only in the one branch that was already free-generation-eligible:

```
SAFETY_STOP / HUMAN_HANDOFF / COMPLETE_OBJECTIVE          → canned text, return BEFORE response_mode is ever read
llm_client is None                                         → canned fallback, return BEFORE response_mode is ever read
engine_mode=="fast" AND action in fast-path-eligible set    → canned fallback, return BEFORE response_mode is ever read
otherwise (the one free-generation branch)                  → response_mode selects complete vs. streaming here, and only here
```

So a call that would never have touched the LLM before P5 still never touches it now, streaming or
not — enforced structurally (the early returns), not by a flag someone could misconfigure. Covered by
dedicated tests in both `test_prompt_builder.py` and `test_engine.py` (canned actions, `engine_mode=
"fast"`, and a client without `stream_text` all confirmed to skip streaming or degrade gracefully).

## Generation identity and isolation

Every `StreamingResponseAssembler.run()` call mints its own `response_id`/`generation_id`
(`resp_<uuid>`/`gen_<uuid>`), and `prompt_builder._generate_streaming()` constructs a fresh
`StreamingResponseAssembler()` per call — there is no shared/reused assembler instance anywhere in the
production path, so there is no buffered chunker state that could leak between two different calls'
generations. Verified directly in `test_engine.py`'s two-call isolation test: two independently seeded
call sessions, streamed through the same `on_speakable_chunk` collector, produce disjoint
`generation_id` sets.

## Cancellation

`CancellationToken` is a plain boolean flag (`cancel()` / `is_cancelled`), not an `asyncio.Event` —
checked and set synchronously, so there's no race between "check" and "act" within a single-threaded
event loop, the same reasoning that makes `TurnManager` itself lock-free. This is the primitive P8
(barge-in) will call when a customer starts speaking mid-response; P5 does not wire anything up to
call `cancel()` yet — nothing in this phase produces a real interruption signal at the right moment,
that's P8's job. What P5 guarantees today: if something *does* call `cancel()`, the assembler stops
processing further events on the next loop iteration, closes the underlying generator properly, and
returns whatever partial text/chunks had already been produced rather than raising.

## Failure classification

`LLMFailureClass` (`AUTH_ERROR`, `RATE_LIMIT`, `TIMEOUT`, `CONNECTION_ERROR`, `PROVIDER_INTERNAL`,
`INVALID_REQUEST`, `STREAM_INTERRUPTED`, `UNKNOWN`) mirrors what's actually distinguishable from an
OpenAI HTTP response and from `httpx`'s own exception types — `401`/`403` → auth, `429` → rate limit,
`5xx` → provider internal, other `4xx` → invalid request, `httpx.TimeoutException` → timeout,
`httpx.ConnectError` → connection error, anything else → unknown. None of these ever propagate as a
raised exception out of `stream_openai_chat_completion()` — every failure mode becomes an
`LLMResponseFailed` event instead, matching this package's established "never raise into a live call"
contract that `complete_text()`/`complete_json()` already follow.

## The prompt fix: no generic openers

A live probe against the real streaming path (documented in the audit doc, and reconfirmed across a
broader 10-run benchmark for the results doc) caught the model opening a Telugu-English/Hindi-English
response with a bare English filler ("Sure!") before anything useful, on the very first real test.
This matters more under streaming than under complete mode: the first chunk spoken is whatever opens
the response, so a generic opener wastes the exact head start streaming exists to create.
`prompt_builder._build_prompt()`'s SPEECH STYLE section now explicitly instructs the model to start
with the actual answer/action and never open with "Sure"/"Okay"/"Absolutely"/"I understand"/"I'd be
happy to help" — a prompt instruction, not a structural guarantee (the model could still ignore it),
but the same class of fix this codebase already uses for tone/style throughout `_build_prompt()`.

## Feature flags

`LLM_RESPONSE_MODE=complete` (default) is byte-identical to pre-P5 behavior: `generate()` always calls
`llm_client.complete_text()` and returns the full response in one piece; `response_mode`/
`on_speakable_chunk`/`latency_sink`/`cancellation_token` are never read. `=streaming` routes eligible
free-generation turns through `StreamingResponseAssembler` instead. Wired into
`services/api/app/config.py` (`Settings.llm_response_mode`) and threaded through both real-call sites
(`live_call/service.py`'s two `process_turn()` calls, `transport/transitional_bridge.py`'s one) the
same way `conversation_engine_mode` already is. `services/voice-worker`'s Test Lab call site is
untouched, same precedent P3.5 set for `engine_mode` — it stays on `response_mode="complete"`
(the default) unless a future pass explicitly wires it in.

## What P5 explicitly does not do (per spec, restated)

- **Streaming TTS** — not yet, P6. `SpeakableChunk`s exist and are tested, but nothing in the real-call
  path synthesizes speech from them today; the final `formatted.text` (built from the complete,
  assembled response, exactly as before) is still what gets sent to batch TTS.
- **Full LLM→TTS pipeline concurrency** — not yet. `on_speakable_chunk` is a real, working callback
  (invoked synchronously during generation, proven by tests), but no production call site passes one
  yet — there's no live consumer to hand chunks to until P6 exists.
- **Automatic barge-in** — not yet, P8. `CancellationToken` is the primitive P8 will call on a detected
  interruption; nothing calls `cancel()` in this phase.
- **Strict stale-audio rejection** — not yet, P9.
- **Speculative/preemptive generation** — not started before a turn is fully committed; P5 only touches
  what happens after `USER_TURN_COMMITTED`, unchanged from P3/P4's own turn-commit boundary.
