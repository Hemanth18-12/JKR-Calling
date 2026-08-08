from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.embeddings import embed_text
from jkr_db.models.knowledge import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeReview,
    RetrievalEvent,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.extraction import (
    chunk_text,
    extract_text_from_csv,
    extract_text_from_docx,
    extract_text_from_pdf,
    fetch_website_text,
)

# Cosine distance above this is treated as "no good match" — the agent must
# ask a clarification or offer a human callback instead of answering (spec
# §16 knowledge answer policy), never invent an answer from a weak match.
# Mock embeddings are bag-of-hashed-words (jkr_db.embeddings docstring), so
# this threshold is tuned generously for that, not for a real semantic model.
RETRIEVAL_DISTANCE_THRESHOLD = 0.75


async def create_collection(db: AsyncSession, *, workspace_id: uuid.UUID, name: str, description: str | None) -> KnowledgeCollection:
    collection = KnowledgeCollection(workspace_id=workspace_id, name=name, description=description)
    db.add(collection)
    await db.flush()
    return collection


async def list_collections(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    result = await db.execute(select(KnowledgeCollection).where(KnowledgeCollection.workspace_id == workspace_id))
    collections = list(result.scalars().all())
    out = []
    for c in collections:
        count_result = await db.execute(
            select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.collection_id == c.id)
        )
        out.append({"collection": c, "document_count": count_result.scalar_one()})
    return out


async def create_document(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    source_type: str,
    title: str,
    collection_id: uuid.UUID | None,
    language: str | None,
    raw_text: str | None,
    source_url: str | None,
    file_base64: str | None,
) -> KnowledgeDocument:
    extracted_text: str
    resolved_title = title

    if source_type in ("manual_faq", "text"):
        if not raw_text or not raw_text.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "raw_text is required for this source type")
        extracted_text = raw_text
    elif source_type == "website":
        if not source_url:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "source_url is required for website sources")
        fetched_title, extracted_text = await fetch_website_text(source_url)
        resolved_title = title or fetched_title
    elif source_type in ("pdf", "docx", "csv"):
        if not file_base64:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_base64 is required for this source type")
        try:
            data = base64.b64decode(file_base64)
        except Exception as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_base64 is not valid base64") from exc
        if source_type == "pdf":
            extracted_text = extract_text_from_pdf(data)
        elif source_type == "docx":
            extracted_text = extract_text_from_docx(data)
        else:
            extracted_text = extract_text_from_csv(data)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported source_type: {source_type}")

    if not extracted_text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No text could be extracted from this source")

    document = KnowledgeDocument(
        workspace_id=workspace_id,
        collection_id=collection_id,
        source_type=source_type,
        title=resolved_title,
        source_url=source_url,
        approval_state="draft",
        language=language,
    )
    db.add(document)
    await db.flush()

    version = KnowledgeDocumentVersion(
        workspace_id=workspace_id, document_id=document.id, version_number=1, raw_text=extracted_text,
    )
    db.add(version)
    await db.flush()
    document.current_version_id = version.id
    await db.flush()
    return document


async def process_document(db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> KnowledgeDocument:
    """Chunk + embed the current version's text — spec §16's
    "semantic chunking → metadata → embedding → vector storage" stages.
    Chunks land at approval_state=draft; only `approve_document` promotes
    them (and only approved chunks are ever retrievable — see `search`)."""
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.current_version_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document has no content version")

    version_result = await db.execute(
        select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == document.current_version_id)
    )
    version = version_result.scalar_one_or_none()
    if version is None or not version.raw_text:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document version has no text to process")

    document.approval_state = "processing"
    await db.flush()

    # Clear any prior chunks for this version (re-processing is idempotent).
    existing_chunks = await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_version_id == version.id))
    for chunk in existing_chunks.scalars().all():
        await db.delete(chunk)
    await db.flush()

    pieces = chunk_text(version.raw_text)
    for index, piece in enumerate(pieces):
        embedding = await embed_text(piece)
        db.add(
            KnowledgeChunk(
                workspace_id=workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                chunk_index=index,
                text=piece,
                embedding=embedding,
                approval_state="draft",
                language=document.language,
            )
        )

    version.processed_at = datetime.now(UTC)
    document.approval_state = "needs_review"
    await db.flush()
    return document


async def list_documents(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id).order_by(KnowledgeDocument.title))
    documents = list(result.scalars().all())
    out = []
    for d in documents:
        count_result = await db.execute(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == d.id))
        out.append({"document": d, "chunk_count": count_result.scalar_one()})
    return out


async def get_document(db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> dict:
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    preview = None
    if document.current_version_id:
        version_result = await db.execute(
            select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == document.current_version_id)
        )
        version = version_result.scalar_one_or_none()
        if version and version.raw_text:
            preview = version.raw_text[:500]

    chunks_result = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id).order_by(KnowledgeChunk.chunk_index)
    )
    return {"document": document, "raw_text_preview": preview, "chunks": list(chunks_result.scalars().all())}


async def set_review_decision(
    db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID, reviewer_id: uuid.UUID, approve: bool, notes: str | None
) -> KnowledgeDocument:
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.approval_state not in ("needs_review", "approved", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Document must be processed before it can be reviewed")

    new_state = "approved" if approve else "rejected"
    document.approval_state = new_state

    chunks_result = await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    for chunk in chunks_result.scalars().all():
        chunk.approval_state = new_state

    db.add(
        KnowledgeReview(
            workspace_id=workspace_id, document_id=document_id, reviewer_id=reviewer_id,
            decision=new_state, notes=notes, reviewed_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return document


async def search(
    db: AsyncSession, *, workspace_id: uuid.UUID, query: str, top_k: int, call_session_id: uuid.UUID | None = None
) -> tuple[list[dict], bool]:
    query_embedding = await embed_text(query)
    distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding)

    result = await db.execute(
        select(KnowledgeChunk, KnowledgeDocument.title, distance_expr.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.approval_state == "approved")
        .order_by(distance_expr)
        .limit(top_k)
    )
    rows = result.all()

    items = [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_title": title,
            "text": chunk.text,
            "score": max(0.0, 1.0 - float(distance)),
            "distance": float(distance),
        }
        for chunk, title, distance in rows
    ]
    above_threshold = bool(items) and items[0]["distance"] <= RETRIEVAL_DISTANCE_THRESHOLD

    db.add(
        RetrievalEvent(
            workspace_id=workspace_id,
            call_session_id=call_session_id,
            query=query,
            matched_chunk_ids=[i["chunk_id"] for i in items],
            top_score=items[0]["score"] if items else None,
            used_in_response=False,
        )
    )
    await db.flush()

    return items, above_threshold
