from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Query
from jkr_db.models.calls import CallEvent, CallSession, CallTurn
from jkr_db.models.calls import InterruptionEvent as InterruptionEventModel
from jkr_db.session import workspace_scoped_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import Settings, get_settings
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.calls import service
from app.modules.calls.schemas import (
    CallDetail,
    CallLatencyMetricOut,
    CallListItem,
    CallOutcomeOut,
    CallTurnOut,
    EndCallResponse,
    InterruptionEventOut,
    TestCallCreate,
    TestCallStarted,
    UserTurnCreate,
    UserTurnResponse,
)

router = APIRouter(prefix="/calls", tags=["calls"])

# CallStatus values that mean "nothing more will ever happen on this call" —
# the SSE stream closes itself once it observes one of these, per
# docs/DECISIONS/0005.
_TERMINAL_CALL_STATUSES = {"completed", "failed", "abandoned"}

_POLL_INTERVAL_SECONDS = 0.5


@router.get("", response_model=list[CallListItem])
async def list_calls(
    status: str | None = Query(default=None),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> list[CallListItem]:
    rows = await service.list_calls(db, workspace_id=auth.workspace_id, status_filter=status)
    return [CallListItem(**r) for r in rows]


@router.post("/test", response_model=TestCallStarted, status_code=201)
async def start_test_call(
    payload: TestCallCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:test")),
    db: AsyncSession = Depends(workspace_db_for("calls:test")),
) -> TestCallStarted:
    result = await service.start_test_call(
        db, settings=settings, workspace_id=auth.workspace_id, agent_id=payload.agent_id, contact_name=payload.contact_name
    )
    return TestCallStarted(**result)


@router.post("/{call_id}/user-turn", response_model=UserTurnResponse)
async def submit_user_turn(
    call_id: uuid.UUID,
    payload: UserTurnCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:test")),
    db: AsyncSession = Depends(workspace_db_for("calls:test")),
) -> UserTurnResponse:
    result = await service.submit_user_turn(
        db, settings=settings, workspace_id=auth.workspace_id, call_id=call_id, text=payload.text
    )
    return UserTurnResponse(**result)


@router.post("/{call_id}/end", response_model=EndCallResponse)
async def end_call(
    call_id: uuid.UUID,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:test")),
    db: AsyncSession = Depends(workspace_db_for("calls:test")),
) -> EndCallResponse:
    result = await service.end_call(db, settings=settings, workspace_id=auth.workspace_id, call_id=call_id)
    return EndCallResponse(**result)


@router.get("/{call_id}", response_model=CallDetail)
async def get_call(
    call_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> CallDetail:
    data = await service.get_call_detail(db, workspace_id=auth.workspace_id, call_id=call_id)
    cs = data["call_session"]
    return CallDetail(
        call_id=cs.id,
        status=cs.status,
        direction=cs.direction,
        language=cs.language,
        agent_id=cs.agent_id,
        started_at=cs.started_at,
        ended_at=cs.ended_at,
        duration_seconds=cs.duration_seconds,
        conversation_state=cs.state,
        turns=[
            CallTurnOut(
                turn_ref=t.turn_ref, sequence_index=t.sequence_index, speaker=t.speaker, text=t.text,
                language=t.language, confidence=t.confidence, is_interrupted=t.is_interrupted, started_at=t.started_at,
            )
            for t in data["turns"]
        ],
        interruptions=[
            InterruptionEventOut(classification=i.classification, stop_latency_ms=i.stop_latency_ms, occurred_at=i.occurred_at)
            for i in data["interruptions"]
        ],
        latency_metrics=[
            CallLatencyMetricOut(stage=m.stage, duration_ms=m.duration_ms, is_simulated=m.is_simulated, recorded_at=m.recorded_at)
            for m in data["latency_metrics"]
        ],
        outcome=(
            CallOutcomeOut(
                category=data["outcome"].category, lead_score=data["outcome"].lead_score,
                score_reasons=data["outcome"].score_reasons, objective_status=data["outcome"].objective_status,
                notes=data["outcome"].notes,
            )
            if data["outcome"]
            else None
        ),
    )


@router.get("/{call_id}/events")
async def stream_call_events(
    call_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("calls:view")),
) -> EventSourceResponse:
    """SSE per docs/DECISIONS/0005 — polls the same tables voice-worker
    writes rather than a dedicated pub/sub. Deliberately does NOT hold the
    `workspace_db_for` request-scoped session open for the connection's
    whole lifetime (that dependency commits/closes once, at ordinary request
    end): a long-lived stream instead opens a fresh, short-lived
    `workspace_scoped_session` every poll tick so each tick reads truly
    fresh committed state, not a snapshot frozen at connection time."""
    workspace_id = auth.workspace_id

    async def event_generator():
        seen_turn_ids: set[uuid.UUID] = set()
        seen_interruption_ids: set[uuid.UUID] = set()
        seen_tool_event_ids: set[uuid.UUID] = set()

        while True:
            async with workspace_scoped_session(workspace_id) as db:
                session_result = await db.execute(
                    select(CallSession.status).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
                )
                call_status = session_result.scalar_one_or_none()
                if call_status is None:
                    yield {"event": "error", "data": json.dumps({"message": "call not found"})}
                    return

                turns_result = await db.execute(
                    select(CallTurn).where(CallTurn.call_session_id == call_id).order_by(CallTurn.sequence_index)
                )
                for turn in turns_result.scalars().all():
                    if turn.id not in seen_turn_ids:
                        seen_turn_ids.add(turn.id)
                        yield {
                            "event": "turn",
                            "data": json.dumps({
                                "turn_ref": turn.turn_ref, "speaker": turn.speaker, "text": turn.text,
                                "is_interrupted": turn.is_interrupted, "sequence_index": turn.sequence_index,
                            }),
                        }

                interruptions_result = await db.execute(
                    select(InterruptionEventModel).where(InterruptionEventModel.call_session_id == call_id).order_by(InterruptionEventModel.occurred_at)
                )
                for interruption in interruptions_result.scalars().all():
                    if interruption.id not in seen_interruption_ids:
                        seen_interruption_ids.add(interruption.id)
                        yield {
                            "event": "interruption",
                            "data": json.dumps({"classification": interruption.classification, "stop_latency_ms": interruption.stop_latency_ms}),
                        }

                tool_events_result = await db.execute(
                    select(CallEvent)
                    .where(CallEvent.call_session_id == call_id, CallEvent.event_type.in_(["knowledge_lookup", "call_started", "call_ended"]))
                    .order_by(CallEvent.created_at)
                )
                for event in tool_events_result.scalars().all():
                    if event.id not in seen_tool_event_ids:
                        seen_tool_event_ids.add(event.id)
                        yield {"event": event.event_type, "data": json.dumps(event.payload)}

                if call_status in _TERMINAL_CALL_STATUSES:
                    yield {"event": "call_ended", "data": json.dumps({"status": call_status})}
                    return

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
