# Sarvam AI Streaming STT — Verified API Contract (P3)

Researched against Sarvam's own AsyncAPI 2.6.0 spec (fetched as raw source via docs.sarvam.ai's
`.md` suffix on each reference page — not a paraphrase of rendered HTML) and cross-verified against
the actual installed `sarvamai` PyPI package (v0.1.30). Every concrete claim below is sourced; see
inline citations. Where something could not be verified, it's flagged explicitly rather than guessed
— this is what actually ships in `sarvam_streaming_stt.py`, not a superset of possibilities.

## Two streaming APIs exist — this project uses the Realtime one

| | **Realtime API (used by JKR)** | Streaming API (Legacy) |
|---|---|---|
| Model | `saaras:v3-realtime` | `saaras:v3` / `saaras:v4` |
| Endpoint | `wss://api.sarvam.ai/speech-to-text-realtime/ws` | `wss://api.sarvam.ai/speech-to-text/ws` |
| Partial transcripts | Yes | No (final-per-utterance only) |
| Mid-call reconfig | Yes (`config.update`) | No — reconnect required |
| 8kHz mu-law (telephony audio) | **Yes, directly** — `encoding=mulaw`/`linear16`, `sample_rate=8000` | No — WAV/PCM only |

Sarvam's own legacy-API doc page states the Realtime API "supersedes this endpoint for new
voice-agent and live-transcription work." That page also calls the Realtime API "(beta)" — but
Sarvam's separate beta-access index page does not list it, only `POST /v2/chat/completions`. The
Realtime endpoint's own documented error codes include a `4000` close explicitly triggered by "beta
denied." **Net: access is unverified until a real connection succeeds with this project's API key.**
See §6 (Failure handling) for how the adapter behaves if that connection is refused.

## Connection

- URL: `wss://api.sarvam.ai/speech-to-text-realtime/ws`, config via query string.
- Auth header: `Api-Subscription-Key: <key>` on the WS upgrade request (same header name/value the
  existing batch `SarvamSTT`/`SarvamTTS` clients already use).
- Query params this project sets: `language_code` (pinned, never `auto` — matches the batch STT
  client's existing "never unknown" policy), `model=saaras:v3-realtime`, `stream_type=fast`,
  `mode=codemix` (matches the batch client's existing default), `endpointing=vad`, `encoding=linear16`
  (we already decode Twilio's mu-law to PCM16 for `AudioFrame` — reusing that avoids a second
  encoding path), `sample_rate=8000`, plus VAD tuning params (`threshold`, `prefix_padding_ms`,
  `silence_duration_ms`, `min_speech_duration_ms`) left at Sarvam's documented defaults for this pass
  — untuned against real call audio, same honesty as `transitional_bridge.py`'s own
  `SILENCE_RMS_THRESHOLD` caveat.

## Message schema (client → server), all JSON text frames, audio always base64

```jsonc
{"event": "audio_input", "audio": "<base64 pcm16>"}
{"event": "flush"}                         // manual endpointing only — not used (we use vad)
{"event": "config.update", "...": "..."}   // mid-call reconfig — not used in this pass
{"event": "ping"}                          // keepalive
{"event": "end"}                           // graceful close
```

## Message schema (server → client)

```jsonc
{"event": "session.begin", "request_id": "...", "config": {...}}
{"event": "vad.speech_start", "utterance_idx": 0, "confidence": 0.91}
{"event": "transcript.partial", "utterance_idx": 0, "text": "...", "language": null}
{"event": "vad.speech_end", "utterance_idx": 0, "confidence": 0.88}
{"event": "transcript.final", "utterance_idx": 0, "text": "...", "language": null, "language_confidence": null, "start_s": null, "end_s": null}
{"event": "error", "code": "...", "is_fatal": false, "message": "...", "status_code": 400}
{"event": "session.end", "request_id": "...", "total_duration_s": 12.4, "total_utterances": 3, "audio_duration_s": 11.8}
```

`language`/`language_confidence` are only populated when `language_code=auto` — since this project
always pins a language, expect these `None` on every event; never manufactured, matching the batch
STT client's own `SttTranscript.language_probability` honesty policy. No transcription-confidence
field is ever emitted by this API — `STTCapabilities.supports_provider_confidence = False`.

## What this project does NOT implement from the full contract, and why

- **`endpointing=manual` / client-driven `speech_start`/`speech_end`/`flush`** — `vad` mode (server-side
  turn detection) is used instead; manual mode exists for callers who want to drive segmentation
  themselves (e.g. from an external VAD), which this project doesn't need.
- **`mode=translate`/`verbatim`/`translit`** — only `codemix` is used, matching the existing batch
  STT client's pinned default; the other modes are for different product needs (translation output,
  literal transliteration) not used anywhere in this codebase today.
- **Session-resume after reconnect** — not found anywhere in Sarvam's documented contract (confirmed
  absent, not merely unimplemented here). A dropped connection means starting a fresh session;
  `sarvam_streaming_stt.py`'s reconnect logic accepts losing whatever audio was in flight during the
  gap — a documented limitation, not a silent one. See `docs/TWILIO_MEDIA_STREAMS.md`.
- **Pronunciation dictionary / custom vocabulary** — not found in the Realtime API's documented
  config surface at all. `STTCapabilities.supports_pronunciation_dictionary = False`.

## Operational constraints (documented, with explicit gaps noted)

- WebSocket Streaming concurrency: 20 (Starter) / 100 (Pro/Business) — table doesn't clarify whether
  Realtime and Legacy share this pool.
- Burst-sensitive rate limiting — opening many connections in a fast burst can be rejected even under
  the concurrency ceiling; not a concern for this project's one-connection-per-call usage pattern.
- Max session duration: confirmed to exist (a documented trigger for `session.end`) but **no numeric
  value published** — not assumed or hardcoded anywhere in this implementation.
- Inactivity timeout: enforced (WS close code `1008`) but no specific idle-seconds threshold
  published. Mitigated two ways: (1) real call audio is forwarded continuously the entire time the
  Media Stream is connected, silence included — the connection is never actually idle during a live
  call; (2) an explicit `{"event": "ping"}` sent every 15s as a documented-available belt-and-suspenders
  measure.
- Close codes handled explicitly: `1003` (rate limit / bad key / quota), `1008` (inactivity),
  `1011` (internal error — retry), `4000` (bad param, or beta access denied).

## Pricing note (not a design input, recorded for completeness)

₹30/hour, billed per second of audio — no separate line item for Realtime vs. Legacy vs. REST/Batch;
appears to be one flat per-audio-second rate regardless of transport.

## Source

Full research trail (raw AsyncAPI spec fetches, `sarvamai` v0.1.30 source inspection, and every doc
page cited) is in this session's research; the summary above is what's load-bearing for the
implementation. Re-verify against `https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws`
if Sarvam's contract changes.
