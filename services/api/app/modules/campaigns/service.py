"""Campaign CRUD + the `/dry-run` endpoint. The actual outbound safety gate
(docs/SECURITY_AND_COMPLIANCE.md §2) lives in `jkr_db.safety_gate`, not here —
shared with services/campaign-worker's real dispatch loop so a dry-run's
"would dispatch" promise and what actually happens at dispatch time can never
silently diverge (see that module's docstring, and docs/DECISIONS/0003)."""

from __future__ import annotations

import uuid
from datetime import time

from fastapi import HTTPException, status
from jkr_db.models.agents import Agent
from jkr_db.models.campaigns import (
    Campaign,
    CampaignAttempt,
    CampaignContact,
    CampaignSchedule,
    CampaignVersion,
)
from jkr_db.models.contacts import Contact
from jkr_db.models.tenancy import Workspace
from jkr_db.phone import mask_for_display
from jkr_db.safety_gate import run_safety_gate as _run_safety_gate
from jkr_messaging import enqueue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.schemas import GateCheckResult
from app.modules.contacts import service as contacts_service


async def _run_safety_gate_as_schema(
    db: AsyncSession, redis_client, *, campaign: Campaign, campaign_contact: CampaignContact,
    contact: Contact, workspace: Workspace, schedule: CampaignSchedule | None,
) -> list[GateCheckResult]:
    raw = await _run_safety_gate(
        db, redis_client, campaign=campaign, campaign_contact=campaign_contact, contact=contact,
        workspace=workspace, schedule=schedule,
    )
    return [GateCheckResult(**c) for c in raw]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_campaign(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str, objective: str, agent_id: uuid.UUID,
    audience_segment_id: uuid.UUID | None, required_fields: list[str], optional_fields: list[str],
    success_conditions: list[str], stop_conditions: list[str], max_attempts: int, daily_budget_paise: int | None,
    created_by: uuid.UUID,
) -> Campaign:
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    if agent.published_version_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agent has no published version — publish it before creating a campaign")

    workspace_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one()

    campaign = Campaign(
        workspace_id=workspace_id, name=name, objective=objective, agent_id=agent.id,
        agent_version_id=agent.published_version_id, audience_segment_id=audience_segment_id,
        status="draft", mode="dry_run", required_fields=required_fields, optional_fields=optional_fields,
        success_conditions=success_conditions, stop_conditions=stop_conditions, max_attempts=max_attempts,
        retry_policy={"backoff_minutes": [30, 120, 480]}, daily_budget_paise=daily_budget_paise, created_by=created_by,
    )
    db.add(campaign)
    await db.flush()

    db.add(
        CampaignSchedule(
            workspace_id=workspace_id, campaign_id=campaign.id,
            calling_window_start=workspace.calling_window_start, calling_window_end=workspace.calling_window_end,
            days_of_week=[0, 1, 2, 3, 4, 5], timezone=workspace.timezone,
        )
    )
    await db.flush()
    return campaign


async def list_campaigns(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Campaign]:
    result = await db.execute(select(Campaign).where(Campaign.workspace_id == workspace_id).order_by(Campaign.created_at.desc()))
    return list(result.scalars().all())


