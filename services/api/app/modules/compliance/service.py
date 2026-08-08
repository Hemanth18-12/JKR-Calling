from __future__ import annotations

import uuid

from jkr_db.models.audit import AuditLog
from jkr_db.models.contacts import ConsentEvent, Contact
from jkr_db.models.identity import User
from jkr_db.models.tenancy import Workspace
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_audit_log(db: AsyncSession, *, workspace_id: uuid.UUID, limit: int = 100) -> list[dict]:
    result = await db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": log.id, "actor_name": actor_name, "action": log.action, "resource_type": log.resource_type,
            "resource_id": log.resource_id, "ip_address": log.ip_address, "created_at": log.created_at,
        }
        for log, actor_name in result.all()
    ]


async def compliance_overview(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    workspace_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one()

    total_contacts_result = await db.execute(select(func.count(Contact.id)).where(Contact.workspace_id == workspace_id))
    total_contacts = total_contacts_result.scalar_one()

    suppressed_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.workspace_id == workspace_id, Contact.is_suppressed.is_(True))
    )
    suppressed_contacts = suppressed_result.scalar_one()

    purpose_result = await db.execute(
        select(ConsentEvent.purpose, func.count(ConsentEvent.id))
        .where(ConsentEvent.workspace_id == workspace_id, ConsentEvent.revoked_at.is_(None))
        .group_by(ConsentEvent.purpose)
    )
    consent_purpose_breakdown = [{"purpose": p, "count": c} for p, c in purpose_result.all()]

    return {
        "calling_window_start": workspace.calling_window_start,
        "calling_window_end": workspace.calling_window_end,
        "timezone": workspace.timezone,
        "total_contacts": total_contacts,
        "suppressed_contacts": suppressed_contacts,
        "consent_purpose_breakdown": consent_purpose_breakdown,
    }
