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


def _question_prefix(
    *, decision: PlannerDecision, extraction: ExtractionResult | None = None, rag_chunks: list[RagChunk], language: str
) -> str:
    if not decision.answer_question_first:
        return ""
    if rag_chunks:
        snippet = first_sentence(rag_chunks[0].text)
        return snippet + ("" if snippet.endswith((".", "!", "?")) else ".") + " "
    if extraction and extraction.question_type == "general_knowledge":
        return ""
    return policy.fallback_text(kind="no_knowledge_match", language=language) + " "


def _fallback_text(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    objective: ObjectiveDefinition, language: str,
) -> str:
    prefix = _question_prefix(decision=decision, extraction=extraction, rag_chunks=rag_chunks, language=language)

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

    if decision.action == "HANDLE_OBJECTION":
        from jkr_conversation import objections
        primary_cat = (decision.objection or "").split(",")[0].strip()
        spoken = objections.get_spoken_objection_fallback(primary_cat, language=language)
        return (prefix + (" " if prefix and spoken else "") + spoken).strip()

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
    recent_interrupt_count: int = 0, customer_utterance: str = "",
) -> tuple[str, str]:
    known_lines = "\n".join(f"- {k}: {v}" for k, v in state.get("known_fields", {}).items()) or "(none yet)"
    rag_lines = "\n".join(f"- {c.text}" for c in rag_chunks[:2]) if rag_chunks else "(none retrieved)"
    recent_lines = "\n".join(f"{t['speaker']}: {t['text']}" for t in (recent_turns or [])[-6:]) or "(this is the first exchange)"

    personality = str(state.get("personality", "warm receptionist")).replace("_", " ").title()
    formality = str(state.get("formality", "balanced"))
    energy = str(state.get("energy", "medium"))
    response_length = str(state.get("response_length", "short"))

    target_field_line = ""
    if decision.target_field:
        field_def = next((f for f in objective.fields if f.key == decision.target_field), None)
        if field_def:
            target_field_line = f"Next field needed from customer: {field_def.extraction_hint} ({field_def.key})"

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
        if extraction.question_type == "general_knowledge":
            action_guidance = (
                "The customer asked a general knowledge or conversational question. Answer it directly, "
                "accurately, and conversationally in 1-2 concise spoken sentences using your general knowledge. "
                "Do NOT use fallback phrases like 'team will confirm' or 'not sure' for general knowledge questions."
            )
        else:
            action_guidance = (
                "You could not confidently answer the customer's specific business question from APPROVED KNOWLEDGE above. "
                "Acknowledge that honestly and politely — say you don't have those specific details on hand and our team will confirm. "
                "Do NOT say anything that signals the call is ending; keep the conversation flowing smoothly."
            )
    elif decision.action == "HANDLE_OBJECTION":
        from jkr_conversation import objections
        detected_cats = [c.strip() for c in (decision.objection or "").split(",") if c.strip()]
        guidance = objections.build_objection_guidance(detected_cats, language=language)
        action_guidance = (
            f"The customer raised this concern/objection: \"{decision.objection}\".\n"
            f"OBJECTION GUIDANCE: {guidance}\n"
            "Be empathetic, respectful, and helpful. Acknowledge their point naturally, answer using approved knowledge, "
            "explain genuine value, and do NOT pressure them into an appointment prematurely."
        )

    question_section = ""
    if extraction.turn_intent == "small_talk":
        question_section = (
            f"CUSTOMER CHIT-CHAT / GREETING:\n"
            f'"{customer_utterance}"\n'
            "GUIDANCE: Respond warmly, politely, and naturally to this greeting or small talk in 1 short conversational sentence (e.g., 'I'm doing well, thank you for asking!'). "
            "NEVER say you don't know, don't have details, or that your team will confirm — this is friendly small talk. Then smoothly proceed with the planned next action.\n\n"
        )
    elif decision.answer_question_first:
        if extraction.question_type == "general_knowledge":
            question_section = (
                f"CUSTOMER QUESTION TO ANSWER (General Knowledge / Concepts):\n"
                f'"{extraction.rewritten_query or customer_utterance}"\n'
                "GUIDANCE FOR THIS QUESTION: Answer this directly, intelligently, and conversationally in 1-2 concise spoken sentences using your general knowledge (e.g. explain the term/concept simply and clearly). "
                "DO NOT say you don't know or that your team will confirm — this is general world knowledge, not proprietary company data. Then continue naturally with the planned next action.\n\n"
            )
        elif rag_chunks:
            question_section = (
                f"CUSTOMER QUESTION TO ANSWER (Business Knowledge - Grounded):\n"
                f'"{extraction.rewritten_query or customer_utterance}"\n'
                "GUIDANCE FOR THIS QUESTION: Answer this question concisely using APPROVED KNOWLEDGE above, then smoothly proceed with the planned next action.\n\n"
            )
        else:
            question_section = (
                f"CUSTOMER QUESTION TO ANSWER (Business Knowledge - No Confident Match):\n"
                f'"{extraction.rewritten_query or customer_utterance}"\n'
                "GUIDANCE FOR THIS QUESTION: Since this is a specific business question not found in APPROVED KNOWLEDGE, politely let the caller know you don't have those exact details on hand and the team will confirm them, then smoothly continue with the planned next action.\n\n"
            )

    clean_biz = (business_identity or "").strip() or "Our Business"

    is_clothing = any(k in clean_biz.lower() for k in ["cloth", "apparel", "wear", "boutique", "fashion", "garment", "textile"])
    customer_name = state.get("customer_name") or "there"
    cust_greeting_target = customer_name if customer_name not in ("there", "Customer", "none") else "the customer"

    if is_clothing:
        service_name = state.get("service_name") or "clothing collections, sizes, and offers"
        calling_reason = state.get("calling_reason") or f"following up on your inquiry with {clean_biz} regarding our latest clothing collections, offers, and sizing"
        step_3 = "3. Ask preferences: Ask what styles, sizes, outfits, or special offers they are looking for."
        step_5 = "5. Confirm selection: Once their preference or size is mentioned, summarize and confirm the item or store visit with them."
        step_6 = "6. If confirmed: Enthusiastically confirm their order or visit details! Let them know a catalog/confirmation message is on its way to their WhatsApp/phone."
    elif objective.id == "book_appointment":
        service_name = state.get("service_name") or "our consultation and appointment services"
        calling_reason = state.get("calling_reason") or f"following up regarding your inquiry with {clean_biz} to schedule or confirm your appointment"
        step_3 = "3. Ask availability: Ask when they are free so you can schedule or confirm their appointment."
        step_5 = "5. Ask confirmation: Once their availability is mentioned, explicitly confirm the appointment date and time."
        step_6 = "6. If confirmed: Enthusiastically confirm the appointment is booked! Let them know a confirmation message with the date and time is on its way to their phone."
    elif objective.id == "renewal_reminder":
        service_name = state.get("service_name") or "account renewal and payment options"
        calling_reason = state.get("calling_reason") or f"courtesy call from {clean_biz} regarding your account and upcoming payment"
        step_3 = "3. Check status: Inquire if they have had a chance to review their renewal or upcoming due date."
        step_5 = "5. Confirm payment method: Confirm their preferred payment method (UPI / online link / bank)."
        step_6 = "6. If confirmed: Thank them and confirm payment link has been dispatched to their phone."
    else:
        service_name = state.get("service_name") or "our services and products"
        calling_reason = state.get("calling_reason") or f"following up on your inquiry with {clean_biz} to assist you and provide details"
        step_3 = "3. Ask requirements: Ask what specific information or assistance they are looking for."
        step_5 = "5. Confirm details: Summarize and confirm their preferences or request."
        step_6 = "6. If confirmed: Enthusiastically confirm the details and inform them that our team will follow up on WhatsApp/phone."

    call_context_section = (
        "CALL CONTEXT & PURPOSE\n"
        f"- Calling on behalf of: {clean_biz}\n"
        f"- Customer name: {customer_name}\n"
        f"- Reason for this call: {calling_reason}\n"
        f"- Domain focus: {service_name}\n\n"
        "CALL SCRIPT FLOW (Natural spoken execution — do not recite mechanically, move forward each turn):\n"
        f"1. Open: Greet {cust_greeting_target} warmly, state your name and that you are calling from {clean_biz}.\n"
        f"2. Reference reason: Clearly state why you are calling: {calling_reason}.\n"
        f"{step_3}\n"
        "4. Handle questions: If they ask anything about the business, products, pricing, or policies, answer genuinely using APPROVED KNOWLEDGE or general context — then steer back to the flow.\n"
        f"{step_5}\n"
        f"{step_6}\n"
        "7. If declined / not interested: Thank them warmly and sincerely for their time ('సరే అండి, మీ సమయానికి చాలా ధన్యవాదాలు! ఉంటానండి' / 'Thank you so much for your time, have a great day!'), and end the call gracefully without pushing.\n\n"
    )

    system = (
        f"IDENTITY & PERSONA\n"
        f"You are {clean_biz}'s AI voice assistant speaking live on a telephone call. "
        f"Persona: {personality}. Tone: {formality}, warm, and energetic ({energy}). "
        f"You already clearly identified yourself as an AI at the start of this call.\n\n"
        + call_context_section
        + f"CALL OBJECTIVE\n{objective.id.replace('_', ' ')}\n\n"
        f"LANGUAGE\n{_language_instruction(language)}\n\n"
        f"CUSTOMER STATE\nAlready known:\n{known_lines}\n\n"
        f"RECENT CONVERSATION (Dialogue History)\n{recent_lines}\n\n"
        + question_section
        + "APPROVED KNOWLEDGE (use ONLY this to answer company-specific factual questions — never state a price, hour, "
        f"policy, or fact not present here)\n{rag_lines}\n\n"
        + (f"CUSTOMER OBJECTION TO ACKNOWLEDGE\n{decision.objection}\n\n" if decision.objection else "")
        + f"PLANNED NEXT ACTION\n{decision.action}. {target_field_line}\n\n"
        + (f"ACTION GUIDANCE\n{action_guidance}\n\n" if action_guidance else "")
        + "CONVERSATIONAL RULES & KNOWLEDGE GROUNDING\n"
        "1. Real understanding: Listen carefully to what the caller says. Respond intelligently, naturally, and contextually to their actual words.\n"
        "2. Empathetic Representative: Be a polite, helpful, persuasive representative — NEVER an aggressive confirmation robot. First understand the customer, answer concerns, explain value, build trust, and handle objections. Only offer next steps when value is established or the customer is ready.\n"
        "3. Structured Objection Handling: If the customer asks about price, trust, doubts, competitor, timing, or needs time to discuss with family/team, address their exact concern with empathy and factual points from APPROVED KNOWLEDGE. Never push ahead while they have unanswered concerns.\n"
        "4. General Knowledge & Chit-chat: If the caller asks a general knowledge question (e.g., definitions, technology, world facts), greets you, or makes small talk, answer directly, smartly, and warmly using your general knowledge. NEVER give a canned 'not sure / team will confirm' fallback for general knowledge questions or small talk.\n"
        "5. Factual Grounding for Business: For business-specific claims (prices, operating hours, policies, specific catalog items), rely strictly on APPROVED KNOWLEDGE above. Never invent business facts or discounts not present in APPROVED KNOWLEDGE.\n"
        "6. Business Knowledge Gaps: ONLY for specific proprietary questions where no matching info exists in APPROVED KNOWLEDGE, politely say you don't have those specific details on hand and offer to have the team confirm.\n"
        "7. Spoken Natural Sentences: Use short spoken sentences suitable for a live phone call. Avoid robotic repetition.\n"
        "8. Confusion & Repeat Requests: If the caller didn't hear you, asks you to repeat ('what did you say', 'repeat that', 'pardon'), warmly and clearly repeat or rephrase your last statement or question in simpler words. Do not ignore their request to repeat.\n"
        "9. Impatience & Directness: If the caller is impatient or asks you to get to the point, immediately state the purpose of the call crisply in one polite sentence without unnecessary pleasantries.\n"
        "10. Genuine Disinterest & Graceful Close: If the caller states they are not interested: never argue, never push, and respect their decision immediately: thank them warmly and sincerely in the call ('సరే అండి, ఏమీ పర్వాలేదు. మీ సమయానికి చాలా ధన్యవాదాలు! ఉంటానండి' / 'Thank you so much for your time, have a great day!') and gracefully conclude.\n"
        "11. AI Identity & Transparency: If asked about your identity ('what is your name', 'are you human', 'are you an AI'), be completely transparent, honest, and friendly. Confirm you are the AI assistant for the business and are here to help them.\n"
        "12. Closing Finality: Once the next action is confirmed or the customer has declined, do not repeat generic acknowledgments or re-open the pitch. If the customer says 'Thank you', 'Okay', 'Thanks', or 'Bye', reply with a warm, single-sentence farewell and conclude.\n\n"
        "ANTI-REPETITION & PROGRESSION GUARD\n"
        "- Carefully review RECENT CONVERSATION (Dialogue History) above.\n"
        "- NEVER repeat any phrase, greeting, introduction, or sentence you already said earlier in the call.\n"
        "- If you already introduced yourself or stated why you are calling in an earlier turn, DO NOT repeat who you are or why you called! Move directly to the next step.\n"
        f"- Use the customer's name ({customer_name}) naturally once or twice across the call, NEVER repeat their name in every sentence.\n"
        "- Move the conversation forward on EVERY turn.\n\n"
        "SPEECH STYLE\n"
        f"Spoken dialogue ({response_length}): one or two short sentences, like a real phone conversation — not a written essay. "
        "No markdown, no bullets, no lists, no headers, no emojis. "
        "Acknowledge the customer's point naturally before moving to the next action. "
        "Do not repeat robotic filler openers verbatim every turn."
        + _brevity_instruction(recent_interrupt_count)
    )

    prompted_utterance = customer_utterance.strip()
    if not prompted_utterance and decision.answer_question_first and extraction.rewritten_query:
        prompted_utterance = extraction.rewritten_query

    if prompted_utterance:
        user = (
            f'Customer said: "{prompted_utterance}"\n\n'
            f"Generate the agent's next spoken response to the customer now."
        )
    else:
        user = "Generate the agent's next spoken line now."

    return system, user


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
_FAST_RESPONSE_ELIGIBLE_ACTIONS = {"ASK_FIELD", "CLARIFY", "CONFIRM_FIELD", "DEFER_QUESTION", "HANDLE_OBJECTION"}


