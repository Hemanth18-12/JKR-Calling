"""Shared declarative base and mixins.

Every tenant-owned table gets `workspace_id` + `created_at` + `updated_at` via
`TenantMixin`, and a Postgres Row-Level Security policy is attached to it in the
Alembic migration (see docs/DECISIONS/0004-tenant-isolation.md) — the mixin alone
does not create the policy, it only guarantees the column exists and is indexed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every bare `Mapped[datetime]` / `Mapped[datetime | None]` column across
    # every model gets a timezone-aware `timestamptz` column by default. Every
    # datetime this codebase produces (`datetime.now(UTC)`, etc.) is
    # timezone-aware, so a naive-by-default DateTime() column here would be a
    # standing footgun — see the incident this fixed: session/call/campaign
    # timestamp inserts failing with "can't subtract offset-naive and
    # offset-aware datetimes" the first time each table was exercised.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin(UUIDPKMixin, TimestampMixin):
    """Base for every workspace-owned table. Enforced with RLS in migrations —
    see docs/DECISIONS/0004-tenant-isolation.md. All repository queries must
    also filter on workspace_id explicitly (defense-in-depth, not RLS-only)."""

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
