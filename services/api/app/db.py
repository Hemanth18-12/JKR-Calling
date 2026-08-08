"""Thin per-service wrapper over jkr_db.session, bound to this service's
DATABASE_URL setting. Three flavors of dependency:

- `platform_db`: no RLS context — for genuinely platform-level tables with no
  workspace_id column at all (users, sessions, workspaces, roles,
  permissions, organizations). Every query against these MUST filter
  explicitly where relevant (e.g. by user_id) since there is no RLS backstop.
- `workspace_db_from_path`: RLS context set to the `workspace_id` path
  parameter of the enclosing route — for every ordinary workspace-owned
  table. FastAPI matches this dependency's `workspace_id` argument to the
  route's own `{workspace_id}` path segment automatically. See
  docs/DECISIONS/0004-tenant-isolation.md.
- `app.deps.user_db` (not here — it depends on AuthContext, which would
  create a circular import with app.deps importing from this module): RLS
  context set to the current user, needed only for `workspace_members`
  queries that are inherently cross-workspace (see `user_scoped_session`'s
  docstring in packages/db/jkr_db/session.py for why that table alone needs
  this).

IMPORTANT: opening a workspace-scoped session for an arbitrary `workspace_id`
does not by itself prove the caller belongs to that workspace — RLS only
restricts *which rows a query can touch*, not *who's allowed to run the
query*. Every route using `workspace_db_from_path` (or any workspace-scoped
session) must still resolve the caller's own membership/permission first
(`tenancy.service.require_membership_with_permission` or
`app.deps.with_workspace`/`require_permission`) before touching workspace-wide
data — that resolution query itself only returns the caller's own row even
though RLS would technically allow reading the whole table, because the
query's own WHERE clause filters to `user_id = caller`. Skipping that check
and going straight to a "list everything in this workspace" query would leak
data to anyone able to pass a `workspace_id` they don't belong to.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

from jkr_db.session import get_session, workspace_scoped_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

# jkr_db.session reads DATABASE_URL from the environment lazily on first use.
# pydantic-settings already resolves env-var-over-.env-file precedence, so
# feed its result back into the process env to guarantee jkr_db sees the same
# value this service was configured with.
os.environ["DATABASE_URL"] = get_settings().database_url


async def platform_db() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


async def workspace_db_from_path(workspace_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with workspace_scoped_session(workspace_id) as session:
        yield session
