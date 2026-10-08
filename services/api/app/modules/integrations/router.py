from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import platform_db
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    CrmVerifyRequest,
    GoogleCalendarConnectRequest,
    GoogleCalendarStatusOut,
    GoogleSheetsConnectRequest,
    IntegrationCatalogItem,
    IntegrationTestRequest,
    IntegrationTestResult,
    MetaConnectRequest,
    MetaVerifyRequest,
    N8nVerifyRequest,
    OAuthUrlResponse,
    WebhookDeliveryOut,
    WebhookEndpointCreate,
    WebhookEndpointOut,
    WhatsAppConnectRequest,
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
        db,
        workspace_id=auth.workspace_id,
        settings=settings,
        url=payload.url,
        secret=payload.secret,
        event_types=payload.event_types,
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


# --- Google OAuth Endpoints ---

@router.get("/google/auth-url", response_model=OAuthUrlResponse)
async def get_google_oauth_url_endpoint(
    integration_type: str = Query(default="google_calendar"),
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> OAuthUrlResponse:
    auth_url, is_configured, message = service.get_google_oauth_url(
        auth.workspace_id, integration_type=integration_type, settings=settings
    )
    return OAuthUrlResponse(auth_url=auth_url, configured=is_configured, message=message)


@router.get("/google/callback")
async def google_oauth_callback_endpoint(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
):
    integration_type, email = await service.exchange_google_code_and_connect(
        db, code=code, state=state, settings=settings
    )
    redirect_target = f"{settings.app_base_url}/app/integrations?connected={integration_type}&email={email}"
    return RedirectResponse(url=redirect_target)


# Legacy endpoints for compatibility
@router.get("/google-calendar/auth-url")
async def get_google_calendar_auth_url_endpoint(
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    auth_url, is_configured, message = service.get_google_oauth_url(
        auth.workspace_id, integration_type="google_calendar", settings=settings
    )
    return {"auth_url": auth_url, "configured": is_configured, "message": message}


@router.post("/google-calendar/connect", response_model=GoogleCalendarStatusOut)
async def connect_google_calendar_endpoint(
    payload: GoogleCalendarConnectRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> GoogleCalendarStatusOut:
    integration = await service.connect_google_calendar(
        db,
        workspace_id=auth.workspace_id,
        settings=settings,
        code=payload.code,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        email=payload.email,
        calendar_id=payload.calendar_id,
    )
    email = (integration.config or {}).get("email")
    ext_url = f"https://calendar.google.com/calendar/u/0/r?authuser={email}" if email else "https://calendar.google.com/calendar/r"
    return GoogleCalendarStatusOut(
        is_connected=True,
        display_name=integration.display_name,
        calendar_id=(integration.config or {}).get("calendar_id", "primary"),
        email=email,
        external_url=ext_url,
        last_synced_at=integration.last_synced_at,
    )


@router.get("/google-calendar/status", response_model=GoogleCalendarStatusOut)
async def get_google_calendar_status_endpoint(
    auth: AuthContext = Depends(require_permission("integrations:view")),
    db: AsyncSession = Depends(workspace_db_for("integrations:view")),
) -> GoogleCalendarStatusOut:
    cat = await service.catalog(db, workspace_id=auth.workspace_id)
    gcal = next((item for item in cat if item["type"] == "google_calendar"), None)
    if not gcal or gcal["status"] != "connected":
        return GoogleCalendarStatusOut(is_connected=False)
    return GoogleCalendarStatusOut(
        is_connected=True,
        display_name=f"Google Calendar ({gcal['connected_account']})",
        email=gcal["connected_account"],
        external_url=gcal["external_url"],
        last_synced_at=gcal["last_synced_at"],
    )


@router.post("/google-sheets/connect")
async def connect_google_sheets_endpoint(
    payload: GoogleSheetsConnectRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    integration = await service.connect_google_sheets(
        db,
        workspace_id=auth.workspace_id,
        settings=settings,
        code=payload.code,
        access_token=payload.access_token,
        email=payload.email,
        spreadsheet_id=payload.spreadsheet_id,
        sheet_name=payload.sheet_name or "Appointments & Leads",
    )
    email = (integration.config or {}).get("email")
    ext_url = f"https://docs.google.com/spreadsheets/u/0/?authuser={email}" if email else "https://docs.google.com/spreadsheets/u/0/"
    return {
        "is_connected": True,
        "display_name": integration.display_name,
        "email": email,
        "external_url": ext_url,
        "spreadsheet_id": (integration.config or {}).get("spreadsheet_id"),
        "last_synced_at": integration.last_synced_at,
    }


@router.post("/meta/connect")
async def connect_meta_endpoint(
    payload: MetaConnectRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await service.connect_meta_lead_ads(
        db,
        workspace_id=auth.workspace_id,
        page_id=payload.page_id,
        page_name=payload.page_name,
        access_token=payload.access_token,
        settings=settings,
    )


@router.post("/whatsapp/connect")
async def connect_whatsapp_endpoint(
    payload: WhatsAppConnectRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await service.connect_whatsapp_business(
        db,
        workspace_id=auth.workspace_id,
        phone_number=payload.phone_number,
        waba_id=payload.waba_id,
        access_token=payload.access_token,
        settings=settings,
    )


# --- Disconnect Any Integration ---

@router.post("/{integration_type}/disconnect")
async def disconnect_integration_endpoint(
    integration_type: str,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> dict:
    await service.disconnect_integration(db, workspace_id=auth.workspace_id, integration_type=integration_type)
    return {"status": "disconnected", "type": integration_type}


# --- Verification Endpoints (n8n & CRM) ---

@router.post("/n8n/verify")
async def verify_n8n_endpoint(
    payload: N8nVerifyRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
) -> dict:
    return await service.verify_and_connect_n8n(
        db,
        workspace_id=auth.workspace_id,
        instance_url=payload.instance_url,
        api_key=payload.api_key,
        webhook_url=payload.webhook_url,
    )


@router.post("/crm/verify")
async def verify_crm_endpoint(
    payload: CrmVerifyRequest,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await service.verify_and_connect_crm(
        db,
        workspace_id=auth.workspace_id,
        crm_type=payload.crm_type,
        hubspot_token=payload.hubspot_token,
        webhook_url=payload.webhook_url,
        crm_name=payload.crm_name,
        settings=settings,
    )


# --- Unified Test Runner for Any Integration ---

@router.post("/{integration_type}/test", response_model=IntegrationTestResult)
async def test_integration_endpoint(
    integration_type: str,
    payload: IntegrationTestRequest | None = None,
    auth: AuthContext = Depends(require_permission("integrations:manage")),
    db: AsyncSession = Depends(workspace_db_for("integrations:manage")),
    settings: Settings = Depends(get_settings),
) -> IntegrationTestResult:
    result = await service.run_integration_test(
        db,
        workspace_id=auth.workspace_id,
        integration_type=integration_type,
        payload=payload.model_dump() if payload else {},
        settings=settings,
    )
    return IntegrationTestResult(**result)
