from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import workspace_db_from_path
from app.deps import AuthContext, get_auth_context, user_db
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    InvitationDetailsPublic,
    MemberInvite,
    MemberOut,
    MemberUpdate,
    PendingInvitationOut,
    WorkspaceCreate,
    WorkspaceListItem,
    WorkspaceOut,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceOut:
    workspace = await service.create_workspace_with_owner(
        db,
        owner=auth.user,
        name=payload.name,
        slug=payload.slug,
        timezone=payload.timezone,
        default_language=payload.default_language,
    )
    auth.session.active_workspace_id = workspace.id
    return WorkspaceOut.model_validate(workspace)


@router.get("", response_model=list[WorkspaceListItem])
async def list_workspaces(
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[WorkspaceListItem]:
    rows = await service.list_workspaces_for_user(db, user_id=auth.user.id)
    return [
        WorkspaceListItem(**WorkspaceOut.model_validate(row["workspace"]).model_dump(), role_key=row["role_key"])
        for row in rows
    ]


@router.get("/invitations/pending", response_model=list[PendingInvitationOut])
async def get_user_pending_invitations(
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[PendingInvitationOut]:
    items = await service.list_pending_invitations_for_user(db, user_email=auth.user.email)
    return [PendingInvitationOut(**it) for it in items]


@router.get("/invitations/details", response_model=InvitationDetailsPublic)
async def get_public_invitation_details(
    token: str,
    db: AsyncSession = Depends(user_db),
) -> InvitationDetailsPublic:
    res = await service.get_invitation_details_by_token(db, token=token)
    return InvitationDetailsPublic(**res)


@router.post("/invitations/accept", response_model=AcceptInvitationResponse)
async def post_accept_invitation(
    payload: AcceptInvitationRequest,
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AcceptInvitationResponse:
    res = await service.accept_invitation(
        db,
        current_user=auth.user,
        token=payload.token,
        invitation_id=payload.invitation_id,
    )
    auth.session.active_workspace_id = res["workspace_id"]
    return AcceptInvitationResponse(**res)


@router.post("/invitations/{invitation_id}/decline", status_code=204)
async def post_decline_invitation(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
) -> None:
    await service.decline_invitation(
        db,
        invitation_id=invitation_id,
        current_user=auth.user,
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:view"
    )
    workspace = await service.get_workspace_or_404(db, workspace_id)
    return WorkspaceOut.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def patch_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage"
    )
    workspace = await service.get_workspace_or_404(db, workspace_id)
    workspace = await service.update_workspace(db, workspace, **payload.model_dump(exclude_unset=True))
    return WorkspaceOut.model_validate(workspace)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def get_members(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
) -> list[MemberOut]:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:view"
    )
    rows = await service.list_members(db, workspace_id=workspace_id)
    return [MemberOut(**row) for row in rows]


@router.post("/{workspace_id}/members", response_model=MemberOut, status_code=201)
async def post_member(
    workspace_id: uuid.UUID,
    payload: MemberInvite,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage_members"
    )
    invitation = await service.invite_member(
        db,
        workspace_id=workspace_id,
        inviter=auth.user,
        email=payload.email,
        role_key=payload.role_key,
        settings=settings,
    )
    rows = await service.list_members(db, workspace_id=workspace_id)
    return next(MemberOut(**r) for r in rows if r["email"].lower() == payload.email.lower())


@router.post("/{workspace_id}/invitations/{invitation_id}/resend", response_model=MemberOut)
async def resend_member_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage_members"
    )
    await service.resend_invitation(
        db,
        workspace_id=workspace_id,
        invitation_id=invitation_id,
        inviter=auth.user,
        settings=settings,
    )
    rows = await service.list_members(db, workspace_id=workspace_id)
    return next(
        MemberOut(**r)
        for r in rows
        if r["id"] == invitation_id or r.get("invitation_id") == invitation_id
    )


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=204)
async def revoke_member_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
) -> None:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage_members"
    )
    await service.revoke_invitation(
        db,
        workspace_id=workspace_id,
        invitation_id=invitation_id,
    )


@router.patch("/{workspace_id}/members/{member_id}", response_model=MemberOut)
async def patch_member(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberUpdate,
    db: AsyncSession = Depends(workspace_db_from_path),
    auth: AuthContext = Depends(get_auth_context),
) -> MemberOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage_members"
    )
    await service.update_member(
        db, workspace_id=workspace_id, member_id=member_id, role_key=payload.role_key, status_value=payload.status
    )
    rows = await service.list_members(db, workspace_id=workspace_id)
    return next(MemberOut(**r) for r in rows if r["id"] == member_id)

