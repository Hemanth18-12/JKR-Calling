# P7 — Backpressure, Queue Bounds, Dead-Air, and Event-Loop Lag

See `docs/P7_REALTIME_PIPELINE_AUDIT.md` for the full queue inventory as found (including the one
genuinely unbounded queue this phase fixed). This doc covers the policy and the two new observability
primitives (dead-air classification, event-loop lag) P7 adds.

## Queue inventory (post-P7)

| Queue | Producer | Consumer | Bound | Policy |
|---|---|---|---|---|
| `inbound_audio_queue` | Twilio receive loop | STT forwarder / batch turn buffer | 250 frames (~5s) | DROP + counted metric — never blocks the receive loop (P2, unchanged) |
| STT `event_queue` | `_drain_stt_events` | streaming-generation poll loop | **100** (was unbounded — fixed this phase) | BLOCK — a stalled poll loop backpressures the drain task, which backpressures the STT socket's own recv, rather than growing without bound |
| TTS `_text_queue` | `on_speakable_chunk` callback / locally-chunked canned text | `TTSStreamingSession._run_sender` | 64 items | BLOCK — spec §44/§53: pause upstream (the LLM callback awaits the `put()`) rather than drop or fail the response |
| `outbound_queue` | `TTSStreamingSession._run_consumer` / batch `_send_pcm_reply` | `_send_loop` | 250 chunks | BLOCK |

Every hot-path queue in this codebase is now bounded, with the bound and the reason documented at its
definition site — the one exception found (STT `event_queue`) was fixed as part of this phase's audit,
not left as a known gap.

**There is no separate "LLM chunk queue"** — `on_speakable_chunk` is a direct synchronous callback
invoked from inside `StreamingResponseAssembler.run()`'s own loop (P5), not a queue. Backpressure from
TTS to the LLM already exists implicitly: if `_text_queue` is full, the callback's `await handle
.send_chunk()` blocks, which blocks `StreamingResponseAssembler.run()`'s own event loop, which — because
the assembler is what's actively consuming the LLM's SSE stream — means the LLM's own token production
isn't being *read* as fast either (spec §42's "pause or slow consumption of future SpeakableChunks" is
satisfied by construction, not by an added mechanism).

## Playback backlog (the one that matters most for future P8 quality)

`RealtimePipelineCoordinator.backpressure_snapshot()["twilio_playback_backlog_ms"]` — the sum of every
`PlaybackUnit.audio_duration_ms` still in the `SENT` state (enqueued/sent, not yet acknowledged or
cleared). This is the practical estimate of how much audio is currently buffered somewhere between this
process and the customer's ear (spec §37-38).

**Not implemented this pass**: an active lookahead cap that pauses TTS→Twilio forwarding once this
backlog crosses a threshold (`PLAYBACK_TARGET_LOOKAHEAD_MS`/`PLAYBACK_MAX_LOOKAHEAD_MS` from spec §39).
The *measurement* exists and is tested; the *enforcement* (pausing the consumer loop when backlog is
too high) does not. Real Sarvam audio arrives in Sarvam's own ~140-275ms sub-chunks (P6 contract doc),
and this codebase's typical response is 1-3 sentences — the backlog in practice stays small without any
active cap, which is why this was deprioritized against the coordinator/accounting work this phase
prioritized. Flagged honestly as a gap for a focused follow-up, not silently deferred.

## Dead-air classification

```python
class DeadAirLevel(StrEnum):
    OK, WARNING, FATAL

DEAD_AIR_WARNING_MS = 1500
DEAD_AIR_FATAL_MS = 4000

def classify_dead_air(elapsed_ms, *, warning_ms=DEAD_AIR_WARNING_MS, fatal_ms=DEAD_AIR_FATAL_MS) -> DeadAirLevel: ...
```

`RealtimePipelineCoordinator.dead_air_status()` measures elapsed time since the active response's
`created_at` (set the instant `begin_response()` is called, immediately after a turn commits — the
practical proxy for `USER_TURN_COMMITTED`, same anchor spec §59's `TURN_COMMIT_TO_FIRST_MEDIA_MS` uses)
and reports the current `ResponseState` as the stage (spec §53's root-cause requirement — "which stage
is currently in progress" is answered directly by which `ResponseState` the context is in, not a
separate parallel tracking mechanism).

**Deliberately not implemented**: any automatic filler-phrase injection (spec §54/§112 explicitly warn
against a fake "checking on that..." unless something real is happening) and any live, continuously-
running polling task that calls this on a timer and pages/logs automatically. What shipped is the
*classification function* and the *on-demand status check* — real, tested, callable from a debug
endpoint or a future watchdog task — not a wired-up alerting pipeline. The distinction matters: a caller
can query "how long has this response been waiting, and on what?" right now; nothing currently asks that
question periodically on its own.

## Event-loop lag

`services/api/app/modules/live_call/transport/event_loop_lag.py` — one process-wide
`EventLoopLagMonitor`, started via the FastAPI app's `lifespan` context manager (not the deprecated
`@app.on_event("startup")`), stopped on shutdown. Measurement technique: schedule a periodic
`asyncio.sleep(interval)` and compare actual elapsed time against the requested interval — any excess is
time the loop was blocked by something else. Exposed on `/health` as `event_loop_lag_ms`/
`event_loop_max_lag_ms` (spec §107: internal-only, no dashboard needed).

**Verified** (`test_event_loop_lag.py`): idle baseline near zero; a deliberate synchronous
`time.sleep()` in the middle of the monitored process produces a measurable, non-zero lag spike — proof
the technique actually detects a blocked loop, not just that the class exists.

## Hot-path blocking audit (spec §50-51)

Checked every realtime task (`_receive_loop`, `_processing_loop`, `_send_loop`,
`TTSStreamingSession._run_sender`/`_run_consumer`, `RealtimePipelineCoordinator`'s own methods) for
`time.sleep`, blocking requests, synchronous DB calls, or subprocess calls in the hot path. None found —
this codebase's existing discipline (async DB sessions throughout, `httpx`/`websockets` for all network
I/O, `audioop` for in-process codec work) already held. `_record_latency`/telemetry persistence calls
are awaited inline today (not yet batched/async-offloaded per spec §135-136's aspiration) — a real,
small gap for a future pass if telemetry volume ever makes it matter; not observed as a problem at this
phase's scale.
