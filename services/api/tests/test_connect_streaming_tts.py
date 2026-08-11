"""_connect_streaming_tts() — spec §17: VoicePersona must remain
authoritative for the live streaming voice, exactly as it already is for
the batch path (service.py's _resolve_tts_speaker). Confirms the resolved
tts_speaker actually reaches StreamingTTSConfig.voice_id, and that a
connect failure degrades gracefully (session.tts_streaming_session stays
None) rather than raising into call setup.
"""

from __future__ import annotations

import uuid

from app.config import Settings
from app.live_providers.streaming_tts import StreamingTTSConfig, TTSCallContext
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.twilio_media_stream import _connect_streaming_tts


class _FakeProvider:
    def __init__(self, *, api_key):
        self.api_key = api_key

    async def connect(self, *, config, context):
        pass

    async def close(self):
        pass

    async def events(self):
        return
        yield  # pragma: no cover — never reached, makes this a generator


def _session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def test_voice_persona_speaker_reaches_streaming_tts_config(monkeypatch):
    captured: dict = {}

    class _CapturingProvider(_FakeProvider):
        async def connect(self, *, config: StreamingTTSConfig, context: TTSCallContext):
            captured["config"] = config
            captured["context"] = context

    import app.live_providers.sarvam_streaming_tts as sarvam_mod

    monkeypatch.setattr(sarvam_mod, "SarvamStreamingTTS", _CapturingProvider)

    session = _session()
    await _connect_streaming_tts(session, language_code="te-IN", tts_speaker="priya", tts_pace=1.3, settings=Settings(sarvam_tts_api_key="k"))

    assert session.tts_streaming_session is not None
    assert session.pipeline_coordinator is not None
    assert captured["config"].voice_id == "priya"
    assert captured["config"].target_language_code == "te-IN"
    assert captured["config"].pace == 1.3


async def test_no_voice_persona_configured_leaves_voice_id_none(monkeypatch):
    captured: dict = {}

    class _CapturingProvider(_FakeProvider):
        async def connect(self, *, config, context):
            captured["config"] = config

    import app.live_providers.sarvam_streaming_tts as sarvam_mod

    monkeypatch.setattr(sarvam_mod, "SarvamStreamingTTS", _CapturingProvider)

    session = _session()
    await _connect_streaming_tts(session, language_code="en-IN", tts_speaker=None, tts_pace=1.0, settings=Settings(sarvam_tts_api_key="k"))

    assert captured["config"].voice_id is None


async def test_connect_failure_degrades_gracefully_leaves_session_none(monkeypatch):
    class _FailingProvider(_FakeProvider):
        async def connect(self, *, config, context):
            raise RuntimeError("connection refused")

    import app.live_providers.sarvam_streaming_tts as sarvam_mod

    monkeypatch.setattr(sarvam_mod, "SarvamStreamingTTS", _FailingProvider)

    session = _session()
    await _connect_streaming_tts(session, language_code="en-IN", tts_speaker=None, tts_pace=1.0, settings=Settings(sarvam_tts_api_key="k"))

    assert session.tts_streaming_session is None  # falls back to batch for the whole call, never raises
    assert session.pipeline_coordinator is None  # never created without a live TTS connection
