"""Per-turn structured extraction — the piece that replaces "dump the raw
utterance into whatever field was pending" (today's actual behavior in
services/voice-worker/app/conversation_engine.py, line
`state["known_fields"][awaiting_field] = transcript.text`) with real
multi-field extraction when a real LLM is available.

Mock mode (no OPENAI_API_KEY) deliberately reproduces today's exact
single-field-dump behavior — it is NOT a smarter regex/rules parser. This is
required, not a shortcut: services/campaign-worker never sets an API key
(its auto-played generic customer replies wouldn't map onto real fields
anyway), and the existing mock-mode tests must keep passing unmodified.
"""

from __future__ import annotations

from dataclasses import replace

from jkr_conversation import domain_normalizer, objectives, policy, rag
from jkr_conversation.llm_client import LLMClient
from jkr_conversation.objectives import ObjectiveDefinition
from jkr_conversation.schemas import DomainTermSnapshot, ExtractionResult, FieldExtraction

_VALID_INTENTS = {"answer", "question", "objection", "small_talk", "silence", "other"}
_VALID_SENTIMENTS = {"positive", "neutral", "negative"}
_VALID_CONFIRMATION_RESPONSES = {"confirm", "reject", "correction"}


def _mock_extract(*, customer_utterance: str, state: dict) -> ExtractionResult:
    awaiting_field = state.get("awaiting_field")
    extracted_fields: dict[str, str] = {}
    field_confidence: dict[str, float] = {}
    if awaiting_field:
        extracted_fields[awaiting_field] = customer_utterance
        # Matches MockSTT's own "deliberately imperfect-looking" confidence
        # philosophy (providers/mock.py) — not always 1.0, so downstream
        # confidence-threshold logic has something real to react to.
        field_confidence[awaiting_field] = 0.6 if len(customer_utterance.strip()) > 2 else 0.4

    detected_question = rag.looks_like_a_question(customer_utterance)

    return ExtractionResult(
        turn_intent="question" if detected_question else "answer",
        extracted_fields=extracted_fields,
        field_confidence=field_confidence,
        uncertain_fields={},
        detected_question=detected_question,
        rewritten_query=customer_utterance if detected_question else None,
        objection=None,
        wants_human=policy.detect_human_handoff(customer_utterance),
        wrong_number=policy.detect_wrong_number(customer_utterance),
        do_not_call=policy.detect_do_not_call(customer_utterance),
        sentiment="neutral",
        is_mock=True,
        turn_path="mock",
    )


def _build_prompt(*, customer_utterance: str, state: dict, objective: ObjectiveDefinition) -> tuple[str, str]:
    field_lines = "\n".join(f"- {f.key}: {f.extraction_hint}" for f in objective.fields)
    known = state.get("known_fields", {})
    known_lines = "\n".join(f"- {k}: {v}" for k, v in known.items()) or "(none yet)"

    system = (
        "You are extracting structured information from one turn of a live phone conversation. "
        "Read the customer's utterance and identify: which of the objective's fields it answers "
        "(a single utterance may answer more than one field at once — extract all that apply), "
        "whether it contains a genuine question the customer wants answered, whether they're "
        "objecting or hesitant, whether they're asking to speak to a human, whether this call has "
        "reached the wrong person/number, whether they're asking not to be called again, and their "
        "overall sentiment. Only extract a field if the utterance actually, clearly addresses it — "
        "never guess or fabricate a value. Respond with ONLY a single JSON object, no other text, "
        "with exactly these keys: "
        "turn_intent (one of: answer, question, objection, small_talk, silence, other), "
        "extracted_fields (object mapping field key to the value stated, only for fields clearly "
        "addressed this turn), "
        "field_confidence (object mapping the same field keys to a 0-1 confidence number), "
        "uncertain_fields (object mapping field key to a list of ambiguous candidate values, only "
        "when genuinely unclear which the customer meant), "
        "detected_question (boolean), "
        "rewritten_query (a short, focused search-style query capturing just the factual question "
        "being asked, or null if detected_question is false), "
        "objection (a short description of the objection, or null), "
        "wants_human (boolean), wrong_number (boolean), do_not_call (boolean), "
        "sentiment (one of: positive, neutral, negative), "
        "confirmation_response (one of: confirm, reject, correction, or null if no confirmation is "
        "currently pending — see below)."
    )

    pending = state.get("pending_confirmation")
    if pending:
        system += (
            f"\n\nPENDING CONFIRMATION: on the previous turn, the agent asked the customer to confirm "
            f"whether the field '{pending.get('field')}' should be recorded as "
            f"\"{pending.get('candidate_value')}\" (the customer may have actually said something closer "
            f"to \"{pending.get('raw_value')}\"). Classify this reply as confirmation_response: "
            f"\"confirm\" if they agreed, \"reject\" if they said that's not right, or \"correction\" if "
            f"they stated a different value instead. If it's a correction, also put the new value into "
            f"extracted_fields['{pending.get('field')}'] as normal."
        )

    user = f'Objective fields (key: what it means):\n{field_lines}\n\nAlready known:\n{known_lines}\n\nCustomer just said: "{customer_utterance}"'
    return system, user


