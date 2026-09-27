"""External Integrations Service for JKR Calling platform.
Manages verified external connections for Google Calendar, Google Sheets, Meta Lead Ads,
WhatsApp Business, n8n, CRM, and Outgoing Webhooks.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, status
from jkr_db.crypto import encrypt_secret
from jkr_db.enums import IntegrationStatus, IntegrationType
from jkr_db.integrations.google_calendar import (
    exchange_code_for_tokens,
    get_google_auth_url as _gen_google_auth_url,
    save_google_calendar_connection,
)
from jkr_db.integrations.google_sheets import save_google_sheets_connection
from jkr_db.models.integrations import Integration, IntegrationCredential, WebhookDelivery, WebhookEndpoint
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.security import assert_public_host

logger = logging.getLogger(__name__)

INTEGRATION_METADATA: dict[str, dict] = {
    "webhook": {
        "label": "Outgoing Webhooks",
        "description": "Real-time HMAC-signed webhooks triggered on call completion and CRM lifecycle events.",
        "requires_oauth": False,
        "default_url": None,
    },
    "crm": {
        "label": "CRM Lead Pipeline",
        "description": "Bidirectional lead qualification and pipeline sync (Salesforce, HubSpot, Zoho, College ERPs).",
        "requires_oauth": False,
        "default_url": None,
    },
    "google_calendar": {
        "label": "Google Calendar",
        "description": "Syncs booked appointments directly to your Google Calendar with real calendar event links.",
        "requires_oauth": True,
        "default_url": "https://calendar.google.com/calendar/r",
    },
    "google_sheets": {
        "label": "Google Sheets",
        "description": "Appends confirmed appointments and qualified caller leads automatically to your spreadsheet.",
        "requires_oauth": True,
        "default_url": "https://docs.google.com/spreadsheets/u/0/",
    },
    "meta_lead_ads": {
        "label": "Meta Lead Ads",
        "description": "Captures inbound leads from Facebook and Instagram Ads and triggers instant AI outreach calls.",
        "requires_oauth": True,
        "default_url": "https://adsmanager.facebook.com/",
    },
    "whatsapp": {
        "label": "WhatsApp Business",
        "description": "Sends instant appointment confirmations and brochures directly to callers over WhatsApp.",
        "requires_oauth": True,
        "default_url": "https://business.facebook.com/wa/manage/",
    },
    "n8n": {
        "label": "n8n Workflow Automation",
        "description": "Connects your self-hosted or cloud n8n workflows for custom lead processing pipelines.",
        "requires_oauth": False,
        "default_url": "https://n8n.io",
    },
}


async def catalog(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    """Returns catalog of integrations with STRICT, verified connection status.
    Only shows 'connected' when a real, verified external connection exists with stored credentials.
    """
    # 1. Outgoing webhooks check
    active_webhook_res = await db.execute(
        select(WebhookEndpoint.id, WebhookEndpoint.url)
        .where(WebhookEndpoint.workspace_id == workspace_id, WebhookEndpoint.is_active.is_(True))
    )
    active_webhooks = active_webhook_res.all()
    has_active_webhook = len(active_webhooks) > 0

    # 2. Query integrations with credentials
    integrations_res = await db.execute(
        select(Integration, IntegrationCredential)
        .outerjoin(IntegrationCredential, IntegrationCredential.integration_id == Integration.id)
        .where(Integration.workspace_id == workspace_id)
    )
    int_by_type = {}
    for integration, cred in integrations_res.all():
        int_by_type[integration.type] = (integration, cred)

    items = []
    for itype, meta in INTEGRATION_METADATA.items():
        is_conn = False
        connected_account = None
        external_url = meta.get("default_url")
        last_synced_at = None

        if itype == "webhook":
            if has_active_webhook:
                is_conn = True
                connected_account = f"{len(active_webhooks)} active endpoint(s)"
                first_url = active_webhooks[0][1]
                external_url = first_url if first_url.startswith("http") else None
        elif itype in int_by_type:
            integration, cred = int_by_type[itype]
            cfg = integration.config or {}
            last_synced_at = integration.last_synced_at

            if itype in ("google_calendar", "google_sheets"):
                # Must have status CONNECTED AND a non-empty credential stored
                if integration.status == IntegrationStatus.CONNECTED and cred and cred.encrypted_secret:
                    is_conn = True
                    email = cfg.get("email")
                    connected_account = email or "Google Account"
                    if itype == "google_calendar":
                        external_url = (
                            f"https://calendar.google.com/calendar/u/0/r?authuser={email}"
                            if email
                            else "https://calendar.google.com/calendar/r"
                        )
                    else:
                        external_url = (
                            f"https://docs.google.com/spreadsheets/u/0/?authuser={email}"
                            if email
                            else "https://docs.google.com/spreadsheets/u/0/"
                        )
            elif itype == "meta_lead_ads":
                if integration.status == IntegrationStatus.CONNECTED and (cred or cfg.get("page_id")):
                    is_conn = True
                    connected_account = f"Page: {cfg.get('page_id')}"
                    external_url = "https://adsmanager.facebook.com/"
            elif itype == "whatsapp":
                if integration.status == IntegrationStatus.CONNECTED and cfg.get("status") == "active":
                    is_conn = True
                    connected_account = cfg.get("phone_number") or "WhatsApp Business"
                    external_url = "https://business.facebook.com/wa/manage/"
            elif itype == "n8n":
                if integration.status == IntegrationStatus.CONNECTED and cfg.get("instance_url"):
                    is_conn = True
                    connected_account = cfg.get("instance_url")
                    external_url = cfg.get("instance_url")
            elif itype == "crm":
                if integration.status == IntegrationStatus.CONNECTED and cfg.get("webhook_url"):
                    is_conn = True
                    connected_account = cfg.get("crm_name") or cfg.get("webhook_url")
                    external_url = cfg.get("webhook_url")

        items.append({
            "type": itype,
            "label": meta["label"],
            "description": meta["description"],
            "requires_oauth": meta["requires_oauth"],
            "status": "connected" if is_conn else "not_connected",
            "connected_account": connected_account,
            "external_url": external_url,
            "last_synced_at": last_synced_at,
        })

    return items


# --- Google OAuth Flow (Calendar & Sheets) ---

def get_google_oauth_url(
    workspace_id: uuid.UUID,
    integration_type: str,
    settings: Settings,
) -> tuple[str | None, bool, str | None]:
    """Generates real Google OAuth consent URL. Returns (auth_url, is_configured, message)."""
    client_id = settings.google_client_id or os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return (
            None,
            False,
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment to connect.",
        )

    redirect_uri = f"{settings.api_base_url}/api/v1/integrations/google/callback"
    state_payload = {"ws": str(workspace_id), "type": integration_type}
    state = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode()

    scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
    if integration_type == "google_calendar":
        scopes.append("https://www.googleapis.com/auth/calendar.events")
    elif integration_type == "google_sheets":
        scopes.append("https://www.googleapis.com/auth/spreadsheets")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return (url, True, None)


async def exchange_google_code_and_connect(
    db: AsyncSession,
    *,
    code: str,
    state: str,
    settings: Settings,
) -> tuple[str, str]:
    """Exchanges Google authorization code for real access/refresh tokens and stores connection."""
    try:
        raw_state = base64.urlsafe_b64decode(state).decode()
        state_data = json.loads(raw_state)
        workspace_id = uuid.UUID(state_data["ws"])
        integration_type = state_data.get("type", "google_calendar")
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid OAuth state parameter: {exc}")

    redirect_uri = f"{settings.api_base_url}/api/v1/integrations/google/callback"
    client_id = settings.google_client_id or os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = settings.google_client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")

    tokens = await exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        client_id=client_id,
        client_secret=client_secret,
    )
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Get caller's Google email
    email = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            ui_res = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if ui_res.status_code == 200:
                email = ui_res.json().get("email")
    except Exception as exc:
        logger.warning("Could not fetch userinfo from Google: %s", exc)

    if integration_type == "google_calendar":
        await save_google_calendar_connection(
            db,
            workspace_id=workspace_id,
            encryption_key=settings.credentials_encryption_key,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=expires_in,
            email=email,
        )
    elif integration_type == "google_sheets":
        await save_google_sheets_connection(
            db,
            workspace_id=workspace_id,
            encryption_key=settings.credentials_encryption_key,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=expires_in,
            email=email,
        )

    return integration_type, email or "Google Account"


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
    """Explicitly connects Google Calendar with provided token or code. Never falls back to mock."""
    if code:
        client_id = settings.google_client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = settings.google_client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
        redirect_uri = f"{settings.api_base_url}/api/v1/integrations/google/callback"
        tokens = await exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
    elif access_token:
        expires_in = 3600
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "An authorization code or valid access token is required to connect Google Calendar.",
        )

    return await save_google_calendar_connection(
        db,
        workspace_id=workspace_id,
        encryption_key=settings.credentials_encryption_key,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in,
        calendar_id=calendar_id,
        email=email,
    )


# --- n8n Verification and Connection ---

async def verify_and_connect_n8n(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    instance_url: str,
    api_key: str | None = None,
    webhook_url: str | None = None,
) -> dict:
    """Verifies n8n instance is reachable by making a real HTTP request.
    Only marks status=connected if verified successfully.
    """
    clean_url = instance_url.strip().rstrip("/")
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "instance_url must start with http:// or https://")

    # Send verification ping to n8n instance
    headers = {}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            test_target = f"{clean_url}/healthz"
            res = await client.get(test_target, headers=headers)
            if res.status_code >= 400:
                # Try hitting root if /healthz not found
                res = await client.get(clean_url, headers=headers)
                if res.status_code >= 500:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"n8n instance responded with error HTTP {res.status_code} at {clean_url}.",
                    )
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Could not connect to n8n instance at {clean_url}: {exc}",
        )

    # Save to database
    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.type == IntegrationType.N8N)
    )
    integration = result.scalar_one_or_none()
    cfg = {
        "instance_url": clean_url,
        "webhook_url": webhook_url or f"{clean_url}/webhook/jkr-calling",
        "has_api_key": bool(api_key),
    }

    if integration is None:
        integration = Integration(
            workspace_id=workspace_id,
            type=IntegrationType.N8N,
            display_name=f"n8n ({clean_url})",
            status=IntegrationStatus.CONNECTED,
            config=cfg,
            last_synced_at=datetime.now(UTC),
        )
        db.add(integration)
    else:
        integration.status = IntegrationStatus.CONNECTED
        integration.display_name = f"n8n ({clean_url})"
        integration.config = cfg
        integration.last_synced_at = datetime.now(UTC)
        integration.last_error = None

    await db.flush()
    return {"status": "connected", "instance_url": clean_url}


# --- CRM Webhook Verification and Connection ---

async def verify_and_connect_crm(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    webhook_url: str,
    crm_name: str = "CRM",
) -> dict:
    """Verifies CRM webhook endpoint by firing a verification ping. Only marks connected on success."""
    clean_url = webhook_url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "webhook_url must start with http:// or https://")

    # Send test ping
    test_body = {
        "event": "verification.ping",
        "timestamp": datetime.now(UTC).isoformat(),
        "workspace_id": str(workspace_id),
        "source": "JKR Calling CRM Verification",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.post(clean_url, json=test_body)
            if res.status_code >= 400:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"CRM endpoint rejected test ping with HTTP {res.status_code}.",
                )
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Could not reach CRM webhook URL: {exc}",
        )

    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.type == IntegrationType.CRM)
    )
    integration = result.scalar_one_or_none()
    cfg = {"webhook_url": clean_url, "crm_name": crm_name, "status": "active"}

    if integration is None:
        integration = Integration(
            workspace_id=workspace_id,
            type=IntegrationType.CRM,
            display_name=f"{crm_name} ({clean_url[:40]}...)",
            status=IntegrationStatus.CONNECTED,
            config=cfg,
            last_synced_at=datetime.now(UTC),
        )
        db.add(integration)
    else:
        integration.status = IntegrationStatus.CONNECTED
        integration.display_name = f"{crm_name} ({clean_url[:40]}...)"
        integration.config = cfg
        integration.last_synced_at = datetime.now(UTC)
        integration.last_error = None

    await db.flush()
    return {"status": "connected", "crm_name": crm_name, "webhook_url": clean_url}


# --- Disconnect Integration ---

async def disconnect_integration(db: AsyncSession, *, workspace_id: uuid.UUID, integration_type: str) -> None:
    """Disconnects integration and removes any stored credentials."""
    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.type == integration_type)
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.status = IntegrationStatus.NOT_CONNECTED
        integration.last_synced_at = None
        # Remove credentials
        await db.execute(
            delete(IntegrationCredential).where(IntegrationCredential.integration_id == integration.id)
        )
        await db.flush()


# --- Webhook Management ---

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
        workspace_id=workspace_id,
        url=url,
        secret_encrypted=encrypt_secret(secret, settings.credentials_encryption_key),
        event_types=event_types,
        is_active=True,
    )
    db.add(endpoint)
    await db.flush()
    return endpoint


async def list_webhook_endpoints(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[WebhookEndpoint]:
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.workspace_id == workspace_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return list(result.scalars().all())


async def deactivate_webhook_endpoint(
    db: AsyncSession, *, workspace_id: uuid.UUID, endpoint_id: uuid.UUID
) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.workspace_id == workspace_id
        )
    )
    endpoint = result.scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook endpoint not found")
    endpoint.is_active = False
    await db.flush()
    return endpoint


async def list_deliveries(
    db: AsyncSession, *, workspace_id: uuid.UUID, endpoint_id: uuid.UUID, limit: int = 50
) -> list[WebhookDelivery]:
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.workspace_id == workspace_id, WebhookDelivery.webhook_endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
