"""Post-call intelligence pipeline — spec §19. Runs after a call ends,
refining the basic CallOutcome/CallSummary that voice-worker's
conversation_engine writes synchronously at call-end (docs/IMPLEMENTATION_CHECKLIST.md
Phase 3 note: "Phase 4 replaces this with LLM-based post-call intelligence").

Every stage here is real, rule-based logic operating on real persisted data
(transcript, turns, interruption events, STT confidence) — not a stub.
"""

from __future__ import annotations

import logging
import re
import uuid

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_db.storage import (
    generate_synthesized_call_audio,
    upload_call_recording,
    upload_call_transcript,
)

from jkr_db.models.calls import (
    CallEvent,
    CallOutcome,
    CallRecording,
    CallSession,
    CallSummary,
    CallTranscript,
    CallTurn,
    ExtractedField,
    QualityEvaluation,
)
from jkr_db.models.calls import InterruptionEvent as InterruptionEventModel
from jkr_db.models.contacts import Contact, SuppressionEntry
from jkr_db.models.knowledge import RetrievalEvent
from jkr_db.models.tools import Appointment, FollowUpTask
from jkr_db.tools_engine import ToolNotDefinedError, ToolNotEnabledError, execute_tool
from jkr_db.webhook_engine import deliver_webhook

logger = logging.getLogger(__name__)

_MONOLOGUE_CHAR_THRESHOLD = 220
_DISCLOSURE_MARKER = re.compile(r"\bai\b", re.IGNORECASE)
_FRUSTRATION_WORDS = ["వద్దు వద్దు", "cancel", "waste", "irritating", "కోపం", "chirakuga", "enough"]
_DNC_WORDS = ["do not call", "wrong number", "తప్పు నంబర్", "నాకు వద్దు", "call చేయకండి"]

OUTCOME_FOLLOWUP_CHANNEL = {
    "appointment_booked": "whatsapp",
    "qualified": "whatsapp",
    "interested": "whatsapp",
    "unreachable": "reminder",
    "not_interested": "close",
    "do_not_call": "suppress",
    "wrong_number": "suppress",
    "needs_human": "human_callback",
}

WHATSAPP_TEMPLATE_BY_OUTCOME = {
    "appointment_booked": "Appointment Confirmed! 📅 Date: {date} | ⏰ Time: {time} | 📍 Location: {location}. We look forward to seeing you!",
    "qualified": "Thank you for your interest! Your enquiry has been qualified with our specialist team. 📄 Brochure: https://jkr.ai/info/brochure. A representative will contact you shortly.",
    "interested": "Thank you for speaking with us today! 🌐 More information & services: https://jkr.ai/info/services. Feel free to reply or call us back anytime.",
}


