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

import asyncio
import base64
import json
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from jkr_conversation.engine import process_turn
from jkr_conversation.schemas import ConversationPolicySnapshot, ConversationTurnResult
from jkr_conversation.state import classify_provisional_outcome, new_conversation_state
from jkr_db.enums import ProviderName
from jkr_db.models.agents import Agent, AgentVersion, ConversationPolicy, VoicePersona
from jkr_db.models.billing import UsageEvent
from jkr_db.models.calls import (
    CallEvent,
    CallLatencyMetric,
    CallOutcome,
    CallParticipant,
    CallSession,
    CallSummary,
    CallTranscript,
    CallTurn,
)
from jkr_db.models.contacts import Contact
from jkr_db.phone import InvalidPhoneNumberError, normalize_e164
from jkr_db.session import workspace_scoped_session
from jkr_db.tools_engine import REAL_SIDE_EFFECT_TOOLS, ToolNotDefinedError, ToolNotEnabledError, execute_tool
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

# <Record>'s "timeout" is seconds of trailing silence Twilio waits before it
# ends the recording and POSTs it to us. Real conversational voice AI
# systems benchmark much lower than Twilio's 5s default (LiveKit VAD
# 0.25-0.55s, OpenAI Realtime 500ms, Deepgram ~1s, Vapi 0.1-1.5s) — but
# those are all real VAD, which separately tracks "waiting for speech to
# start" vs. "silence after speech ended." <Record> has only ONE timer for
# both. Confirmed by a real call: a customer who paused to think before
# answering an open-ended question ("describe your issue") had their
# recording end in total silence at timeout=2s — before they'd said a
# word — and the call was abandoned as a false "lost your response."
# Tuned up to prioritize never losing a genuine reply over shaving off
# dead-air; a dropped call is a far worse outcome than an extra second of
# gap. This whole class of bug goes away once real streaming VAD (which
# can tell "still thinking" apart from "done talking") replaces <Record> —
# see docs/REALTIME_VOICE_MIGRATION_AUDIT.md.
RECORD_SILENCE_TIMEOUT_SECONDS = 4


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


def _resolve_tts_speaker(voice: VoicePersona | None) -> str | None:
    """None means "use SarvamTTS's own default (priya)" — the safe choice
    for every agent that isn't explicitly configured for provider=
    sarvam_tts, since VoicePersona.voice_id otherwise holds a provider-
    specific placeholder (e.g. the seed/demo default "mock-warm-female-te")
    that would break a real Sarvam TTS call if sent as a literal speaker
    name. Only pass voice_id through when the persona was actually set up
    for Sarvam — see docs/REALTIME_VOICE_MIGRATION_AUDIT.md."""
    if voice is not None and voice.provider == ProviderName.SARVAM_TTS and voice.voice_id:
        return voice.voice_id
    return None


# P7 — bulbul:v3's own verified pace range (docs/SARVAM_STREAMING_TTS_CONTRACT.md);
# bulbul:v2 supports a wider 0.3-3.0 range, but this codebase's streaming
# path is pinned to v3 (see sarvam_streaming_tts.py), so v3's tighter range
# is the one that actually matters — clamping here means an out-of-range
# VoicePersona.speaking_speed value degrades to the nearest valid pace
# rather than the provider rejecting the whole config message.
SARVAM_V3_MIN_PACE = 0.5
SARVAM_V3_MAX_PACE = 2.0


def _resolve_tts_pace(voice: VoicePersona | None) -> float:
    """Only meaningful for a persona actually configured for Sarvam — same
    gating _resolve_tts_speaker already applies, for the same reason (a
    non-Sarvam persona's speaking_speed wasn't necessarily authored with
    Sarvam's pace semantics/range in mind)."""
    if voice is None or voice.provider != ProviderName.SARVAM_TTS:
        return 1.0
    return max(SARVAM_V3_MIN_PACE, min(SARVAM_V3_MAX_PACE, voice.speaking_speed))


def _redis_key(token: str) -> str:
    return f"{REDIS_KEY_PREFIX}{token}"


def _audio_redis_key(audio_id: str) -> str:
    return f"{AUDIO_KEY_PREFIX}{audio_id}"


