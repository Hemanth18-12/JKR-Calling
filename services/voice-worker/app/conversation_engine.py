"""Orchestrates TurnManager + MockLLM + SpokenResponseFormatter + persistence
for one call. This is the text-simulated stand-in for the real-time pipeline
in docs/VOICE_ARCHITECTURE.md §1 — every stage after the STT boundary is real
logic, only the transport is simulated (docs/DECISIONS/0002-voice-runtime.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

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
from jkr_db.models.calls import InterruptionEvent as InterruptionEventModel
from jkr_db.tools_engine import ToolNotDefinedError, ToolNotEnabledError, execute_tool
from jkr_messaging import enqueue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_retrieval import first_sentence, looks_like_a_question, search_knowledge
from app.providers.mock import MockLLM, MockSTT, MockTTS
from app.session_registry import CallRuntime
from app.session_registry import discard as registry_discard
from app.session_registry import get as registry_get
from app.session_registry import put as registry_put
from app.spoken_formatter import SpokenResponseFormatter
from app.turn_manager import InterruptionClassification, TurnManager, estimate_speaking_duration_ms

# Spec §16: never invent pricing/medical/eligibility/etc. — if the customer
# asks something knowledge-lookup-shaped and nothing approved matches well
# enough, say so and defer to a human rather than guessing.
NO_MATCH_FALLBACK = {
    "te": "ఆ విషయం గురించి ఖచ్చితంగా చెప్పలేను అండి, మా టీమ్ మీకు వివరాలు తెలియజేస్తుంది.",
    "hi": "उस बारे में मैं अभी पूरी तरह नहीं बता पाऊँगा, हमारी टीम आपको बताएगी।",
    "en": "I'm not fully sure about that — our team will confirm the details with you.",
}

# Deliberately small keyword list, not real intent detection — mirrors
# NO_MATCH_FALLBACK's approach. HandoffReason.CUSTOMER_REQUESTED (spec §18).
HUMAN_HANDOFF_TRIGGERS = [
    "talk to a person", "talk to someone", "real person", "human agent", "speak to a manager",
    "మనిషితో మాట్లాడాలి", "మనిషిని కలపండి", "इंसान से बात", "किसी आदमी से बात करनी है",
]

HUMAN_HANDOFF_ACK = {
    "te": "సరే అండి, నేను మా టీమ్ మెంబర్‌ని కలుపుతున్నాను, ఒక్క నిమిషం.",
    "hi": "ठीक है, मैं आपको हमारी टीम के किसी सदस्य से जोड़ रहा हूँ, एक मिनट रुकिए।",
    "en": "Sure, let me connect you with a member of our team — one moment.",
}


def _wants_human_handoff(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in HUMAN_HANDOFF_TRIGGERS)

_stt = MockSTT()
_tts = MockTTS()


@dataclass
class TurnOut:
    turn_ref: str
    speaker: str
    text: str
    is_interrupted: bool = False
    # Simulated speaking duration (docs/DECISIONS/0002) — a caller that isn't
    # a human waiting for TTS audio (i.e. campaign-worker's auto-play "mock
    # customer") needs this to know how long to wait before replying, or
    # every reply arrives near-instantly and TurnManager correctly classifies
    # it as a false-positive filler (elapsed_ms < min_interruption_ms), never
    # advancing the script. See services/campaign-worker/app/dialer.py.
    estimated_duration_ms: int | None = None


@dataclass
class UserTurnOut:
    user_turn: TurnOut
    interruption_classification: str
    stop_latency_ms: int | None
    agent_turn: TurnOut | None
    conversation_state: dict
    call_status: str


def _fill_greeting(text: str, contact_name: str | None) -> str:
    if contact_name:
        return text.replace("{name}", contact_name)
    return text.replace("{name} ", "").replace("{name}", "")


async def _record_latency(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, stage: str, duration_ms: int, provider: str = "mock") -> None:
    db.add(
        CallLatencyMetric(
            workspace_id=workspace_id,
            call_session_id=call_id,
            provider=provider,
            stage=stage,
            duration_ms=duration_ms,
            is_simulated=True,
            recorded_at=datetime.now(UTC),
        )
    )


async def _persist_agent_turn(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, sequence_index: int, turn_ref: str, text: str, language: str
) -> None:
    now = datetime.now(UTC)
    db.add(
        CallTurn(
            workspace_id=workspace_id,
            call_session_id=call_id,
            turn_ref=turn_ref,
            sequence_index=sequence_index,
            speaker="agent",
            text=text,
            language=language,
            confidence=None,
            is_interrupted=False,
            started_at=now,
            ended_at=now,
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_id, event_type="agent_turn", payload={"text": text}))
    # Simulated pipeline stage latencies — is_simulated=True throughout;
    # see docs/DECISIONS/0002-voice-runtime.md.
    await _record_latency(db, workspace_id=workspace_id, call_id=call_id, stage="llm_first_token", duration_ms=180)
    await _record_latency(db, workspace_id=workspace_id, call_id=call_id, stage="tts_first_audio", duration_ms=120)


async def start_session(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    contact_name: str | None = None,
    campaign_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
) -> dict:
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise ValueError("Agent not found")

    version_id = agent.published_version_id
    version_result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id, AgentVersion.workspace_id == workspace_id)
        .order_by((AgentVersion.id == version_id).desc(), AgentVersion.version_number.desc())
    )
    version = version_result.scalars().first()
    if version is None:
        raise ValueError("Agent has no versions")

    policy_result = await db.execute(select(ConversationPolicy).where(ConversationPolicy.agent_version_id == version.id))
    policy = policy_result.scalar_one_or_none()
    voice_result = await db.execute(select(VoicePersona).where(VoicePersona.agent_version_id == version.id))
    voice = voice_result.scalar_one_or_none()

    language = voice.language if voice else agent.primary_language

    conversation_state = {
        "objective": version.primary_objective,
        "language": language,
        "intent": None,
        "sentiment": "neutral",
        "known_fields": {},
        "missing_fields": [s["field"] for s in MockLLM(version.primary_objective, language).script()],
        "uncertain_fields": [],
        "risk_flags": [],
        "customer_requested_human": False,
        "do_not_call": False,
        "next_best_action": "ask_question",
        "objective_status": "in_progress",
        "asked_count": 0,
        "awaiting_field": None,
    }

    call_session = CallSession(
        workspace_id=workspace_id,
        direction="outbound",
        status="in_progress",
        agent_id=agent.id,
        agent_version_id=version.id,
        contact_id=contact_id,
        campaign_id=campaign_id,
        idempotency_key=f"test-{uuid.uuid4()}",
        language=language,
        state=conversation_state,
        started_at=datetime.now(UTC),
        answered_at=datetime.now(UTC),
        is_mock=True,
        disclosure_confirmed=True,
    )
    db.add(call_session)
    await db.flush()

    db.add(
        CallParticipant(
            workspace_id=workspace_id, call_session_id=call_session.id, role="agent",
            display_name=agent.name, joined_at=datetime.now(UTC),
        )
    )
    db.add(
        CallParticipant(
            workspace_id=workspace_id, call_session_id=call_session.id, role="customer",
            display_name=contact_name or "Test Customer", joined_at=datetime.now(UTC),
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session.id, event_type="call_started", payload={}))
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_session.id, event_type="disclosure_confirmed", payload={}))

    turn_manager = TurnManager(
        call_id=call_session.id,
        accidental_interruption_phrases=policy.accidental_interruption_phrases if policy else [],
        min_interruption_ms=policy.min_interruption_ms if policy else 250,
    )
    llm = MockLLM(objective=version.primary_objective, language=language)
    registry_put(
        call_session.id,
        CallRuntime(
            turn_manager=turn_manager, llm=llm, language=language,
            human_transfer_enabled=policy.human_transfer_enabled if policy else True,
        ),
    )

    greeting = _fill_greeting(version.greeting_text, contact_name)
    formatter = SpokenResponseFormatter(language=language, max_sentences=policy.max_response_sentences if policy else 3)
    formatted = formatter.format(greeting, prepend_acknowledgement=False)

    turn_record = turn_manager.start_agent_turn(formatted.text)
    await _persist_agent_turn(
        db, workspace_id=workspace_id, call_id=call_session.id, sequence_index=0,
        turn_ref=turn_record.turn_ref, text=formatted.text, language=language,
    )
    await db.flush()

    return {
        "call_id": call_session.id,
        "status": call_session.status,
        "language": language,
        "greeting": formatted.text,
        "estimated_duration_ms": estimate_speaking_duration_ms(formatted.text),
        "conversation_state": conversation_state,
    }


async def submit_user_turn(
    db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, text: str
) -> UserTurnOut:
    session_result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
    )
    call_session = session_result.scalar_one_or_none()
    if call_session is None:
        raise ValueError("Call session not found")
    if call_session.status != "in_progress":
        raise ValueError("Call is not in progress")

    runtime = registry_get(call_id)
    if runtime is None:
        # Worker restarted mid-call — see session_registry.py docstring.
        raise ValueError("Call runtime not found (voice-worker may have restarted); end and start a new test call")

    state = dict(call_session.state)

    transcript = await _stt.transcribe(audio_or_text=text, language=runtime.language)

    classification = runtime.turn_manager.handle_user_utterance(transcript.text)

    # Count of existing turns drives sequence_index and turn_ref numbering.
    existing_turns = await db.execute(select(CallTurn).where(CallTurn.call_session_id == call_id))
    sequence_index = len(existing_turns.scalars().all())

    now = datetime.now(UTC)
    user_turn_ref = runtime.turn_manager.next_turn_ref("user")
    db.add(
        CallTurn(
            workspace_id=workspace_id, call_session_id=call_id, turn_ref=user_turn_ref,
            sequence_index=sequence_index, speaker="customer", text=transcript.text,
            language=runtime.language, confidence=transcript.confidence,
            is_interrupted=False, started_at=now, ended_at=now,
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_id, event_type="user_turn", payload={"text": transcript.text}))
    await _record_latency(db, workspace_id=workspace_id, call_id=call_id, stage="stt_final", duration_ms=90)

    stop_latency_ms = classification.stop_latency_ms
    if classification.classification != InterruptionClassification.NONE:
        db.add(
            InterruptionEventModel(
                workspace_id=workspace_id, call_session_id=call_id,
                turn_ref=classification.cancelled_sequence_id, classification=classification.classification.value,
                stop_latency_ms=stop_latency_ms, occurred_at=now, details={"user_text": transcript.text},
            )
        )
        if classification.classification == InterruptionClassification.MEANINGFUL and classification.cancelled_sequence_id:
            cancelled_turn = await db.execute(
                select(CallTurn)
                .where(CallTurn.call_session_id == call_id, CallTurn.speaker == "agent")
                .order_by(CallTurn.sequence_index.desc())
                .limit(1)
            )
            row = cancelled_turn.scalar_one_or_none()
            if row is not None:
                row.is_interrupted = True
            await _record_latency(
                db, workspace_id=workspace_id, call_id=call_id, stage="interrupt_stop", duration_ms=stop_latency_ms or 0
            )
            runtime.turn_manager.mark_recovered()

    if classification.classification == InterruptionClassification.FALSE_POSITIVE:
        # Spec §11: a false interruption (short filler like "hmm"/"అవును")
        # must NOT cancel or advance past the agent's current turn — the
        # agent is still, logically, mid-utterance. No new agent turn, no
        # script advancement; just log that the customer said something.
        await db.flush()
        return UserTurnOut(
            user_turn=TurnOut(turn_ref=user_turn_ref, speaker="customer", text=transcript.text),
            interruption_classification=classification.classification.value,
            stop_latency_ms=stop_latency_ms,
            agent_turn=None,
            conversation_state=state,
            call_status=call_session.status,
        )

    formatter = SpokenResponseFormatter(language=runtime.language, max_sentences=3)

    if (
        runtime.human_transfer_enabled
        and not state.get("customer_requested_human")
        and _wants_human_handoff(transcript.text)
    ):
        # Spec §18: an explicit request for a human takes priority over
        # script progression — no more scripted questions, hand off instead.
        state["customer_requested_human"] = True
        state["next_best_action"] = "human_handoff"
        state["objective_status"] = "needs_human"

        try:
            await execute_tool(
                db, workspace_id=workspace_id, tool_name="create_human_callback",
                tool_input={
                    "reason": "customer_requested",
                    "packet": {"known_fields": state["known_fields"], "last_customer_utterance": transcript.text},
                },
                idempotency_key=f"call-{call_id}-human_callback", call_session_id=call_id,
                agent_version_id=call_session.agent_version_id,
            )
        except (ToolNotDefinedError, ToolNotEnabledError):
            pass  # tool not configured for this workspace — the spoken handoff still happens, just unaudited

        lang_prefix = runtime.language.split("-")[0] if runtime.language.split("-")[0] in ("te", "hi") else "en"
        formatted = formatter.format(HUMAN_HANDOFF_ACK.get(lang_prefix, HUMAN_HANDOFF_ACK["en"]), prepend_acknowledgement=False)

        agent_sequence_index = sequence_index + 1
        turn_record = runtime.turn_manager.start_agent_turn(formatted.text)
        await _persist_agent_turn(
            db, workspace_id=workspace_id, call_id=call_id, sequence_index=agent_sequence_index,
            turn_ref=turn_record.turn_ref, text=formatted.text, language=runtime.language,
        )
        call_session.state = state
        await db.flush()
        return UserTurnOut(
            user_turn=TurnOut(turn_ref=user_turn_ref, speaker="customer", text=transcript.text),
            interruption_classification=classification.classification.value,
            stop_latency_ms=stop_latency_ms,
            agent_turn=TurnOut(
                turn_ref=turn_record.turn_ref, speaker="agent", text=formatted.text,
                estimated_duration_ms=estimate_speaking_duration_ms(formatted.text),
            ),
            conversation_state=state,
            call_status=call_session.status,
        )

    # Advance conversation state.
    awaiting_field = state.get("awaiting_field")
    if awaiting_field is None and state["asked_count"] == 0:
        # First customer utterance after the greeting. The greeting's own
        # "is now a good time?" beat already prompted them, so whatever they
        # volunteer here answers the FIRST script question implicitly (spec
        # §9's dental example has the customer's reason arrive unprompted
        # the same way) — attribute it directly rather than asking a
        # redundant, already-answered question right back at them.
        first_step = runtime.llm.next_question(asked_count=0)
        if first_step is not None:
            awaiting_field = first_step["field"]
            state["asked_count"] = 1

    if awaiting_field:
        state["known_fields"][awaiting_field] = transcript.text
        state["missing_fields"] = [f for f in state["missing_fields"] if f != awaiting_field]

    next_step = runtime.llm.next_question(asked_count=state["asked_count"])
    agent_turn_out: TurnOut | None = None
    call_status = call_session.status

    # Spec §16 knowledge answer policy: if the customer asked something
    # knowledge-shaped, answer from approved knowledge, or say so and defer
    # to a human — never guess. Checked against the raw utterance, not the
    # value just captured into known_fields (a factual question and a
    # scripted-field answer are different things even in the same turn).
    knowledge_prefix = ""
    if looks_like_a_question(transcript.text):
        lang_prefix = runtime.language.split("-")[0] if runtime.language.split("-")[0] in ("te", "hi") else "en"
        match_text, above_threshold = await search_knowledge(
            db, workspace_id=workspace_id, query=transcript.text, call_session_id=call_id
        )
        db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_id, event_type="knowledge_lookup", payload={"query": transcript.text, "matched": above_threshold}))
        if above_threshold and match_text:
            snippet = first_sentence(match_text)
            knowledge_prefix = snippet + ("" if snippet.endswith((".", "!", "?")) else ".") + " "
        else:
            knowledge_prefix = NO_MATCH_FALLBACK.get(lang_prefix, NO_MATCH_FALLBACK["en"]) + " "

    if next_step is not None:
        state["asked_count"] += 1
        state["awaiting_field"] = next_step["field"]
        state["next_best_action"] = "ask_question"
        raw = knowledge_prefix + runtime.llm.question_text(next_step)
        formatted = formatter.format(raw, prepend_acknowledgement=True)
    else:
        state["awaiting_field"] = None
        state["objective_status"] = "completed"
        state["next_best_action"] = "close_conversation"
        raw = knowledge_prefix + runtime.llm.closing_text()
        formatted = formatter.format(raw, prepend_acknowledgement=False)

        if state["objective"] == "book_appointment" and call_session.contact_id is not None:
            # Spec §33 demo beat 13-15: completing the booking script fields
            # actually books the appointment, not just marks the script done.
            try:
                execution = await execute_tool(
                    db, workspace_id=workspace_id, tool_name="book_appointment", tool_input=state["known_fields"],
                    idempotency_key=f"call-{call_id}-book_appointment", call_session_id=call_id, contact_id=call_session.contact_id,
                    agent_version_id=call_session.agent_version_id,
                )
                if execution.status == "succeeded":
                    state["tool_results"] = {"book_appointment": execution.output}
            except (ToolNotDefinedError, ToolNotEnabledError):
                pass  # tool not configured for this workspace — the call still closes normally, just unbooked

    agent_sequence_index = sequence_index + 1
    turn_record = runtime.turn_manager.start_agent_turn(formatted.text)
    await _persist_agent_turn(
        db, workspace_id=workspace_id, call_id=call_id, sequence_index=agent_sequence_index,
        turn_ref=turn_record.turn_ref, text=formatted.text, language=runtime.language,
    )
    agent_turn_out = TurnOut(
        turn_ref=turn_record.turn_ref, speaker="agent", text=formatted.text,
        estimated_duration_ms=estimate_speaking_duration_ms(formatted.text),
    )

    call_session.state = state
    await db.flush()

    return UserTurnOut(
        user_turn=TurnOut(turn_ref=user_turn_ref, speaker="customer", text=transcript.text),
        interruption_classification=classification.classification.value,
        stop_latency_ms=stop_latency_ms,
        agent_turn=agent_turn_out,
        conversation_state=state,
        call_status=call_status,
    )


async def end_session(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, end_reason: str = "agent_ended") -> dict:
    session_result = await db.execute(
        select(CallSession).where(CallSession.id == call_id, CallSession.workspace_id == workspace_id)
    )
    call_session = session_result.scalar_one_or_none()
    if call_session is None:
        raise ValueError("Call session not found")

    turns_result = await db.execute(
        select(CallTurn).where(CallTurn.call_session_id == call_id).order_by(CallTurn.sequence_index)
    )
    turns = list(turns_result.scalars().all())
    full_text = "\n".join(f"[{t.speaker}] {t.text}" for t in turns)

    now = datetime.now(UTC)
    call_session.status = "completed"
    call_session.end_reason = end_reason
    call_session.ended_at = now
    if call_session.started_at:
        call_session.duration_seconds = int((now - call_session.started_at).total_seconds())

    db.add(CallTranscript(workspace_id=workspace_id, call_session_id=call_id, full_text=full_text, language=call_session.language, is_final=True))

    state = call_session.state or {}
    objective_status = state.get("objective_status", "in_progress")
    objective = state.get("objective", "")
    known_fields = state.get("known_fields", {})

    if objective_status == "completed" and objective == "book_appointment":
        category = "appointment_booked"
        lead_score = "hot"
    elif objective_status == "completed" and known_fields:
        category = "qualified"
        lead_score = "warm"
    elif known_fields:
        category = "interested"
        lead_score = "warm"
    else:
        category = "unreachable"
        lead_score = "not_qualified"

    db.add(
        CallOutcome(
            workspace_id=workspace_id, call_session_id=call_id, category=category, lead_score=lead_score,
            score_reasons=[f"{k}: {v}" for k, v in known_fields.items()],
            objective_status=objective_status,
            notes="Generated by voice-worker's mock conversation engine — Phase 4 replaces this with LLM-based post-call intelligence.",
        )
    )
    db.add(
        CallSummary(
            workspace_id=workspace_id, call_session_id=call_id,
            summary_text=(f"Objective: {objective} ({objective_status}). " + "; ".join(f"{k}: {v}" for k, v in known_fields.items()))
            or "No information collected.",
            generated_by="mock_llm",
        )
    )
    db.add(CallEvent(workspace_id=workspace_id, call_session_id=call_id, event_type="call_ended", payload={"reason": end_reason}))

    # Real usage tracking (docs/IMPLEMENTATION_CHECKLIST.md Phase 9) — every
    # completed call logs its actual duration as billable telephony seconds,
    # regardless of mock-vs-real provider. Mock calls are free (cost_paise
    # stays 0, per the campaign safety gate's budget check), but the *usage*
    # itself is real, not simulated — this is what a real provider bill
    # would be metered against once one is configured.
    if call_session.duration_seconds is not None:
        db.add(
            UsageEvent(
                workspace_id=workspace_id, call_session_id=call_id, event_type="telephony_seconds",
                quantity=call_session.duration_seconds, unit="seconds", occurred_at=now,
            )
        )

    await db.flush()
    registry_discard(call_id)

    # Off the request path — a slow/failed pipeline run must never delay
    # "call ended" from reaching the caller. Enqueued here (not by whichever
    # service asked us to end the call) so it fires identically whether a
    # human ended it via services/api's Test Lab proxy or campaign-worker's
    # dialer ended it directly — see services/intelligence-worker/app/pipeline.py.
    enqueue("run_post_call_pipeline", args=(str(call_id), str(workspace_id)), queue_name="intelligence")

    return {"call_id": call_id, "status": call_session.status, "outcome_category": category, "lead_score": lead_score}