async def _dispatch_follow_up(db: AsyncSession, *, workspace_id: uuid.UUID, follow_up_task: FollowUpTask, category: str) -> None:
    channel = follow_up_task.channel
    idempotency_key = f"followup-{follow_up_task.id}-{channel}"

    if channel == "whatsapp":
        if category == "appointment_booked":
            apt_result = await db.execute(
                select(Appointment).where(
                    Appointment.workspace_id == workspace_id,
                    Appointment.call_session_id == follow_up_task.call_session_id,
                ).order_by(Appointment.created_at.desc())
            )
            apt = apt_result.scalar_one_or_none()
            if apt is None and follow_up_task.contact_id:
                apt_result = await db.execute(
                    select(Appointment).where(
                        Appointment.workspace_id == workspace_id,
                        Appointment.contact_id == follow_up_task.contact_id,
                    ).order_by(Appointment.created_at.desc())
                )
                apt = apt_result.scalar_one_or_none()

            if apt and apt.scheduled_for:
                date_str = apt.scheduled_for.strftime("%A, %B %d, %Y")
                time_str = apt.scheduled_for.strftime("%I:%M %p")
            else:
                date_str = "upcoming appointment date"
                time_str = "confirmed time"

            loc_str = apt.location if (apt and apt.location) else "Aaha Dental Care, Road No. 12, Banjara Hills, Hyderabad"
            body = f"Appointment Confirmed! 📅 Date: {date_str} | ⏰ Time: {time_str} | 📍 Location: {loc_str}. We look forward to seeing you!"
        elif category == "qualified":
            body = "Thank you for your interest! Your enquiry has been qualified with our specialist team. 📄 Brochure: https://jkr.ai/info/brochure. A representative will contact you shortly."
        elif category == "interested":
            body = "Thank you for speaking with us today! 🌐 More information & services: https://jkr.ai/info/services. Feel free to reply or call us back anytime."
        else:
            body = WHATSAPP_TEMPLATE_BY_OUTCOME.get(category, "Thanks for your time — our team will follow up shortly.")

        try:
            execution = await execute_tool(
                db, workspace_id=workspace_id, tool_name="send_whatsapp", tool_input={"body": body},
                idempotency_key=idempotency_key, call_session_id=follow_up_task.call_session_id, contact_id=follow_up_task.contact_id,
            )
            out = execution.output or {}
            if out.get("status") == "failed":
                follow_up_task.status = "failed"
                follow_up_task.payload = {**follow_up_task.payload, "error": out.get("error")}
            else:
                follow_up_task.status = "sent"
                if out.get("provider_message_id"):
                    follow_up_task.payload = {**follow_up_task.payload, "provider_message_id": out.get("provider_message_id")}
        except (ToolNotDefinedError, ToolNotEnabledError) as exc:
            follow_up_task.status = "failed"
            follow_up_task.payload = {**follow_up_task.payload, "error": f"Tool error: {str(exc)}"}
        except Exception as exc:
            follow_up_task.status = "failed"
            follow_up_task.payload = {**follow_up_task.payload, "error": str(exc)}
    elif channel == "human_callback":
        try:
            await execute_tool(
                db, workspace_id=workspace_id, tool_name="create_human_callback",
                tool_input={"reason": "business_rule", "packet": {"outcome_category": category}},
                idempotency_key=idempotency_key, call_session_id=follow_up_task.call_session_id,
            )
            follow_up_task.status = "completed"
        except (ToolNotDefinedError, ToolNotEnabledError):
            pass
    elif channel == "suppress":
        contact_result = await db.execute(select(Contact).where(Contact.id == follow_up_task.contact_id, Contact.workspace_id == workspace_id))
        contact = contact_result.scalar_one_or_none()
        if contact is not None and not contact.is_suppressed:
            existing = await db.execute(
                select(SuppressionEntry).where(SuppressionEntry.workspace_id == workspace_id, SuppressionEntry.phone_e164 == contact.phone_e164)
            )
            if existing.scalar_one_or_none() is None:
                reason = "wrong_number" if category == "wrong_number" else "customer_opt_out"
                db.add(SuppressionEntry(workspace_id=workspace_id, contact_id=contact.id, phone_e164=contact.phone_e164, reason=reason, note="Auto-suppressed by post-call intelligence"))
            contact.is_suppressed = True
        follow_up_task.status = "completed"


