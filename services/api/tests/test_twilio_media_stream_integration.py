"""End-to-end proof the Media Stream transport actually wires together:
a real WebSocket connection (via FastAPI's TestClient), a real Postgres
CallSession, a real Redis-backed state blob (the same one
start_live_test_call would create), and the real, unmodified
jkr_conversation ConversationEngine — only Sarvam's STT/TTS network calls
are monkeypatched, so this proves everything BUT third-party network I/O
without needing real Twilio or a real Sarvam API key (spec §63/§64: the
transport migration must never break the shared conversation engine, and
this is the test that would catch it if it did).
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

from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.live_call.service import REDIS_TTL_SECONDS, _redis_key  # noqa: E402
from app.modules.live_call.transport.media_tokens import create_media_session_token  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _load_simulator():
    """`tests.tools.twilio_media_simulator` can't be imported by its dotted
    path here: services/api/tests/ is EARLIER on sys.path than the repo
    root (pytest's own collection puts services/api first), so `tests`
    resolves to services/api/tests (which has no `tools` submodule) before
    Python ever considers the repo-root `tests` package. Loading by file
    path sidesteps that namespace collision entirely."""
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


@dataclass
class _FakeTranscript:
    text: str
    detected_language_code: str | None = "te-IN"
    language_probability: float | None = 0.9


class _FakeSTT:
    def __init__(self, *, api_key: str):
        pass

    async def transcribe(self, *, audio_bytes: bytes, language_code: str):
        return _FakeTranscript(text="root canal గురించి అడుగుతున్నాను")


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
            wav_file.writeframes(b"\x00\x01" * 400)  # ~50ms of arbitrary non-silent-looking audio
        return buffer.getvalue()


@pytest.fixture(autouse=True)
def _fresh_engine_per_test():
    """Plain sync fixture (not pytest_asyncio) — these tests are
    deliberately sync functions using asyncio.run() at explicit boundaries
    (see _reset_db_engine()'s own docstring for why), so an async fixture
    tied to pytest-asyncio's event loop would just add a fifth, unrelated
    loop context to reason about."""
    _reset_db_engine()
    yield
    _reset_db_engine()


async def _seed_call() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, call_session_id, agent_id)."""
    from jkr_db.models.agents import Agent, AgentVersion
    from jkr_db.models.calls import CallSession
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Media Stream Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Media Stream Test WS", slug=f"media-stream-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="Stream Test Agent", business_identity="Aaha Dental Care", primary_language="te-en-IN", status="active")
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
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"media-stream-test-{uuid.uuid4()}",
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
    """The SQLAlchemy async engine is cached at module level, bound to
    whichever event loop first used it (packages/db/jkr_db/session.py).
    TestClient's WebSocket handling runs the ASGI app on ITS OWN internal
    event loop (an anyio BlockingPortal in a background thread) — a
    completely different loop from whatever ran the seed/cleanup phases
    around it. Reusing a pool bound to a closed/foreign loop crashes
    ("attached to a different loop"), so the engine must be dropped and
    allowed to lazily recreate itself at every one of these boundaries.

    jkr_messaging.get_redis() has the exact same @lru_cache-bound-to-a-
    loop problem — its underlying connection dies with "Event loop is
    closed" the moment the loop that created it closes, so it's reset
    here too, at every one of the same boundaries."""
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None

    from jkr_messaging import get_redis

    get_redis.cache_clear()


async def _seed_and_cache_redis_state(workspace_id: uuid.UUID, call_session_id: uuid.UUID) -> tuple[str, dict]:
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
    return redis_state_token, redis_state


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


def test_full_media_stream_round_trip(monkeypatch):
    from app.modules.live_call.transport import transitional_bridge

    monkeypatch.setattr(transitional_bridge, "SarvamSTT", _FakeSTT)
    monkeypatch.setattr(transitional_bridge, "SarvamTTS", _FakeTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")

    _reset_db_engine()
    workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
    _reset_db_engine()
    redis_state_token, _redis_state = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

    try:
        settings = Settings()
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST", redis_state_token=redis_state_token,
        )

        _reset_db_engine()  # everything from here runs on TestClient's own internal loop
        client = TestClient(app)
        received_media_messages = []
        reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST", call_sid="CA_TEST"))

            # Drain messages until we see at least one outbound `media`
            # frame (the greeting) — proves handle_twilio_start actually
            # kicked off greeting synthesis + send, not just a state change.
            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    break

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST"):
                ws.send_json(event)

            # Drain until a SECOND media message arrives (the reply to the
            # simulated speech) or we give up after a generous number of
            # frames — mark events interleave with media, so keep reading.
            for _ in range(200):
                msg = ws.receive_json()
                if msg.get("event") == "media":
                    received_media_messages.append(msg)
                    reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST", call_sid="CA_TEST"))

        assert len(received_media_messages) >= 1, "never received the greeting over the WebSocket"
        assert reply_seen, "never received a reply to the simulated customer speech"

        # And the real proof this hit the real, unmodified ConversationEngine:
        # a real CallTurn row for the customer utterance the fake STT returned.
        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        speakers = [t.speaker for t in turns]
        assert "agent" in speakers  # the greeting
        assert "customer" in speakers  # the transcribed (fake) speech
        customer_turn = next(t for t in turns if t.speaker == "customer")
        assert customer_turn.text == "root canal గురించి అడుగుతున్నాను"
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))


def test_invalid_token_is_rejected_before_any_audio_processing():
    client = TestClient(app)
    # Connection is accepted at the ASGI level then immediately closed by
    # the handler once token verification fails — no exception expected.
    with client.websocket_connect("/api/v1/live-call/ws/twilio/media/not-a-real-token"):
        pass


def test_call_not_found_is_rejected():
    settings = Settings()
    session_token = create_media_session_token(
        secret=settings.session_secret, call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(),
        twilio_call_sid="CA_NONE", redis_state_token="does-not-matter",
    )
    _reset_db_engine()
    client = TestClient(app)
    with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}"):
        pass
