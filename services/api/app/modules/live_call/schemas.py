from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LiveTestCallCreate(BaseModel):
    agent_id: uuid.UUID
    to_number: str = Field(min_length=6, max_length=20)
    customer_name: str | None = Field(default=None, max_length=100)


class LiveTestCallStarted(BaseModel):
    call_id: uuid.UUID
    call_sid: str
    status: str
