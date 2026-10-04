from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import platform_db
from app.deps import AuthContext, get_auth_context, require_permission, with_workspace, workspace_db
from app.modules.coins import service
from app.modules.coins.schemas import (
    COIN_TIERS,
    AdminDashboardOverview,
    AdminReviewRequest,
    CoinTier,
    CoinTopupRequestCreate,
    CoinTopupRequestOut,
    CoinTransactionOut,
    CoinWalletOut,
)

router = APIRouter(prefix="/coins", tags=["coins"])
admin_router = APIRouter(prefix="/admin/coins", tags=["admin-coins"])

ADMIN_EMAIL = "jkrcalling4@gmail.com"


def require_super_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    clean_email = auth.user.email.strip().lower()
    if not auth.user.is_platform_super_admin or clean_email != ADMIN_EMAIL:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Access restricted: Only {ADMIN_EMAIL} is authorized to access platform administration.",
        )
    return auth


# --- Workspace-scoped endpoints ---

@router.get("/tiers", response_model=list[CoinTier])
async def get_coin_tiers() -> list[CoinTier]:
    return COIN_TIERS


@router.get("/wallet", response_model=CoinWalletOut)
async def get_wallet(
    auth: AuthContext = Depends(require_permission("billing:view")),
    db: AsyncSession = Depends(workspace_db),
) -> CoinWalletOut:
    return await service.get_wallet_balance(db, workspace_id=auth.workspace_id)


@router.get("/transactions", response_model=list[CoinTransactionOut])
async def get_transactions(
    auth: AuthContext = Depends(require_permission("billing:view")),
    db: AsyncSession = Depends(workspace_db),
) -> list[CoinTransactionOut]:
    return await service.list_transactions(db, workspace_id=auth.workspace_id)


@router.get("/topup-requests", response_model=list[CoinTopupRequestOut])
async def get_topup_requests(
    auth: AuthContext = Depends(require_permission("billing:view")),
    db: AsyncSession = Depends(workspace_db),
) -> list[CoinTopupRequestOut]:
    return await service.list_topup_requests(db, workspace_id=auth.workspace_id)


@router.post("/topup-requests", response_model=CoinTopupRequestOut)
async def create_topup_request(
    payload: CoinTopupRequestCreate,
    auth: AuthContext = Depends(require_permission("billing:manage")),
    db: AsyncSession = Depends(workspace_db),
) -> CoinTopupRequestOut:
    return await service.create_topup_request(
        db,
        workspace_id=auth.workspace_id,
        user_id=auth.user.id,
        payload=payload,
    )


@router.get("/screenshots/{request_id}")
async def get_screenshot(
    request_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(platform_db),
):
    path = await service.get_screenshot_file_path(db, request_id=request_id, user=auth.user)
    return FileResponse(path, media_type="image/png")


# --- Admin review endpoints ---

@admin_router.get("/topup-requests", response_model=list[CoinTopupRequestOut])
async def admin_list_topup_requests(
    status: Annotated[str | None, Query()] = None,
    auth: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(platform_db),
) -> list[CoinTopupRequestOut]:
    return await service.admin_list_topup_requests(db, status_filter=status)


@admin_router.post("/topup-requests/{request_id}/approve", response_model=CoinTopupRequestOut)
async def admin_approve_topup(
    request_id: uuid.UUID,
    payload: AdminReviewRequest,
    auth: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(platform_db),
) -> CoinTopupRequestOut:
    return await service.admin_approve_topup(
        db,
        request_id=request_id,
        reviewer_id=auth.user.id,
        notes=payload.notes,
    )


@admin_router.post("/topup-requests/{request_id}/reject", response_model=CoinTopupRequestOut)
async def admin_reject_topup(
    request_id: uuid.UUID,
    payload: AdminReviewRequest,
    auth: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(platform_db),
) -> CoinTopupRequestOut:
    return await service.admin_reject_topup(
        db,
        request_id=request_id,
        reviewer_id=auth.user.id,
        notes=payload.notes,
    )


@admin_router.get("/overview", response_model=AdminDashboardOverview)
async def admin_get_overview(
    auth: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(platform_db),
) -> AdminDashboardOverview:
    return await service.get_admin_dashboard_overview(db)

