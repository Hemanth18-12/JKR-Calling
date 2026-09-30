from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import platform_db
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.operations import service
from app.modules.operations.schemas import AppointmentCreate, AppointmentOut, FollowUpTaskOut, HumanHandoffOut

router = APIRouter(tags=["operations"])


@router.get("/follow-ups", response_model=list[FollowUpTaskOut])
async def list_follow_ups(
    status: str | None = Query(default=None),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> list[FollowUpTaskOut]:
    rows = await service.list_follow_ups(db, workspace_id=auth.workspace_id, status_filter=status)
    return [FollowUpTaskOut(**r) for r in rows]


@router.post("/follow-ups/{task_id}/complete", response_model=FollowUpTaskOut)
async def complete_follow_up(
    task_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("contacts:edit")),
    db: AsyncSession = Depends(workspace_db_for("contacts:edit")),
) -> FollowUpTaskOut:
    task = await service.complete_follow_up(db, workspace_id=auth.workspace_id, task_id=task_id)
    rows = await service.list_follow_ups(db, workspace_id=auth.workspace_id, status_filter=None)
    return next(FollowUpTaskOut(**r) for r in rows if r["id"] == task.id)


@router.get("/handoffs", response_model=list[HumanHandoffOut])
async def list_handoffs(
    status: str | None = Query(default=None),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> list[HumanHandoffOut]:
    rows = await service.list_handoffs(db, workspace_id=auth.workspace_id, status_filter=status)
    return [HumanHandoffOut(**r) for r in rows]


class HandoffActionRequest(BaseModel):
    action: str


@router.post("/handoffs/{handoff_id}/action", response_model=HumanHandoffOut)
async def act_on_handoff(
    handoff_id: uuid.UUID,
    payload: HandoffActionRequest,
    auth: AuthContext = Depends(require_permission("calls:transfer")),
    db: AsyncSession = Depends(workspace_db_for("calls:transfer")),
) -> HumanHandoffOut:
    await service.resolve_handoff(db, workspace_id=auth.workspace_id, handoff_id=handoff_id, resolver_id=auth.user.id, action=payload.action)
    rows = await service.list_handoffs(db, workspace_id=auth.workspace_id, status_filter=None)
    return next(HumanHandoffOut(**r) for r in rows if r["id"] == handoff_id)


@router.get("/appointments", response_model=list[AppointmentOut])
async def list_appointments(
    status: str | None = Query(default=None),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> list[AppointmentOut]:
    rows = await service.list_appointments(db, workspace_id=auth.workspace_id, status_filter=status)
    return [AppointmentOut(**r) for r in rows]


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
async def create_appointment_endpoint(
    payload: AppointmentCreate,
    auth: AuthContext = Depends(require_permission("contacts:edit")),
    db: AsyncSession = Depends(workspace_db_for("contacts:edit")),
) -> AppointmentOut:
    row = await service.create_appointment(
        db,
        workspace_id=auth.workspace_id,
        contact_id=payload.contact_id,
        customer_name=payload.customer_name,
        phone=payload.phone,
        scheduled_for=payload.scheduled_for,
        duration_minutes=payload.duration_minutes,
        location=payload.location,
        notes=payload.notes,
    )
    return AppointmentOut(**row)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("contacts:edit")),
    db: AsyncSession = Depends(workspace_db_for("contacts:edit")),
) -> AppointmentOut:
    await service.cancel_appointment(db, workspace_id=auth.workspace_id, appointment_id=appointment_id)
    rows = await service.list_appointments(db, workspace_id=auth.workspace_id, status_filter=None)
    return next(AppointmentOut(**r) for r in rows if r["id"] == appointment_id)


@router.get("/appointments/export/csv")
async def export_appointments_csv_endpoint(
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> Response:
    csv_text = await service.export_appointments_csv(db, workspace_id=auth.workspace_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="appointments-export.csv"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/appointments/{appointment_id}/invite.ics")
async def download_appointment_ics(
    appointment_id: uuid.UUID,
    db: AsyncSession = Depends(platform_db),
) -> Response:
    ics_text, filename = await service.get_appointment_ics(db, appointment_id=appointment_id)
    return Response(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )

