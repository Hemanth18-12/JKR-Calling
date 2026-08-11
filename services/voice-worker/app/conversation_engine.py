"""Orchestrates TurnManager + the shared jkr_conversation engine + persistence
for one call. This is the text-simulated stand-in for the real-time pipeline
in docs/VOICE_ARCHITECTURE.md §1 — every stage after the STT boundary is real
logic, only the transport is simulated (docs/DECISIONS/0002-voice-runtime.md).

Conversation intelligence (field extraction, RAG, next-action planning,
response generation) lives in jkr_conversation and is shared verbatim with
the real Twilio call path (services/api/app/modules/live_call/service.py) —
this module's job is transport/turn-taking (TurnManager, persistence,
tool execution), never business conversation reasoning itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from jkr_conversation.engine import process_turn
from jkr_conversation.formatter import SpokenResponseFormatter
from jkr_conversation.schemas import ConversationPolicySnapshot
from jkr_conversation.state import classify_provisional_outcome, new_conversation_state
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

from app.providers.mock import MockSTT, MockTTS
from app.session_registry import CallRuntime
from app.session_registry import discard as registry_discard
from app.session_registry import get as registry_get
from app.session_registry import put as registry_put
from app.turn_manager import InterruptionClassification, TurnManager, estimate_speaking_duration_ms

_stt = MockSTT()
_tts = MockTTS()


def _policy_snapshot(policy: ConversationPolicy | None) -> ConversationPolicySnapshot:
    if policy is None:
        return ConversationPolicySnapshot()
    return ConversationPolicySnapshot(
        max_response_sentences=policy.max_response_sentences,
        human_transfer_enabled=policy.human_transfer_enabled,
        do_not_call_behavior=policy.do_not_call_behavior,
        wrong_number_behavior=policy.wrong_number_behavior,
        clarification_behavior=policy.clarification_behavior,
        confirmation_behavior=policy.confirmation_behavior,
        max_turns=policy.max_turns,
        max_call_duration_seconds=policy.max_call_duration_seconds,
        accidental_interruption_phrases=policy.accidental_interruption_phrases,
    )


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
    conversation_state = new_conversation_state(objective=version.primary_objective, language=language)

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
    registry_put(
        call_session.id,
        CallRuntime(
            turn_manager=turn_manager, language=language,
            human_transfer_enabled=policy.human_transfer_enabled if policy else True,
            policy=_policy_snapshot(policy), business_identity=agent.business_identity,
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

    # Everything from here down — field extraction, knowledge retrieval,
    # next-action planning, response generation — is the shared engine, the
    # exact same code path the real Twilio call path uses (see
    # services/api/app/modules/live_call/service.py). This module only
    # handles transport/turn-taking and persistence, never conversation
    # reasoning itself.
    result = await process_turn(
        db, workspace_id=workspace_id, call_session_id=call_id, state=state,
        customer_utterance=transcript.text, conversation_policy=runtime.policy,
        business_identity=runtime.business_identity, transcript_confidence=transcript.confidence,
        agent_id=call_session.agent_id, now=now,
    )
    state = result.state

    for tool_call in result.tool_calls_requested:
        try:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name=tool_call.tool_name, tool_input=tool_call.tool_input,
                idempotency_key=f"call-{call_id}-{tool_call.idempotency_suffix}", call_session_id=call_id,
                contact_id=call_session.contact_id, agent_version_id=call_session.agent_version_id,
            )
            if execution.status == "succeeded":
                state.setdefault("tool_results", {})[tool_call.tool_name] = execution.output
        except (ToolNotDefinedError, ToolNotEnabledError):
            pass  # tool not configured for this workspace — the call still proceeds, matching prior behavior

    agent_sequence_index = sequence_index + 1
    turn_record = runtime.turn_manager.start_agent_turn(result.reply_text)
    await _persist_agent_turn(
        db, workspace_id=workspace_id, call_id=call_id, sequence_index=agent_sequence_index,
        turn_ref=turn_record.turn_ref, text=result.reply_text, language=runtime.language,
    )
    agent_turn_out = TurnOut(
        turn_ref=turn_record.turn_ref, speaker="agent", text=result.reply_text,
        estimated_duration_ms=estimate_speaking_duration_ms(result.reply_text),
    )

    call_session.state = state
    await db.flush()

    return UserTurnOut(
        user_turn=TurnOut(turn_ref=user_turn_ref, speaker="customer", text=transcript.text),
        interruption_classification=classification.classification.value,
        stop_latency_ms=stop_latency_ms,
        agent_turn=agent_turn_out,
        conversation_state=state,
        call_status=call_session.status,
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
    category, lead_score = classify_provisional_outcome(state)

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
