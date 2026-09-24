from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    GoogleCalendarConnectRequest,
    GoogleCalendarStatusOut,
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


# --- Google Calendar Endpoints ---

@router.get("/google-calendar/auth-url")
async def get_google_calendar_auth_url_endpoint(
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    url = service.get_google_calendar_auth_url(auth.workspace_id, settings)
    return {"auth_url": url}


@router.post("/google-calendar/connect", response_model=GoogleCalendarStatusOut)
async def connect_google_calendar_endpoint(
    payload: GoogleCalendarConnectRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> GoogleCalendarStatusOut:
    await service.connect_google_calendar(
        db,
        workspace_id=auth.workspace_id,
        settings=settings,
        code=payload.code,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        email=payload.email,
        calendar_id=payload.calendar_id,
    )
    status_data = await service.get_google_calendar_status(db, workspace_id=auth.workspace_id)
    return GoogleCalendarStatusOut(**status_data)


@router.post("/google-calendar/disconnect")
async def disconnect_google_calendar_endpoint(
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> dict:
    await service.disconnect_google_calendar(db, workspace_id=auth.workspace_id)
    return {"status": "disconnected"}


@router.get("/google-calendar/status", response_model=GoogleCalendarStatusOut)
async def get_google_calendar_status_endpoint(
    auth: AuthContext = Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> GoogleCalendarStatusOut:
    status_data = await service.get_google_calendar_status(db, workspace_id=auth.workspace_id)
    return GoogleCalendarStatusOut(**status_data)
