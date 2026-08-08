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
from jkr_db.models.integrations import WebhookDelivery, WebhookEndpoint
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
    return [
        {
            "type": item["type"], "label": item["label"], "requires_oauth": item["requires_oauth"],
            "status": "connected" if item["type"] == "webhook" and has_active_webhook else "not_connected",
        }
        for item in INTEGRATION_CATALOG
    ]


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
