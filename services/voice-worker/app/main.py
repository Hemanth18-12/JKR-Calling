from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, status
from jkr_db.session import workspace_scoped_session
from pydantic import BaseModel

from app import conversation_engine, db  # noqa: F401 — db import wires DATABASE_URL into the env
from app.config import get_settings

settings = get_settings()
app = FastAPI(title="JKR AI Calling — voice-worker", version="0.1.0")


async def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """This process is never reached from the public internet — only
    services/api calls it (docs/ARCHITECTURE.md §1: "the browser never talks
    to voice-worker directly"). A shared-secret header is enough to keep it
    that way even if it's accidentally exposed on a shared network."""
    if x_internal_token != settings.internal_service_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid internal service token")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class CreateSessionRequest(BaseModel):
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    contact_name: str | None = None
    campaign_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


@app.post("/sessions", dependencies=[Depends(require_internal_token)])
async def create_session(payload: CreateSessionRequest) -> dict:
    try:
        # Deliberately NOT a Depends()-based generator dependency: workspace_id
        # lives in the POST body here, not a path param FastAPI can inject
        # into a dependency ahead of the handler running. Driving the
        # `@asynccontextmanager`-based session via a bare `async with` (as
        # below) is the correct pattern for that; driving it by manually
        # calling `.aclose()` on the generator (an earlier version of this
        # file did that) throws GeneratorExit into `session.begin()`'s
        # __aexit__, which SQLAlchemy treats as "there was an error" and
        # rolls back — silently discarding every write on the "successful"
        # path. `async with` always resumes normally, so it always commits.
        async with workspace_scoped_session(payload.workspace_id) as db:
            result = await conversation_engine.start_session(
                db,
                workspace_id=payload.workspace_id,
                agent_id=payload.agent_id,
                contact_name=payload.contact_name,
                campaign_id=payload.campaign_id,
                contact_id=payload.contact_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "call_id": str(result["call_id"]),
        "status": result["status"],
        "language": result["language"],
        "greeting": result["greeting"],
        "estimated_duration_ms": result["estimated_duration_ms"],
        "conversation_state": result["conversation_state"],
    }


class UserTurnRequest(BaseModel):
    workspace_id: uuid.UUID
    text: str


@app.post("/sessions/{call_id}/user-turn", dependencies=[Depends(require_internal_token)])
async def user_turn(call_id: uuid.UUID, payload: UserTurnRequest) -> dict:
    try:
        async with workspace_scoped_session(payload.workspace_id) as db:
            result = await conversation_engine.submit_user_turn(
                db, workspace_id=payload.workspace_id, call_id=call_id, text=payload.text
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "user_turn": {"turn_ref": result.user_turn.turn_ref, "text": result.user_turn.text},
        "interruption_classification": result.interruption_classification,
        "stop_latency_ms": result.stop_latency_ms,
        "agent_turn": (
            {
                "turn_ref": result.agent_turn.turn_ref, "text": result.agent_turn.text,
                "estimated_duration_ms": result.agent_turn.estimated_duration_ms,
            }
            if result.agent_turn else None
        ),
        "conversation_state": result.conversation_state,
        "call_status": result.call_status,
    }


class EndSessionRequest(BaseModel):
    workspace_id: uuid.UUID
    end_reason: str = "agent_ended"


@app.post("/sessions/{call_id}/end", dependencies=[Depends(require_internal_token)])
async def end_session(call_id: uuid.UUID, payload: EndSessionRequest) -> dict:
    try:
        async with workspace_scoped_session(payload.workspace_id) as db:
            result = await conversation_engine.end_session(
                db, workspace_id=payload.workspace_id, call_id=call_id, end_reason=payload.end_reason
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "call_id": str(result["call_id"]),
        "status": result["status"],
        "outcome_category": result["outcome_category"],
        "lead_score": result["lead_score"],
    }
