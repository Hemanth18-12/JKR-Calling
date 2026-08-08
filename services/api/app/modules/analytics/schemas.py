from __future__ import annotations

from pydantic import BaseModel


class CountBucket(BaseModel):
    key: str
    count: int


class BusinessOverview(BaseModel):
    total_calls: int
    connected_calls: int
    connect_rate: float
    appointments_booked: int
    contacts_reached: int
    active_campaigns: int
    pending_handoffs: int
    revenue_paise: int
    revenue_event_count: int


class FunnelStage(BaseModel):
    stage: str
    count: int


class CallAnalytics(BaseModel):
    status_breakdown: list[CountBucket]
    outcome_breakdown: list[CountBucket]
    lead_score_breakdown: list[CountBucket]
    avg_duration_seconds: float | None
    mock_call_count: int
    real_call_count: int
    funnel: list[FunnelStage]


class ConversationQuality(BaseModel):
    calls_evaluated: int
    avg_overall_score: float | None
    disclosure_present_rate: float | None
    avg_interruption_quality_score: float | None
    avg_knowledge_grounding_score: float | None
    needs_human_review_rate: float | None
    long_monologue_rate: float | None


class ProviderLatencyStage(BaseModel):
    stage: str
    avg_duration_ms: float
    sample_count: int


class ProviderAnalytics(BaseModel):
    latency_by_stage: list[ProviderLatencyStage]
    account_health: list[dict]


class CampaignFunnelItem(BaseModel):
    status: str
    count: int


class CampaignAnalytics(BaseModel):
    campaign_id: str
    contact_status_breakdown: list[CampaignFunnelItem]
    total_attempts: int
    dispatched_attempts: int
    gate_blocked_attempts: int
