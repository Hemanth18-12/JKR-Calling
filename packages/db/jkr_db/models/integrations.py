from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import IntegrationStatus, IntegrationType, WebhookDeliveryStatus


class Integration(Base, TenantMixin):
    __tablename__ = "integrations"

    type: Mapped[IntegrationType] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[IntegrationStatus] = mapped_column(
        String(16), nullable=False, default=IntegrationStatus.NOT_CONNECTED
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class IntegrationCredential(Base, TenantMixin):
    __tablename__ = "integration_credentials"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    encrypted_secret: Mapped[str] = mapped_column(String(4000), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WebhookEndpoint(Base, TenantMixin):
    __tablename__ = "webhook_endpoints"

    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(2000), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WebhookDelivery(Base, TenantMixin):
    __tablename__ = "webhook_deliveries"

    webhook_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        String(16), nullable=False, default=WebhookDeliveryStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
