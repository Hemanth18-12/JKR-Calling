from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from jkr_db.phone import mask_for_display
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.contacts import service
from app.modules.contacts.schemas import (
    ConsentEventCreate,
    ConsentEventOut,
    ContactCreate,
    ContactDetail,
    ContactOut,
    SegmentCreate,
    SegmentOut,
    SuppressionCreate,
    SuppressionOut,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(
    payload: ContactCreate,
    auth: AuthContext = Depends(require_permission("contacts:create")),
    db: AsyncSession = Depends(workspace_db_for("contacts:create")),
) -> ContactOut:
    contact = await service.create_contact(
        db, workspace_id=auth.workspace_id, full_name=payload.full_name, phone=payload.phone, email=payload.email,
        preferred_language=payload.preferred_language, location=payload.location, lead_source=payload.lead_source,
    )
    return ContactOut(**service.contact_out(contact))


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    auth: AuthContext = Depends(require_permission("contacts:view")),
    db: AsyncSession = Depends(workspace_db_for("contacts:view")),
) -> list[ContactOut]:
    contacts = await service.list_contacts(db, workspace_id=auth.workspace_id)
    return [ContactOut(**service.contact_out(c)) for c in contacts]


@router.get("/{contact_id}", response_model=ContactDetail)
async def get_contact(
    contact_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("contacts:view")),
    db: AsyncSession = Depends(workspace_db_for("contacts:view")),
) -> ContactDetail:
    contact = await service.get_contact(db, workspace_id=auth.workspace_id, contact_id=contact_id)
    unmasked = "contacts:view_unmasked" in auth.permissions or auth.user.is_platform_super_admin
    return ContactDetail(**service.contact_out(contact), phone_e164=contact.phone_e164 if unmasked else None)


@router.post("/{contact_id}/consent", response_model=ConsentEventOut, status_code=201)
async def record_consent(
    contact_id: uuid.UUID,
    payload: ConsentEventCreate,
    auth: AuthContext = Depends(require_permission("contacts:edit")),
    db: AsyncSession = Depends(workspace_db_for("contacts:edit")),
) -> ConsentEventOut:
    event = await service.record_consent(
        db, workspace_id=auth.workspace_id, contact_id=contact_id, purpose=payload.purpose, source=payload.source,
        campaign_category=payload.campaign_category, evidence_url=payload.evidence_url, expires_at=payload.expires_at,
    )
    return ConsentEventOut.model_validate(event)


@router.get("/{contact_id}/consent", response_model=list[ConsentEventOut])
async def list_consent_events(
    contact_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("contacts:view")),
    db: AsyncSession = Depends(workspace_db_for("contacts:view")),
) -> list[ConsentEventOut]:
    events = await service.list_consent_events(db, workspace_id=auth.workspace_id, contact_id=contact_id)
    return [ConsentEventOut.model_validate(e) for e in events]


@router.post("/suppression", response_model=SuppressionOut, status_code=201)
async def add_suppression(
    payload: SuppressionCreate,
    auth: AuthContext = Depends(require_permission("contacts:suppress")),
    db: AsyncSession = Depends(workspace_db_for("contacts:suppress")),
) -> SuppressionOut:
    entry = await service.suppress(
        db, workspace_id=auth.workspace_id, phone=payload.phone, reason=payload.reason, note=payload.note,
        created_by=auth.user.id,
    )
    return SuppressionOut(
        id=entry.id, contact_id=entry.contact_id, phone_masked=mask_for_display(entry.phone_e164),
        reason=entry.reason, note=entry.note, created_at=entry.created_at,
    )


@router.get("/suppression/list", response_model=list[SuppressionOut])
async def list_suppression(
    auth: AuthContext = Depends(require_permission("contacts:view")),
    db: AsyncSession = Depends(workspace_db_for("contacts:view")),
) -> list[SuppressionOut]:
    entries = await service.list_suppression_entries(db, workspace_id=auth.workspace_id)
    return [
        SuppressionOut(
            id=e.id, contact_id=e.contact_id, phone_masked=mask_for_display(e.phone_e164),
            reason=e.reason, note=e.note, created_at=e.created_at,
        )
        for e in entries
    ]


@router.post("/segments", response_model=SegmentOut, status_code=201)
async def create_segment(
    payload: SegmentCreate,
    auth: AuthContext = Depends(require_permission("contacts:create")),
    db: AsyncSession = Depends(workspace_db_for("contacts:create")),
) -> SegmentOut:
    segment = await service.create_segment(
        db, workspace_id=auth.workspace_id, name=payload.name, description=payload.description,
        contact_ids=payload.contact_ids,
    )
    return SegmentOut(id=segment.id, name=segment.name, description=segment.description, member_count=len(payload.contact_ids))


@router.get("/segments/list", response_model=list[SegmentOut])
async def list_segments(
    auth: AuthContext = Depends(require_permission("contacts:view")),
    db: AsyncSession = Depends(workspace_db_for("contacts:view")),
) -> list[SegmentOut]:
    rows = await service.list_segments(db, workspace_id=auth.workspace_id)
    return [
        SegmentOut(id=r["segment"].id, name=r["segment"].name, description=r["segment"].description, member_count=r["member_count"])
        for r in rows
    ]
