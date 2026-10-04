from __future__ import annotations

import base64
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from jkr_db.models.coins import CoinTopupRequest, CoinTransaction, CoinWallet
from jkr_db.models.identity import User
from jkr_db.models.tenancy import Workspace
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.coins.schemas import (
    COIN_TIERS,
    CoinTier,
    CoinTopupRequestCreate,
    CoinTopupRequestOut,
    CoinTransactionOut,
    CoinWalletOut,
)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[4] / "storage" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


async def get_or_create_wallet(db: AsyncSession, *, workspace_id: uuid.UUID) -> CoinWallet:
    res = await db.execute(select(CoinWallet).where(CoinWallet.workspace_id == workspace_id))
    wallet = res.scalar_one_or_none()
    if wallet is None:
        wallet = CoinWallet(
            workspace_id=workspace_id,
            balance_coins=0,
            total_recharged_coins=0,
            total_spent_coins=0,
        )
        db.add(wallet)
        await db.flush()
    return wallet


async def get_wallet_balance(db: AsyncSession, *, workspace_id: uuid.UUID) -> CoinWalletOut:
    wallet = await get_or_create_wallet(db, workspace_id=workspace_id)
    return CoinWalletOut(
        workspace_id=wallet.workspace_id,
        balance_coins=wallet.balance_coins,
        total_recharged_coins=wallet.total_recharged_coins,
        total_spent_coins=wallet.total_spent_coins,
    )


async def check_call_allowed(db: AsyncSession, *, workspace_id: uuid.UUID) -> tuple[bool, int, str]:
    wallet = await get_or_create_wallet(db, workspace_id=workspace_id)
    if wallet.balance_coins <= 0:
        return (
            False,
            wallet.balance_coins,
            "Insufficient coin balance. Your balance is 0 coins. Please top up your wallet to make calls (1 coin = 1 second of AI talk time).",
        )
    return True, wallet.balance_coins, ""


async def create_topup_request(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: CoinTopupRequestCreate,
) -> CoinTopupRequestOut:
    tier = next((t for t in COIN_TIERS if t.id == payload.tier_id), None)
    if tier is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid tier_id '{payload.tier_id}'. Valid options: {[t.id for t in COIN_TIERS]}",
        )

    # Duplicate prevention: Check if identical pending request was created in the last 10 minutes
    from datetime import timedelta
    ten_mins_ago = datetime.now(UTC) - timedelta(minutes=10)
    dup_res = await db.execute(
        select(CoinTopupRequest, Workspace.name, User.email)
        .join(Workspace, Workspace.id == CoinTopupRequest.workspace_id)
        .join(User, User.id == CoinTopupRequest.user_id)
        .where(
            CoinTopupRequest.workspace_id == workspace_id,
            CoinTopupRequest.user_id == user_id,
            CoinTopupRequest.tier_id == tier.id,
            CoinTopupRequest.status == "pending",
            CoinTopupRequest.created_at >= ten_mins_ago,
        )
        .order_by(desc(CoinTopupRequest.created_at))
        .limit(1)
    )
    dup_row = dup_res.first()
    if dup_row is not None:
        existing_topup, ws_name, u_email = dup_row
        return CoinTopupRequestOut(
            id=existing_topup.id,
            workspace_id=existing_topup.workspace_id,
            workspace_name=ws_name,
            user_id=existing_topup.user_id,
            user_email=u_email,
            tier_id=existing_topup.tier_id,
            price_inr=existing_topup.price_inr,
            base_coins=existing_topup.base_coins,
            bonus_coins=existing_topup.bonus_coins,
            total_coins=existing_topup.total_coins,
            screenshot_url=f"/api/v1/coins/screenshots/{existing_topup.id}",
            status=existing_topup.status,
            admin_notes=existing_topup.admin_notes,
            reviewed_by=existing_topup.reviewed_by,
            reviewed_at=existing_topup.reviewed_at,
            created_at=existing_topup.created_at,
        )

    # Decode base64 screenshot
    data_str = payload.screenshot_base64
    if "," in data_str:
        data_str = data_str.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(data_str)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid screenshot base64 encoding."
        ) from exc

    req_id = uuid.uuid4()
    filename = f"{req_id}.png"
    file_path = SCREENSHOTS_DIR / filename
    file_path.write_bytes(image_bytes)

    topup = CoinTopupRequest(
        id=req_id,
        workspace_id=workspace_id,
        user_id=user_id,
        tier_id=tier.id,
        price_inr=tier.price_inr,
        base_coins=tier.base_coins,
        bonus_coins=tier.bonus_coins,
        total_coins=tier.total_coins,
        screenshot_path=str(filename),
        status="pending",
    )
    db.add(topup)
    await db.flush()

    # Fetch user/ws metadata
    ws_res = await db.execute(select(Workspace.name).where(Workspace.id == workspace_id))
    ws_name = ws_res.scalar_one_or_none() or "Unknown Workspace"
    u_res = await db.execute(select(User.email).where(User.id == user_id))
    u_email = u_res.scalar_one_or_none() or "unknown@user"

    return CoinTopupRequestOut(
        id=topup.id,
        workspace_id=topup.workspace_id,
        workspace_name=ws_name,
        user_id=topup.user_id,
        user_email=u_email,
        tier_id=topup.tier_id,
        price_inr=topup.price_inr,
        base_coins=topup.base_coins,
        bonus_coins=topup.bonus_coins,
        total_coins=topup.total_coins,
        screenshot_url=f"/api/v1/coins/screenshots/{topup.id}",
        status=topup.status,
        admin_notes=topup.admin_notes,
        reviewed_by=topup.reviewed_by,
        reviewed_at=topup.reviewed_at,
        created_at=topup.created_at,
    )


