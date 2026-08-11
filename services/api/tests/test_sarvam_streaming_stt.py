from __future__ import annotations

import json

import pytest
from app.live_providers.sarvam_streaming_stt import (
    CAPABILITIES,
    REALTIME_STT_MODEL,
    NotConfiguredError,
    SarvamStreamingSTT,
    SarvamStreamingSTTError,
    _build_connect_url,
    _parse_event,
)
from app.live_providers.streaming_stt import (
    FinalTranscript,
    PartialTranscript,
    SpeechEnded,
    SpeechStarted,
    StreamingSTTConfig,
    STTError,
    STTReconfigured,
    STTSessionEnded,
    STTSessionStarted,
)


class _FakeWSConnection:
    def __init__(self, incoming: list[str] | None = None):
        self.sent_messages: list[str] = []
        self.closed = False
        self._incoming = list(incoming or [])

    async def send(self, message: str) -> None:
        if self.closed:
            raise RuntimeError("cannot send on a closed connection")
        self.sent_messages.append(message)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


def _sent_events(fake: _FakeWSConnection) -> list[dict]:
    return [json.loads(m) for m in fake.sent_messages]


# --- _build_connect_url --------------------------------------------------


def test_build_connect_url_includes_required_params_and_pinned_model():
    import urllib.parse

    config = StreamingSTTConfig(language_code="te-IN")
    url = _build_connect_url(config, ws_url="wss://api.sarvam.ai/speech-to-text-realtime/ws")
    assert url.startswith("wss://api.sarvam.ai/speech-to-text-realtime/ws?")
    base, _, query = url.partition("?")
    params = urllib.parse.parse_qs(query)
    assert params["language_code"] == ["te-IN"]
    assert params["model"] == [REALTIME_STT_MODEL]
    assert params["encoding"] == ["linear16"]
    assert params["sample_rate"] == ["8000"]


def test_build_connect_url_omits_prompt_when_not_set():
    config = StreamingSTTConfig(language_code="hi-IN")
    url = _build_connect_url(config, ws_url="wss://x/ws")
    assert "prompt=" not in url


def test_build_connect_url_includes_prompt_when_set():
    config = StreamingSTTConfig(language_code="hi-IN", prompt="dental clinic terminology")
    url = _build_connect_url(config, ws_url="wss://x/ws")
    assert "prompt=dental" in url


# --- _parse_event ----------------------------------------------------------


def test_parse_event_session_begin():
    event = _parse_event({"event": "session.begin", "request_id": "req-1"})
    assert isinstance(event, STTSessionStarted)
    assert event.request_id == "req-1"


def test_parse_event_session_end():
    event = _parse_event({
        "event": "session.end", "request_id": "req-1", "total_duration_s": 12.4,
        "total_utterances": 3, "audio_duration_s": 11.8,
    })
    assert isinstance(event, STTSessionEnded)
    assert event.audio_duration_s == 11.8
    assert event.total_utterances == 3


def test_parse_event_speech_start_and_end():
    start = _parse_event({"event": "vad.speech_start", "utterance_idx": 0, "confidence": 0.91})
    end = _parse_event({"event": "vad.speech_end", "utterance_idx": 0, "confidence": 0.88})
    assert isinstance(start, SpeechStarted)
    assert start.provider_confidence == 0.91
    assert isinstance(end, SpeechEnded)
    assert end.provider_confidence == 0.88


def test_parse_event_partial_transcript():
    event = _parse_event({"event": "transcript.partial", "utterance_idx": 0, "text": "root ca", "language": None})
    assert isinstance(event, PartialTranscript)
    assert event.text == "root ca"
    assert event.detected_language_code is None


def test_parse_event_final_transcript_never_manufactures_provider_confidence():
    event = _parse_event({
        "event": "transcript.final", "utterance_idx": 0, "text": " root canal ", "language": None,
        "language_confidence": None, "start_s": 0.0, "end_s": 2.3,
    })
    assert isinstance(event, FinalTranscript)
    assert event.text == "root canal"  # stripped
    assert event.provider_confidence is None  # Sarvam never emits this — must never be fabricated


