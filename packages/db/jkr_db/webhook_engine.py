"""Outbound webhook delivery — shared by services/api (registration lives
there) and intelligence-worker (fires `call.completed` at the end of the
post-call pipeline). Lives in packages/db for the same reason
`safety_gate.py`/`tools_engine.py` do: two independently-deployed services
need the exact same delivery/signing logic, not two implementations that can
drift. See docs/IMPLEMENTATION_CHECKLIST.md Phase 9.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.crypto import decrypt_secret
from jkr_db.models.integrations import WebhookDelivery, WebhookEndpoint


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def deliver_webhook(
    db: AsyncSession, *, encryption_key: str, workspace_id: uuid.UUID, event_type: str, payload: dict
) -> None:
    """Fires every active endpoint subscribed to `event_type`. Best-effort,
    single attempt this pass (no retry queue) — a failed delivery is
    recorded as `failed`, not silently dropped, but isn't automatically
    retried. Must never raise into its caller: a webhook delivery failure
    must not fail the pipeline run that triggered it."""
    endpoints_result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == workspace_id, WebhookEndpoint.is_active.is_(True))
    )
    endpoints = [e for e in endpoints_result.scalars().all() if event_type in e.event_types]
    if not endpoints:
        return

    body_dict = {"event_type": event_type, "payload": payload}
    body = json.dumps(body_dict, default=str).encode("utf-8")

    for endpoint in endpoints:
        secret = decrypt_secret(endpoint.secret_encrypted, encryption_key)
        signature = sign_payload(secret, body)
        delivery = WebhookDelivery(
            workspace_id=workspace_id, webhook_endpoint_id=endpoint.id, event_type=event_type, payload=body_dict,
            status="pending", attempt_count=1, last_attempted_at=datetime.now(UTC),
        )
        db.add(delivery)
        await db.flush()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    endpoint.url, content=body,
                    headers={"Content-Type": "application/json", "X-JKR-Signature": signature, "X-JKR-Event": event_type},
                )
            delivery.response_status = response.status_code
            delivery.status = "delivered" if 200 <= response.status_code < 300 else "failed"
        except httpx.HTTPError:
            delivery.status = "failed"
        await db.flush()