async def list_topup_requests(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[CoinTopupRequestOut]:
    res = await db.execute(
        select(CoinTopupRequest, Workspace.name, User.email)
        .join(Workspace, Workspace.id == CoinTopupRequest.workspace_id)
        .join(User, User.id == CoinTopupRequest.user_id)
        .where(CoinTopupRequest.workspace_id == workspace_id)
        .order_by(desc(CoinTopupRequest.created_at))
    )
    items = []
    for topup, ws_name, u_email in res.all():
        items.append(
            CoinTopupRequestOut(
                id=topup.id,
                workspace_id=topup.workspace_id,
                workspace_name=ws_name,
                user_id=topup.user_id,
                user_email=u_email,
                tier_id=topup.tier_id,
                price_inr=topup.price_inr,
                base_coins=topup.base_coins,
                bonus_coins=topup.bonus_coins,
                total_coins=topup.total_coins,
                screenshot_url=f"/api/v1/coins/screenshots/{topup.id}",
                status=topup.status,
                admin_notes=topup.admin_notes,
                reviewed_by=topup.reviewed_by,
                reviewed_at=topup.reviewed_at,
                created_at=topup.created_at,
            )
        )
    return items


async def list_transactions(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[CoinTransactionOut]:
    res = await db.execute(
        select(CoinTransaction)
        .where(CoinTransaction.workspace_id == workspace_id)
        .order_by(desc(CoinTransaction.created_at))
        .limit(100)
    )
    return [
        CoinTransactionOut(
            id=tx.id,
            workspace_id=tx.workspace_id,
            user_id=tx.user_id,
            amount_coins=tx.amount_coins,
            transaction_type=tx.transaction_type,
            reference_id=tx.reference_id,
            description=tx.description,
            balance_after=tx.balance_after,
            created_at=tx.created_at,
        )
        for tx in res.scalars().all()
    ]


async def admin_list_topup_requests(
    db: AsyncSession, *, status_filter: str | None = None
) -> list[CoinTopupRequestOut]:
    query = (
        select(CoinTopupRequest, Workspace.name, User.email)
        .join(Workspace, Workspace.id == CoinTopupRequest.workspace_id)
        .join(User, User.id == CoinTopupRequest.user_id)
        .order_by(desc(CoinTopupRequest.created_at))
    )
    if status_filter and status_filter != "all":
        query = query.where(CoinTopupRequest.status == status_filter)

    res = await db.execute(query)
    items = []
    for topup, ws_name, u_email in res.all():
        items.append(
            CoinTopupRequestOut(
                id=topup.id,
                workspace_id=topup.workspace_id,
                workspace_name=ws_name,
                user_id=topup.user_id,
                user_email=u_email,
                tier_id=topup.tier_id,
                price_inr=topup.price_inr,
                base_coins=topup.base_coins,
                bonus_coins=topup.bonus_coins,
                total_coins=topup.total_coins,
                screenshot_url=f"/api/v1/coins/screenshots/{topup.id}",
                status=topup.status,
                admin_notes=topup.admin_notes,
                reviewed_by=topup.reviewed_by,
                reviewed_at=topup.reviewed_at,
                created_at=topup.created_at,
            )
        )
    return items


async def admin_approve_topup(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    notes: str | None = None,
) -> CoinTopupRequestOut:
    res = await db.execute(
        select(CoinTopupRequest, Workspace.name, User.email)
        .join(Workspace, Workspace.id == CoinTopupRequest.workspace_id)
        .join(User, User.id == CoinTopupRequest.user_id)
        .where(CoinTopupRequest.id == request_id)
    )
    row = res.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Top-up request not found.")
    topup, ws_name, u_email = row

    if topup.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot approve request with status '{topup.status}'. Only pending requests can be approved.",
        )

    wallet = await get_or_create_wallet(db, workspace_id=topup.workspace_id)
    wallet.balance_coins += topup.total_coins
    wallet.total_recharged_coins += topup.total_coins

    now = datetime.now(UTC)
    topup.status = "approved"
    topup.reviewed_by = reviewer_id
    topup.reviewed_at = now
    topup.admin_notes = notes

    tx = CoinTransaction(
        workspace_id=topup.workspace_id,
        user_id=topup.user_id,
        amount_coins=topup.total_coins,
        transaction_type="topup",
        reference_id=str(topup.id),
        description=f"UPI Top-up approved (Rs. {topup.price_inr} for {topup.total_coins} coins)",
        balance_after=wallet.balance_coins,
    )
    db.add(tx)
    await db.flush()

    return CoinTopupRequestOut(
        id=topup.id,
        workspace_id=topup.workspace_id,
        workspace_name=ws_name,
        user_id=topup.user_id,
        user_email=u_email,
        tier_id=topup.tier_id,
        price_inr=topup.price_inr,
        base_coins=topup.base_coins,
        bonus_coins=topup.bonus_coins,
        total_coins=topup.total_coins,
        screenshot_url=f"/api/v1/coins/screenshots/{topup.id}",
        status=topup.status,
        admin_notes=topup.admin_notes,
        reviewed_by=topup.reviewed_by,
        reviewed_at=topup.reviewed_at,
        created_at=topup.created_at,
    )


async def admin_reject_topup(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    notes: str | None = None,
) -> CoinTopupRequestOut:
    res = await db.execute(
        select(CoinTopupRequest, Workspace.name, User.email)
        .join(Workspace, Workspace.id == CoinTopupRequest.workspace_id)
        .join(User, User.id == CoinTopupRequest.user_id)
        .where(CoinTopupRequest.id == request_id)
    )
    row = res.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Top-up request not found.")
    topup, ws_name, u_email = row

    if topup.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot reject request with status '{topup.status}'. Only pending requests can be rejected.",
        )

    now = datetime.now(UTC)
    topup.status = "rejected"
    topup.reviewed_by = reviewer_id
    topup.reviewed_at = now
    topup.admin_notes = notes
    await db.flush()

    return CoinTopupRequestOut(
        id=topup.id,
        workspace_id=topup.workspace_id,
        workspace_name=ws_name,
        user_id=topup.user_id,
        user_email=u_email,
        tier_id=topup.tier_id,
        price_inr=topup.price_inr,
        base_coins=topup.base_coins,
        bonus_coins=topup.bonus_coins,
        total_coins=topup.total_coins,
        screenshot_url=f"/api/v1/coins/screenshots/{topup.id}",
        status=topup.status,
        admin_notes=topup.admin_notes,
        reviewed_by=topup.reviewed_by,
        reviewed_at=topup.reviewed_at,
        created_at=topup.created_at,
    )


