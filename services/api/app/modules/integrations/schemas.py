from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WebhookEndpointCreate(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    secret: str = Field(min_length=8, max_length=200)
    event_types: list[str] = Field(default_factory=lambda: ["call.completed"])


class WebhookEndpointOut(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime


class WebhookDeliveryOut(BaseModel):
    id: uuid.UUID
    event_type: str
    status: str
    attempt_count: int
    response_status: int | None
    last_attempted_at: datetime | None
    created_at: datetime


class IntegrationCatalogItem(BaseModel):
    type: str
    label: str
    description: str | None = None
    status: str
    requires_oauth: bool
    connected_account: str | None = None
    external_url: str | None = None
    last_synced_at: datetime | None = None


class OAuthUrlResponse(BaseModel):
    auth_url: str | None = None
    configured: bool
    message: str | None = None


class GoogleCalendarConnectRequest(BaseModel):
    code: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = None
    calendar_id: str = "primary"


class GoogleCalendarStatusOut(BaseModel):
    is_connected: bool
    display_name: str | None = None
    calendar_id: str | None = None
    email: str | None = None
    external_url: str | None = None
    last_synced_at: datetime | None = None


class N8nVerifyRequest(BaseModel):
    instance_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = None
    webhook_url: str | None = None


class MetaVerifyRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=200)
    access_token: str = Field(min_length=10, max_length=1000)


class CrmVerifyRequest(BaseModel):
    webhook_url: str = Field(min_length=1, max_length=1000)
    crm_name: str = Field(default="Custom CRM", max_length=100)
