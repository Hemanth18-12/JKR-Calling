from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FollowUpTaskOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    call_session_id: uuid.UUID | None
    channel: str
    status: str
    scheduled_for: datetime | None
    payload: dict
    completed_at: datetime | None
    created_at: datetime


class HumanHandoffOut(BaseModel):
    id: uuid.UUID
    call_session_id: uuid.UUID
    contact_name: str | None
    reason: str
    status: str
    packet: dict
    assigned_to_user_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class AppointmentOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None = None
    contact_name: str | None = None
    call_session_id: uuid.UUID | None = None
    scheduled_for: datetime
    duration_minutes: int = 30
    status: str
    location: str | None = None
    notes: str | None = None
    created_at: datetime


class AppointmentCreate(BaseModel):
    contact_id: uuid.UUID | None = None
    customer_name: str | None = None
    phone: str | None = None
    scheduled_for: datetime
    duration_minutes: int = 30
    location: str | None = None
    notes: str | None = None

