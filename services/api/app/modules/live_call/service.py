"""Service logic for the live real-call test path.

Deliberately does not reuse services/voice-worker's conversation_engine —
that engine's turn-taking is built around MockLLM's scripted-FSM methods
(next_question/closing_text/question_text), not a general chat loop, and
reworking it wasn't in scope for "prove one real call end-to-end." This
module keeps its own minimal Redis-backed message history for the duration
of one call and persists turns directly into the same call_sessions/
call_turns tables everything else uses, so a real call shows up in the
normal Calls UI/analytics exactly like a mock one — just with is_mock=False.

Speaking uses Sarvam TTS (real Telugu/Hindi/English pronunciation), played
via TwiML <Play> of a briefly-cached audio URL; listening uses Twilio's
<Record> to capture raw audio, transcribed by Sarvam STT — Twilio's own
<Say>/<Gather> only support English and were replaced for exactly that
reason (see docs.sarvam.ai). This is still a synchronous, one-request-per-
turn webhook loop, not the real-time streaming MediaRuntime/TurnManager
pipeline used elsewhere — no barge-in, no duplex audio. If Sarvam TTS
synthesis fails for any reason, this falls back to Twilio's <Say> in English
rather than dropping the call, since a live phone call must always end
gracefully.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from jkr_db.models.agents import Agent, AgentVersion
from jkr_db.models.billing import UsageEvent
from jkr_db.models.calls import CallEvent, CallOutcome, CallParticipant, CallSession, CallSummary, CallTranscript, CallTurn
from jkr_db.phone import InvalidPhoneNumberError, normalize_e164
from jkr_db.session import workspace_scoped_session
from jkr_messaging import enqueue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.live_providers.openai_llm import NotConfiguredError as LLMNotConfiguredError
from app.live_providers.openai_llm import OpenAIChat
from app.live_providers.sarvam_stt import SarvamSTT
from app.live_providers.sarvam_tts import SarvamTTS
from app.live_providers.twilio_telephony import NotConfiguredError as TelephonyNotConfiguredError
from app.live_providers.twilio_telephony import TwilioClient, fetch_recording, validate_twilio_signature

MAX_AGENT_TURNS = 5  # greeting + up to 3 real exchanges + a forced closing turn — bounds cost/duration
REDIS_KEY_PREFIX = "jkr:live_call:"
REDIS_TTL_SECONDS = 1800
AUDIO_KEY_PREFIX = "jkr:live_call_audio:"
AUDIO_TTL_SECONDS = 300  # only needs to survive until Twilio's <Play> fetches it, once
FALLBACK_LANGUAGE = "en-IN"  # only used if Sarvam TTS errors and we fall back to Twilio's <Say>


def _sarvam_language_code(primary_language: str | None) -> str:
    """Maps this codebase's agent.primary_language values (e.g. "te-IN",
    "te-en-IN", "hi-IN") onto one of Sarvam's supported single BCP-47 codes —
    Sarvam's REST TTS endpoint takes exactly one language per request, so a
    code-switched value like "te-en-IN" resolves to its non-English half."""
    lang = (primary_language or "").lower()
    if "te" in lang:
        return "te-IN"
    if "hi" in lang:
        return "hi-IN"
    return "en-IN"


def _redis_key(token: str) -> str:
    return f"{REDIS_KEY_PREFIX}{token}"


def _audio_redis_key(audio_id: str) -> str:
    return f"{AUDIO_KEY_PREFIX}{audio_id}"


def _webhook_urls(settings: Settings, token: str) -> tuple[str, str, str]:
    base = settings.effective_public_webhook_base_url.rstrip("/")
    return (
        f"{base}/api/v1/live-call/webhooks/twilio/voice/{token}",
        f"{base}/api/v1/live-call/webhooks/twilio/status/{token}",
        f"{base}/api/v1/live-call/webhooks/twilio/recording/{token}",
    )


def _audio_url(settings: Settings, audio_id: str) -> str:
    base = settings.effective_public_webhook_base_url.rstrip("/")
    return f"{base}/api/v1/live-call/audio/{audio_id}.wav"


async def cache_audio(redis: Any, *, audio_bytes: bytes) -> str:
    audio_id = uuid.uuid4().hex
    await redis.set(_audio_redis_key(audio_id), base64.b64encode(audio_bytes).decode("ascii"), ex=AUDIO_TTL_SECONDS)
    return audio_id


async def get_cached_audio(redis: Any, *, audio_id: str) -> bytes | None:
    raw = await redis.get(_audio_redis_key(audio_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("ascii")
    return base64.b64decode(raw)


async def _speak(
    text: str, *, language_code: str, settings: Settings, redis: Any
) -> tuple[str, str]:
    """Returns ("play", audio_url) on successful Sarvam synthesis, or
    ("say", text) to fall back to Twilio's own English voice — never raises,
    since a TTS provider hiccup must not silently kill a live phone call."""
    try:
        tts = SarvamTTS(api_key=settings.sarvam_tts_api_key or settings.sarvam_api_key)
        audio_bytes = await tts.synthesize(text=text, language_code=language_code)
    except Exception:  # noqa: BLE001 — deliberately broad, see docstring (covers TTSNotConfiguredError too)
        return ("say", text)
    audio_id = await cache_audio(redis, audio_bytes=audio_bytes)
    return ("play", _audio_url(settings, audio_id))


async def start_live_test_call(
    db: AsyncSession, redis: Any, *, settings: Settings, workspace_id: uuid.UUID, agent_id: uuid.UUID, to_number: str
) -> dict:
    if not settings.enable_live_calls:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Live calls are disabled — set ENABLE_LIVE_CALLS=true to enable this")

    try:
        to_e164 = normalize_e164(to_number)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if to_e164 not in settings.authorized_test_numbers_list:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{to_e164} is not in AUTHORIZED_TEST_NUMBERS — add your own verified number there before dialing it",
        )

    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    if agent.published_version_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agent has no published version")

    version_result = await db.execute(select(AgentVersion).where(AgentVersion.id == agent.published_version_id))
    version = version_result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Published agent version not found")

    try:
        telephony = TwilioClient(
            account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, from_number=settings.twilio_from_number
        )
    except TelephonyNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    # Not used until the webhook fires, but fail fast — a call that connects
    # and then immediately errors on turn one is worse than never dialing.
    try:
        OpenAIChat(api_key=settings.openai_api_key)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    language_code = _sarvam_language_code(agent.primary_language)

    # A fresh, independently-committing session for every write below —
    # deliberately not the request-scoped `db` (whose session.begin() rolls
    # back the *entire* request transaction on any exception, including the
    # Twilio call failing below). Also sidesteps a subtler trap: Postgres
    # `SET LOCAL app.current_workspace_id` (what RLS checks against) only
    # lives for one transaction, so manually committing the request-scoped
    # session mid-request would silently drop RLS on whatever runs after —
    # every fresh workspace_scoped_session sets it up correctly on its own.
    async with workspace_scoped_session(workspace_id) as write_db:
        call_session = CallSession(
            workspace_id=workspace_id,
            direction="outbound",
            status="queued",
            agent_id=agent.id,
            agent_version_id=version.id,
            idempotency_key=f"live-{uuid.uuid4()}",
            language=language_code,
            state={"live_real_call": True},
            started_at=datetime.now(UTC),
            is_mock=False,
            disclosure_confirmed=True,
        )
        write_db.add(call_session)
        await write_db.flush()
        call_session_id = call_session.id
        write_db.add(
            CallParticipant(
                workspace_id=workspace_id, call_session_id=call_session_id, role="agent",
                display_name=agent.name, joined_at=datetime.now(UTC),
            )
        )
        write_db.add(
            CallParticipant(
                workspace_id=workspace_id, call_session_id=call_session_id, role="customer",
                display_name="Live test call", phone_e164=to_e164, joined_at=datetime.now(UTC),
            )
        )
        write_db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type="call_started", payload={"live_real_call": True}))

    greeting_body = version.greeting_text.replace("{name} ", "").replace("{name}", "").strip()
    disclosure = version.ai_disclosure_text.strip()
    # Seed/authored greeting text for several personas already opens with the
    # disclosure sentence verbatim — blindly prepending it again said the same
    # sentence twice back to back. Only prepend when it isn't already there.
    greeting = greeting_body if (disclosure and disclosure in greeting_body) else (disclosure + " " + greeting_body).strip()
    system_prompt = (
        f"You are the AI voice receptionist for {agent.business_identity}, on a real live phone call. "
        f"Your objective this call: {version.primary_objective.replace('_', ' ')}. "
        "Speak naturally and briefly, one short sentence or question at a time — this is a live voice "
        "call, not a chat window. Ask one relevant question, listen, then ask the next. Never invent "
        "facts you don't actually know — offer to have a team member follow up instead."
    )

    token = uuid.uuid4().hex
    state = {
        "workspace_id": str(workspace_id),
        "call_session_id": str(call_session_id),
        "closing_text": version.closing_text,
        "language_code": language_code,
        "greeted": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": greeting},
        ],
        "agent_turns": 1,
        "next_sequence_index": 0,
    }
    await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)

    webhook_url, status_callback_url, _recording_url = _webhook_urls(settings, token)

    try:
        call_sid = await telephony.create_call(to=to_e164, webhook_url=webhook_url, status_callback_url=status_callback_url)
    except Exception as exc:  # noqa: BLE001 — surface Twilio's own error text as-is
        async with workspace_scoped_session(workspace_id) as write_db:
            result = await write_db.execute(select(CallSession).where(CallSession.id == call_session_id))
            failed_session = result.scalar_one_or_none()
            if failed_session is not None:
                failed_session.status = "failed"
                failed_session.end_reason = "error"
        await redis.delete(_redis_key(token))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Twilio call creation failed: {exc}") from exc

    async with workspace_scoped_session(workspace_id) as write_db:
        result = await write_db.execute(select(CallSession).where(CallSession.id == call_session_id))
        dialing_session = result.scalar_one_or_none()
        if dialing_session is not None:
            dialing_session.status = "dialing"
            dialing_session.state = {"live_real_call": True, "provider_call_sid": call_sid}

    return {"call_id": call_session_id, "call_sid": call_sid, "status": "dialing"}


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _speak_element(kind: str, content: str) -> str:
    """`kind`/`content` come from `_speak()`: ("play", url) for real Sarvam
    audio, or ("say", text) for the Twilio-voice fallback."""
    if kind == "play":
        return f"<Play>{_escape_xml(content)}</Play>"
    return f'<Say language="{FALLBACK_LANGUAGE}">{_escape_xml(content)}</Say>'


def _twiml_speak_and_record(kind: str, content: str, *, action_url: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{_speak_element(kind, content)}"
        f'<Record action="{action_url}" method="POST" maxLength="20" timeout="3" '
        f'trim="trim-silence" playBeep="false"/>'
        f'<Say language="{FALLBACK_LANGUAGE}">We did not catch a response. Thank you, goodbye.</Say><Hangup/></Response>'
    )


def _twiml_speak_and_hangup(kind: str, content: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{_speak_element(kind, content)}<Hangup/></Response>'


async def _persist_turn(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, state: dict, speaker: str, text: str
) -> None:
    now = datetime.now(UTC)
    seq = state["next_sequence_index"]
    db.add(
        CallTurn(
            workspace_id=workspace_id, call_session_id=call_session_id, turn_ref=f"{speaker}-{seq}",
            sequence_index=seq, speaker=speaker, text=text, language=state.get("language_code", FALLBACK_LANGUAGE),
            confidence=None, is_interrupted=False, started_at=now, ended_at=now,
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type=f"{speaker}_turn", payload={"text": text}))
    state["next_sequence_index"] = seq + 1


async def _finalize_call(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, call_status: str, end_reason: str,
    had_exchange: bool, language_code: str = FALLBACK_LANGUAGE,
) -> None:
    session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
    call_session = session_result.scalar_one_or_none()
    if call_session is None or call_session.status in {"completed", "failed", "no_answer", "busy", "abandoned"}:
        return

    turns_result = await db.execute(select(CallTurn).where(CallTurn.call_session_id == call_session_id).order_by(CallTurn.sequence_index))
    turns = list(turns_result.scalars().all())
    full_text = "\n".join(f"[{t.speaker}] {t.text}" for t in turns)

    now = datetime.now(UTC)
    call_session.status = call_status
    call_session.end_reason = end_reason
    call_session.ended_at = now
    if call_session.answered_at is None:
        call_session.answered_at = call_session.started_at
    if call_session.started_at:
        call_session.duration_seconds = int((now - call_session.started_at).total_seconds())

    db.add(CallTranscript(workspace_id=workspace_id, call_session_id=call_session_id, full_text=full_text, language=language_code, is_final=True))

    category = "interested" if had_exchange else "unreachable"
    lead_score = "warm" if had_exchange else "not_qualified"
    db.add(
        CallOutcome(
            workspace_id=workspace_id, call_session_id=call_session_id, category=category, lead_score=lead_score,
            score_reasons=[], objective_status="in_progress" if had_exchange else "abandoned",
            notes="Real live call via Twilio + a real LLM + Sarvam TTS/STT — see app/modules/live_call/service.py.",
        )
    )
    db.add(
        CallSummary(
            workspace_id=workspace_id, call_session_id=call_session_id,
            summary_text=full_text or "No exchange occurred.", generated_by="openai_live_test",
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type="call_ended", payload={"reason": end_reason}))

    if call_session.duration_seconds is not None:
        db.add(
            UsageEvent(
                workspace_id=workspace_id, call_session_id=call_session_id, event_type="telephony_seconds",
                quantity=call_session.duration_seconds, unit="seconds", occurred_at=now,
            )
        )

    await db.flush()
    enqueue("run_post_call_pipeline", args=(str(call_session_id), str(workspace_id)), queue_name="intelligence")


async def handle_voice_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> str:
    """Handles only Twilio's *initial* connection — speaks the greeting and
    starts recording the customer's reply. All subsequent turns go through
    `handle_recording_webhook` instead, since <Record> (not <Gather>) is now
    what captures customer speech."""
    webhook_url, _, recording_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=webhook_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    raw = await redis.get(_redis_key(token))
    if raw is None:
        return _twiml_speak_and_hangup("say", "This test session has expired. Goodbye.")

    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])
    language_code = state.get("language_code", FALLBACK_LANGUAGE)

    async with workspace_scoped_session(workspace_id) as db:
        greeting = state["messages"][-1]["content"]
        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=greeting)
        session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call_session = session_result.scalar_one_or_none()
        if call_session is not None:
            call_session.status = "in_progress"
            call_session.answered_at = datetime.now(UTC)
        state["greeted"] = True
        await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)

    kind, content = await _speak(greeting, language_code=language_code, settings=settings, redis=redis)
    return _twiml_speak_and_record(kind, content, action_url=recording_url)


async def handle_recording_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> str:
    """Handles every turn after the greeting: downloads what <Record> just
    captured, transcribes it via Sarvam STT, gets the next reply, and either
    continues (speak + record again) or ends the call (speak + hangup)."""
    _, _, recording_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=recording_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    raw = await redis.get(_redis_key(token))
    if raw is None:
        return _twiml_speak_and_hangup("say", "This test session has expired. Goodbye.")

    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])
    language_code = state.get("language_code", FALLBACK_LANGUAGE)

    twilio_recording_url = form.get("RecordingUrl") or ""
    recording_duration = int(form.get("RecordingDuration") or "0")

    speech_result = ""
    if twilio_recording_url and recording_duration > 0:
        try:
            audio_bytes = await fetch_recording(
                account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, recording_url=twilio_recording_url
            )
            stt = SarvamSTT(api_key=settings.sarvam_api_key or settings.sarvam_tts_api_key)
            speech_result = await stt.transcribe(audio_bytes=audio_bytes)
        except Exception:  # noqa: BLE001 — same reasoning as _speak: never kill the call over a transcription hiccup (covers STTNotConfiguredError too)
            speech_result = ""

    async with workspace_scoped_session(workspace_id) as db:
        if not speech_result:
            closing = "We seem to have lost your response. Thank you for your time, goodbye."
            await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=closing)
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id,
                call_status="abandoned", end_reason="timeout", had_exchange=state["agent_turns"] > 1,
                language_code=language_code,
            )
            await redis.delete(_redis_key(token))
            kind, content = await _speak(closing, language_code=language_code, settings=settings, redis=redis)
            return _twiml_speak_and_hangup(kind, content)

        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="customer", text=speech_result)
        state["messages"].append({"role": "user", "content": speech_result})

        force_close = state["agent_turns"] >= MAX_AGENT_TURNS
        llm_errored = False
        if force_close:
            reply = state["closing_text"]
        else:
            try:
                llm = OpenAIChat(api_key=settings.openai_api_key)
                reply = await llm.reply(messages=state["messages"])
            except Exception:  # noqa: BLE001 — a live phone call must still end gracefully on an LLM error
                reply = state["closing_text"]
                force_close = True
                llm_errored = True

        state["messages"].append({"role": "assistant", "content": reply})
        state["agent_turns"] += 1
        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=reply)

        if force_close:
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                end_reason="error" if llm_errored else "completed", had_exchange=True, language_code=language_code,
            )
            await redis.delete(_redis_key(token))
            kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis)
            return _twiml_speak_and_hangup(kind, content)

        await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)
        kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis)
        return _twiml_speak_and_record(kind, content, action_url=recording_url)


async def handle_status_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> None:
    """Closes out the call record for outcomes the earlier webhooks never see
    at all — no-answer/busy/failed/the customer hanging up before Twilio ever
    reaches <Record>. A completed call is already finalized by
    handle_recording_webhook, so this is a no-op for the normal path (guarded
    by _finalize_call's own idempotency check)."""
    _, status_callback_url, _recording_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=status_callback_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    call_status = form.get("CallStatus", "")
    raw = await redis.get(_redis_key(token))
    if raw is None:
        return
    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])

    if call_status in {"completed", "in-progress", "ringing", "queued"}:
        return  # "completed" here still means the voice webhook path already (or will) finalize it

    status_and_reason = {
        "no-answer": ("no_answer", "timeout"),
        "busy": ("busy", "error"),
        "failed": ("failed", "error"),
        "canceled": ("failed", "error"),
    }.get(call_status, ("failed", "error"))

    async with workspace_scoped_session(workspace_id) as db:
        await _finalize_call(
            db, workspace_id=workspace_id, call_session_id=call_session_id,
            call_status=status_and_reason[0], end_reason=status_and_reason[1], had_exchange=state["agent_turns"] > 1,
            language_code=state.get("language_code", FALLBACK_LANGUAGE),
        )
    await redis.delete(_redis_key(token))
