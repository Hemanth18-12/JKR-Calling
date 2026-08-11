"""ONE canonical knowledge-retrieval implementation — replaces two
independently-maintained, near-duplicate copies that had already drifted:
services/voice-worker/app/knowledge_retrieval.py::search_knowledge() (set
RetrievalEvent.used_in_response = above_threshold, correct) and
services/api/app/modules/knowledge/service.py::search() (hardcoded
used_in_response=False unconditionally — a real, confirmed bug). Both call
sites now import from here instead.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass

from jkr_db.embeddings import embed_text
from jkr_db.models.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievalEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_conversation.schemas import RagChunk


@dataclass(frozen=True)
class RagTiming:
    """P3.5 §6 — RAG was previously one opaque `engine_rag` number. This
    breaks it into what a real-call probe (docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md
    §3) showed actually dominates it: the embedding API call, not pgvector
    (which is fast) and not chunk hydration (folded into the same query,
    negligible)."""

    embedding_ms: int
    vector_search_ms: int
    total_ms: int

# Tuned for REAL OpenAI text-embedding-3-small cosine distances, not the
# mock hash-bucket embedder's — a hash-based embedder needed a generous
# 0.75 because it only clusters on shared vocabulary; real embeddings
# cluster tighter on genuine semantic similarity, so a looser threshold
# there would let weakly-related chunks answer confidently, which is the
# exact failure mode spec §16 forbids. 0.4 is a reasoned starting point,
# not a labeled-eval-tuned one — a real retrieval eval dataset (deferred
# this pass) should replace this constant with a measured value.
RETRIEVAL_DISTANCE_THRESHOLD = 0.4

# Deliberately broad/multilingual — a customer question can arrive as
# "ధర ఎంత?" or "cost enta untundi" or plain "?" with no other marker.
QUESTION_TRIGGERS = [
    "?", "ఎంత", "enta", "entha", "ధర", "dhara", "cost", "price", "ఎప్పుడు", "eppudu",
    "when", "టైమ్", "time", "ఎలా", "ela", "how", "timing", "hours", "available", "undha", "unda",
]

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def looks_like_a_question(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in QUESTION_TRIGGERS)


def first_sentence(text: str, max_chars: int = 180) -> str:
    parts = _SENTENCE_END.split(text.strip())
    snippet = parts[0] if parts else text
    return snippet[:max_chars].strip()


async def search_knowledge_with_timing(
    db: AsyncSession, *, workspace_id: uuid.UUID, query: str, call_session_id: uuid.UUID | None = None, top_k: int = 4
) -> tuple[list[RagChunk], bool, RagTiming]:
    """Returns (chunks, above_threshold, timing) — chunks ordered by
    relevance, best first. Always logs a RetrievalEvent, even on a miss
    (knowledge-grounding-rate analytics needs the misses as much as the
    hits), with used_in_response correctly reflecting whether the top
    result actually cleared the confidence threshold.

    P3.5 §6: separately timed embedding vs. pgvector search — a direct
    provider probe (docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md §3) showed the
    embedding API call dominates "RAG latency", not the vector search
    itself; this makes that visible per-call instead of asserted once."""
    t0 = time.perf_counter()
    query_embedding = await embed_text(query)
    embedding_ms = int((time.perf_counter() - t0) * 1000)

    distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding)
    t0 = time.perf_counter()
    result = await db.execute(
        select(KnowledgeChunk, KnowledgeDocument.title, distance_expr.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.approval_state == "approved")
        .order_by(distance_expr)
        .limit(top_k)
    )
    rows = result.all()
    vector_search_ms = int((time.perf_counter() - t0) * 1000)

    chunks = [
        RagChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=max(0.0, 1.0 - float(distance)),
            distance=float(distance),
        )
        for chunk, title, distance in rows
    ]
    above_threshold = bool(chunks) and chunks[0].distance <= RETRIEVAL_DISTANCE_THRESHOLD

    db.add(
        RetrievalEvent(
            workspace_id=workspace_id,
            call_session_id=call_session_id,
            query=query,
            matched_chunk_ids=[c.chunk_id for c in chunks],
            top_score=chunks[0].score if chunks else None,
            used_in_response=above_threshold,
        )
    )
    await db.flush()

    timing = RagTiming(embedding_ms=embedding_ms, vector_search_ms=vector_search_ms, total_ms=embedding_ms + vector_search_ms)
    return chunks, above_threshold, timing


async def search_knowledge(
    db: AsyncSession, *, workspace_id: uuid.UUID, query: str, call_session_id: uuid.UUID | None = None, top_k: int = 4
) -> tuple[list[RagChunk], bool]:
    """Returns (chunks, above_threshold) — the pre-P3.5 signature, kept
    unchanged for existing callers (e.g. the manual knowledge-search
    endpoint in services/api) that don't need the timing breakdown."""
    chunks, above_threshold, _timing = await search_knowledge_with_timing(
        db, workspace_id=workspace_id, query=query, call_session_id=call_session_id, top_k=top_k
    )
    return chunks, above_threshold
