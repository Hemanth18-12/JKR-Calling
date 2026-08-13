from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from jkr_messaging import get_redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.campaigns import service
from app.modules.campaigns.schemas import (
    AddContactsRequest,
    CampaignAttemptOut,
    CampaignContactOut,
    CampaignContactSummary,
    CampaignCreate,
    CampaignDetail,
    CampaignOut,
    CampaignScheduleOut,
    CampaignScheduleUpdate,
    DryRunResponse,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    auth: AuthContext = Depends(require_permission("campaigns:create")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:create")),
) -> CampaignOut:
    campaign = await service.create_campaign(
        db, workspace_id=auth.workspace_id, name=payload.name, objective=payload.objective, agent_id=payload.agent_id,
        audience_segment_id=payload.audience_segment_id, required_fields=payload.required_fields,
        optional_fields=payload.optional_fields, success_conditions=payload.success_conditions,
        stop_conditions=payload.stop_conditions, max_attempts=payload.max_attempts,
        daily_budget_paise=payload.daily_budget_paise, created_by=auth.user.id,
    )
    return CampaignOut.model_validate(campaign)


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> list[CampaignOut]:
    campaigns = await service.list_campaigns(db, workspace_id=auth.workspace_id)
    return [CampaignOut.model_validate(c) for c in campaigns]


@router.get("/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> CampaignDetail:
    campaign = await service.get_campaign(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    schedule = await service.get_schedule(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    counts = await service.contact_counts(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return CampaignDetail(
        **CampaignOut.model_validate(campaign).model_dump(),
        schedule=CampaignScheduleOut.model_validate(schedule) if schedule else None,
        contact_counts=[CampaignContactSummary(**c) for c in counts],
    )


@router.patch("/{campaign_id}/schedule", response_model=CampaignScheduleOut)
async def update_schedule(
    campaign_id: uuid.UUID,
    payload: CampaignScheduleUpdate,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> CampaignScheduleOut:
    schedule = await service.update_schedule(
        db, workspace_id=auth.workspace_id, campaign_id=campaign_id, calling_window_start=payload.calling_window_start,
        calling_window_end=payload.calling_window_end, days_of_week=payload.days_of_week,
    )
    return CampaignScheduleOut.model_validate(schedule)


@router.post("/{campaign_id}/contacts", status_code=201)
async def add_contacts(
    campaign_id: uuid.UUID,
    payload: AddContactsRequest,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> dict:
    added = await service.add_contacts(
        db, workspace_id=auth.workspace_id, campaign_id=campaign_id, contact_ids=payload.contact_ids, segment_id=payload.segment_id,
    )
    return {"added": added}


@router.get("/{campaign_id}/contacts", response_model=list[CampaignContactOut])
async def list_campaign_contacts(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> list[CampaignContactOut]:
    rows = await service.list_campaign_contacts(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return [CampaignContactOut(**r) for r in rows]


@router.get("/{campaign_id}/contacts/{campaign_contact_id}/attempts", response_model=list[CampaignAttemptOut])
async def list_attempts(
    campaign_id: uuid.UUID,
    campaign_contact_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> list[CampaignAttemptOut]:
    attempts = await service.list_attempts(db, workspace_id=auth.workspace_id, campaign_contact_id=campaign_contact_id)
    return [CampaignAttemptOut.model_validate(a) for a in attempts]


@router.post("/{campaign_id}/dry-run", response_model=DryRunResponse)
async def dry_run(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:validate")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:validate")),
) -> DryRunResponse:
    result = await service.dry_run(db, get_redis(), workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return DryRunResponse(**result)


@router.post("/{campaign_id}/launch", response_model=CampaignOut)
async def launch_campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:launch")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:launch")),
) -> CampaignOut:
    campaign = await service.launch_campaign(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return CampaignOut.model_validate(campaign)


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:pause")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:pause")),
) -> CampaignOut:
    campaign = await service.pause_campaign(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return CampaignOut.model_validate(campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:cancel")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:cancel")),
) -> CampaignOut:
    campaign = await service.cancel_campaign(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)
    return CampaignOut.model_validate(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:cancel")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:cancel")),
) -> None:
    await service.delete_campaign(db, workspace_id=auth.workspace_id, campaign_id=campaign_id)

