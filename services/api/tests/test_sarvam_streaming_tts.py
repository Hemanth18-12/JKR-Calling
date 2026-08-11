from __future__ import annotations

import base64
import json

import pytest
from app.live_providers.sarvam_streaming_tts import (
    CAPABILITIES,
    NotConfiguredError,
    SarvamStreamingTTS,
    SarvamStreamingTTSError,
    _classify_error,
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


def _sent(fake: _FakeWSConnection) -> list[dict]:
    return [json.loads(m) for m in fake.sent_messages]


def _audio_msg(*, audio_bytes: bytes = b"\xff\xff\xfe\xfe") -> str:
    return json.dumps({"type": "audio", "data": {"content_type": "audio/mulaw", "audio": base64.b64encode(audio_bytes).decode("ascii")}})


def _final_msg() -> str:
    return json.dumps({"type": "event", "data": {"event_type": "final"}})


async def _fake_connect_returning(fake: _FakeWSConnection, monkeypatch):
    async def fake_connect(url, **kwargs):
        return fake

    import app.live_providers.sarvam_streaming_tts as mod

    monkeypatch.setattr(mod.websockets, "connect", fake_connect)


# --- construction / guard rails ------------------------------------------


def test_requires_api_key():
    with pytest.raises(NotConfiguredError):
        SarvamStreamingTTS(api_key="")


def test_capabilities_reflect_verified_sarvam_contract():
    tts = SarvamStreamingTTS(api_key="k")
    assert tts.capabilities == CAPABILITIES
    assert CAPABILITIES.supports_direct_mulaw_8k is True  # verified live — see contract doc
    assert CAPABILITIES.supports_live_reconfiguration is False  # not verified this pass


async def test_send_text_before_connect_raises():
    tts = SarvamStreamingTTS(api_key="k")
    with pytest.raises(SarvamStreamingTTSError):
        await tts.send_text(text="hi", response_id="r1", chunk_index=0)


async def test_flush_before_connect_raises():
    tts = SarvamStreamingTTS(api_key="k")
    with pytest.raises(SarvamStreamingTTSError):
        await tts.flush(response_id="r1")


# --- connect() wire format -------------------------------------------------


async def test_connect_sends_config_with_mulaw_8k_and_pace(monkeypatch):
    fake = _FakeWSConnection()
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="secret")
    await tts.connect(
        config=StreamingTTSConfig(target_language_code="te-IN", voice_id="priya", pace=1.2),
        context=TTSCallContext(call_session_id="c1", workspace_id="w1"),
    )

    msg = _sent(fake)[0]
    assert msg["type"] == "config"
    assert msg["data"]["language_code"] == "te-IN"
    assert msg["data"]["speaker"] == "priya"
    assert msg["data"]["pace"] == 1.2
    assert msg["data"]["output_audio_codec"] == "mulaw"
    assert msg["data"]["speech_sample_rate"] == "8000"


async def test_connect_omits_speaker_when_voice_id_not_given(monkeypatch):
    fake = _FakeWSConnection()
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="secret")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))

    msg = _sent(fake)[0]
    assert "speaker" not in msg["data"]  # None means "provider's own default", same policy as SarvamTTS


# --- send_text / flush wire format -----------------------------------------


async def test_send_text_and_flush_wire_format(monkeypatch):
    fake = _FakeWSConnection()
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.send_text(text="Hello there.", response_id="resp_1", chunk_index=0)
    await tts.flush(response_id="resp_1")

    sent = _sent(fake)
    assert sent[1] == {"type": "text", "data": {"text": "Hello there."}}
    assert sent[2] == {"type": "flush"}


# --- events() / audio+completion parsing -----------------------------------


async def test_first_audio_chunk_emits_ttsfirstaudio_then_chunk(monkeypatch):
    fake = _FakeWSConnection(incoming=[_audio_msg(audio_bytes=b"\x01\x02"), _final_msg()])
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.send_text(text="hi", response_id="resp_1", chunk_index=0)

    events = [e async for e in tts.events()]
    assert isinstance(events[0], TTSFirstAudio)
    assert events[0].response_id == "resp_1"
    assert isinstance(events[1], TTSAudioChunk)
    assert events[1].data == b"\x01\x02"
    assert events[1].audio_chunk_index == 0
    assert events[1].codec == "mulaw"
    assert events[1].sample_rate == 8000
    assert isinstance(events[2], TTSGenerationCompleted)
    assert events[2].response_id == "resp_1"


