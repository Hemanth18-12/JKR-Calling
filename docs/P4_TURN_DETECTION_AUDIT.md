# P4 — Turn Detection Audit

Traced from the actual P3 code (`services/api/app/modules/live_call/transport/streaming_bridge.py`,
`app/live_providers/streaming_stt.py`) before any P4 change. This is what P4 replaces.

## Current speech-start behavior

`SpeechStarted` (Sarvam's `vad.speech_start` event) is parsed into a typed event and reaches
`_handle_stt_event()`, but is used for exactly one thing: starting a latency timer
(`turn_state.turn_start_monotonic`) for the `stt_stream_first_partial`/`stt_stream_finalize` metrics.
It has **zero** effect on conversational state — nothing tracks "the customer is currently speaking"
anywhere reachable outside this one timer field.

## Current speech-end behavior

**`SpeechEnded` (Sarvam's `vad.speech_end` event) is not handled at all.** `_handle_stt_event()`'s
if/elif chain has a branch for `STTSessionStarted`, `STTSessionEnded`, `STTError`, `"SpeechStarted"`
(by type-name string, not `isinstance`), `"PartialTranscript"`, and `FinalTranscript` — there is no
branch for `SpeechEnded` at all. It falls through to the final `return _CONTINUE` and is silently
dropped. This is a genuine gap, not a documented limitation.

## Current final-transcript behavior — this is the core thing P4 replaces

`_handle_final_transcript()` does, in order, for **every** `FinalTranscript` event:
1. Empty-text check → drop and log if empty.
2. Duplicate check (`utterance_idx` + normalized text) → drop and log if duplicate.
3. Record `stt_stream_finalize` latency.
4. **Immediately** call `process_known_transcript_turn()` → the real `ConversationEngine`, persist,
   TTS, reply — no waiting, no semantic check, no coalescing with a possible continuation.

There is no concept of "this final might not be the whole thought" anywhere in this path. A Sarvam
final for "Tomorrow" and a later final for "actually evening better" (the exact P4 spec's own
thinking-pause example) would today produce **two separate `ConversationEngine.process_turn()`
calls, hence two separate agent replies** — the second call would arrive with `known_fields`
already partially filled from the first, likely producing a confusing double-response. This has not
been observed on a real call yet only because it hasn't been specifically tested, not because the
code guards against it.

## Current partial-transcript handling

`PartialTranscript` only drives the `stt_stream_first_partial` latency metric. Its `text` is never
read for anything else — no display, no speculative processing, no semantic pre-check.

## Transcript coalescing

**None exists.** Each `FinalTranscript` is independent; there is no `current_turn_segments` list, no
concept of "same logical turn," nothing resembling `SegmentAggregator`.

## Silence timer / transitional buffer remnants

`transitional_bridge.TurnBuffer` (the P2/batch-mode trailing-silence energy detector,
`audioop.rms()`-based) still exists and is still the live implementation for `STT_MODE=batch`, but
`streaming_bridge.py` (`STT_MODE=streaming`) does not use it at all — turn segmentation under
streaming mode is 100% Sarvam's own server-side VAD (`endpointing=vad` in `StreamingSTTConfig`),
consumed only as "did a final arrive," never as an independent local signal.

## When turn ID is created

Never. There is no `turn_id` concept anywhere in the streaming path — `sequence_index` (from
`redis_state["agent_turns"]`) is the closest thing, incremented per persisted turn, not assigned at
speech-start.

## When ConversationEngine is invoked

Directly from `_handle_final_transcript()`, synchronously in the same coroutine that received the
`FinalTranscript` event, with no intermediate authority. This is the literal thing spec §34/§91
require changing: "Sarvam FinalTranscript must NOT directly trigger ConversationEngine.process_turn()."

## Grace timers / call-closing interactions

`_TurnTrackingState.in_grace_period`/`grace_deadline`, `_check_grace_expiry()` — the P2/P3
closing-grace mechanism (never hang up while the customer might still be speaking after a completed
objective) is independent of turn detection and must be preserved unchanged (spec §74/§107).

## Current customer-speaking / agent-speaking state

Does not exist as an explicit signal. `RealtimeMediaSession.playback_state` (IDLE/PLAYING/CLEARING)
tracks agent playback for marks/clear purposes (P2), but nothing publishes "customer is currently
speaking" as a queryable signal, and nothing correlates the two. P4 §31/§95 requires this to exist
for P8's future use, without acting on it yet.

## Twilio inbound-track handling

Unchanged since P2 — `_receive_loop` in `twilio_media_stream.py` decodes every inbound `media` event
into a normalized `AudioFrame` (PCM16, 8kHz, mono) and enqueues it; `_forward_audio_to_stt` drains
that same queue continuously to Sarvam. This queue is the natural point to also tap for local VAD
(P4 needs to observe the same frames, not a second copy of the audio).

## Existing TurnManager

None. This is a new component.

## Existing Bolna-derived interruption concepts

None found in this codebase — no references to Bolna, no existing interruption/barge-in scaffolding
beyond P2's `clear_agent_audio()` primitive (sends Twilio's `clear` message + drains the outbound
queue; exists and is tested, has no automatic trigger — that remains P8's job, unchanged by P4).

## Current endpoint delay

Whatever Sarvam's server-side VAD decides internally (`silence_duration_ms=500` default, per
`docs/SARVAM_STREAMING_STT_CONTRACT.md` — untuned, not measured against real PSTN audio). JKR has no
independent delay of its own today; a `FinalTranscript` commits the instant it's received.

## Current false-split risk

**High**, by construction — see "current final-transcript behavior" above. Any Sarvam final followed
by a continuation before the next natural pause boundary produces two engine calls today.

## Current long-pause risk

Bounded only by Sarvam's own `silence_duration_ms` (500ms default) — JKR has no visibility into or
control over what happens if Sarvam is slow to finalize; there's no local max-endpoint-wait fallback.

## Current Telugu/code-mix risk

Nothing in the endpointing path is language-aware at all today — `StreamingSTTConfig` is built once
per call from the pinned `language_code`/`mode="codemix"`, but that only affects Sarvam's own
transcription behavior, not any JKR-side pause/endpoint logic (there isn't any).

## Current provider coupling

Total, for endpointing specifically: Sarvam's finals are the only turn-boundary signal. VAD events
exist as a typed event but are unused (`SpeechStarted`) or unhandled (`SpeechEnded`). This is exactly
the "no single provider owns JKR conversational turn boundaries" violation P4 §1 identifies.

## What P4 must change, precisely

Replace step 4 of "current final-transcript behavior" above: `_handle_final_transcript()` currently
calls `process_known_transcript_turn()` directly. P4 inserts a `TurnManager` between the STT event
stream and that call — `_handle_stt_event()`'s `FinalTranscript`/`SpeechStarted`/`SpeechEnded`/
`PartialTranscript` branches feed the `TurnManager` instead of driving engine logic directly; only a
`TurnManager`-emitted `USER_TURN_COMMITTED` decision reaches `process_known_transcript_turn()`. Under
`TURN_DETECTION_MODE=provider` (the default), the `TurnManager` must reproduce today's exact
behavior (commit on first valid non-duplicate final) — this preserves `<Record>` mode and
`STT_MODE=batch` untouched, and makes `STT_MODE=streaming` + `TURN_DETECTION_MODE=provider`
byte-behavior-identical to pre-P4, satisfying spec §75/§107's backward-compatibility requirement.
