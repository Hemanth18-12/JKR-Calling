from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    business_identity: str = Field(min_length=1, max_length=200)
    description: str | None = None
    primary_language: str = "te-en-IN"
    persona_template: str = "warm_receptionist"


class AgentUpdate(BaseModel):
    name: str | None = None
    business_identity: str | None = None
    description: str | None = None
    primary_language: str | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    business_identity: str
    description: str | None
    status: str
    primary_language: str
    published_version_id: uuid.UUID | None
    active_phone_number_id: uuid.UUID | None
    persona_template: str | None
    created_at: datetime


class VoicePersonaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    voice_id: str
    gender_presentation: str
    language: str
    speaking_speed: float
    stability: float
    expressiveness: float
    fallback_voice_id: str | None
    sample_audio_url: str | None


class VoicePersonaUpdate(BaseModel):
    provider: str | None = None
    voice_id: str | None = None
    gender_presentation: str | None = None
    language: str | None = None
    speaking_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    expressiveness: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_voice_id: str | None = None


class ConversationPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interruption_enabled: bool
    min_interruption_ms: int
    accidental_interruption_phrases: list[str]
    silence_timeout_ms: int
    max_monologue_ms: int
    max_response_sentences: int
    confirmation_behavior: str
    clarification_behavior: str
    background_noise_tolerance: str
    human_transfer_enabled: bool
    call_later_enabled: bool
    wrong_number_behavior: str
    do_not_call_behavior: str


class ConversationPolicyUpdate(BaseModel):
    interruption_enabled: bool | None = None
    min_interruption_ms: int | None = Field(default=None, ge=0, le=5000)
    accidental_interruption_phrases: list[str] | None = None
    silence_timeout_ms: int | None = Field(default=None, ge=1000, le=60000)
    max_monologue_ms: int | None = Field(default=None, ge=1000, le=60000)
    max_response_sentences: int | None = Field(default=None, ge=1, le=10)
    confirmation_behavior: str | None = None
    clarification_behavior: str | None = None
    background_noise_tolerance: str | None = None
    human_transfer_enabled: bool | None = None
    call_later_enabled: bool | None = None
    wrong_number_behavior: str | None = None
    do_not_call_behavior: str | None = None


class PronunciationEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    term: str
    pronunciation: str
    language: str


class PronunciationEntryCreate(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    pronunciation: str = Field(min_length=1, max_length=200)
    language: str


class AgentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    version_number: int
    status: str
    primary_objective: str
    ai_disclosure_text: str
    greeting_text: str
    closing_text: str
    personality: str
    formality: str
    energy: str
    response_length: str
    use_honorifics: bool
    supported_languages: list[str]
    code_switching_behavior: str
    restricted_phrases: list[str]
    escalation_policy: dict
    quality_score: float | None
    published_at: datetime | None
    created_at: datetime


class AgentVersionDetail(AgentVersionOut):
    voice_persona: VoicePersonaOut | None
    conversation_policy: ConversationPolicyOut | None
    pronunciation_entries: list[PronunciationEntryOut]


class AgentVersionUpdate(BaseModel):
    primary_objective: str | None = None
    ai_disclosure_text: str | None = None
    greeting_text: str | None = None
    closing_text: str | None = None
    personality: str | None = None
    formality: str | None = None
    energy: str | None = None
    response_length: str | None = None
    use_honorifics: bool | None = None
    supported_languages: list[str] | None = None
    code_switching_behavior: str | None = None
    restricted_phrases: list[str] | None = None
    escalation_policy: dict | None = None


class AgentDetail(AgentOut):
    versions: list[AgentVersionOut]


class PersonaTemplateOut(BaseModel):
    key: str
    label: str
