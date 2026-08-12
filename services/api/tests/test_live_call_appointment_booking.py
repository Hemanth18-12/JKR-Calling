"""Stage 2 Fix 1 — real Postgres coverage for the two pieces service.py adds
around appointment booking: resolving a real contact_id at call creation
(_get_or_create_contact) and never letting a canned success reply escape a
real tool failure (_execute_tool_calls / _tool_failure_reply). See
docs/STAGE2_REAL_CALL_FIXES.md.

Deliberately separate from test_live_call_service.py, whose own docstring
scopes it to pure helpers with no DB session — these two helpers are
genuinely DB-backed (a real Contact lookup, a real execute_tool() call
against Postgres), so they get the same seed/cleanup-against-real-Postgres
treatment as test_twilio_media_stream_integration.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from app.modules.live_call import service  # noqa: E402
from jkr_conversation.schemas import ToolCallRequest  # noqa: E402


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


class _FakeTurnResult:
    """Duck-types the two fields _execute_tool_calls actually reads off a
    ConversationTurnResult — same "minimal fake, not the real frozen
    dataclass" approach test_live_call_service.py's own _FakeResult already
    uses for _end_reason_for."""

    def __init__(self, tool_calls_requested, state=None):
        self.tool_calls_requested = tool_calls_requested
        self.state = state if state is not None else {}


async def _seed_workspace_agent_and_call(*, with_contact: bool = True, tool_enabled: bool | None = True) -> dict:
    """tool_enabled=None means "don't seed a ToolDefinition at all" (the
    not-configured case) rather than seeding one that's disabled."""
    from jkr_db.models.agents import Agent, AgentVersion, ToolDefinition
    from jkr_db.models.calls import CallSession
    from jkr_db.models.contacts import Contact
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Appointment Booking Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Appointment Booking Test WS", slug=f"appt-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        agent = Agent(workspace_id=workspace_id, name="Booking Test Agent", business_identity="Aaha Dental Care", primary_language="en-IN", status="active")
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="book_appointment", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Hello, can we talk?", closing_text="Thank you.",
            supported_languages=["en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        if tool_enabled is not None:
            db.add(
                ToolDefinition(
                    workspace_id=workspace_id, name="book_appointment", description="Book a new appointment for the contact",
                    required_permission="contacts:edit", timeout_seconds=10, confirmation_required=True, is_enabled=tool_enabled,
                )
            )

        contact_id = None
        if with_contact:
            contact = Contact(workspace_id=workspace_id, full_name="Live test call", phone_e164="+919876500000")
            db.add(contact)
            await db.flush()
            contact_id = contact.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="in_progress",
            agent_id=agent.id, agent_version_id=agent_version.id, contact_id=contact_id,
            idempotency_key=f"appt-test-{uuid.uuid4()}", language="en-IN", state={}, started_at=datetime.now(UTC),
            is_mock=False, disclosure_confirmed=True,
        )
        db.add(call_session)
        await db.flush()

    return {"workspace_id": workspace_id, "call_session": call_session, "contact_id": contact_id}


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in ("appointments", "tool_executions", "tool_definitions", "call_sessions", "contacts", "agent_versions"):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


def _book_appointment_call() -> ToolCallRequest:
    return ToolCallRequest(
        tool_name="book_appointment",
        tool_input={"preferred_date": "tomorrow", "preferred_time": "morning", "reason_for_visit": "cleaning"},
        idempotency_suffix="book_appointment",
    )


# --- _get_or_create_contact ------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_contact_is_find_or_create_by_phone_number():
    from jkr_db.models.contacts import Contact
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_workspace_agent_and_call(with_contact=False)
    workspace_id = seeded["workspace_id"]
    try:
        async with workspace_scoped_session(workspace_id) as db:
            first = await service._get_or_create_contact(db, workspace_id=workspace_id, phone_e164="+919876511111")
            second = await service._get_or_create_contact(db, workspace_id=workspace_id, phone_e164="+919876511111")
            rows = (await db.execute(select(Contact).where(Contact.workspace_id == workspace_id))).scalars().all()
        assert first.id == second.id
        assert len(rows) == 1
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_get_or_create_contact_does_not_leak_across_workspaces():
    from jkr_db.session import workspace_scoped_session

    seeded_a = await _seed_workspace_agent_and_call(with_contact=False)
    seeded_b = await _seed_workspace_agent_and_call(with_contact=False)
    try:
        async with workspace_scoped_session(seeded_a["workspace_id"]) as db:
            contact_a = await service._get_or_create_contact(db, workspace_id=seeded_a["workspace_id"], phone_e164="+919876522222")
        async with workspace_scoped_session(seeded_b["workspace_id"]) as db:
            contact_b = await service._get_or_create_contact(db, workspace_id=seeded_b["workspace_id"], phone_e164="+919876522222")
        assert contact_a.id != contact_b.id
        assert contact_a.workspace_id == seeded_a["workspace_id"]
        assert contact_b.workspace_id == seeded_b["workspace_id"]
    finally:
        await _cleanup(seeded_a["workspace_id"])
        await _cleanup(seeded_b["workspace_id"])


