from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import (
    AgentStatus,
    AgentVersionStatus,
    LanguageCode,
    ProviderName,
    ToolName,
)


class Agent(Base, TenantMixin):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    business_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[AgentStatus] = mapped_column(String(32), nullable=False, default=AgentStatus.DRAFT)
    primary_language: Mapped[LanguageCode] = mapped_column(
        String(16), nullable=False, default=LanguageCode.TELUGU_ENGLISH
    )
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="SET NULL", use_alter=True, name="fk_agents_published_version"),
        nullable=True,
    )
    active_phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True
    )
    persona_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # No vocabulary assigned is a normal, valid state — extraction simply
    # skips domain normalization for this agent. See DomainVocabulary below.
    domain_vocabulary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_vocabularies.id", ondelete="SET NULL"), nullable=True
    )


class AgentVersion(Base, TenantMixin):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version_number", name="uq_agent_version_number"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AgentVersionStatus] = mapped_column(
        String(32), nullable=False, default=AgentVersionStatus.DRAFT
    )
    primary_objective: Mapped[str] = mapped_column(String(100), nullable=False)
    ai_disclosure_text: Mapped[str] = mapped_column(String(500), nullable=False)
    greeting_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    closing_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    personality: Mapped[str] = mapped_column(String(64), nullable=False, default="warm_receptionist")
    formality: Mapped[str] = mapped_column(String(32), nullable=False, default="balanced")
    energy: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    response_length: Mapped[str] = mapped_column(String(32), nullable=False, default="short")
    use_honorifics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supported_languages: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False, default=list
    )
    code_switching_behavior: Mapped[str] = mapped_column(
        String(32), nullable=False, default="adaptive"
    )
    restricted_phrases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    escalation_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class VoicePersona(Base, TenantMixin):
    __tablename__ = "voice_personas"

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[ProviderName] = mapped_column(String(32), nullable=False, default=ProviderName.MOCK)
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False, default="mock-warm-female-te")
    gender_presentation: Mapped[str] = mapped_column(String(32), nullable=False, default="female")
    language: Mapped[LanguageCode] = mapped_column(String(16), nullable=False, default=LanguageCode.TELUGU_ENGLISH)
    speaking_speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    stability: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    expressiveness: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    fallback_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sample_audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PronunciationEntry(Base, TenantMixin):
    __tablename__ = "pronunciation_entries"

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    pronunciation: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[LanguageCode] = mapped_column(String(16), nullable=False)


class ConversationPolicy(Base, TenantMixin):
    __tablename__ = "conversation_policies"

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    interruption_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_interruption_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=250)
    accidental_interruption_phrases: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False,
        default=lambda: ["hmm", "okay", "haa", "అవును", "achha", "theek hai", "right"],
    )
    silence_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=6000)
    max_monologue_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=12000)
    max_response_sentences: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    confirmation_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="confirm_critical")
    clarification_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="ask_dont_guess")
    background_noise_tolerance: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    human_transfer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    call_later_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    wrong_number_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="apologize_and_suppress")
    do_not_call_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="immediate_suppress")
    # Safety-net ceilings for the shared conversation engine (packages/conversation)
    # — a normal call ends when the objective reaches a terminal state on its
    # own; these only fire if something goes wrong and a call would otherwise
    # run unbounded. Replaces the old hardcoded MAX_AGENT_TURNS=5 module
    # constant in services/api/app/modules/live_call/service.py.
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_call_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)


class DomainVocabulary(Base, TenantMixin):
    """A named set of business-domain terms (dental, admissions, real
    estate, ...) an agent can be assigned to, so extraction can recognize
    when a transcribed value is probably a mis-hearing of a real domain
    term — see jkr_conversation.domain_normalizer. Not agent-exclusive by
    FK direction (Agent -> DomainVocabulary) so one vocabulary can be
    shared across multiple agents in a workspace."""

    __tablename__ = "domain_vocabularies"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DomainTerm(Base, TenantMixin):
    __tablename__ = "domain_terms"

    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_vocabularies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical: Mapped[str] = mapped_column(String(200), nullable=False)
    # Alternate spellings/mishearings — no independent lifecycle of their
    # own this pass (no per-alias approval state), so a plain array column
    # rather than a join table, matching restricted_phrases/
    # accidental_interruption_phrases elsewhere in this same file.
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    # "standard" | "critical" — critical terms get confirmed before being
    # trusted under the default confirm_critical policy; see
    # jkr_conversation.engine's confirmation decision table.
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False, default=list)


class ToolDefinition(Base, TenantMixin):
    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_tool_definition_workspace_name"),)

    name: Mapped[ToolName] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    required_permission: Mapped[str] = mapped_column(String(100), nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    retry_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="key_based")
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audit_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failure_fallback: Mapped[str] = mapped_column(String(64), nullable=False, default="offer_human_callback")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AgentTool(Base, TenantMixin):
    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint("agent_version_id", "tool_definition_id", name="uq_agent_tool"),
    )

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_definitions.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_override: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
