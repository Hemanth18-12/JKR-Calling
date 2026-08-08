from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import ExperimentStatus, ExperimentVariantType


class Experiment(Base, TenantMixin):
    __tablename__ = "experiments"

    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(String(16), nullable=False, default=ExperimentStatus.DRAFT)
    hypothesis: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ExperimentVariant(Base, TenantMixin):
    __tablename__ = "experiment_variants"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_type: Mapped[ExperimentVariantType] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allocation_pct: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)


class ExperimentAssignment(Base, TenantMixin):
    __tablename__ = "experiment_assignments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiment_variants.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(nullable=False)
    exposed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ConversionEvent(Base, TenantMixin):
    __tablename__ = "conversion_events"

    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    conversion_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)


class RevenueEvent(Base, TenantMixin):
    __tablename__ = "revenue_events"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    attribution_type: Mapped[str] = mapped_column(String(24), nullable=False, default="influenced")
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
