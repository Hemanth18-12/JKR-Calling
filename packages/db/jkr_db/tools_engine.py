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

import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.models.agents import AgentTool, ToolDefinition
from jkr_db.models.contacts import Contact
from jkr_db.models.knowledge import KnowledgeChunk, RetrievalEvent
from jkr_db.models.tools import Appointment, FollowUpTask, HumanHandoff, Message, ToolExecution

REAL_SIDE_EFFECT_TOOLS = {
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "create_human_callback",
    "transfer_call",
    "send_whatsapp",
    "send_sms",
    "send_email",
    "check_availability",
    "check_calendar_slots",
    "create_lead",
    "create_crm_lead",
    "update_lead",
    "update_crm_stage",
    "create_followup",
    "get_information",
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


def _normalize_phone_number(raw_phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", (raw_phone or "").strip())
    if not cleaned:
        return ""
    if not cleaned.startswith("+"):
        if len(cleaned) == 10 and cleaned.startswith(("6", "7", "8", "9")):
            cleaned = "+91" + cleaned
        else:
            cleaned = "+" + cleaned
    return cleaned


async def _dispatch(
    db: AsyncSession, *, tool_name: str, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None,
    contact_id: uuid.UUID | None, tool_input: dict,
) -> dict:
    if tool_name in ("check_calendar_slots", "check_availability"):
        return _run_check_calendar_slots(tool_input)
    if tool_name == "book_appointment":
        return await _run_book_appointment(db, workspace_id=workspace_id, call_session_id=call_session_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name == "reschedule_appointment":
        return await _run_reschedule_appointment(db, workspace_id=workspace_id, tool_input=tool_input)
    if tool_name == "cancel_appointment":
        return await _run_cancel_appointment(db, workspace_id=workspace_id, tool_input=tool_input)
    if tool_name in ("create_human_callback", "transfer_call"):
        return await _run_create_human_callback(db, workspace_id=workspace_id, call_session_id=call_session_id, tool_input=tool_input)
    if tool_name in ("send_whatsapp", "send_sms"):
        return await _run_send_message(db, channel="whatsapp" if tool_name == "send_whatsapp" else "sms", workspace_id=workspace_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name in ("create_crm_lead", "create_lead"):
        return await _run_create_lead(db, workspace_id=workspace_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name in ("update_crm_stage", "update_lead"):
        return await _run_update_lead(db, workspace_id=workspace_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name == "create_followup":
        return await _run_create_followup(db, workspace_id=workspace_id, call_session_id=call_session_id, contact_id=contact_id, tool_input=tool_input)
    if tool_name == "get_information":
        return await _run_get_information(db, workspace_id=workspace_id, call_session_id=call_session_id, tool_input=tool_input)
    if tool_name == "send_email":
        return _run_send_email(tool_input)
    return {"mock": True, "tool": tool_name, "note": "No external integration configured this pass — synthetic response.", "external_ref": f"mock-{uuid.uuid4()}"}


def _run_check_calendar_slots(tool_input: dict | None = None) -> dict:
    pref_date = (tool_input or {}).get("preferred_date") or (tool_input or {}).get("date")
    base = parse_fuzzy_datetime(pref_date, None) if pref_date else (datetime.now(UTC) + timedelta(days=2))
    slots = [(base + timedelta(days=i)).replace(hour=11, minute=0, second=0, microsecond=0).isoformat() for i in range(3)]
    return {"available_slots": slots, "service": (tool_input or {}).get("service_type", "General Consultation")}


async def _get_workspace_contact(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    """Same shape as _get_workspace_appointment below — a contact_id alone
    is never trusted as proof it belongs to this workspace (RLS scopes what
    a SELECT can *see*, but a blind INSERT using a caller-supplied
    contact_id would otherwise create a row in this workspace that
    references another tenant's contact). Raises the same ToolInputError a
    missing contact_id already raises, so a cross-tenant contact_id and a
    nonexistent one fail identically — never leaking which case it was."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise ToolInputError(f"Contact {contact_id} not found in this workspace")
    return contact


async def _run_book_appointment(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None, contact_id: uuid.UUID | None, tool_input: dict,
) -> dict:
    if contact_id is None:
        raise ToolInputError("book_appointment requires a contact_id (no real contact attached to this call)")
    await _get_workspace_contact(db, workspace_id=workspace_id, contact_id=contact_id)
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


async def _dispatch_twilio_message(*, channel: str, to_e164: str, body: str) -> tuple[str, str | None, str | None]:
    """Sends real WhatsApp or SMS message via Twilio REST API.
    Returns (status, provider_message_id, error_detail).
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not (account_sid and auth_token):
        logger.info("Twilio credentials not configured — recorded %s message locally as mock_sent", channel)
        return ("mock_sent", f"mock-{uuid.uuid4()}", None)

    clean_to = _normalize_phone_number(to_e164)
    if channel == "whatsapp":
        from_param = whatsapp_from if whatsapp_from.startswith("whatsapp:") else f"whatsapp:{whatsapp_from}"
        to_param = clean_to if clean_to.startswith("whatsapp:") else f"whatsapp:{clean_to}"
    else:
        from_param = from_number
        to_param = clean_to

    if not from_param:
        return ("failed", None, "Sender phone number (TWILIO_FROM_NUMBER / TWILIO_WHATSAPP_FROM) not configured")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    try:
        async with httpx.AsyncClient(timeout=10.0, auth=(account_sid, auth_token)) as client:
            response = await client.post(
                url,
                data={
                    "From": from_param,
                    "To": to_param,
                    "Body": body,
                },
            )
            if response.status_code < 400:
                data = response.json()
                msg_sid = data.get("sid")
                logger.info("Twilio %s dispatched successfully: SID %s to %s", channel, msg_sid, to_param)
                return ("sent", msg_sid, None)
            else:
                err_text = response.text
                if "63015" in err_text or "could not find recipient" in err_text.lower():
                    detailed_err = (
                        f"Twilio WhatsApp Sandbox Error 63015: Recipient '{to_param}' has not joined Sandbox. "
                        f"Recipient must send Sandbox Join Code (e.g. 'join <keyword>') to +14155238886 first."
                    )
                elif "21608" in err_text or "unverified" in err_text.lower():
                    detailed_err = f"Twilio Trial Restriction: Recipient '{to_param}' is unverified in your Twilio account."
                else:
                    detailed_err = f"Twilio HTTP {response.status_code}: {err_text}"
                logger.warning("Twilio %s failed (HTTP %s): %s", channel, response.status_code, detailed_err)
                return ("failed", None, detailed_err)
    except Exception as exc:
        logger.exception("Error dispatching Twilio %s message: %s", channel, exc)
        return ("failed", None, str(exc))


async def _run_send_message(db: AsyncSession, *, channel: str, workspace_id: uuid.UUID, contact_id: uuid.UUID | None, tool_input: dict) -> dict:
    if contact_id is None:
        raise ToolInputError(f"send_{channel} requires a contact_id")
    contact = await _get_workspace_contact(db, workspace_id=workspace_id, contact_id=contact_id)
    body = tool_input.get("body", "")
    now = datetime.now(UTC)

    msg_status, provider_msg_id, error_detail = await _dispatch_twilio_message(
        channel=channel, to_e164=contact.phone_e164, body=body
    )

    message = Message(
        workspace_id=workspace_id,
        contact_id=contact_id,
        channel=channel,
        direction="outbound",
        body=body,
        status=msg_status,
        provider_message_id=provider_msg_id,
        sent_at=now if msg_status in ("sent", "mock_sent") else None,
    )
    db.add(message)
    await db.flush()
    return {
        "message_id": str(message.id),
        "status": msg_status,
        "provider_message_id": provider_msg_id,
        "error": error_detail,
    }


async def _run_create_lead(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID | None, tool_input: dict) -> dict:
    name = tool_input.get("name") or tool_input.get("full_name") or "New Inbound Lead"
    phone = tool_input.get("phone") or tool_input.get("phone_e164") or ""
    tags = tool_input.get("tags") or ["ai-lead", "inbound"]
    normalized_phone = _normalize_phone_number(phone) if phone else ""

    contact = None
    if contact_id:
        result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
        contact = result.scalar_one_or_none()
    elif normalized_phone:
        result = await db.execute(select(Contact).where(Contact.phone_e164 == normalized_phone, Contact.workspace_id == workspace_id))
        contact = result.scalar_one_or_none()

    if contact is None and normalized_phone:
        contact = Contact(
            workspace_id=workspace_id,
            phone_e164=normalized_phone,
            full_name=name,
            tags=tags,
            consent_obtained=True,
            consent_method="ai_call",
        )
        db.add(contact)
        await db.flush()
    elif contact:
        contact.tags = list(set((contact.tags or []) + tags))
        await db.flush()

    return {
        "status": "created" if contact else "mock_lead_created",
        "lead_id": str(contact.id) if contact else f"lead-{uuid.uuid4()}",
        "name": name,
        "phone": normalized_phone,
    }


async def _run_update_lead(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID | None, tool_input: dict) -> dict:
    stage = tool_input.get("stage") or tool_input.get("pipeline_stage") or "qualified"
    tags = tool_input.get("tags") or [stage]

    if contact_id:
        result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
        contact = result.scalar_one_or_none()
        if contact:
            contact.tags = list(set((contact.tags or []) + tags))
            await db.flush()
            return {"status": "updated", "contact_id": str(contact.id), "stage": stage, "tags": contact.tags}

    return {"status": "updated", "stage": stage, "mock": True}


async def _run_create_followup(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None, contact_id: uuid.UUID | None, tool_input: dict
) -> dict:
    if contact_id is None:
        raise ToolInputError("create_followup requires a contact_id")
    await _get_workspace_contact(db, workspace_id=workspace_id, contact_id=contact_id)

    channel = tool_input.get("channel", "whatsapp")
    reason = tool_input.get("reason", "follow_up_requested")
    preferred_date = tool_input.get("preferred_date")
    preferred_time = tool_input.get("preferred_time")
    scheduled_for = parse_fuzzy_datetime(preferred_date, preferred_time) if (preferred_date or preferred_time) else None

    follow_up = FollowUpTask(
        workspace_id=workspace_id,
        contact_id=contact_id,
        call_session_id=call_session_id,
        channel=channel,
        status="pending",
        scheduled_for=scheduled_for,
        payload={"reason": reason, "scheduled_for": scheduled_for.isoformat() if scheduled_for else None},
    )
    db.add(follow_up)
    await db.flush()
    return {
        "follow_up_id": str(follow_up.id),
        "channel": channel,
        "status": "pending",
        "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
    }


async def _run_get_information(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID | None, tool_input: dict
) -> dict:
    query = tool_input.get("query") or tool_input.get("question") or ""
    if not query:
        return {"query": "", "answer": "No query provided.", "found": False, "confidence": 0.0}

    keywords = [k.strip().lower() for k in query.split() if len(k.strip()) > 3]
    chunks_result = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.workspace_id == workspace_id).limit(25)
    )
    chunks = chunks_result.scalars().all()

    best_chunk = None
    best_score = 0.0
    matched_ids = []

    for chunk in chunks:
        chunk_lower = chunk.text.lower()
        matches = sum(1 for kw in keywords if kw in chunk_lower) if keywords else 0
        score = matches / max(len(keywords), 1) if keywords else 0.2
        if score > best_score:
            best_score = score
            best_chunk = chunk
            matched_ids.append(chunk.id)

    confidence = min(round(best_score if best_chunk else 0.25, 2), 0.95)
    answer = (
        best_chunk.text
        if best_chunk and confidence >= 0.4
        else "I don't have that specific information right now, but I will make a note for our team to follow up with you."
    )
    found = best_chunk is not None and confidence >= 0.4

    retrieval_event = RetrievalEvent(
        workspace_id=workspace_id,
        call_session_id=call_session_id,
        query=query,
        matched_chunk_ids=matched_ids[:3],
        top_score=confidence,
        used_in_response=found,
    )
    db.add(retrieval_event)
    await db.flush()

    return {
        "query": query,
        "answer": answer[:350],
        "found": found,
        "confidence": confidence,
        "retrieval_event_id": str(retrieval_event.id),
    }


def _run_send_email(tool_input: dict) -> dict:
    to_email = tool_input.get("to_email") or tool_input.get("email", "")
    subject = tool_input.get("subject", "JKR AI Calling Follow-up")
    body = tool_input.get("body", "")
    return {
        "status": "mock_sent",
        "to_email": to_email,
        "subject": subject,
        "provider_message_id": f"email-mock-{uuid.uuid4()}",
        "note": "Email recorded locally as mock_sent.",
    }
