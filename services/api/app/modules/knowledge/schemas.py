from __future__ import annotations

import uuid
from datetime import datetime

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
    # For manual_faq / text:
    raw_text: str | None = None
    # For website:
    source_url: str | None = None
    # For pdf/docx/csv (base64-encoded file content — see extraction.py
    # docstring / docs/IMPLEMENTATION_CHECKLIST.md for why this pass accepts
    # base64-in-JSON rather than multipart, and does not persist original
    # file bytes to object storage):
    file_base64: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID | None
    source_type: str
    title: str
    source_url: str | None
    approval_state: str
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