def _parse_llm_extraction(raw: dict, *, objective: ObjectiveDefinition) -> ExtractionResult:
    """Defensive parsing — JSON-mode output is well-formed JSON but its
    *content* is never trusted blindly: field keys the model invented that
    aren't real objective fields are dropped, confidences are clamped,
    unrecognized enum-like strings fall back to a safe default rather than
    propagating garbage into the planner."""
    valid_keys = {f.key for f in objective.fields}

    extracted_fields_field = raw.get("extracted_fields")
    extracted_fields_raw: dict = extracted_fields_field if isinstance(extracted_fields_field, dict) else {}
    extracted_fields = {
        k: str(v) for k, v in extracted_fields_raw.items() if k in valid_keys and v not in (None, "")
    }

    field_confidence_field = raw.get("field_confidence")
    field_confidence_raw: dict = field_confidence_field if isinstance(field_confidence_field, dict) else {}
    field_confidence: dict[str, float] = {}
    for k in extracted_fields:
        try:
            field_confidence[k] = max(0.0, min(1.0, float(field_confidence_raw.get(k, 0.75))))
        except (TypeError, ValueError):
            field_confidence[k] = 0.75

    uncertain_fields_field = raw.get("uncertain_fields")
    uncertain_fields_raw: dict = uncertain_fields_field if isinstance(uncertain_fields_field, dict) else {}
    uncertain_fields = {
        k: [str(c) for c in v]
        for k, v in uncertain_fields_raw.items()
        if k in valid_keys and isinstance(v, list) and v
    }

    turn_intent_field = raw.get("turn_intent")
    turn_intent: str = turn_intent_field if turn_intent_field in _VALID_INTENTS else "other"
    sentiment_field = raw.get("sentiment")
    sentiment: str = sentiment_field if sentiment_field in _VALID_SENTIMENTS else "neutral"

    rewritten_query = raw.get("rewritten_query")
    rewritten_query = rewritten_query.strip() if isinstance(rewritten_query, str) and rewritten_query.strip() else None

    objection = raw.get("objection")
    objection = objection.strip() if isinstance(objection, str) and objection.strip() else None

    confirmation_response_field = raw.get("confirmation_response")
    confirmation_response = confirmation_response_field if confirmation_response_field in _VALID_CONFIRMATION_RESPONSES else None

    return ExtractionResult(
        turn_intent=turn_intent,
        extracted_fields=extracted_fields,
        field_confidence=field_confidence,
        uncertain_fields=uncertain_fields,
        detected_question=bool(raw.get("detected_question")),
        rewritten_query=rewritten_query,
        objection=objection,
        wants_human=bool(raw.get("wants_human")),
        wrong_number=bool(raw.get("wrong_number")),
        do_not_call=bool(raw.get("do_not_call")),
        sentiment=sentiment,
        is_mock=False,
        raw_model_output=raw,
        confirmation_response=confirmation_response,
    )


