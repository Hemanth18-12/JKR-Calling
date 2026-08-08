from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    objective: str = Field(pattern=r"^(book_appointment|qualify_lead|collect_feedback|renewal_reminder|custom)$")
    agent_id: uuid.UUID
    audience_segment_id: uuid.UUID | None = None
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=3, ge=1, le=10)
    daily_budget_paise: int | None = Field(default=None, ge=0)


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    objective: str
    agent_id: uuid.UUID
    agent_version_id: uuid.UUID
    audience_segment_id: uuid.UUID | None
    status: str
    mode: str
    max_attempts: int
    daily_budget_paise: int | None
    legal_reviewed_at: datetime | None
    created_at: datetime


class CampaignScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calling_window_start: time
    calling_window_end: time
    days_of_week: list[int]
    timezone: str


class CampaignScheduleUpdate(BaseModel):
    calling_window_start: time | None = None
    calling_window_end: time | None = None
    days_of_week: list[int] | None = None


class CampaignContactSummary(BaseModel):
    status: str
    count: int


class CampaignDetail(CampaignOut):
    schedule: CampaignScheduleOut | None
    contact_counts: list[CampaignContactSummary]


class CampaignContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    phone_masked: str
    status: str
    attempt_count: int
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None


class AddContactsRequest(BaseModel):
    contact_ids: list[uuid.UUID] = Field(default_factory=list)
    segment_id: uuid.UUID | None = None


class GateCheckResult(BaseModel):
    check: str
    passed: bool
    detail: str | None = None


class DryRunContactResult(BaseModel):
    campaign_contact_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    would_dispatch: bool
    failed_check: str | None
    checks: list[GateCheckResult]


class DryRunResponse(BaseModel):
    campaign_id: uuid.UUID
    evaluated: int
    would_dispatch: int
    blocked: int
    results: list[DryRunContactResult]


class CampaignAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_number: int
    call_session_id: uuid.UUID | None
    dispatched: bool
    outcome: str | None
    failure_reason: str | None
    gate_result: dict
    created_at: datetime