def _webhook_urls(settings: Settings, token: str) -> tuple[str, str, str, str]:
    base = settings.effective_public_webhook_base_url.rstrip("/")
    return (
        f"{base}/api/v1/live-call/webhooks/twilio/voice/{token}",
        f"{base}/api/v1/live-call/webhooks/twilio/status/{token}",
        f"{base}/api/v1/live-call/webhooks/twilio/recording/{token}",
        f"{base}/api/v1/live-call/webhooks/twilio/closing-grace/{token}",
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
    text: str, *, language_code: str, settings: Settings, redis: Any, speaker: str | None = None, pace: float = 1.0
) -> tuple[str, str]:
    """Returns ("play", audio_url) on successful Sarvam synthesis, or
    ("say", text) to fall back to Twilio's own English voice — never raises,
    since a TTS provider hiccup must not silently kill a live phone call.

    `speaker` is the agent's configured VoicePersona.voice_id (see
    start_live_test_call), only ever passed through when that persona is
    actually configured for provider=sarvam_tts — SarvamTTS's own "priya"
    default covers every agent that isn't (which today is all of them; see
    docs/REALTIME_VOICE_MIGRATION_AUDIT.md — this used to be silently
    ignored regardless of configuration).

    `pace` is _resolve_tts_pace(voice)'s result — previously computed and
    cached in Redis state as "tts_pace" but never actually forwarded to
    SarvamTTS itself (dead computation; see docs/STAGE2_REAL_CALL_FIXES.md
    Fix 3), so a configured VoicePersona.speaking_speed had no real effect
    on this transport. Always passed through (unlike speaker) since 1.0 is
    Sarvam's own natural-pace default — there is no "omit it" case to
    preserve here."""
    try:
        tts = SarvamTTS(
            api_key=settings.sarvam_tts_api_key or settings.sarvam_api_key, pace=pace,
            **({"speaker": speaker} if speaker else {}),
        )
        audio_bytes = await tts.synthesize(text=text, language_code=language_code)
    except Exception:  # noqa: BLE001 — deliberately broad, see docstring (covers TTSNotConfiguredError too)
        return ("say", text)
    audio_id = await cache_audio(redis, audio_bytes=audio_bytes)
    return ("play", _audio_url(settings, audio_id))


async def _get_or_create_contact(db: AsyncSession, *, workspace_id: uuid.UUID, phone_e164: str) -> Contact:
    """The canonical contact_id this call's tool requests must carry all the
    way through — resolved once, here, at call creation, from the one real
    identity a live call actually has at that point (the number being
    dialed). Previously never resolved at all: CallSession.contact_id stayed
    None for every /api/v1/live-call call, so book_appointment always
    received contact_id=None and could never legally succeed (see
    docs/STAGE2_REAL_CALL_FIXES.md Fix 1). full_name is a placeholder — the
    real name isn't known until/unless the conversation captures one — same
    placeholder spirit as the CallParticipant display_name already used for
    this call below."""
    existing = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id, Contact.phone_e164 == phone_e164))
    contact = existing.scalar_one_or_none()
    if contact is not None:
        return contact
    contact = Contact(workspace_id=workspace_id, full_name="Live test call", phone_e164=phone_e164)
    db.add(contact)
    await db.flush()
    return contact


