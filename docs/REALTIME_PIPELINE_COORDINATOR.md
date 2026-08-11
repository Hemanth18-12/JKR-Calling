# P7 — RealtimePipelineCoordinator

See `docs/P7_REALTIME_PIPELINE_AUDIT.md` (what P7 replaces), `docs/PLAYBACK_ACCOUNTING.md` (the
playback-unit/mark/clear model in depth), `docs/BACKPRESSURE_ARCHITECTURE.md` (queues, backpressure,
dead-air, event-loop lag), and `docs/P7_REALTIME_PIPELINE_RESULTS.md` (what shipped, tested, measured).

## Why this exists

By P6, every realtime component was independently correct: `StreamingResponseAssembler` (P5) correctly
streams LLM text; `TTSStreamingSession` (P6) correctly streams TTS audio and has its own minimal
generation-ownership lock; `RealtimeMediaSession` (P2) correctly tracks marks and playback state. But
"which response owns the call right now" was answered differently — and separately — by each layer:
`RealtimeMediaSession` had its own `start_new_response_sequence()` counter (used only by the batch
path), `TTSStreamingSession` had its own `_active_response_id` (used only by the streaming path), and
nothing above the TTS layer checked ownership at all. `RealtimePipelineCoordinator` is the single
authority these all now answer to.

## What it is, concretely

`services/api/app/modules/live_call/transport/coordinator.py`. One instance per call, created alongside
`TTSStreamingSession` in `_connect_streaming_tts()` (never on its own — a call with no live TTS
connection has nothing for a coordinator to orchestrate), stored on `RealtimeMediaSession
.pipeline_coordinator`.

It does **not** own STT algorithms, `TurnManager` rules, RAG, `ConversationEngine`, LLM prompting, the
TTS provider's wire protocol, or Twilio's codec details — all of that is unchanged, owned exactly where
it already was. It owns **lifecycle and flow control**: whose text/audio is currently allowed to become
customer-facing output, and precise accounting of what happened to it.

## Response lifecycle

```python
class ResponseState(StrEnum):
    CREATED, GENERATING_TEXT, TEXT_STREAMING, TTS_STREAMING,
    GENERATION_COMPLETE, PLAYBACK_PENDING, PLAYBACK_COMPLETE,
    CANCEL_PENDING, CANCELLED, SUPERSEDED, FAILED
```

Only `PLAYBACK_COMPLETE`/`CANCELLED`/`SUPERSEDED`/`FAILED` are terminal — release ownership. Everything
else is "in flight" and still owns the call's audio. `PLAYBACK_PENDING`/`CANCEL_PENDING` are modeled in
the enum (spec §6) but not currently entered by any code path this phase — `complete_generation()` goes
straight from `TTS_STREAMING` to `GENERATION_COMPLETE`/`FAILED`, and cancellation is synchronous enough
in this implementation that a distinct "pending" state was never observably reachable; kept for forward
compatibility rather than removed.

## Response identity

```python
@dataclass
class ActiveResponseContext:
    call_id: uuid.UUID
    turn_id: str
    response_id: str       # = SpeakableChunk.response_id, reused end-to-end (P5 → P6 → P7)
    generation_id: str
    sequence_id: str        # = response_id in this implementation — see "What sequence_id actually is" below
    state: ResponseState
    ...
```

`response_id`/`generation_id` are minted once, in `begin_response()`, and follow the response through
every layer: `TTSResponseHandle`/`CoordinatedResponseHandle` → `provider.send_text()`/`flush()` → every
`TTSStreamEvent` the provider yields → `OutboundAudioChunk.response_sequence_id` → `PlaybackUnit
.response_id`. No identity is re-derived or reconstructed at any layer.

**What `sequence_id` actually is**: the spec's model separates `response_id` and `sequence_id` as
distinct concepts; this implementation found no case where they needed to differ (a response never
splits into multiple sub-sequences in the current architecture), so `sequence_id` is set equal to
`response_id` — the field exists (on both `ActiveResponseContext` and `PlaybackUnit`) so a future phase
that DOES need sub-sequence granularity doesn't need to add a new field, just start populating this one
differently.

## Distinct generated/committed/sent/acknowledged tracking (spec §17-23)

