from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=6, max_length=32, description="Any format — normalized to E.164 server-side")
    email: str | None = None
    preferred_language: str | None = None
    location: str | None = None
    lead_source: str | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_masked: str
    email: str | None
    preferred_language: str | None
    location: str | None
    lead_source: str | None
    consent_status: str
    is_suppressed: bool
    conversion_status: str | None
    last_call_at: datetime | None
    created_at: datetime


class ContactDetail(ContactOut):
    phone_e164: str | None  # only populated when caller has contacts:view_unmasked


class ConsentEventCreate(BaseModel):
    purpose: str = Field(pattern=r"^(marketing|transactional|service|appointment_reminder)$")
    source: str = Field(pattern=r"^(signed_form|verbal_recorded|checkbox|whatsapp_opt_in|api)$")
    campaign_category: str | None = None
    evidence_url: str | None = None
    expires_at: datetime | None = None


class ConsentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    purpose: str
    source: str
    campaign_category: str | None
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class SuppressionCreate(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    reason: str = Field(pattern=r"^(customer_opt_out|wrong_number|legal_suppression|workspace_block|complaint|repeated_failure|manual_block)$")
    note: str | None = None


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    phone_masked: str
    reason: str
    note: str | None
    created_at: datetime


class SegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    contact_ids: list[uuid.UUID] = Field(default_factory=list)


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    member_count: int
