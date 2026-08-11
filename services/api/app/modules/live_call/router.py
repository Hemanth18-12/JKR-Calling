from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jkr_messaging import get_redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.live_call import service
from app.modules.live_call.schemas import LiveTestCallCreate, LiveTestCallStarted

router = APIRouter(prefix="/live-call", tags=["live-call"])


@router.get("/audio/{audio_id}.wav")
async def live_call_audio(audio_id: str) -> Response:
    """Public, unauthenticated by design — Twilio's <Play> verb just does a
    plain GET fetch (no way for it to send a session cookie or signature).
    The random audio_id itself is the only access control, same trust model
    as Twilio's own RecordingUrl; audio is cached for AUDIO_TTL_SECONDS only,
    long enough for Twilio to fetch it once."""
    audio_bytes = await service.get_cached_audio(get_redis(), audio_id=audio_id)
    if audio_bytes is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio not found or expired")
    return Response(content=audio_bytes, media_type="audio/wav")


@router.post("", response_model=LiveTestCallStarted, status_code=201)
async def start_live_test_call(
    payload: LiveTestCallCreate,
    settings: Settings = Depends(get_settings),
    auth: AuthContext = Depends(require_permission("calls:test")),
    db: AsyncSession = Depends(workspace_db_for("calls:test")),
) -> LiveTestCallStarted:
    result = await service.start_live_test_call(
        db, get_redis(), settings=settings, workspace_id=auth.workspace_id, agent_id=payload.agent_id, to_number=payload.to_number
    )
    return LiveTestCallStarted(**result)


# --- Public webhooks below: Twilio calls these directly, with no session
# cookie and no workspace context — every request is instead authenticated
# by verifying Twilio's own HMAC request signature against the auth token
# (see app/live_providers/twilio_telephony.validate_twilio_signature). Do not
# add `Depends(require_permission(...))` to these routes. ---


@router.post("/webhooks/twilio/voice/{token}")
async def twilio_voice_webhook(
    token: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("X-Twilio-Signature")
    twiml = await service.handle_voice_webhook(token=token, form=form, signature=signature, settings=settings, redis=get_redis())
    return Response(content=twiml, media_type="application/xml")


@router.post("/webhooks/twilio/recording/{token}")
async def twilio_recording_webhook(
    token: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("X-Twilio-Signature")
    twiml = await service.handle_recording_webhook(token=token, form=form, signature=signature, settings=settings, redis=get_redis())
    return Response(content=twiml, media_type="application/xml")


@router.post("/webhooks/twilio/closing-grace/{token}")
async def twilio_closing_grace_webhook(
    token: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("X-Twilio-Signature")
    twiml = await service.handle_closing_grace_webhook(token=token, form=form, signature=signature, settings=settings, redis=get_redis())
    return Response(content=twiml, media_type="application/xml")


@router.post("/webhooks/twilio/status/{token}")
async def twilio_status_webhook(
    token: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    signature = request.headers.get("X-Twilio-Signature")
    await service.handle_status_webhook(token=token, form=form, signature=signature, settings=settings, redis=get_redis())
    return Response(status_code=204)