def test_parse_event_error():
    event = _parse_event({"event": "error", "code": "invalid_config", "is_fatal": False, "message": "bad param", "status_code": 400})
    assert isinstance(event, STTError)
    assert event.is_fatal is False
    assert event.status_code == 400


def test_parse_event_config_update_ack():
    event = _parse_event({"event": "config.update.ack"})
    assert isinstance(event, STTReconfigured)


def test_parse_event_unrecognized_returns_none_not_a_crash():
    # forward-compatible, same policy as transport/schemas.py::parse_twilio_event
    assert _parse_event({"event": "some_future_event_type"}) is None


# --- SarvamStreamingSTT ------------------------------------------------


def test_requires_api_key():
    with pytest.raises(NotConfiguredError):
        SarvamStreamingSTT(api_key="", config=StreamingSTTConfig(language_code="en-IN"))


def test_capabilities_reflect_verified_sarvam_realtime_contract():
    stt = SarvamStreamingSTT(api_key="k", config=StreamingSTTConfig(language_code="en-IN"))
    assert stt.capabilities == CAPABILITIES
    assert CAPABILITIES.supports_partial_transcripts is True
    assert CAPABILITIES.supports_provider_confidence is False  # never emitted by this provider
    assert CAPABILITIES.supports_pronunciation_dictionary is False  # not found in the documented contract


async def test_send_audio_before_connect_raises():
    stt = SarvamStreamingSTT(api_key="k", config=StreamingSTTConfig(language_code="en-IN"))
    with pytest.raises(SarvamStreamingSTTError):
        await stt.send_audio(b"\x00\x00")


async def test_connect_sends_via_websockets_connect_and_send_audio_base64_encodes(monkeypatch):
    fake = _FakeWSConnection()
    captured_kwargs = {}

    async def fake_connect(url, **kwargs):
        captured_kwargs["url"] = url
        captured_kwargs.update(kwargs)
        return fake

    import app.live_providers.sarvam_streaming_stt as mod

    monkeypatch.setattr(mod.websockets, "connect", fake_connect)

    stt = SarvamStreamingSTT(api_key="secret-key", config=StreamingSTTConfig(language_code="te-IN"))
    await stt.connect()

    assert captured_kwargs["additional_headers"] == {"Api-Subscription-Key": "secret-key"}
    assert "language_code=te-IN" in captured_kwargs["url"]

    await stt.send_audio(b"\x01\x02\x03")
    sent = _sent_events(fake)
    assert sent[0]["event"] == "audio_input"
    import base64

    assert base64.b64decode(sent[0]["audio"]) == b"\x01\x02\x03"


async def test_close_sends_end_event_and_is_idempotent(monkeypatch):
    fake = _FakeWSConnection()

    async def fake_connect(url, **kwargs):
        return fake

    import app.live_providers.sarvam_streaming_stt as mod

    monkeypatch.setattr(mod.websockets, "connect", fake_connect)

    stt = SarvamStreamingSTT(api_key="k", config=StreamingSTTConfig(language_code="en-IN"))
    await stt.connect()
    await stt.close()
    assert fake.closed is True
    assert _sent_events(fake)[-1]["event"] == "end"

    # idempotent — a second close() must not raise or try to send again
    sent_count_before = len(fake.sent_messages)
    await stt.close()
    assert len(fake.sent_messages) == sent_count_before


async def test_events_yields_typed_events_and_skips_unparseable_messages(monkeypatch):
    fake = _FakeWSConnection(incoming=[
        json.dumps({"event": "session.begin", "request_id": "r1"}),
        "not json at all",
        json.dumps({"event": "transcript.final", "utterance_idx": 0, "text": "hello", "language": None, "language_confidence": None}),
    ])

    async def fake_connect(url, **kwargs):
        return fake

    import app.live_providers.sarvam_streaming_stt as mod

    monkeypatch.setattr(mod.websockets, "connect", fake_connect)

    stt = SarvamStreamingSTT(api_key="k", config=StreamingSTTConfig(language_code="en-IN"))
    await stt.connect()

    received = [event async for event in stt.events()]
    assert len(received) == 2  # the malformed message is silently skipped, never crashes the loop
    assert isinstance(received[0], STTSessionStarted)
    assert isinstance(received[1], FinalTranscript)
    assert received[1].text == "hello"
