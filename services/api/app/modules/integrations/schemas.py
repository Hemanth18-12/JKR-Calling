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
    status: str
    requires_oauth: bool
