from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import ConsentPurpose, ConsentSource, LanguageCode, SuppressionReason


class Contact(Base, TenantMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "phone_e164", name="uq_contact_workspace_phone"),)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    preferred_language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    lead_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crm_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_call_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_callback_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consent_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    is_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conversion_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revenue_value_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ContactField(Base, TenantMixin):
    __tablename__ = "contact_fields"
    __table_args__ = (UniqueConstraint("contact_id", "key", name="uq_contact_field_key"),)

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(1000), nullable=False)


class ContactTag(Base, TenantMixin):
    __tablename__ = "contact_tags"
    __table_args__ = (UniqueConstraint("contact_id", "tag", name="uq_contact_tag"),)

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)


class Segment(Base, TenantMixin):
    __tablename__ = "segments"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SegmentMember(Base, TenantMixin):
    __tablename__ = "segment_members"
    __table_args__ = (UniqueConstraint("segment_id", "contact_id", name="uq_segment_member"),)

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ConsentEvent(Base, TenantMixin):
    __tablename__ = "consent_events"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[ConsentPurpose] = mapped_column(String(32), nullable=False)
    source: Mapped[ConsentSource] = mapped_column(String(32), nullable=False)
    campaign_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SuppressionEntry(Base, TenantMixin):
    __tablename__ = "suppression_entries"
    __table_args__ = (UniqueConstraint("workspace_id", "phone_e164", name="uq_suppression_workspace_phone"),)

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[SuppressionReason] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
