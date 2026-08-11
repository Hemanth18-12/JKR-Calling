# Twilio Media Streams — Real-Time Transport (P2)

The persistent, bidirectional WebSocket transport that replaces Twilio's `<Record>` (batch,
one HTTP webhook per turn) as the live-call audio path, when
`TWILIO_VOICE_TRANSPORT=media_stream`. This is **P2 of the real-time voice engine migration** —
transport only. STT, TTS, and turn detection are still batch/heuristic in this phase (see
§9 Known Limitations); P3+ replaces those.

## 1. Architecture

```text
Twilio phone call
  → POST /webhooks/twilio/voice/{token}          (handle_voice_webhook, unchanged for <Record>)
  → if TWILIO_VOICE_TRANSPORT=media_stream:
      <Connect><Stream url="wss://.../api/v1/live-call/ws/twilio/media/{signed_token}"/></Connect>
  → Twilio opens a persistent WebSocket to that URL
  → services/api/app/modules/live_call/transport/twilio_media_stream.py:twilio_media_stream_websocket
      accept() → verify signed token → look up CallSession + Redis state → create RealtimeMediaSession
      → 4 concurrent asyncio tasks: receive loop, processing loop, send loop, watchdog
  → `start` event arrives → greeting synthesized + sent → customer audio buffered/transcribed/
    replied to in a loop (transitional_bridge.py, reusing the exact same SarvamSTT/
    jkr_conversation.engine.process_turn/SarvamTTS calls <Record> mode uses)
  → call ends: WebSocket closed server-side (no further TwiML after <Connect> → Twilio hangs up)
```

**Module layout** (`services/api/app/modules/live_call/transport/`):

| File | Responsibility |
|---|---|
| `base.py` | `VoiceTransport` Protocol, `AudioFrame`/`OutboundAudioChunk`, `MediaSessionStatus`/`PlaybackState` enums + the state transition table |
| `media_tokens.py` | Signed, expiring media-session tokens (HMAC-SHA256) |
| `schemas.py` | Pydantic models for Twilio's exact verified wire-format JSON, both directions |
| `audio_codec.py` | mu-law 8kHz ↔ PCM16 ↔ WAV conversion (stdlib `audioop`) |
| `events.py` | Lifecycle event name constants, structured logging, process-local metrics |
| `session.py` | `RealtimeMediaSession` (state machine + queues + marks) and `MediaSessionRegistry` |
| `transitional_bridge.py` | **TRANSITIONAL** — buffers audio, detects turns via trailing silence, drives the existing batch STT/engine/TTS pipeline |
| `twilio_media_stream.py` | The WebSocket endpoint itself, TwiML builder, task orchestration |

`services/api/app/modules/live_call/service.py` (the existing `<Record>` module) is **unmodified**
except one small, additive branch in `handle_voice_webhook`: if
`settings.twilio_voice_transport == "media_stream"`, it mints a signed token and returns
`<Connect><Stream>` TwiML instead of running its normal `<Record>` logic. Every existing
`<Record>`-mode function, test, and behavior is untouched.

## 2. Why `services/api`, not `services/voice-worker`

The spec suggested preferring `services/voice-worker` for long-lived realtime sessions if the API
is deployed somewhere unsuitable for persistent WebSockets (serverless). `services/api` already
runs as a standard long-lived `uvicorn` process (confirmed: `docker-compose.yml`'s `api` service,
no serverless config anywhere in this repo), and **all** existing real-call Twilio/Sarvam
integration already lives in `services/api/app/modules/live_call/` and
`services/api/app/live_providers/`. Moving Media Streams to `voice-worker` would mean either
duplicating that integration or adding a new cross-service auth/handoff layer for no benefit —
`voice-worker` remains the mock/Test Lab-only service it already was. Documented here explicitly
per spec §72's "explain why" requirement for deviating from the suggested default.

## 3. Session authentication (spec §12/§13/§46/§47)

The WebSocket URL never carries a raw `call_session_id`/`workspace_id` the client could forge.
`handle_voice_webhook` mints a signed token (`media_tokens.create_media_session_token`) binding:

- `call_session_id`, `workspace_id` — resolved server-side from a real, already-created `CallSession`
- `twilio_call_sid` — from Twilio's own webhook POST (`form["CallSid"]`)
- `redis_state_token` — the same opaque per-call Redis key `<Record>` mode's other three webhooks
  already use, so the WS handler can read `business_identity`/`policy`/`recent_turns`/`tts_speaker`
  without a second state mechanism
