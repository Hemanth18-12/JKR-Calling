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
from jkr_conversation.streaming_llm import (  # noqa: E402
    LLMResponseCompleted,
    LLMResponseStarted,
    TextDelta,
)


class _CountingLLMClient:
    """P3.5 — proves a claim like "zero LLM calls" or "one LLM call" for
    real, not by inference from timing. Raising on both methods by default
    would break mock-mode's own fallback-on-None contract, so this returns
    None (exactly what "no LLM configured" already means to every caller in
    this package) while still counting every attempt."""

    def __init__(self):
        self.complete_json_calls = 0
        self.complete_text_calls = 0

    async def complete_json(self, *, system, user, max_tokens=300):
        self.complete_json_calls += 1
        return None

    async def complete_text(self, *, system, user, max_tokens=150):
        self.complete_text_calls += 1
        return None


class _FakeStreamingLLMClient:
    """P5 — the shape OpenAILLMClient has after adding stream_text():
    satisfies LLMClient (complete_json/complete_text) AND exposes
    stream_text, so process_turn(response_mode="streaming") has something
    real to drive without touching the network."""

    def __init__(self, events: list, complete_text_response: str | None = None):
        self._events = events
        self._complete_text_response = complete_text_response
        self.complete_json_calls = 0
        self.complete_text_calls = 0
        self.stream_text_call_count = 0
        self.last_system: str | None = None

    async def complete_json(self, *, system, user, max_tokens=300):
        self.complete_json_calls += 1
        return None

    async def complete_text(self, *, system, user, max_tokens=150):
        self.complete_text_calls += 1
        return self._complete_text_response

    def stream_text(self, *, system, user, max_tokens=150):
        self.stream_text_call_count += 1
        self.last_system = system
        return self._events_gen()

    async def _events_gen(self):
        for event in self._events:
            yield event


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


