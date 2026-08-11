from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import (
    CallDirection,
    CallEndReason,
    CallOutcomeCategory,
    CallStatus,
    InterruptionClass,
    LanguageCode,
    LeadScoreBucket,
    SpeakerRole,
)


class CallSession(Base, TenantMixin):
    __tablename__ = "call_sessions"

    direction: Mapped[CallDirection] = mapped_column(String(16), nullable=False)
    status: Mapped[CallStatus] = mapped_column(String(16), nullable=False, default=CallStatus.QUEUED)
    end_reason: Mapped[CallEndReason | None] = mapped_column(String(24), nullable=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    campaign_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_contacts.id", ondelete="SET NULL"), nullable=True
    )
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True
    )
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_accounts.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disclosure_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CallParticipant(Base, TenantMixin):
    __tablename__ = "call_participants"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[SpeakerRole] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CallTurn(Base, TenantMixin):
    __tablename__ = "call_turns"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[SpeakerRole] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CallEvent(Base, TenantMixin):
    __tablename__ = "call_events"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class CallRecording(Base, TenantMixin):
    __tablename__ = "call_recordings"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CallTranscript(Base, TenantMixin):
    __tablename__ = "call_transcripts"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CallLatencyMetric(Base, TenantMixin):
    __tablename__ = "call_latency_metrics"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)


class InterruptionEvent(Base, TenantMixin):
    __tablename__ = "interruption_events"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[InterruptionClass] = mapped_column(String(24), nullable=False)
    stop_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class TranscriptCorrectionEvent(Base, TenantMixin):
    """One row per domain-term candidate correction the shared conversation
    engine surfaced — real telemetry now (raw vs. candidate vs. what was
    actually accepted, and whether the customer confirmed it), so a
    workspace's vocabulary can be reviewed/extended from real mishearings
    over time. Not auto-learned into vocabulary — that stays a manual
    admin action, deliberately, per docs on this upgrade."""

    __tablename__ = "transcript_correction_events"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    domain_term_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_terms.id", ondelete="SET NULL"), nullable=True
    )
    sequence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_term: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidate_term: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accepted_term: Mapped[str | None] = mapped_column(String(200), nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_method: Mapped[str] = mapped_column(String(32), nullable=False, default="fuzzy_alias_match")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CallOutcome(Base, TenantMixin):
    __tablename__ = "call_outcomes"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    category: Mapped[CallOutcomeCategory] = mapped_column(String(32), nullable=False)
    lead_score: Mapped[LeadScoreBucket | None] = mapped_column(String(16), nullable=True)
    score_reasons: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    objective_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExtractedField(Base, TenantMixin):
    __tablename__ = "extracted_fields"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str] = mapped_column(String(1000), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CallSummary(Base, TenantMixin):
    __tablename__ = "call_summaries"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="mock_llm")


class QualityEvaluation(Base, TenantMixin):
    __tablename__ = "quality_evaluations"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    disclosure_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opening_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_value_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    interruption_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    repetition_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    knowledge_grounding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tone_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    objective_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correct_closing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    customer_frustration_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    long_monologue_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