- `exp` — a generous 1-hour expiry (checked once at connect time only, never per-frame, so a long
  real call is never invalidated mid-call by this same check)

HMAC-SHA256, `hmac.compare_digest`, no new dependency — mirrors `app/security.py`'s existing CSRF
token pattern. On connect: `websocket.accept()` first (required before any FastAPI WebSocket can
send a close frame with a reason), then immediate verification; an invalid/expired/tampered token,
a call that doesn't exist, or a call already in a terminal status all close the socket immediately
(codes 4401/4404/4409 — the 4000-4999 range RFC 6455 reserves for application use) before any audio
is ever accepted.

## 4. Event model — the exact verified Twilio contract

Confirmed against Twilio's current official docs (not inferred/guessed — see `schemas.py`'s own
module docstring for the verification). Every inbound message carries `sequenceNumber` and
`streamSid` at the **top level**, not nested. Codec is fixed: `audio/x-mulaw`, 8000 Hz, mono —
not configurable for classic (non-ConversationRelay) Media Streams.

Inbound (Twilio → us): `connected`, `start` (→ `RealtimeMediaSession.handle_twilio_start`),
`media` (→ decoded, enqueued as an `AudioFrame`), `mark` (→ playback acknowledgement), `stop`,
`dtmf` (captured in the schema, not acted on in P2).

Outbound (us → Twilio): `media` (`{"event":"media","streamSid":...,"media":{"payload":...}}` —
no track/chunk/timestamp on the way out, those are inbound-only fields), `mark`, `clear`.

## 5. Task architecture (spec §16/§17)

Four concurrent `asyncio.Task`s per session, all registered on the `RealtimeMediaSession` so
`close()` cancels every one of them from a single authoritative place:

1. **Receive loop** — reads Twilio's JSON frames, decodes audio, enqueues. Never does STT/LLM/TTS
   work inline — this is what keeps media reception responsive regardless of how slow downstream
   processing is.
2. **Processing loop** — the only loop allowed to touch STT/engine/TTS. Sends the greeting once
   streaming starts, then runs the transitional turn-buffer loop (§7).
3. **Send loop** — the single serialized sender; nothing else calls `websocket.send_json()`
   directly, so outbound messages can never interleave.
4. **Watchdog** — flags (and fails) a session that connected but then received no media at all for
   too long (default 30s), distinct from normal between-turn silence.

## 6. Audio pipeline

```text
Twilio media.payload (base64 mu-law)
  → audio_codec.decode_twilio_media_payload() → PCM16 mono @ 8kHz
  → AudioFrame → RealtimeMediaSession.inbound_audio_queue (bounded, non-blocking put)
  → TurnBuffer.add_frame() (transitional_bridge.py)
  → [turn complete] → audio_codec.pcm16_to_wav_bytes() → SarvamSTT.transcribe() [unchanged]
```

```text
process_turn() reply text [unchanged]
  → SarvamTTS.synthesize() [unchanged] → WAV bytes
  → audio_codec.wav_bytes_to_pcm16() → OutboundAudioChunk → outbound_queue
  → audio_codec.encode_twilio_media_payload() (resamples to 8kHz if needed) → outbound `media` message
```

**Backpressure** (spec §18/§19): inbound queue is bounded (~250 frames, ~5s of audio) and uses
`put_nowait()` — a full queue means downstream processing has stalled, and the response is a
counted, logged drop (`inbound_media_backpressure` event, `dropped_inbound_frames` metric), never
blocking the receive loop. Outbound queue backpressure is a plain blocking `put()` — the producer
is our own code, not an external network loop, so slowing generation to match what the send loop
can push is safe and desired.

## 7. Turn detection — batch path (STT_MODE=batch), superseded by default (P3)

`transitional_bridge.TurnBuffer` buffers PCM16 audio and uses simple trailing-silence RMS energy
detection (`audioop.rms`) to decide when a turn has ended — deliberately **not** real VAD.
`TRAILING_SILENCE_SECONDS = 4.0` mirrors `service.py`'s `RECORD_SILENCE_TIMEOUT_SECONDS` for
consistency. `SILENCE_RMS_THRESHOLD = 300` (PCM16 amplitude scale, max 32767) is a first-pass
heuristic that has **not been tuned against real phone-line audio**.