async def deduct_call_coins(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    call_id: uuid.UUID,
    duration_seconds: int,
) -> int:
    coins_to_deduct = max(0, int(duration_seconds))
    if coins_to_deduct == 0:
        return 0

    wallet = await get_or_create_wallet(db, workspace_id=workspace_id)
    wallet.balance_coins = max(0, wallet.balance_coins - coins_to_deduct)
    wallet.total_spent_coins += coins_to_deduct

    tx = CoinTransaction(
        workspace_id=workspace_id,
        user_id=None,
        amount_coins=-coins_to_deduct,
        transaction_type="call_deduction",
        reference_id=str(call_id),
        description=f"Call usage: {duration_seconds}s AI conversation ({coins_to_deduct} coins)",
        balance_after=wallet.balance_coins,
    )
    db.add(tx)
    await db.flush()
    return wallet.balance_coins


async def get_screenshot_file_path(
    db: AsyncSession, *, request_id: uuid.UUID, user: User
) -> Path:
    res = await db.execute(select(CoinTopupRequest).where(CoinTopupRequest.id == request_id))
    topup = res.scalar_one_or_none()
    if topup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found.")

    # Access security: only the user who created it, or the platform super admin (jkrcalling4@gmail.com), can view
    is_admin = user.is_platform_super_admin and user.email.strip().lower() == "jkrcalling4@gmail.com"
    if not is_admin and topup.user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You do not have permission to view this screenshot."
        )

    file_path = SCREENSHOTS_DIR / topup.screenshot_path
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot file not found on disk.")

    return file_path


