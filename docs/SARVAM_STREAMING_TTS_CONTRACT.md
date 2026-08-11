# Sarvam Streaming TTS — Verified WebSocket Contract

Verified two ways before writing any provider code: (1) fetched Sarvam's own current docs
(`docs.sarvam.ai/api-reference/text-to-speech/stream.md`), and (2) ran live probe scripts against
`wss://api.sarvam.ai/text-to-speech/ws` with the real configured `SARVAM_API_KEY`, because the docs
themselves hedge ("currently supports MP3 only, optimized for real-time playback") in a way that
turned out to be **stale/inaccurate** — confirmed empirically below. Same discipline as
`docs/SARVAM_STREAMING_STT_CONTRACT.md` and P5's OpenAI SSE verification: never guessed, never trusted
docs alone when a live probe was possible.

## Connection

`wss://api.sarvam.ai/text-to-speech/ws?model=<model>&send_completion_event=true`

Header auth: `Api-Subscription-Key: <SARVAM_API_KEY or SARVAM_TTS_API_KEY>`.

`model`: `bulbul:v2` (default) or `bulbul:v3`. No `bulbul:v3-beta` needed — `bulbul:v3` is GA and used
throughout this implementation (matches `SarvamTTS`'s existing batch-REST default).

## Client → server messages

**Config (required first message):**
```json
{"type": "config", "data": {
  "language_code": "en-IN",
  "speaker": "priya",
  "pace": 1.0,
  "output_audio_codec": "mulaw",
  "speech_sample_rate": "8000"
}}
```
`language_code` and `target_language_code` were BOTH empirically accepted for a valid value and BOTH
produced the identical generic validation error for an invalid one (`zz-ZZ` → `"Input parameters has
to be a valid dictionary"` either way) — inconclusive on which is "real," but harmless either way since
both work. `language_code` is used here since it's what the docs' own JSON example uses.

**Text:**
```json
{"type": "text", "data": {"text": "..."}}
```
Multiple `text` messages can be sent back-to-back on one connection before any `flush` — confirmed live
(three separate ~50-70 char sends, no flush between them, all accepted immediately).

**Flush:**
```json
{"type": "flush"}
```
Forces processing of whatever's left in Sarvam's own internal buffer below its auto-emit threshold.
**Confirmed live: audio is emitted automatically once the buffer crosses ~50 chars (`min_buffer_size`),
with no flush needed at all** — 154 characters of text with zero flush produced a real audio message at
209ms. `flush` is only needed to force out a final trailing fragment shorter than that threshold — the
exact same role `SpeakableChunker.flush()` already plays in `packages/conversation`. This means: feed
every `SpeakableChunk` as its own `text` message the instant it's produced, and send exactly one
`flush` when the response is fully done — never flush per-chunk (matches spec's own explicit guidance).

**Ping:** `{"type": "ping"}` — confirmed live: no response is sent back (fire-and-forget keepalive, not
request/response). Docs say the connection auto-closes after 60s of inactivity.

## Server → client messages

**Audio:**
```json
{"type": "audio", "data": {"content_type": "audio/mulaw", "audio": "<base64>", "request_id": "..."}}
```

**Event (completion):**
```json
{"type": "event", "data": {"event_type": "final", "message": "...", "timestamp": "..."}}
```

**Error:**
```json
{"type": "error", "data": {"message": "...", "code": 400, "request_id": "..."}}
```
Confirmed live for an invalid speaker: `400: Speaker 'x' is not recognized. Available speakers are:
anushka, abhilash, manisha, vidya, arya, karun, hitesh, aditya, ritu, priya, neha, rahul, pooja, rohan,
simran, kavya, amit, dev, ishita, shreya, ratan, varun, manan, sumit, roopa, kabir, aayan, shubh,
ashutosh, advait, anand, tanya, tarun, sunny, mani, gokul, vijay, shruti, suhani, mohit, kavitha, rehan,
soham, rupali, ...` — this is the real, current `bulbul:v3` speaker list (a superset of `bulbul:v2`'s
four female / three male names `SarvamTTS`'s batch client already defaults to `priya` for).

## CRITICAL empirical finding: `request_id` is per-CONNECTION, not per-response

Sent two independent text→flush cycles on the SAME websocket connection and both cycles' audio/event
messages carried the **identical** `request_id`. This means the provider gives no built-in way to tell
"this audio belongs to response A vs response B" once a connection is reused across multiple agent
turns (which is exactly what P6 requires — one persistent connection per call). **Our own
`response_id`/`generation_id`/`sequence_id` bookkeeping (already planned per spec §49) is not optional
polish — it is the only correlation mechanism available at all.** The `event_type=final` message is the
only reliable per-response completion boundary Sarvam gives us; our own code must track "I am currently
waiting for the final event that closes out response N" as explicit local state.

## CRITICAL empirical finding: direct μ-law 8kHz output works today, despite the docs' hedge

The docs literally say `output_audio_codec` "currently supports MP3 only, optimized for real-time
playback" — **this is stale.** Live probe results, `bulbul:v3`, `send_completion_event=true`:

| `output_audio_codec` | `speech_sample_rate` | Result |
|---|---|---|
| `mp3` (default) | 24000 | Real MPEG frames (LAME-encoded) — confirmed via frame sync bytes and `LAME3.100` tag in the stream. Would need an in-process MP3 decoder to use — explicitly avoided (spec §32/§90's "no ffmpeg per chunk" + no new heavy dependency). |
| `linear16` | 8000 | Raw PCM16 mono @ 8kHz, `content_type: audio/pcm`, no header, no container — directly usable, only needs μ-law encoding (already in `audio_codec.py`). |
| `mulaw` | 8000 | **Raw μ-law bytes @ 8kHz, `content_type: audio/mulaw`, no header at all.** This is Twilio's exact wire format — zero conversion needed beyond base64 decode. |
| `wav` | 8000 | Real `RIFF...WAVE` container confirmed (`b'RIFF\x1ab\x00\x00WAVEfmt '`) — would need header stripping if ever used; not used here since raw `mulaw` is directly available. |

**Decision: `output_audio_codec="mulaw"`, `speech_sample_rate="8000"`.** This is the direct fast path
spec §37 asks to verify rather than assume — verified, and it's real. Zero resampling, zero encoding,
zero container parsing needed for the common case; `encode_twilio_media_payload()`'s resample branch
only exists as a defensive fallback for a provider/model combination that doesn't support this (kept,
not deleted, exactly for that reason).

## Chunk sizing observed

`bulbul:v3` streams audio back in ~1100-2200 decoded-byte pieces (roughly 140-275ms of μ-law-8k audio
per message) — Sarvam is already doing its own reasonable packetization; sub-slicing these further
before forwarding to Twilio was considered (spec §40) and not implemented this pass — each Sarvam audio
message is forwarded as its own Twilio `media` message directly. Twilio's Media Streams API accepts
payloads larger than the traditional 20ms recommendation (this codebase's existing P2 code already
proves that: `_send_pcm_reply` has always sent one whole-reply chunk as a single `media` message across
every prior phase) — so this is a reasonable default, not a compliance gap, though finer slicing remains
a documented future optimization if real-call listening reveals choppiness at this granularity.

## Generation speed

A 168-character three-sentence response (~12.7s of resulting speech, 73 audio messages) fully completed
(`final` event) in 4.5 real seconds — Sarvam generates meaningfully faster than real-time (~2.8x), which
is what makes "LLM keeps generating while TTS synthesizes earlier chunks" a real win rather than a
theoretical one: TTS is not the bottleneck once the connection is warm and the first chunk is in flight.

## What this implementation does NOT use

- `pitch`/`loudness` — `bulbul:v3` doesn't support them per the docs (v2-only fields); not sent.
- `dict_id` (pronunciation dictionary) — real capability, not wired into `StreamingTTSConfig` this pass
  (spec §65 explicitly permits not blocking P6 on this); flagged as a follow-up, not silently dropped.
- `enable_preprocessing` — always-on for `bulbul:v3` per the docs; not sent (nothing to configure).
- MP3/WAV output — available but unused; the direct `mulaw` fast path made them unnecessary.
