# P6 — Streaming TTS: Results & Verification Status

See `docs/P6_STREAMING_TTS_AUDIT.md` (what P6 replaces), `docs/SARVAM_STREAMING_TTS_CONTRACT.md`
(verified live wire contract), and `docs/STREAMING_TTS_ARCHITECTURE.md` (what shipped and why). This
doc states what has and hasn't been verified, honestly — same practice as every previous phase.

## P5 baseline — result

410 tests confirmed passing repo-wide before any P6 code was written, per this phase's own instruction.

## What shipped

- `live_providers/streaming_tts.py` — provider-neutral `StreamingTTSProvider` Protocol, `TTSCapabilities`,
  `StreamingTTSConfig`, the full `TTSStreamEvent` model.
- `live_providers/sarvam_streaming_tts.py` — the real Sarvam WebSocket client. Contract verified **live**
  against the real API before writing any code — the docs' own claim ("MP3 only, currently supported")
  turned out to be stale; live probes confirmed `output_audio_codec=mulaw` + `speech_sample_rate=8000`
  returns raw, headerless audio in Twilio's exact wire format. Also discovered live: Sarvam's
  `request_id` is scoped to the whole connection, not per-response — our own `response_id` bookkeeping is
  the only correlation mechanism available, not an optional nicety.
