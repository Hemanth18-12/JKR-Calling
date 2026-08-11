# P6 — Streaming TTS Audit

## P5 baseline — result

410 tests passing repo-wide (184 `packages/conversation` + 32 `packages/db` + 160 `services/api` + 10
`services/voice-worker` + 13 `services/campaign-worker` + 11 `services/intelligence-worker`), confirmed
by re-running the full suite before any P6 change, per this phase's own instruction. This is the number
P6 is measured against.

## Current TTS path, traced

```
turn_result.reply_text (a complete string — batch or, since P5, LLM-streamed-then-assembled either way)
  → synthesize_for_stream(text, ...)  [transitional_bridge.py]
      → SarvamTTS(api_key, speaker).synthesize(text=text, language_code=...)
          → POST https://api.sarvam.ai/text-to-speech  (one REST call, whole text, base64 WAV response)
      → wav_bytes_to_pcm16(wav_bytes)  [audio_codec.py]
  → _send_pcm_reply(session, pcm16_bytes, sample_rate)  [twilio_media_stream.py]
      → session.start_new_response_sequence()
      → ONE OutboundAudioChunk (the entire reply's audio, unsplit)
      → session.enqueue_outbound_audio(chunk)
  → _send_loop: dequeue → encode_twilio_media_payload (resample + μ-law encode) → one `media` message
                → one `mark` message right after
```

**This is a single, fully-blocking round trip per turn**: nothing downstream of `process_turn()` sees
any audio until the *entire* REST response has arrived and been base64-decoded. P5's `LLM_RESPONSE_MODE
=streaming` already exists and measurably reduces time-to-first-speakable-text (`docs/
P5_STREAMING_LLM_RESULTS.md`), but **nothing consumes that early text today** — `process_known_
transcript_turn()` (`transitional_bridge.py`) calls `process_turn(..., response_mode=settings.
llm_response_mode)` and only ever reads the final `result.reply_text` after the whole call returns; no
`on_speakable_chunk` callback is passed anywhere in `services/api`. P5's own results doc says this
plainly: "No production call site passes an `on_speakable_chunk` callback yet." P6's job starts exactly
there.

## Which call sites reach TTS

Two turn loops both end up calling the same `synthesize_for_stream()` + `_send_pcm_reply()` pair, on the
full assembled reply text, every time:
- `twilio_media_stream.py::_run_batch_turn_loop` (STT_MODE=batch, or the streaming-STT
  `batch_next_turn` fallback) — one call site for the mid-call reply, one for the greeting.
- `streaming_bridge.py::_commit_turn_to_engine` (STT_MODE=streaming) — the same pair.

Both also independently implement a **closing grace-period timer that starts immediately after
enqueueing the reply's audio**, not after Twilio confirms it actually played:

```python
if turn_result.force_close:
    in_grace_period = True
    grace_deadline = time.monotonic() + GRACE_SECONDS   # starts NOW, not after playback