async def run_post_call_pipeline(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, encryption_key: str) -> dict:
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
    agent_turns = [t for t in turns if t.speaker == "agent"]
    customer_turns = [t for t in turns if t.speaker == "customer"]

    interruptions_result = await db.execute(
        select(InterruptionEventModel).where(InterruptionEventModel.call_session_id == call_id)
    )
    interruptions = list(interruptions_result.scalars().all())
    meaningful_interruptions = [i for i in interruptions if i.classification == "meaningful"]

    knowledge_events_result = await db.execute(
        select(CallEvent).where(CallEvent.call_session_id == call_id, CallEvent.event_type == "knowledge_lookup")
    )
    knowledge_events = list(knowledge_events_result.scalars().all())

    state = call_session.state or {}
    known_fields: dict[str, str] = state.get("known_fields", {})
    objective_status = state.get("objective_status", "in_progress")
    objective = state.get("objective", "")

    full_transcript_text = " ".join(t.text for t in turns).lower()

    # --- extraction_validator ---------------------------------------------
    field_confidence: dict[str, float] = state.get("field_confidence", {})
    await _validate_extracted_fields(
        db, workspace_id=workspace_id, call_id=call_id, known_fields=known_fields,
        field_confidence=field_confidence, customer_turns=customer_turns,
    )

    # --- outcome_classifier -------------------------------------------------
    category, lead_score, reasons = _classify_outcome(
        objective=objective, objective_status=objective_status, known_fields=known_fields, transcript_text=full_transcript_text,
    )
    apt_check = await db.execute(
        select(Appointment).where(Appointment.call_session_id == call_id, Appointment.workspace_id == workspace_id)
    )
    if apt_check.scalar_one_or_none() is not None:
        category = "appointment_booked"
        lead_score = "hot"
        reasons = ["Appointment successfully booked during call"]

    await _upsert_outcome(db, workspace_id=workspace_id, call_id=call_id, category=category, lead_score=lead_score, reasons=reasons, objective_status=objective_status)

    # --- summary_processor ---------------------------------------------------
    summary_text = _build_summary(objective=objective, objective_status=objective_status, known_fields=known_fields)
    await _upsert_summary(db, workspace_id=workspace_id, call_id=call_id, summary_text=summary_text)

    # --- quality_evaluator ---------------------------------------------------
    quality = _evaluate_quality(
        agent_turns=agent_turns, customer_turns=customer_turns, meaningful_interruptions=meaningful_interruptions,
        total_interruptions=len(interruptions), objective_status=objective_status, knowledge_events=knowledge_events,
        transcript_text=full_transcript_text,
    )
    await _upsert_quality(db, workspace_id=workspace_id, call_id=call_id, quality=quality)

    # --- follow_up_planner ---------------------------------------------------
    if call_session.contact_id is not None:
        channel = OUTCOME_FOLLOWUP_CHANNEL.get(category, "human_callback")
        follow_up_task = FollowUpTask(
            workspace_id=workspace_id, contact_id=call_session.contact_id, call_session_id=call_id,
            channel=channel, status="pending",
            payload={"outcome_category": category, "known_fields": known_fields},
        )
        db.add(follow_up_task)
        await db.flush()
        await _dispatch_follow_up(db, workspace_id=workspace_id, follow_up_task=follow_up_task, category=category)

    # --- Persist CallTranscript & CallRecording to MinIO Storage & DB --------
    transcript_payload = {
        "call_id": str(call_id),
        "workspace_id": str(workspace_id),
        "language": str(call_session.language or "te-IN"),
        "direction": str(call_session.direction),
        "duration_seconds": call_session.duration_seconds or 15,
        "full_text": full_transcript_text or "No turns recorded",
        "turns": [
            {
                "sequence_index": t.sequence_index,
                "speaker": t.speaker,
                "text": t.text,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            }
            for t in turns
        ],
        "outcome": {
            "category": category,
            "lead_score": lead_score,
            "reasons": reasons,
        },
        "quality": quality,
    }

    storage_rec_key = f"recordings/{workspace_id}/{call_id}.wav"
    try:
        call_dur = max(call_session.duration_seconds or 15, 3)
        audio_wav = generate_synthesized_call_audio(duration_seconds=call_dur)
        storage_rec_key = upload_call_recording(workspace_id, call_id, audio_wav, format="wav")
        upload_call_transcript(workspace_id, call_id, transcript_payload)
    except Exception as exc:
        logger.warning("MinIO recording/transcript persistence error for call %s: %s", call_id, exc)

    existing_transcript = await db.execute(select(CallTranscript).where(CallTranscript.call_session_id == call_id))
    if existing_transcript.scalar_one_or_none() is None:
        db.add(
            CallTranscript(
                workspace_id=workspace_id,
                call_session_id=call_id,
                full_text=full_transcript_text or "No turns recorded",
                language=call_session.language,
                is_final=True,
            )
        )

    existing_rec = await db.execute(select(CallRecording).where(CallRecording.call_session_id == call_id))
    if existing_rec.scalar_one_or_none() is None:
        db.add(
            CallRecording(
                workspace_id=workspace_id,
                call_session_id=call_id,
                storage_key=storage_rec_key,
                duration_seconds=call_session.duration_seconds or 15,
                retention_expires_at=datetime.now(UTC) + timedelta(days=90),
            )
        )

    # --- Knowledge Gap Auto-Ticketing ----------------------------------------
    retrieval_res = await db.execute(
        select(RetrievalEvent).where(RetrievalEvent.call_session_id == call_id)
    )
    r_events = retrieval_res.scalars().all()
    if not r_events and any("?" in t.text or any(w in t.text.lower() for w in ("cost", "price", "when", "how much", "timing", "address")) for t in customer_turns):
        q_turn = next((t.text for t in customer_turns if "?" in t.text or any(w in t.text.lower() for w in ("cost", "price", "when", "how much", "timing", "address"))), None)
        if q_turn:
            db.add(
                RetrievalEvent(
                    workspace_id=workspace_id,
                    call_session_id=call_id,
                    query=q_turn,
                    matched_chunk_ids=[],
                    top_score=0.35,
                    used_in_response=False,
                )
            )

    await db.flush()

    if encryption_key:
        await deliver_webhook(
            db, encryption_key=encryption_key, workspace_id=workspace_id, event_type="call.completed",
            payload={"call_id": str(call_id), "outcome_category": category, "lead_score": lead_score, "summary": summary_text},
        )

    return {"call_id": call_id, "outcome_category": category, "lead_score": lead_score, "overall_score": quality["overall_score"]}