async def get_admin_dashboard_overview(db: AsyncSession) -> AdminDashboardOverview:
    from datetime import timedelta
    from jkr_db.models.calls import CallSession
    from jkr_db.models.tenancy import WorkspaceMember
    from sqlalchemy import func
    from app.modules.coins.schemas import AdminDashboardOverview, AdminTierRevenue, AdminUserSummary

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Revenue totals
    tot_rev_res = await db.execute(
        select(func.coalesce(func.sum(CoinTopupRequest.price_inr), 0))
        .where(CoinTopupRequest.status == "approved")
    )
    total_revenue_inr = int(tot_rev_res.scalar() or 0)

    month_rev_res = await db.execute(
        select(func.coalesce(func.sum(CoinTopupRequest.price_inr), 0))
        .where(CoinTopupRequest.status == "approved", CoinTopupRequest.created_at >= month_start)
    )
    revenue_this_month_inr = int(month_rev_res.scalar() or 0)

    week_rev_res = await db.execute(
        select(func.coalesce(func.sum(CoinTopupRequest.price_inr), 0))
        .where(CoinTopupRequest.status == "approved", CoinTopupRequest.created_at >= week_start)
    )
    revenue_this_week_inr = int(week_rev_res.scalar() or 0)

    # 2. Revenue breakdown by tier
    tier_counts = await db.execute(
        select(
            CoinTopupRequest.tier_id,
            func.count(CoinTopupRequest.id),
            func.coalesce(func.sum(CoinTopupRequest.price_inr), 0),
        )
        .where(CoinTopupRequest.status == "approved")
        .group_by(CoinTopupRequest.tier_id)
    )
    tier_map = {r[0]: (int(r[1]), int(r[2])) for r in tier_counts.all()}
    revenue_by_tier = []
    for t in COIN_TIERS:
        cnt, rev = tier_map.get(t.id, (0, 0))
        revenue_by_tier.append(
            AdminTierRevenue(
                tier_id=t.id,
                price_inr=t.price_inr,
                total_coins=t.total_coins,
                approved_count=cnt,
                total_revenue_inr=rev,
            )
        )

    # 3. Top-up request counts
    req_counts = await db.execute(
        select(
            CoinTopupRequest.status,
            func.count(CoinTopupRequest.id),
            func.coalesce(func.sum(CoinTopupRequest.total_coins), 0),
        )
        .group_by(CoinTopupRequest.status)
    )
    req_map = {r[0]: (int(r[1]), int(r[2])) for r in req_counts.all()}
    pending_count = req_map.get("pending", (0, 0))[0]
    approved_count = req_map.get("approved", (0, 0))[0]
    rejected_count = req_map.get("rejected", (0, 0))[0]
    total_coins_recharged = req_map.get("approved", (0, 0))[1]

    # 4. Usage overview
    wallet_usage = await db.execute(
        select(func.coalesce(func.sum(CoinWallet.total_spent_coins), 0))
    )
    total_coins_spent = int(wallet_usage.scalar() or 0)

    calls_usage = await db.execute(
        select(func.count(CallSession.id), func.coalesce(func.sum(CallSession.duration_seconds), 0))
    )
    total_calls_count, total_call_seconds = calls_usage.one()
    total_calls_count = int(total_calls_count or 0)
    total_call_seconds = int(total_call_seconds or 0)

    # 5. User Overview
    users_count_res = await db.execute(select(func.count(User.id)))
    total_users_count = int(users_count_res.scalar() or 0)

    ws_count_res = await db.execute(select(func.count(Workspace.id)))
    total_workspaces_count = int(ws_count_res.scalar() or 0)

    # Load users with their workspaces and wallets
    user_rows = await db.execute(
        select(
            User.id,
            User.email,
            User.full_name,
            User.created_at,
            User.last_login_at,
            Workspace.id.label("workspace_id"),
            Workspace.name.label("workspace_name"),
            func.coalesce(CoinWallet.balance_coins, 0),
            func.coalesce(CoinWallet.total_recharged_coins, 0),
            func.coalesce(CoinWallet.total_spent_coins, 0),
        )
        .outerjoin(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .outerjoin(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .outerjoin(CoinWallet, CoinWallet.workspace_id == Workspace.id)
        .order_by(desc(User.created_at))
        .limit(100)
    )
    users_list = []
    seen_users = set()
    for row in user_rows.all():
        u_id = row[0]
        if u_id in seen_users:
            continue
        seen_users.add(u_id)
        users_list.append(
            AdminUserSummary(
                user_id=u_id,
                email=row[1],
                full_name=row[2],
                signup_date=row[3],
                last_login_at=row[4],
                workspace_id=row[5],
                workspace_name=row[6] or "No Workspace",
                coin_balance=int(row[7]),
                total_recharged_coins=int(row[8]),
                total_spent_coins=int(row[9]),
            )
        )

    return AdminDashboardOverview(
        total_revenue_inr=total_revenue_inr,
        revenue_this_month_inr=revenue_this_month_inr,
        revenue_this_week_inr=revenue_this_week_inr,
        revenue_by_tier=revenue_by_tier,
        pending_requests_count=pending_count,
        approved_requests_count=approved_count,
        rejected_requests_count=rejected_count,
        total_coins_recharged=total_coins_recharged,
        total_coins_spent=total_coins_spent,
        total_call_seconds=total_call_seconds,
        total_calls_count=total_calls_count,
        total_users_count=total_users_count,
        total_workspaces_count=total_workspaces_count,
        users=users_list,
    )

