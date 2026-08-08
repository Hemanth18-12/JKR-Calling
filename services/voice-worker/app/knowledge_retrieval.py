"""Knowledge retrieval, called directly against Postgres rather than
round-tripping through services/api — voice-worker already holds a direct
DB connection for call_* tables (docs/ARCHITECTURE.md §8), and the browser
never talks to voice-worker anyway, so there's no trust-boundary reason to
proxy this through services/api. Mirrors (deliberately small duplication,
not worth a network hop for) services/api/app/modules/knowledge/service.py::search
— both MUST use the same `jkr_db.embeddings.embed_text` or cosine similarity
between the two sides is meaningless.
"""

from __future__ import annotations

import re
import uuid

from jkr_db.embeddings import embed_text
from jkr_db.models.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievalEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

RETRIEVAL_DISTANCE_THRESHOLD = 0.75

# Deliberately broad/multilingual — spec §9/§16 examples code-switch Telugu
# and English mid-sentence, so a question can arrive as "ధర ఎంత?" or
# "cost enta untundi" or plain "?" with no other marker.
QUESTION_TRIGGERS = [
    "?", "ఎంత", "enta", "entha", "ధర", "dhara", "cost", "price", "ఎప్పుడు", "eppudu",
    "when", "టైమ్", "time", "ఎలా", "ela", "how", "timing", "hours",
]


def looks_like_a_question(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in QUESTION_TRIGGERS)


async def search_knowledge(
    db: AsyncSession, *, workspace_id: uuid.UUID, query: str, call_session_id: uuid.UUID, top_k: int = 3
) -> tuple[str | None, bool]:
    """Returns (best_chunk_text_or_None, above_threshold). Always logs a
    RetrievalEvent, even on a miss — spec §22's knowledge-grounding-rate
    analytics needs the misses as much as the hits."""
    query_embedding = await embed_text(query)
    distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding)

    result = await db.execute(
        select(KnowledgeChunk, distance_expr.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.approval_state == "approved")
        .order_by(distance_expr)
        .limit(top_k)
    )
    rows = result.all()

    best_text = None
    above_threshold = False
    matched_ids = []
    top_score = None
    if rows:
        matched_ids = [chunk.id for chunk, _ in rows]
        best_chunk, best_distance = rows[0]
        top_score = max(0.0, 1.0 - float(best_distance))
        if float(best_distance) <= RETRIEVAL_DISTANCE_THRESHOLD:
            best_text = best_chunk.text
            above_threshold = True

    db.add(
        RetrievalEvent(
            workspace_id=workspace_id, call_session_id=call_session_id, query=query,
            matched_chunk_ids=matched_ids, top_score=top_score, used_in_response=above_threshold,
        )
    )
    return best_text, above_threshold


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def first_sentence(text: str, max_chars: int = 180) -> str:
    parts = _SENTENCE_END.split(text.strip())
    snippet = parts[0] if parts else text
    return snippet[:max_chars].strip()
