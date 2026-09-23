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

import asyncio
import logging
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("jkr_db.session")

_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_info() -> dict[str, Any]:
    """Extract non-sensitive connection details for logging and diagnostics."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling",
    )
    try:
        parsed = make_url(database_url)
        return {
            "host": parsed.host or "unknown-host",
            "port": parsed.port or 5432,
            "database": parsed.database or "unknown-db",
            "user": parsed.username or "unknown-user",
        }
    except Exception:
        return {
            "host": "unparseable-host",
            "port": 5432,
            "database": "unknown-db",
            "user": "unknown-user",
        }


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
            "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling",
        )
        if database_url.startswith("postgresql+psycopg://"):
            database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgresql://") and not database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # asyncpg expects 'ssl=require' rather than 'sslmode=require'
        if "sslmode=" in database_url and "asyncpg" in database_url:
            database_url = database_url.replace("sslmode=", "ssl=")

        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 10,
            "echo": bool(os.environ.get("SQL_ECHO")),
        }
        if "asyncpg" in database_url:
            connect_timeout = float(os.environ.get("DB_CONNECT_TIMEOUT", "10.0"))
            command_timeout = float(os.environ.get("DB_COMMAND_TIMEOUT", "15.0"))
            engine_kwargs["connect_args"] = {
                "timeout": connect_timeout,
                "command_timeout": command_timeout,
            }

        _engine = create_async_engine(database_url, **engine_kwargs)
    return _engine


async def ping_database(timeout: float = 5.0) -> tuple[bool, str]:
    """Startup health check that pings the database and logs a clear, loud error.

    Pings the configured database with `SELECT 1`. If the connection fails,
    logs an unmissable banner to stderr and application logs with target host,
    port, database name, and an actionable hint (e.g. Render free-tier Postgres
    instance expired or was deleted).
    """
    info = get_database_info()
    host = info["host"]
    port = info["port"]
    db_name = info["database"]

    try:
        engine = get_engine()
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        msg = f"[DATABASE HEALTH CHECK] Connected to PostgreSQL host: {host}:{port}/{db_name}"
        logger.info(msg)
        return True, msg
    except Exception as exc:
        err_type = type(exc).__name__
        err_msg = str(exc)
        loud_error = (
            "\n" + "=" * 80 + "\n"
            f"[DATABASE CONNECTION ERROR] Could not connect to PostgreSQL database!\n"
            f"  Host:     {host}\n"
            f"  Port:     {port}\n"
            f"  Database: {db_name}\n"
            f"  Error:    {err_type}: {err_msg}\n\n"
            f"  HINT: Check if the Render Postgres instance expired or was deleted.\n"
            f"        Render free-tier PostgreSQL databases expire and are deleted after 30 days.\n"
            f"        Verify DATABASE_URL in your Render Dashboard settings or create a new database.\n"
            + "=" * 80 + "\n"
        )
        logger.error(loud_error)
        sys.stderr.write(loud_error)
        sys.stderr.flush()
        return False, f"Failed to connect to {host}:{port}/{db_name}: {err_type}: {err_msg}"


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