- `transport/tts_bridge.py` — `TTSStreamingSession` (one persistent connection per call, ordered
  text-sender task, audio-consumer task), `TTSResponseHandle`, `begin_response_feed()`,
  `chunk_text_for_tts()` (reuses P5's `SpeakableChunker` for already-known text).
- `transport/session.py` — `RealtimeMediaSession.wait_for_mark_ack()` (the real fix for closing-grace
  starting before playback actually finished), `OutboundAudioChunk.mark_name`/`audio_is_mulaw_8k`.
- `transport/transitional_bridge.py` — `speak_turn_reply()`, unifying both turn loops' reply-to-audio
  logic into one function with the streaming-with-batch-fallback policy implemented once.
- Both real-call turn loops (`twilio_media_stream.py`'s `_run_batch_turn_loop`, `streaming_bridge.py`'s
  `_commit_turn_to_engine`) wired to feed `on_speakable_chunk` into `process_turn()` and route through
  `speak_turn_reply()`.
- `TTS_MODE=batch` (default) / `=streaming`, `TTS_STREAM_FAILURE_POLICY=batch_fallback` (default) /
  `=fail`, both validated against `TWILIO_VOICE_TRANSPORT` (silently degrades to batch under `record`,
  same posture as every other transport-dependent flag in this codebase).
- A real, found-while-building fix: `_finish_response()` would have hung forever if a TTS connection
  died mid-response with no completion event ever arriving — now bounded by a 30s timeout that resolves
  to a normal failure, flowing through the same fallback policy as any other provider failure.

## Verified — unit and targeted integration tests, all real, all passing

**213 tests in `services/api`** (160 baseline + 53 new), unchanged counts elsewhere (184
`packages/conversation` + 32 `packages/db` + 10 `services/voice-worker` + 13 `services/campaign-worker` +
11 `services/intelligence-worker`) — **463 tests passing repo-wide, zero failures.**

The 53 new tests, by file:
- `test_sarvam_streaming_tts.py` (19) — config message wire format (mulaw/8000/pace/speaker), send_text/
  flush wire format, first-audio-event-fires-once-per-response, two responses on one connection each
  getting their own `TTSFirstAudio` (realistic ordering — second response's text only sent after the
  first's completion was observed, matching real `tts_bridge.py` usage), local-only cancellation
  dropping subsequent audio for a cancelled response, full error-classification table, idempotent close.
- `test_tts_bridge.py` (11) — strict text ordering into the provider (chunk_index monotonically
  increasing), `finish()` returning the correct final mark name and first-audio timing, failure with
  zero chunks sent vs. failure after partial audio (the exact spec §71/§72 distinction), generation-
  ownership supersede (old response marked failed + provider.cancel() fired), two independent
  `TTSStreamingSession`s never crossing response ids or audio bytes, the dead-connection timeout.
- `test_speak_turn_reply.py` (7) — empty-reply no-op, callback-fired skips re-feeding (no double-speak),
  callback-not-fired chunks the formatted text locally, batch fallback exactly when zero audio was ever
  sent, **no** fallback attempted when partial audio was already delivered, fatal only when both
  streaming and batch fallback fail, batch-mode-with-no-handle uses the original path unchanged.
- `test_media_session.py` (+5) — `wait_for_mark_ack()`: already-acknowledged returns immediately,
  resolves when the ack arrives later, times out cleanly if it never arrives, cleans up its own waiter
  state after a timeout (no leak), and two different marks are never confused with each other.
- `test_send_loop_audio_format.py` (4) — a `mulaw`-flagged chunk is forwarded as a byte-for-byte base64
  passthrough (**no RIFF/WAVE/ID3 header ever reaches the payload**, spec §96 directly verified), the
  mark name used is the one assigned at enqueue time (not regenerated), the existing PCM16 batch path
  still goes through `encode_twilio_media_payload()` unchanged, and a legacy chunk with no pre-assigned
  mark name still gets one generated on the fly.
- `test_connect_streaming_tts.py` (3) — `VoicePersona`'s resolved speaker actually reaches
  `StreamingTTSConfig.voice_id` (spec §17), no-persona-configured leaves `voice_id=None` (provider
  default, same policy `SarvamTTS` already has), and a connect failure degrades gracefully rather than
  raising into call setup.
- `test_config.py` (4) — `effective_tts_mode` defaults to `batch`, silently degrades under
  `TWILIO_VOICE_TRANSPORT=record`, actually activates under `media_stream`, failure-policy default.

## Real-provider benchmark — 10 real connections, live Sarvam API

Ran through the actual production code (`SarvamStreamingTTS` → `TTSStreamingSession` → a real
`RealtimeMediaSession`'s real outbound queue), `bulbul:v3`, `priya`, across the same five categories P5's
own benchmark used (Telugu-English/Hindi-English/English, ask-field/RAG/objection/multi-intent). Two
full passes = 10 samples, meeting the "10+ before any P50/P95 claim" bar this session has held to
throughout.

| Metric | n | min | P50 | P95 | max | avg |
|---|---|---|---|---|---|---|
| Connect time | 10 | 125ms | 140ms | 169ms | 179ms | 144ms |
| First audio (send → first chunk received) | 10 | 205ms | 218ms | 238ms | 238ms | 220ms |

Zero failures across all 10 real calls. Average 47 audio sub-chunks per multi-sentence response,
confirming the contract doc's "Sarvam already does reasonable packetization" finding held up under
repeated sampling, not just the original one-off probe.

**Combined with P5's own real numbers** (LLM first-speakable-chunk P50 ~1069ms, P95 ~1610ms): since TTS
connects once at call start (its ~140ms is paid before the customer ever speaks, never per-turn), the
per-turn addition on top of P5's first-speakable-chunk latency is just the ~218ms TTS-first-audio time —
**estimated turn-committed → first-agent-audio-ready P50 ≈ 1069 + 218 ≈ 1.29s**, P95 ≈ 1610 + 238 ≈
1.85s, before accounting for audio conversion (a no-op passthrough for the verified mulaw path — not a
meaningfully measurable additional cost) and the actual Twilio media-send call (in-process, sub-
millisecond). This is an estimate combining two independently-measured real numbers, not a single
end-to-end real-call measurement — see "NOT done" below.

## Concurrency proof (spec §44/§93) — demonstrated at the unit level

`test_text_sent_to_provider_in_order` and the two-responses-on-one-connection test in
`test_sarvam_streaming_tts.py` directly prove chunks are sent to the provider incrementally as
`send_chunk()` is called, not batched — combined with `begin_response_feed()`'s callback wiring (proven
in `test_tts_bridge.py`'s `test_begin_response_feed_tracks_whether_callback_fired`), this establishes the
mechanism: an LLM `on_speakable_chunk` callback firing mid-generation feeds TTS immediately, before the
LLM has produced the rest of the response. What is **not** independently reproduced in a single test is
the full three-way race (LLM still generating chunk 2 WHILE chunk 0's audio has already reached Twilio)
end-to-end through a real `process_turn()` call — the pieces are each proven correct in isolation
(P5 proved the LLM-streaming side; this phase proves the TTS-consuming side), not stitched into one
combined real-time assertion this pass.

## NOT done — honestly

- **No real phone call has been placed with `TTS_MODE=streaming`.** `.env` has it unset (default
  `batch`) — same policy every phase has held: a response-audible flag doesn't get flipped live without
  the user's own test call. See the manual verification plan below.
- **No full DB-backed integration test** (real `ConversationEngine` + real `TurnManager` + mocked
  provider network boundaries only, spec §115) was written this pass. Each layer is unit-tested
  thoroughly and independently (the provider's wire contract, the bridge's ordering/ownership/failure
  logic, the turn-loop wiring's fallback policy, the audio format at the byte level) — what's not
  independently re-proven is the full chain end-to-end against a real Postgres-backed call session. A
  reasonable next step, not a silently skipped one.
- **No audio quality / prosody / chunk-seam listening review** (spec §85-91) — this requires a human
  actually listening to real synthesized speech across chunk boundaries, which cannot be done inside
  this session. The benchmark above confirms chunks arrive correctly-formed and in order; it says
  nothing about whether they sound natural strung together.
- **TTS WebSocket reconnect** is not implemented — a connection that drops mid-call is not
  automatically re-established for later turns (the dead-connection timeout prevents a hang for the
  CURRENT response; nothing reconnects for the NEXT one). A real, scoped-out gap.
- **`VoicePersona.speaking_speed`** still isn't threaded into `StreamingTTSConfig.pace` — the same
  pre-existing gap the P6 audit doc flagged in the batch path (`SarvamTTS.synthesize()` has never
  accepted a pace parameter either). `pace` defaults to `1.0` throughout.
- **Pronunciation dictionaries** — verified as a real, working Sarvam config field
  (`dict_id`), not wired into any agent-facing configuration surface this pass (spec §65 permits this).

## Manual real-call verification plan

Once the user is ready:
1. Set `TTS_MODE=streaming` (requires `TWILIO_VOICE_TRANSPORT=media_stream`; works under either
   `STT_MODE` and either `LLM_RESPONSE_MODE`, though `LLM_RESPONSE_MODE=streaming` is needed to see the
   LLM/TTS overlap this phase's KPI is actually about — under `LLM_RESPONSE_MODE=complete`, streaming TTS
   still helps via local chunking, just without LLM overlap).
2. Place one authorized test call covering: a plain field-ask turn, a RAG-answered question, an
   objection, a turn in each of Telugu-English/Hindi-English/English, and a full call through to closing
   (to directly confirm the mark-wait grace-period fix and that the duplicate-closing-reaffirm behavior
   from P4/P5 still holds).
3. Pull `call_events`/`call_latency_metrics` for that call and compare the actual
   `tts_stream_connected`/`tts_response_superseded` (should never fire in normal operation) event log
   against what this doc predicts.
4. Listen specifically for: reply start delay (should feel faster than a `TTS_MODE=batch` call on the
   same script), audible chunk seams/prosody breaks, any dead air, correct voice/language throughout,
   and that the closing plays fully before the call actually ends.
5. Compare against the same scripted turns with `TTS_MODE=batch` to hear the actual before/after.

## Definition-of-done, honestly marked

Provider abstraction, real verified Sarvam WebSocket implementation, one persistent connection per call
reused across turns, `VoicePersona`/language-profile control, P5 `SpeakableChunk` feeding TTS in real
time, LLM-continues-while-TTS-synthesizes (the underlying mechanism, unit-proven), audio arriving before
full response completion, correct μ-law/8kHz/no-header audio, ordered text and audio, bounded queues,
mark tracking, closing-grace-waits-for-real-playback, duplicate-closing-fix preserved, cancellation
primitive, minimal generation ownership, streaming-failure fallback (before vs. after audio, correctly
distinguished), batch fallback preserved, real-provider latency numbers — **done, tested**.
Real-call verification, audio quality review, full DB-backed integration test, TTS reconnect,
`speaking_speed`/pronunciation-dictionary wiring — **not done**, explicitly flagged, not silently
claimed. Ruff/mypy — **clean** on every touched/new file. No automatic git commit — **honored**.

## What's still unfinished after P6 (restated, per spec §142)

```
P3:  Streaming STT                          — DONE
P3.5: Conversation fast paths                — DONE
P4:  Turn detection                          — DONE
P5:  Streaming LLM                           — DONE
P6:  Streaming TTS                           — DONE (architecturally + unit/targeted-integration-tested; real-call verification pending)
P7:  Broader pipeline/backpressure tuning    — NOT DONE
P8:  Automatic barge-in                      — NOT DONE (primitives exist: TurnManager's USER_SPEECH_STARTED,
                                                 CancellationToken, StreamingTTSProvider.cancel() — nothing
                                                 wires them together yet)
P9:  Strict replay/stale-audio enforcement   — NOT DONE (minimal generation-ownership lock only)
```
