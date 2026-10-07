"""Tests for CartesiaTTS in services/api."""

from __future__ import annotations

import httpx
import pytest

from jkr_db.enums import ProviderName
from jkr_db.models.agents import VoicePersona
from app.config import Settings
from app.live_providers.cartesia_tts import CartesiaTTS, NotConfiguredError
from app.modules.live_call import service


def test_cartesia_tts_not_configured_when_no_key(monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(NotConfiguredError, match="Neither CARTESIA_API_KEY nor OPENAI_API_KEY is set"):
        CartesiaTTS(api_key="")


def test_cartesia_tts_constructs_with_explicit_key():
    tts = CartesiaTTS(api_key="cartesia-test-key", model="sonic-3.6", pace=1.2, speaker="my-voice")
    assert tts._api_key == "cartesia-test-key"
    assert tts._model == "sonic-3.6"
    assert tts._pace == 1.2
    assert tts._speaker == "my-voice"


@pytest.mark.asyncio
async def test_cartesia_tts_synthesize_sends_correct_parameters_and_returns_wav(monkeypatch):
    captured_request = {}
    fake_wav_bytes = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 8000

    class _FakeClient:
        async def post(self, url, headers=None, json=None, timeout=None):
            captured_request["url"] = str(url)
            captured_request["headers"] = headers
            captured_request["json"] = json
            req = httpx.Request("POST", url)
            return httpx.Response(200, content=fake_wav_bytes, request=req)

    monkeypatch.setattr("app.live_providers.cartesia_tts.get_shared_http_client", lambda: _FakeClient())

    tts = CartesiaTTS(api_key="secret-cartesia-key", model="sonic-3.6", speaker="skylar-voice", pace=1.1)
    result = await tts.synthesize(text="Hello world", language_code="te-IN")

    assert result == fake_wav_bytes
    assert captured_request["headers"]["X-API-Key"] == "secret-cartesia-key"
    assert captured_request["headers"]["Cartesia-Version"] == "2024-11-13"
    assert captured_request["json"]["model_id"] == "sonic-3.6"
    assert captured_request["json"]["transcript"] == "Hello world"
    assert captured_request["json"]["voice"]["id"] == "skylar-voice"
    assert captured_request["json"]["output_format"]["container"] == "wav"
    assert captured_request["json"]["output_format"]["encoding"] == "pcm_s16le"
    assert captured_request["json"]["output_format"]["sample_rate"] == 8000
    assert captured_request["json"]["language"] == "te"
    assert captured_request["json"]["generation_config"]["speed"] == 1.1


@pytest.mark.asyncio
async def test_cartesia_tts_falls_back_to_openai_on_cartesia_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai_wav = b"RIFF" + b"\x00" * 36 + b"data-from-openai"

    class _FailingCartesiaClient:
        async def post(self, url, headers=None, json=None, timeout=None):
            req = httpx.Request("POST", url)
            if "cartesia" in str(url):
                res = httpx.Response(500, text="Cartesia Internal Error", request=req)
                raise httpx.HTTPStatusError("Server error", request=req, response=res)
            return httpx.Response(200, content=fake_openai_wav, request=req)

    monkeypatch.setattr("app.live_providers.cartesia_tts.get_shared_http_client", lambda: _FailingCartesiaClient())

    tts = CartesiaTTS(api_key="test-key")
    result = await tts.synthesize(text="Hello fallback", language_code="en-IN")
    assert result == fake_openai_wav


@pytest.mark.asyncio
async def test_cartesia_tts_raises_when_both_cartesia_and_fallback_fail(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class _AlwaysFailingClient:
        async def post(self, url, headers=None, json=None, timeout=None):
            req = httpx.Request("POST", url)
            res = httpx.Response(500, text="Cartesia Internal Error", request=req)
            raise httpx.HTTPStatusError("Server error", request=req, response=res)

    monkeypatch.setattr("app.live_providers.cartesia_tts.get_shared_http_client", lambda: _AlwaysFailingClient())

    tts = CartesiaTTS(api_key="test-key")
    with pytest.raises(RuntimeError, match="Both Cartesia TTS and OpenAI TTS fallback failed"):
        await tts.synthesize(text="Hello fail", language_code="en")


def test_resolve_tts_speaker_supports_cartesia():
    voice = VoicePersona(provider=ProviderName.CARTESIA, voice_id="skylar-cartesia-id")
    assert service._resolve_tts_speaker(voice) == "skylar-cartesia-id"


def test_resolve_tts_pace_supports_cartesia():
    voice = VoicePersona(provider=ProviderName.CARTESIA, voice_id="skylar-cartesia-id", speaking_speed=1.4)
    assert service._resolve_tts_pace(voice) == 1.4


class _FakeRedis:
    async def set(self, *args, **kwargs):
        pass


class _CapturingCartesiaTTS:
    captured_kwargs: dict = {}

    def __init__(self, **kwargs):
        _CapturingCartesiaTTS.captured_kwargs = kwargs

    async def synthesize(self, *, text, language_code):
        return b"fake-cartesia-wav"


@pytest.mark.asyncio
async def test_speak_uses_cartesia_tts_when_configured(monkeypatch):
    monkeypatch.setattr(service, "CartesiaTTS", _CapturingCartesiaTTS)
    settings = Settings(cartesia_api_key="my-cartesia-key", tts_provider="cartesia")

    kind, _content = await service._speak(
        "hello cartesia",
        language_code="te-IN",
        settings=settings,
        redis=_FakeRedis(),
        speaker="custom-cartesia-voice",
        pace=1.3,
    )

    assert kind == "play"
    assert _CapturingCartesiaTTS.captured_kwargs.get("speaker") == "custom-cartesia-voice"
    assert _CapturingCartesiaTTS.captured_kwargs.get("pace") == 1.3
    assert _CapturingCartesiaTTS.captured_kwargs.get("api_key") == "my-cartesia-key"
