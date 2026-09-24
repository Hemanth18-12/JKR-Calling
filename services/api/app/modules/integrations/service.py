"""Generic outbound webhooks — **Medium** tier (docs/DECISIONS/0007-scope-for-this-pass.md):
a real, working delivery path (register an endpoint, SSRF-guard the URL the
same way knowledge-ingestion does, HMAC-sign every payload, record a
`WebhookDelivery` row per attempt) triggered for real on call completion.
OAuth-based integrations (Google Calendar/Sheets, Meta Lead Ads, WhatsApp,
n8n) are catalog entries only — inert until real OAuth credentials exist,
same posture as `docs/DECISIONS/0006-auth.md`'s Google-login stub. "Mock
CRM" isn't a separate connectable integration here: `create_crm_lead`/
`update_crm_stage` (services/api/app/modules/tools) already are the mock CRM
path, so this module doesn't duplicate it as a second concept.

Actual delivery (`deliver_webhook`) lives in `jkr_db.webhook_engine`, not
here — intelligence-worker fires the `call.completed` event from its own
process and needs the identical signing/delivery logic, not a second
implementation. Registration/listing stay here since they're plain CRUD
behind this service's own permission checks.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from fastapi import HTTPException, status
from jkr_db.crypto import encrypt_secret
from jkr_db.enums import IntegrationStatus, IntegrationType
from jkr_db.integrations.google_calendar import (
    exchange_code_for_tokens,
    get_google_auth_url,
    save_google_calendar_connection,
)
from jkr_db.models.integrations import Integration, IntegrationCredential, WebhookDelivery, WebhookEndpoint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.security import assert_public_host

INTEGRATION_CATALOG: list[dict] = [
    {"type": "webhook", "label": "Outgoing webhooks", "requires_oauth": False},
    {"type": "crm", "label": "CRM (via the create_crm_lead/update_crm_stage tools)", "requires_oauth": False},
    {"type": "google_calendar", "label": "Google Calendar", "requires_oauth": True},
    {"type": "google_sheets", "label": "Google Sheets", "requires_oauth": True},
    {"type": "meta_lead_ads", "label": "Meta Lead Ads", "requires_oauth": True},
    {"type": "whatsapp", "label": "WhatsApp Business", "requires_oauth": True},
    {"type": "n8n", "label": "n8n", "requires_oauth": True},
]


async def catalog(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    active_result = await db.execute(
        select(WebhookEndpoint.id).where(WebhookEndpoint.workspace_id == workspace_id, WebhookEndpoint.is_active.is_(True)).limit(1)
    )
    has_active_webhook = active_result.scalar_one_or_none() is not None

    integrations_res = await db.execute(
        select(Integration.type).where(
            Integration.workspace_id == workspace_id,
            Integration.status == IntegrationStatus.CONNECTED,
        )
    )
    connected_types = {r[0] for r in integrations_res.all()}

    items = []
    for item in INTEGRATION_CATALOG:
        is_conn = False
        if item["type"] == "webhook" and has_active_webhook:
            is_conn = True
        elif item["type"] in connected_types:
            is_conn = True

        items.append({
            "type": item["type"],
            "label": item["label"],
            "requires_oauth": item["requires_oauth"],
            "status": "connected" if is_conn else "not_connected",
        })
    return items


async def create_webhook_endpoint(
    db: AsyncSession, *, workspace_id: uuid.UUID, settings: Settings, url: str, secret: str, event_types: list[str],
) -> WebhookEndpoint:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only http/https URLs are supported")
    if not parsed.hostname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid URL")
    assert_public_host(parsed.hostname, url)

    endpoint = WebhookEndpoint(
        workspace_id=workspace_id, url=url, secret_encrypted=encrypt_secret(secret, settings.credentials_encryption_key),
        event_types=event_types, is_active=True,
    )
    db.add(endpoint)
    await db.flush()
    return endpoint


async def list_webhook_endpoints(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[WebhookEndpoint]:
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == workspace_id).order_by(WebhookEndpoint.created_at.desc()))
    return list(result.scalars().all())


async def deactivate_webhook_endpoint(db: AsyncSession, *, workspace_id: uuid.UUID, endpoint_id: uuid.UUID) -> WebhookEndpoint:
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id, WebhookEndpoint.workspace_id == workspace_id))
    endpoint = result.scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook endpoint not found")
    endpoint.is_active = False
    await db.flush()
    return endpoint


async def list_deliveries(db: AsyncSession, *, workspace_id: uuid.UUID, endpoint_id: uuid.UUID, limit: int = 50) -> list[WebhookDelivery]:
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.workspace_id == workspace_id, WebhookDelivery.webhook_endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# --- Google Calendar Operations ---

def get_google_calendar_auth_url(workspace_id: uuid.UUID, settings: Settings) -> str:
    client_id = settings.google_client_id or "demo-google-client-id.apps.googleusercontent.com"
    redirect_uri = settings.google_oauth_redirect_uri or f"{settings.app_base_url}/api/v1/integrations/google-calendar/callback"
    state = f"ws_{workspace_id}"
    return get_google_auth_url(client_id=client_id, redirect_uri=redirect_uri, state=state)


async def connect_google_calendar(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    settings: Settings,
    code: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    email: str | None = None,
    calendar_id: str = "primary",
) -> Integration:
    if code:
        tokens = await exchange_code_for_tokens(
            code=code,
            redirect_uri=settings.google_oauth_redirect_uri,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
    elif not access_token:
        # Fallback to demo/mock token for testing
        access_token = f"mock_token_{uuid.uuid4().hex[:12]}"
        refresh_token = f"mock_refresh_{uuid.uuid4().hex[:12]}"
        expires_in = 3600
    else:
        expires_in = 3600

    integration = await save_google_calendar_connection(
        db,
        workspace_id=workspace_id,
        encryption_key=settings.credentials_encryption_key,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in,
        calendar_id=calendar_id,
        email=email or "dentist@aahadental.in",
    )
    return integration


async def disconnect_google_calendar(db: AsyncSession, *, workspace_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_CALENDAR,
        )
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.status = IntegrationStatus.NOT_CONNECTED
        await db.flush()


async def get_google_calendar_status(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_CALENDAR,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration or integration.status != IntegrationStatus.CONNECTED:
        return {"is_connected": False}

    cfg = integration.config or {}
    return {
        "is_connected": True,
        "display_name": integration.display_name,
        "calendar_id": cfg.get("calendar_id", "primary"),
        "email": cfg.get("email"),
        "last_synced_at": integration.last_synced_at,
    }
