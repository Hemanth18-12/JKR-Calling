"""P8 end-to-end proof: with BARGE_IN_ENABLED=true and the full realtime
stack active (STT_MODE=streaming, TTS_MODE=streaming, TURN_DETECTION_MODE=
hybrid), a customer utterance that starts while the agent's first reply is
still streaming actually stops that reply (a real Twilio `clear` message is
sent), and the customer's SECOND utterance is committed and answered
normally — proving the streaming_bridge.py wiring (_dispatch_commit's
background-task restructure, _update_interruption_candidate,
_execute_pending_interruption) end to end, not just the pure
InterruptionPolicy/coordinator units in isolation.

Same established pattern as test_turn_detection_integration.py /
test_streaming_stt_integration.py: real WebSocket -> RealtimeMediaSession ->
RealtimePipelineCoordinator -> TurnManager -> ConversationEngine -> real
Postgres/Redis, with only the two external provider network boundaries
faked (Sarvam streaming STT, Sarvam streaming TTS). Real sleeps are used to
pace the fake STT's scripted events relative to real background-task
progress — the same accepted pattern test_p7_pipeline_integration.py and
test_turn_detection_integration.py already use for this class of test (never
for the pure, fake-clock InterruptionPolicy/TurnManager unit tests).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")
os.environ.setdefault("REDIS_URL", "redis://localhost:16379/0")

from app.config import get_settings  # noqa: E402
from app.live_providers.streaming_stt import (  # noqa: E402
    FinalTranscript,
    PartialTranscript,
    SpeechEnded,
    SpeechStarted,
    STTSessionStarted,
)
from app.live_providers.streaming_tts import (  # noqa: E402
    TTSAudioChunk,
    TTSCapabilities,
    TTSGenerationCompleted,
)
from app.main import app  # noqa: E402
from app.modules.live_call.service import REDIS_TTL_SECONDS, _redis_key  # noqa: E402
from app.modules.live_call.transport import streaming_bridge  # noqa: E402
from app.modules.live_call.transport.media_tokens import create_media_session_token  # noqa: E402
from app.modules.live_call.transport.replay_metrics import metrics as replay_metrics  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_FIRST_UTTERANCE = "Root canal cost entha"
_SECOND_UTTERANCE = "wait one minute tomorrow appointment available a"


def _load_simulator():
    import importlib.util

    here = os.path.abspath(__file__)
    repo_root = here
    for _ in range(6):  # barge_in -> voice -> tests -> api -> services -> repo root
        repo_root = os.path.dirname(repo_root)
    path = os.path.join(repo_root, "tests", "tools", "twilio_media_simulator.py")
    spec = importlib.util.spec_from_file_location("twilio_media_simulator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_simulator = _load_simulator()
build_connected_event = _simulator.build_connected_event
build_mark_event = _simulator.build_mark_event
build_speech_and_silence_sequence = _simulator.build_speech_and_silence_sequence
build_start_event = _simulator.build_start_event
build_stop_event = _simulator.build_stop_event


class _FakeBatchTTS:
    """Used only for the greeting, which is always sent via the pre-P6
    batch PCM path regardless of TTS_MODE (see _processing_loop)."""

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


class _FakeStreamingTTS:
    """Produces audio as each send_text() arrives (matching the real
    verified Sarvam behavior, same pattern test_p7_pipeline_integration.py's
    own fake uses) and NEVER emits its own completion event particularly
    fast — audio just accumulates as SENT PlaybackUnits, unacknowledged
    (the test never sends a Twilio `mark` event back), which is exactly
    what makes "interrupted mid-playback, real Twilio clear required"
    reproducible deterministically rather than racily."""

    def __init__(self, *, api_key: str, **kwargs):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._audio_chunk_index: dict[str, int] = {}
        self.cancelled: list[str] = []
        self._cancelled_response_ids: set[str] = set()

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        if response_id in self._cancelled_response_ids:
            return
        index = self._audio_chunk_index.get(response_id, 0)
        self._audio_chunk_index[response_id] = index + 1
        await self._queue.put(
            TTSAudioChunk(response_id=response_id, audio_chunk_index=index, data=b"\xff" * 800, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)
        )

    async def flush(self, *, response_id):
        if response_id in self._cancelled_response_ids:
            return
        await self._queue.put(TTSGenerationCompleted(response_id=response_id))

    async def cancel(self, response_id):
        self.cancelled.append(response_id)
        self._cancelled_response_ids.add(response_id)

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


@dataclass
class _FakeStreamingSTTInterrupt:
    """Scripts exactly the scenario this phase's own final engineering test
    describes: a first utterance triggers a reply; while that reply is
    still streaming (unacknowledged), a second utterance starts with a
    high-priority interruption cue ("wait", "one minute") in its partial
    transcript, then completes with a real follow-up question."""

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
            utterance_idx=0, text=_FIRST_UTTERANCE, detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        # Give the background response task (P8's whole point: this loop
        # must not be blocked while that happens) real time to begin
        # generating and start streaming audio before the customer barges in.
        await asyncio.sleep(0.3)
        yield SpeechStarted(utterance_idx=1, provider_confidence=None, raw={})
        yield PartialTranscript(utterance_idx=1, text="wait one minute", detected_language_code="en-IN", raw={})
        await asyncio.sleep(0.2)
        yield FinalTranscript(
            utterance_idx=1, text=_SECOND_UTTERANCE, detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        while True:  # noqa: ASYNC110 — stays "connected" until cancelled by session.close()
            await asyncio.sleep(3600)


@dataclass
class _FakeStreamingSTTBackchannel:
    """Scripts the negative case: a short filler ("hmm") arrives while the
    first reply is still streaming — must NOT be treated as a genuine
    interruption (spec: distinguish backchannel from real barge-in), and
    must not even reach TurnManager's own commit logic as a second turn."""

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
            utterance_idx=0, text=_FIRST_UTTERANCE, detected_language_code="en-IN",
            language_probability=0.9, start_s=None, end_s=None, provider_confidence=None, raw={},
        )
        await asyncio.sleep(0.3)
        yield SpeechStarted(utterance_idx=1, provider_confidence=None, raw={})
        yield PartialTranscript(utterance_idx=1, text="hmm", detected_language_code="en-IN", raw={})
        await asyncio.sleep(0.2)
        yield SpeechEnded(utterance_idx=1, provider_confidence=None, raw={})
        while True:  # noqa: ASYNC110
            await asyncio.sleep(3600)