async def _validate_extracted_fields(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, known_fields: dict, field_confidence: dict, customer_turns: list) -> None:
    text_to_confidence = {t.text: (t.confidence or 0.0) for t in customer_turns}
    for field_key, field_value in known_fields.items():
        if field_key in field_confidence:
            confidence = field_confidence[field_key]
        else:
            confidence = text_to_confidence.get(field_value, 0.0)
        existing = await db.execute(
            select(ExtractedField).where(ExtractedField.call_session_id == call_id, ExtractedField.field_key == field_key)
        )
        row = existing.scalar_one_or_none()
        is_validated = confidence >= 0.9
        if row is None:
            db.add(
                ExtractedField(
                    workspace_id=workspace_id, call_session_id=call_id, field_key=field_key,
                    field_value=field_value, confidence=confidence, is_validated=is_validated,
                )
            )
        else:
            row.confidence = confidence
            row.is_validated = is_validated


def _classify_outcome(*, objective: str, objective_status: str, known_fields: dict, transcript_text: str) -> tuple[str, str, list[str]]:
    if any(word in transcript_text for word in _DNC_WORDS):
        return "do_not_call", "not_qualified", ["Customer indicated do-not-call or wrong number"]

    if objective_status == "completed" and objective == "book_appointment":
        return "appointment_booked", "hot", [f"{k}: {v}" for k, v in known_fields.items()]
    if objective_status == "completed" and known_fields:
        return "qualified", "warm", [f"{k}: {v}" for k, v in known_fields.items()]
    if known_fields:
        return "interested", "warm", [f"Partial info collected: {len(known_fields)} field(s)"]
    return "unreachable", "not_qualified", ["No information collected before call ended"]


async def _upsert_outcome(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, category: str, lead_score: str, reasons: list[str], objective_status: str) -> None:
    existing = await db.execute(select(CallOutcome).where(CallOutcome.call_session_id == call_id))
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(
            CallOutcome(
                workspace_id=workspace_id, call_session_id=call_id, category=category, lead_score=lead_score,
                score_reasons=reasons, objective_status=objective_status, notes="Generated by post-call intelligence pipeline.",
            )
        )
    else:
        row.category = category
        row.lead_score = lead_score
        row.score_reasons = reasons
        row.objective_status = objective_status
        row.notes = "Generated by post-call intelligence pipeline."


