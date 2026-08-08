from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin, TimestampMixin, UUIDPKMixin
from jkr_db.enums import InvoiceStatus, UsageEventType


class SubscriptionPlan(Base, UUIDPKMixin, TimestampMixin):
    """Platform-level catalog, not workspace-scoped."""

    __tablename__ = "subscription_plans"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    monthly_price_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class UsageEvent(Base, TenantMixin):
    __tablename__ = "usage_events"

    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[UsageEventType] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)


class ProviderCost(Base, TenantMixin):
    __tablename__ = "provider_costs"

    usage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usage_events.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    markup_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workspace_charge_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)


class Invoice(Base, TenantMixin):
    __tablename__ = "invoices"

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[InvoiceStatus] = mapped_column(String(16), nullable=False, default=InvoiceStatus.DRAFT)
    issued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