**As of P3, this is no longer the default** — `STT_MODE=streaming` (now the recommended setting
under `TWILIO_VOICE_TRANSPORT=media_stream`) replaces this turn-buffer entirely with Sarvam's real
streaming STT and server-side VAD; see §15. This module was **not deleted** — it remains the
permanent implementation for `STT_MODE=batch` and the explicit
`STT_STREAM_FAILURE_POLICY=batch_next_turn` fallback if the streaming connection can't be
established or drops and exhausts its reconnect attempts.

## 8. Closing / grace, marks, and clearing playback

The closing-grace mechanism from `<Record>` mode (never hang up while the customer might be
speaking) is reimplemented for streaming in `twilio_media_stream._processing_loop`: after a
force-close turn's reply is sent, the loop keeps listening for `GRACE_SECONDS = 4.0`; genuine new
speech resumes the conversation (`_reopen_conversation_state`, reused unchanged from `service.py`);
persistent silence — with a safety margin that extends the deadline if media arrived very
recently, so a customer who starts talking right at the deadline is never cut off — finalizes the
call for real via `_finalize_call` (also reused unchanged).

**Marks** (spec §26): every outbound audio chunk is followed by a `mark` message; Twilio echoes it
back once actually played, tracked separately as `marks_sent` vs `marks_acknowledged` — "enqueued"
is never assumed to mean "the customer heard it."

**Clear** (spec §27): `clear_agent_audio()` exists and is directly testable today (sends Twilio's
`clear` message, drains the outbound queue) but is **not yet wired to any automatic trigger** —
there is no interruption/VAD detection in P2 to call it from. That's P8.

## 9. Known limitations (honest, not silently absent)

- **TTS remains batch** even under `STT_MODE=streaming` — `SarvamTTS.synthesize()` is called
  exactly as before, once a full reply is generated. P6 replaces this with streaming synthesis.
  Under `STT_MODE=batch`, STT is batch too (§7).
- **No real VAD / turn detection under STT_MODE=batch** — trailing-silence heuristic only (§7).
  `STT_MODE=streaming` (§15) uses Sarvam's own server-side VAD instead, but true human-like
  turn-taking tuning (interruption tolerance, backchannel detection) is still P4's job.
- **No barge-in** — the customer cannot interrupt agent playback; `clear_agent_audio()` is a
  tested, working primitive with nothing calling it yet. P8.
- **No sequence-ID replay protection enforcement** — `response_sequence_id`/`chunk_index` are
  generated and carried on every `OutboundAudioChunk` (the foundation P9 builds on), but nothing
  yet rejects a stale/duplicate chunk from playing. P9.
- **TTS failure has no fallback mid-stream.** `<Record>` mode falls back to Twilio's own `<Say>`
  on a Sarvam TTS error; once a Media Stream is active there is no further TwiML round-trip to
  fall back into. `synthesize_for_stream()` returning `None` currently means the call ends
  gracefully rather than leaving the customer in silence — a real gap, not silently glossed over.
- **Single-process, in-memory session registry** — a real, documented limitation (spec §70/§71),
  not an oversight. Fine for one process; would need a session-affinity story before horizontal
  scaling.
- **RLS' `SET LOCAL app.current_workspace_id`** is scoped per-transaction, so every discrete unit
  of work (send greeting, process one turn, finalize) opens its own fresh
  `workspace_scoped_session(...)`, matching the `<Record>`-mode pattern exactly — no long-lived DB
  session is held open for the call's full duration.

## 10. Feature flags

| Setting | Default | Values |
|---|---|---|
| `TWILIO_VOICE_TRANSPORT` | `record` | `record` \| `media_stream` — per-environment opt-in, never silently switched |
| `TWILIO_MEDIA_STREAM_FAILURE_POLICY` | `fail` | `fail` \| `fallback_record` (not yet implemented — see §11) |
| `VOICE_MEDIA_DEBUG` | `false` | verbose per-frame logging (metadata only, **never raw audio** — spec §41/§42) |
| `STT_MODE` (P3) | `batch` | `batch` \| `streaming` — only takes effect when `TWILIO_VOICE_TRANSPORT=media_stream`; silently stays `batch` otherwise (see `Settings.effective_stt_mode`) |
| `STT_STREAM_FAILURE_POLICY` (P3) | `fail` | `fail` \| `batch_next_turn` — what happens once the streaming STT connection exhausts its bounded reconnect attempts |

