from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jkr_db.models.identity import User
from jkr_db.models.tenancy import Organization, Role, Workspace, WorkspaceMember, WorkspaceInvitation
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.identity.email_service import send_invitation_email
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
    if db.bind and db.bind.dialect.name == "postgresql":
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
    # 1. Active and existing workspace members
    result = await db.execute(
        select(WorkspaceMember, User, Role)
        .join(User, User.id == WorkspaceMember.user_id)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.full_name)
    )
    members_list = [
        {
            "id": member.id,
            "user_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role_key": role.key,
            "status": member.status,
            "invited_at": member.invited_at,
            "joined_at": member.joined_at,
            "invitation_id": None,
        }
        for member, user, role in result.all()
    ]

    active_emails = {m["email"].lower() for m in members_list}

    # 2. Pending invitations for this workspace
    inv_result = await db.execute(
        select(WorkspaceInvitation, Role)
        .join(Role, Role.id == WorkspaceInvitation.role_id)
        .where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.status == "pending",
            WorkspaceInvitation.expires_at > datetime.now(UTC),
        )
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    for inv, role in inv_result.all():
        if inv.email.lower() not in active_emails:
            members_list.append(
                {
                    "id": inv.id,
                    "user_id": None,
                    "email": inv.email,
                    "full_name": inv.email.split("@")[0].replace(".", " ").title(),
                    "role_key": role.key,
                    "status": "invited",
                    "invited_at": inv.created_at,
                    "joined_at": None,
                    "invitation_id": inv.id,
                }
            )

    return members_list


async def invite_member(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    inviter: User,
    email: str,
    role_key: str,
    settings: Settings,
) -> dict:
    clean_email = email.strip().lower()
    workspace = await get_workspace_or_404(db, workspace_id)

    role_result = await db.execute(select(Role).where(Role.key == role_key))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{role_key}'")

    # Check if already an active member of this workspace
    user_result = await db.execute(select(User).where(User.email == clean_email))
    existing_user = user_result.scalar_one_or_none()
    if existing_user:
        existing_mem = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == existing_user.id,
                WorkspaceMember.status == "active",
            )
        )
        if existing_mem.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "User is already an active member of this workspace")

    # Invalidate previous pending invitations for this email in this workspace
    prev_invs = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == clean_email,
            WorkspaceInvitation.status == "pending",
        )
    )
    for prev in prev_invs.scalars().all():
        prev.status = "revoked"

    # Generate secure random token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(days=7)

    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        email=clean_email,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        token_hash=token_hash,
        status="pending",
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.flush()

    # Dispatch email via Brevo
    app_base = (settings.app_base_url or "http://localhost:3000").rstrip("/")
    invite_url = f"{app_base}/invite/accept?token={raw_token}"
    inviter_name = inviter.full_name or inviter.email.split("@")[0]
    role_name = role.name or role.key.replace("_", " ").title()

    await send_invitation_email(
        to_email=clean_email,
        workspace_name=workspace.name,
        inviter_name=inviter_name,
        role_name=role_name,
        invite_url=invite_url,
    )

    return {
        "id": invitation.id,
        "workspace_id": workspace_id,
        "email": clean_email,
        "role_key": role.key,
        "status": "pending",
        "expires_at": expires_at,
        "created_at": invitation.created_at,
    }


async def resend_invitation(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    inviter: User,
    settings: Settings,
) -> dict:
    inv_result = await db.execute(
        select(WorkspaceInvitation, Role, Workspace)
        .join(Role, Role.id == WorkspaceInvitation.role_id)
        .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
        .where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.workspace_id == workspace_id,
        )
    )
    row = inv_result.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    invitation, role, workspace = row

    raw_token = secrets.token_urlsafe(32)
    invitation.token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation.status = "pending"
    invitation.expires_at = datetime.now(UTC) + timedelta(days=7)
    await db.flush()

    app_base = (settings.app_base_url or "http://localhost:3000").rstrip("/")
    invite_url = f"{app_base}/invite/accept?token={raw_token}"
    inviter_name = inviter.full_name or inviter.email.split("@")[0]
    role_name = role.name or role.key.replace("_", " ").title()

    await send_invitation_email(
        to_email=invitation.email,
        workspace_name=workspace.name,
        inviter_name=inviter_name,
        role_name=role_name,
        invite_url=invite_url,
    )

    return {
        "id": invitation.id,
        "workspace_id": workspace_id,
        "email": invitation.email,
        "role_key": role.key,
        "status": "pending",
        "expires_at": invitation.expires_at,
        "created_at": invitation.created_at,
    }


async def revoke_invitation(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> None:
    inv_result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.workspace_id == workspace_id,
        )
    )
    invitation = inv_result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    invitation.status = "revoked"
    await db.flush()


