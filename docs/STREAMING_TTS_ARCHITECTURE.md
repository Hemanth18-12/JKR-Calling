# P6 — Streaming TTS Architecture

See `docs/P6_STREAMING_TTS_AUDIT.md` (what P6 replaces), `docs/SARVAM_STREAMING_TTS_CONTRACT.md` (the
verified wire contract), and `docs/P6_STREAMING_TTS_RESULTS.md` (what shipped, tested, measured) for
the rest of the picture. This doc is the "what it is and why," parallel to `docs/
STREAMING_LLM_ARCHITECTURE.md`.

## Where it lives

- `services/api/app/live_providers/streaming_tts.py` — `StreamingTTSProvider` Protocol,
  `StreamingTTSConfig`, `TTSCallContext`, `TTSCapabilities`, `TTSFailureClass`, and the
  `TTSStreamEvent` union (`TTSSessionStarted` / `TTSTextAccepted` / `TTSFirstAudio` / `TTSAudioChunk` /
  `TTSGenerationCompleted` / `TTSStreamFailed` / `TTSStreamCancelled` / `TTSSessionClosed`). No Sarvam
  wire shapes leak past this module.
- `services/api/app/live_providers/sarvam_streaming_tts.py` — the real WebSocket client, verified live
  against `wss://api.sarvam.ai/text-to-speech/ws` (not guessed — see the contract doc for the probe
  scripts and results). Uses `output_audio_codec="mulaw"` + `speech_sample_rate="8000"`: raw,
  header-free audio at exactly Twilio's wire format.
