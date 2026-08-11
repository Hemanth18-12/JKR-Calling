# P3 — Streaming STT: Results & Verification Status

## Sarvam API selected

**Realtime API** (`saaras:v3-realtime`, `wss://api.sarvam.ai/speech-to-text-realtime/ws`) over the
Legacy Streaming API (`saaras:v3`/`v4`) — the only one of the two with true partial transcripts,
mid-call reconfiguration, and native 8kHz mu-law/PCM16 support (no resampling needed from Twilio's
native telephony audio). Full verified contract: `docs/SARVAM_STREAMING_STT_CONTRACT.md`.

**Access status is unverified.** Sarvam's own documentation gives an ambiguous signal — one guide
page calls the Realtime API "(beta)" and states its documented `4000` WebSocket close code can mean
"beta access denied"; a separate beta-access index page does not list this endpoint at all. This
project's Sarvam API key has never been used to open a real connection to this endpoint. **This is
the single most important open item in P3** — see "What still needs a real call" below.

## Architecture (what shipped)

- `app/live_providers/streaming_stt.py` — transport-independent `StreamingSTTProvider` protocol,
  typed event model (`STTSessionStarted/Ended`, `SpeechStarted/Ended`, `PartialTranscript`,
  `FinalTranscript`, `STTReconfigured`, `STTError`), `StreamingSTTConfig`, `STTCapabilities`.
