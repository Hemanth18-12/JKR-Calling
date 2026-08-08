"""Usage/billing summary — **Medium** tier (docs/DECISIONS/0007-scope-for-this-pass.md):
real `usage_events` aggregation from actual call activity (voice-worker
writes one per completed call — see conversation_engine.py::end_session),
and the campaign daily-budget figures reuse the same real
`call_sessions.cost_paise` sum the safety gate's budget check already
enforces at dispatch time (services/api's copy lives in
jkr_db.safety_gate._today_spend_paise; this is the same query, not a
different source of truth). What's not built: invoicing, plan/subscription
management, or a persisted per-workspace budget setting (only per-campaign
budgets exist in the schema this pass)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from jkr_db.models.billing import UsageEvent
from jkr_db.models.calls import CallSession
from jkr_db.models.campaigns import Campaign
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def usage_summary(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    usage_result = await db.execute(
        select(UsageEvent.event_type, UsageEvent.unit, func.sum(UsageEvent.quantity), func.count(UsageEvent.id))
        .where(UsageEvent.workspace_id == workspace_id)
        .group_by(UsageEvent.event_type, UsageEvent.unit)
    )
    usage_by_type = [
        {"event_type": t, "unit": u, "total_quantity": float(q), "event_count": c} for t, u, q, c in usage_result.all()
    ]

    calls_result = await db.execute(
        select(func.count(CallSession.id), func.coalesce(func.sum(CallSession.duration_seconds), 0)).where(
            CallSession.workspace_id == workspace_id, CallSession.status == "completed"
        )
    )
    total_calls, total_call_seconds = calls_result.one()

    campaigns_result = await db.execute(
        select(Campaign).where(Campaign.workspace_id == workspace_id, Campaign.daily_budget_paise.is_not(None))
    )
    campaign_budgets = []
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for campaign in campaigns_result.scalars().all():
        spend_result = await db.execute(
            select(func.coalesce(func.sum(CallSession.cost_paise), 0)).where(
                CallSession.campaign_id == campaign.id, CallSession.started_at >= today_start
            )
        )
        spent_today = spend_result.scalar_one()
        campaign_budgets.append(
            {
                "campaign_id": str(campaign.id), "campaign_name": campaign.name,
                "daily_budget_paise": campaign.daily_budget_paise, "spent_today_paise": int(spent_today),
            }
        )

    return {
        "usage_by_type": usage_by_type, "total_calls": total_calls, "total_call_seconds": float(total_call_seconds),
        "campaign_budgets": campaign_budgets,
    }
