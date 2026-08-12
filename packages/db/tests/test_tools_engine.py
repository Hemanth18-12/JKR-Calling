from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from jkr_db.tools_engine import REAL_SIDE_EFFECT_TOOLS, execute_tool, parse_fuzzy_datetime  # noqa: E402
from sqlalchemy import select  # noqa: E402

# A fixed Monday for deterministic day-of-week math.
_MONDAY = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def test_parse_fuzzy_datetime_recognizes_tomorrow():
    result = parse_fuzzy_datetime("tomorrow", None, now=_MONDAY)
    assert result.date() == datetime(2026, 8, 4, tzinfo=UTC).date()


def test_parse_fuzzy_datetime_recognizes_day_name():
    result = parse_fuzzy_datetime("Saturday works for me", None, now=_MONDAY)
    assert result.weekday() == 5  # Saturday


def test_parse_fuzzy_datetime_recognizes_time_of_day_word():
    result = parse_fuzzy_datetime("tomorrow", "morning", now=_MONDAY)
    assert result.hour == 10


def test_parse_fuzzy_datetime_recognizes_explicit_hour():
    result = parse_fuzzy_datetime("tomorrow", "3pm works", now=_MONDAY)
    assert result.hour == 15


def test_parse_fuzzy_datetime_falls_back_on_unparseable_text():
    result = parse_fuzzy_datetime("Sure, tell me more about that.", None, now=_MONDAY)
    assert result.date() == datetime(2026, 8, 6, tzinfo=UTC).date()
    assert result.hour == 11


def test_parse_fuzzy_datetime_handles_none_input():
    result = parse_fuzzy_datetime(None, None, now=_MONDAY)
    assert result > _MONDAY


def test_real_side_effect_tools_matches_documented_set():
    assert REAL_SIDE_EFFECT_TOOLS == {
        "book_appointment", "reschedule_appointment", "cancel_appointment",
        "create_human_callback", "send_whatsapp", "send_sms",
    }


# --- execute_tool()/book_appointment: real Postgres, seed + cleanup -------
# The audit finding this covers: a real live call could reach book_appointment
# with no contact_id, the tool silently failed, and nothing downstream of
# execute_tool() ever checked — a canned "appointment noted" line still got
# spoken. These tests prove the tool layer itself: (a) never fabricates
# success without a real contact, (b) never lets a cross-tenant contact_id
# through, and (c) is genuinely idempotent — see
# docs/STAGE2_REAL_CALL_FIXES.md Fix 1.


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


