"""End-to-end process_turn() scenarios against a real Postgres database —
the one place a real KnowledgeChunk row is needed to exercise RAG for real,
following the same fixture pattern as
services/voice-worker/tests/test_conversation_engine.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling")

from jkr_conversation import engine  # noqa: E402
from jkr_conversation.schemas import ConversationPolicySnapshot  # noqa: E402
from jkr_conversation.state import new_conversation_state  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_per_test():
    import jkr_db.session as session_module

    session_module._engine = None
    session_module._session_factory = None
    yield
    eng = session_module._engine
    session_module._engine = None
    session_module._session_factory = None
    if eng is not None:
        await eng.dispose()


async def _seed_workspace_with_knowledge_and_call() -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, call_session_id) — a real CallSession row is
    required since RetrievalEvent.call_session_id is a real foreign key, and
    process_turn is always called against an already-created call session in
    both real call sites (voice-worker's start_session, live_call's
    start_live_test_call)."""
    from jkr_db.embeddings import embed_text
    from jkr_db.models.agents import Agent, AgentVersion
    from jkr_db.models.calls import CallSession
    from jkr_db.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Engine Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Engine Test WS", slug=f"engine-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        doc = KnowledgeDocument(workspace_id=workspace_id, source_type="manual_faq", title="Pricing", approval_state="approved", language="en")
        db.add(doc)
        await db.flush()
        version = KnowledgeDocumentVersion(workspace_id=workspace_id, document_id=doc.id, version_number=1)
        db.add(version)
        await db.flush()
        text = "Root canal treatment costs between 8000 and 12000 rupees depending on complexity."
        db.add(
            KnowledgeChunk(
                workspace_id=workspace_id, document_id=doc.id, document_version_id=version.id, chunk_index=0,
                text=text, embedding=await embed_text(text), approval_state="approved", language="en",
            )
        )

        agent = Agent(workspace_id=workspace_id, name="Test Agent", business_identity="Aaha Dental Care", primary_language="en-IN", status="active")
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="book_appointment", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Hello {name}, can we talk?", closing_text="Thank you.",
            supported_languages=["en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="in_progress",
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"engine-test-{uuid.uuid4()}",
            language="en-IN", state={}, started_at=datetime.now(UTC), is_mock=True, disclosure_confirmed=True,
        )
        db.add(call_session)
        await db.flush()
        call_session_id = call_session.id

    return workspace_id, call_session_id


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in (
            "retrieval_events", "knowledge_chunks", "knowledge_document_versions", "knowledge_documents",
            "call_sessions", "agent_versions",
        ):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
    async with get_session() as db:
        ws_row = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
        org_id = ws_row.organization_id
        await db.execute(text("DELETE FROM workspaces WHERE id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(org_id)})


@pytest.mark.asyncio
async def test_normal_turn_fills_field_and_asks_the_next_one():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
            )
        assert result.planner_action == "ASK_FIELD"
        assert result.state["known_fields"]["reason_for_visit"] == "I need it for a filling"
        assert result.call_should_end is False
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_question_priority_turn_logs_a_used_retrieval_event():
    from jkr_db.models.knowledge import RetrievalEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                # High exact-token overlap with the stored chunk — keeps this
                # test robust whether OPENAI_API_KEY is set (real embeddings)
                # or not (mock hash-bucket embedder, which only clusters on
                # shared vocabulary, not paraphrase-level similarity).
                customer_utterance="root canal treatment costs between 8000 and 12000 rupees enta?",
                conversation_policy=ConversationPolicySnapshot(), business_identity="Aaha Dental Care",
                now=datetime.now(UTC),
            )
            event = (
                await db.execute(select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace_id))
            ).scalar_one()

        assert result.rag_chunks  # a real chunk came back
        assert "8000" in result.reply_text or "12000" in result.reply_text  # answered from real approved knowledge
        assert event.used_in_response is True
        # Still asks the next field in the same turn — question-priority is
        # an annotation, not a flow-stopping exclusive action.
        assert result.planner_action == "ASK_FIELD"
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_do_not_call_turn_ends_the_call():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="please do not call again", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
            )
        assert result.call_should_end is True
        assert result.end_reason == "do_not_call"
        assert result.state["do_not_call"] is True
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_objective_completion_requests_the_booking_tool():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        state["known_fields"] = {"reason_for_visit": "root canal", "preferred_date": "tomorrow"}
        state["awaiting_field"] = "preferred_time"
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="evening works for me", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
            )
        assert result.planner_action == "COMPLETE_OBJECTIVE"
        assert result.call_should_end is True
        assert result.end_reason == "objective_completed"
        assert len(result.tool_calls_requested) == 1
        assert result.tool_calls_requested[0].tool_name == "book_appointment"
        assert result.tool_calls_requested[0].tool_input["preferred_time"] == "evening works for me"
        # Never overclaims a booking the tool hasn't actually run yet — the
        # canned closing text, not a free-generated "your appointment is confirmed."
        assert "confirmed and follow up" in result.reply_text or "will confirm" in result.reply_text
    finally:
        await _cleanup(workspace_id)
