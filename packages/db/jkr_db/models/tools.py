from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import (
    AppointmentStatus,
    FollowUpChannel,
    FollowUpStatus,
    HandoffReason,
    HandoffStatus,
    ToolExecutionStatus,
)


class ToolExecution(Base, TenantMixin):
    __tablename__ = "tool_executions"

    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ToolExecutionStatus] = mapped_column(String(16), nullable=False, default=ToolExecutionStatus.PENDING)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Appointment(Base, TenantMixin):
    __tablename__ = "appointments"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[AppointmentStatus] = mapped_column(String(16), nullable=False, default=AppointmentStatus.SCHEDULED)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_calendar_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class HumanHandoff(Base, TenantMixin):
    __tablename__ = "human_handoffs"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[HandoffReason] = mapped_column(String(32), nullable=False)
    status: Mapped[HandoffStatus] = mapped_column(String(16), nullable=False, default=HandoffStatus.PENDING)
    packet: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


class FollowUpTask(Base, TenantMixin):
    __tablename__ = "follow_up_tasks"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[FollowUpChannel] = mapped_column(String(24), nullable=False)
    status: Mapped[FollowUpStatus] = mapped_column(String(16), nullable=False, default=FollowUpStatus.PENDING)
    scheduled_for: Mapped[datetime | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Message(Base, TenantMixin):
    __tablename__ = "messages"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