# --- _execute_tool_calls ----------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_calls_books_a_real_appointment_when_contact_id_is_present():
    """Case A — the contact_id resolved at call creation actually reaches
    the tool, and a real Appointment row results."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_workspace_agent_and_call(with_contact=True, tool_enabled=True)
    workspace_id, call_session, contact_id = seeded["workspace_id"], seeded["call_session"], seeded["contact_id"]
    try:
        result = _FakeTurnResult(tool_calls_requested=[_book_appointment_call()])
        async with workspace_scoped_session(workspace_id) as db:
            tool_failed = await service._execute_tool_calls(
                db, workspace_id=workspace_id, call_session_id=call_session.id, call_session=call_session, result=result,
            )
            appointments = (await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))).scalars().all()

        assert tool_failed is False
        assert "book_appointment" in result.state.get("tool_results", {})
        assert len(appointments) == 1
        assert appointments[0].contact_id == contact_id
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_calls_reports_failure_and_books_nothing_without_a_contact():
    """Case B — a call session with no contact (the exact pre-fix state
    every /api/v1/live-call CallSession used to be in): the tool must fail,
    the caller must be told to override the spoken reply, and no
    Appointment may exist."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_workspace_agent_and_call(with_contact=False, tool_enabled=True)
    workspace_id, call_session = seeded["workspace_id"], seeded["call_session"]
    assert call_session.contact_id is None
    try:
        result = _FakeTurnResult(tool_calls_requested=[_book_appointment_call()])
        async with workspace_scoped_session(workspace_id) as db:
            tool_failed = await service._execute_tool_calls(
                db, workspace_id=workspace_id, call_session_id=call_session.id, call_session=call_session, result=result,
            )
            appointments = (await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))).scalars().all()

        assert tool_failed is True
        assert "tool_results" not in result.state
        assert appointments == []
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_calls_treats_an_unconfigured_tool_as_not_a_failure():
    """Matches pre-fix behavior for this specific case on purpose: a
    workspace that never enabled book_appointment at all is a configuration
    choice, not a booking failure this turn — the call proceeds exactly as
    it did before this fix (ToolNotDefinedError is swallowed, not counted)."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_workspace_agent_and_call(with_contact=True, tool_enabled=None)
    workspace_id, call_session = seeded["workspace_id"], seeded["call_session"]
    try:
        result = _FakeTurnResult(tool_calls_requested=[_book_appointment_call()])
        async with workspace_scoped_session(workspace_id) as db:
            tool_failed = await service._execute_tool_calls(
                db, workspace_id=workspace_id, call_session_id=call_session.id, call_session=call_session, result=result,
            )
            appointments = (await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))).scalars().all()

        assert tool_failed is False
        assert appointments == []
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_calls_is_idempotent_across_repeated_webhook_retries():
    """Case E — a Twilio webhook retry re-running the same turn must not
    double-book. Uses the exact idempotency_key format service.py builds
    (f"call-{call_session_id}-{idempotency_suffix}")."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    seeded = await _seed_workspace_agent_and_call(with_contact=True, tool_enabled=True)
    workspace_id, call_session = seeded["workspace_id"], seeded["call_session"]
    try:
        async with workspace_scoped_session(workspace_id) as db:
            result1 = _FakeTurnResult(tool_calls_requested=[_book_appointment_call()])
            await service._execute_tool_calls(
                db, workspace_id=workspace_id, call_session_id=call_session.id, call_session=call_session, result=result1,
            )
            result2 = _FakeTurnResult(tool_calls_requested=[_book_appointment_call()])
            await service._execute_tool_calls(
                db, workspace_id=workspace_id, call_session_id=call_session.id, call_session=call_session, result=result2,
            )
            appointments = (await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))).scalars().all()

        assert len(appointments) == 1
        assert result1.state["tool_results"]["book_appointment"] == result2.state["tool_results"]["book_appointment"]
    finally:
        await _cleanup(workspace_id)
