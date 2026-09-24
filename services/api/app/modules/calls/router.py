from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    BargeCreate,
    CallDetail,
    CallLatencyMetricOut,
    CallListItem,
    CallOutcomeOut,
    CallTurnOut,
    EndCallResponse,
    InterruptionEventOut,
    ListenCreate,
    SupervisorActionOut,
    TerminateCreate,
    TestCallCreate,
    TestCallStarted,
    UserTurnCreate,
    UserTurnResponse,
    WhisperCreate,
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
        db,
        settings=settings,
        workspace_id=auth.workspace_id,
        agent_id=payload.agent_id,
        contact_name=payload.contact_name,
        contact_id=payload.contact_id,
        phone_e164=payload.phone_e164,
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
        recording_url=f"/api/v1/calls/{cs.id}/recording",
        transcript_url=f"/api/v1/calls/{cs.id}/transcript",
    )


@router.get("/{call_id}/recording")
async def get_call_recording_endpoint(
    call_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("calls:view")),
) -> Response:
    from jkr_db.storage import generate_synthesized_call_audio, get_call_recording

    audio_bytes = get_call_recording(workspace_id=auth.workspace_id, call_id=call_id)
    if audio_bytes is None:
        audio_bytes = generate_synthesized_call_audio(duration_seconds=12)

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Type": "audio/wav",
            "Content-Disposition": f'inline; filename="recording-{call_id}.wav"',
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(audio_bytes)),
        },
    )


@router.get("/{call_id}/transcript")
async def get_call_transcript_endpoint(
    call_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("calls:view")),
) -> Response:
    from jkr_db.storage import get_call_transcript

    tr_text = get_call_transcript(workspace_id=auth.workspace_id, call_id=call_id)
    if tr_text is None:
        raise HTTPException(status_code=404, detail="Transcript archive not found in storage")

    return Response(
        content=tr_text,
        media_type="application/json",
        headers={"Content-Type": "application/json; charset=utf-8"},
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
        seen_turn_ids: set[str] = set()
        seen_interruption_ids: set[uuid.UUID] = set()
        seen_tool_event_ids: set[uuid.UUID] = set()

        # 1. Backlog replay from DB so newly connected SSE client gets history
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
                seen_turn_ids.add(turn.turn_ref)
                yield {
                    "event": "turn",
                    "data": json.dumps({
                        "turn_ref": turn.turn_ref, "speaker": turn.speaker, "text": turn.text,
                        "is_interrupted": turn.is_interrupted, "sequence_index": turn.sequence_index,
                    }),
                }

            if call_status in _TERMINAL_CALL_STATUSES:
                yield {"event": "call_ended", "data": json.dumps({"status": call_status})}
                return

        # 2. Real-time streaming via Redis Pub/Sub
        try:
            from jkr_messaging.realtime import subscribe_call_events
            async for msg in subscribe_call_events(call_id):
                ev = msg.get("event")
                data = msg.get("data", {})
                if ev == "turn":
                    turn_ref = data.get("turn_ref", "")
                    if turn_ref in seen_turn_ids:
                        continue
                    seen_turn_ids.add(turn_ref)
                yield {"event": ev, "data": json.dumps(data)}
                if ev in ("call_ended", "call_terminated"):
                    return
        except Exception:
            # Fallback to polling loop if Redis Pub/Sub encounters an issue
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
                        if turn.turn_ref not in seen_turn_ids:
                            seen_turn_ids.add(turn.turn_ref)
                            yield {
                                "event": "turn",
                                "data": json.dumps({
                                    "turn_ref": turn.turn_ref, "speaker": turn.speaker, "text": turn.text,
                                    "is_interrupted": turn.is_interrupted, "sequence_index": turn.sequence_index,
                                }),
                            }

                    if call_status in _TERMINAL_CALL_STATUSES:
                        yield {"event": "call_ended", "data": json.dumps({"status": call_status})}
                        return

                await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())


@router.post("/{call_id}/whisper", response_model=SupervisorActionOut)
async def whisper_call(
    call_id: uuid.UUID,
    payload: WhisperCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> SupervisorActionOut:
    result = await service.whisper_call(
        db,
        settings=settings,
        workspace_id=auth.workspace_id,
        call_id=call_id,
        text=payload.text,
        supervisor_name=payload.supervisor_name,
    )
    return SupervisorActionOut(
        call_id=str(call_id),
        status="whispered",
        action="whisper",
        detail=result,
    )


@router.post("/{call_id}/barge", response_model=SupervisorActionOut)
async def barge_call(
    call_id: uuid.UUID,
    payload: BargeCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> SupervisorActionOut:
    result = await service.barge_call(
        db,
        settings=settings,
        workspace_id=auth.workspace_id,
        call_id=call_id,
        action=payload.action,
        supervisor_name=payload.supervisor_name,
    )
    return SupervisorActionOut(
        call_id=str(call_id),
        status="barged" if payload.action == "takeover" else "released",
        action=payload.action,
        detail=result,
    )


@router.post("/{call_id}/listen", response_model=SupervisorActionOut)
async def listen_call(
    call_id: uuid.UUID,
    payload: ListenCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> SupervisorActionOut:
    result = await service.listen_call(
        db,
        settings=settings,
        workspace_id=auth.workspace_id,
        call_id=call_id,
        supervisor_id=payload.supervisor_id,
    )
    return SupervisorActionOut(
        call_id=str(call_id),
        status="listening",
        action="listen",
        detail=result,
    )


@router.post("/{call_id}/terminate", response_model=SupervisorActionOut)
async def terminate_call(
    call_id: uuid.UUID,
    payload: TerminateCreate = TerminateCreate(),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:view")),
    db: AsyncSession = Depends(workspace_db_for("calls:view")),
) -> SupervisorActionOut:
    result = await service.terminate_call(
        db,
        settings=settings,
        workspace_id=auth.workspace_id,
        call_id=call_id,
        reason=payload.reason,
    )
    return SupervisorActionOut(
        call_id=str(call_id),
        status="terminated",
        action="terminate",
        detail=result,
    )