async def test_second_audio_chunk_does_not_repeat_first_audio_event(monkeypatch):
    fake = _FakeWSConnection(incoming=[_audio_msg(), _audio_msg(), _final_msg()])
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.send_text(text="hi", response_id="resp_1", chunk_index=0)

    events = [e async for e in tts.events()]
    first_audio_events = [e for e in events if isinstance(e, TTSFirstAudio)]
    audio_chunks = [e for e in events if isinstance(e, TTSAudioChunk)]
    assert len(first_audio_events) == 1
    assert [c.audio_chunk_index for c in audio_chunks] == [0, 1]


async def test_two_responses_on_same_connection_each_get_their_own_first_audio(monkeypatch):
    """Realistic usage (matches tts_bridge.py): the second response's text
    is only sent once the first response's own completion has already been
    observed — exactly how TTSResponseHandle.finish() awaits
    TTSGenerationCompleted before a turn loop starts the next response."""
    fake = _FakeWSConnection(incoming=[_audio_msg(), _final_msg(), _audio_msg(), _final_msg()])
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    event_iter = tts.events()

    await tts.send_text(text="one", response_id="resp_1", chunk_index=0)
    await tts.flush(response_id="resp_1")
    first_audio_1 = await anext(event_iter)
    chunk_1 = await anext(event_iter)
    completed_1 = await anext(event_iter)
    assert isinstance(first_audio_1, TTSFirstAudio) and first_audio_1.response_id == "resp_1"
    assert isinstance(chunk_1, TTSAudioChunk) and chunk_1.response_id == "resp_1"
    assert isinstance(completed_1, TTSGenerationCompleted) and completed_1.response_id == "resp_1"

    await tts.send_text(text="two", response_id="resp_2", chunk_index=0)
    await tts.flush(response_id="resp_2")
    first_audio_2 = await anext(event_iter)
    chunk_2 = await anext(event_iter)
    completed_2 = await anext(event_iter)
    assert isinstance(first_audio_2, TTSFirstAudio) and first_audio_2.response_id == "resp_2"
    assert isinstance(chunk_2, TTSAudioChunk) and chunk_2.response_id == "resp_2"
    assert isinstance(completed_2, TTSGenerationCompleted) and completed_2.response_id == "resp_2"


# --- cancellation (local-only) ---------------------------------------------


async def test_cancel_drops_subsequent_audio_for_that_response(monkeypatch):
    fake = _FakeWSConnection(incoming=[_audio_msg(), _final_msg()])
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.send_text(text="hi", response_id="resp_1", chunk_index=0)
    await tts.cancel("resp_1")

    events = [e async for e in tts.events()]
    assert not any(isinstance(e, (TTSAudioChunk, TTSFirstAudio)) for e in events)
    assert isinstance(events[-1], TTSStreamCancelled)
    assert events[-1].response_id == "resp_1"


# --- error classification ---------------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("401: unauthorized", TTSFailureClass.AUTH_ERROR),
        ("403: forbidden", TTSFailureClass.AUTH_ERROR),
        ("429: too many requests", TTSFailureClass.RATE_LIMIT),
        ("500: internal error", TTSFailureClass.PROVIDER_INTERNAL),
        ("400: Speaker 'x' is not recognized", TTSFailureClass.INVALID_REQUEST),
        ("something with no code prefix at all", TTSFailureClass.UNKNOWN),
    ],
)
def test_classify_error(message, expected):
    assert _classify_error(message, status_code=None) == expected


async def test_error_message_yields_ttsstreamfailed(monkeypatch):
    fake = _FakeWSConnection(incoming=[
        json.dumps({"type": "error", "data": {"message": "400: Speaker 'nope' is not recognized"}}),
    ])
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.send_text(text="hi", response_id="resp_1", chunk_index=0)

    events = [e async for e in tts.events()]
    assert len(events) == 1
    assert isinstance(events[0], TTSStreamFailed)
    assert events[0].response_id == "resp_1"
    assert events[0].failure_class == TTSFailureClass.INVALID_REQUEST


async def test_close_is_idempotent(monkeypatch):
    fake = _FakeWSConnection()
    await _fake_connect_returning(fake, monkeypatch)

    tts = SarvamStreamingTTS(api_key="k")
    await tts.connect(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    await tts.close()
    assert fake.closed is True
    await tts.close()  # must not raise
