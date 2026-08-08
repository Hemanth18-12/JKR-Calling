"""Pure heuristics ported from services/voice-worker/tests/test_knowledge_retrieval.py,
plus a real DB-integration regression test for the exact bug this module
fixes: services/api/app/modules/knowledge/service.py::search() used to
hardcode RetrievalEvent.used_in_response=False unconditionally, disagreeing
with voice-worker's own (correct) search_knowledge(). rag.py's one
implementation must get this right on both a hit and a miss.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from jkr_conversation.rag import first_sentence, looks_like_a_question  # noqa: E402


def test_looks_like_a_question_detects_question_mark():
    assert looks_like_a_question("root canal ఎంత అవుతుంది?") is True


def test_looks_like_a_question_detects_price_keywords_without_question_mark():
    assert looks_like_a_question("cost enta untundi") is True
    assert looks_like_a_question("ధర ఎంత") is True


def test_looks_like_a_question_false_for_plain_statement():
    assert looks_like_a_question("రేపు ఉదయం పది గంటలకు వీలుగా ఉంటుంది") is False


def test_first_sentence_returns_only_the_first_sentence():
    text = "Root canal costs 8000 to 12000 rupees. We are open Monday to Saturday."
    assert first_sentence(text) == "Root canal costs 8000 to 12000 rupees."


def test_first_sentence_truncates_a_single_long_sentence():
    text = "A" * 300
    result = first_sentence(text, max_chars=180)
    assert len(result) == 180


# --- DB-integration: the actual used_in_response regression test ----------


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_per_test():
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None
    yield
    engine = session_module._engine
    session_module._engine = None
    session_module._session_factory = None
    if engine is not None:
        await engine.dispose()


async def _seed_workspace_with_one_approved_chunk() -> uuid.UUID:
    from jkr_db.embeddings import embed_text
    from jkr_db.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="RAG Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="RAG Test WS", slug=f"rag-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        doc = KnowledgeDocument(
            workspace_id=workspace_id, source_type="manual_faq", title="Pricing FAQ",
            approval_state="approved", language="en",
        )
        db.add(doc)
        await db.flush()
        version = KnowledgeDocumentVersion(workspace_id=workspace_id, document_id=doc.id, version_number=1)
        db.add(version)
        await db.flush()
        text = "Root canal treatment costs between 8000 and 12000 rupees depending on complexity."
        embedding = await embed_text(text)
        db.add(
            KnowledgeChunk(
                workspace_id=workspace_id, document_id=doc.id, document_version_id=version.id, chunk_index=0,
                text=text, embedding=embedding, approval_state="approved", language="en",
            )
        )
        await db.flush()
    return workspace_id


async def _cleanup_workspace(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in ("retrieval_events", "knowledge_chunks", "knowledge_document_versions", "knowledge_documents"):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})

    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


@pytest.mark.asyncio
async def test_used_in_response_is_true_on_an_above_threshold_hit():
    from jkr_conversation.rag import search_knowledge
    from jkr_db.models.knowledge import RetrievalEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    workspace_id = await _seed_workspace_with_one_approved_chunk()
    try:
        async with workspace_scoped_session(workspace_id) as db:
            chunks, above_threshold = await search_knowledge(
                db, workspace_id=workspace_id, query="root canal treatment costs between 8000 and 12000 rupees", call_session_id=None
            )
            event = (
                await db.execute(select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace_id))
            ).scalar_one()

        assert above_threshold is True
        assert chunks and chunks[0].text.startswith("Root canal treatment costs")
        assert event.used_in_response is True  # the exact bug: knowledge/service.py::search() used to hardcode False here
    finally:
        await _cleanup_workspace(workspace_id)


@pytest.mark.asyncio
async def test_used_in_response_is_false_on_a_miss():
    from jkr_conversation.rag import search_knowledge
    from jkr_db.models.knowledge import RetrievalEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    workspace_id = await _seed_workspace_with_one_approved_chunk()
    try:
        async with workspace_scoped_session(workspace_id) as db:
            chunks, above_threshold = await search_knowledge(
                db, workspace_id=workspace_id, query="do you offer free parking on weekends", call_session_id=None
            )
            event = (
                await db.execute(select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace_id))
            ).scalar_one()

        assert above_threshold is False
        assert event.used_in_response is False
    finally:
        await _cleanup_workspace(workspace_id)
