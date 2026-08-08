from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.identity import User
from jkr_db.models.tenancy import Organization, Role, Workspace, WorkspaceMember
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.providers import service as providers_service
from app.modules.tools import service as tools_service


async def create_workspace_with_owner(
    db: AsyncSession, *, owner: User, name: str, slug: str, timezone: str, default_language: str
) -> Workspace:
    existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Workspace slug '{slug}' is already taken")

    owner_role = await db.execute(select(Role).where(Role.key == "workspace_owner"))
    role = owner_role.scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "RBAC catalog not seeded")

    org = Organization(name=name)
    db.add(org)
    await db.flush()

    workspace = Workspace(
        organization_id=org.id, name=name, slug=slug, timezone=timezone, default_language=default_language
    )
    db.add(workspace)
    await db.flush()

    # This session only carries `app.current_user_id` (docs/DECISIONS/0004,
    # `user_scoped_session`) — the WorkspaceMember insert below relies on that
    # (its dual-condition policy), but provider_accounts/provider_health use
    # the plain single-workspace policy, so it needs `app.current_workspace_id`
    # set too, for this workspace we just created. `workspace.id` is a
    # uuid.UUID from the ORM, never raw client input, so interpolating its
    # str() form is safe (same reasoning as jkr_db.session._validated_uuid_literal).
    await db.execute(text(f"SET LOCAL app.current_workspace_id = '{workspace.id}'"))

    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=owner.id,
            role_id=role.id,
            status="active",
            joined_at=datetime.now(UTC),
        )
    )
    await providers_service.seed_default_accounts(db, workspace_id=workspace.id)
    await tools_service.seed_default_tool_definitions(db, workspace_id=workspace.id)
    await db.flush()
    return workspace


async def list_workspaces_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Workspace, Role.key)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active")
        .order_by(Workspace.name)
    )
    return [{"workspace": ws, "role_key": role_key} for ws, role_key in result.all()]


async def get_membership(
    db: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> tuple[WorkspaceMember, Role] | None:
    result = await db.execute(
        select(WorkspaceMember, Role)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.workspace_id == workspace_id)
    )
    return result.first()


async def require_membership_with_permission(
    db: AsyncSession, *, user: User, workspace_id: uuid.UUID, permission_key: str
) -> tuple[WorkspaceMember, Role]:
    row = await get_membership(db, user_id=user.id, workspace_id=workspace_id)
    if row is None or row[0].status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an active member of this workspace")
    membership, role = row
    if user.is_platform_super_admin:
        return membership, role

    from jkr_db.models.tenancy import Permission, RolePermission

    perm_result = await db.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id, Permission.key == permission_key)
    )
    if perm_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission_key}")
    return membership, role


async def get_workspace_or_404(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


async def update_workspace(db: AsyncSession, workspace: Workspace, **fields) -> Workspace:
    for key, value in fields.items():
        if value is not None:
            setattr(workspace, key, value)
    await db.flush()
    return workspace


async def list_members(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(WorkspaceMember, User, Role)
        .join(User, User.id == WorkspaceMember.user_id)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.full_name)
    )
    return [
        {
            "id": member.id,
            "user_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role_key": role.key,
            "status": member.status,
            "invited_at": member.invited_at,
            "joined_at": member.joined_at,
        }
        for member, user, role in result.all()
    ]


async def invite_member(
    db: AsyncSession, *, workspace_id: uuid.UUID, email: str, role_key: str
) -> WorkspaceMember:
    user_result = await db.execute(select(User).where(User.email == email.lower()))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No account with this email yet — ask them to sign up first, then invite them.",
        )

    role_result = await db.execute(select(Role).where(Role.key == role_key))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{role_key}'")

    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this workspace")

    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user.id,
        role_id=role.id,
        status="invited",
        invited_at=datetime.now(UTC),
    )
    db.add(member)
    await db.flush()
    return member


async def update_member(
    db: AsyncSession, *, workspace_id: uuid.UUID, member_id: uuid.UUID, role_key: str | None, status_value: str | None
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    if role_key is not None:
        role_result = await db.execute(select(Role).where(Role.key == role_key))
        role = role_result.scalar_one_or_none()
        if role is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{role_key}'")
        member.role_id = role.id
    if status_value is not None:
        member.status = status_value
        if status_value == "active" and member.joined_at is None:
            member.joined_at = datetime.now(UTC)

    await db.flush()
    return member
