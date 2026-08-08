from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.contacts import ConsentEvent, Contact, Segment, SegmentMember, SuppressionEntry
from jkr_db.phone import InvalidPhoneNumberError, mask_for_display, normalize_e164
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def contact_out(contact: Contact) -> dict:
    return {
        "id": contact.id,
        "full_name": contact.full_name,
        "phone_masked": mask_for_display(contact.phone_e164),
        "email": contact.email,
        "preferred_language": contact.preferred_language,
        "location": contact.location,
        "lead_source": contact.lead_source,
        "consent_status": contact.consent_status,
        "is_suppressed": contact.is_suppressed,
        "conversion_status": contact.conversion_status,
        "last_call_at": contact.last_call_at,
        "created_at": contact.created_at,
    }


async def create_contact(
    db: AsyncSession, *, workspace_id: uuid.UUID, full_name: str, phone: str, email: str | None,
    preferred_language: str | None, location: str | None, lead_source: str | None,
) -> Contact:
    try:
        phone_e164 = normalize_e164(phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    existing = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == phone_e164)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A contact with this phone number already exists")

    is_suppressed_result = await db.execute(
        select(SuppressionEntry).where(SuppressionEntry.workspace_id == workspace_id, SuppressionEntry.phone_e164 == phone_e164)
    )
    contact = Contact(
        workspace_id=workspace_id, full_name=full_name, phone_e164=phone_e164, email=email,
        preferred_language=preferred_language, location=location, lead_source=lead_source,
        is_suppressed=is_suppressed_result.scalar_one_or_none() is not None,
    )
    db.add(contact)
    await db.flush()
    return contact


async def list_contacts(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Contact]:
    result = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id).order_by(Contact.created_at.desc()))
    return list(result.scalars().all())


async def get_contact(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return contact


async def record_consent(
    db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID, purpose: str, source: str,
    campaign_category: str | None, evidence_url: str | None, expires_at: datetime | None,
) -> ConsentEvent:
    contact = await get_contact(db, workspace_id=workspace_id, contact_id=contact_id)
    event = ConsentEvent(
        workspace_id=workspace_id, contact_id=contact.id, purpose=purpose, source=source,
        campaign_category=campaign_category, evidence_url=evidence_url,
        granted_at=datetime.now(UTC), expires_at=expires_at,
    )
    db.add(event)
    contact.consent_status = "granted"
    await db.flush()
    return event


async def list_consent_events(db: AsyncSession, *, workspace_id: uuid.UUID, contact_id: uuid.UUID) -> list[ConsentEvent]:
    result = await db.execute(
        select(ConsentEvent)
        .where(ConsentEvent.workspace_id == workspace_id, ConsentEvent.contact_id == contact_id)
        .order_by(ConsentEvent.granted_at.desc())
    )
    return list(result.scalars().all())


async def suppress(
    db: AsyncSession, *, workspace_id: uuid.UUID, phone: str, reason: str, note: str | None, created_by: uuid.UUID | None,
) -> SuppressionEntry:
    """Written synchronously, takes effect immediately — no retry/schedule can
    ever call a suppressed contact after this returns (docs/SECURITY_AND_COMPLIANCE.md §3)."""
    try:
        phone_e164 = normalize_e164(phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    existing = await db.execute(
        select(SuppressionEntry).where(SuppressionEntry.workspace_id == workspace_id, SuppressionEntry.phone_e164 == phone_e164)
    )
    entry = existing.scalar_one_or_none()
    if entry is not None:
        return entry

    contact_result = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == phone_e164))
    contact = contact_result.scalar_one_or_none()

    entry = SuppressionEntry(
        workspace_id=workspace_id, contact_id=contact.id if contact else None, phone_e164=phone_e164,
        reason=reason, note=note, created_by=created_by,
    )
    db.add(entry)
    if contact is not None:
        contact.is_suppressed = True
    await db.flush()
    return entry


async def list_suppression_entries(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[SuppressionEntry]:
    result = await db.execute(
        select(SuppressionEntry).where(SuppressionEntry.workspace_id == workspace_id).order_by(SuppressionEntry.created_at.desc())
    )
    return list(result.scalars().all())


async def is_suppressed(db: AsyncSession, *, workspace_id: uuid.UUID, phone_e164: str) -> bool:
    result = await db.execute(
        select(SuppressionEntry.id).where(SuppressionEntry.workspace_id == workspace_id, SuppressionEntry.phone_e164 == phone_e164)
    )
    return result.scalar_one_or_none() is not None


async def create_segment(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str, description: str | None, contact_ids: list[uuid.UUID],
) -> Segment:
    segment = Segment(workspace_id=workspace_id, name=name, description=description, is_dynamic=False, definition={})
    db.add(segment)
    await db.flush()
    for contact_id in set(contact_ids):
        db.add(SegmentMember(workspace_id=workspace_id, segment_id=segment.id, contact_id=contact_id))
    await db.flush()
    return segment


async def list_segments(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Segment, func.count(SegmentMember.id))
        .outerjoin(SegmentMember, SegmentMember.segment_id == Segment.id)
        .where(Segment.workspace_id == workspace_id)
        .group_by(Segment.id)
        .order_by(Segment.name)
    )
    return [{"segment": segment, "member_count": count} for segment, count in result.all()]


async def get_segment_contact_ids(db: AsyncSession, *, workspace_id: uuid.UUID, segment_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(SegmentMember.contact_id).where(SegmentMember.workspace_id == workspace_id, SegmentMember.segment_id == segment_id)
    )
    return [row[0] for row in result.all()]
