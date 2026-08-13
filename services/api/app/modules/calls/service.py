from __future__ import annotations

import uuid

import httpx
from fastapi import HTTPException, status
from jkr_db.models.agents import Agent
from jkr_db.models.calls import CallLatencyMetric, CallOutcome, CallSession, CallTurn
from jkr_db.models.calls import InterruptionEvent as InterruptionEventModel
from jkr_db.models.contacts import Contact
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings


def _headers(settings: Settings) -> dict:
    return {"X-Internal-Token": settings.internal_service_token}


async def start_test_call(
    db: AsyncSession, *, settings: Settings, workspace_id: uuid.UUID, agent_id: uuid.UUID, contact_name: str | None
) -> dict:
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    if agent_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    async with httpx.AsyncClient(base_url=settings.voice_worker_base_url, timeout=10.0) as client:
        try:
            response = await client.post(
                "/sessions",
                json={"workspace_id": str(workspace_id), "agent_id": str(agent_id), "contact_name": contact_name},
                headers=_headers(settings),
            )
        except httpx.ConnectError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "voice-worker is not reachable — is it running?"
            ) from exc
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, response.json().get("detail", "voice-worker error"))
    return response.json()


async def submit_user_turn(
    db: AsyncSession, *, settings: Settings, workspace_id: uuid.UUID, call_id: uuid.UUID, text: str
) -> dict:
    session_result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")

    async with httpx.AsyncClient(base_url=settings.voice_worker_base_url, timeout=10.0) as client:
        try:
            response = await client.post(
                f"/sessions/{call_id}/user-turn",
                json={"workspace_id": str(workspace_id), "text": text},
                headers=_headers(settings),
            )
        except httpx.ConnectError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "voice-worker is not reachable — is it running?"
            ) from exc
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, response.json().get("detail", "voice-worker error"))
    return response.json()


async def end_call(db: AsyncSession, *, settings: Settings, workspace_id: uuid.UUID, call_id: uuid.UUID) -> dict:
    session_result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")

    async with httpx.AsyncClient(base_url=settings.voice_worker_base_url, timeout=10.0) as client:
        try:
            response = await client.post(
                f"/sessions/{call_id}/end",
                json={"workspace_id": str(workspace_id)},
                headers=_headers(settings),
            )
        except httpx.ConnectError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "voice-worker is not reachable — is it running?"
            ) from exc
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, response.json().get("detail", "voice-worker error"))

    # Post-call intelligence (spec §19) is enqueued by voice-worker itself,
    # not here — a call can also be ended by campaign-worker's dialer (never
    # going through this proxy at all), and "ending a call always triggers
    # the pipeline" must hold regardless of which caller ended it. See
    # services/voice-worker/app/conversation_engine.py::end_session.
    return response.json()


async def list_calls(db: AsyncSession, *, workspace_id: uuid.UUID, status_filter: str | None = None) -> list[dict]:
    query = (
        select(CallSession, Contact.full_name, CallOutcome.category)
        .outerjoin(Contact, Contact.id == CallSession.contact_id)
        .outerjoin(CallOutcome, CallOutcome.call_session_id == CallSession.id)
        .where(CallSession.workspace_id == workspace_id)
        .order_by(CallSession.started_at.desc().nullslast(), CallSession.id.desc())
    )
    if status_filter:
        query = query.where(CallSession.status == status_filter)
    result = await db.execute(query)
    return [
        {
            "call_id": cs.id, "status": cs.status, "direction": cs.direction, "contact_name": contact_name,
            "outcome_category": outcome_category, "started_at": cs.started_at, "duration_seconds": cs.duration_seconds,
            "is_mock": cs.is_mock, "campaign_id": cs.campaign_id,
        }
        for cs, contact_name, outcome_category in result.all()
    ]


async def get_call_detail(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID) -> dict:
    session_result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
    )
    call_session = session_result.scalar_one_or_none()
    if call_session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")

    turns_result = await db.execute(
        select(CallTurn).where(CallTurn.call_session_id == call_id).order_by(CallTurn.sequence_index)
    )
    interruptions_result = await db.execute(
        select(InterruptionEventModel).where(InterruptionEventModel.call_session_id == call_id).order_by(InterruptionEventModel.occurred_at)
    )
    latency_result = await db.execute(
        select(CallLatencyMetric).where(CallLatencyMetric.call_session_id == call_id).order_by(CallLatencyMetric.recorded_at)
    )
    outcome_result = await db.execute(select(CallOutcome).where(CallOutcome.call_session_id == call_id))

    return {
        "call_session": call_session,
        "turns": list(turns_result.scalars().all()),
        "interruptions": list(interruptions_result.scalars().all()),
        "latency_metrics": list(latency_result.scalars().all()),
        "outcome": outcome_result.scalar_one_or_none(),
    }
