"""Async engine/session factory shared by every Python service.

Tenant isolation layer 2 (RLS): `workspace_scoped_session` issues
`SET LOCAL app.current_workspace_id` at the start of the transaction so every
RLS policy defined in the migrations applies for the lifetime of that
transaction only — see docs/DECISIONS/0004-tenant-isolation.md.

One transaction per session, committed once when the context manager exits
cleanly (rolled back on exception) — every flavor below wraps its body in
`session.begin()`. `SET LOCAL` only lasts for the current transaction, so a
mid-request `commit()` would silently drop the RLS context for anything
queried afterward on the same session; service-layer code must therefore call
`await db.flush()` (to get generated PKs/defaults back) rather than
`await db.commit()`, and let the owning dependency's `session.begin()` commit
exactly once when the request finishes. A service function calling
`commit()` itself is very likely a bug, not a feature.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _validated_uuid_literal(value: uuid.UUID | str) -> str:
    """Postgres's `SET`/`SET LOCAL` are utility statements — they do not
    accept bind parameters ($1) at the wire protocol level; passing one
    raises a syntax error, not a silent no-op, so this was caught immediately
    rather than becoming a latent RLS bypass. The value must therefore be
    interpolated directly into the SQL text. That is only safe because we
    round-trip it through `uuid.UUID(...)` first: if it isn't a well-formed
    UUID this raises, and if it is, `str(uuid.UUID(...))` can only ever
    produce the canonical `[0-9a-f-]` form — there is no input that makes
    this interpolation unsafe once that parse has succeeded."""
    return str(uuid.UUID(str(value)))


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://jkr:jkr_local_dev@localhost:5432/jkr_ai_calling",
        )
        _engine = create_async_engine(
            database_url, pool_pre_ping=True, pool_size=10, max_overflow=10,
            echo=bool(os.environ.get("SQL_ECHO")),
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Plain session, no RLS context set — for genuinely platform-level
    tables with no workspace_id column (users, sessions, workspaces, roles,
    permissions, organizations)."""
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


@asynccontextmanager
async def workspace_scoped_session(workspace_id: uuid.UUID | str) -> AsyncIterator[AsyncSession]:
    """Session with `app.current_workspace_id` set for the duration of the
    transaction. Every request handler that reads/writes tenant-owned tables
    must use this, not `get_session`."""
    factory = get_session_factory()
    wsid = _validated_uuid_literal(workspace_id)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL app.current_workspace_id = '{wsid}'"))
            yield session


@asynccontextmanager
async def user_scoped_session(
    user_id: uuid.UUID | str, workspace_id: uuid.UUID | str | None = None
) -> AsyncIterator[AsyncSession]:
    """Session with `app.current_user_id` set (and optionally
    `app.current_workspace_id` too).

    `workspace_members` is the one table that is inherently a cross-workspace
    query surface for its own user (a caller must be able to list every
    workspace *they* belong to before any single workspace is "active"), so
    it carries a policy of `workspace_id = current_workspace_id OR user_id =
    current_user_id` rather than the plain single-workspace equality every
    other tenant table uses — see the `cc55370bda3d` migration and
    docs/DECISIONS/0004-tenant-isolation.md. This session flavor is what
    satisfies the `user_id = current_user_id` half of that policy; it grants
    no access to any other tenant table (their RLS policies don't reference
    app.current_user_id at all).
    """
    factory = get_session_factory()
    uid = _validated_uuid_literal(user_id)
    wsid = _validated_uuid_literal(workspace_id) if workspace_id is not None else None
    async with factory() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL app.current_user_id = '{uid}'"))
            if wsid is not None:
                await session.execute(text(f"SET LOCAL app.current_workspace_id = '{wsid}'"))
            yield session