async def _seed_workspace_with_dental_vocabulary() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, call_session_id, agent_id) — a minimal
    workspace with an agent assigned a dental DomainVocabulary containing
    the exact real-call bug: "root canal treatment" (critical) with
    "ఫ్రూట్ కెనాల్స్" (the literal mis-transcription from call
    1482f303-3dc9-4fa2-b32c-83f43f24d7c0) seeded as a known alias."""
    from jkr_db.models.agents import Agent, AgentVersion, DomainTerm, DomainVocabulary
    from jkr_db.models.calls import CallSession
    from jkr_db.models.tenancy import Organization, Workspace
    from jkr_db.session import get_session, workspace_scoped_session

    workspace_id = uuid.uuid4()
    async with get_session() as db:
        org = Organization(name="Engine Domain Test Org")
        db.add(org)
        await db.flush()
        db.add(Workspace(id=workspace_id, organization_id=org.id, name="Engine Domain Test WS", slug=f"engine-domain-test-{workspace_id}"))
        await db.flush()

    async with workspace_scoped_session(workspace_id) as db:
        vocabulary = DomainVocabulary(workspace_id=workspace_id, name="Dental Procedures")
        db.add(vocabulary)
        await db.flush()
        db.add(
            DomainTerm(
                workspace_id=workspace_id, vocabulary_id=vocabulary.id, canonical="root canal treatment",
                aliases=["ఫ్రూట్ కెనాల్స్", "fruit canals", "RCT"], category="procedure",
                criticality="critical", languages=["te", "en"],
            )
        )
        await db.flush()

        agent = Agent(
            workspace_id=workspace_id, name="Domain Test Agent", business_identity="Aaha Dental Care",
            primary_language="te-en-IN", status="active", domain_vocabulary_id=vocabulary.id,
        )
        db.add(agent)
        await db.flush()
        agent_version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="published",
            primary_objective="book_appointment", ai_disclosure_text="I'm an AI assistant.",
            greeting_text="Hello, can we talk?", closing_text="Thank you.",
            supported_languages=["te-en-IN"], published_at=datetime.now(UTC),
        )
        db.add(agent_version)
        await db.flush()
        agent.published_version_id = agent_version.id

        call_session = CallSession(
            workspace_id=workspace_id, direction="outbound", status="in_progress",
            agent_id=agent.id, agent_version_id=agent_version.id, idempotency_key=f"engine-domain-test-{uuid.uuid4()}",
            language="te-en-IN", state={}, started_at=datetime.now(UTC), is_mock=True, disclosure_confirmed=True,
        )
        db.add(call_session)
        await db.flush()
        call_session_id = call_session.id

    return workspace_id, call_session_id, agent.id


async def _cleanup(workspace_id: uuid.UUID) -> None:
    from jkr_db.models.tenancy import Workspace
    from jkr_db.session import get_session, workspace_scoped_session
    from sqlalchemy import select, text

    async with workspace_scoped_session(workspace_id) as db:
        for table in (
            "transcript_correction_events", "retrieval_events", "knowledge_chunks", "knowledge_document_versions",
            "knowledge_documents", "call_sessions", "agent_versions",
        ):
            await db.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("UPDATE agents SET published_version_id = NULL, domain_vocabulary_id = NULL WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM agents WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM domain_terms WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
        await db.execute(text("DELETE FROM domain_vocabularies WHERE workspace_id = :wsid"), {"wsid": str(workspace_id)})
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


@pytest.mark.asyncio
async def test_domain_mistranscription_is_flagged_for_confirmation_not_silently_trusted():
    """The exact bug from real call 1482f303-3dc9-4fa2-b32c-83f43f24d7c0:
    "root canal" mis-transcribed as "ఫ్రూట్ కెనాల్స్" (fruit canals) used to
    get stored at field_confidence=1.0 and parroted back. It must now be
    flagged (CONFIRM_FIELD) instead of written straight to known_fields."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="te-en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="నాకు ఫ్రూట్ కెనాల్స్ కావాలి", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC),
            )
        assert result.planner_action == "CONFIRM_FIELD"
        assert "reason_for_visit" not in result.state["known_fields"]
        pending = result.state["pending_confirmation"]
        assert pending["field"] == "reason_for_visit"
        assert pending["candidate_value"] == "root canal treatment"
        assert "root canal treatment" in result.reply_text  # natural confirmation, not "you said X, is that correct?"
        assert "is that correct" not in result.reply_text.lower()
        assert result.call_should_end is False
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_customer_confirms_domain_correction_writes_canonical_value():
    from jkr_db.models.calls import TranscriptCorrectionEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="te-en-IN")
        state["pending_confirmation"] = {
            "field": "reason_for_visit", "raw_value": "నాకు ఫ్రూట్ కెనాల్స్ కావాలి",
            "candidate_value": "root canal treatment", "semantic_confidence": 1.0,
            "domain_term_id": None, "correction_method": "fuzzy_alias_match",
        }
        state["field_ask_counts"] = {"reason_for_visit": 1}
        state["awaiting_field"] = "reason_for_visit"
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="avunu andi", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC),
            )
            events = (
                await db.execute(select(TranscriptCorrectionEvent).where(TranscriptCorrectionEvent.call_session_id == call_id))
            ).scalars().all()

        assert result.state["known_fields"]["reason_for_visit"] == "root canal treatment"
        assert result.state["pending_confirmation"] is None
        assert result.state["field_confidence"]["reason_for_visit"] == 0.95
        # Continues naturally onto the next missing field in the same turn.
        assert result.planner_action == "ASK_FIELD"
        assert result.state["awaiting_field"] == "preferred_date"

        assert len(events) == 1
        assert events[0].customer_confirmed is True
        assert events[0].candidate_term == "root canal treatment"
        assert events[0].accepted_term == "root canal treatment"
        assert events[0].raw_term == "నాకు ఫ్రూట్ కెనాల్స్ కావాలి"
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_customer_rejects_domain_correction_leaves_field_missing_and_logs_event():
    from jkr_db.models.calls import TranscriptCorrectionEvent
    from jkr_db.session import workspace_scoped_session
    from sqlalchemy import select

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="te-en-IN")
        state["pending_confirmation"] = {
            "field": "reason_for_visit", "raw_value": "నాకు ఫ్రూట్ కెనాల్స్ కావాలి",
            "candidate_value": "root canal treatment", "semantic_confidence": 1.0,
            "domain_term_id": None, "correction_method": "fuzzy_alias_match",
        }
        state["field_ask_counts"] = {"reason_for_visit": 1}
        state["awaiting_field"] = "reason_for_visit"
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="kaadu", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC),
            )
            events = (
                await db.execute(select(TranscriptCorrectionEvent).where(TranscriptCorrectionEvent.call_session_id == call_id))
            ).scalars().all()

        assert "reason_for_visit" not in result.state["known_fields"]
        assert result.state["pending_confirmation"] is None
        # Never silently guessed — falls back to re-asking the same field
        # (still within its ask-cap), not to accepting the rejected value.
        assert result.planner_action == "ASK_FIELD"
        assert result.state["awaiting_field"] == "reason_for_visit"

        assert len(events) == 1
        assert events[0].customer_confirmed is False
        assert events[0].accepted_term is None
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_customer_states_a_correction_during_confirmation():
    """Neither a clean "yes" nor a clean "no" — the customer states a
    different value outright ("filling" instead). Mock-mode keyword
    detection finds no yes/no trigger, so this resolves as "correction":
    the new value flows through the same per-field fold-in as anything
    else stated this turn. "filling" is itself a seeded, standard-
    criticality term, so — unlike the critical root canal case — it's
    accepted directly without a second confirmation round."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="te-en-IN")
        state["pending_confirmation"] = {
            "field": "reason_for_visit", "raw_value": "నాకు ఫ్రూట్ కెనాల్స్ కావాలి",
            "candidate_value": "root canal treatment", "semantic_confidence": 1.0,
            "domain_term_id": None, "correction_method": "fuzzy_alias_match",
        }
        state["field_ask_counts"] = {"reason_for_visit": 1}
        state["awaiting_field"] = "reason_for_visit"
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC),
            )
        assert result.state["pending_confirmation"] is None
        assert result.state["known_fields"]["reason_for_visit"] == "filling"
        assert result.planner_action == "ASK_FIELD"
        assert result.state["awaiting_field"] == "preferred_date"
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_pending_question_blocks_premature_objective_completion():
    """An unanswered customer question must block COMPLETE_OBJECTIVE even
    when every field is already filled — the call defers instead of ending
    mid-question."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        state["known_fields"] = {
            "reason_for_visit": "root canal treatment", "preferred_date": "tomorrow", "preferred_time": "evening",
        }
        state["awaiting_field"] = None
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                # No knowledge base seeded in this workspace at all, so this
                # question is guaranteed to go unanswered (above_threshold
                # can never be True with zero chunks) regardless of wording.
                customer_utterance="what time do you close today?", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC),
            )
        assert result.planner_action == "DEFER_QUESTION"
        assert result.call_should_end is False
        assert result.state["objective_status"] != "completed"
        assert "team will confirm" in result.reply_text
    finally:
        await _cleanup(workspace_id)


