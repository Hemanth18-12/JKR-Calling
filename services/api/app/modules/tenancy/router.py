from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import workspace_db_from_path
from app.deps import AuthContext, get_auth_context, user_db
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    MemberInvite,
    MemberOut,
    MemberUpdate,
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
    # A newly created workspace becomes this session's active workspace so
    # the next page load resolves it without an explicit ?workspace_id=.
    # `auth.session` lives on its own session from get_auth_context's
    # `platform_db` (open for the request's lifetime, auto-committed at the
    # end) — mutate it directly rather than through
    # identity_service.set_active_workspace, whose membership re-check runs
    # on a fresh connection that can't yet see the membership row `db` just
    # flushed but hasn't committed (cross-connection read-committed
    # isolation). We already know this workspace is valid — we just made it.
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
) -> MemberOut:
    await service.require_membership_with_permission(
        db, user=auth.user, workspace_id=workspace_id, permission_key="workspaces:manage_members"
    )
    member = await service.invite_member(
        db, workspace_id=workspace_id, email=payload.email, role_key=payload.role_key
    )
    rows = await service.list_members(db, workspace_id=workspace_id)
    return next(MemberOut(**r) for r in rows if r["id"] == member.id)


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