- `app/live_providers/sarvam_streaming_stt.py` — the real adapter: hand-rolled against the raw
  `websockets` library (matching this codebase's existing no-SDK pattern for Sarvam), connects,
  streams audio continuously, parses every documented server event.
- `app/modules/live_call/transport/streaming_bridge.py` — owns the persistent connection for one
  call's lifetime: continuous audio forwarding, event handling, dedup, grace/closing state machine,
  bounded reconnect (3 attempts, 0.5s/1.5s/3.0s backoff).
- `transitional_bridge.process_known_transcript_turn()` — extracted from the batch path so the
  entire `persist → ConversationEngine → tools → reply` pipeline is shared, never duplicated,
  between `STT_MODE=batch` and `STT_MODE=streaming`.
- Feature flags: `STT_MODE=batch|streaming` (only takes effect under
  `TWILIO_VOICE_TRANSPORT=media_stream`), `STT_STREAM_FAILURE_POLICY=fail|batch_next_turn`.

## What was verified, and how

**Not verified**: any real connection to Sarvam's Realtime STT WebSocket. No real phone call has
been placed with `STT_MODE=streaming` set. This section is explicit about that rather than
implying otherwise.

**Verified, with real infrastructure and a faked STT network boundary only** (same rigor/pattern as
P2's own integration test):
- `test_sarvam_streaming_stt.py` (17 tests) — URL/query-param construction against the verified
  contract, every documented event type parses correctly into the typed model, malformed messages
  are skipped without crashing, `provider_confidence` is never fabricated, base64 audio encoding is
  correct, close-is-idempotent, connect/send/close against a fake WebSocket object.
- `test_streaming_bridge.py` (11 tests) — dedup logic (same utterance_idx+text → dropped; different
  utterance_idx with identical text → NOT dropped, since a customer can genuinely say "yes" twice),
  grace-period expiry/extension/finalization, and — critically — the **reconnect and failure-policy
  behavior with zero mocking of anything except the Sarvam connection itself**: `connect()` always
  raising `ConnectionRefusedError` correctly exhausts 3 reconnect attempts and then either closes
  the session as failed (`stt_stream_failure_policy=fail`) or leaves it open for batch fallback
  (`batch_next_turn`) — this is the exact scenario a real beta-access denial would produce.
- `test_streaming_stt_integration.py` (2 tests) — full real WebSocket (FastAPI `TestClient`), real
  Postgres `CallSession`, real Redis state, real unmodified `jkr_conversation.engine.process_turn()`:
  1. A fake streaming STT provider emits one `FinalTranscript` only after real audio frames have
     actually flowed through the real receive-loop → `RealtimeMediaSession` → `send_audio()` path
     (not a canned timer) — and the test asserts **exactly one** `CallTurn` row was created for it,
     directly proving no duplicate-engine-call bug.
  2. A fake provider whose `connect()` always fails, with `STT_STREAM_FAILURE_POLICY=batch_next_turn`
     — proves the call survives on the batch path and still produces a reply, rather than the
     customer being dropped.
- Full regression check: 290 tests pass across every touched package (packages/conversation 106,
  services/api 118, packages/db 32, voice-worker 10, campaign-worker 13, intelligence-worker 11) —
  zero regressions in the batch `<Record>` path or the P2 batch Media Stream path.

## Latency — no before/after comparison exists yet

The P2 baseline is real (from an actual call, see `docs/REALTIME_VOICE_MIGRATION_AUDIT.md` §12.2):
`stt_transcribe` (batch REST call) averaged 439ms, max 590ms — a small share of the ~3.1-4.8s total
per-turn time, most of which is the `ConversationEngine`'s sequential LLM chain (extraction ~1993ms,
RAG ~1679ms when it runs, generation ~726ms), not STT.

**No streaming-mode number exists to compare against it** — that requires an actual Sarvam
connection succeeding on a real call, which hasn't happened. The `stt_stream_finalize` and
`stt_stream_first_partial` metrics are wired into `CallLatencyMetric` (`provider="sarvam"`) and will
populate automatically the first time a real streaming call completes a turn — no additional
instrumentation work is needed once access is confirmed.

**Expectation, not a measurement**: streaming should reduce the STT-attributable latency by
removing the "upload full utterance, wait for one REST round-trip" step in favor of overlapping
transcription with the tail of speech — realistically saving somewhere in the low-hundreds-of-ms
range per turn, given the batch call itself was already only ~440-590ms. Given the engine's own LLM
chain is 5-10x larger than the STT step, **streaming STT alone will not resolve the "so much lag"
complaint that motivated P3** — that requires a separate pass at the engine's sequential
extraction/RAG/generation calls (parallelizing them, or streaming the LLM response), explicitly not
started in this pass.

## Quality — not measured against real audio

No real Telugu/Hindi/English or code-mixed audio has gone through the streaming path. Domain
correction, RAG, and the closing system are unchanged and reused exactly as the batch path uses
them (proven via the integration test's exactly-once-through-the-real-engine assertion), so there is
no NEW correctness risk in that part of the pipeline — but STT-specific quality questions (does
streaming transcribe "root canal" as accurately as batch did; does `mode=codemix` behave the same
way in the Realtime API as in the batch REST API; does the server-side VAD correctly detect Telugu
speech-end timing) are genuinely unanswered without a real call.

## Self-transcription (never hearing the agent's own voice) — verified by construction, not by test

Twilio's Media Streams `<Connect><Stream>` only ever sends **inbound** track `media` events to the
server (confirmed in P2's wire-protocol research); the server's own outbound TTS audio is written
directly to the WebSocket as outbound `media` messages and never re-enters
`RealtimeMediaSession.inbound_audio_queue`. Since `streaming_bridge._forward_audio_to_stt()` only
ever reads from that same inbound queue, the streaming STT connection structurally cannot receive
the agent's own voice — there is no code path for it to happen, independent of any test. This
matches the P3 spec's mandatory self-transcription requirement, verified by architecture rather than
by a dedicated audio test (a dedicated test would need to fabricate a scenario this codebase has no
way to produce even by mistake).

## What still needs a real call (explicit manual verification plan)

None of the following has been done. In order:

1. Confirm Sarvam Realtime API access: set `TWILIO_VOICE_TRANSPORT=media_stream`,
   `STT_MODE=streaming`, `STT_STREAM_FAILURE_POLICY=fail` (so a beta-access denial fails loudly
   instead of silently falling back), place one real call. Watch `services/api` logs for
   `stt_stream_connected` (success) vs. `stt_stream_connect_failed`/`stt_stream_failed` (denied or
   network issue).
2. If access is denied: email `developer@sarvam.ai` (or their Discord) requesting Realtime API
   whitelisting, referencing the `saaras:v3-realtime` model and the `4000`/beta-denial close code.
   Re-test once granted.
3. If access succeeds: confirm the customer's speech is transcribed correctly for at least one
   Telugu-English code-mixed utterance and one pure-English utterance — compare against what batch
   mode (`STT_MODE=batch`) would have produced for the same words, same as this session's own
   before/after diagnostic pattern.
4. Query `call_latency_metrics` for the real call's `stt_stream_finalize` and
   `stt_stream_first_partial` values; compare against the P2 batch baseline numbers above.
5. Deliberately let a call go quiet mid-sentence (a real pause) and confirm the agent doesn't
   respond prematurely — server-side VAD (`silence_duration_ms=500` default) behavior on real audio
   is unverified.
6. Deliberately test a dropped network moment if possible (e.g. brief wifi interruption) to observe
   real reconnect behavior and log `stt_stream_reconnecting`/`stt_stream_connected` again.
7. Confirm `STT_STREAM_FAILURE_POLICY=batch_next_turn` in a real environment: if access is denied at
   step 1, switch this flag and re-run the same call — the customer should still get a working
   (batch-speed) conversation instead of a dropped/failed call.
8. Report back the results the same way as every previous phase in this project, so any real
   correctness or latency surprises can be diagnosed against real `call_events`/
   `call_latency_metrics` data, not guessed at.

## Explicitly NOT done in P3 (per spec, restated for the final report)

- TTS is still batch (`SarvamTTS.synthesize()` after a full reply is generated) — P6.
- LLM generation inside `ConversationEngine` is still non-streaming — no partial-response speaking.
- P4 (true human-like turn detection/VAD tuning), P8 (barge-in), P9 (full replay protection) are
  all still not implemented — P3 only replaced the STT leg of the pipeline.
- No recovery/replay buffer across a streaming STT reconnect (documented limitation, not silent).
- `mode="codemix"` used unconditionally rather than varying by language profile.
