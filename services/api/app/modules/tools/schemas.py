from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ToolDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    required_permission: str
    timeout_seconds: int
    confirmation_required: bool
    is_enabled: bool
    has_real_side_effect: bool


class ToolDefinitionUpdate(BaseModel):
    is_enabled: bool


class AgentToolOut(BaseModel):
    tool_definition_id: uuid.UUID
    name: str
    description: str
    enabled: bool


class AgentToolUpdate(BaseModel):
    enabled: bool


class ToolExecutionOut(BaseModel):
    id: uuid.UUID
    tool_definition_id: uuid.UUID
    tool_name: str
    status: str
    input: dict
    output: dict | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
