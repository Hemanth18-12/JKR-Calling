from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.deps import require_permission, workspace_db_for
from app.modules.providers import service
from app.modules.providers.schemas import (
    ProviderAccountCreate,
    ProviderAccountOut,
    ProviderAccountUpdate,
    ProviderCatalogEntry,
    ProviderHealthOut,
)

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/catalog", response_model=list[ProviderCatalogEntry])
async def get_catalog(_auth=Depends(require_permission("integrations:view"))) -> list[ProviderCatalogEntry]:
    return [ProviderCatalogEntry(**entry) for entry in service.CATALOG]


@router.get("/accounts", response_model=list[ProviderAccountOut])
async def list_accounts(
    auth=Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> list[ProviderAccountOut]:
    accounts = await service.list_accounts(db, workspace_id=auth.workspace_id)
    return [ProviderAccountOut.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=ProviderAccountOut, status_code=201)
async def create_account(
    payload: ProviderAccountCreate,
    settings: Settings = Depends(get_settings),
    auth=Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> ProviderAccountOut:
    account = await service.create_account(db, workspace_id=auth.workspace_id, settings=settings, payload=payload)
    return ProviderAccountOut.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=ProviderAccountOut)
async def update_account(
    account_id: uuid.UUID,
    payload: ProviderAccountUpdate,
    settings: Settings = Depends(get_settings),
    auth=Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> ProviderAccountOut:
    account = await service.update_account(
        db, workspace_id=auth.workspace_id, account_id=account_id, settings=settings, payload=payload
    )
    return ProviderAccountOut.model_validate(account)


@router.post("/accounts/{account_id}/health-check", response_model=ProviderHealthOut)
async def health_check(
    account_id: uuid.UUID,
    auth=Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> ProviderHealthOut:
    record = await service.health_check(db, workspace_id=auth.workspace_id, account_id=account_id)
    return ProviderHealthOut.model_validate(record)
