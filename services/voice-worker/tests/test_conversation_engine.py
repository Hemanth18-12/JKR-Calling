"""Integration tests against a real Postgres database (the same one local
dev/CI already runs) — conversation_engine's persistence and state-machine
logic is exactly the part that's too easy to get subtly wrong without a real
DB round-trip (see the two bugs this file's assertions were written to catch:
the first-utterance field misattribution, and false-positive fillers wrongly
advancing the script — docs/IMPLEMENTATION_CHECKLIST.md Phase 3 notes).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from jkr_db.models.agents import Agent, AgentVersion, ConversationPolicy, VoicePersona
from jkr_db.models.tenancy import Organization, Workspace
from jkr_db.session import workspace_scoped_session
from sqlalchemy import select, text

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling",
)

from app import conversation_engine  # noqa: E402
from app.session_registry import discard as registry_discard  # noqa: E402


# pytest-asyncio (function-scoped loop, this project's default) gives each
# test its OWN event loop, but jkr_db.session caches its AsyncEngine at
# module level for one process's whole lifetime — correct in production (one
# process, one loop), wrong across tests (asyncpg connections are loop-bound;
# reusing an engine created on a prior test's now-closed loop raises "got
# Future attached to a different loop"). Reset the cache every test so each
# gets a fresh engine bound to its own loop.
@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_per_test():
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None
    yield
    engine = session_module._engine
    session_module._engine = None
    session_module._session_factory = None
    if engine is not None:
        await engine.dispose()


async def _seed_workspace_and_agent() -> tuple[uuid.UUID, uuid.UUID]:
    from jkr_db.session import get_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Test Org")
        db.add(org)
        await db.flush()
        db.add(
            Workspace(
                id=workspace_id, organization_id=org.id, name="Test WS", slug=f"test-ws-{workspace_id}",
            )
        )
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(
            workspace_id=workspace_id, name="Test Agent", business_identity="Test Biz",
            primary_language="te-en-IN", status="active",
        )
        db.add(agent)
        await db.flush()

        version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="book_appointment", ai_disclosure_text="నేను AI assistantని.",
            greeting_text="నమస్కారం {name} గారు, నేను AI assistantని. మాట్లాడొచ్చా?",
            closing_text="ధన్యవాదాలు.", supported_languages=["te-en-IN"], published_at=datetime.now(UTC),
        )
        db.add(version)
        await db.flush()

        agent.published_version_id = version.id
        db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=version.id, language="te-en-IN"))
        db.add(
            ConversationPolicy(
                workspace_id=workspace_id, agent_version_id=version.id,
                accidental_interruption_phrases=["hmm", "okay", "అవును"],
                # Low on purpose for tests: a real deployment's timing floor
                # (spec §11 default ~250ms) exists to filter out replies too
                # fast to be a plausible human reaction; test turns fire only
                # a few ms apart even with an explicit `await asyncio.sleep`,
                # so this is lowered to keep tests fast without disabling the
                # floor's behavior entirely (still asserted in test_turn_manager.py
                # against the real default).
                min_interruption_ms=10,
            )
        )
        await db.flush()
        return workspace_id, agent.id


@pytest_asyncio.fixture
async def workspace_and_agent():
    workspace_id, agent_id = await _seed_workspace_and_agent()
    yield workspace_id, agent_id
    # Cleanup: RLS-scoped delete of everything under this workspace, then the
    # workspace/org rows themselves via the superuser-equivalent app role
    # (workspace/organizations have no RLS — see docs/DATA_MODEL.md §1).
    async with workspace_scoped_session(workspace_id) as db:
        for table in (
            "call_latency_metrics", "interruption_events", "call_events", "call_turns",
            "call_transcripts", "call_outcomes", "call_summaries", "call_participants",
            "call_sessions", "pronunciation_entries", "conversation_policies", "voice_personas",
            "agent_versions",
        ):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    from jkr_db.session import get_session

    async with get_session() as db:
        ws = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws_row = ws.scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


@pytest.mark.asyncio
async def test_first_utterance_is_attributed_to_first_script_field(workspace_and_agent):
    workspace_id, agent_id = workspace_and_agent
    async with workspace_scoped_session(workspace_id) as db:
        created = await conversation_engine.start_session(db, workspace_id=workspace_id, agent_id=agent_id, contact_name="Ravi")
        call_id = created["call_id"]

    await asyncio.sleep(0.05)  # clear the (test-lowered) min_interruption_ms floor
    async with workspace_scoped_session(workspace_id) as db:
        result = await conversation_engine.submit_user_turn(
            db, workspace_id=workspace_id, call_id=call_id, text="నాకు root canal కావాలి"
        )

    assert result.conversation_state["known_fields"].get("reason_for_visit") == "నాకు root canal కావాలి"
    assert result.conversation_state["asked_count"] == 2  # first field auto-attributed, second question just asked
    registry_discard(call_id)


@pytest.mark.asyncio
async def test_false_positive_does_not_advance_script_or_produce_agent_turn(workspace_and_agent):
    workspace_id, agent_id = workspace_and_agent
    async with workspace_scoped_session(workspace_id) as db:
        created = await conversation_engine.start_session(db, workspace_id=workspace_id, agent_id=agent_id, contact_name="Ravi")
        call_id = created["call_id"]

    await asyncio.sleep(0.05)
    async with workspace_scoped_session(workspace_id) as db:
        before = await conversation_engine.submit_user_turn(
            db, workspace_id=workspace_id, call_id=call_id, text="నాకు root canal కావాలి"
        )
    state_before = before.conversation_state

    # Fire the false-positive filler immediately (well within the just-started
    # next agent turn's simulated speaking window).
    async with workspace_scoped_session(workspace_id) as db:
        result = await conversation_engine.submit_user_turn(db, workspace_id=workspace_id, call_id=call_id, text="అవును")

    assert result.interruption_classification == "false_positive"
    assert result.agent_turn is None
    assert result.conversation_state == state_before  # nothing advanced
    registry_discard(call_id)


@pytest.mark.asyncio
async def test_full_flow_reaches_appointment_booked_outcome(workspace_and_agent):
    workspace_id, agent_id = workspace_and_agent
    async with workspace_scoped_session(workspace_id) as db:
        created = await conversation_engine.start_session(db, workspace_id=workspace_id, agent_id=agent_id, contact_name="Ravi")
        call_id = created["call_id"]

    for answer in ["root canal కావాలి", "రేపు వీలుగా ఉంటుంది", "ఉదయం పది గంటలకు"]:
        await asyncio.sleep(0.05)
        async with workspace_scoped_session(workspace_id) as db:
            result = await conversation_engine.submit_user_turn(db, workspace_id=workspace_id, call_id=call_id, text=answer)

    assert result.conversation_state["objective_status"] == "completed"
    assert set(result.conversation_state["known_fields"].keys()) == {"reason_for_visit", "preferred_date", "preferred_time"}

    async with workspace_scoped_session(workspace_id) as db:
        outcome = await conversation_engine.end_session(db, workspace_id=workspace_id, call_id=call_id)

    assert outcome["status"] == "completed"
    assert outcome["outcome_category"] == "appointment_booked"
    assert outcome["lead_score"] == "hot"
