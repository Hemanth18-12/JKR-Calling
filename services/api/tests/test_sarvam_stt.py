"""Confirms the STT-config fix for bugs 2/3 (domain mis-transcription +
language auto-detect instability): language_code is a required, pinned
argument (no more silent "unknown" default a call site could regress to),
mode defaults to "codemix", and the model is saaras:v4 — all asserted
against what's actually sent over the wire, not just the client's own
return value.
"""

from __future__ import annotations

import pytest
from app.live_providers.sarvam_stt import NotConfiguredError, SarvamSTT, SttTranscript


class _FakeResponse:
    def __init__(self, json_data: dict):
        self._json_data = json_data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json_data


class _FakeAsyncClient:
    """P3.5 §34: production code now calls get_shared_http_client().post(...)
    directly (no `async with` context manager) — reusing one process-
    lifetime client instead of opening a new one per call. This fake mirrors
    that shape, not the old per-call `async with httpx.AsyncClient()`."""

    captured_calls: list[dict] = []

    async def post(self, url, *, headers, data, files):
        _FakeAsyncClient.captured_calls.append({"url": url, "headers": headers, "data": data, "files": files})
        return _FakeResponse({"transcript": "  root canal treatment  ", "language_code": "te-IN", "language_probability": 0.97})


@pytest.fixture(autouse=True)
def _reset_captured_calls():
    _FakeAsyncClient.captured_calls = []
    yield


async def test_transcribe_pins_requested_language_code_and_defaults_to_codemix(monkeypatch):
    monkeypatch.setattr("app.live_providers.sarvam_stt.get_shared_http_client", lambda: _FakeAsyncClient())
    stt = SarvamSTT(api_key="fake-key")

    result = await stt.transcribe(audio_bytes=b"fake-audio-bytes", language_code="te-IN")

    assert isinstance(result, SttTranscript)
    assert result.text == "root canal treatment"  # whitespace stripped
    assert result.detected_language_code == "te-IN"
    assert result.language_probability == 0.97

    assert len(_FakeAsyncClient.captured_calls) == 1
    call = _FakeAsyncClient.captured_calls[0]
    assert call["data"]["language_code"] == "te-IN"  # pinned — never "unknown"
    assert call["data"]["mode"] == "codemix"
    assert call["data"]["model"] == "saaras:v4"


async def test_transcribe_language_code_is_required(monkeypatch):
    monkeypatch.setattr("app.live_providers.sarvam_stt.get_shared_http_client", lambda: _FakeAsyncClient())
    stt = SarvamSTT(api_key="fake-key")
    with pytest.raises(TypeError):
        await stt.transcribe(audio_bytes=b"fake-audio-bytes")  # type: ignore[call-arg]


async def test_transcribe_mode_can_be_overridden(monkeypatch):
    monkeypatch.setattr("app.live_providers.sarvam_stt.get_shared_http_client", lambda: _FakeAsyncClient())
    stt = SarvamSTT(api_key="fake-key")
    await stt.transcribe(audio_bytes=b"fake-audio-bytes", language_code="hi-IN", mode="translate")
    assert _FakeAsyncClient.captured_calls[0]["data"]["mode"] == "translate"


def test_missing_api_key_raises_not_configured():
    with pytest.raises(NotConfiguredError):
        SarvamSTT(api_key="")


async def test_raw_response_is_preserved_for_debugging(monkeypatch):
    monkeypatch.setattr("app.live_providers.sarvam_stt.get_shared_http_client", lambda: _FakeAsyncClient())
    stt = SarvamSTT(api_key="fake-key")
    result = await stt.transcribe(audio_bytes=b"fake-audio-bytes", language_code="en-IN")
    assert result.raw_response["language_code"] == "te-IN"