def _is_expired(dt: datetime) -> bool:
    if dt.tzinfo is None:
        return dt < datetime.now(UTC).replace(tzinfo=None)
    return dt < datetime.now(UTC)


async def get_invitation_details_by_token(
    db: AsyncSession,
    *,
    token: str,
) -> dict:
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    res = await db.execute(
        select(WorkspaceInvitation, Workspace, Role, User)
        .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
        .join(Role, Role.id == WorkspaceInvitation.role_id)
        .join(User, User.id == WorkspaceInvitation.invited_by_user_id)
        .where(WorkspaceInvitation.token_hash == token_hash)
    )
    row = res.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found or link is invalid.")
    invitation, workspace, role, inviter = row
    if invitation.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This invitation is no longer valid (status: {invitation.status}).")
    if _is_expired(invitation.expires_at):
        invitation.status = "expired"
        await db.flush()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation link has expired.")

    return {
        "workspace_name": workspace.name,
        "role_key": role.key,
        "role_name": role.name or role.key.replace("_", " ").title(),
        "inviter_name": inviter.full_name or inviter.email.split("@")[0],
        "email": invitation.email,
        "expires_at": invitation.expires_at,
    }


async def accept_invitation(
    db: AsyncSession,
    *,
    current_user: User,
    token: str | None = None,
    invitation_id: uuid.UUID | None = None,
) -> dict:
    if token:
        token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
        stmt = (
            select(WorkspaceInvitation, Workspace, Role)
            .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
            .join(Role, Role.id == WorkspaceInvitation.role_id)
            .where(WorkspaceInvitation.token_hash == token_hash)
        )
    elif invitation_id:
        stmt = (
            select(WorkspaceInvitation, Workspace, Role)
            .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
            .join(Role, Role.id == WorkspaceInvitation.role_id)
            .where(
                WorkspaceInvitation.id == invitation_id,
                WorkspaceInvitation.email == current_user.email.lower(),
            )
        )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Either token or invitation_id must be provided.")

    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found or link is invalid.")
    invitation, workspace, role = row

    if invitation.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This invitation is already {invitation.status}.")
    if _is_expired(invitation.expires_at):
        invitation.status = "expired"
        await db.flush()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation link has expired.")

    # Guard: invited email must match current user email!
    if current_user.email.lower() != invitation.email.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This invitation was sent to {invitation.email}. You are currently signed in as {current_user.email}. Please switch accounts to accept this invitation.",
        )

    # Check if membership already exists
    mem_res = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == invitation.workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )
    existing_mem = mem_res.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing_mem:
        existing_mem.status = "active"
        existing_mem.role_id = invitation.role_id
        if not existing_mem.joined_at:
            existing_mem.joined_at = now
    else:
        db.add(
            WorkspaceMember(
                workspace_id=invitation.workspace_id,
                user_id=current_user.id,
                role_id=invitation.role_id,
                status="active",
                joined_at=now,
            )
        )

    invitation.status = "accepted"
    invitation.accepted_at = now
    invitation.accepted_by_user_id = current_user.id
    await db.flush()

    return {
        "success": True,
        "workspace_id": invitation.workspace_id,
        "workspace_name": workspace.name,
        "role_key": role.key,
    }


async def decline_invitation(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    current_user: User,
) -> None:
    res = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.email == current_user.email.lower(),
            WorkspaceInvitation.status == "pending",
        )
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pending invitation not found.")
    invitation.status = "declined"
    await db.flush()


async def list_pending_invitations_for_user(
    db: AsyncSession,
    *,
    user_email: str,
) -> list[dict]:
    res = await db.execute(
        select(WorkspaceInvitation, Workspace, Role, User)
        .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
        .join(Role, Role.id == WorkspaceInvitation.role_id)
        .join(User, User.id == WorkspaceInvitation.invited_by_user_id)
        .where(
            WorkspaceInvitation.email == user_email.lower(),
            WorkspaceInvitation.status == "pending",
            WorkspaceInvitation.expires_at > datetime.now(UTC),
        )
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    return [
        {
            "id": inv.id,
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "role_key": role.key,
            "role_name": role.name or role.key.replace("_", " ").title(),
            "inviter_name": inviter.full_name or inviter.email.split("@")[0],
            "email": inv.email,
            "expires_at": inv.expires_at,
        }
        for inv, ws, role, inviter in res.all()
    ]


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
        if status_value == "suspended":
            role_result = await db.execute(select(Role.key).where(Role.id == member.role_id))
            if role_result.scalar_one_or_none() == "workspace_owner":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot suspend the workspace owner.")
        member.status = status_value
        if status_value == "active" and member.joined_at is None:
            member.joined_at = datetime.now(UTC)

    await db.flush()
    return member

