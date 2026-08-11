# P7 — Realtime Pipeline Audit

## Baseline

463 tests confirmed passing repo-wide before any P7 change (184 `packages/conversation` + 32
`packages/db` + 213 `services/api` + 10 `services/voice-worker` + 13 `services/campaign-worker` + 11
`services/intelligence-worker`).

## Real phone baseline

**NOT YET VERIFIED.** This environment has no ability to place an actual authorized Twilio phone call
(no interactive telephony/audio-device access). Per this phase's own explicit instruction for exactly
this case, P7 proceeds on implementation with this stated plainly rather than inventing a result — see
`docs/P7_REALTIME_PIPELINE_RESULTS.md` for the manual verification plan the user can run.

## The full call graph, traced (STT_MODE=streaming, the path P7 actually targets)

```
Twilio media frame (base64 mu-law)
  → twilio_media_stream.py::_receive_loop → decode_twilio_media_payload → AudioFrame
  → session.enqueue_inbound_audio()                                    [queue: inbound_audio_queue, bounded 250, DROP on full]
  → streaming_bridge.py::_forward_audio_to_stt → SarvamStreamingSTT.send_audio()
  → (Sarvam STT WebSocket, external)
  → SarvamStreamingSTT.events() → _drain_stt_events()
  → event_queue                                                        [queue: UNBOUNDED — see finding below]
  → _run_one_streaming_generation's poll loop → _handle_stt_event()
  → TurnManager.on_signal() / on_timer_tick() → TurnDecision.COMMIT_TURN
  → _commit_turn_to_engine() → process_known_transcript_turn()
  → jkr_conversation.engine.process_turn()
      → FastTurnRouter | extractor.extract()
      → RAG (rag.search_knowledge_with_timing(), if decision.rag_query)
      → prompt_builder.generate(response_mode=..., on_speakable_chunk=callback)
          → [complete mode] llm_client.complete_text() → one string, returned whole
          → [streaming mode] OpenAILLMClient.stream_text() → StreamingResponseAssembler.run()
              → SpeakableChunker.feed() per TextDelta
              → on_speakable_chunk(chunk) invoked SYNCHRONOUSLY, in-line, no queue between
                LLM-consumption and this callback
  → (turn loop) begin_response_feed()/on_chunk closure → TTSResponseHandle.send_chunk()
  → TTSStreamingSession._text_queue                                    [queue: bounded 64 (TEXT_QUEUE_MAXSIZE)]
  → TTSStreamingSession._run_sender() → SarvamStreamingTTS.send_text()/flush()
  → (Sarvam TTS WebSocket, external)
  → SarvamStreamingTTS.events() → TTSStreamingSession._run_consumer()
  → OutboundAudioChunk construction (mark_name assigned here, audio_is_mulaw_8k=True)
  → session.enqueue_outbound_audio()                                   [queue: outbound_queue, bounded 250, BLOCKS on full]
  → twilio_media_stream.py::_send_loop → base64 passthrough (mulaw) or encode_twilio_media_payload (PCM16)
  → websocket.send_json(media) → websocket.send_json(mark)
  → (Twilio, external)
  → Twilio sends back a `mark` event
  → _receive_loop → session.record_mark_acknowledged()
```

## Every queue, inventoried

| Queue | Producer | Consumer | Bound | Overflow behavior |
|---|---|---|---|---|
| `inbound_audio_queue` | Twilio receive loop | `_forward_audio_to_stt` (streaming) / turn buffer (batch) | 250 frames (~5s audio) | Drop + counted metric (never blocks receive loop) |
| STT `event_queue` | `_drain_stt_events` | `_run_one_streaming_generation` poll loop | **none — `asyncio.Queue()`** | Unbounded growth if the poll loop stalls |
| TTS `_text_queue` | `on_speakable_chunk` callback / locally-chunked canned text | `TTSStreamingSession._run_sender` | 64 items | Blocks producer (backpressure) — no drop policy |
| `outbound_queue` | `TTSStreamingSession._run_consumer` / batch `_send_pcm_reply` | `_send_loop` | 250 chunks | Blocks producer (backpressure) — no drop policy |

**Finding**: the STT `event_queue` in `streaming_bridge.py::_run_one_streaming_generation` has no
`maxsize` — the one genuinely unbounded queue in the hot path (spec §43). In practice its growth is
bounded by STT event cadence (per-utterance partial/final events, not per-audio-frame), not by raw audio
throughput, so the practical risk is much lower than an unbounded audio-frame queue would be — but it's
still a real gap against the "every hot-path queue must be bounded or explicitly justified" rule, fixed
in this phase (see architecture doc).

**Finding**: there is no separate "LLM chunk queue" — `on_speakable_chunk` is a direct, synchronous
callback invoked from inside `StreamingResponseAssembler.run()`'s own event loop, not a queue. The first
actual queue a chunk of text passes through is the TTS `_text_queue`. This matches the code as it exists
today (not the section 33 assumption of a distinct LLM-chunk queue) — documented in the architecture doc
rather than adding an unneeded intermediate queue.