async def _seed_workspace_with_contact_and_tool(*, tool_name: str = "book_appointment", enabled: bool = True) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, contact_id) — the minimal real rows execute_tool
    needs: a ToolDefinition (it raises ToolNotDefinedError/ToolNotEnabledError
    otherwise) and a Contact to book against. Field values for ToolDefinition
    mirror seed.py's TOOL_CATALOG entry for book_appointment exactly, not
    invented ad hoc."""
    from jkr_db.models.agents import ToolDefinition
    from jkr_db.models.contacts import Contact
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Tools Engine Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Tools Engine Test WS", slug=f"tools-engine-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        db.add(
            ToolDefinition(
                workspace_id=workspace_id, name=tool_name, description="Book a new appointment for the contact",
                required_permission="contacts:edit", timeout_seconds=10, confirmation_required=True, is_enabled=enabled,
            )
        )
        contact = Contact(workspace_id=workspace_id, full_name="Test Contact", phone_e164="+919876543210")
        db.add(contact)
        await db.flush()
        contact_id = contact.id

    return workspace_id, contact_id


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in ("appointments", "messages", "tool_executions", "tool_definitions", "contacts"):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


@pytest.mark.asyncio
async def test_execute_tool_books_a_real_appointment_for_a_valid_contact():
    """Case A — valid contact: the tool receives the correct contact_id and
    the Appointment row it creates actually carries it, not just a
    success-shaped ToolExecution."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session

    workspace_id, contact_id = await _seed_workspace_with_contact_and_tool()
    try:
        async with workspace_scoped_session(workspace_id) as db:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name="book_appointment",
                tool_input={"preferred_date": "tomorrow", "preferred_time": "morning", "reason_for_visit": "cleaning"},
                idempotency_key=f"test-{uuid.uuid4()}", contact_id=contact_id,
            )
            assert execution.status == "succeeded"
            assert execution.output["appointment_id"]

            appt_result = await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))
            appointments = appt_result.scalars().all()
        assert len(appointments) == 1
        assert appointments[0].contact_id == contact_id
        assert str(appointments[0].id) == execution.output["appointment_id"]
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_never_fabricates_success_without_a_contact_id():
    """Case B — missing contact_id: the tool must fail, not silently
    proceed, and no Appointment row may exist afterward — this is the exact
    audit finding (a spoken "noted" with nothing actually booked)."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session

    workspace_id, _contact_id = await _seed_workspace_with_contact_and_tool()
    try:
        async with workspace_scoped_session(workspace_id) as db:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name="book_appointment",
                tool_input={"preferred_date": "tomorrow", "preferred_time": "morning", "reason_for_visit": "cleaning"},
                idempotency_key=f"test-{uuid.uuid4()}", contact_id=None,
            )
            assert execution.status == "failed"
            assert execution.output is None
            assert "contact_id" in execution.error

            appt_result = await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))
            appointments = appt_result.scalars().all()
        assert appointments == []
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_rejects_a_contact_from_a_different_workspace():
    """Case D — wrong-workspace contact: a contact_id that's real, but
    belongs to a DIFFERENT workspace than the one executing the tool, must
    be rejected exactly like a missing one — no booking, and the error
    message doesn't reveal whether the contact exists elsewhere."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session

    workspace_a, contact_a = await _seed_workspace_with_contact_and_tool()
    workspace_b, _contact_b = await _seed_workspace_with_contact_and_tool()
    try:
        async with workspace_scoped_session(workspace_b) as db:
            execution = await execute_tool(
                db, workspace_id=workspace_b, tool_name="book_appointment",
                tool_input={"preferred_date": "tomorrow", "preferred_time": "morning", "reason_for_visit": "cleaning"},
                idempotency_key=f"test-{uuid.uuid4()}", contact_id=contact_a,
            )
            assert execution.status == "failed"
            assert "not found in this workspace" in execution.error

            appt_result = await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_b))
            appointments = appt_result.scalars().all()
        assert appointments == []
    finally:
        await _cleanup(workspace_a)
        await _cleanup(workspace_b)


@pytest.mark.asyncio
async def test_execute_tool_book_appointment_fails_cleanly_when_tool_not_configured():
    """Case C (tool-configuration flavor) — a workspace with no
    ToolDefinition for book_appointment (or one explicitly disabled) must
    raise, not silently succeed or silently no-op with a success-shaped
    result."""
    from jkr_db.tools_engine import ToolNotEnabledError

    workspace_id, contact_id = await _seed_workspace_with_contact_and_tool(enabled=False)
    try:
        from jkr_db.session import workspace_scoped_session

        async with workspace_scoped_session(workspace_id) as db:
            with pytest.raises(ToolNotEnabledError):
                await execute_tool(
                    db, workspace_id=workspace_id, tool_name="book_appointment",
                    tool_input={"preferred_date": "tomorrow", "preferred_time": "morning"},
                    idempotency_key=f"test-{uuid.uuid4()}", contact_id=contact_id,
                )
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_execute_tool_book_appointment_is_idempotent_on_repeated_calls():
    """Case E — the same idempotency_key replayed (e.g. a webhook retry)
    must return the original execution, not create a second Appointment."""
    from jkr_db.models.tools import Appointment
    from jkr_db.session import workspace_scoped_session

    workspace_id, contact_id = await _seed_workspace_with_contact_and_tool()
    try:
        key = f"test-{uuid.uuid4()}"
        async with workspace_scoped_session(workspace_id) as db:
            first = await execute_tool(
                db, workspace_id=workspace_id, tool_name="book_appointment",
                tool_input={"preferred_date": "tomorrow", "preferred_time": "morning"},
                idempotency_key=key, contact_id=contact_id,
            )
            second = await execute_tool(
                db, workspace_id=workspace_id, tool_name="book_appointment",
                tool_input={"preferred_date": "next week", "preferred_time": "evening"},  # different input — must still short-circuit
                idempotency_key=key, contact_id=contact_id,
            )
            appt_result = await db.execute(select(Appointment).where(Appointment.workspace_id == workspace_id))
            appointments = appt_result.scalars().all()

        assert first.id == second.id
        assert first.output == second.output
        assert len(appointments) == 1
    finally:
        await _cleanup(workspace_id)
