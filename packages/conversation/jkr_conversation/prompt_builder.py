"""Builds the agent's spoken reply for the action the planner chose.

Structural safety rule (deliberate, not a prompt instruction the model could
ignore): SAFETY_STOP, HUMAN_HANDOFF, and COMPLETE_OBJECTIVE (every reason,
tool-backed or not) ALWAYS use pre-approved canned text via closing.py,
never free LLM generation — these are exactly the moments where an LLM
overclaiming ("your appointment is confirmed") or sounding non-final right
before a hangup would be worst. Free generation is reserved for the safe,
non-terminal cases: asking/clarifying/confirming a field, deferring on an
unanswered question, optionally folding in a RAG-grounded answer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from jkr_conversation import closing, formatter, objectives, policy
from jkr_conversation.language import get_language_profile, lang_prefix
from jkr_conversation.llm_client import LLMClient
from jkr_conversation.objectives import ObjectiveDefinition
from jkr_conversation.rag import first_sentence
from jkr_conversation.schemas import (
    ConversationPolicySnapshot,
    ExtractionResult,
    PlannerDecision,
    RagChunk,
)
from jkr_conversation.streaming_response import (
    CancellationToken,
    SpeakableChunk,
    StreamingResponseAssembler,
)


def _question_prefix(*, decision: PlannerDecision, rag_chunks: list[RagChunk], language: str) -> str:
    if not decision.answer_question_first:
        return ""
    if rag_chunks:
        snippet = first_sentence(rag_chunks[0].text)
        return snippet + ("" if snippet.endswith((".", "!", "?")) else ".") + " "
    return policy.fallback_text(kind="no_knowledge_match", language=language) + " "


def _fallback_text(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    objective: ObjectiveDefinition, language: str,
) -> str:
    prefix = _question_prefix(decision=decision, rag_chunks=rag_chunks, language=language)

    if decision.action == "CLARIFY" and decision.target_field:
        candidates = extraction.uncertain_fields.get(decision.target_field) or [
            extraction.extracted_fields.get(decision.target_field, "")
        ]
        return prefix + formatter.build_clarification(decision.target_field, candidates, language=language)

    if decision.action == "CONFIRM_FIELD" and decision.target_field:
        pending = state.get("pending_confirmation") or {}
        candidate_value = pending.get("candidate_value") or extraction.extracted_fields.get(decision.target_field, "")
        return prefix + formatter.build_confirmation(candidate_value, language=language)

    if decision.action == "ASK_FIELD" and decision.target_field:
        field_def = next((f for f in objective.fields if f.key == decision.target_field), None)
        question_text = field_def.question.get(lang_prefix(language), field_def.question["en"]) if field_def else ""
        return prefix + question_text

    if decision.action == "DEFER_QUESTION":
        # The objective would otherwise be done, but an unanswered question
        # blocks closing — reuse the honest "not sure, team will confirm"
        # fallback (no new template needed) rather than closing prematurely.
        return prefix.strip() or policy.fallback_text(kind="no_knowledge_match", language=language)

    # COMPLETE_OBJECTIVE never reaches here — generate() always returns its
    # canned closing.build_closing_text(...) before _fallback_text is called.
    return prefix.strip() or policy.fallback_text(kind="no_knowledge_match", language=language)


def _language_instruction(language: str) -> str:
    """Was previously one hardcoded line telling the model to code-switch
    regardless of the selected language profile — meaning "Telugu-only"/
    "Hindi-only"/"English-only" were never actually strict, since the LLM
    was always told to mix English in. Now conditional on
    jkr_conversation.language.get_language_profile()."""
    profile = get_language_profile(language)
    if profile.code_mixed:
        return (
            f"Speak naturally in {profile.display_name}-English, the way a real person code-switches in "
            f"everyday conversation — {profile.display_name} as the sentence foundation, common English "
            "business/domain words mixed in naturally where that's how a native speaker would actually talk, "
            "not a formal translation. Don't alternate languages artificially just because code-mixing is enabled. "
            f"Every sentence must still be grounded in {profile.display_name} — connecting words, verbs, and "
            f"sentence structure stay in {profile.display_name} even for a plain logistics question (e.g. asking "
            f"when to call back). Never answer in a fully English sentence with no {profile.display_name} in it; "
            "that reads as a jarring language switch to the customer, not natural code-mixing."
        )
    if profile.base_language == "en":
        return (
            "Speak natural, concise Indian English. Do not mix in Telugu or Hindi words unless the customer "
            "explicitly asks to switch languages."
        )
    return (
        f"Speak conversational {profile.display_name}. Avoid unnecessary English words — only use English for "
        "proper nouns or standard technical/business terms that would sound unnatural if translated (e.g. the "
        "business's own vocabulary may already use an English term). Do not deliberately code-switch."
    )


# P10 §42 — a starting point, not a measured-optimal value (same honest
# framing every other tunable constant in this codebase carries — e.g.
# turns/policies.py's own FAST/BALANCED/PATIENT presets). "Recent" is
# whatever the caller's own window means (streaming_bridge.py's
# turn_state.recent_interrupt_count is a running per-call count, never
# reset mid-call — see docs/P10_REAL_CALL_BENCHMARK.md for why a per-call
# running count was chosen over a decaying/windowed one for this first pass).
ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD = 2


def _brevity_instruction(recent_interrupt_count: int) -> str:
    """P10 §42 — architecture already exists (P8 tracks
    recent_interrupt_count; this is the first thing that actually reads
    it). Deliberately ONLY a style hint appended to the existing SPEECH
    STYLE section — never touches RAG facts, tool behavior, or safety
    rules, which live in separate, untouched sections of the prompt."""
    if recent_interrupt_count < ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD:
        return ""
    return (
        " This customer has interrupted you several times — they clearly prefer short, direct exchanges. "
        "Answer in one short sentence wherever possible and skip anything not strictly necessary right now."
    )


def _build_prompt(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    objective: ObjectiveDefinition, business_identity: str, language: str, recent_turns: list[dict] | None,
    recent_interrupt_count: int = 0,
) -> tuple[str, str]:
    known_lines = "\n".join(f"- {k}: {v}" for k, v in state.get("known_fields", {}).items()) or "(none yet)"
    rag_lines = "\n".join(f"- {c.text}" for c in rag_chunks[:2]) if rag_chunks else "(none retrieved)"
    recent_lines = "\n".join(f"{t['speaker']}: {t['text']}" for t in (recent_turns or [])[-4:]) or "(this is the first exchange)"

    target_field_line = ""
    if decision.target_field:
        field_def = next((f for f in objective.fields if f.key == decision.target_field), None)
        if field_def:
            target_field_line = f"Ask about: {field_def.extraction_hint}"

    action_guidance = ""
    if decision.action == "CONFIRM_FIELD" and decision.target_field:
        pending = state.get("pending_confirmation") or {}
        candidate_value = pending.get("candidate_value", "")
        action_guidance = (
            f'You may have misheard a value the customer gave: "{candidate_value}". Double-check it '
            "naturally, the way a real person confirms something mid-conversation — NEVER the robotic "
            '"You said X, is that correct?" phrasing. One short question only.'
        )
    elif decision.action == "DEFER_QUESTION":
        action_guidance = (
            "You could not confidently answer the customer's question from APPROVED KNOWLEDGE above. "
            "Acknowledge that honestly — say you're not fully sure and the team will confirm. Do NOT say "
            "anything that signals the call is ending; the conversation continues after this."
        )

    system = (
        f"IDENTITY\nYou are the AI voice assistant for {business_identity}. You already clearly "
        f"identified yourself as an AI at the start of this call.\n\n"
        f"CALL OBJECTIVE\n{objective.id.replace('_', ' ')}\n\n"
        f"LANGUAGE\n{_language_instruction(language)}\n\n"
        f"CUSTOMER STATE\nAlready known:\n{known_lines}\n\n"
        f"RECENT CONVERSATION\n{recent_lines}\n\n"
        + (f"CUSTOMER QUESTION TO ANSWER FIRST\n{extraction.rewritten_query}\n\n" if decision.answer_question_first else "")
        + "APPROVED KNOWLEDGE (use ONLY this to answer factual questions — never state a price, hour, "
        f"policy, or fact not present here)\n{rag_lines}\n\n"
        + (f"CUSTOMER OBJECTION TO ACKNOWLEDGE\n{decision.objection}\n\n" if decision.objection else "")
        + f"NEXT ACTION\n{decision.action}. {target_field_line}\n\n"
        + (f"ACTION GUIDANCE\n{action_guidance}\n\n" if action_guidance else "")
        + "SAFETY RULES\nNever invent a fact not in APPROVED KNOWLEDGE above. If asked something not "
        "covered there, say you're not fully sure and the team will confirm — never guess. Never claim "
        "a booking/order/payment is confirmed unless told it already succeeded. Never repeat a question "
        "about information already given in CUSTOMER STATE above.\n\n"
        # P5 §21-22: real, not hypothetical — a live probe against this
        # exact prompt shape (docs/P5_STREAMING_LLM_AUDIT.md) caught the
        # model opening a Telugu-English response with a bare English
        # "Sure!" before anything useful, 2 of 3 times. Streaming makes
        # this worse than it already was: the first chunk spoken is
        # whatever opens the response, so a generic opener wastes the
        # exact head-start streaming exists to create.
        "SPEECH STYLE\nOne or two short sentences, like a real phone conversation — not a written "
        "paragraph. No markdown, no lists, no bullet points, no headers. Start the sentence with the "
        "actual useful answer or action — never open with a generic filler phrase like \"Sure\", "
        "\"Okay\", \"Absolutely\", \"I understand\", or \"I'd be happy to help\" before getting to the "
        "point. If there's a follow-up question to ask, put it after the answer, not before it."
        + _brevity_instruction(recent_interrupt_count)
    )
    return system, "Generate the agent's next spoken line now."


#  P3.5 §42-46: ASK_FIELD/CLARIFY/CONFIRM_FIELD/DEFER_QUESTION each already
# have a tested, natural, per-language canned template (_fallback_text ->
# objective field questions / build_clarification / build_confirmation /
# the shared "not fully sure" fallback) — the exact same templates mock
# mode has used unconditionally all along. Under engine_mode=="fast" these
# are trusted directly instead of also paying for a second LLM call whose
# job would only be to phrase something very similar. Deliberately NOT
# implemented as "ask the model to co-produce a draft in the SAME call as
# extraction" (this phase's spec's literal suggestion) — the deterministic
# planner decides target_field/rag_query/answer_question_first AFTER
# extraction runs, so an extraction-time draft can't know what it's
# actually responding to; reusing the already-correct canned templates for
# the decision the real planner made avoids a second, competing source of
# "what should happen next" truth. See docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md §4.
_FAST_RESPONSE_ELIGIBLE_ACTIONS = {"ASK_FIELD", "CLARIFY", "CONFIRM_FIELD", "DEFER_QUESTION"}


async def generate(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    conversation_policy: ConversationPolicySnapshot, business_identity: str, language: str,
    recent_turns: list[dict] | None, llm_client: LLMClient | None, engine_mode: str = "legacy",
    # P5 — all four default to no-op/complete-mode behavior, so every
    # existing call site (and its `-> str` return type) is unaffected.
    # response_mode only ever takes effect in the free-generation branch
    # below — SAFETY_STOP/HUMAN_HANDOFF/COMPLETE_OBJECTIVE/fast-path-eligible
    # turns return before reaching it, streaming or not, unchanged from P3.5.
    response_mode: str = "complete",  # "complete" | "streaming"
    on_speakable_chunk: Callable[[SpeakableChunk], Awaitable[None] | None] | None = None,
    latency_sink: dict[str, int] | None = None,
    cancellation_token: CancellationToken | None = None,
    recent_interrupt_count: int = 0,
) -> str:
    objective = objectives.get_objective(state.get("objective", objectives.DEFAULT_OBJECTIVE_ID))

    if decision.action == "SAFETY_STOP":
        kind = "do_not_call" if extraction.do_not_call else "wrong_number"
        return policy.fallback_text(kind=kind, language=language)

    if decision.action == "HUMAN_HANDOFF":
        return policy.fallback_text(kind="human_handoff", language=language)

    if decision.action == "COMPLETE_OBJECTIVE":
        # Every objective completion — tool-backed or not — always uses the
        # centralized, deterministic closing system, never free generation.
        # This is the direct fix for the abrupt-hangup bug: a freely
        # generated closing could sound non-final ("if tomorrow morning
        # works...") right before the call hangs up.
        if state.get("reopened_from_closing"):
            # The customer kept talking after the closing already played
            # once (grace-period reopen — see service.py's
            # _reopen_conversation_state) and the objective re-completed
            # with nothing new to add. Repeating the full closing script
            # verbatim reads as a broken robot; reaffirm briefly instead.
            reason_key = closing.REOPENED_REAFFIRM
        elif decision.reason in ("max_turns_reached", "max_duration_reached"):
            reason_key = closing.CALL_TIME_LIMIT
        else:
            reason_key = closing.OBJECTIVE_COMPLETED
        return closing.build_closing_text(
            reason_key, objective=objective, language=language, context=closing.build_context(state)
        )

    fallback = _fallback_text(decision=decision, extraction=extraction, state=state, rag_chunks=rag_chunks, objective=objective, language=language)

    if llm_client is None:
        return fallback

    if engine_mode == "fast" and decision.action in _FAST_RESPONSE_ELIGIBLE_ACTIONS:
        return fallback

    system, user = _build_prompt(
        decision=decision, extraction=extraction, state=state, rag_chunks=rag_chunks, objective=objective,
        business_identity=business_identity, language=language, recent_turns=recent_turns,
        recent_interrupt_count=recent_interrupt_count,
    )

    if response_mode == "streaming":
        # LLMClient (the Protocol every module in this package types against)
        # deliberately does NOT declare stream_text — only OpenAILLMClient
        # has it so far, and a test double / future provider without
        # streaming support must be able to satisfy LLMClient without also
        # implementing it. getattr(..., None), not hasattr + a typed call,
        # so a client lacking it degrades to complete-mode's fallback below
        # rather than mypy needing (and failing to find) it on the Protocol.
        stream_text = getattr(llm_client, "stream_text", None)
        if stream_text is not None:
            text = await _generate_streaming(
                stream_text=stream_text, system=system, user=user, on_speakable_chunk=on_speakable_chunk,
                latency_sink=latency_sink, cancellation_token=cancellation_token,
            )
            return text if text else fallback

    try:
        text = await llm_client.complete_text(system=system, user=user, max_tokens=150)
    except Exception:  # noqa: BLE001 — a client that violates its own "never raise" contract must still fall back
        text = None
    return text if text else fallback


async def _generate_streaming(
    *, stream_text: Callable[..., object], system: str, user: str,
    on_speakable_chunk: Callable[[SpeakableChunk], Awaitable[None] | None] | None,
    latency_sink: dict[str, int] | None, cancellation_token: CancellationToken | None,
) -> str | None:
    """Isolated from generate() itself so a client that violates its "never
    raise" contract mid-stream (see llm_client.py's own docstring on this)
    still falls back to canned text instead of taking the call down — same
    guarantee the complete-mode branch already has via its own try/except."""
    try:
        assembler = StreamingResponseAssembler()
        event_stream = stream_text(system=system, user=user, max_tokens=150)
        result = await assembler.run(
            event_stream, cancellation_token=cancellation_token, on_chunk=on_speakable_chunk,
        )
    except Exception:  # noqa: BLE001
        return None

    if latency_sink is not None:
        if result.ttft_ms is not None:
            latency_sink["llm_ttft"] = result.ttft_ms
        if result.first_speakable_chunk_ms is not None:
            latency_sink["llm_first_speakable_chunk"] = result.first_speakable_chunk_ms
        latency_sink["llm_full_generation"] = result.full_generation_ms

    return result.full_text