```python
text_generated: str          # everything the LLM produced (or the canned string) — customer may not hear all of it
text_committed_to_tts: str   # already submitted to TTS — still doesn't mean the customer heard it
audio_ms_generated: int      # provider produced it — does not mean sent
audio_ms_sent: int           # sent to Twilio — does not guarantee heard
audio_ms_acknowledged: int   # best available application-level evidence that playback progressed
```

No single `response_completed=True` boolean anywhere. `first_audio_ms` is threaded through separately
from `TTSTurnOutcome` (P6's own TTS-layer timing) rather than re-derived.

## Ownership enforcement

Every entry point into customer-facing output goes through an ownership check:

```python
def is_current(self, response_id: str) -> bool:
    return self._active is not None and self._active.response_id == response_id and not self._active.is_terminal()
```

`submit_speakable_chunk()` (the callback P5's `on_speakable_chunk` invokes) checks this before doing
anything; a chunk for a response that's no longer current is dropped and logged
(`pipeline_chunk_dropped_stale`), never forwarded to TTS. This is spec §12-14's requirement made real —
previously, nothing upstream of `TTSStreamingSession` performed this check at all.

## One active response, supersede vs. cancel

`begin_response()` automatically supersedes an unfinished previous response before creating the new one
— at most one response is ever "active" per call. **CANCEL** (`cancel_response()`) means the response
should stop with no replacement necessarily existing; **SUPERSEDE** (`supersede_response()`) means it
lost ownership because a newer response replaced it — the same underlying stop mechanism
(`TTSStreamingSession.cancel_response()`), but a different `ResponseState` and a different semantic
for whatever consumes it later (P8 will care about this distinction; P7 just preserves it).

Neither is triggered automatically from user speech in P7 — `note_customer_speech()` only *records*
`customer_spoke_during_generation`/`customer_spoke_during_playback` on the active context (spec §88-91);
nothing acts on it. That's P8's job.

## A real bug this design surfaced and fixed during development

The first implementation had `RealtimePipelineCoordinator.supersede_response()`/`cancel_response()`
reaching directly into `TTSStreamingSession._provider.cancel()`, bypassing `TTSStreamingSession`'s own
`_pending` bookkeeping entirely. This meant the coordinator's `ActiveResponseContext` and
`TTSStreamingSession`'s internal state could disagree about whether a response was still live — a
classic "two sources of truth" bug. Fixed by extracting `TTSStreamingSession.cancel_response()` as a
proper public method (refactored out of `begin_response()`'s own inline supersede logic, which now calls
it too) and having the coordinator call *that* instead of touching the provider directly — both layers
now always agree, verified by `test_begin_response_supersedes_unfinished_previous_response` and the
rest of `test_coordinator.py`.

## `begin_response_feed()` / `CoordinatedResponseHandle`

The one function every turn loop calls to start a response through the coordinator:

```python
feed = await begin_response_feed(session.pipeline_coordinator, turn_id=...)
# feed.handle: CoordinatedResponseHandle | None — duck-type-compatible with tts_bridge.py's own
#              TTSResponseHandle (send_chunk/finish), so speak_turn_reply() needed zero changes
# feed.on_chunk: the callback to hand process_turn(on_speakable_chunk=...)
# feed.callback_fired(): whether it ever actually fired
```

`CoordinatedResponseHandle.send_chunk()`/`finish()` delegate to `coordinator.submit_speakable_chunk()`/
`complete_generation()` — every chunk, whether LLM-streamed or locally-chunked canned text, is
ownership-checked and lifecycle-tracked identically (spec §92-94: "everything audible goes through
coordinator" — canned/fast-path/RAG/closing responses are not a separate path).

## P8 readiness: `interrupt_active_response()`

```python
async def interrupt_active_response(self, *, reason: str) -> InterruptionSnapshot | None:
```

Not wired to any automatic trigger (no VAD/interruption policy calls this in P7 — that's P8's whole
job). Building block only: returns an `InterruptionSnapshot` (generated/committed text, generated/sent/
acknowledged audio ms, pending playback ms, the full `PlaybackUnit` list) and cancels the active
response. Tested directly (`test_interrupt_active_response_returns_snapshot_and_cancels`) — proven to
work correctly today, waiting for P8 to decide *when* to call it.
