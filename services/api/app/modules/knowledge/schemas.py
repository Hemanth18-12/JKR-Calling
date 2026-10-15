from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    document_count: int


class DocumentCreate(BaseModel):
    source_type: str = Field(pattern=r"^(manual_faq|text|website|pdf|docx|csv)$")
    title: str = Field(min_length=1, max_length=300)
    collection_id: uuid.UUID | None = None
    language: str | None = None
    scope: str = Field(default="workspace", pattern=r"^(workspace|agent)$")
    agent_ids: list[uuid.UUID] = Field(default_factory=list)
    # For manual_faq / text:
    raw_text: str | None = None
    # For website:
    source_url: str | None = None
    # For pdf/docx/csv:
    file_base64: str | None = None


class DocumentAgentsUpdate(BaseModel):
    scope: str = Field(pattern=r"^(workspace|agent)$")
    agent_ids: list[uuid.UUID] = Field(default_factory=list)


class DocumentOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID | None
    source_type: str
    title: str
    source_url: str | None
    approval_state: str
    scope: str = "workspace"
    agent_ids: list[uuid.UUID] = Field(default_factory=list)
    language: str | None
    sensitivity: str
    chunk_count: int
    created_at: datetime


class DocumentDetail(DocumentOut):
    raw_text_preview: str | None


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    text: str
    approval_state: str
    page: int | None
    section: str | None


class ReviewDecision(BaseModel):
    notes: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    agent_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    above_threshold: bool


class GenerateKnowledgeRequest(BaseModel):
    business_type: str = Field(default="general")
    agent_category: str = Field(default="general")
    language: str = Field(default="en")  # en, te, hi
    agent_id: uuid.UUID | None = None
    answers: dict[str, Any] = Field(default_factory=dict)


class GenerateKnowledgeResponse(BaseModel):
    title: str
    generated_text: str
    health_score: int
    missing_fields: list[str]
    suggestions: list[str]


class HealthScoreRequest(BaseModel):
    document_id: uuid.UUID | None = None
    text: str | None = None
    category: str | None = None


class HealthScoreResponse(BaseModel):
    score: int
    missing_sections: list[str]
    suggestions: list[str]


class TestAgentRequest(BaseModel):
    agent_id: uuid.UUID | None = None
    query: str = Field(min_length=1)
    language: str = Field(default="en")


class TestAgentResponse(BaseModel):
    answer: str
    grounded: bool
    matched_chunks: list[SearchResultItem]
    used_scope: str
    latency_ms: dict[str, int]


class KnowledgeGapItem(BaseModel):
    id: uuid.UUID
    query: str
    count: int
    last_asked_at: datetime | None
