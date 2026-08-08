"""Service logic for the live real-call test path.

Conversation intelligence (field extraction, RAG, next-action planning,
response generation) now comes from jkr_conversation — the exact same shared
engine services/voice-worker/app/conversation_engine.py uses for Test Lab
calls. This module's own job is transport: driving Twilio's webhook loop,
Sarvam TTS/STT, and persisting turns into the same call_sessions/call_turns
tables everything else uses, so a real call shows up in the normal Calls
UI/analytics exactly like a mock one — just with is_mock=False. It keeps a
minimal Redis-backed cache (recent turns, cached policy) for the duration of
one call since each webhook is a fresh, stateless HTTP request; the durable
conversation state (known_fields, objective_status, etc.) lives on
CallSession.state, same as every other call.

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
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from jkr_conversation.engine import process_turn
from jkr_conversation.schemas import ConversationPolicySnapshot
from jkr_conversation.state import classify_provisional_outcome, new_conversation_state
from jkr_db.models.agents import Agent, AgentVersion, ConversationPolicy
from jkr_db.models.billing import UsageEvent
from jkr_db.models.calls import (
    CallEvent,
    CallOutcome,
    CallParticipant,
    CallSession,
    CallSummary,
    CallTranscript,
    CallTurn,
)
from jkr_db.phone import InvalidPhoneNumberError, normalize_e164
from jkr_db.session import workspace_scoped_session
from jkr_db.tools_engine import ToolNotDefinedError, ToolNotEnabledError, execute_tool
from jkr_messaging import enqueue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.live_providers.sarvam_stt import SarvamSTT
from app.live_providers.sarvam_tts import SarvamTTS
from app.live_providers.twilio_telephony import NotConfiguredError as TelephonyNotConfiguredError
from app.live_providers.twilio_telephony import (
    TwilioClient,
    fetch_recording,
    validate_twilio_signature,
)

# Real ending is the shared engine's planner reaching a terminal state
# (ConversationPolicy.max_turns/max_call_duration_seconds are the safety-net
# ceiling, enforced inside process_turn) — no local turn cap needed here
# anymore. agent_turns below is kept only as an observability counter.
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

    policy_result = await db.execute(select(ConversationPolicy).where(ConversationPolicy.agent_version_id == version.id))
    policy = policy_result.scalar_one_or_none()
    policy_snapshot = (
        ConversationPolicySnapshot(
            max_response_sentences=policy.max_response_sentences,
            human_transfer_enabled=policy.human_transfer_enabled,
            do_not_call_behavior=policy.do_not_call_behavior,
            wrong_number_behavior=policy.wrong_number_behavior,
            clarification_behavior=policy.clarification_behavior,
            confirmation_behavior=policy.confirmation_behavior,
            max_turns=policy.max_turns,
            max_call_duration_seconds=policy.max_call_duration_seconds,
        )
        if policy
        else ConversationPolicySnapshot()
    )

    try:
        telephony = TwilioClient(
            account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, from_number=settings.twilio_from_number
        )
    except TelephonyNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    # No OpenAI fail-fast check here anymore — jkr_conversation degrades
    # gracefully to deterministic mock-mode responses without a key, same
    # posture Sarvam TTS already has via its own <Say> fallback. A live call
    # is placeable either way; it just won't sound as adaptive without a key.

    language_code = _sarvam_language_code(agent.primary_language)

    # A fresh, independently-committing session for every write below —
    # deliberately not the request-scoped `db` (whose session.begin() rolls
    # back the *entire* request transaction on any exception, including the
    # Twilio call failing below). Also sidesteps a subtler trap: Postgres
    # `SET LOCAL app.current_workspace_id` (what RLS checks against) only
    # lives for one transaction, so manually committing the request-scoped
    # session mid-request would silently drop RLS on whatever runs after —
    # every fresh workspace_scoped_session sets it up correctly on its own.
    conversation_state = new_conversation_state(objective=version.primary_objective, language=language_code)
    conversation_state["live_real_call"] = True

    async with workspace_scoped_session(workspace_id) as write_db:
        call_session = CallSession(
            workspace_id=workspace_id,
            direction="outbound",
            status="queued",
            agent_id=agent.id,
            agent_version_id=version.id,
            idempotency_key=f"live-{uuid.uuid4()}",
            language=language_code,
            state=conversation_state,
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

    token = uuid.uuid4().hex
    state = {
        "workspace_id": str(workspace_id),
        "call_session_id": str(call_session_id),
        "closing_text": version.closing_text,
        "language_code": language_code,
        "business_identity": agent.business_identity,
        "policy": asdict(policy_snapshot),
        "greeted": False,
        "recent_turns": [{"speaker": "agent", "text": greeting}],
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

    conversation_state = call_session.state or {}
    category, lead_score = classify_provisional_outcome(conversation_state)
    objective_status = conversation_state.get("objective_status", "in_progress" if had_exchange else "abandoned")
    db.add(
        CallOutcome(
            workspace_id=workspace_id, call_session_id=call_session_id, category=category, lead_score=lead_score,
            score_reasons=[f"{k}: {v}" for k, v in conversation_state.get("known_fields", {}).items()],
            objective_status=objective_status,
            notes="Real live call via Twilio + Sarvam TTS/STT + the shared jkr_conversation engine — see app/modules/live_call/service.py.",
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
        greeting = state["recent_turns"][-1]["text"]
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

        # Everything from here down — field extraction, knowledge retrieval,
        # next-action planning, response generation — is the shared engine,
        # the exact same code path services/voice-worker uses for Test Lab
        # calls. This module only handles Twilio transport and persistence,
        # never conversation reasoning itself.
        session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call_session = session_result.scalar_one_or_none()
        conversation_state = dict(call_session.state) if call_session is not None and call_session.state else {}
        policy_snapshot = ConversationPolicySnapshot(**state.get("policy", {}))

        result = await process_turn(
            db, workspace_id=workspace_id, call_session_id=call_session_id, state=conversation_state,
            customer_utterance=speech_result, conversation_policy=policy_snapshot,
            business_identity=state.get("business_identity", ""), recent_turns=state.get("recent_turns", [])[-6:],
        )

        for tool_call in result.tool_calls_requested:
            try:
                execution = await execute_tool(
                    db, workspace_id=workspace_id, tool_name=tool_call.tool_name, tool_input=tool_call.tool_input,
                    idempotency_key=f"call-{call_session_id}-{tool_call.idempotency_suffix}",
                    call_session_id=call_session_id, agent_version_id=call_session.agent_version_id if call_session else None,
                )
                if execution.status == "succeeded":
                    result.state.setdefault("tool_results", {})[tool_call.tool_name] = execution.output
            except (ToolNotDefinedError, ToolNotEnabledError):
                pass  # tool not configured for this workspace — the call still proceeds, matching prior behavior

        if call_session is not None:
            call_session.state = result.state

        reply = result.reply_text
        state["recent_turns"].append({"speaker": "customer", "text": speech_result})
        state["recent_turns"].append({"speaker": "agent", "text": reply})
        state["agent_turns"] += 1
        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=reply)

        # live_call has no real warm-transfer capability yet, so a human-
        # handoff decision closes the call here too — unlike Test Lab, which
        # keeps the session open after an acknowledged handoff.
        force_close = result.call_should_end or result.planner_action == "HUMAN_HANDOFF"

        if force_close:
            end_reason_by_planner_reason = {
                "do_not_call_requested": "do_not_call",
                "wrong_number": "wrong_number",
                "all_fields_collected": "completed",
                "max_turns_reached": "completed",
                "max_duration_reached": "completed",
            }
            end_reason = end_reason_by_planner_reason.get(result.planner_reason, "transferred" if result.planner_action == "HUMAN_HANDOFF" else "completed")
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                end_reason=end_reason, had_exchange=True, language_code=language_code,
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
