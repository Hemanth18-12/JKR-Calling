from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from jkr_conversation.rag import search_knowledge
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.knowledge import service
from app.modules.knowledge.schemas import (
    ChunkOut,
    CollectionCreate,
    CollectionOut,
    DocumentCreate,
    DocumentDetail,
    DocumentOut,
    ReviewDecision,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/collections", response_model=CollectionOut, status_code=201)
async def create_collection(
    payload: CollectionCreate,
    auth: AuthContext = Depends(require_permission("knowledge:create")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:create")),
) -> CollectionOut:
    collection = await service.create_collection(db, workspace_id=auth.workspace_id, name=payload.name, description=payload.description)
    return CollectionOut(id=collection.id, name=collection.name, description=collection.description, document_count=0)


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(
    auth: AuthContext = Depends(require_permission("knowledge:view")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:view")),
) -> list[CollectionOut]:
    rows = await service.list_collections(db, workspace_id=auth.workspace_id)
    return [
        CollectionOut(id=r["collection"].id, name=r["collection"].name, description=r["collection"].description, document_count=r["document_count"])
        for r in rows
    ]


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    auth: AuthContext = Depends(require_permission("knowledge:view")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:view")),
) -> list[DocumentOut]:
    rows = await service.list_documents(db, workspace_id=auth.workspace_id)
    return [
        DocumentOut(
            id=r["document"].id, collection_id=r["document"].collection_id, source_type=r["document"].source_type,
            title=r["document"].title, source_url=r["document"].source_url, approval_state=r["document"].approval_state,
            language=r["document"].language, sensitivity=r["document"].sensitivity, chunk_count=r["chunk_count"],
            created_at=r["document"].created_at,
        )
        for r in rows
    ]


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def create_document(
    payload: DocumentCreate,
    auth: AuthContext = Depends(require_permission("knowledge:create")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:create")),
) -> DocumentOut:
    document = await service.create_document(
        db, workspace_id=auth.workspace_id, source_type=payload.source_type, title=payload.title,
        collection_id=payload.collection_id, language=payload.language, raw_text=payload.raw_text,
        source_url=payload.source_url, file_base64=payload.file_base64,
    )
    return DocumentOut(
        id=document.id, collection_id=document.collection_id, source_type=document.source_type, title=document.title,
        source_url=document.source_url, approval_state=document.approval_state, language=document.language,
        sensitivity=document.sensitivity, chunk_count=0, created_at=document.created_at,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("knowledge:view")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:view")),
) -> DocumentDetail:
    data = await service.get_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    d = data["document"]
    return DocumentDetail(
        id=d.id, collection_id=d.collection_id, source_type=d.source_type, title=d.title, source_url=d.source_url,
        approval_state=d.approval_state, language=d.language, sensitivity=d.sensitivity, chunk_count=len(data["chunks"]),
        created_at=d.created_at, raw_text_preview=data["raw_text_preview"],
    )


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
async def get_document_chunks(
    document_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("knowledge:view")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:view")),
) -> list[ChunkOut]:
    data = await service.get_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    return [
        ChunkOut(id=c.id, chunk_index=c.chunk_index, text=c.text, approval_state=c.approval_state, page=c.page, section=c.section)
        for c in data["chunks"]
    ]


@router.post("/documents/{document_id}/process", response_model=DocumentOut)
async def process_document(
    document_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("knowledge:edit")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:edit")),
) -> DocumentOut:
    document = await service.process_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    data = await service.get_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    return DocumentOut(
        id=document.id, collection_id=document.collection_id, source_type=document.source_type, title=document.title,
        source_url=document.source_url, approval_state=document.approval_state, language=document.language,
        sensitivity=document.sensitivity, chunk_count=len(data["chunks"]), created_at=document.created_at,
    )


@router.post("/documents/{document_id}/approve", response_model=DocumentOut)
async def approve_document(
    document_id: uuid.UUID,
    payload: ReviewDecision,
    auth: AuthContext = Depends(require_permission("knowledge:approve")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:approve")),
) -> DocumentOut:
    document = await service.set_review_decision(
        db, workspace_id=auth.workspace_id, document_id=document_id, reviewer_id=auth.user.id, approve=True, notes=payload.notes
    )
    data = await service.get_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    return DocumentOut(
        id=document.id, collection_id=document.collection_id, source_type=document.source_type, title=document.title,
        source_url=document.source_url, approval_state=document.approval_state, language=document.language,
        sensitivity=document.sensitivity, chunk_count=len(data["chunks"]), created_at=document.created_at,
    )


@router.post("/documents/{document_id}/reject", response_model=DocumentOut)
async def reject_document(
    document_id: uuid.UUID,
    payload: ReviewDecision,
    auth: AuthContext = Depends(require_permission("knowledge:approve")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:approve")),
) -> DocumentOut:
    document = await service.set_review_decision(
        db, workspace_id=auth.workspace_id, document_id=document_id, reviewer_id=auth.user.id, approve=False, notes=payload.notes
    )
    data = await service.get_document(db, workspace_id=auth.workspace_id, document_id=document_id)
    return DocumentOut(
        id=document.id, collection_id=document.collection_id, source_type=document.source_type, title=document.title,
        source_url=document.source_url, approval_state=document.approval_state, language=document.language,
        sensitivity=document.sensitivity, chunk_count=len(data["chunks"]), created_at=document.created_at,
    )


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    auth: AuthContext = Depends(require_permission("knowledge:view")),
    db: AsyncSession = Depends(workspace_db_for("knowledge:view")),
) -> SearchResponse:
    chunks, above_threshold = await search_knowledge(db, workspace_id=auth.workspace_id, query=payload.query, top_k=payload.top_k)
    return SearchResponse(
        results=[
            SearchResultItem(chunk_id=c.chunk_id, document_id=c.document_id, document_title=c.document_title, text=c.text, score=c.score)
            for c in chunks
        ],
        above_threshold=above_threshold,
    )
