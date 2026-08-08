"""Typed contracts for the shared conversation engine — see engine.py's
process_turn() for how these compose. Plain dataclasses, not Pydantic: this
package has no FastAPI/request-validation boundary of its own, and every
caller (voice-worker, services/api) already has its own request/response
schemas at its own edge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jkr_conversation.formatter import FormattedResponse


@dataclass(frozen=True)
class ConversationPolicySnapshot:
    """Plain-dict-constructible snapshot of the ConversationPolicy columns
    this package needs — not the ORM row, so a caller that can't cheaply hold
    an ORM object across a request boundary (live_call's Redis-backed state)
    can build one from a plain cached dict just as easily as
    conversation_engine.py can build one from the ORM row it already has."""

    max_response_sentences: int = 3
    human_transfer_enabled: bool = True
    do_not_call_behavior: str = "immediate_suppress"
    wrong_number_behavior: str = "apologize_and_suppress"
    clarification_behavior: str = "ask_dont_guess"
    confirmation_behavior: str = "confirm_critical"
    max_turns: int = 30
    max_call_duration_seconds: int = 300


@dataclass(frozen=True)
class RagChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    text: str
    score: float
    distance: float


@dataclass(frozen=True)
class ExtractionResult:
    """Structured output of one customer utterance — either a real LLM JSON-
    mode call (extractor.py's real path) or a deterministic heuristic
    (mock-mode fallback, is_mock=True). `extracted_fields` may contain zero,
    one, or several field keys in a single turn — this is what lets "CSE
    kavali, rank 28000, hostel kuda kavali" fill three fields at once instead
    of one per turn."""

    turn_intent: str  # "answer" | "question" | "objection" | "small_talk" | "silence" | "other"
    extracted_fields: dict[str, str] = field(default_factory=dict)
    field_confidence: dict[str, float] = field(default_factory=dict)
    uncertain_fields: dict[str, list[str]] = field(default_factory=dict)
    detected_question: bool = False
    rewritten_query: str | None = None
    objection: str | None = None
    wants_human: bool = False
    wrong_number: bool = False
    do_not_call: bool = False
    sentiment: str = "neutral"  # "positive" | "neutral" | "negative"
    is_mock: bool = True
    raw_model_output: dict | None = None


@dataclass(frozen=True)
class PlannerDecision:
    """The planner's single exclusive next action, plus non-exclusive
    annotations layered on top of it — see planner.py's docstring for why
    "answer the customer's question" is a modifier rather than its own rung
    on the priority ladder (it composes with ASK_FIELD in the same turn, the
    same way the mock engine already prepends a knowledge answer in front of
    the next scripted question today)."""

    action: str  # "SAFETY_STOP" | "HUMAN_HANDOFF" | "CLARIFY" | "ASK_FIELD" | "COMPLETE_OBJECTIVE"
    reason: str
    target_field: str | None = None
    answer_question_first: bool = False
    rag_query: str | None = None
    objection: str | None = None


@dataclass(frozen=True)
class ToolCallRequest:
    """A tool the engine has decided should run — the caller (voice-worker's
    conversation_engine.py, or live_call's service.py) actually executes it
    via jkr_db.tools_engine.execute_tool, since that call needs a live DB
    session and workspace/contact context this package doesn't hold."""

    tool_name: str
    tool_input: dict
    idempotency_suffix: str


@dataclass(frozen=True)
class ConversationTurnResult:
    reply_text: str
    formatted: FormattedResponse
    state: dict
    planner_action: str
    planner_reason: str
    extraction: ExtractionResult
    rag_chunks: list[RagChunk]
    call_should_end: bool
    end_reason: str | None  # "objective_completed" | "do_not_call" | "wrong_number" | "max_turns_reached" | "max_duration_reached" | None
    tool_calls_requested: list[ToolCallRequest]
    latency_ms: dict[str, int]