```

This is exactly the bug pattern P6's spec warns against (§59-61: "Sarvam completion ≠ closing playback
completion"). It has been survivable so far only because (a) TTS has always been synthesized in full
before `_send_pcm_reply` is even called, so there's no partial-audio case today, and (b) `GRACE_SECONDS
=4.0` combined with the existing `GRACE_SAFETY_MARGIN_SECONDS` re-arm logic (`recent < 1.5s` pushes the
deadline out) has apparently been generous enough in practice. It is still a real, fixable gap: a long
closing sentence whose audio takes longer than ~4s to actually finish playing through Twilio could, in
principle, have its grace period expire mid-playback. P6 fixes this properly using Twilio mark
acknowledgement, already tracked by `RealtimeMediaSession` but not yet awaited by anything.

## What already exists and is directly reusable (not being rebuilt)

- `RealtimeMediaSession` (`transport/session.py`): `playback_state` (IDLE/PLAYING/CLEARING),
  `marks_sent`/`marks_acknowledged` lists, `record_mark_sent`/`record_mark_acknowledged`,
  `start_new_response_sequence()`/`next_chunk_index()` (response/chunk-id foundation, unused by
  anything downstream today), `outbound_queue` (bounded, backpressure via blocking `put`),
  `request_clear_playback()`. **Missing**: any way to *wait* for a specific mark to be acknowledged —
  `record_mark_acknowledged` only ever flips `playback_state` back to IDLE and appends to a list; no
  caller can currently ask "has response R's *final* audio actually finished playing yet?" This is the
  one real gap P6 needs to close in `RealtimeMediaSession` itself (see architecture doc's "mark
  waiting" section) rather than building a wholly separate tracking object.
- `audio_codec.py`: `encode_twilio_media_payload()` already does exactly "resample if needed, PCM16 →
  μ-law, base64" in pure stdlib `audioop` — no ffmpeg, no temp files, already proven across every
  previous phase. Reused as-is for any path that still needs PCM→μ-law (kept as the fallback codec
  path); the Sarvam `mulaw`/8000Hz direct-output path verified in `docs/
  SARVAM_STREAMING_TTS_CONTRACT.md` needs **no conversion at all** — just base64 decode.
- `_send_loop`/`clear_agent_audio`/the single-serialized-sender architecture (`twilio_media_stream.py`):
  unchanged. Streaming TTS output still flows through `session.enqueue_outbound_audio()` →
  `dequeue_outbound_audio()` → this same loop, per spec §38 ("do not bypass the P2 sender
  architecture").
- `_resolve_tts_speaker()`/`_sarvam_language_code()` (`service.py`): the existing `VoicePersona
  .voice_id` → `tts_speaker` resolution and `agent.primary_language` → Sarvam BCP-47 code mapping are
  already correct and provider-agnostic in shape; reused directly for `StreamingTTSConfig`.
- `_shared_http.py` pattern: not applicable to a WebSocket client, but the "one connection reused, not
  recreated per call" philosophy it embodies is exactly what `SarvamStreamingSTT` already proved out for
  the STT side (`sarvam_streaming_stt.py`) — the new `SarvamStreamingTTS` provider mirrors that class's
  shape (`connect()`/`events()`/`close()`) directly rather than inventing a new pattern.
- `websockets` (v17.0.1) is already an installed, used dependency (via `sarvam_streaming_stt.py`) — no
  new dependency needed for the TTS WebSocket client either.

## VoicePersona — already authoritative, already wired correctly

`VoicePersona.voice_id`/`provider`/`speaking_speed` exist in the DB schema and `_resolve_tts_speaker()`
already refuses to pass a non-Sarvam persona's `voice_id` through as a literal speaker name (it returns
`None`, falling back to `SarvamTTS`'s own default). `speaking_speed` is modeled but **never actually
read anywhere** — `SarvamTTS.synthesize()` has no `pace` parameter at all today. This is a real, small
gap P6 closes by threading `VoicePersona.speaking_speed` into `StreamingTTSConfig.pace` (Sarvam's
streaming config accepts `pace` directly, verified in the contract doc).

## What's genuinely new for P6

1. A provider-neutral `StreamingTTSProvider` abstraction + the real `SarvamStreamingTTS` WebSocket
   client (contract verified live, not guessed — see `docs/SARVAM_STREAMING_TTS_CONTRACT.md`).
2. A per-call TTS input queue + worker that both turn loops feed — fed either by an `on_speakable_chunk`
   callback wired into `process_turn()` (LLM-streamed responses) or by a locally-chunked already-known
   string (canned/fast-path/complete-mode responses — spec §62-63: these should ALSO get the "first
   audio before the whole utterance is synthesized" benefit, not just LLM-streamed ones).
3. The mark-wait addition to `RealtimeMediaSession` + both turn loops' grace-period start moved to
   after the final mark is actually acknowledged, not after audio is merely enqueued.
4. `TTS_MODE=batch|streaming` (default `batch`) and `TTS_STREAM_FAILURE_POLICY` config, validated
   against `TWILIO_VOICE_TRANSPORT`.
5. Generation ownership (one active response sequence per call) and stale-connection/sequence
   discarding — a minimal version, explicitly not full P9.

## What stays completely untouched

`jkr_conversation` (engine, planner, extraction, RAG, domain correction, closing text templates,
`SpeakableChunker`, `StreamingResponseAssembler`) — P6 is a pure consumer of P5's `on_speakable_chunk`
hook, already designed for exactly this. `TurnManager`/STT (P3/P4) — unrelated to the outbound path.
`SarvamTTS` (batch REST client) — kept exactly as-is as the `TTS_MODE=batch` implementation and as the
streaming-failure fallback target.