def _is_repetition(candidate: str, previous_text: str) -> bool:
    if not candidate or not previous_text:
        return False
    cand_clean = " ".join(candidate.strip().lower().split())
    prev_clean = " ".join(previous_text.strip().lower().split())
    if cand_clean == prev_clean:
        return True
    import re
    cand_words = [w for w in re.findall(r"\w+", cand_clean) if len(w) > 1]
    prev_words = [w for w in re.findall(r"\w+", prev_clean) if len(w) > 1]
    if not cand_words or not prev_words:
        return False
    if len(cand_words) >= 5 and len(prev_words) >= 5 and cand_words[:5] == prev_words[:5]:
        return True
    cand_set = set(cand_words)
    prev_set = set(prev_words)
    overlap = len(cand_set.intersection(prev_set))
    min_len = min(len(cand_set), len(prev_set))
    if min_len >= 4 and (overlap / min_len) >= 0.65:
        return True
    return False


async def generate(
    *, decision: PlannerDecision, extraction: ExtractionResult, state: dict, rag_chunks: list[RagChunk],
    conversation_policy: ConversationPolicySnapshot, business_identity: str, language: str,
    recent_turns: list[dict] | None, llm_client: LLMClient | None, engine_mode: str = "legacy",
    customer_utterance: str = "",
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

    should_fast_respond = (
        engine_mode == "fast"
        and decision.action in _FAST_RESPONSE_ELIGIBLE_ACTIONS
        and not (decision.answer_question_first and extraction.question_type == "general_knowledge")
        and not (decision.action == "DEFER_QUESTION" and extraction.question_type == "general_knowledge")
        and extraction.turn_intent != "small_talk"
        and not decision.objection
    )
    if should_fast_respond:
        return fallback

    system, user = _build_prompt(
        decision=decision, extraction=extraction, state=state, rag_chunks=rag_chunks, objective=objective,
        business_identity=business_identity, language=language, recent_turns=recent_turns,
        recent_interrupt_count=recent_interrupt_count, customer_utterance=customer_utterance,
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

    if text and recent_turns:
        last_agent_text = ""
        for t in reversed(recent_turns):
            if t.get("speaker") == "agent":
                last_agent_text = t.get("text", "")
                break
        if last_agent_text and _is_repetition(text, last_agent_text):
            retry_user = (
                user
                + f'\n\nCRITICAL ANTI-REPETITION CONSTRAINT: In your previous turn, you said: "{last_agent_text}". '
                'Do NOT repeat or closely rephrase that statement. Instead, briefly acknowledge the customer and '
                'move to the next conversational step immediately.'
            )
            try:
                retry_text = await llm_client.complete_text(system=system, user=retry_user, max_tokens=150)
                if retry_text and not _is_repetition(retry_text, last_agent_text):
                    text = retry_text
            except Exception:
                pass

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
