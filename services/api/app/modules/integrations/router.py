from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    IntegrationCatalogItem,
    WebhookDeliveryOut,
    WebhookEndpointCreate,
    WebhookEndpointOut,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationCatalogItem])
async def catalog(
    auth: AuthContext = Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> list[IntegrationCatalogItem]:
    rows = await service.catalog(db, workspace_id=auth.workspace_id)
    return [IntegrationCatalogItem(**r) for r in rows]


@router.post("/webhooks", response_model=WebhookEndpointOut, status_code=201)
async def create_webhook(
    payload: WebhookEndpointCreate,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> WebhookEndpointOut:
    endpoint = await service.create_webhook_endpoint(
        db, workspace_id=auth.workspace_id, settings=settings, url=payload.url, secret=payload.secret, event_types=payload.event_types,
    )
    return WebhookEndpointOut.model_validate(endpoint, from_attributes=True)


@router.get("/webhooks", response_model=list[WebhookEndpointOut])
async def list_webhooks(
    auth: AuthContext = Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> list[WebhookEndpointOut]:
    endpoints = await service.list_webhook_endpoints(db, workspace_id=auth.workspace_id)
    return [WebhookEndpointOut.model_validate(e, from_attributes=True) for e in endpoints]


@router.post("/webhooks/{endpoint_id}/deactivate", response_model=WebhookEndpointOut)
async def deactivate_webhook(
    endpoint_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> WebhookEndpointOut:
    endpoint = await service.deactivate_webhook_endpoint(db, workspace_id=auth.workspace_id, endpoint_id=endpoint_id)
    return WebhookEndpointOut.model_validate(endpoint, from_attributes=True)


@router.get("/webhooks/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    endpoint_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> list[WebhookDeliveryOut]:
    deliveries = await service.list_deliveries(db, workspace_id=auth.workspace_id, endpoint_id=endpoint_id)
    return [WebhookDeliveryOut.model_validate(d, from_attributes=True) for d in deliveries]
