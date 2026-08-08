from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel


class AuditLogEntryOut(BaseModel):
    id: uuid.UUID
    actor_name: str | None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    created_at: datetime


class ConsentPurposeCount(BaseModel):
    purpose: str
    count: int


class ComplianceOverview(BaseModel):
    calling_window_start: time
    calling_window_end: time
    timezone: str
    total_contacts: int
    suppressed_contacts: int
    consent_purpose_breakdown: list[ConsentPurposeCount]
