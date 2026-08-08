"""Mock business-tool execution engine (spec §17/§18) — shared by voice-worker
(in-call tools like `book_appointment`, fired mid-conversation) and
intelligence-worker (post-call follow-up tools like `send_whatsapp`), so both
write `tool_executions` audit rows through one real, idempotency-checked path
rather than two divergent ad hoc ones. Lives in packages/db for the same
reason `safety_gate.py` does — see that module's docstring.

Only `book_appointment`, `reschedule_appointment`, `cancel_appointment`,
`create_human_callback`, `send_whatsapp`, and `send_sms` have real local side
effects (they write to schema this codebase actually models —
`appointments`/`human_handoffs`/`messages`). `check_calendar_slots`,
`create_crm_lead`, `update_crm_stage`, and `send_email` are mock-only this
pass: there's no real calendar/CRM/email integration built yet (that's a
later pass's "integrations" work), so they return a synthetic response and
write nothing beyond the `tool_executions` audit row itself — never silently
pretended to be real.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.models.agents import AgentTool, ToolDefinition
from jkr_db.models.tools import Appointment, HumanHandoff, Message, ToolExecution

REAL_SIDE_EFFECT_TOOLS = {
    "book_appointment", "reschedule_appointment", "cancel_appointment", "create_human_callback", "send_whatsapp", "send_sms",
}


class ToolNotDefinedError(Exception):
    pass


class ToolNotEnabledError(Exception):
    pass


class ToolInputError(Exception):
    pass


# Deliberately forgiving, not a real NLU date parser — MockLLM's captured
# fields are whatever free text the customer/mock-customer said (e.g.
# "Saturday morning" from a human, or a generic canned reply like "Sure,
# tell me more about that." from campaign-worker's auto-play — see
# services/campaign-worker/app/dialer.py). Recognizes a handful of common
# day-name/relative-day patterns and a time-of-day word; anything else
# falls back to a sane default (3 days out, 11:00) rather than failing the
# whole tool call over an unparseable date, which would be a worse UX than
# a slightly-wrong slot the human team confirms anyway (spec §17: tool
# outputs are provisional until a human confirms).
_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_TIME_WORDS = {"morning": 10, "afternoon": 14, "evening": 18, "night": 20}
_HOUR_PATTERN = re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.IGNORECASE)


def parse_fuzzy_datetime(date_text: str | None, time_text: str | None, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    combined = f"{date_text or ''} {time_text or ''}".lower()

    target_date = now + timedelta(days=3)
    if "tomorrow" in combined:
        target_date = now + timedelta(days=1)
    else:
        for offset, day_name in enumerate(_DAY_NAMES):
            if day_name in combined:
                days_ahead = (offset - now.weekday()) % 7
                target_date = now + timedelta(days=days_ahead or 7)
                break

    hour = 11
    hour_match = _HOUR_PATTERN.search(combined)
    if hour_match:
        raw_hour = int(hour_match.group(1)) % 12
        hour = raw_hour + (12 if hour_match.group(2).lower() == "pm" else 0)
    else:
        for word, word_hour in _TIME_WORDS.items():
            if word in combined:
                hour = word_hour
                break

    return target_date.replace(hour=hour, minute=0, second=0, microsecond=0)


async def execute_tool(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_name: str,
    tool_input: dict,
    idempotency_key: str,
    call_session_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    agent_version_id: uuid.UUID | None = None,
) -> ToolExecution:
    """Idempotent: replaying the same `idempotency_key` returns the original
    execution rather than running the tool twice — this is what makes it
    safe for a Dramatiq actor with `max_retries` to call this (see
    services/intelligence-worker/app/pipeline.py's follow-up dispatch).

    `agent_version_id` (voice-worker only — intelligence-worker's follow-up
    dispatch has no single agent "using" the tool, so it omits this) also
    enforces the per-agent-version `AgentTool.enabled` toggle from the Agent
    Studio Tools tab, not just the workspace-wide `ToolDefinition.is_enabled`
    — a version with no `AgentTool` row for this tool is treated as enabled,
    matching `seed_default_agent_tools`'s all-on default."""
    existing = await db.execute(
        select(ToolExecution).where(ToolExecution.workspace_id == workspace_id, ToolExecution.idempotency_key == idempotency_key)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        return existing_row

    definition_result = await db.execute(
        select(ToolDefinition).where(ToolDefinition.workspace_id == workspace_id, ToolDefinition.name == tool_name)
    )
    definition = definition_result.scalar_one_or_none()
    if definition is None:
        raise ToolNotDefinedError(f"Tool '{tool_name}' has no ToolDefinition in this workspace")
    if not definition.is_enabled:
        raise ToolNotEnabledError(f"Tool '{tool_name}' is disabled in this workspace")

    if agent_version_id is not None:
        agent_tool_result = await db.execute(
            select(AgentTool.enabled).where(AgentTool.agent_version_id == agent_version_id, AgentTool.tool_definition_id == definition.id)
        )
        agent_tool_enabled = agent_tool_result.scalar_one_or_none()
        if agent_tool_enabled is False:
            raise ToolNotEnabledError(f"Tool '{tool_name}' is disabled for this agent version")

    now = datetime.now(UTC)
    execution = ToolExecution(
        workspace_id=workspace_id, call_session_id=call_session_id, tool_definition_id=definition.id,
        status="running", input=tool_input, idempotency_key=idempotency_key, started_at=now,
    )
    db.add(execution)
    await db.flush()

    try:
        output = await _dispatch(
            db, tool_name=tool_name, workspace_id=workspace_id, call_session_id=call_session_id,
            contact_id=contact_id, tool_input=tool_input,
        )
        execution.status = "succeeded"
        execution.output = output
    except ToolInputError as exc:
        execution.status = "failed"
        execution.error = str(exc)
    execution.completed_at = datetime.now(UTC)
    await db.flush()
    return execution


async def _dispatch(
    db: AsyncSession, *, tool_name: str, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None,
    contact_id: uuid.UUID | None, tool_input: dict,
) -> dict:
    if tool_name == "check_calendar_slots":
        return _run_check_calendar_slots()
    if tool_name == "book_appointment":
        return await _run_book_appointment(db, workspace_id=workspace_id, call_session_id=call_session_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name == "reschedule_appointment":
        return await _run_reschedule_appointment(db, workspace_id=workspace_id, tool_input=tool_input)
    if tool_name == "cancel_appointment":
        return await _run_cancel_appointment(db, workspace_id=workspace_id, tool_input=tool_input)
    if tool_name == "create_human_callback":
        return await _run_create_human_callback(db, workspace_id=workspace_id, call_session_id=call_session_id, tool_input=tool_input)
    if tool_name in ("send_whatsapp", "send_sms"):
        return await _run_send_message(db, channel="whatsapp" if tool_name == "send_whatsapp" else "sms", workspace_id=workspace_id, contact_id=contact_id, tool_input=tool_input)
    # create_crm_lead / update_crm_stage / send_email — mock-only, see module docstring.
    return {"mock": True, "tool": tool_name, "note": "No external integration configured this pass — synthetic response.", "external_ref": f"mock-{uuid.uuid4()}"}


def _run_check_calendar_slots() -> dict:
    base = datetime.now(UTC) + timedelta(days=2)
    slots = [(base + timedelta(days=i)).replace(hour=11, minute=0, second=0, microsecond=0).isoformat() for i in range(3)]
    return {"available_slots": slots}


async def _run_book_appointment(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None, contact_id: uuid.UUID | None, tool_input: dict,
) -> dict:
    if contact_id is None:
        raise ToolInputError("book_appointment requires a contact_id (no real contact attached to this call)")
    scheduled_for = parse_fuzzy_datetime(tool_input.get("preferred_date"), tool_input.get("preferred_time"))
    appointment = Appointment(
        workspace_id=workspace_id, contact_id=contact_id, call_session_id=call_session_id,
        scheduled_for=scheduled_for, duration_minutes=30, status="scheduled",
        notes=tool_input.get("reason_for_visit"),
    )
    db.add(appointment)
    await db.flush()
    return {"appointment_id": str(appointment.id), "scheduled_for": scheduled_for.isoformat()}


async def _get_workspace_appointment(db: AsyncSession, *, workspace_id: uuid.UUID, appointment_id: str) -> Appointment:
    try:
        parsed_id = uuid.UUID(appointment_id)
    except (ValueError, TypeError) as exc:
        raise ToolInputError("appointment_id is required and must be a valid UUID") from exc
    result = await db.execute(select(Appointment).where(Appointment.id == parsed_id, Appointment.workspace_id == workspace_id))
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise ToolInputError(f"Appointment {appointment_id} not found in this workspace")
    return appointment


async def _run_reschedule_appointment(db: AsyncSession, *, workspace_id: uuid.UUID, tool_input: dict) -> dict:
    appointment = await _get_workspace_appointment(db, workspace_id=workspace_id, appointment_id=tool_input.get("appointment_id", ""))
    appointment.scheduled_for = parse_fuzzy_datetime(tool_input.get("preferred_date"), tool_input.get("preferred_time"))
    appointment.status = "rescheduled"
    await db.flush()
    return {"appointment_id": str(appointment.id), "scheduled_for": appointment.scheduled_for.isoformat()}


async def _run_cancel_appointment(db: AsyncSession, *, workspace_id: uuid.UUID, tool_input: dict) -> dict:
    appointment = await _get_workspace_appointment(db, workspace_id=workspace_id, appointment_id=tool_input.get("appointment_id", ""))
    appointment.status = "cancelled"
    await db.flush()
    return {"appointment_id": str(appointment.id)}


async def _run_create_human_callback(db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None, tool_input: dict) -> dict:
    if call_session_id is None:
        raise ToolInputError("create_human_callback requires a call_session_id")
    handoff = HumanHandoff(
        workspace_id=workspace_id, call_session_id=call_session_id,
        reason=tool_input.get("reason", "customer_requested"), status="pending",
        packet=tool_input.get("packet", {}),
    )
    db.add(handoff)
    await db.flush()
    return {"handoff_id": str(handoff.id)}


async def _run_send_message(db: AsyncSession, *, channel: str, workspace_id: uuid.UUID, contact_id: uuid.UUID | None, tool_input: dict) -> dict:
    if contact_id is None:
        raise ToolInputError(f"send_{channel} requires a contact_id")
    now = datetime.now(UTC)
    message = Message(
        workspace_id=workspace_id, contact_id=contact_id, channel=channel, direction="outbound",
        body=tool_input.get("body", ""), status="sent", sent_at=now,
    )
    db.add(message)
    await db.flush()
    return {"message_id": str(message.id)}
