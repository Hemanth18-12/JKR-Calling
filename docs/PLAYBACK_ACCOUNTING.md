# P7 — Playback Accounting: PlaybackUnit, Marks, and the PLAYED-vs-CLEARED Distinction

See `docs/REALTIME_PIPELINE_COORDINATOR.md` for the surrounding coordinator. This doc is specifically
about how one piece of audio's fate gets tracked from "TTS produced it" to "we know what happened to
it" — the single most important piece of groundwork P7 lays for P8.

## Why "one PlaybackUnit per SpeakableChunk" isn't what shipped

The spec's own framing (§24) describes a playback unit as `SpeakableChunk → TTS → audio → one logical
playback unit`. In practice, Sarvam's own internal buffering does not preserve that boundary — verified
in `docs/SARVAM_STREAMING_TTS_CONTRACT.md`: audio is emitted once Sarvam's own buffer crosses a
character threshold, not 1:1 with each `send_text()` call. A single `SpeakableChunk` can produce zero,
one, or several raw audio messages, and a raw audio message doesn't self-report which `SpeakableChunk`
it "belongs to."

**What shipped instead**: one `PlaybackUnit` per audio chunk actually enqueued to Twilio (1:1 with
`OutboundAudioChunk`, 1:1 with a Twilio `mark`). This is the finest granularity the pipeline has
*precise, not approximate* tracking for — we assign the mark name, we know exactly when it's sent, and
Twilio's own mark event tells us exactly when it's acknowledged. `PlaybackUnit.text` is deliberately left
unset rather than asserting a false precision about which words map to which audio (spec §158's own
explicit caution against overclaiming ear-level accuracy).

## PlaybackUnit

```python
@dataclass
class PlaybackUnit:
    response_id: str
    sequence_id: str
    unit_index: int             # = TTSAudioChunk.audio_chunk_index
    mark_name: str
    audio_duration_ms: int       # via audio_codec.audio_duration_ms() — see below
    bytes_sent: int
    created_at: float
    sent_at: float | None
    mark_acknowledged_at: float | None
    state: PlaybackUnitState     # CREATED | SENT | ACKNOWLEDGED | CLEARED | CANCELLED
    clear_epoch_at_creation: int
```

Built in `RealtimePipelineCoordinator._apply_outcome()`, from `TTSTurnOutcome.chunks` — a list of
`SentAudioChunkInfo` records `TTSStreamingSession._run_consumer()` already builds (mark name, bytes,
duration, timestamp) as it enqueues each `OutboundAudioChunk` — P7 doesn't recompute anything
`tts_bridge.py` already computed, it just surfaces it at the coordinator layer.

## `audio_duration_ms()` — one centralized utility, not scattered assumptions

```python
def audio_duration_ms(*, byte_length: int, codec: str, sample_rate: int, channels: int = 1) -> int:
```

In `transport/audio_codec.py`. `codec="mulaw"` (one byte/sample — Sarvam's verified direct streaming
output) or `"pcm16"` (two bytes/sample — the batch path); any other value raises rather than silently
guessing. This is what makes "8000 bytes ≈ 1 second" (spec §75) a single, tested calculation instead of
a comment repeated in several places.

## PLAYED vs. CLEARED — the actual mechanism

Two hooks, added to `RealtimeMediaSession` as optional callbacks (`on_mark_acknowledged`,
`on_playback_clear`) so the session itself doesn't need to know a coordinator exists:

```python
def _on_mark_acknowledged(self, mark_name: str) -> None:
    unit = self._units_by_mark.get(mark_name)
    if unit is None or unit.state in (PlaybackUnitState.CLEARED, PlaybackUnitState.ACKNOWLEDGED):
        return  # cleared audio is never retroactively "heard"; a redelivered ack never double-counts
    unit.state = PlaybackUnitState.ACKNOWLEDGED
    ...
    ctx.audio_ms_acknowledged += unit.audio_duration_ms

def _on_playback_clear(self) -> None:
    self._clear_epoch += 1
    for unit in self._units_by_mark.values():
        if unit.state == PlaybackUnitState.SENT:
            unit.state = PlaybackUnitState.CLEARED
```

The rule, stated plainly: **at the moment a clear is requested, every unit that has been sent but whose
mark has not yet been acknowledged is classified CLEARED, immediately** — not left pending, not
retroactively resolved later. If Twilio still delivers that unit's mark event afterward (it may),
`_on_mark_acknowledged`'s own guard refuses to flip it back to ACKNOWLEDGED. This is a deliberately
conservative, "unknown → treat as not heard" rule, chosen specifically because it's the safe direction
for P8 (better to undercount confirmed-heard audio than to overcount it when barge-in logic needs to
reason about what the customer actually heard).

This required no real Twilio clear-during-playback data to implement correctly — the rule is entirely
about *our own* bookkeeping at the instant *we* issue a clear, which is fully known and controlled by
this code, not something that needed to be observed from a real call.

A queued-but-not-yet-sent chunk (still sitting in `outbound_queue` when a clear happens) is handled by
`_send_loop`'s own pre-existing P2 logic (`if playback_state == CLEARING: continue`) — it's dropped
before ever becoming a `PlaybackUnit`, correctly, with no P7 change needed there.

**Verified** (`test_clear_marks_pending_units_cleared_not_acknowledged`): two units sent, one acked
before a clear, one not — the acked one stays ACKNOWLEDGED, the pending one becomes CLEARED, and a late
ack for the cleared one is provably ignored.

## Idempotency

A real bug caught by testing, not by inspection: the first version of `_on_mark_acknowledged` only
guarded against `CLEARED`, not against an *already-ACKNOWLEDGED* unit — so a redelivered mark event
(spec §131: "duplicate event tolerance") would double-count `audio_ms_acknowledged`. Fixed by adding
`ACKNOWLEDGED` to the same early-return guard; `test_duplicate_mark_ack_does_not_double_count` is the
regression test.

## Backlog / lookahead estimation

`RealtimePipelineCoordinator.backpressure_snapshot()`:

```python
pending_audio_ms = sum(u.audio_duration_ms for u in ctx.playback_units if u.state == PlaybackUnitState.SENT)
```

Every unit still in the SENT state (enqueued/sent to Twilio, not yet acknowledged or cleared) counts
toward the outstanding playback backlog — the practical estimate of "how much audio is currently
buffered somewhere between us and the customer's ear." See `docs/BACKPRESSURE_ARCHITECTURE.md` for how
this feeds into lookahead/backpressure policy.

## What this is NOT

Not P9's strict stale/duplicate-sequence rejection — `_units_by_mark` and `_contexts` are plain dicts
that grow for the life of a call (bounded by call duration and turn count, not actively pruned this
pass), and there is no cryptographic or sequence-number-based rejection of out-of-order provider events
beyond what `is_current()`'s response-id check already provides. Not exact word-level "what did the
customer hear" reconstruction — `PlaybackUnit.text` is deliberately absent.