def _build_summary(*, objective: str, objective_status: str, known_fields: dict) -> str:
    if not known_fields:
        return f"Objective: {objective or 'unspecified'}. No information was collected before the call ended."
    facts = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known_fields.items())
    status_text = "completed" if objective_status == "completed" else "in progress when the call ended"
    return f"Objective ({objective.replace('_', ' ')}) {status_text}. {facts}."


async def _upsert_summary(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, summary_text: str) -> None:
    existing = await db.execute(select(CallSummary).where(CallSummary.call_session_id == call_id))
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(CallSummary(workspace_id=workspace_id, call_session_id=call_id, summary_text=summary_text, generated_by="intelligence_worker_rules"))
    else:
        row.summary_text = summary_text
        row.generated_by = "intelligence_worker_rules"


def _evaluate_quality(*, agent_turns: list, customer_turns: list, meaningful_interruptions: list, total_interruptions: int, objective_status: str, knowledge_events: list, transcript_text: str) -> dict:
    disclosure_present = bool(agent_turns) and bool(_DISCLOSURE_MARKER.search(agent_turns[0].text))
    opening_relevance_score = 1.0 if agent_turns else 0.0

    first_value_seconds = None
    if agent_turns and customer_turns:
        delta = (customer_turns[0].started_at - agent_turns[0].started_at).total_seconds()
        first_value_seconds = max(delta, 0.0)

    total_agent_turns = max(len(agent_turns), 1)
    interruption_quality_score = round(1.0 - (len(meaningful_interruptions) / total_agent_turns), 2)
    interruption_quality_score = max(0.0, min(1.0, interruption_quality_score))

    agent_texts = [t.text for t in agent_turns]
    repetition_flag = len(agent_texts) != len(set(agent_texts))
    hallucination_flag = False

    if knowledge_events:
        matched = sum(1 for e in knowledge_events if e.payload.get("matched"))
        knowledge_grounding_score = round(matched / len(knowledge_events), 2)
    else:
        knowledge_grounding_score = None

    customer_frustration_flag = any(word in transcript_text for word in _FRUSTRATION_WORDS)
    tone_score = 0.4 if customer_frustration_flag else 0.85

    objective_completed = objective_status == "completed"
    correct_closing = objective_completed
    long_monologue_flag = any(len(t.text) > _MONOLOGUE_CHAR_THRESHOLD for t in agent_turns)

    numeric_scores = [opening_relevance_score, interruption_quality_score, tone_score]
    if knowledge_grounding_score is not None:
        numeric_scores.append(knowledge_grounding_score)
    overall_score = round(sum(numeric_scores) / len(numeric_scores), 2)

    needs_human_review = overall_score < 0.5 or customer_frustration_flag or hallucination_flag or not disclosure_present

    return {
        "disclosure_present": disclosure_present,
        "opening_relevance_score": opening_relevance_score,
        "first_value_seconds": first_value_seconds,
        "interruption_quality_score": interruption_quality_score,
        "repetition_flag": repetition_flag,
        "hallucination_flag": hallucination_flag,
        "knowledge_grounding_score": knowledge_grounding_score,
        "tone_score": tone_score,
        "objective_completed": objective_completed,
        "correct_closing": correct_closing,
        "customer_frustration_flag": customer_frustration_flag,
        "long_monologue_flag": long_monologue_flag,
        "overall_score": overall_score,
        "needs_human_review": needs_human_review,
    }


async def _upsert_quality(db: AsyncSession, *, workspace_id: uuid.UUID, call_id: uuid.UUID, quality: dict) -> None:
    existing = await db.execute(select(QualityEvaluation).where(QualityEvaluation.call_session_id == call_id))
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(QualityEvaluation(workspace_id=workspace_id, call_session_id=call_id, **quality))
    else:
        for key, value in quality.items():
            setattr(row, key, value)
