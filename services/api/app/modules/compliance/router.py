from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.compliance import service
from app.modules.compliance.schemas import AuditLogEntryOut, ComplianceOverview

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/overview", response_model=ComplianceOverview)
async def compliance_overview(
    auth: AuthContext = Depends(require_permission("compliance:view")),
    db: AsyncSession = Depends(workspace_db_for("compliance:view")),
) -> ComplianceOverview:
    data = await service.compliance_overview(db, workspace_id=auth.workspace_id)
    return ComplianceOverview(**data)


@router.get("/audit-log", response_model=list[AuditLogEntryOut])
async def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_permission("compliance:view")),
    db: AsyncSession = Depends(workspace_db_for("compliance:view")),
) -> list[AuditLogEntryOut]:
    rows = await service.list_audit_log(db, workspace_id=auth.workspace_id, limit=limit)
    return [AuditLogEntryOut(**r) for r in rows]