# --- P3.5: engine_mode="fast" -------------------------------------------------


@pytest.mark.asyncio
async def test_fast_mode_do_not_call_never_touches_the_llm_at_all():
    """Spec §103 — the real point of FastTurnRouter: today (legacy mode) a
    do-not-call phrase still pays for a full extraction LLM call before
    policy.apply_backstop's safety net even matters. Fast mode must
    short-circuit before extractor.extract() is ever reached."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        counting_client = _CountingLLMClient()
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="please do not call again", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=counting_client, engine_mode="fast",
            )
        assert counting_client.complete_json_calls == 0
        assert counting_client.complete_text_calls == 0
        assert result.call_should_end is True
        assert result.end_reason == "do_not_call"
        assert result.state["last_turn_debug"]["turn_path"] == "fast_path"
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_fast_mode_no_rag_turn_skips_rag_entirely():
    """Spec §94/§98 — confirms conditional RAG (pre-existing behavior, not
    new in P3.5) holds under fast mode too: a plain field answer with no
    question in it must never trigger rag.search_knowledge()."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="tomorrow evening", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC), engine_mode="fast",
            )
        assert result.rag_chunks == []
        assert "rag" not in result.latency_ms
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_fast_mode_question_turn_still_runs_rag_and_answers_from_real_knowledge():
    """Spec §99 — customer question priority must survive fast mode: a
    question about approved knowledge still triggers real RAG and gets
    answered from it, exactly as legacy mode already does."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="root canal treatment costs between 8000 and 12000 rupees enta?",
                conversation_policy=ConversationPolicySnapshot(), business_identity="Aaha Dental Care",
                now=datetime.now(UTC), engine_mode="fast",
            )
        assert result.rag_chunks  # real chunk came back
        assert "8000" in result.reply_text or "12000" in result.reply_text
        assert "rag_embedding" in result.latency_ms
        assert "rag_vector_search" in result.latency_ms
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_fast_mode_ask_field_skips_the_second_llm_call_too():
    """Spec §100 — the full "no-RAG one-call target": in mock mode there
    was never an LLM call to skip in the first place (extraction already
    falls back to the heuristic), so this uses a real-shaped counting
    client standing in for "a real LLM IS configured" to prove the
    response-generation call specifically is skipped under fast mode."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        counting_client = _CountingLLMClient()
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=counting_client, engine_mode="fast",
            )
        assert result.planner_action == "ASK_FIELD"
        # extraction still ran for real (this utterance isn't a
        # fast_router-eligible case) — one complete_json call — but the
        # SEPARATE response-generation call is skipped entirely.
        assert counting_client.complete_json_calls == 1
        assert counting_client.complete_text_calls == 0
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_fast_mode_domain_correction_still_flags_for_confirmation():
    """Spec §102 — the real-call domain-mistranscription bug fix must
    survive fast mode unchanged: "fruit canals" isn't a fast_router-
    eligible utterance, so it falls through to real extraction + domain
    normalization exactly as legacy mode does."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id, agent_id = await _seed_workspace_with_dental_vocabulary()
    try:
        state = new_conversation_state(objective="book_appointment", language="te-en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="నాకు ఫ్రూట్ కెనాల్స్ కావాలి", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", agent_id=agent_id, now=datetime.now(UTC), engine_mode="fast",
            )
        assert result.planner_action == "CONFIRM_FIELD"
        assert "reason_for_visit" not in result.state["known_fields"]
        assert result.state["pending_confirmation"]["candidate_value"] == "root canal treatment"
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_legacy_mode_is_completely_unaffected_by_fast_router_existing():
    """The default (engine_mode not passed -> "legacy") must behave
    byte-identically to pre-P3.5: a do-not-call phrase still goes through
    real extraction (mock heuristic here), fast_router is never consulted."""
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
        assert result.state["last_turn_debug"]["turn_path"] == "mock"
    finally:
        await _cleanup(workspace_id)


# --- P5: streaming response_mode, end to end through the real engine -------


@pytest.mark.asyncio
async def test_streaming_response_mode_produces_reply_from_the_stream_and_records_latency():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        fake = _FakeStreamingLLMClient(events=[
            LLMResponseStarted(request_id="r1"),
            TextDelta(text="Sure, what date works for you?"),
            LLMResponseCompleted(full_text="Sure, what date works for you?"),
        ])
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake, response_mode="streaming",
            )
        assert fake.stream_text_call_count == 1
        assert fake.complete_text_calls == 0
        assert "what date works for you" in result.reply_text.lower()
        assert "llm_ttft" in result.latency_ms
        assert "llm_first_speakable_chunk" in result.latency_ms
        assert "llm_full_generation" in result.latency_ms
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_streaming_response_mode_invokes_on_speakable_chunk_through_process_turn():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        fake = _FakeStreamingLLMClient(events=[
            LLMResponseStarted(request_id="r1"),
            TextDelta(text="Sure, what date works?"),
            LLMResponseCompleted(full_text="Sure, what date works?"),
        ])
        seen: list[str] = []

        async def on_chunk(chunk):
            seen.append(chunk.text)

        async with workspace_scoped_session(workspace_id) as db:
            await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake, response_mode="streaming", on_speakable_chunk=on_chunk,
            )
        assert seen  # at least one chunk was surfaced in real time, during process_turn itself
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_streaming_response_mode_prompt_reflects_rag_evidence_gathered_before_streaming_started():
    """Spec §23-24: RAG must complete before streaming generation starts.
    Verified concretely (not just by code-reading the sequential awaits) —
    the retrieved chunk's own figures show up in the system prompt actually
    handed to stream_text(), which could only happen if RAG had already run."""
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        fake = _FakeStreamingLLMClient(events=[
            LLMResponseStarted(request_id="r1"),
            TextDelta(text="It costs between 8000 and 12000 rupees."),
            LLMResponseCompleted(full_text="It costs between 8000 and 12000 rupees."),
        ])
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="root canal treatment costs between 8000 and 12000 rupees enta?",
                conversation_policy=ConversationPolicySnapshot(), business_identity="Aaha Dental Care",
                now=datetime.now(UTC), llm_client=fake, response_mode="streaming",
            )
        assert result.rag_chunks
        assert fake.last_system is not None
        assert "8000" in fake.last_system
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_streaming_response_mode_never_used_for_do_not_call_closing():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        fake = _FakeStreamingLLMClient(events=[TextDelta(text="SHOULD NEVER BE USED")])
        async with workspace_scoped_session(workspace_id) as db:
            result = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="please do not call again", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake, response_mode="streaming",
            )
        assert fake.stream_text_call_count == 0
        assert result.call_should_end is True
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_streaming_response_mode_never_used_for_objective_completion():
    from jkr_db.session import workspace_scoped_session

    workspace_id, call_id = await _seed_workspace_with_knowledge_and_call()
    try:
        state = new_conversation_state(objective="book_appointment", language="en-IN")
        async with workspace_scoped_session(workspace_id) as db:
            turn1 = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=state,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
            )
            assert turn1.planner_action == "ASK_FIELD"  # reason_for_visit filled, preferred_date still open

            turn2 = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=turn1.state,
                customer_utterance="tomorrow", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
            )
            assert turn2.planner_action == "ASK_FIELD"  # preferred_date filled, preferred_time still open

            fake = _FakeStreamingLLMClient(events=[TextDelta(text="SHOULD NEVER BE USED")])
            turn3 = await engine.process_turn(
                db, workspace_id=workspace_id, call_session_id=call_id, state=turn2.state,
                customer_utterance="evening around 6pm", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake, response_mode="streaming",
            )
        assert turn3.planner_action == "COMPLETE_OBJECTIVE"
        assert fake.stream_text_call_count == 0
    finally:
        await _cleanup(workspace_id)


@pytest.mark.asyncio
async def test_streaming_response_mode_generation_ids_never_cross_between_two_calls():
    """Spec §105 — two-call isolation: chunks/generation state must never
    cross sessions. Two independently seeded workspaces/call sessions, each
    driven through process_turn(response_mode="streaming") with its own
    fake client, feeding the SAME on_chunk collector — proves nothing about
    one call's generation leaks into the other's."""
    from jkr_db.session import workspace_scoped_session

    workspace_id_a, call_id_a = await _seed_workspace_with_knowledge_and_call()
    workspace_id_b, call_id_b = await _seed_workspace_with_knowledge_and_call()
    seen: list[tuple[str, str]] = []  # (workspace label, generation_id)

    async def on_chunk_a(chunk):
        seen.append(("a", chunk.generation_id))

    async def on_chunk_b(chunk):
        seen.append(("b", chunk.generation_id))

    try:
        state_a = new_conversation_state(objective="book_appointment", language="en-IN")
        fake_a = _FakeStreamingLLMClient(events=[
            LLMResponseStarted(request_id="ra"), TextDelta(text="Reply for call A."),
            LLMResponseCompleted(full_text="Reply for call A."),
        ])
        async with workspace_scoped_session(workspace_id_a) as db:
            await engine.process_turn(
                db, workspace_id=workspace_id_a, call_session_id=call_id_a, state=state_a,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake_a, response_mode="streaming", on_speakable_chunk=on_chunk_a,
            )

        state_b = new_conversation_state(objective="book_appointment", language="en-IN")
        fake_b = _FakeStreamingLLMClient(events=[
            LLMResponseStarted(request_id="rb"), TextDelta(text="Reply for call B."),
            LLMResponseCompleted(full_text="Reply for call B."),
        ])
        async with workspace_scoped_session(workspace_id_b) as db:
            await engine.process_turn(
                db, workspace_id=workspace_id_b, call_session_id=call_id_b, state=state_b,
                customer_utterance="I need it for a filling", conversation_policy=ConversationPolicySnapshot(),
                business_identity="Aaha Dental Care", now=datetime.now(UTC),
                llm_client=fake_b, response_mode="streaming", on_speakable_chunk=on_chunk_b,
            )

        gen_ids_a = {gid for label, gid in seen if label == "a"}
        gen_ids_b = {gid for label, gid in seen if label == "b"}
        assert gen_ids_a and gen_ids_b
        assert gen_ids_a.isdisjoint(gen_ids_b)
    finally:
        await _cleanup(workspace_id_a)
        await _cleanup(workspace_id_b)
