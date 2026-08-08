from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.billing import service
from app.modules.billing.schemas import UsageSummary

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/usage", response_model=UsageSummary)
async def usage_summary(
    auth: AuthContext = Depends(require_permission("billing:view")),
    db: AsyncSession = Depends(workspace_db_for("billing:view")),
) -> UsageSummary:
    data = await service.usage_summary(db, workspace_id=auth.workspace_id)
    return UsageSummary(**data)
