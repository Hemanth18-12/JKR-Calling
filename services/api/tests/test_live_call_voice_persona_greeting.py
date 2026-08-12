"""Stage 2 Fix 3 — proves the greeting path's VoicePersona resolution
(Agent -> published AgentVersion -> VoicePersona -> _resolve_tts_speaker() /
_resolve_tts_pace(), the exact sequence start_live_test_call runs at
services/api/app/modules/live_call/service.py before it ever synthesizes
the greeting) is genuinely agent-specific against a REAL seeded database —
not just against hand-built VoicePersona objects in memory, which
test_live_call_service.py's existing pure-function tests already cover.

Investigation for this fix found the greeting and every later turn already
share one resolution, computed once at call setup and cached in Redis state
("tts_speaker"/"tts_pace") — both read it identically (see
docs/STAGE2_REAL_CALL_FIXES.md Fix 3). What was actually missing was
regression coverage proving that shared resolution differs correctly
between two real agents, which is what this file adds. Doesn't drive
start_live_test_call() itself — that also places a real Twilio call — same
"test the DB-backed piece directly, not the whole webhook" scoping as
test_live_call_appointment_booking.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from app.modules.live_call import service  # noqa: E402
from jkr_db.enums import ProviderName  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_per_test():
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None
    yield
    eng = session_module._engine
    session_module._engine = None
    session_module._session_factory = None
    if eng is not None:
        await eng.dispose()


async def _seed_two_agents_with_different_voice_personas() -> dict:
    """One workspace, two agents — Agent A (Sarvam, voice_id="shubh", pace
    0.8, Telugu) and Agent B (Sarvam, voice_id="anushka", pace 1.6, Hindi) —
    plus a third, Agent C, with no VoicePersona row at all (the fallback
    case)."""
    from jkr_db.models.agents import Agent, AgentVersion, VoicePersona
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Voice Persona Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Voice Persona Test WS", slug=f"voice-persona-test-{workspace_id}"))
        await db.flush()

    version_ids: dict[str, uuid.UUID] = {}
    async with workspace_scoped_session(workspace_id) as db:
        for label, primary_language in (("agent_a", "te-IN"), ("agent_b", "hi-IN"), ("agent_c", "en-IN")):
            agent = Agent(workspace_id=workspace_id, name=label, business_identity="Aaha Dental Care", primary_language=primary_language, status="active")
            db.add(agent)
            await db.flush()
            version = AgentVersion(
                workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
                primary_objective="book_appointment", ai_disclosure_text="I'm an AI assistant.",
                greeting_text="Hello, can we talk?", closing_text="Thank you.",
                supported_languages=[primary_language], published_at=datetime.now(UTC),
            )
            db.add(version)
            await db.flush()
            agent.published_version_id = version.id
            version_ids[label] = version.id

        db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=version_ids["agent_a"], provider=ProviderName.SARVAM_TTS, voice_id="shubh", speaking_speed=0.8, language="te-IN"))
        db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=version_ids["agent_b"], provider=ProviderName.SARVAM_TTS, voice_id="anushka", speaking_speed=1.6, language="hi-IN"))
        # agent_c deliberately gets no VoicePersona row at all.

    return {"workspace_id": workspace_id, "version_ids": version_ids}


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in ("voice_personas", "agent_versions"):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


async def _load_voice_persona(workspace_id: uuid.UUID, agent_version_id: uuid.UUID):
    from jkr_db.models.agents import VoicePersona
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    async with workspace_scoped_session(workspace_id) as db:
        result = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == agent_version_id))
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_two_real_agents_resolve_to_two_different_greeting_speakers_and_paces():
    seeded = await _seed_two_agents_with_different_voice_personas()
    workspace_id, version_ids = seeded["workspace_id"], seeded["version_ids"]
    try:
        voice_a = await _load_voice_persona(workspace_id, version_ids["agent_a"])
        voice_b = await _load_voice_persona(workspace_id, version_ids["agent_b"])

        speaker_a, pace_a = service._resolve_tts_speaker(voice_a), service._resolve_tts_pace(voice_a)
        speaker_b, pace_b = service._resolve_tts_speaker(voice_b), service._resolve_tts_pace(voice_b)

        assert speaker_a == "shubh"
        assert speaker_b == "anushka"
        assert speaker_a != speaker_b
        assert pace_a == 0.8
        assert pace_b == 1.6
        assert pace_a != pace_b
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_agent_with_no_voice_persona_row_falls_back_to_provider_default():
    seeded = await _seed_two_agents_with_different_voice_personas()
    workspace_id, version_ids = seeded["workspace_id"], seeded["version_ids"]
    try:
        voice_c = await _load_voice_persona(workspace_id, version_ids["agent_c"])
        assert voice_c is None  # confirms the fixture really did leave agent_c unconfigured

        assert service._resolve_tts_speaker(voice_c) is None  # SarvamTTS's own "priya" default takes over
        assert service._resolve_tts_pace(voice_c) == 1.0
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_greeting_language_code_is_derived_from_each_agents_own_primary_language():
    """Agent A is te-IN, Agent B is hi-IN — service._sarvam_language_code
    must resolve each independently, not share one call-wide default."""
    from jkr_db.models.agents import Agent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_two_agents_with_different_voice_personas()
    workspace_id = seeded["workspace_id"]
    try:
        async with workspace_scoped_session(workspace_id) as db:
            agents = (await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars().all()
        by_name = {a.name: a for a in agents}

        assert service._sarvam_language_code(by_name["agent_a"].primary_language) == "te-IN"
        assert service._sarvam_language_code(by_name["agent_b"].primary_language) == "hi-IN"
        assert service._sarvam_language_code(by_name["agent_c"].primary_language) == "en-IN"
    finally:
        await _cleanup(workspace_id)