async def start_live_test_call(
    db: AsyncSession, redis: Any, *, settings: Settings, workspace_id: uuid.UUID, agent_id: uuid.UUID, to_number: str
) -> dict:
    if not settings.enable_live_calls:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Live calls are disabled — set ENABLE_LIVE_CALLS=true to enable this")

    try:
        to_e164 = normalize_e164(to_number)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if not settings.is_authorized_test_number(to_e164):
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

    # The agent's configured voice — previously loaded from the DB and then
    # silently discarded; every real call used SarvamTTS's hardcoded "priya"
    # default regardless of what was configured (see
    # docs/REALTIME_VOICE_MIGRATION_AUDIT.md).
    voice_result = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == version.id))
    voice = voice_result.scalar_one_or_none()
    tts_speaker = _resolve_tts_speaker(voice)
    tts_pace = _resolve_tts_pace(voice)

    missing_twilio = []
    if not settings.twilio_account_sid:
        missing_twilio.append("TWILIO_ACCOUNT_SID")
    if not settings.twilio_auth_token:
        missing_twilio.append("TWILIO_AUTH_TOKEN")
    if not settings.twilio_from_number:
        missing_twilio.append("TWILIO_FROM_NUMBER")
    if missing_twilio:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Twilio credentials missing on Render: {', '.join(missing_twilio)}. Please check the Environment tab on Render.",
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
        contact = await _get_or_create_contact(write_db, workspace_id=workspace_id, phone_e164=to_e164)
        call_session = CallSession(
            workspace_id=workspace_id,
            direction="outbound",
            status="queued",
            agent_id=agent.id,
            agent_version_id=version.id,
            contact_id=contact.id,
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
    webhook_url, status_callback_url, _recording_url, _closing_grace_url = _webhook_urls(settings, token)

    # Synthesize the greeting concurrently with placing the call, rather
    # than only after the customer has already picked up (the old behavior
    # — handle_voice_webhook called _speak() itself, so the customer sat in
    # silence through a full TTS round-trip AFTER answering). Twilio's own
    # ring time is several seconds of otherwise-wasted lead time; neither
    # task depends on the other's result, so they run in parallel here, not
    # back-to-back.
    try:
        (greeting_kind, greeting_content), call_sid = await asyncio.gather(
            _speak(greeting, language_code=language_code, settings=settings, redis=redis, speaker=tts_speaker, pace=tts_pace),
            telephony.create_call(to=to_e164, webhook_url=webhook_url, status_callback_url=status_callback_url),
        )
    except Exception as exc:  # noqa: BLE001 — surface Twilio's own error text as-is
        async with workspace_scoped_session(workspace_id) as write_db:
            result = await write_db.execute(select(CallSession).where(CallSession.id == call_session_id))
            failed_session = result.scalar_one_or_none()
            if failed_session is not None:
                failed_session.status = "failed"
                failed_session.end_reason = "error"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Twilio call creation failed: {exc}") from exc

    state = {
        "workspace_id": str(workspace_id),
        "call_session_id": str(call_session_id),
        "closing_text": version.closing_text,
        "language_code": language_code,
        "business_identity": agent.business_identity,
        "policy": asdict(policy_snapshot),
        # None for every agent still on the mock/default voice persona —
        # SarvamTTS's own "priya" default covers that case, see _speak().
        "tts_speaker": tts_speaker,
        "tts_pace": tts_pace,
        "greeted": False,
        "recent_turns": [{"speaker": "agent", "text": greeting}],
        "agent_turns": 1,
        "next_sequence_index": 0,
        # Pre-synthesized above — handle_voice_webhook uses this directly
        # instead of calling _speak() again once the customer answers.
        "greeting_kind": greeting_kind,
        "greeting_content": greeting_content,
    }
    await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)

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
    # playBeep=true (was false): <Record> has no volume/sensitivity
    # parameter at all — "must speak loudly to be heard" was never
    # fixable via any silence-threshold tuning. The real, documented-
    # adjacent cause is the customer having no cue for exactly when
    # recording starts without a beep, so they likely began speaking
    # right as/before the verb transitioned, clipping their utterance's
    # onset — a beep gives them an explicit "go" signal instead.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{_speak_element(kind, content)}"
        f'<Record action="{action_url}" method="POST" maxLength="20" timeout="{RECORD_SILENCE_TIMEOUT_SECONDS}" '
        f'trim="trim-silence" playBeep="true"/>'
        f'<Say language="{FALLBACK_LANGUAGE}">We did not catch a response. Thank you, goodbye.</Say><Hangup/></Response>'
    )


