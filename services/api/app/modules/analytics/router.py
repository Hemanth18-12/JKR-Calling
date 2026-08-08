from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    BusinessOverview,
    CallAnalytics,
    CampaignAnalytics,
    ConversationQuality,
    ProviderAnalytics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=BusinessOverview)
async def business_overview(
    auth: AuthContext = Depends(require_permission("analytics:view")),
    db: AsyncSession = Depends(workspace_db_for("analytics:view")),
) -> BusinessOverview:
    data = await service.business_overview(db, workspace_id=auth.workspace_id)
    return BusinessOverview(**data)


@router.get("/calls", response_model=CallAnalytics)
async def calls(
    auth: AuthContext = Depends(require_permission("analytics:view")),
    db: AsyncSession = Depends(workspace_db_for("analytics:view")),
) -> CallAnalytics:
    data = await service.call_analytics(db, workspace_id=auth.workspace_id)
    return CallAnalytics(**data)


@router.get("/conversation-quality", response_model=ConversationQuality)
async def conversation_quality(
    auth: AuthContext = Depends(require_permission("analytics:view")),
    db: AsyncSession = Depends(workspace_db_for("analytics:view")),
) -> ConversationQuality:
    data = await service.conversation_quality(db, workspace_id=auth.workspace_id)
    return ConversationQuality(**data)


@router.get("/providers", response_model=ProviderAnalytics)
async def providers(
    auth: AuthContext = Depends(require_permission("analytics:view")),
    db: AsyncSession = Depends(workspace_db_for("analytics:view")),
) -> ProviderAnalytics:
    data = await service.provider_analytics(db, workspace_id=auth.workspace_id)
    return ProviderAnalytics(**data)


@router.get("/campaigns/{campaign_id}", response_model=CampaignAnalytics)
async def campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("analytics:view")),
    db: AsyncSession = Depends(workspace_db_for("analytics:view")),
) -> CampaignAnalytics:
    data = await service.campaign_analytics(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return CampaignAnalytics(**data)
