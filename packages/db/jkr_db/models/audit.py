from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TimestampMixin, UUIDPKMixin
from jkr_db.enums import SecurityEventSeverity


class AuditLog(Base, UUIDPKMixin, TimestampMixin):
    """workspace_id is nullable here (unlike TenantMixin) because some audited
    actions are platform-level (e.g. a JKR admin action across workspaces)."""

    __tablename__ = "audit_logs"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SecurityEvent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "security_events"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[SecurityEventSeverity] = mapped_column(
        String(16), nullable=False, default=SecurityEventSeverity.INFO
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class FeatureFlag(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "feature_flags"
    __table_args__ = (Index("ix_feature_flags_key_workspace", "key", "workspace_id", unique=True),)

    key: Mapped[str] = mapped_column(String(100), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