## Generation identifiers, before P7

- `jkr_conversation.streaming_response.SpeakableChunk`: `response_id`, `generation_id`, `chunk_index` —
  minted fresh per `StreamingResponseAssembler.run()` call (i.e., per LLM generation attempt).
- `TTSStreamingSession`: its OWN `response_id` concept (reused from `SpeakableChunk.response_id` when
  fed via the callback, or freshly minted via `begin_response()`'s default for locally-chunked text) —
  tracks `_active_response_id`, `_pending: dict[str, _PendingResponse]`, superseding an unfinished
  previous response when a new one begins (P6's minimal ownership lock).
- `RealtimeMediaSession`: `current_response_sequence_id`/`current_response_chunk_index` (set by
  `start_new_response_sequence()`, used only by the BATCH `_send_pcm_reply` path — the streaming path
  via `TTSStreamingSession` never calls this, using its own `response_id` instead). **Finding**: two
  parallel, not-fully-unified "response identity" concepts exist today (`RealtimeMediaSession`'s own
  sequence counter for batch, `TTSStreamingSession`'s `response_id` for streaming) — P7's coordinator
  unifies these into one authoritative identity per response, used by both paths.
- `SarvamStreamingTTS`: its own `_active_response_id` (see P6 contract doc) tags outgoing
  `TTSStreamEvent`s — trusts the caller never to start response N+1 before response N's completion was
  observed (documented, not defensively enforced — see the P6 provider file's own comment).

**No generation identifier exists yet for**: an LLM generation independent of its `SpeakableChunker`
instance (each `StreamingResponseAssembler.run()` call mints one internally, but nothing outside that
call can check "is this still the current generation" mid-stream — there is no external cancellation
check inside the assembler's own loop beyond the `CancellationToken` no caller currently sets). A TTS
WebSocket *connection* generation (for reconnect — P6 didn't implement TTS reconnect at all, so this
doesn't exist; P7 adds it, see the results doc).

## Ownership checks, before P7

- `TTSStreamingSession.begin_response()`: supersedes an unfinished previous response (marks it failed,
  fires `provider.cancel()`, drops its future audio via the `pending.event.is_set()` check in
  `_run_consumer`). This is real, tested ownership — but scoped ONLY to the TTS layer. Nothing upstream
  (the LLM `on_speakable_chunk` callback itself) checks whether its own generation is still "current"
  before calling `send_chunk()` — a superseded response's callback, if somehow still firing, would still
  successfully enqueue text (which would then be correctly dropped downstream by TTS-layer ownership,
  but only after the wasted round trip).
- No call-level "one active response" enforcement exists above the TTS layer — `process_known_
  transcript_turn()` is only ever invoked once per turn today because both turn loops process turns
  strictly sequentially (no concurrent turn processing exists), so in practice this has never been
  violated — but nothing STRUCTURALLY prevents it the way P7's coordinator will.

## Playback/mark accounting, before P7

`RealtimeMediaSession` tracks `marks_sent`/`marks_acknowledged` as flat lists and `playback_state`
(IDLE/PLAYING/CLEARING) as one call-wide enum — correct for "is anything currently playing," but with no
per-chunk/per-response granularity: there's no way today to ask "was THIS specific piece of audio played
or cleared." `wait_for_mark_ack()` (added in P6) answers "did this one mark eventually get acknowledged"
but doesn't distinguish a genuine playback acknowledgement from one that arrives for audio that was
actually cleared first (spec §30's PLAYED-vs-CLEARED distinction doesn't exist yet — `record_mark_
acknowledged()` doesn't know a `clear` happened at all right now). This is the single most important gap
P7 closes for P8's future benefit.

## Dead-air / stall detection, before P7

None. If the LLM stalls, if TTS stalls, if Twilio's send queue stops draining — nothing today measures
"how long has it been since the customer heard anything" or attributes a delay to a specific pipeline
stage. `RESPONSE_COMPLETION_TIMEOUT_SECONDS=30` (added in P6) is the only timeout in the whole streaming
path, and it only fires once, at the very end of a response's TTS lifecycle — not a running watchdog.

## Event loop lag, before P7

Not measured anywhere in this codebase.

## `VoicePersona.speaking_speed`, before P7

Modeled in the DB (`packages/db/jkr_db/models/agents.py::VoicePersona.speaking_speed`, default `1.0`)
but never read by any TTS call site — confirmed by grep, flagged in both the P6 audit and results docs,
not yet fixed.

## TTS reconnect, before P7

None. `_connect_streaming_tts()` connects once at call start; if the connection dies at any point
(between responses or mid-response), nothing reconnects it — the call silently stays on `TTS_MODE=batch`
behavior for the rest of the call only in the sense that `session.tts_streaming_session` would need to
be re-checked per turn anyway (it isn't invalidated automatically, so a dead connection would just start
failing every subsequent `send_text`/`flush` call, correctly triggering `speak_turn_reply`'s existing
batch-fallback policy per turn — inefficient, but not silently broken; still, no reconnect is attempted).
