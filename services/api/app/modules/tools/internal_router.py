from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from jkr_db.models.calls import CallSession
from jkr_db.models.contacts import Contact
from jkr_db.models.tenancy import Workspace
from jkr_db.session import workspace_scoped_session
from jkr_db.tools_engine import ToolInputError, ToolNotDefinedError, ToolNotEnabledError, execute_tool
from pydantic import BaseModel
from sqlalchemy import select

logger = logging.getLogger("jkr_api.internal_tools")
router = APIRouter(prefix="/internal/tools", tags=["internal-tools"])


class DograhBookAppointmentRequest(BaseModel):
    call_session_id: str | None = None
    workspace_id: str | None = None
    contact_name: str | None = "Caller"
    phone_number: str | None = None
    preferred_date: str
    preferred_time: str | None = "11:00 AM"
    service_type: str | None = "Dental Consultation"


class DograhSendWhatsAppRequest(BaseModel):
    call_session_id: str | None = None
    workspace_id: str | None = None
    phone_number: str
    message_text: str


class DograhCallTransferRequest(BaseModel):
    call_session_id: str | None = None
    reason: str | None = "Caller requested human supervisor"
    target: str | None = None


async def _resolve_call_context(
    call_session_id_str: str | None,
    phone_number: str | None,
    contact_name: str | None,
) -> tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]:
    """Resolves (workspace_id, call_session_id, contact_id) for internal webhook calls."""
    # 1. Try finding call session if ID provided
    if call_session_id_str:
        try:
            cs_id = uuid.UUID(call_session_id_str)
            # Find workspace from call session across DB
            from jkr_db.session import get_engine
            from sqlalchemy.ext.asyncio import AsyncSession
            engine = get_engine()
            async with AsyncSession(engine) as session:
                res = await session.execute(
                    select(CallSession).where(CallSession.id == cs_id)
                )
                call_sess = res.scalar_one_or_none()
                if call_sess:
                    return call_sess.workspace_id, call_sess.id, call_sess.contact_id
        except Exception as exc:
            logger.warning("Could not resolve call session ID %s: %s", call_session_id_str, exc)

    # 2. Fallback to default workspace
    from jkr_db.session import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    engine = get_engine()
    async with AsyncSession(engine) as session:
        ws_res = await session.execute(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
        ws = ws_res.scalar_one_or_none()
        if not ws:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No workspace configured in database")
        workspace_id = ws.id

    # 3. Resolve or create contact in workspace
    async with workspace_scoped_session(workspace_id) as session:
        contact_id = None
        if phone_number:
            c_res = await session.execute(
                select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == phone_number)
            )
            contact = c_res.scalar_one_or_none()
            if not contact:
                contact = Contact(
                    workspace_id=workspace_id,
                    full_name=contact_name or "Caller",
                    phone_e164=phone_number,
                )
                session.add(contact)
                await session.flush()
            contact_id = contact.id

    return workspace_id, None, contact_id


@router.post("/book_appointment")
async def internal_book_appointment(payload: DograhBookAppointmentRequest) -> dict[str, Any]:
    """Endpoint invoked by Dograh's workflow engine when book_appointment tool is triggered."""
    workspace_id, call_session_id, contact_id = await _resolve_call_context(
        payload.call_session_id, payload.phone_number, payload.contact_name
    )

    tool_input = {
        "preferred_date": payload.preferred_date,
        "preferred_time": payload.preferred_time,
        "service_type": payload.service_type,
        "contact_name": payload.contact_name,
        "phone_number": payload.phone_number,
    }

    async with workspace_scoped_session(workspace_id) as session:
        try:
            execution = await execute_tool(
                session,
                workspace_id=workspace_id,
                tool_name="book_appointment",
                tool_input=tool_input,
                call_session_id=call_session_id,
                contact_id=contact_id,
                idempotency_key=f"dograh-book-{uuid.uuid4().hex[:12]}",
            )
            return {
                "success": execution.status == "succeeded",
                "status": execution.status,
                "execution_id": str(execution.id),
                "output": execution.output,
                "error": execution.error,
            }
        except (ToolNotDefinedError, ToolNotEnabledError, ToolInputError) as exc:
            logger.error("Internal book_appointment error: %s", exc)
            return {
                "success": False,
                "status": "failed",
                "error": str(exc),
                "output": {"confirmed": False, "reason": str(exc)},
            }


@router.post("/send_whatsapp")
async def internal_send_whatsapp(payload: DograhSendWhatsAppRequest) -> dict[str, Any]:
    """Endpoint invoked by Dograh's workflow engine when send_whatsapp tool is triggered."""
    workspace_id, call_session_id, contact_id = await _resolve_call_context(
        payload.call_session_id, payload.phone_number, None
    )

    tool_input = {
        "phone_number": payload.phone_number,
        "message_text": payload.message_text,
        "body": payload.message_text,
    }

    async with workspace_scoped_session(workspace_id) as session:
        try:
            execution = await execute_tool(
                session,
                workspace_id=workspace_id,
                tool_name="send_whatsapp",
                tool_input=tool_input,
                call_session_id=call_session_id,
                contact_id=contact_id,
                idempotency_key=f"dograh-wa-{uuid.uuid4().hex[:12]}",
            )
            return {
                "success": execution.status == "succeeded",
                "status": execution.status,
                "execution_id": str(execution.id),
                "output": execution.output,
                "error": execution.error,
            }
        except (ToolNotDefinedError, ToolNotEnabledError, ToolInputError) as exc:
            logger.error("Internal send_whatsapp error: %s", exc)
            return {
                "success": False,
                "status": "failed",
                "error": str(exc),
            }


@router.post("/call_transfer")
async def internal_call_transfer(payload: DograhCallTransferRequest) -> dict[str, Any]:
    """Endpoint invoked by Dograh's workflow engine when call_transfer is triggered."""
    return {
        "success": True,
        "action": "transfer",
        "target": payload.target or "sip:supervisor@jkr.internal",
        "reason": payload.reason,
    }
