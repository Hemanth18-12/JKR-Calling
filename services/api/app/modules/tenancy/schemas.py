from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    timezone: str = "Asia/Kolkata"
    default_language: str = "te-en-IN"


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    default_language: str | None = None
    calling_window_start: time | None = None
    calling_window_end: time | None = None
    recording_retention_days: int | None = Field(default=None, ge=1, le=3650)
    transcript_retention_days: int | None = Field(default=None, ge=1, le=3650)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    timezone: str
    default_language: str
    calling_window_start: time
    calling_window_end: time
    identity_verified_at: datetime | None
    recording_retention_days: int
    transcript_retention_days: int
    is_demo: bool
    created_at: datetime


class WorkspaceListItem(WorkspaceOut):
    role_key: str


class MemberInvite(BaseModel):
    email: EmailStr
    role_key: str


class MemberUpdate(BaseModel):
    role_key: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|invited|suspended)$")


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role_key: str
    status: str
    invited_at: datetime | None
    joined_at: datetime | None
