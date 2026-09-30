"""Read + resolve access to the artifacts calls produce: follow-up tasks,
human handoffs, and appointments. Creation happens elsewhere (the tool
framework, `jkr_db.tools_engine` — see docs/IMPLEMENTATION_CHECKLIST.md
Phase 6) — this module is the operator-facing worklist view over that data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.calls import CallSession
from jkr_db.models.contacts import Contact
from jkr_db.models.tools import Appointment, FollowUpTask, HumanHandoff
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_follow_ups(db: AsyncSession, *, workspace_id: uuid.UUID, status_filter: str | None) -> list[dict]:
    query = (
        select(FollowUpTask, Contact.full_name)
        .join(Contact, Contact.id == FollowUpTask.contact_id)
        .where(FollowUpTask.workspace_id == workspace_id)
        .order_by(FollowUpTask.created_at.desc())
    )
    if status_filter:
        query = query.where(FollowUpTask.status == status_filter)
    result = await db.execute(query)
    return [
        {
            "id": t.id, "contact_id": t.contact_id, "contact_name": name, "call_session_id": t.call_session_id,
            "channel": t.channel, "status": t.status, "scheduled_for": t.scheduled_for, "payload": t.payload,
            "completed_at": t.completed_at, "created_at": t.created_at,
        }
        for t, name in result.all()
    ]


async def complete_follow_up(db: AsyncSession, *, workspace_id: uuid.UUID, task_id: uuid.UUID) -> FollowUpTask:
    result = await db.execute(select(FollowUpTask).where(FollowUpTask.id == task_id, FollowUpTask.workspace_id == workspace_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up task not found")
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    await db.flush()
    return task


async def list_handoffs(db: AsyncSession, *, workspace_id: uuid.UUID, status_filter: str | None) -> list[dict]:
    query = (
        select(HumanHandoff, Contact.full_name)
        .join(CallSession, CallSession.id == HumanHandoff.call_session_id)
        .outerjoin(Contact, Contact.id == CallSession.contact_id)
        .where(HumanHandoff.workspace_id == workspace_id)
        .order_by(HumanHandoff.created_at.desc())
    )
    if status_filter:
        query = query.where(HumanHandoff.status == status_filter)
    result = await db.execute(query)
    return [
        {
            "id": h.id, "call_session_id": h.call_session_id, "contact_name": name, "reason": h.reason,
            "status": h.status, "packet": h.packet, "assigned_to_user_id": h.assigned_to_user_id,
            "resolved_at": h.resolved_at, "created_at": h.created_at,
        }
        for h, name in result.all()
    ]


async def resolve_handoff(db: AsyncSession, *, workspace_id: uuid.UUID, handoff_id: uuid.UUID, resolver_id: uuid.UUID, action: str) -> HumanHandoff:
    result = await db.execute(select(HumanHandoff).where(HumanHandoff.id == handoff_id, HumanHandoff.workspace_id == workspace_id))
    handoff = result.scalar_one_or_none()
    if handoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Handoff not found")
    if action == "accept":
        handoff.status = "accepted"
        handoff.assigned_to_user_id = resolver_id
    elif action == "resolve":
        handoff.status = "resolved"
        handoff.resolved_at = datetime.now(UTC)
    elif action == "abandon":
        handoff.status = "abandoned"
        handoff.resolved_at = datetime.now(UTC)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown action '{action}'")
    await db.flush()
    return handoff


async def list_appointments(db: AsyncSession, *, workspace_id: uuid.UUID, status_filter: str | None) -> list[dict]:
    query = (
        select(Appointment, Contact.full_name)
        .outerjoin(Contact, Contact.id == Appointment.contact_id)
        .where(Appointment.workspace_id == workspace_id)
        .order_by(Appointment.scheduled_for.desc())
    )
    if status_filter:
        query = query.where(Appointment.status == status_filter)
    result = await db.execute(query)
    return [
        {
            "id": a.id, "contact_id": a.contact_id, "contact_name": name or "Customer", "call_session_id": a.call_session_id,
            "scheduled_for": a.scheduled_for, "duration_minutes": a.duration_minutes, "status": a.status,
            "location": a.location, "notes": a.notes, "created_at": a.created_at,
        }
        for a, name in result.all()
    ]


async def create_appointment(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID | None = None,
    customer_name: str | None = None,
    phone: str | None = None,
    scheduled_for: datetime,
    duration_minutes: int = 30,
    location: str | None = None,
    notes: str | None = None,
) -> dict:
    import logging, os
    logger = logging.getLogger(__name__)

    contact = None
    if contact_id is not None:
        res = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
        contact = res.scalar_one_or_none()
    elif phone:
        res = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == phone))
        contact = res.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            workspace_id=workspace_id,
            full_name=customer_name or "New Customer",
            phone_e164=phone or "+919876500000",
            consent_status="granted",
        )
        db.add(contact)
        await db.flush()
        contact_id = contact.id
    else:
        contact_id = contact.id

    appointment = Appointment(
        workspace_id=workspace_id,
        contact_id=contact_id,
        scheduled_for=scheduled_for,
        duration_minutes=duration_minutes,
        status="scheduled",
        location=location or "Main Clinic / Office",
        notes=notes,
    )
    db.add(appointment)
    await db.flush()

    # --- Sync to Google Calendar if connected ---
    try:
        from jkr_db.integrations.google_calendar import (
            create_google_calendar_event,
            get_active_google_calendar_token,
        )
        encryption_key = os.environ.get("CREDENTIALS_ENCRYPTION_KEY", "change_me_dev_only_fernet_key_44_bytes_base64")
        token, cal_id = await get_active_google_calendar_token(db, workspace_id=workspace_id, encryption_key=encryption_key)
        if token:
            name = (contact.full_name if contact else customer_name) or "Customer"
            gcal_event = await create_google_calendar_event(
                access_token=token,
                calendar_id=cal_id,
                summary=f"Appointment: {name}",
                description=f"Confirmed Appointment\nNotes: {notes or 'Scheduled'}\nPhone: {contact.phone_e164 if contact else phone}",
                start_time=scheduled_for,
                duration_minutes=duration_minutes,
                location=location,
            )
            gcal_link = gcal_event.get("htmlLink") or gcal_event.get("id")
            if gcal_link:
                appointment.notes = f"{appointment.notes or ''}\n[Google Calendar: {gcal_link}]".strip()
            await db.flush()
    except Exception as exc:
        logger.warning("Google Calendar sync on manual appointment failed: %s", exc)

    # --- Sync to Google Sheets if connected ---
    try:
        from jkr_db.integrations.google_sheets import (
            append_appointment_row,
            get_active_google_sheets_token,
        )
        encryption_key = os.environ.get("CREDENTIALS_ENCRYPTION_KEY", "change_me_dev_only_fernet_key_44_bytes_base64")
        gs_token, gs_cfg = await get_active_google_sheets_token(db, workspace_id=workspace_id, encryption_key=encryption_key)
        if gs_token and gs_cfg.get("spreadsheet_id"):
            name = (contact.full_name if contact else customer_name) or "Customer"
            await append_appointment_row(
                access_token=gs_token,
                spreadsheet_id=gs_cfg["spreadsheet_id"],
                sheet_name=gs_cfg.get("sheet_name", "Appointments & Leads"),
                values=[
                    scheduled_for.strftime("%Y-%m-%d"),
                    scheduled_for.strftime("%I:%M %p"),
                    name,
                    contact.phone_e164 if contact else phone,
                    notes or "General Appointment",
                    location or "Main Clinic / Office",
                    "Confirmed",
                ],
            )
    except Exception as exc:
        logger.warning("Google Sheets sync on manual appointment failed: %s", exc)

    contact_name = contact.full_name if contact else (customer_name or "Customer")
    return {
        "id": appointment.id,
        "contact_id": appointment.contact_id,
        "contact_name": contact_name,
        "call_session_id": appointment.call_session_id,
        "scheduled_for": appointment.scheduled_for,
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
        "location": appointment.location,
        "notes": appointment.notes,
        "created_at": appointment.created_at,
    }


async def cancel_appointment(db: AsyncSession, *, workspace_id: uuid.UUID, appointment_id: uuid.UUID) -> Appointment:
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id, Appointment.workspace_id == workspace_id))
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    appointment.status = "cancelled"
    await db.flush()
    return appointment
