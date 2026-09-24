"""Google Calendar Integration for JKR Calling platform.
Implements Google OAuth 2.0 authorization, credential storage, token refresh,
and Google Calendar event creation when appointments are booked.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.crypto import decrypt_secret, encrypt_secret
from jkr_db.enums import IntegrationStatus, IntegrationType
from jkr_db.models.integrations import Integration, IntegrationCredential

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]


def get_google_auth_url(
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Generate Google OAuth 2.0 authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(GOOGLE_TOKEN_URL, data=data)
        if res.status_code != 200:
            raise RuntimeError(f"Google token exchange failed ({res.status_code}): {res.text}")
        return res.json()


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Obtain a new access token using the refresh token."""
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(GOOGLE_TOKEN_URL, data=data)
        if res.status_code != 200:
            raise RuntimeError(f"Google token refresh failed ({res.status_code}): {res.text}")
        return res.json()


async def save_google_calendar_connection(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    encryption_key: str,
    access_token: str,
    refresh_token: str | None,
    expires_in_seconds: int = 3600,
    calendar_id: str = "primary",
    email: str | None = None,
) -> Integration:
    """Save or update Google Calendar integration and encrypted credentials."""
    # Find or create Integration record
    result = await db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_CALENDAR,
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        integration = Integration(
            workspace_id=workspace_id,
            type=IntegrationType.GOOGLE_CALENDAR,
            display_name=f"Google Calendar ({email or 'Connected'})",
            status=IntegrationStatus.CONNECTED,
            config={"calendar_id": calendar_id, "email": email or ""},
            last_synced_at=datetime.now(UTC),
        )
        db.add(integration)
        await db.flush()
    else:
        integration.status = IntegrationStatus.CONNECTED
        integration.display_name = f"Google Calendar ({email or 'Connected'})"
        integration.config = {"calendar_id": calendar_id, "email": email or ""}
        integration.last_synced_at = datetime.now(UTC)
        integration.last_error = None
        await db.flush()

    # Save encrypted credentials
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


async def get_active_google_calendar_token(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    encryption_key: str,
    client_id: str = "",
    client_secret: str = "",
) -> tuple[str | None, str]:
    """Retrieve valid access token and calendar_id for workspace."""
    result = await db.execute(
        select(Integration, IntegrationCredential)
        .join(IntegrationCredential, IntegrationCredential.integration_id == Integration.id)
        .where(
            Integration.workspace_id == workspace_id,
            Integration.type == IntegrationType.GOOGLE_CALENDAR,
            Integration.status == IntegrationStatus.CONNECTED,
        )
    )
    row = result.first()
    if not row:
        return None, "primary"

    integration, cred = row
    calendar_id = integration.config.get("calendar_id", "primary")

    decrypted = decrypt_secret(cred.encrypted_secret, encryption_key)
    parts = decrypted.split(":::", 1)
    access_token = parts[0]
    refresh_token = parts[1] if len(parts) > 1 else ""

    # Check if expired and refreshable
    if cred.expires_at and cred.expires_at < datetime.now(UTC) and refresh_token and client_id and client_secret:
        try:
            refreshed = await refresh_access_token(refresh_token, client_id, client_secret)
            access_token = refreshed["access_token"]
            expires_in = refreshed.get("expires_in", 3600)
            cred.encrypted_secret = encrypt_secret(f"{access_token}:::{refresh_token}", encryption_key)
            cred.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            await db.flush()
        except Exception as exc:
            logger.warning("Token refresh failed: %s", exc)

    return access_token, calendar_id


async def create_google_calendar_event(
    access_token: str,
    *,
    calendar_id: str = "primary",
    summary: str,
    description: str,
    start_time: datetime,
    duration_minutes: int = 30,
    location: str | None = None,
    attendee_email: str | None = None,
) -> dict[str, Any]:
    """Create real Google Calendar event via Google REST API.
    If access_token is a mock/test token, returns synthetic valid Google event response.
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }
    if location:
        event_body["location"] = location
    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]

    # If simulated / mock token
    if access_token.startswith("mock_") or access_token.startswith("simulated_") or access_token.startswith("dev_"):
        event_id = f"gcal_{uuid.uuid4().hex[:16]}"
        return {
            "id": event_id,
            "status": "confirmed",
            "htmlLink": f"https://www.google.com/calendar/event?eid={event_id}",
            "summary": summary,
            "description": description,
            "location": location,
            "start": event_body["start"],
            "end": event_body["end"],
            "is_simulated": True,
        }

    url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/{calendar_id}/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(url, json=event_body, headers=headers)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Google Calendar event creation failed ({res.status_code}): {res.text}")
        data = res.json()
        data["is_simulated"] = False
        return data
