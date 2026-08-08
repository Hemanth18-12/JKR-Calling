from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import (
    CampaignContactStatus,
    CampaignMode,
    CampaignObjective,
    CampaignStatus,
    RetryReason,
)


class Campaign(Base, TenantMixin):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    objective: Mapped[CampaignObjective] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=False
    )
    audience_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[CampaignStatus] = mapped_column(String(16), nullable=False, default=CampaignStatus.DRAFT)
    mode: Mapped[CampaignMode] = mapped_column(String(16), nullable=False, default=CampaignMode.DRY_RUN)
    required_fields: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    optional_fields: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    success_conditions: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    stop_conditions: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    legal_reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    daily_budget_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CampaignVersion(Base, TenantMixin):
    __tablename__ = "campaign_versions"
    __table_args__ = (UniqueConstraint("campaign_id", "version_number", name="uq_campaign_version_number"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CampaignSchedule(Base, TenantMixin):
    __tablename__ = "campaign_schedules"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    calling_window_start: Mapped[time] = mapped_column(nullable=False, default=time(9, 0))
    calling_window_end: Mapped[time] = mapped_column(nullable=False, default=time(20, 0))
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=lambda: [0, 1, 2, 3, 4, 5])
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    starts_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CampaignContact(Base, TenantMixin):
    __tablename__ = "campaign_contacts"
    __table_args__ = (UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CampaignContactStatus] = mapped_column(
        String(24), nullable=False, default=CampaignContactStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    extracted_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CampaignAttempt(Base, TenantMixin):
    __tablename__ = "campaign_attempts"

    campaign_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    gate_result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dispatched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class RetryJob(Base, TenantMixin):
    __tablename__ = "retry_jobs"

    campaign_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[RetryReason] = mapped_column(String(32), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
