"""P7 §82-83/§141-144 — bounded TTS reconnect between responses (never
mid-response, never an indefinite retry loop). See docs/
STREAMING_TTS_ARCHITECTURE.md's reconnect section and
docs/REALTIME_PIPELINE_COORDINATOR.md.
"""

from __future__ import annotations

import asyncio
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSCallContext,
    TTSCapabilities,
    TTSGenerationCompleted,
)
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import (
    MAX_TTS_RECONNECT_CYCLES,
    TTSStreamingSession,
)


class _DyingProvider:
    """events() ends immediately (simulating a dropped connection) —
    connect()/send_text()/flush() otherwise behave normally."""

    def __init__(self):
        self.connected = False

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        self.connected = True

    async def send_text(self, *, text, response_id, chunk_index):
        pass

    async def flush(self, *, response_id):
        pass

    async def cancel(self, response_id):
        pass

    async def close(self):
        pass

    async def events(self):
        return
        yield  # pragma: no cover — makes this a generator that yields nothing


class _AlwaysFailsToConnectProvider(_DyingProvider):
    async def connect(self, *, config, context):
        raise RuntimeError("connection refused")


class _WorksForeverProvider:
    """A provider whose events() never ends on its own — used as the
    target of a successful reconnect, to prove the session actually
    resumes consuming from the NEW instance."""

    def __init__(self):
        self.connected = False
        self._queue: asyncio.Queue = asyncio.Queue()

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        self.connected = True

    async def send_text(self, *, text, response_id, chunk_index):
        pass

    async def flush(self, *, response_id):
        await self._queue.put(TTSGenerationCompleted(response_id=response_id))

    async def cancel(self, response_id):
        pass

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


def _media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def _start(session: TTSStreamingSession) -> None:
    await session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))


# --- no reconnect configured (pre-P7 behavior) -------------------------


async def test_no_provider_factory_means_no_reconnect_attempted():
    provider = _DyingProvider()
    session = TTSStreamingSession(provider=provider, media_session=_media_session())  # no provider_factory
    await _start(session)
    await asyncio.sleep(0.05)  # let the consumer task observe events() ending

    assert session.reconnect_attempts == 0
    await session.close()


# --- idle reconnect succeeds --------------------------------------------


async def test_idle_reconnect_succeeds_and_resumes_from_new_provider():
    initial = _DyingProvider()
    replacement = _WorksForeverProvider()
    factory_calls = []

    def factory():
        factory_calls.append(1)
        return replacement

    session = TTSStreamingSession(provider=initial, media_session=_media_session(), provider_factory=factory)
    await _start(session)
    await asyncio.sleep(0.05)  # let the dying provider's events() end and reconnect happen

    assert session.reconnect_successes >= 1
    assert len(factory_calls) >= 1
    assert replacement.connected is True

    # prove the session is now actually using the replacement: a real
    # response completes successfully through it.
    handle = session.begin_response("resp_after_reconnect")
    await handle.send_chunk("hello")
    outcome = await handle.finish()
    assert outcome.failed is False
    await session.close()


async def test_reconnect_generation_counter_increments_on_success():
    initial = _DyingProvider()
    replacement = _WorksForeverProvider()
    session = TTSStreamingSession(provider=initial, media_session=_media_session(), provider_factory=lambda: replacement)
    assert session._connection_generation == 0  # noqa: SLF001
    await _start(session)
    await asyncio.sleep(0.05)

    assert session._connection_generation >= 1  # noqa: SLF001
    await session.close()


# --- mid-response: no reconnect attempted -------------------------------


async def test_no_reconnect_attempted_mid_response():
    """spec §144 — a connection lost WHILE a response is active must not
    trigger a reconnect attempt; the in-flight _finish_response() call's
    own timeout is what resolves it, never a blind mid-stream reconnect."""

    class _DiesAfterOneEventProvider:
        def __init__(self):
            self._queue: asyncio.Queue = asyncio.Queue()

        @property
        def capabilities(self):
            return TTSCapabilities(True, True, True, True, False, True, True, True)

        async def connect(self, *, config, context):
            pass

        async def send_text(self, *, text, response_id, chunk_index):
            pass

        async def flush(self, *, response_id):
            pass  # deliberately never completes — response stays "active" until the response's own timeout

        async def cancel(self, response_id):
            pass

        async def close(self):
            pass

        async def events(self):
            return
            yield  # pragma: no cover

    provider = _DiesAfterOneEventProvider()
    factory_calls = []
    session = TTSStreamingSession(
        provider=provider, media_session=_media_session(),
        provider_factory=lambda: factory_calls.append(1) or provider,  # would be called if (incorrectly) reconnected
    )
    await _start(session)

    handle = session.begin_response("resp_active")
    await handle.send_chunk("hello")
    await asyncio.sleep(0.05)  # let events() end while the response is still active

    assert factory_calls == []  # reconnect must NOT have been attempted
    assert session.reconnect_attempts == 0
    await session.close()


# --- bounded cycles / attempts, never an infinite loop ----------------------


async def test_reconnect_cycles_are_bounded_not_infinite():
    """A provider that connects successfully every time but whose events()
    always ends immediately must not spin forever — this is the exact bug
    caught during P7 development (see tts_bridge.py's MAX_TTS_RECONNECT_CYCLES
    docstring)."""
    factory_call_count = {"n": 0}

    def factory():
        factory_call_count["n"] += 1
        return _DyingProvider()

    session = TTSStreamingSession(provider=_DyingProvider(), media_session=_media_session(), provider_factory=factory)
    await _start(session)

    # bounded means this completes promptly — the test itself times out via
    # the harness if this regresses to an infinite loop.
    await asyncio.wait_for(session._consumer_task, timeout=5.0)  # noqa: SLF001

    assert factory_call_count["n"] <= MAX_TTS_RECONNECT_CYCLES + 1
    await session.close()


async def test_reconnect_all_attempts_fail_gives_up_cleanly():
    provider = _DyingProvider()
    session = TTSStreamingSession(
        provider=provider, media_session=_media_session(),
        provider_factory=lambda: _AlwaysFailsToConnectProvider(),
    )
    await _start(session)

    await asyncio.wait_for(session._consumer_task, timeout=10.0)  # noqa: SLF001

    assert session.reconnect_failures > 0
    await session.close()
