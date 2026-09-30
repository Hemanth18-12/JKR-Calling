"""Google Sheets Integration for JKR Calling platform.
Implements credential storage, token refresh, and appending call/appointment rows
to a Google Spreadsheet using the Google Sheets REST API.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.crypto import decrypt_secret, encrypt_secret
from jkr_db.enums import IntegrationStatus, IntegrationType
from jkr_db.models.integrations import Integration, IntegrationCredential

logger = logging.getLogger(__name__)

GOOGLE_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def save_google_sheets_connection(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    encryption_key: str,
    access_token: str,
    refresh_token: str | None,
    expires_in_seconds: int = 3600,
    email: str | None = None,
    spreadsheet_id: str | None = None,
    sheet_name: str = "Appointments & Leads",
) -> Integration:
    """Save or update Google Sheets integration and encrypted credentials."""
    result = await db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_SHEETS,
        )
    )
    integration = result.scalar_one_or_none()
    display_title = f"Google Sheets ({email or 'Connected'})"
    cfg = {
        "email": email or "",
        "spreadsheet_id": spreadsheet_id or "",
        "sheet_name": sheet_name,
        "auto_sync": True,
    }

    if integration is None:
        integration = Integration(
            workspace_id=workspace_id,
            type=IntegrationType.GOOGLE_SHEETS,
            display_name=display_title,
            status=IntegrationStatus.CONNECTED,
            config=cfg,
            last_synced_at=datetime.now(UTC),
        )
        db.add(integration)
        await db.flush()
    else:
        integration.status = IntegrationStatus.CONNECTED
        integration.display_name = display_title
        integration.config = cfg
        integration.last_synced_at = datetime.now(UTC)
        integration.last_error = None
        await db.flush()

    payload = f"{access_token}:::{refresh_token or ''}"
    encrypted = encrypt_secret(payload, encryption_key)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

    cred_result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.integration_id == integration.id)
    )
    cred = cred_result.scalar_one_or_none()
    if cred is None:
        cred = IntegrationCredential(
            workspace_id=workspace_id,
            integration_id=integration.id,
            encrypted_secret=encrypted,
            expires_at=expires_at,
        )
        db.add(cred)
    else:
        cred.encrypted_secret = encrypted
        cred.expires_at = expires_at

    await db.flush()
    return integration


async def get_active_google_sheets_token(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    encryption_key: str,
    client_id: str = "",
    client_secret: str = "",
) -> tuple[str | None, dict]:
    """Retrieve valid access token and config for workspace Google Sheets."""
    result = await db.execute(
        select(Integration, IntegrationCredential)
        .join(IntegrationCredential, IntegrationCredential.integration_id == Integration.id)
        .where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_SHEETS,
            Integration.status == IntegrationStatus.CONNECTED,
        )
    )
    row = result.first()
    if not row:
        return None, {}

    integration, cred = row
    cfg = integration.config or {}

    decrypted = decrypt_secret(cred.encrypted_secret, encryption_key)
    parts = decrypted.split(":::", 1)
    access_token = parts[0]
    refresh_token = parts[1] if len(parts) > 1 else ""

    # Check if expired and refreshable
    if cred.expires_at and cred.expires_at < datetime.now(UTC) and refresh_token and client_id and client_secret:
        try:
            from jkr_db.integrations.google_calendar import refresh_access_token
            refreshed = await refresh_access_token(refresh_token, client_id, client_secret)
            access_token = refreshed["access_token"]
            expires_in = refreshed.get("expires_in", 3600)
            cred.encrypted_secret = encrypt_secret(f"{access_token}:::{refresh_token}", encryption_key)
            cred.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            await db.flush()
        except Exception as exc:
            logger.warning("Google Sheets token refresh failed: %s", exc)

    return access_token, cfg


async def append_appointment_row(
    access_token: str,
    *,
    spreadsheet_id: str,
    sheet_name: str = "Sheet1",
    values: list[Any],
) -> dict[str, Any]:
    """Appends a row to a Google Spreadsheet via the Google Sheets v4 REST API."""
    if not spreadsheet_id:
        return {"status": "skipped", "reason": "No spreadsheet_id configured"}

    if access_token.startswith("mock_") or access_token.startswith("simulated_") or access_token.startswith("dev_"):
        return {"status": "appended", "is_simulated": True, "values": values}

    url = f"{GOOGLE_SHEETS_API_BASE}/{spreadsheet_id}/values/{sheet_name}!A1:append?valueInputOption=USER_ENTERED"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "range": f"{sheet_name}!A1",
        "majorDimension": "ROWS",
        "values": [values],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(url, json=body, headers=headers)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Google Sheets row append failed ({res.status_code}): {res.text}")
        return res.json()
