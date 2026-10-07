"""Tests for CartesiaStreamingTTS in services/api."""

from __future__ import annotations

import base64
import json
import pytest

from app.live_providers.cartesia_streaming_tts import (
    CartesiaStreamingTTS,
    CartesiaStreamingTTSError,
    NotConfiguredError,
)
from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSFailureClass,
    TTSFirstAudio,
    TTSGenerationCompleted,
    TTSStreamCancelled,
    TTSStreamFailed,
)


def test_cartesia_streaming_tts_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    with pytest.raises(NotConfiguredError):
        CartesiaStreamingTTS(api_key="")


def test_cartesia_streaming_tts_capabilities():
    tts = CartesiaStreamingTTS(api_key="test-key")
    caps = tts.capabilities
    assert caps.supports_streaming_input is True
    assert caps.supports_streaming_audio is True
    assert caps.supports_flush is True
    assert caps.supports_completion_event is True
    assert caps.supports_direct_mulaw_8k is True
    assert caps.supports_cancel is True


@pytest.mark.asyncio
async def test_cartesia_streaming_tts_raises_before_connect():
    tts = CartesiaStreamingTTS(api_key="test-key")

    with pytest.raises(CartesiaStreamingTTSError):
        await tts.send_text(text="hi", response_id="r1", chunk_index=0)

    with pytest.raises(CartesiaStreamingTTSError):
        await tts.flush(response_id="r1")

    with pytest.raises(CartesiaStreamingTTSError):
        async for _ in tts.events():
            pass


class _FakeWebSocket:
    def __init__(self, incoming_messages: list[str] | None = None):
        self.sent_messages: list[str] = []
        self.incoming_messages = incoming_messages or []
        self.closed = False

    async def send(self, data: str):
        self.sent_messages.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.incoming_messages:
            raise StopAsyncIteration
        return self.incoming_messages.pop(0)


@pytest.mark.asyncio
async def test_cartesia_streaming_tts_connect_and_send_text(monkeypatch):
    fake_ws = _FakeWebSocket()

    async def fake_connect(url, **kwargs):
        assert "cartesia_version=" in url
        assert "api_key=test-cartesia-key" in url
        assert kwargs["additional_headers"]["X-API-Key"] == "test-cartesia-key"
        return fake_ws

    monkeypatch.setattr("websockets.connect", fake_connect)

    tts = CartesiaStreamingTTS(api_key="test-cartesia-key")
    config = StreamingTTSConfig(model="sonic-3.6", target_language_code="te-IN", voice_id="custom-voice", pace=1.1)
    context = TTSCallContext(call_session_id="call-1", workspace_id="ws-1")

    await tts.connect(config=config, context=context)

    # 1. Send text
    await tts.send_text(text="నమస్కారం", response_id="resp-1", chunk_index=0)
    assert len(fake_ws.sent_messages) == 1
    sent = json.loads(fake_ws.sent_messages[0])
    assert sent["context_id"] == "resp-1"
    assert sent["transcript"] == "నమస్కారం"
    assert sent["model_id"] == "sonic-3.6"
    assert sent["voice"]["id"] == "custom-voice"
    assert sent["output_format"]["encoding"] == "pcm_mulaw"
    assert sent["output_format"]["sample_rate"] == 8000
    assert sent["language"] == "te"
    assert sent["continue"] is True
    assert sent["generation_config"]["speed"] == 1.1

    # 2. Flush
    await tts.flush(response_id="resp-1")
    assert len(fake_ws.sent_messages) == 2
    flushed = json.loads(fake_ws.sent_messages[1])
    assert flushed["context_id"] == "resp-1"
    assert flushed["continue"] is False


@pytest.mark.asyncio
async def test_cartesia_streaming_tts_events_audio_chunk_and_done(monkeypatch):
    fake_mulaw_bytes = b"\xff\x00\xaa\x55" * 160  # mulaw audio chunk
    b64_audio = base64.b64encode(fake_mulaw_bytes).decode()

    messages = [
        json.dumps({"type": "chunk", "context_id": "resp-1", "data": b64_audio}),
        json.dumps({"type": "done", "context_id": "resp-1"}),
    ]
    fake_ws = _FakeWebSocket(incoming_messages=messages)

    async def fake_connect(url, **kwargs):
        return fake_ws

    monkeypatch.setattr("websockets.connect", fake_connect)

    tts = CartesiaStreamingTTS(api_key="test-key")
    await tts.connect(
        config=StreamingTTSConfig(target_language_code="te-IN"),
        context=TTSCallContext(call_session_id="c1", workspace_id="w1"),
    )

    events = []
    async for event in tts.events():
        events.append(event)

    assert len(events) == 3
    assert isinstance(events[0], TTSFirstAudio)
    assert events[0].response_id == "resp-1"

    assert isinstance(events[1], TTSAudioChunk)
    assert events[1].response_id == "resp-1"
    assert events[1].audio_chunk_index == 0
    assert events[1].data == fake_mulaw_bytes
    assert events[1].codec == "mulaw"
    assert events[1].sample_rate == 8000

    assert isinstance(events[2], TTSGenerationCompleted)
    assert events[2].response_id == "resp-1"


@pytest.mark.asyncio
async def test_cartesia_streaming_tts_cancel_discards_audio(monkeypatch):
    b64_audio = base64.b64encode(b"\x00" * 100).decode()
    messages = [
        json.dumps({"type": "chunk", "context_id": "cancelled-resp", "data": b64_audio}),
        json.dumps({"type": "done", "context_id": "cancelled-resp"}),
    ]
    fake_ws = _FakeWebSocket(incoming_messages=messages)

    async def fake_connect(url, **kwargs):
        return fake_ws

    monkeypatch.setattr("websockets.connect", fake_connect)

    tts = CartesiaStreamingTTS(api_key="test-key")
    await tts.connect(
        config=StreamingTTSConfig(target_language_code="en"),
        context=TTSCallContext(call_session_id="c1", workspace_id="w1"),
    )

    await tts.cancel("cancelled-resp")
    assert any(json.loads(m).get("cancel") is True for m in fake_ws.sent_messages)

    events = []
    async for event in tts.events():
        events.append(event)

    # Audio chunk must be dropped; done becomes TTSStreamCancelled
    assert len(events) == 1
    assert isinstance(events[0], TTSStreamCancelled)
    assert events[0].response_id == "cancelled-resp"


@pytest.mark.asyncio
async def test_cartesia_streaming_tts_error_event(monkeypatch):
    messages = [
        json.dumps({"type": "error", "context_id": "resp-err", "code": 401, "message": "Invalid API Key"}),
    ]
    fake_ws = _FakeWebSocket(incoming_messages=messages)

    async def fake_connect(url, **kwargs):
        return fake_ws

    monkeypatch.setattr("websockets.connect", fake_connect)

    tts = CartesiaStreamingTTS(api_key="test-key")
    await tts.connect(
        config=StreamingTTSConfig(target_language_code="en"),
        context=TTSCallContext(call_session_id="c1", workspace_id="w1"),
    )

    events = []
    async for event in tts.events():
        events.append(event)

    assert len(events) == 1
    assert isinstance(events[0], TTSStreamFailed)
    assert events[0].failure_class == TTSFailureClass.AUTH_ERROR
    assert "Invalid API Key" in events[0].message
