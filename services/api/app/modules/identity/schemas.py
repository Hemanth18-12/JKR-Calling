from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class WorkspaceMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    role_key: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_platform_super_admin: bool
    created_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[WorkspaceMembershipOut]
    active_workspace_id: uuid.UUID | None
    google_oauth_enabled: bool
