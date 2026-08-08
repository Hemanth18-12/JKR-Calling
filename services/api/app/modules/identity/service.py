from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jkr_db.models.identity import PasswordCredential, User
from jkr_db.models.identity import Session as SessionModel
from jkr_db.models.tenancy import Role, Workspace, WorkspaceMember
from jkr_db.session import user_scoped_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.security import generate_session_token, hash_password, hash_session_token, verify_password


async def create_user(db: AsyncSession, *, email: str, full_name: str, password: str) -> User:
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=email.lower(), full_name=full_name)
    db.add(user)
    await db.flush()

    db.add(PasswordCredential(user_id=user.id, password_hash=hash_password(password)))
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User:
    result = await db.execute(
        select(User, PasswordCredential)
        .join(PasswordCredential, PasswordCredential.user_id == User.id)
        .where(User.email == email.lower())
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    user, credential = row
    if not user.is_active or not verify_password(password, credential.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


async def create_session(
    db: AsyncSession,
    *,
    user: User,
    settings: Settings,
    user_agent: str | None,
    ip_address: str | None,
    active_workspace_id: uuid.UUID | None = None,
) -> tuple[SessionModel, str]:
    if active_workspace_id is None:
        # workspace_members carries RLS (docs/DECISIONS/0004-tenant-isolation.md);
        # `db` here is an unscoped platform session, which — correctly — can
        # see none of it. Open a short-lived user-scoped session just for this
        # lookup rather than widening what `db` itself is allowed to touch.
        async with user_scoped_session(user.id) as scoped:
            first_membership = await scoped.execute(
                select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id).limit(1)
            )
            active_workspace_id = first_membership.scalar_one_or_none()

    raw_token = generate_session_token()
    session_row = SessionModel(
        user_id=user.id,
        active_workspace_id=active_workspace_id,
        token_hash=hash_session_token(raw_token),
        user_agent=(user_agent or "")[:500],
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session_row)
    await db.flush()
    return session_row, raw_token


async def set_active_workspace(
    db: AsyncSession, *, session_row: SessionModel, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> SessionModel:
    """Switch which workspace a session defaults to (workspace switcher, or
    right after creating your first workspace). Requires an active
    membership — never trusts the caller's assertion alone."""
    async with user_scoped_session(user_id) as scoped:
        membership = await scoped.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.status == "active",
            )
        )
        if membership.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an active member of this workspace")

    session_row.active_workspace_id = workspace_id
    await db.flush()
    return session_row


async def revoke_session(db: AsyncSession, *, token_hash: str) -> None:
    result = await db.execute(select(SessionModel).where(SessionModel.token_hash == token_hash))
    session_row = result.scalar_one_or_none()
    if session_row is not None:
        session_row.revoked_at = datetime.now(UTC)
        await db.flush()


async def list_memberships(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(WorkspaceMember, Workspace, Role)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active")
        .order_by(Workspace.name)
    )
    return [
        {
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "workspace_slug": workspace.slug,
            "role_key": role.key,
        }
        for _membership, workspace, role in result.all()
    ]
