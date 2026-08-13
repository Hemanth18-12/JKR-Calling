from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TestCallCreate(BaseModel):
    agent_id: uuid.UUID
    contact_name: str | None = None


class TurnInfo(BaseModel):
    turn_ref: str
    text: str


class TestCallStarted(BaseModel):
    call_id: uuid.UUID
    status: str
    language: str
    greeting: str
    conversation_state: dict


class UserTurnCreate(BaseModel):
    text: str


class UserTurnResponse(BaseModel):
    user_turn: TurnInfo
    interruption_classification: str
    stop_latency_ms: int | None
    agent_turn: TurnInfo | None
    conversation_state: dict
    call_status: str


class EndCallResponse(BaseModel):
    call_id: uuid.UUID
    status: str
    outcome_category: str
    lead_score: str


class CallTurnOut(BaseModel):
    turn_ref: str
    sequence_index: int
    speaker: str
    text: str
    language: str | None
    confidence: float | None
    is_interrupted: bool
    started_at: datetime


class CallLatencyMetricOut(BaseModel):
    stage: str
    duration_ms: int
    is_simulated: bool
    recorded_at: datetime


class InterruptionEventOut(BaseModel):
    classification: str
    stop_latency_ms: int | None
    occurred_at: datetime


class CallOutcomeOut(BaseModel):
    category: str
    lead_score: str | None
    score_reasons: list[str]
    objective_status: str | None
    notes: str | None


class CallListItem(BaseModel):
    call_id: uuid.UUID
    status: str
    direction: str
    contact_name: str | None
    outcome_category: str | None
    started_at: datetime | None
    duration_seconds: int | None
    is_mock: bool
    campaign_id: uuid.UUID | None = None


class CallDetail(BaseModel):
    call_id: uuid.UUID
    status: str
    direction: str
    language: str | None
    agent_id: uuid.UUID
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    conversation_state: dict
    turns: list[CallTurnOut]
    interruptions: list[InterruptionEventOut]
    latency_metrics: list[CallLatencyMetricOut]
    outcome: CallOutcomeOut | None