def _twiml_speak_and_hangup(kind: str, content: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{_speak_element(kind, content)}<Hangup/></Response>'


def _twiml_speak_then_grace_listen(kind: str, content: str, *, action_url: str) -> str:
    """The closing line, followed by a short listening window instead of an
    immediate hangup. Twilio's <Play> always finishes before <Record> starts
    (sequential TwiML execution — confirmed, not assumed), so this alone is
    what guarantees the closing audio fully plays before any hangup logic
    can run. Real speech within the window routes to
    handle_closing_grace_webhook, which either resumes the conversation or
    (for a do-not-call/wrong-number closing) still ends the call — see that
    handler. Silence there finalizes for real. The trailing <Say>/<Hangup>
    is a defensive fallback only: action_url always fires once <Record>
    completes, silence or not, so this line normally never executes.
    playBeep=true for the same reason as _twiml_speak_and_record — without
    it, a customer speaking up right after the closing line risks having
    its onset clipped."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{_speak_element(kind, content)}"
        f'<Record action="{action_url}" method="POST" maxLength="6" timeout="{RECORD_SILENCE_TIMEOUT_SECONDS}" '
        f'trim="trim-silence" playBeep="true"/>'
        f'<Say language="{FALLBACK_LANGUAGE}">Goodbye.</Say><Hangup/></Response>'
    )


def _twiml_hangup_only() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def _reopen_conversation_state(state: dict) -> dict:
    """Called only when the customer speaks again during the closing grace
    window for a genuinely resumable closing (objective completion / human
    handoff) — the call isn't actually over yet. Flips objective_status back
    to in_progress so the shared engine treats this as a live turn again.
    Deliberately does NOT reset do_not_call/wrong_number — those are never
    reached from here in the first place (handle_closing_grace_webhook
    short-circuits before calling this for that case), but even so, this
    function must never be the thing that could silently undo either flag."""
    reopened = dict(state)
    if reopened.get("objective_status") == "completed":
        reopened["objective_status"] = "in_progress"
    reopened["awaiting_field"] = None
    reopened["next_best_action"] = "ask_question"
    reopened["reopened_from_closing"] = True
    return reopened


_END_REASON_BY_PLANNER_REASON = {
    "do_not_call_requested": "do_not_call",
    "wrong_number": "wrong_number",
    "all_fields_collected": "completed",
    "max_turns_reached": "completed",
    "max_duration_reached": "completed",
}


def _end_reason_for(result: ConversationTurnResult) -> str:
    return _END_REASON_BY_PLANNER_REASON.get(
        result.planner_reason, "transferred" if result.planner_action == "HUMAN_HANDOFF" else "completed"
    )


# Spoken ONLY when a REAL_SIDE_EFFECT_TOOLS call (book_appointment etc.)
# actually failed this turn — never the canned objective closing_text
# (objectives.py), which is unconditionally success-flavored and, before
# this fix, was spoken regardless of whether the tool succeeded. See
# docs/STAGE2_REAL_CALL_FIXES.md Fix 1: the customer must never hear a
# false success.
_TOOL_FAILURE_REPLY = {
    "te-IN": "క్షమించండి అండి, మీ అపాయింట్‌మెంట్ ఇప్పుడే book చేయలేకపోయాను. దయచేసి కొద్దిసేపటి తర్వాత మళ్ళీ ప్రయత్నించండి, లేదా మమ్మల్ని నేరుగా సంప్రదించండి.",
    "hi-IN": "माफ़ कीजिए, आपकी अपॉइंटमेंट अभी बुक नहीं हो पाई। कृपया थोड़ी देर बाद फिर कोशिश करें, या हमसे सीधे संपर्क करें।",
    "en-IN": "Sorry, I wasn't able to book your appointment just now. Please try again shortly, or contact us directly.",
}


def _tool_failure_reply(language_code: str) -> str:
    return _TOOL_FAILURE_REPLY.get(language_code, _TOOL_FAILURE_REPLY["en-IN"])


async def _execute_tool_calls(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID,
    call_session: CallSession | None, result: ConversationTurnResult,
) -> bool:
    """Executes every tool the planner requested this turn, folding
    successful outputs into result.state (mutated in place, same as before
    this fix). Returns True if any REAL_SIDE_EFFECT_TOOLS call — one with
    genuine business consequences, e.g. book_appointment — failed, so the
    caller can override the spoken reply: the canned COMPLETE_OBJECTIVE
    closing line is built by process_turn() before any tool call is even
    constructed, let alone executed (see engine.py), so it cannot itself
    reflect the tool's real outcome. A tool the workspace hasn't configured
    (ToolNotDefinedError/ToolNotEnabledError) is not a failure of THIS
    call's booking attempt — the call proceeds exactly as before this fix.

    contact_id now always comes from call_session.contact_id, resolved once
    at call creation by _get_or_create_contact — previously omitted
    entirely here, which is the other half of the same audit finding (see
    docs/STAGE2_REAL_CALL_FIXES.md Fix 1)."""
    any_real_tool_failed = False
    for tool_call in result.tool_calls_requested:
        try:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name=tool_call.tool_name, tool_input=tool_call.tool_input,
                idempotency_key=f"call-{call_session_id}-{tool_call.idempotency_suffix}",
                call_session_id=call_session_id, contact_id=call_session.contact_id if call_session else None,
                agent_version_id=call_session.agent_version_id if call_session else None,
            )
            if execution.status == "succeeded":
                result.state.setdefault("tool_results", {})[tool_call.tool_name] = execution.output
            elif tool_call.tool_name in REAL_SIDE_EFFECT_TOOLS:
                any_real_tool_failed = True
        except (ToolNotDefinedError, ToolNotEnabledError):
            pass  # tool not configured for this workspace — the call still proceeds, matching prior behavior
    return any_real_tool_failed


async def _record_latency(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, stage: str, duration_ms: int, provider: str | None = None
) -> None:
    """Real (is_simulated=False) per-stage timing for the batch Twilio
    <Record> pipeline — this is the baseline instrumentation the real-time
    migration audit (docs/REALTIME_VOICE_MIGRATION_AUDIT.md) is measured
    against, mirroring services/voice-worker/app/conversation_engine.py's
    own _record_latency (same CallLatencyMetric table, is_simulated=True
    there since that path has no real audio at all)."""
    db.add(
        CallLatencyMetric(
            workspace_id=workspace_id, call_session_id=call_session_id, provider=provider,
            stage=stage, duration_ms=duration_ms, is_simulated=False, recorded_at=datetime.now(UTC),
        )
    )


async def _persist_turn(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_session_id: uuid.UUID, state: dict, speaker: str, text: str,
    metadata: dict | None = None,
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
    payload = {"text": text, **(metadata or {})}
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session_id, event_type=f"{speaker}_turn", payload=payload))
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
    try:
        from jkr_db.pipeline import run_post_call_pipeline
        await run_post_call_pipeline(
            db, workspace_id=workspace_id, call_id=call_session_id,
            encryption_key=settings.credentials_encryption_key,
        )
    except Exception as exc:
        logger.exception("Error executing post_call_pipeline inline: %s", exc)
        try:
            enqueue("run_post_call_pipeline", args=(str(call_session_id), str(workspace_id)), queue_name="intelligence")
        except Exception:
            pass


async def handle_voice_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> str:
    """Handles only Twilio's *initial* connection — speaks the greeting and
    starts recording the customer's reply. All subsequent turns go through
    `handle_recording_webhook` instead, since <Record> (not <Gather>) is now
    what captures customer speech."""
    webhook_url, _, recording_url, _closing_grace_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=webhook_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    raw = await redis.get(_redis_key(token))
    if raw is None:
        return _twiml_speak_and_hangup("say", "This test session has expired. Goodbye.")

    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])
    language_code = state.get("language_code", FALLBACK_LANGUAGE)

    if settings.twilio_voice_transport == "media_stream":
        # P2: hand off to the persistent bidirectional Media Stream —
        # everything else (greeting, in_progress/answered_at, listening for
        # customer turns) happens inside the WebSocket handler once Twilio's
        # `start` event arrives (transport/twilio_media_stream.py), not
        # here. This webhook's only job in this mode is producing the
        # <Connect><Stream> TwiML with a signed session token.
        from app.modules.live_call.transport.media_tokens import create_media_session_token
        from app.modules.live_call.transport.twilio_media_stream import build_media_stream_twiml

        session_token = create_media_session_token(
            secret=settings.session_secret, call_session_id=call_session_id, workspace_id=workspace_id,
            twilio_call_sid=form.get("CallSid", ""), redis_state_token=token,
        )
        ws_url = f"{settings.effective_media_stream_ws_base_url}/api/v1/live-call/ws/twilio/media/{session_token}"
        return build_media_stream_twiml(ws_url)

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

    # Normally already synthesized during dialing (start_live_test_call) —
    # this only re-synthesizes as a defensive fallback (e.g. redis state
    # written by an older code path mid-deploy).
    greeting_kind = state.get("greeting_kind")
    greeting_content = state.get("greeting_content")
    if greeting_kind and greeting_content:
        kind, content = greeting_kind, greeting_content
    else:
        kind, content = await _speak(greeting, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
    return _twiml_speak_and_record(kind, content, action_url=recording_url)


async def handle_recording_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> str:
    """Handles every turn after the greeting: downloads what <Record> just
    captured, transcribes it via Sarvam STT, gets the next reply, and either
    continues (speak + record again) or ends the call (speak + hangup).

    Instrumented (CallLatencyMetric, is_simulated=False) as the real-time
    migration's Phase 1 baseline — see docs/REALTIME_VOICE_MIGRATION_AUDIT.md.
    Every stage here is a blocking, sequential network round-trip; this is
    exactly what real numbers from this instrumentation quantify,
    turn_total_backend most of all."""
    turn_t0 = time.perf_counter()
    _, _, recording_url, closing_grace_url = _webhook_urls(settings, token)
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
    stt_metadata: dict = {}
    fetch_recording_ms: int | None = None
    stt_transcribe_ms: int | None = None
    if twilio_recording_url and recording_duration > 0:
        try:
            t0 = time.perf_counter()
            audio_bytes = await fetch_recording(
                account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, recording_url=twilio_recording_url
            )
            fetch_recording_ms = int((time.perf_counter() - t0) * 1000)
            stt = SarvamSTT(api_key=settings.sarvam_api_key or settings.sarvam_tts_api_key)
            t0 = time.perf_counter()
            transcript = await stt.transcribe(audio_bytes=audio_bytes, language_code=language_code)
            stt_transcribe_ms = int((time.perf_counter() - t0) * 1000)
            speech_result = transcript.text
            stt_metadata = {
                "stt_detected_language_code": transcript.detected_language_code,
                "stt_language_probability": transcript.language_probability,
                "stt_requested_language_code": language_code,
            }
        except Exception:  # noqa: BLE001 — same reasoning as _speak: never kill the call over a transcription hiccup (covers STTNotConfiguredError too)
            speech_result = ""

    async with workspace_scoped_session(workspace_id) as db:
        if fetch_recording_ms is not None:
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="twilio_recording_fetch", duration_ms=fetch_recording_ms, provider="twilio")
        if stt_transcribe_ms is not None:
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="stt_transcribe", duration_ms=stt_transcribe_ms, provider="sarvam")

        if not speech_result:
            closing = "We seem to have lost your response. Thank you for your time, goodbye."
            await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=closing)
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id,
                call_status="abandoned", end_reason="timeout", had_exchange=state["agent_turns"] > 1,
                language_code=language_code,
            )
            await redis.delete(_redis_key(token))
            kind, content = await _speak(closing, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
            return _twiml_speak_and_hangup(kind, content)

        await _persist_turn(
            db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="customer",
            text=speech_result, metadata=stt_metadata,
        )

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
            agent_id=call_session.agent_id if call_session else None,
            business_identity=state.get("business_identity", ""), recent_turns=state.get("recent_turns", [])[-6:],
            engine_mode=settings.conversation_engine_mode, response_mode=settings.llm_response_mode,
        )
        # jkr_conversation's own internal stage breakdown (domain_vocabulary,
        # extraction, planning, rag if it ran, generation) — process_turn
        # already measures this; just persisting it here, for free.
        for stage, duration_ms in result.latency_ms.items():
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage=f"engine_{stage}", duration_ms=duration_ms, provider="jkr_conversation")

        tool_failed = await _execute_tool_calls(
            db, workspace_id=workspace_id, call_session_id=call_session_id, call_session=call_session, result=result,
        )

        if call_session is not None:
            call_session.state = result.state

        reply = _tool_failure_reply(language_code) if tool_failed else result.reply_text
        state["recent_turns"].append({"speaker": "customer", "text": speech_result})
        state["recent_turns"].append({"speaker": "agent", "text": reply})
        state["agent_turns"] += 1
        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=reply)

        # live_call has no real warm-transfer capability yet, so a human-
        # handoff decision closes the call here too — unlike Test Lab, which
        # keeps the session open after an acknowledged handoff.
        force_close = result.call_should_end or result.planner_action == "HUMAN_HANDOFF"

        if force_close:
            # Never finalize the instant a closing is decided — the closing
            # audio must fully play, then a short grace window gives the
            # customer a real chance to speak before the call actually ends
            # (this is the direct fix for the abrupt-hangup bug: previously
            # this hung up immediately after speaking, so a customer reply
            # captured nothing). handle_closing_grace_webhook does the real
            # finalize (on silence) or resumes the conversation (on speech).
            state["pending_end_reason"] = _end_reason_for(result)
            await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)
            t0 = time.perf_counter()
            kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="tts_synthesize", duration_ms=int((time.perf_counter() - t0) * 1000), provider="sarvam")
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="turn_total_backend", duration_ms=int((time.perf_counter() - turn_t0) * 1000))
            return _twiml_speak_then_grace_listen(kind, content, action_url=closing_grace_url)

        await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)
        t0 = time.perf_counter()
        kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
        await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="tts_synthesize", duration_ms=int((time.perf_counter() - t0) * 1000), provider="sarvam")
        await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage="turn_total_backend", duration_ms=int((time.perf_counter() - turn_t0) * 1000))
        return _twiml_speak_and_record(kind, content, action_url=recording_url)


async def handle_closing_grace_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> str:
    """Handles what happened during the short listening window after a
    closing line played. Silence means the call genuinely ends now — the
    closing already played in full, so this is the real finalize. Real
    speech means the customer had more to say: for a do-not-call/wrong-
    number closing, that never resumes the conversation (same "the LLM
    can't override do-not-call" guarantee extended to this mechanism — it's
    acknowledged, but the call still ends); for every other closing reason,
    it's fed back through process_turn on a reopened conversation state,
    exactly like any other turn, and may itself end in another closing
    (handled by recursing into this same grace flow again)."""
    _, _, recording_url, closing_grace_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=closing_grace_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    raw = await redis.get(_redis_key(token))
    if raw is None:
        return _twiml_hangup_only()

    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])
    language_code = state.get("language_code", FALLBACK_LANGUAGE)

    twilio_recording_url = form.get("RecordingUrl") or ""
    recording_duration = int(form.get("RecordingDuration") or "0")

    speech_result = ""
    stt_metadata: dict = {}
    if twilio_recording_url and recording_duration > 0:
        try:
            audio_bytes = await fetch_recording(
                account_sid=settings.twilio_account_sid, auth_token=settings.twilio_auth_token, recording_url=twilio_recording_url
            )
            stt = SarvamSTT(api_key=settings.sarvam_api_key or settings.sarvam_tts_api_key)
            transcript = await stt.transcribe(audio_bytes=audio_bytes, language_code=language_code)
            speech_result = transcript.text
            stt_metadata = {
                "stt_detected_language_code": transcript.detected_language_code,
                "stt_language_probability": transcript.language_probability,
                "stt_requested_language_code": language_code,
            }
        except Exception:  # noqa: BLE001 — same reasoning as _speak: never kill the call over a transcription hiccup
            speech_result = ""

    async with workspace_scoped_session(workspace_id) as db:
        if not speech_result:
            # Silence within the grace window — the closing already fully
            # played; now really end the call.
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                end_reason=state.get("pending_end_reason", "completed"), had_exchange=True, language_code=language_code,
            )
            await redis.delete(_redis_key(token))
            return _twiml_hangup_only()

        session_result = await db.execute(select(CallSession).where(CallSession.id == call_session_id))
        call_session = session_result.scalar_one_or_none()
        conversation_state = dict(call_session.state) if call_session is not None and call_session.state else {}

        await _persist_turn(
            db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="customer",
            text=speech_result, metadata=stt_metadata,
        )

        if conversation_state.get("do_not_call") or conversation_state.get("wrong_number"):
            # Compliance-critical: speaking up during the grace window after
            # a do-not-call/wrong-number closing never undoes it.
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                end_reason=state.get("pending_end_reason", "completed"), had_exchange=True, language_code=language_code,
            )
            await redis.delete(_redis_key(token))
            return _twiml_hangup_only()

        # A genuine resume — reopen the conversation state and feed this
        # utterance back through the shared engine like any other turn.
        conversation_state = _reopen_conversation_state(conversation_state)
        policy_snapshot = ConversationPolicySnapshot(**state.get("policy", {}))

        result = await process_turn(
            db, workspace_id=workspace_id, call_session_id=call_session_id, state=conversation_state,
            customer_utterance=speech_result, conversation_policy=policy_snapshot,
            agent_id=call_session.agent_id if call_session else None,
            business_identity=state.get("business_identity", ""), recent_turns=state.get("recent_turns", [])[-6:],
            engine_mode=settings.conversation_engine_mode, response_mode=settings.llm_response_mode,
        )
        # jkr_conversation's own internal stage breakdown (domain_vocabulary,
        # extraction, planning, rag if it ran, generation) — process_turn
        # already measures this; just persisting it here, for free.
        for stage, duration_ms in result.latency_ms.items():
            await _record_latency(db, workspace_id=workspace_id, call_session_id=call_session_id, stage=f"engine_{stage}", duration_ms=duration_ms, provider="jkr_conversation")

        tool_failed = await _execute_tool_calls(
            db, workspace_id=workspace_id, call_session_id=call_session_id, call_session=call_session, result=result,
        )

        if call_session is not None:
            call_session.state = result.state

        reply = _tool_failure_reply(language_code) if tool_failed else result.reply_text
        state["recent_turns"].append({"speaker": "customer", "text": speech_result})
        state["recent_turns"].append({"speaker": "agent", "text": reply})
        state["agent_turns"] += 1
        await _persist_turn(db, workspace_id=workspace_id, call_session_id=call_session_id, state=state, speaker="agent", text=reply)

        force_close = result.call_should_end or result.planner_action == "HUMAN_HANDOFF"
        if force_close:
            state["pending_end_reason"] = _end_reason_for(result)
            await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)
            kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
            return _twiml_speak_then_grace_listen(kind, content, action_url=closing_grace_url)

        await redis.set(_redis_key(token), json.dumps(state), ex=REDIS_TTL_SECONDS)
        kind, content = await _speak(reply, language_code=language_code, settings=settings, redis=redis, speaker=state.get("tts_speaker"), pace=state.get("tts_pace", 1.0))
        return _twiml_speak_and_record(kind, content, action_url=recording_url)


async def handle_status_webhook(*, token: str, form: dict[str, str], signature: str | None, settings: Settings, redis: Any) -> None:
    """Closes out the call record for outcomes the earlier webhooks never see
    at all — no-answer/busy/failed/the customer hanging up before Twilio ever
    reaches <Record>. A completed call is normally already finalized by
    handle_recording_webhook/handle_closing_grace_webhook, so the "completed"
    branch below is a no-op then (guarded by _finalize_call's own idempotency
    check) — it only does real work if Twilio's "completed" status fires
    without ever reaching those webhooks (e.g. the customer hangs up their
    phone entirely during the grace window instead of staying silent or
    speaking), which would otherwise leave that session stuck in_progress
    forever."""
    _, status_callback_url, _recording_url, _closing_grace_url = _webhook_urls(settings, token)
    if not signature or not validate_twilio_signature(auth_token=settings.twilio_auth_token, url=status_callback_url, params=form, signature=signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")

    call_status = form.get("CallStatus", "")
    raw = await redis.get(_redis_key(token))
    if raw is None:
        return
    state = json.loads(raw)
    workspace_id = uuid.UUID(state["workspace_id"])
    call_session_id = uuid.UUID(state["call_session_id"])

    if call_status in {"in-progress", "ringing", "queued"}:
        return

    if call_status == "completed":
        async with workspace_scoped_session(workspace_id) as db:
            await _finalize_call(
                db, workspace_id=workspace_id, call_session_id=call_session_id, call_status="completed",
                end_reason=state.get("pending_end_reason", "completed"), had_exchange=state["agent_turns"] > 1,
                language_code=state.get("language_code", FALLBACK_LANGUAGE),
            )
        await redis.delete(_redis_key(token))
        return

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
