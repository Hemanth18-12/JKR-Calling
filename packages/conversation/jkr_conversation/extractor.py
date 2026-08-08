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

from jkr_conversation import objectives, policy, rag
from jkr_conversation.llm_client import LLMClient
from jkr_conversation.objectives import ObjectiveDefinition
from jkr_conversation.schemas import ExtractionResult

_VALID_INTENTS = {"answer", "question", "objection", "small_talk", "silence", "other"}
_VALID_SENTIMENTS = {"positive", "neutral", "negative"}


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
        "sentiment (one of: positive, neutral, negative)."
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
    )


async def extract(*, customer_utterance: str, state: dict, llm_client: LLMClient | None) -> ExtractionResult:
    objective = objectives.get_objective(state.get("objective", objectives.DEFAULT_OBJECTIVE_ID))

    if llm_client is not None:
        system, user = _build_prompt(customer_utterance=customer_utterance, state=state, objective=objective)
        try:
            raw = await llm_client.complete_json(system=system, user=user, max_tokens=400)
        except Exception:  # noqa: BLE001 — a client that violates its own "never raise" contract must still fall back
            raw = None
        if raw is not None:
            try:
                return _parse_llm_extraction(raw, objective=objective)
            except Exception:  # noqa: BLE001 — malformed model output must fall back, never break a live call
                pass

    return _mock_extract(customer_utterance=customer_utterance, state=state)
