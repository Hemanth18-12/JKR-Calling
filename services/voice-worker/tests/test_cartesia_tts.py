"""Tests for CartesiaTTS provider in voice-worker."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.providers.base import NotConfiguredError, VoiceConfig
from app.providers.cartesia import CartesiaTTS
from app.providers.mock import MockTTS


def test_cartesia_tts_not_configured_error_when_key_missing(monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(cartesia_api_key=""))
    tts = CartesiaTTS(api_key="")
    voice = VoiceConfig(provider="cartesia", voice_id="test-voice", language="te-IN")

    with pytest.raises(NotConfiguredError, match="CARTESIA_API_KEY is not configured"):
        import asyncio
        asyncio.run(tts.synthesize(text="నమస్కారం", voice=voice))


def test_cartesia_tts_constructs_with_api_key():
    tts = CartesiaTTS(api_key="test-key-123", model="sonic-3.6", default_voice_id="my-voice")
    assert tts.api_key == "test-key-123"
    assert tts.model == "sonic-3.6"
    assert tts.default_voice_id == "my-voice"


@pytest.mark.asyncio
async def test_cartesia_tts_synthesize_sends_correct_parameters_and_normalizes_audio(monkeypatch):
    captured_request = {}

    # 44 bytes header + 16000 bytes PCM (1 second of 8kHz 16-bit mono)
    fake_wav = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 16000

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        captured_request["url"] = str(url)
        captured_request["headers"] = headers
        captured_request["json"] = json
        return httpx.Response(200, content=fake_wav, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    tts = CartesiaTTS(api_key="test-cartesia-key")
    voice = VoiceConfig(provider="cartesia", voice_id="custom-voice-id", language="te-IN", speaking_speed=1.2)

    result = await tts.synthesize(text="మీ అపాయింట్‌మెంట్ కన్ఫర్మ్ అయింది", voice=voice)

    assert result.is_simulated is False
    assert result.audio_duration_ms == 1000  # 16000 bytes / (8000 * 2) = 1.0s = 1000ms
    assert captured_request["headers"]["X-API-Key"] == "test-cartesia-key"
    assert captured_request["json"]["voice"]["id"] == "custom-voice-id"
    assert captured_request["json"]["language"] == "te"
    assert captured_request["json"]["generation_config"]["speed"] == 1.2


@pytest.mark.asyncio
async def test_cartesia_tts_handles_401_auth_error(monkeypatch):
    async def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, text="Unauthorized", request=request)
        raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    tts = CartesiaTTS(api_key="invalid-key")
    voice = VoiceConfig(provider="cartesia", voice_id="v1", language="en")

    with pytest.raises(RuntimeError, match="Cartesia authentication failed"):
        await tts.synthesize(text="Hello", voice=voice)


@pytest.mark.asyncio
async def test_cartesia_tts_handles_429_rate_limit(monkeypatch):
    async def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(429, text="Rate limit exceeded", request=request)
        raise httpx.HTTPStatusError("Rate limit", request=request, response=response)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    tts = CartesiaTTS(api_key="rate-limited-key")
    voice = VoiceConfig(provider="cartesia", voice_id="v1", language="en")

    with pytest.raises(RuntimeError, match="Cartesia rate limit reached"):
        await tts.synthesize(text="Hello", voice=voice)


@pytest.mark.asyncio
async def test_cartesia_tts_handles_timeout(monkeypatch):
    async def mock_post(self, url, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    tts = CartesiaTTS(api_key="timeout-key")
    voice = VoiceConfig(provider="cartesia", voice_id="v1", language="en")

    with pytest.raises(RuntimeError, match="Cartesia TTS synthesis request timed out"):
        await tts.synthesize(text="Hello", voice=voice)


def test_provider_selection_mock_vs_cartesia(monkeypatch):
    from app.conversation_engine import get_tts_provider

    # 1. When TTS_PROVIDER=mock
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(tts_provider="mock", cartesia_api_key=""))
    provider = get_tts_provider()
    assert isinstance(provider, MockTTS)

    # 2. When TTS_PROVIDER=cartesia and CARTESIA_API_KEY present
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(tts_provider="cartesia", cartesia_api_key="test-api-key"),
    )
    provider = get_tts_provider()
    assert isinstance(provider, CartesiaTTS)
    assert provider.api_key == "test-api-key"


@pytest.mark.asyncio
async def test_cartesia_tts_stop_session():
    tts = CartesiaTTS(api_key="test-key")
    await tts.stop(session_id="call-123")
    assert "call-123" in tts._stopped_sessions
