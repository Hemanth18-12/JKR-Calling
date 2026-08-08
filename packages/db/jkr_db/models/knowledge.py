from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin
from jkr_db.enums import ApprovalState, KnowledgeSourceType, LanguageCode

EMBEDDING_DIM = 1536  # matches text-embedding-3-small; mock embedder pads/truncates to this


class KnowledgeCollection(Base, TenantMixin):
    __tablename__ = "knowledge_collections"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class KnowledgeDocument(Base, TenantMixin):
    __tablename__ = "knowledge_documents"

    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_collections.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[KnowledgeSourceType] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approval_state: Mapped[ApprovalState] = mapped_column(String(16), nullable=False, default=ApprovalState.DRAFT)
    language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(24), nullable=False, default="normal")
    expiry_at: Mapped[datetime | None] = mapped_column(nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_scanned")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "knowledge_document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_knowledge_documents_current_version",
        ),
        nullable=True,
    )


class KnowledgeDocumentVersion(Base, TenantMixin):
    __tablename__ = "knowledge_document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class KnowledgeChunk(Base, TenantMixin):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approval_state: Mapped[ApprovalState] = mapped_column(String(16), nullable=False, default=ApprovalState.DRAFT)
    language: Mapped[LanguageCode | None] = mapped_column(String(16), nullable=True)


class KnowledgeReview(Base, TenantMixin):
    __tablename__ = "knowledge_reviews"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False)


class RetrievalEvent(Base, TenantMixin):
    __tablename__ = "retrieval_events"

    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    matched_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    top_score: Mapped[float | None] = mapped_column(nullable=True)
    used_in_response: Mapped[bool] = mapped_column(nullable=False, default=False)
