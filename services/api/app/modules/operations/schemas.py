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
    contact_id: uuid.UUID
    contact_name: str
    call_session_id: uuid.UUID | None
    scheduled_for: datetime
    duration_minutes: int
    status: str
    location: str | None
    notes: str | None
    created_at: datetime
