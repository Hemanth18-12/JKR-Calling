from __future__ import annotations

import asyncio

from app.modules.live_call.transport.event_loop_lag import EventLoopLagMonitor


async def test_starts_at_zero_lag_before_any_sample():
    monitor = EventLoopLagMonitor(interval_seconds=10.0)
    assert monitor.current_lag_ms == 0.0
    assert monitor.max_lag_ms == 0.0
    assert monitor.samples == 0


async def test_collects_samples_once_started():
    monitor = EventLoopLagMonitor(interval_seconds=0.02)
    monitor.start()
    await asyncio.sleep(0.1)  # several intervals
    monitor.stop()
    assert monitor.samples >= 2


async def test_start_is_idempotent():
    monitor = EventLoopLagMonitor(interval_seconds=0.02)
    monitor.start()
    task_before = monitor._task  # noqa: SLF001
    monitor.start()
    assert monitor._task is task_before  # noqa: SLF001 — second start() did not replace the running task
    monitor.stop()


async def test_stop_before_start_does_not_raise():
    monitor = EventLoopLagMonitor()
    monitor.stop()  # must not raise


async def test_lag_under_artificial_blocking_is_measured():
    monitor = EventLoopLagMonitor(interval_seconds=0.02)
    monitor.start()
    await asyncio.sleep(0.01)
    # Simulate a hot-path block: a synchronous sleep starves the event loop,
    # so the monitor's own sleep(0.02) can't resume on schedule.
    import time

    time.sleep(0.08)  # noqa: ASYNC251 — deliberate: this IS the blocking hot-path call under test
    await asyncio.sleep(0.03)  # let the monitor task catch up and record the overshoot
    monitor.stop()
    assert monitor.max_lag_ms > 0
