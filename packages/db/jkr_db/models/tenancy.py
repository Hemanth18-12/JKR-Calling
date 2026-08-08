from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, ForeignKey, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TimestampMixin, UUIDPKMixin
from jkr_db.enums import MemberStatus


class Organization(Base, UUIDPKMixin, TimestampMixin):
    """A JKR client organization. May own multiple workspaces (e.g. a hospital
    group with several branches, each a workspace)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_email: Mapped[str | None] = mapped_column(String(320), nullable=True)


class Workspace(Base, UUIDPKMixin, TimestampMixin):
    """The tenant root. Everything workspace-owned hangs off this via
    workspace_id (TenantMixin). Not itself workspace_id-scoped."""

    __tablename__ = "workspaces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="te-en-IN")
    calling_window_start: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    calling_window_end: Mapped[time] = mapped_column(Time, nullable=False, default=time(20, 0))
    identity_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    recording_retention_days: Mapped[int] = mapped_column(nullable=False, default=90)
    transcript_retention_days: Mapped[int] = mapped_column(nullable=False, default=90)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Role(Base, UUIDPKMixin, TimestampMixin):
    """RBAC role catalog — seeded with the 9 roles from spec §4. workspace_id
    is null for the platform-wide catalog rows (all roles ship platform-wide;
    a workspace cannot currently define custom roles)."""

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_platform_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class WorkspaceMember(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[MemberStatus] = mapped_column(
        String(32), nullable=False, default=MemberStatus.INVITED
    )
    invited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(nullable=True)