- `services/api/app/modules/live_call/transport/tts_bridge.py` — `TTSStreamingSession` (owns the
  connection, the ordered text-sender task, the audio-consumer task), `TTSResponseHandle` (one per
  logical agent response), `begin_response_feed()` (the glue every turn loop uses), `chunk_text_for_tts()`
  (local chunking for already-fully-known text, reusing P5's `SpeakableChunker`).
- `services/api/app/modules/live_call/transport/session.py` — `RealtimeMediaSession` gained
  `wait_for_mark_ack()` and a `tts_streaming_session` slot; `OutboundAudioChunk` gained `mark_name`
  (assigned at enqueue time, not send time) and `audio_is_mulaw_8k` (skip PCM→μ-law re-encoding for
  audio that's already μ-law).
- `services/api/app/modules/live_call/transport/transitional_bridge.py` — `speak_turn_reply()`, the one
  function both turn loops now call to turn a turn's reply text into audio, unifying what used to be two
  separate inline `synthesize_for_stream()`+`_send_pcm_reply()` blocks.
- `services/api/app/config.py` — `Settings.tts_mode` / `effective_tts_mode` / `tts_stream_failure_policy`.

## The core design decision: one text queue, fed two different ways

`TTSStreamingSession` doesn't care whether text arrives from an LLM streaming in real time or from a
string that was already fully known — both paths end up calling `TTSResponseHandle.send_chunk()`, which
pushes onto the same ordered `asyncio.Queue`, drained by one sender task. This is what makes ordering a
structural guarantee (spec §22-23) rather than something to test for and hope holds:

```
P5 on_speakable_chunk callback (LLM streaming a response)  ─┐
                                                              ├─> TTSResponseHandle.send_chunk() ─> _text_queue ─> _run_sender() ─> provider.send_text()/flush()
chunk_text_for_tts(already-known reply text)                ─┘
```

`begin_response_feed(tts_session)` is the one place a turn loop decides which path applies, by
inspecting whether the `on_speakable_chunk` callback it handed to `process_turn()` ever actually fired:

- **Fired** (an LLM-streamed response reached free generation): the callback already sent every chunk
  to `send_chunk()` in real time, DURING `process_turn()`'s own execution — audio can start arriving
  before the LLM has finished generating the rest of the answer. This is P6's actual point.
- **Never fired** (canned text, `FastTurnRouter`, `COMPLETE_OBJECTIVE`, or `LLM_RESPONSE_MODE=complete`):
  `speak_turn_reply()` chunks the already-fully-formatted `result.reply_text` locally via
  `chunk_text_for_tts()` and feeds it the same way — spec §62-64's requirement that canned responses
  also get the "audio starts before the whole utterance is synthesized" benefit, just without an LLM to
  overlap with (there's nothing to overlap — the text was already fully known).

## A real formatting tradeoff, stated plainly

`SpokenResponseFormatter.format()` (acknowledgement prefix, `max_response_sentences` truncation) needs
the WHOLE response text and runs only after `process_turn()` returns. An LLM-streamed reply's audio may
already be playing by then (spec §70: "once SpeakableChunk 0 has reached TTS it's effectively
committed"). So: **when the callback fires, the acknowledgement prefix is never spoken, and
`max_response_sentences` truncation is never enforced on the streamed audio** — the customer hears
exactly what the LLM produced, unsummarized. Canned/fast-path/complete-mode replies are unaffected:
they always chunk the fully-formatted string, so they keep today's formatting behavior byte-for-byte.
This is a real, deliberate scope boundary for P6, not an oversight — see the results doc for how much it
actually matters in practice (not much: this codebase's own prompt already asks for 1-2 sentences, and
skipping a generic acknowledgement filler is arguably an improvement, not a regression).

## Connection lifecycle: one per call, connected early

`_connect_streaming_tts()` runs once, in `_processing_loop`, right after Media Streams itself starts and
before the greeting is even synthesized (spec §15) — so the first REAL turn's `SpeakableChunk` never
pays WebSocket handshake latency. Measured live: connect P50 140ms (see results doc) — entirely hidden
from the customer-facing latency budget by connecting this early. A connect failure leaves
`session.tts_streaming_session = None`; every turn loop treats that exactly like `TTS_MODE=batch` for
the rest of the call — never fails call setup over a provider hiccup.

## Correlating audio with responses: our IDs, not the provider's

Verified live (contract doc): Sarvam's own `request_id` is scoped to the WHOLE WebSocket connection, not
to an individual text/flush cycle — reusing one connection across many turns (which P6 does by design)
means the provider gives no built-in way to tell which turn a given audio chunk belongs to.
`response_id` (P5's own `SpeakableChunk.response_id`, reused end-to-end rather than inventing a second
id) is threaded through every layer instead: `TTSResponseHandle` → `provider.send_text()`/`flush()` →
every `TTSStreamEvent` the provider yields → `OutboundAudioChunk.response_sequence_id`.

## Generation ownership — minimal, not P9

`TTSStreamingSession.begin_response()` supersedes an unfinished previous response rather than letting
two audio streams mix (spec §50-51): the old response's pending outcome is marked failed
(`"superseded_by_new_response"`), `provider.cancel()` is fired for it, and any of its audio still
arriving from the provider is dropped by `_run_consumer`'s `pending.event.is_set()` check. This path is
never actually exercised in normal P6 operation — every turn loop always awaits one response's
`finish()` before the next customer turn can begin a new one — it's a safety net against a future bug,
explicitly not full P9 stale-replay protection (spec §78).

## Dead-connection timeout

A real gap found while writing this: if the provider connection dies mid-response with no completion
event ever arriving, `_finish_response()` would otherwise await `pending.event.wait()` forever.
`RESPONSE_COMPLETION_TIMEOUT_SECONDS` (30s — generous relative to Sarvam's measured faster-than-real-time
throughput) bounds this: a timeout resolves the response as failed
(`"timeout_waiting_for_completion"`), which then flows through the exact same
chunks-sent-zero-vs-nonzero fallback policy as any other provider failure. Never a silent hang.

## Failure policy

`speak_turn_reply()` implements spec §71/§72 precisely:

- **No audio sent yet for this response** (`chunks_sent == 0`): fall back to one batch REST
  `SarvamTTS.synthesize()` call on the same text — the exact pre-P6 path, so the customer still hears a
  complete, correct reply, just without the early-audio benefit for that one turn.
- **Some audio already delivered** (`chunks_sent > 0`): no fallback is attempted. Replaying from the
  start would repeat what the customer already heard; a smart partial-recovery utterance would need to
  know exactly which words were actually spoken, which nothing in this pipeline tracks precisely enough
  to do safely. The simplest acceptable P6 behavior — stop, log it, let the call continue on the next
  turn — is what shipped, documented as a deliberate scope boundary, not a silent gap.

`TTS_STREAM_FAILURE_POLICY=batch_fallback` (default) governs the first case; `=fail` is available for
environments that would rather end the call than fall back silently.

## Closing integration: the real playback-completion fix

Every reply-then-force-close path in both turn loops used to start the grace-period timer the instant
audio was *enqueued*, not once it had actually *played* (a real, if rarely-triggered, bug — see the
audit doc). `OutboundAudioChunk.mark_name` is now assigned by the enqueuer (not the send loop) precisely
so a caller can know in advance which mark corresponds to a response's last chunk;
`RealtimeMediaSession.wait_for_mark_ack()` lets `_grace_deadline_after_playback()` await that specific
mark (bounded by `MARK_ACK_TIMEOUT_SECONDS=10s`, falling back to starting the timer anyway on a lost
mark message — never hangs the call) before the grace clock starts. Applied uniformly to both the batch
and streaming-TTS paths, and to every force-close branch in both turn loops — the existing
duplicate-closing-reaffirm behavior (`REOPENED_REAFFIRM`) is untouched, since it's a `closing.py`/
`prompt_builder.py` concern P6 never touches.

## Audio bridge: verified direct pass-through, not a new decoder

`docs/SARVAM_STREAMING_TTS_CONTRACT.md`'s live probe found `output_audio_codec=mulaw` +
`speech_sample_rate=8000` returns raw, headerless μ-law bytes — Twilio's exact wire format. So the
"bridge" is almost nothing: `TTSAudioChunk.data` goes straight into `OutboundAudioChunk(...,
audio_is_mulaw_8k=True)`, and `_send_loop` base64-encodes it directly, skipping
`encode_twilio_media_payload()`'s PCM16 resample/μ-law-encode path entirely for this case (that path is
kept, unchanged, for the existing batch-TTS `OutboundAudioChunk`s, which are still PCM16). No ffmpeg, no
temporary files, no new decoder dependency — confirmed unnecessary by the live probe, not assumed.

## What P6 explicitly does not do (per spec, restated)

- **Automatic barge-in**: not yet, P8. `provider.cancel()` and `TTSStreamingSession`'s supersede logic
  are the primitives; nothing calls them from a detected interruption.
- **TTS WebSocket reconnect**: not implemented. Unlike the STT streaming side (P3/P4's bounded
  reconnect), a dropped TTS connection mid-call is not automatically reconnected — the dead-connection
  timeout above prevents a hang, and the failure policy provides a fallback for the CURRENT response,
  but no new connection is established for subsequent turns. A real, documented gap, not silently
  dropped — flagged as a follow-up in the results doc.
- **Full P9 stale-replay protection**: the generation-ownership lock here is minimal (see above).
- **Live mid-call reconfiguration**: `supports_live_reconfiguration=False` — not verified this pass; a
  language switch mid-call would need a fresh connection, not attempted here since P6 never triggers one.
- **Pronunciation dictionaries**: `dict_id` is a real, verified config field, not wired into any agent
  configuration surface this pass (spec §65 explicitly permits this).
- **Sub-20ms audio re-packetization**: Sarvam's own ~140-275ms chunking is forwarded as-is; see the
  contract doc's "Chunk sizing observed" section for the reasoning.