`Settings.effective_media_stream_ws_base_url` derives `wss://`/`ws://` from
`PUBLIC_WEBHOOK_BASE_URL`/`API_BASE_URL` automatically.

## 11. Deployment requirements (spec §71/§74)

- The reverse proxy in front of `services/api` (ngrok locally; nginx/Caddy/load balancer in
  production) must support WebSocket upgrade on the `/api/v1/live-call/ws/twilio/media/{token}`
  path — ngrok's free tier does this by default (already relied on for the rest of this session's
  live-call testing).
- `wss://` (TLS) is required for any real Twilio call — Twilio does not connect Media Streams over
  plain `ws://` to a public endpoint.
- No new health-check endpoint was added in this pass; `GET /health` already exists and does not
  call Twilio — session-level health (§74's "Twilio transport / media gateway / active
  WebSockets") is answerable today via `RealtimeMediaSession.to_debug_dict()` per-session, not yet
  aggregated into a single endpoint.
- `TWILIO_MEDIA_STREAM_FAILURE_POLICY=fallback_record` is defined as a setting but **not yet
  implemented** — today, a failed Media Stream connect always fails the call
  (`WS_CLOSE_*` codes), regardless of this setting's value. Implementing the actual fallback
  (placing a fresh `<Record>`-mode call after a Media Stream setup failure) is a follow-up, not
  silently claimed as done.

## 12. Debugging

- `VOICE_MEDIA_DEBUG=true` enables per-frame `media_frame_received`/`media_frame_sent` log events
  (metadata only — chunk index, timestamp, sequence — never the base64 payload itself).
- `RealtimeMediaSession.to_debug_dict()` answers spec §75's required questions for one call:
  WebSocket connect state, stream SID, codec/sample rate, inbound/outbound frame and byte counts,
  dropped-frame count, queue depths, marks sent/acknowledged, time since last media.
- `tests/tools/twilio_media_simulator.py` — sends the same connected/start/media/mark/stop event
  sequence a real Twilio call would, for local debugging without a paid phone call:
  ```
  uv run --package jkr-api python tests/tools/twilio_media_simulator.py <ws_url>
  ```
  Its event-builder functions are also imported directly (via file-path loading, not the dotted
  package path — see the integration test's own comment on why) by the automated test suite, so
  the exact same fixtures back both manual and automated testing.

## 13. Testing

- `test_media_tokens.py` — signed token creation/verification (valid, tampered, expired, malformed).
- `test_audio_codec.py` — mu-law/PCM16/WAV round-trips, resampling.
- `test_twilio_schemas.py` — every event type parses against the exact verified field names;
  outbound message shapes match Twilio's contract; unrecognized events degrade gracefully.
- `test_media_session.py` — the full state machine (valid/invalid transitions, idempotent
  `close()` from every trigger path), inbound backpressure, outbound sequencing, marks, watchdog,
  session isolation between two concurrent sessions.
- `test_transitional_bridge.py` — `TurnBuffer`'s silence/speech detection, including the critical
  "pure silence never completes a turn even past max duration" case (never call STT on nothing).
- `test_twilio_media_stream_integration.py` — a real WebSocket connection (FastAPI `TestClient`)
  against a real Postgres `CallSession` and real Redis state, driving the actual unmodified
  `jkr_conversation.engine.process_turn()` (only Sarvam's network calls are mocked): greeting sent,
  simulated speech transcribed and replied to, real `CallTurn` rows persisted — proof the whole
  pipeline wires together, not just its individual pieces. Plus invalid-token and call-not-found
  rejection tests.

All existing `<Record>`-mode tests pass unmodified. P3 adds `test_sarvam_streaming_stt.py`,
`test_streaming_bridge.py`, and `test_streaming_stt_integration.py` — see §15 for what they cover.
118 total in `services/api/tests` as of P3 (up from 88 after P2 — 30 new, zero regressions); 290
across every touched package repo-wide (packages/conversation 106, services/api 118,
packages/db 32, voice-worker 10, campaign-worker 13, intelligence-worker 11).

## 14. Migrating back to `<Record>`

Set `TWILIO_VOICE_TRANSPORT=record` (or leave it at its default) — `handle_voice_webhook`'s
existing, untouched `<Record>` branch handles everything exactly as it did before this phase. No
code path needs to change; the two transports are fully independent behind one flag. Setting
`STT_MODE=batch` (the default) has the same effect for STT specifically, while staying on
`media_stream` transport.

## 15. P3 — streaming STT (`STT_MODE=streaming`)

Full verified provider contract: `docs/SARVAM_STREAMING_STT_CONTRACT.md`. Full audit of what this
replaces and the real-call latency evidence that motivated it:
`docs/REALTIME_VOICE_MIGRATION_AUDIT.md` §12. Results/verification: `docs/P3_STREAMING_STT_RESULTS.md`.

**What changed**: `transport/streaming_bridge.py` (new) owns a persistent Sarvam Realtime STT
WebSocket connection (`app/live_providers/sarvam_streaming_stt.py`, against the
transport-independent `app/live_providers/streaming_stt.py` protocol) for the life of one call,
created right after the greeting is sent — not on first speech. Every inbound Twilio audio frame is
forwarded continuously, silence included (Sarvam's own server-side VAD needs a continuous stream to
detect speech boundaries itself); there is no client-side turn buffering at all in this mode. A
`transcript.final` event **is** the turn boundary — it goes straight to
`transitional_bridge.process_known_transcript_turn()`, the exact same persist → `ConversationEngine`
→ tool-execution → reply pipeline the batch path uses (extracted out of
`process_transitional_turn()` specifically so this logic is never duplicated between the two STT
modes). Empty finals are dropped and logged (`stt_stream_empty_transcript_dropped`); duplicate
finals (same `utterance_idx` + normalized text) are dropped and logged
(`stt_stream_duplicate_final_dropped`) rather than re-run through the engine.

**Reconnect**: Sarvam's protocol has no session-resume (verified — see the contract doc). A dropped
connection starts a brand-new `SarvamStreamingSTT` instance and a brand-new pair of
(audio-forward, event-consume) tasks; the previous generation's tasks are always fully torn down
first, so generations never run concurrently — this is *how* stale-generation events are
structurally impossible, not a runtime tag check. Up to 3 reconnect attempts with backoff
(0.5s/1.5s/3.0s) before `STT_STREAM_FAILURE_POLICY` decides what happens next. Whatever audio was
in flight during the reconnect gap is lost — a documented limitation, not a silent one; there is no
recovery buffer in this pass.

**Grace/closing**: reimplemented in `streaming_bridge.py` against STT events rather than shared
with `_run_batch_turn_loop`'s TurnBuffer-polling version — deliberately isolated, matching P2's own
precedent of not forcing a shared abstraction across the two transport-mode loops just to avoid a
small amount of duplication. Real-call bug fix carried in this same pass (transport-independent,
also fixes `<Record>` mode): a customer speaking again during the grace window used to get the
identical full closing script repeated verbatim when the objective re-completed with nothing new —
`jkr_conversation/closing.py`'s new `REOPENED_REAFFIRM` reason now gives a short, distinct
reaffirmation instead (see `docs/REALTIME_VOICE_MIGRATION_AUDIT.md` §12.2).

**Metrics**: `stt_stream_finalize` (speech-end → final transcript — the key P3 latency metric,
recorded via the existing `CallLatencyMetric` table, `provider="sarvam"`) and
`stt_stream_first_partial` (turn start → first partial transcript), directly comparable against the
batch path's `stt_transcribe` stage in the same table.

**Known limitations specific to P3** (in addition to §9's carried-forward ones):
- **Sarvam Realtime API access is unverified for this account** — Sarvam's own docs give an
  ambiguous beta signal (one page calls it beta, the beta-access index page doesn't list it). The
  code handles a refused connection via the normal reconnect → failure-policy path, but this has
  only been verified against a faked WebSocket boundary in tests, not a real Sarvam connection —
  see `docs/P3_STREAMING_STT_RESULTS.md` for exactly what was and wasn't verified against a real call.
- **No recovery/replay buffer across a reconnect** (see Reconnect above).
- **VAD tuning params left at Sarvam's documented defaults** — untuned against real call audio,
  same honesty as §7's batch-mode `SILENCE_RMS_THRESHOLD`.
- **`mode="codemix"` is used unconditionally**, matching the batch STT client's existing pinned
  default, rather than varying by the customer's selected strict-vs-code-mixed language profile —
  a reasonable-but-unexamined carryover, not a new design decision made in this pass.
