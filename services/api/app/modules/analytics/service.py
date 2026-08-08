"""Read-only aggregation queries over operational data — there is no
separate analytics/fact-table schema in this pass (deliberately: every
number here is computed from the same rows the rest of the product writes,
so a dashboard number can never silently drift from what actually
happened). Real logic, real data; the only thing genuinely limited is how
much data exists to aggregate in a fresh local workspace."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from jkr_db.models.calls import CallLatencyMetric, CallOutcome, CallSession, QualityEvaluation
from jkr_db.models.campaigns import Campaign, CampaignAttempt, CampaignContact
from jkr_db.models.experiments import RevenueEvent
from jkr_db.models.providers import ProviderAccount, ProviderHealth
from jkr_db.models.tools import Appointment, HumanHandoff
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# CallOutcomeCategory values that represent a genuinely answered call —
# everything else (unreachable, wrong_number with no answer, etc.) means the
# phone never actually connected. Mirrors intelligence-worker's own
# classification, not re-derived from raw transcripts here.
_CONNECTED_OUTCOME_CATEGORIES = {
    "interested", "qualified", "appointment_booked", "callback_requested", "not_interested", "needs_human",
}
_BOOKED_APPOINTMENT_STATUSES = {"scheduled", "confirmed", "rescheduled", "completed"}


async def business_overview(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    total_calls_result = await db.execute(select(func.count(CallSession.id)).where(CallSession.workspace_id == workspace_id))
    total_calls = total_calls_result.scalar_one()

    connected_result = await db.execute(
        select(func.count(CallOutcome.id))
        .join(CallSession, CallSession.id == CallOutcome.call_session_id)
        .where(CallSession.workspace_id == workspace_id, CallOutcome.category.in_(_CONNECTED_OUTCOME_CATEGORIES))
    )
    connected_calls = connected_result.scalar_one()

    appointments_result = await db.execute(
        select(func.count(Appointment.id)).where(Appointment.workspace_id == workspace_id, Appointment.status.in_(_BOOKED_APPOINTMENT_STATUSES))
    )
    appointments_booked = appointments_result.scalar_one()

    contacts_reached_result = await db.execute(
        select(func.count(func.distinct(CallSession.contact_id))).where(
            CallSession.workspace_id == workspace_id, CallSession.contact_id.is_not(None), CallSession.status == "completed"
        )
    )
    contacts_reached = contacts_reached_result.scalar_one()

    active_campaigns_result = await db.execute(
        select(func.count(Campaign.id)).where(Campaign.workspace_id == workspace_id, Campaign.status == "active")
    )
    active_campaigns = active_campaigns_result.scalar_one()

    pending_handoffs_result = await db.execute(
        select(func.count(HumanHandoff.id)).where(HumanHandoff.workspace_id == workspace_id, HumanHandoff.status == "pending")
    )
    pending_handoffs = pending_handoffs_result.scalar_one()

    revenue_result = await db.execute(
        select(func.coalesce(func.sum(RevenueEvent.amount_paise), 0), func.count(RevenueEvent.id)).where(RevenueEvent.workspace_id == workspace_id)
    )
    revenue_paise, revenue_event_count = revenue_result.one()

    return {
        "total_calls": total_calls,
        "connected_calls": connected_calls,
        "connect_rate": round(connected_calls / total_calls, 4) if total_calls else 0.0,
        "appointments_booked": appointments_booked,
        "contacts_reached": contacts_reached,
        "active_campaigns": active_campaigns,
        "pending_handoffs": pending_handoffs,
        "revenue_paise": int(revenue_paise),
        "revenue_event_count": revenue_event_count,
    }


async def call_analytics(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    status_result = await db.execute(
        select(CallSession.status, func.count(CallSession.id)).where(CallSession.workspace_id == workspace_id).group_by(CallSession.status)
    )
    status_breakdown = [{"key": s, "count": c} for s, c in status_result.all()]

    outcome_result = await db.execute(
        select(CallOutcome.category, func.count(CallOutcome.id))
        .join(CallSession, CallSession.id == CallOutcome.call_session_id)
        .where(CallSession.workspace_id == workspace_id)
        .group_by(CallOutcome.category)
    )
    outcome_breakdown = [{"key": o, "count": c} for o, c in outcome_result.all()]

    lead_score_result = await db.execute(
        select(CallOutcome.lead_score, func.count(CallOutcome.id))
        .join(CallSession, CallSession.id == CallOutcome.call_session_id)
        .where(CallSession.workspace_id == workspace_id, CallOutcome.lead_score.is_not(None))
        .group_by(CallOutcome.lead_score)
    )
    lead_score_breakdown = [{"key": s, "count": c} for s, c in lead_score_result.all()]

    avg_duration_result = await db.execute(
        select(func.avg(CallSession.duration_seconds)).where(CallSession.workspace_id == workspace_id, CallSession.duration_seconds.is_not(None))
    )
    avg_duration = avg_duration_result.scalar_one()

    mock_count_result = await db.execute(
        select(CallSession.is_mock, func.count(CallSession.id)).where(CallSession.workspace_id == workspace_id).group_by(CallSession.is_mock)
    )
    mock_counts = dict(mock_count_result.all())

    outcome_by_key = {b["key"]: b["count"] for b in outcome_breakdown}
    funnel = [
        {"stage": "dialed", "count": status_breakdown and sum(b["count"] for b in status_breakdown) or 0},
        {"stage": "connected", "count": sum(outcome_by_key.get(k, 0) for k in _CONNECTED_OUTCOME_CATEGORIES)},
        {"stage": "qualified", "count": outcome_by_key.get("qualified", 0) + outcome_by_key.get("appointment_booked", 0)},
        {"stage": "appointment_booked", "count": outcome_by_key.get("appointment_booked", 0)},
    ]

    return {
        "status_breakdown": status_breakdown,
        "outcome_breakdown": outcome_breakdown,
        "lead_score_breakdown": lead_score_breakdown,
        "avg_duration_seconds": round(float(avg_duration), 1) if avg_duration is not None else None,
        "mock_call_count": mock_counts.get(True, 0),
        "real_call_count": mock_counts.get(False, 0),
        "funnel": funnel,
    }


async def conversation_quality(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(
            func.count(QualityEvaluation.id),
            func.avg(QualityEvaluation.overall_score),
            func.avg(func.cast(QualityEvaluation.disclosure_present, Integer)),
            func.avg(QualityEvaluation.interruption_quality_score),
            func.avg(QualityEvaluation.knowledge_grounding_score),
            func.avg(func.cast(QualityEvaluation.needs_human_review, Integer)),
            func.avg(func.cast(QualityEvaluation.long_monologue_flag, Integer)),
        ).where(QualityEvaluation.workspace_id == workspace_id)
    )
    count, avg_overall, disclosure_rate, avg_interruption, avg_knowledge, review_rate, monologue_rate = result.one()

    def _round(v: float | None) -> float | None:
        return round(float(v), 3) if v is not None else None

    return {
        "calls_evaluated": count,
        "avg_overall_score": _round(avg_overall),
        "disclosure_present_rate": _round(disclosure_rate),
        "avg_interruption_quality_score": _round(avg_interruption),
        "avg_knowledge_grounding_score": _round(avg_knowledge),
        "needs_human_review_rate": _round(review_rate),
        "long_monologue_rate": _round(monologue_rate),
    }


async def provider_analytics(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    latency_result = await db.execute(
        select(CallLatencyMetric.stage, func.avg(CallLatencyMetric.duration_ms), func.count(CallLatencyMetric.id))
        .where(CallLatencyMetric.workspace_id == workspace_id)
        .group_by(CallLatencyMetric.stage)
        .order_by(CallLatencyMetric.stage)
    )
    latency_by_stage = [
        {"stage": stage, "avg_duration_ms": round(float(avg_ms), 1), "sample_count": count}
        for stage, avg_ms, count in latency_result.all()
    ]

    accounts_result = await db.execute(select(ProviderAccount).where(ProviderAccount.workspace_id == workspace_id))
    accounts = list(accounts_result.scalars().all())
    account_health = []
    for account in accounts:
        latest_health_result = await db.execute(
            select(ProviderHealth)
            .where(ProviderHealth.provider_account_id == account.id)
            .order_by(ProviderHealth.checked_at.desc())
            .limit(1)
        )
        latest = latest_health_result.scalar_one_or_none()
        account_health.append(
            {
                "kind": account.kind, "name": account.name, "display_name": account.display_name,
                "status": latest.status if latest else account.status,
                "latency_p50_ms": latest.latency_p50_ms if latest else None,
            }
        )

    return {"latency_by_stage": latency_by_stage, "account_health": account_health}


async def campaign_analytics(db: AsyncSession, *, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> dict:
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id))
    if campaign_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")

    status_result = await db.execute(
        select(CampaignContact.status, func.count(CampaignContact.id))
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
        .group_by(CampaignContact.status)
    )
    contact_status_breakdown = [{"status": s, "count": c} for s, c in status_result.all()]

    attempts_result = await db.execute(
        select(CampaignAttempt.dispatched, func.count(CampaignAttempt.id))
        .join(CampaignContact, CampaignContact.id == CampaignAttempt.campaign_contact_id)
        .where(CampaignContact.workspace_id == workspace_id, CampaignContact.campaign_id == campaign_id)
        .group_by(CampaignAttempt.dispatched)
    )
    dispatched_counts = dict(attempts_result.all())

    return {
        "campaign_id": str(campaign_id),
        "contact_status_breakdown": contact_status_breakdown,
        "total_attempts": sum(dispatched_counts.values()),
        "dispatched_attempts": dispatched_counts.get(True, 0),
        "gate_blocked_attempts": dispatched_counts.get(False, 0),
    }