async def get_campaign(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


async def get_schedule(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> CampaignSchedule | None:
    result = await db.execute(
        select(CampaignSchedule).where(CampaignSchedule.workspace_id == workspace_id, CampaignSchedule.campaign_id == campaign_id)
    )
    return result.scalar_one_or_none()


async def update_schedule(
    db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID,
    calling_window_start: time | None, calling_window_end: time | None, days_of_week: list[int] | None,
) -> CampaignSchedule:
    schedule = await get_schedule(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign schedule not found")
    if calling_window_start is not None:
        schedule.calling_window_start = calling_window_start
    if calling_window_end is not None:
        schedule.calling_window_end = calling_window_end
    if days_of_week is not None:
        schedule.days_of_week = days_of_week
    await db.flush()
    return schedule


async def contact_counts(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(CampaignContact.status, func.count(CampaignContact.id))
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
        .group_by(CampaignContact.status)
    )
    return [{"status": status_value, "count": count} for status_value, count in result.all()]


async def add_contacts(
    db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID, contact_ids: list[uuid.UUID], segment_id: uuid.UUID | None,
) -> int:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Contacts can only be added while a campaign is draft or paused")

    all_ids = set(contact_ids)
    if segment_id is not None:
        all_ids |= set(await contacts_service.get_segment_contact_ids(db, workspace_id=workspace_id, segment_id=segment_id))
    if not all_ids:
        return 0

    existing_result = await db.execute(
        select(CampaignContact.contact_id).where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
    )
    existing_ids = {row[0] for row in existing_result.all()}

    added = 0
    for contact_id in all_ids - existing_ids:
        db.add(CampaignContact(workspace_id=workspace_id, campaign_id=campaign_id, contact_id=contact_id, status="pending"))
        added += 1
    await db.flush()
    return added


async def list_campaign_contacts(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(CampaignContact, Contact)
        .join(Contact, Contact.id == CampaignContact.contact_id)
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
        .order_by(CampaignContact.created_at)
    )

    return [
        {
            "id": cc.id, "contact_id": contact.id, "contact_name": contact.full_name,
            "phone_masked": mask_for_display(contact.phone_e164), "status": cc.status,
            "attempt_count": cc.attempt_count, "last_attempt_at": cc.last_attempt_at, "next_attempt_at": cc.next_attempt_at,
        }
        for cc, contact in result.all()
    ]


async def dry_run(db: AsyncSession, redis_client, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> dict:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    workspace_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one()
    schedule = await get_schedule(db, workspace_id=workspace_id, campaign_id=campaign_id)

    rows = await db.execute(
        select(CampaignContact, Contact)
        .join(Contact, Contact.id == CampaignContact.contact_id)
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
        .order_by(CampaignContact.created_at)
    )

    results = []
    would_dispatch = 0
    for cc, contact in rows.all():
        checks = await _run_safety_gate_as_schema(
            db, redis_client, campaign=campaign, campaign_contact=cc, contact=contact, workspace=workspace, schedule=schedule,
        )
        passed = all(c.passed for c in checks)
        failed = next((c.check for c in checks if not c.passed), None)
        if passed:
            would_dispatch += 1
        results.append(
            {
                "campaign_contact_id": cc.id, "contact_id": contact.id, "contact_name": contact.full_name,
                "would_dispatch": passed, "failed_check": failed, "checks": checks,
            }
        )

    return {
        "campaign_id": campaign.id, "evaluated": len(results), "would_dispatch": would_dispatch,
        "blocked": len(results) - would_dispatch, "results": results,
    }


async def launch_campaign(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot launch a campaign in status '{campaign.status}'")

    pending_result = await db.execute(
        select(func.count(CampaignContact.id)).where(
            CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id,
            CampaignContact.status.in_(["pending", "retry_scheduled", "no_answer", "busy"]),
        )
    )
    if pending_result.scalar_one() == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Campaign has no dispatchable contacts — add contacts before launching")

    version_count_result = await db.execute(select(func.count(CampaignVersion.id)).where(CampaignVersion.campaign_id == campaign_id))
    next_version = version_count_result.scalar_one() + 1
    db.add(
        CampaignVersion(
            workspace_id=workspace_id, campaign_id=campaign_id, version_number=next_version,
            snapshot={
                "name": campaign.name, "objective": campaign.objective, "agent_version_id": str(campaign.agent_version_id),
                "max_attempts": campaign.max_attempts, "required_fields": campaign.required_fields,
                "success_conditions": campaign.success_conditions, "stop_conditions": campaign.stop_conditions,
            },
        )
    )
    campaign.status = "active"
    await db.flush()

    enqueue("run_campaign_dispatch_batch", args=(str(campaign.id), str(workspace_id)), queue_name="campaigns")
    return campaign


async def pause_campaign(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an active campaign can be paused")
    campaign.status = "paused"
    await db.flush()
    return campaign


async def cancel_campaign(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status in ("completed", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Campaign is already '{campaign.status}'")
    campaign.status = "cancelled"
    await db.flush()
    return campaign


async def delete_campaign(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
    campaign = await get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign.status in ("active", "paused"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete campaign while in status '{campaign.status}'. Please cancel it first."
        )
    await db.delete(campaign)
    await db.flush()


async def list_attempts(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_contact_id: uuid.UUID) -> list[CampaignAttempt]:
    result = await db.execute(
        select(CampaignAttempt)
        .where(CampaignAttempt.workspace_id == workspace_id, CampaignAttempt.campaign_contact_id == campaign_contact_id)
        .order_by(CampaignAttempt.attempt_number)
    )
    return list(result.scalars().all())