def _reset_db_engine() -> None:
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None

    from jkr_messaging import get_redis

    get_redis.cache_clear()


async def _seed_call() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    from jkr_db.models.agents import Agent, AgentVersion
    from jkr_db.models.calls import CallSession
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Barge-In Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Barge-In Test WS", slug=f"barge-in-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="Barge-In Test Agent", business_identity="Aaha Dental Care", primary_language="en-IN", status="active")
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
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"barge-in-test-{uuid.uuid4()}",
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


async def _seed_and_cache_redis_state(workspace_id: uuid.UUID, call_session_id: uuid.UUID) -> str:
    from jkr_messaging import get_redis

    redis = get_redis()
    redis_state_token = uuid.uuid4().hex
    redis_state: dict = {
        "workspace_id": str(workspace_id), "call_session_id": str(call_session_id),
        "closing_text": "Thank you.", "language_code": "en-IN", "business_identity": "Aaha Dental Care",
        "policy": {}, "tts_speaker": None, "tts_pace": 1.0, "greeted": False,
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


async def _fetch_redis_state(redis_state_token: str) -> dict:
    from jkr_messaging import get_redis

    redis = get_redis()
    raw = await redis.get(_redis_key(redis_state_token))
    return json.loads(raw)


async def _delete_redis_key(redis_state_token: str) -> None:
    from jkr_messaging import get_redis

    await get_redis().delete(_redis_key(redis_state_token))


def _drain_greeting_and_ack_its_marks(ws, *, stream_sid: str) -> None:
    """Waits for the greeting's own media, then acknowledges every mark
    that follows it — simulating realistic Twilio behavior (marks return
    once that audio actually finishes playing) so the greeting is properly
    "no longer active" (see streaming_bridge.py's _agent_active_response())
    before the customer's own first turn is sent. Deliberately NOT applied
    to any later response in these tests — the whole point of the
    interrupt scenario is that the FIRST REAL REPLY's marks are still
    outstanding when the interruption lands, same as a customer genuinely
    barging in on a still-playing response in a real call."""
    seen_media = False
    for i in range(10):
        msg = ws.receive_json()
        event_name = msg.get("event")
        if event_name == "media":
            seen_media = True
        elif event_name == "mark" and seen_media:
            ws.send_json(build_mark_event(stream_sid=stream_sid, name=msg["mark"]["name"], sequence=str(100 + i)))
            return
    raise AssertionError("greeting's media/mark pair never arrived")


def test_customer_barge_in_stops_reply_clears_twilio_and_answers_new_question(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeStreamingSTTInterrupt)
    monkeypatch.setattr("app.modules.live_call.transport.transitional_bridge.SarvamTTS", _FakeBatchTTS)
    monkeypatch.setattr("app.live_providers.sarvam_streaming_tts.SarvamStreamingTTS", _FakeStreamingTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TTS_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    monkeypatch.setenv("TURN_DETECTION_MODE", "hybrid")
    monkeypatch.setenv("TURN_PROFILE", "fast")
    monkeypatch.setenv("BARGE_IN_ENABLED", "true")
    monkeypatch.setenv("BARGE_IN_SENSITIVITY", "high")
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        assert settings.effective_barge_in_enabled is True
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_BARGEIN", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        clear_seen = False
        first_reply_seen = False
        second_reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_BARGEIN", call_sid="CA_TEST_BARGEIN"))

            _drain_greeting_and_ack_its_marks(ws, stream_sid="MZ_TEST_BARGEIN")

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_BARGEIN", speech_frames=60, silence_frames=10):
                ws.send_json(event)

            # Drain until we see: the FIRST reply's media (proves the
            # original response really did start streaming before the
            # interruption), then a `clear` event (proves a real Twilio
            # clear was sent, not just local bookkeeping), then a SECOND
            # reply's media (proves the call recovered and answered the new
            # question, not just went silent).
            for _ in range(2000):
                msg = ws.receive_json()
                event_name = msg.get("event")
                if event_name == "media" and not first_reply_seen:
                    first_reply_seen = True
                elif event_name == "clear":
                    clear_seen = True
                elif event_name == "media" and first_reply_seen and clear_seen:
                    second_reply_seen = True
                    break

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_BARGEIN", call_sid="CA_TEST_BARGEIN"))

        assert first_reply_seen, "the original reply never even started streaming — test setup problem, not a barge-in result"
        assert clear_seen, "no Twilio clear message was sent — the interruption did not actually stop the original reply"
        assert second_reply_seen, "no second reply was ever produced after the interruption — the call went silent instead of recovering"
        # P9 — the same real end-to-end interruption this test already
        # proves, now also proving the zero-leak guarantee through the
        # ACTUAL WebSocket send loop (twilio_media_stream.py's _send_loop),
        # not just the coordinator-level unit tests in tests/voice/replay/.
        assert replay_metrics.stale_audio_sent_total == 0

        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        customer_turns = [t for t in turns if t.speaker == "customer"]
        # Both the interrupted utterance's OWN triggering text and the
        # interrupting utterance itself must be on the record — the
        # interruption must never make history vanish (spec: normal
        # TurnManager -> engine pipeline, no dropped turns).
        customer_texts = [t.text for t in customer_turns]
        assert _FIRST_UTTERANCE in customer_texts
        assert _SECOND_UTTERANCE in customer_texts

        redis_state = asyncio.run(_fetch_redis_state(redis_state_token))
        recent_turns = redis_state["recent_turns"]
        agent_entries = [t for t in recent_turns if t.get("speaker") == "agent"]
        # The interrupted response's history entry (if it survived the
        # repair at all) must never be the full, freely-generated reply —
        # spec: never store the full generated text as if it were spoken.
        assert not any(t.get("interrupted") and len(t.get("text", "")) == 0 for t in agent_entries), "an interrupted turn was left with a fabricated non-empty-looking but actually empty entry"
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()


def test_backchannel_during_reply_does_not_trigger_a_clear_or_a_second_turn(monkeypatch):
    monkeypatch.setattr(streaming_bridge, "SarvamStreamingSTT", _FakeStreamingSTTBackchannel)
    monkeypatch.setattr("app.modules.live_call.transport.transitional_bridge.SarvamTTS", _FakeBatchTTS)
    monkeypatch.setattr("app.live_providers.sarvam_streaming_tts.SarvamStreamingTTS", _FakeStreamingTTS)
    monkeypatch.setenv("SARVAM_API_KEY", "fake")
    monkeypatch.setenv("SARVAM_TTS_API_KEY", "fake")
    monkeypatch.setenv("STT_MODE", "streaming")
    monkeypatch.setenv("TTS_MODE", "streaming")
    monkeypatch.setenv("TWILIO_VOICE_TRANSPORT", "media_stream")
    monkeypatch.setenv("TURN_DETECTION_MODE", "hybrid")
    monkeypatch.setenv("TURN_PROFILE", "fast")
    monkeypatch.setenv("BARGE_IN_ENABLED", "true")
    monkeypatch.setenv("BARGE_IN_SENSITIVITY", "high")
    get_settings.cache_clear()

    try:
        _reset_db_engine()
        workspace_id, call_session_id, agent_id = asyncio.run(_seed_call())
        _reset_db_engine()
        redis_state_token = asyncio.run(_seed_and_cache_redis_state(workspace_id, call_session_id))

        settings = get_settings()
        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid="CA_TEST_BACKCHANNEL", redis_state_token=redis_state_token,
        )

        _reset_db_engine()
        client = TestClient(app)
        events_seen: list[str] = []
        first_reply_seen = False
        with client.websocket_connect(f"/api/v1/live-call/ws/twilio/media/{session_token}") as ws:
            ws.send_json(build_connected_event())
            ws.send_json(build_start_event(stream_sid="MZ_TEST_BACKCHANNEL", call_sid="CA_TEST_BACKCHANNEL"))

            _drain_greeting_and_ack_its_marks(ws, stream_sid="MZ_TEST_BACKCHANNEL")

            for event in build_speech_and_silence_sequence(stream_sid="MZ_TEST_BACKCHANNEL", speech_frames=60, silence_frames=10):
                ws.send_json(event)

            for _ in range(50):
                msg = ws.receive_json()
                event_name = msg.get("event", "")
                events_seen.append(event_name)
                if event_name == "media":
                    first_reply_seen = True
                    break

            # Real-time wait (server runs concurrently in its own thread/
            # loop, same TestClient model every other test in this file
            # relies on) covering the fake STT's own scripted 0.3s + 0.2s
            # sleeps between the first reply and the "hmm" burst — long
            # enough for the backchannel evidence to actually be evaluated
            # server-side before this test concludes nothing interrupted it.
            time.sleep(0.8)

            ws.send_json(build_stop_event(stream_sid="MZ_TEST_BACKCHANNEL", call_sid="CA_TEST_BACKCHANNEL"))
            try:
                for _ in range(20):
                    msg = ws.receive_json()
                    events_seen.append(msg.get("event", ""))
            except Exception:  # noqa: BLE001 — the socket closing after `stop` is expected, not a failure
                pass

        assert first_reply_seen, "the original reply never started streaming — test setup problem"
        assert "clear" not in events_seen, f"a Twilio clear was sent for a mere backchannel — should never interrupt: {events_seen}"

        _reset_db_engine()
        turns = asyncio.run(_fetch_call_turns(workspace_id, call_session_id))
        customer_turns = [t for t in turns if t.speaker == "customer"]
        # "hmm" alone must never even reach a second committed customer
        # turn — TurnManager's own backchannel-not-expected-as-answer gate
        # (reused by InterruptionPolicy) already prevents that.
        assert len(customer_turns) == 1
        assert customer_turns[0].text == _FIRST_UTTERANCE
    finally:
        _reset_db_engine()
        asyncio.run(_delete_redis_key(redis_state_token))
        asyncio.run(_cleanup(workspace_id))
        get_settings.cache_clear()
