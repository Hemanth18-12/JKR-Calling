"""P7 §49-50 — event loop lag: a realtime system can have healthy provider
latency but still feel slow if the event loop itself is blocked by
something in a hot path (a sync DB call, a CPU-heavy conversion, blocking
I/O). Process-wide, not call-scoped — one monitor per worker process,
started once at process startup.

Measurement technique: schedule a periodic `asyncio.sleep(interval)` and
compare the ACTUAL elapsed time against the requested interval. Any excess
is time the loop spent doing something else (or was simply too busy to
resume this coroutine promptly) rather than idling — the standard way to
observe scheduler responsiveness from inside the loop itself.
"""

from __future__ import annotations

import asyncio
import time


class EventLoopLagMonitor:
    def __init__(self, *, interval_seconds: float = 1.0):
        self._interval_seconds = interval_seconds
        self._current_lag_ms = 0.0
        self._max_lag_ms = 0.0
        self._samples = 0
        self._task: asyncio.Task | None = None

    @property
    def current_lag_ms(self) -> float:
        return self._current_lag_ms

    @property
    def max_lag_ms(self) -> float:
        return self._max_lag_ms

    @property
    def samples(self) -> int:
        return self._samples

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while True:
            t0 = time.monotonic()
            await asyncio.sleep(self._interval_seconds)
            actual = time.monotonic() - t0
            lag_ms = max(0.0, (actual - self._interval_seconds) * 1000)
            self._current_lag_ms = lag_ms
            self._max_lag_ms = max(self._max_lag_ms, lag_ms)
            self._samples += 1


# One process-wide instance, mirroring transport/events.py's own
# module-level `metrics` singleton pattern for exactly this kind of
# process-lifetime observability state.
event_loop_lag_monitor = EventLoopLagMonitor()
