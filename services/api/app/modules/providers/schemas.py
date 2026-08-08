from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    name: str
    display_name: str
    is_default: bool
    priority: int
    status: str
    region: str | None
    created_at: datetime


class ProviderAccountCreate(BaseModel):
    kind: str = Field(pattern=r"^(telephony|stt|llm|tts)$")
    name: str
    display_name: str
    is_default: bool = False
    priority: int = 100
    region: str | None = None
    config: dict = Field(default_factory=dict)
    secret: str | None = None


class ProviderAccountUpdate(BaseModel):
    display_name: str | None = None
    is_default: bool | None = None
    priority: int | None = None
    config: dict | None = None
    secret: str | None = None


class ProviderCatalogEntry(BaseModel):
    kind: str
    name: str
    label: str
    requires_credentials: bool
    configured_env_vars: list[str]


class ProviderHealthOut(BaseModel):
    provider_account_id: uuid.UUID
    status: str
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    error_rate: float | None
    checked_at: datetime