def _resolve_pending_confirmation(result: ExtractionResult, *, customer_utterance: str, pending: dict) -> ExtractionResult:
    """Unlike do-not-call's keyword backstop, real-mode LLM classification
    is trusted here when available — it reasons over full sentence context
    (distinguishing a bare "no" from "no, I meant X"), which pure keyword
    matching cannot. Keyword matching (policy.detect_confirmation_response)
    is only the decider in mock mode or when the model didn't classify at
    all. A reply that's neither a clear yes nor a clear no is treated as a
    correction — the safest default, "ask twice, then accept what was
    literally said," same philosophy as planner.py's ask-cap.

    On confirm/reject, the pending field is never left holding whatever the
    base extraction (mock's awaiting_field dump, in particular) happened to
    capture from this turn's literal "yes"/"no" text — that's not a field
    value. On correction, the raw utterance becomes the candidate value if
    nothing more specific was already extracted, so there's always
    something for engine.py's confirmation table to act on."""
    if not result.is_mock and result.confirmation_response is not None:
        response = result.confirmation_response
    else:
        response = policy.detect_confirmation_response(customer_utterance) or result.confirmation_response or "correction"

    extracted_fields = dict(result.extracted_fields)
    field_confidence = dict(result.field_confidence)
    field = pending.get("field")

    if response in ("confirm", "reject") and field in extracted_fields:
        del extracted_fields[field]
        field_confidence.pop(field, None)
    elif response == "correction" and field and field not in extracted_fields:
        extracted_fields[field] = customer_utterance
        field_confidence[field] = 0.6 if len(customer_utterance.strip()) > 2 else 0.4

    return replace(
        result, confirmation_response=response, extracted_fields=extracted_fields, field_confidence=field_confidence
    )


def _annotate_domain_candidates(result: ExtractionResult, *, domain_terms: list[DomainTermSnapshot]) -> ExtractionResult:
    """Runs every field extracted this turn (from the real LLM, the mock
    heuristic, or a resolved confirmation/correction) through the agent's
    domain vocabulary. Never mutates known_fields or auto-selects a value
    itself — only attaches ranked-candidate detail for engine.py's
    confirmation decision table to act on. A domain match with no actual
    correction (the customer already said the canonical term or a known
    alias of itself) still gets a FieldExtraction entry — criticality alone
    can require confirmation under conversation_policy.confirmation_behavior,
    independent of whether anything was corrected."""
    if not domain_terms or not result.extracted_fields:
        return result
    field_extractions = dict(result.field_extractions)
    for field_key, raw_value in result.extracted_fields.items():
        candidates = domain_normalizer.normalize(raw_value, vocabulary_terms=domain_terms)
        if not candidates:
            continue
        top = candidates[0]
        corrected = top.matched_alias.strip().lower() != top.canonical.strip().lower()
        field_extractions[field_key] = FieldExtraction(
            raw_value=raw_value,
            confidence=result.field_confidence.get(field_key, 0.75),
            candidate_value=top.canonical if corrected else None,
            semantic_confidence=top.ratio,
            correction_method="fuzzy_alias_match" if corrected else None,
            criticality=top.criticality,
            domain_term_id=top.domain_term_id,
        )
    return replace(result, field_extractions=field_extractions)


async def extract(
    *,
    customer_utterance: str,
    state: dict,
    llm_client: LLMClient | None,
    domain_terms: list[DomainTermSnapshot] | None = None,
    acknowledgement_phrases: list[str] | None = None,
) -> ExtractionResult:
    objective = objectives.get_objective(state.get("objective", objectives.DEFAULT_OBJECTIVE_ID))

    result: ExtractionResult | None = None
    if llm_client is not None:
        system, user = _build_prompt(customer_utterance=customer_utterance, state=state, objective=objective)
        try:
            raw = await llm_client.complete_json(system=system, user=user, max_tokens=400)
        except Exception:  # noqa: BLE001 — a client that violates its own "never raise" contract must still fall back
            raw = None
        if raw is not None:
            try:
                result = _parse_llm_extraction(raw, objective=objective)
            except Exception:  # noqa: BLE001 — malformed model output must fall back, never break a live call
                result = None

    if result is None:
        result = _mock_extract(customer_utterance=customer_utterance, state=state)

    pending = state.get("pending_confirmation")
    if pending:
        # A field pending confirmation is being resolved this turn — never
        # also run acknowledgement-only detection on the same utterance
        # (a short "avunu"/"yes" must resolve the confirmation, not get
        # discarded as mere filler).
        result = _resolve_pending_confirmation(result, customer_utterance=customer_utterance, pending=pending)
    elif policy.is_acknowledgement_only(customer_utterance, phrases=acknowledgement_phrases or []):
        result = replace(result, turn_intent="acknowledgement", extracted_fields={}, field_confidence={})

    return _annotate_domain_candidates(result, domain_terms=domain_terms or [])
