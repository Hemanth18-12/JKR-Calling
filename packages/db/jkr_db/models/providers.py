from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import ProviderHealthStatus, ProviderKind, ProviderName


class ProviderAccount(Base, TenantMixin):
    """A configured provider account for a workspace, e.g. 'Twilio production'
    or 'Mock Telephony' (every workspace gets a mock account per kind by
    default — see docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md)."""

    __tablename__ = "provider_accounts"

    kind: Mapped[ProviderKind] = mapped_column(String(16), nullable=False)
    name: Mapped[ProviderName] = mapped_column(String(32), nullable=False, default=ProviderName.MOCK)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[ProviderHealthStatus] = mapped_column(
        String(16), nullable=False, default=ProviderHealthStatus.UNKNOWN
    )
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ProviderCredential(Base, TenantMixin):
    __tablename__ = "provider_credentials"

    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    encrypted_secret: Mapped[str] = mapped_column(String(4000), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ProviderHealth(Base, TenantMixin):
    __tablename__ = "provider_health"

    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ProviderHealthStatus] = mapped_column(String(16), nullable=False)
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class PhoneNumber(Base, TenantMixin):
    __tablename__ = "phone_numbers"

    number_e164: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_accounts.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False, default=lambda: ["voice"])
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
