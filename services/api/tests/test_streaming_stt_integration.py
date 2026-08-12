"""End-to-end proof STT_MODE=streaming actually wires together: a real
WebSocket connection (FastAPI TestClient), a real Postgres CallSession, a
real Redis-backed state blob, and the real, unmodified jkr_conversation
ConversationEngine via streaming_bridge.py's
process_known_transcript_turn() call — only the Sarvam Realtime STT
WebSocket itself is faked (network boundary), same pattern as
test_twilio_media_stream_integration.py's batch-mode proof. This is the
test that would catch a regression where STT_MODE=streaming stopped
actually reaching the real engine, or reached it more than once per
utterance, or fed it an empty/duplicate transcript.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")
os.environ.setdefault("REDIS_URL", "redis://localhost:16379/0")

from app.config import get_settings  # noqa: E402
from app.live_providers.streaming_stt import FinalTranscript, STTSessionStarted  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.live_call.service import REDIS_TTL_SECONDS, _redis_key  # noqa: E402
from app.modules.live_call.transport import streaming_bridge  # noqa: E402
from app.modules.live_call.transport.media_tokens import create_media_session_token  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_FAKE_TRANSCRIPT_TEXT = "root canal గురించి అడుగుతున్నాను"


def _load_simulator():
    import importlib.util

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    path = os.path.join(repo_root, "tests", "tools", "twilio_media_simulator.py")
    spec = importlib.util.spec_from_file_location("twilio_media_simulator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_simulator = _load_simulator()
build_connected_event = _simulator.build_connected_event
build_speech_and_silence_sequence = _simulator.build_speech_and_silence_sequence
build_start_event = _simulator.build_start_event
build_stop_event = _simulator.build_stop_event


class _FakeTTS:
    def __init__(self, *, api_key: str, **kwargs):
        pass

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        import io
        import wave

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(8000)
            wav_file.writeframes(b"\x00\x01" * 400)
        return buffer.getvalue()


@dataclass
class _FakeStreamingSTT:
    """Stands in for the real Sarvam WebSocket: connect()/send_audio() are
    no-ops beyond bookkeeping, and events() yields a scripted
    STTSessionStarted followed by one FinalTranscript once enough audio
    frames have actually been forwarded through _forward_audio_to_stt —
    proving the real audio path (Twilio media event -> AudioFrame ->
    session.inbound_audio_queue -> send_audio()) is what drives it, not a
    canned timer."""

    api_key: str
    config: object
    _sent_frames: int = 0
    _emitted_final: bool = False

    async def connect(self) -> None:
        return None

    async def send_audio(self, pcm16_bytes: bytes) -> None:
        self._sent_frames += 1

    async def flush(self) -> None:
        return None

    async def reconfigure(self, **kwargs: object) -> None:
        return None

    async def close(self) -> None:
        return None

    async def events(self):
        yield STTSessionStarted(request_id="fake-req-1", raw={})
        while self._sent_frames < 5:  # noqa: ASYNC110 — test double; a real Event would need send_audio() to signal it, more machinery than this fake needs
            await asyncio.sleep(0.01)
        yield FinalTranscript(
            utterance_idx=0, text=_FAKE_TRANSCRIPT_TEXT, detected_language_code="te-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        while True:  # noqa: ASYNC110 — stays "connected" until the surrounding task is cancelled by session.close()
            await asyncio.sleep(3600)


@pytest.fixture(autouse=True)
def _fresh_engine_per_test():
    _reset_db_engine()
    yield
    _reset_db_engine()


async def _seed_call() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    from jkr_db.models.agents import Agent, AgentVersion
    from jkr_db.models.calls import CallSession
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Streaming STT Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Streaming STT Test WS", slug=f"streaming-stt-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="Streaming Test Agent", business_identity="Aaha Dental Care", primary_language="te-en-IN", status="active")
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="qualify_and_route", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Namaskaram, can we talk?", closing_text="Thank you.",
            supported_languages=["te-en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="dialing",
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"streaming-stt-test-{uuid.uuid4()}",
            language="te-en-IN", state={"objective": "qualify_and_route", "known_fields": {}}, started_at=datetime.now(UTC),
            is_mock=False, disclosure_confirmed=True,
        )
        db.add(call_session)
        await db.flush()
        call_session_id = call_session.id

    return workspace_id, call_session_id, agent.id


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in (
            "call_latency_metrics", "call_events", "call_turns", "call_transcripts", "call_outcomes",
            "call_summaries", "usage_events", "call_sessions", "agent_versions",
        ):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


def _reset_db_engine() -> None:
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None

    from jkr_messaging import get_redis

    get_redis.cache_clear()


async def _seed_and_cache_redis_state(workspace_id: uuid.UUID, call_session_id: uuid.UUID) -> str:
    from jkr_messaging import get_redis

    redis = get_redis()
    redis_state_token = uuid.uuid4().hex
    redis_state: dict = {
        "workspace_id": str(workspace_id), "call_session_id": str(call_session_id),
        "closing_text": "Thank you.", "language_code": "te-IN", "business_identity": "Aaha Dental Care",
        "policy": {}, "tts_speaker": None, "greeted": False,
        "recent_turns": [{"speaker": "agent", "text": "Namaskaram, can we talk?"}],
        "agent_turns": 1, "next_sequence_index": 0,
    }
    await redis.set(_redis_key(redis_state_token), json.dumps(redis_state), ex=REDIS_TTL_SECONDS)
    return redis_state_token


async def _fetch_call_turns(workspace_id: uuid.UUID, call_session_id: uuid.UUID) -> list:
    from jkr_db.models.calls import CallTurn
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(CallTurn).where(CallTurn.call_session_id == call_session_id).order_by(CallTurn.sequence_index))
        return list(result.scalars().all())


async def _delete_redis_key(redis_state_token: str) -> None:
    from jkr_messaging import get_redis

    await get_redis().delete(_redis_key(redis_state_token))


def test_streaming_stt_round_trip_reaches_real_engine_exactly_once(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeStreamingSTT)
    monkeypatch.setattr("app.modules.live_call.transport.transitional_bridge.SarvamTTS", _FakeTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        assert settings.effective_stt_mode == "streaming"
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_STREAM", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        received_media_messages = []
        reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_STREAM", call_sid="CA_TEST_STREAM"))

            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    break

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_STREAM", speech_frames=10, silence_frames=5):
                ws.send_json(event)

            for _ in range(200):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_STREAM", call_sid="CA_TEST_STREAM"))

        assert len(received_media_messages) >= 1, "never received the greeting over the WebSocket"
        assert reply_seen, "never received a reply to the simulated customer speech"

        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        customer_turns = [t for t in turns if t.speaker == "customer"]
        # Exactly one customer turn for the one FinalTranscript the fake
        # provider emitted — the direct proof no per-utterance duplication
        # happened between the STT event and the engine call.
        assert len(customer_turns) == 1
        assert customer_turns[0].text == _FAKE_TRANSCRIPT_TEXT
        assert any(t.speaker == "agent" for t in turns)
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()


def test_streaming_stt_falls_back_to_batch_on_connect_failure_with_batch_next_turn_policy(monkeypatch):
    """Proves STT_STREAM_FAILURE_POLICY=batch_next_turn actually keeps the
    call alive on the proven batch path rather than dropping the customer
    — the direct requirement from the P3 spec's "keep batch STT as an
    explicit fallback" instruction."""
    from app.modules.live_call.transport import transitional_bridge

    class _AlwaysFailsToConnect:
        def __init__(self, *, api_key, config):
            pass

        async def connect(self):
            raise ConnectionRefusedError("simulated: Sarvam Realtime API refused this connection")

    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _AlwaysFailsToConnect)
    monkeypatch.setattr(streaming_bridge, "_RECONNECT_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(transitional_bridge, "SarvamSTT", lambda **kw: _FakeBatchSTT())
    monkeypatch.setattr(transitional_bridge, "SarvamTTS", _FakeTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    monkeypatch.setenv("STT_STREAM_FAILURE_POLICY", "batch_next_turn")
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_FALLBACK", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        received_media_messages = []
        reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_FALLBACK", call_sid="CA_TEST_FALLBACK"))

            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    break

            # Streaming connect() fails and exhausts reconnects almost
            # immediately (0s backoff); the call should still be alive on
            # the batch fallback path, so the SAME speech-then-silence
            # sequence a batch-mode call would need still produces a reply.
            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_FALLBACK"):
                ws.send_json(event)

            for _ in range(300):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_FALLBACK", call_sid="CA_TEST_FALLBACK"))

        assert reply_seen, "batch fallback never produced a reply after the streaming connection was refused"
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()


@dataclass
class _FakeBatchTranscript:
    text: str
    detected_language_code: str | None = "te-IN"
    language_probability: float | None = 0.9


class _FakeBatchSTT:
    async def transcribe(self, *, audio_bytes: bytes, language_code: str):
        return _FakeBatchTranscript(text=_FAKE_TRANSCRIPT_TEXT)


class _FakeFatalErrorSTT:
    """Real-incident regression: connect() succeeds (this is exactly what a
    real Sarvam quota_exceeded/402 looks like — the WebSocket handshake and
    auth succeed, then the provider sends a fatal `error` event and closes
    the connection the moment real audio arrives), but every generation
    immediately yields a fatal STTError and ends — reproducing an account
    whose credits are exhausted staying exhausted across every reconnect
    attempt, exactly as observed on the real call this test is named for."""

    def __init__(self, *, api_key, config):
        pass

    async def connect(self) -> None:
        return None

    async def send_audio(self, pcm16_bytes: bytes) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def reconfigure(self, **kwargs: object) -> None:
        return None

    async def close(self) -> None:
        return None

    async def events(self):
        from app.live_providers.streaming_stt import STTError

        yield STTError(code="quota_exceeded", message="Credits exhausted.", is_fatal=True, status_code=402, raw={})


async def _fetch_call_events(workspace_id: uuid.UUID, call_session_id: uuid.UUID) -> list:
    from jkr_db.models.calls import CallEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(CallEvent).where(CallEvent.call_session_id == call_session_id).order_by(CallEvent.created_at))
        return list(result.scalars().all())


def test_fatal_stt_error_and_give_up_are_persisted_as_call_events(monkeypatch):
    """The actual real-call forensics finding this fix closes: a fatal
    provider error (Sarvam quota_exceeded) previously left the DB with
    exactly zero evidence anything had gone wrong — CallTurn, CallEvent, and
    CallLatencyMetric all stayed empty for the entire rest of the call,
    making a real incident take a live out-of-band provider probe to
    diagnose instead of a two-second query. This proves both the fatal
    STTError itself and the eventual give-up are now durably queryable."""
    from app.modules.live_call.transport import transitional_bridge

    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeFatalErrorSTT)
    monkeypatch.setattr(streaming_bridge, "_RECONNECT_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(transitional_bridge, "SarvamTTS", _FakeTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    monkeypatch.setenv("STT_STREAM_FAILURE_POLICY", "fail")  # the actual default — no batch fallback
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_FATAL", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_FATAL", call_sid="CA_TEST_FATAL"))

            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    break

            # The server-side WebSocket closes itself once give-up calls
            # session.close(failed=True) — no need to send a stop event.
            for _ in range(500):
                try:
                    ws.receive_json()
                except Exception:
                    break

        _reset_db_engine()
        events = asyncio.run(_fetch_call_events(workspace_id, call_session_id))
        event_types = [e.event_type for e in events]

        assert "stt_stream_fatal_error" in event_types
        fatal_event = next(e for e in events if e.event_type == "stt_stream_fatal_error")
        assert fatal_event.payload["code"] == "quota_exceeded"
        assert fatal_event.payload["status_code"] == 402

        assert "stt_stream_gave_up" in event_types
        gave_up_event = next(e for e in events if e.event_type == "stt_stream_gave_up")
        assert gave_up_event.payload["failure_policy"] == "fail"
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()
