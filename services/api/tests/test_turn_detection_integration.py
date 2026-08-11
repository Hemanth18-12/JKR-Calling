"""P4 end-to-end proof: TURN_DETECTION_MODE=hybrid actually coalesces two
separate Sarvam finals (a thinking-pause split, spec §58/§113) into exactly
ONE ConversationEngine invocation over the real WebSocket -> MediaSession ->
TurnManager -> engine pipeline — only the Sarvam WebSocket itself is faked
(network boundary), same established pattern as
test_streaming_stt_integration.py's P3 proof. A second test confirms
TURN_DETECTION_MODE=provider (the default) is unaffected — the exact
byte-behavior-identical backward-compatibility guarantee this phase depends
on.
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

_FIRST_FRAGMENT = "Tomorrow but"
_SECOND_FRAGMENT = "actually evening better"
_COALESCED_TEXT = f"{_FIRST_FRAGMENT} {_SECOND_FRAGMENT}"


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
class _FakeStreamingSTTTwoFragments:
    """Emits TWO separate finals with a short real-time gap between them —
    simulating exactly the "Tomorrow... actually evening better" thinking-
    pause scenario spec §58 requires TurnManager to coalesce into one
    logical turn."""

    api_key: str
    config: object
    _sent_frames: int = 0

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
        while self._sent_frames < 5:  # noqa: ASYNC110 — test double, see test_streaming_stt_integration.py's identical pattern
            await asyncio.sleep(0.01)
        yield FinalTranscript(
            utterance_idx=0, text=_FIRST_FRAGMENT, detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        await asyncio.sleep(0.2)  # well within FAST profile's fragment_coalesce_ms (900ms)
        yield FinalTranscript(
            utterance_idx=1, text=_SECOND_FRAGMENT, detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        while True:  # noqa: ASYNC110 — stays "connected" until cancelled by session.close()
            await asyncio.sleep(3600)


@dataclass
class _FakeStreamingSTTSingleFinal:
    """Emits one final — used for the provider-mode backward-compat check."""

    api_key: str
    config: object
    _sent_frames: int = 0

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
        while self._sent_frames < 5:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        yield FinalTranscript(
            utterance_idx=0, text="Tomorrow evening.", detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        while True:  # noqa: ASYNC110
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
        org = Organization(name="Turn Detection Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Turn Detection Test WS", slug=f"turn-detect-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="Turn Detect Test Agent", business_identity="Aaha Dental Care", primary_language="en-IN", status="active")
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="qualify_and_route", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Hello, can we talk?", closing_text="Thank you.",
            supported_languages=["en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="dialing",
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"turn-detect-test-{uuid.uuid4()}",
            language="en-IN", state={"objective": "qualify_and_route", "known_fields": {}}, started_at=datetime.now(UTC),
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
        "closing_text": "Thank you.", "language_code": "en-IN", "business_identity": "Aaha Dental Care",
        "policy": {}, "tts_speaker": None, "greeted": False,
        "recent_turns": [{"speaker": "agent", "text": "Hello, can we talk?"}],
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


def test_hybrid_mode_coalesces_thinking_pause_into_one_engine_invocation(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeStreamingSTTTwoFragments)
    monkeypatch.setattr("app.modules.live_call.transport.transitional_bridge.SarvamTTS", _FakeTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    monkeypatch.setenv("TURN_DETECTION_MODE", "hybrid")
    monkeypatch.setenv("TURN_PROFILE", "fast")
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        assert settings.effective_turn_detection_mode == "hybrid"
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_HYBRID", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        received_media_messages = []
        reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_HYBRID", call_sid="CA_TEST_HYBRID"))

            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    break

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_HYBRID", speech_frames=10, silence_frames=5):
                ws.send_json(event)

            # Give the fake STT time to emit both fragments and TurnManager
            # time to coalesce + commit (FAST profile's ceiling is a
            # couple hundred ms past the second fragment) before expecting
            # the reply — drain until the reply's media frame arrives.
            for _ in range(400):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_HYBRID", call_sid="CA_TEST_HYBRID"))

        assert reply_seen, "never received a reply to the coalesced turn"

        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        customer_turns = [t for t in turns if t.speaker == "customer"]
        # The direct proof: TWO Sarvam finals produced exactly ONE customer
        # CallTurn, with the coalesced text — not two separate engine calls.
        assert len(customer_turns) == 1, f"expected exactly one coalesced customer turn, got {len(customer_turns)}: {[t.text for t in customer_turns]}"
        assert customer_turns[0].text == _COALESCED_TEXT
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()


def test_provider_mode_default_is_unaffected_by_p4(monkeypatch):
    """TURN_DETECTION_MODE unset -> "provider" -> byte-behavior-identical
    to pre-P4: a single final commits immediately, same as P3."""
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeStreamingSTTSingleFinal)
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
        assert settings.effective_turn_detection_mode == "provider"
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_PROVIDER", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        received_media_messages = []
        reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_PROVIDER", call_sid="CA_TEST_PROVIDER"))

            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    break

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_PROVIDER", speech_frames=10, silence_frames=5):
                ws.send_json(event)

            for _ in range(200):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_PROVIDER", call_sid="CA_TEST_PROVIDER"))

        assert reply_seen

        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        customer_turns = [t for t in turns if t.speaker == "customer"]
        assert len(customer_turns) == 1
        assert customer_turns[0].text == "Tomorrow evening."
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()
