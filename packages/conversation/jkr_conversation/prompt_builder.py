"""Builds the agent's spoken reply for the action the planner chose.

Structural safety rule (deliberate, not a prompt instruction the model could
ignore): SAFETY_STOP, HUMAN_HANDOFF, and COMPLETE_OBJECTIVE on a
tool-backed objective (e.g. book_appointment) ALWAYS use pre-approved canned
text, never free LLM generation — these are exactly the moments where an
LLM overclaiming ("your appointment is confirmed") before the tool has
actually run would be worst. Free generation is reserved for the safe
cases: asking/clarifying a field, optionally folding in a RAG-grounded
answer to a question the customer also asked.
"""

from __future__ import annotations

from jkr_conversation import formatter, objectives, policy
from jkr_conversation.language import lang_prefix
from jkr_conversation.llm_client import LLMClient
from jkr_conversation.objectives import ObjectiveDefinition
from jkr_conversation.rag import first_sentence
from jkr_conversation.schemas import (
    ConversationPolicySnapshot,
    ExtractionResult,
    PlannerDecision,
    RagChunk,
)


def _question_prefix(*, decision: PlannerDecision, rag_chunks: list[RagChunk], language: str) -> str:
    if not decision.answer_question_first:
        return ""
    if rag_chunks:
        snippet = first_sentence(rag_chunks[0].text)
        return snippet + ("" if snippet.endswith((".", "!", "?")) else ".") + " "
    return policy.fallback_text(kind="no_knowledge_match", language=language) + " "


def _fallback_text(
    *, decision: PlannerDecision, extraction: ExtractionResult, rag_chunks: list[RagChunk],
    objective: ObjectiveDefinition, language: str,
) -> str:
    prefix = _question_prefix(decision=decision, rag_chunks=rag_chunks, language=language)

    if decision.action == "CLARIFY" and decision.target_field:
        candidates = extraction.uncertain_fields.get(decision.target_field) or [
            extraction.extracted_fields.get(decision.target_field, "")
        ]
        return prefix + formatter.build_clarification(decision.target_field, candidates, language=language)

    if decision.action == "ASK_FIELD" and decision.target_field:
        field_def = next((f for f in objective.fields if f.key == decision.target_field), None)
        question_text = field_def.question.get(lang_prefix(language), field_def.question["en"]) if field_def else ""
        return prefix + question_text

    if decision.action == "COMPLETE_OBJECTIVE":
        return prefix + objective.closing_text.get(lang_prefix(language), objective.closing_text["en"])

    return prefix.strip() or policy.fallback_text(kind="no_knowledge_match", language=language)


def _build_prompt(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    objective: ObjectiveDefinition, business_identity: str, language: str, recent_turns: list[dict] | None,
) -> tuple[str, str]:
    known_lines = "\n".join(f"- {k}: {v}" for k, v in state.get("known_fields", {}).items()) or "(none yet)"
    rag_lines = "\n".join(f"- {c.text}" for c in rag_chunks[:2]) if rag_chunks else "(none retrieved)"
    recent_lines = "\n".join(f"{t['speaker']}: {t['text']}" for t in (recent_turns or [])[-4:]) or "(this is the first exchange)"

    target_field_line = ""
    if decision.target_field:
        field_def = next((f for f in objective.fields if f.key == decision.target_field), None)
        if field_def:
            target_field_line = f"Ask about: {field_def.extraction_hint}"

    system = (
        f"IDENTITY\nYou are the AI voice assistant for {business_identity}. You already clearly "
        f"identified yourself as an AI at the start of this call.\n\n"
        f"CALL OBJECTIVE\n{objective.id.replace('_', ' ')}\n\n"
        f"LANGUAGE\nSpeak naturally in {language} — mixing English words into Telugu/Hindi sentences "
        f"where that's how a real person would talk (code-switching), not a formal translation.\n\n"
        f"CUSTOMER STATE\nAlready known:\n{known_lines}\n\n"
        f"RECENT CONVERSATION\n{recent_lines}\n\n"
        + (f"CUSTOMER QUESTION TO ANSWER FIRST\n{extraction.rewritten_query}\n\n" if decision.answer_question_first else "")
        + "APPROVED KNOWLEDGE (use ONLY this to answer factual questions — never state a price, hour, "
        f"policy, or fact not present here)\n{rag_lines}\n\n"
        + (f"CUSTOMER OBJECTION TO ACKNOWLEDGE\n{decision.objection}\n\n" if decision.objection else "")
        + f"NEXT ACTION\n{decision.action}. {target_field_line}\n\n"
        "SAFETY RULES\nNever invent a fact not in APPROVED KNOWLEDGE above. If asked something not "
        "covered there, say you're not fully sure and the team will confirm — never guess. Never claim "
        "a booking/order/payment is confirmed unless told it already succeeded. Never repeat a question "
        "about information already given in CUSTOMER STATE above.\n\n"
        "SPEECH STYLE\nOne or two short sentences, like a real phone conversation — not a written "
        "paragraph. No markdown, no lists, no bullet points, no headers."
    )
    return system, "Generate the agent's next spoken line now."


async def generate(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    conversation_policy: ConversationPolicySnapshot, business_identity: str, language: str,
    recent_turns: list[dict] | None, llm_client: LLMClient | None,
) -> str:
    objective = objectives.get_objective(state.get("objective", objectives.DEFAULT_OBJECTIVE_ID))

    if decision.action == "SAFETY_STOP":
        kind = "do_not_call" if extraction.do_not_call else "wrong_number"
        return policy.fallback_text(kind=kind, language=language)

    if decision.action == "HUMAN_HANDOFF":
        return policy.fallback_text(kind="human_handoff", language=language)

    if decision.action == "COMPLETE_OBJECTIVE" and objective.tool_on_completion:
        return objective.closing_text.get(lang_prefix(language), objective.closing_text["en"])

    fallback = _fallback_text(decision=decision, extraction=extraction, rag_chunks=rag_chunks, objective=objective, language=language)

    if llm_client is None:
        return fallback

    system, user = _build_prompt(
        decision=decision, extraction=extraction, state=state, rag_chunks=rag_chunks, objective=objective,
        business_identity=business_identity, language=language, recent_turns=recent_turns,
    )
    try:
        text = await llm_client.complete_text(system=system, user=user, max_tokens=150)
    except Exception:  # noqa: BLE001 — a client that violates its own "never raise" contract must still fall back
        text = None
    return text if text else fallback
