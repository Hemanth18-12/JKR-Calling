from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException, Query, status
from jkr_db.models.identity import Session as SessionModel
from jkr_db.models.identity import User
from jkr_db.models.tenancy import Permission, Role, RolePermission, WorkspaceMember
from jkr_db.session import user_scoped_session, workspace_scoped_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import platform_db
from app.security import hash_session_token


class AuthContext:
    """Resolved identity for the current request: who, and (optionally) which
    workspace they're acting in with what permissions."""

    def __init__(self, user: User, session: SessionModel):
        self.user = user
        self.session = session
        self.workspace_id: uuid.UUID | None = None
        self.role_key: str | None = None
        self.permissions: set[str] = set()


async def get_auth_context(
    db: AsyncSession = Depends(platform_db),
    jkr_session: str | None = Cookie(default=None),
) -> AuthContext:
    if not jkr_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    token_hash = hash_session_token(jkr_session)
    result = await db.execute(select(SessionModel).where(SessionModel.token_hash == token_hash))
    session_row = result.scalar_one_or_none()

    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session not found or revoked")
    if session_row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    user_result = await db.execute(select(User).where(User.id == session_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    return AuthContext(user=user, session=session_row)


async def user_db(auth: AuthContext = Depends(get_auth_context)) -> AsyncIterator[AsyncSession]:
    """Session scoped to `app.current_user_id` — the only thing that can
    legitimately query `workspace_members` across more than one workspace at
    once (e.g. "which workspaces am I a member of"). See the dual-condition
    RLS policy on that table in the `cc55370bda3d` migration and the
    docstring on `jkr_db.session.user_scoped_session`."""
    async with user_scoped_session(auth.user.id) as session:
        yield session


async def with_workspace(
    workspace_id: uuid.UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(user_db),
) -> AuthContext:
    """Resolves the active workspace (explicit ?workspace_id= query param, or
    the session's remembered active workspace), loads the caller's membership,
    role and permission set. Never trusts a client-asserted role — only the
    stored WorkspaceMember row for (user, workspace)."""

    resolved_id = workspace_id or auth.session.active_workspace_id
    if resolved_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No workspace selected")

    result = await db.execute(
        select(WorkspaceMember, Role)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.workspace_id == resolved_id, WorkspaceMember.user_id == auth.user.id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
    membership, role = row
    if membership.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Membership is not active")

    perm_result = await db.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    )
    auth.workspace_id = resolved_id
    auth.role_key = role.key
    auth.permissions = {row[0] for row in perm_result.all()}
    return auth


def require_permission(permission_key: str):
    async def _dep(auth: AuthContext = Depends(with_workspace)) -> AuthContext:
        if auth.user.is_platform_super_admin:
            return auth
        if permission_key not in auth.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission_key}")
        return auth

    return _dep


async def workspace_db(auth: AuthContext = Depends(with_workspace)) -> AsyncIterator[AsyncSession]:
    assert auth.workspace_id is not None
    async with workspace_scoped_session(auth.workspace_id) as session:
        yield session


def workspace_db_for(permission_key: str):
    """Combines permission check + RLS-scoped session in one dependency, for
    the common case of a mutating route that needs both."""

    permission_dep = Depends(require_permission(permission_key))

    async def _dep(auth: AuthContext = permission_dep) -> AsyncIterator[AsyncSession]:
        assert auth.workspace_id is not None
        async with workspace_scoped_session(auth.workspace_id) as session:
            yield session

    return _dep


__all__ = [
    "AuthContext",
    "get_auth_context",
    "get_settings",
    "require_permission",
    "user_db",
    "with_workspace",
    "workspace_db",
    "workspace_db_for",
]
