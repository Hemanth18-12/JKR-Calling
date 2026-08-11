"""P3.5 FastTurnRouter — deterministic, zero-LLM, zero-I/O turn
classification for a small set of high-confidence, low-ambiguity,
context-bound cases (spec §21: "do not overbuild deterministic NLP...
fast paths should cover only high-confidence, low-ambiguity, context-bound
cases. Everything else goes through" the real extractor).

Every case here directly reuses policy.py's existing keyword detectors —
the same ones engine.py already applies AFTER extraction as a hard
backstop (policy.apply_backstop, "the LLM cannot override do-not-call").
This module runs the identical checks BEFORE the LLM call, so a confident
match skips it entirely instead of only mattering after already paying for
it. Nothing here is a new, separately-maintained keyword list — see
policy.py for the single source of truth.

Deliberately NOT attempted here (see docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md
§4 for the full reasoning): simple-typed-field parsing (date/time/phone/
rank/amount) — real deterministic parsing across 5 languages and
code-mixed speech is a substantial, separate undertaking with real
misparse risk, explicitly warned against building casually by this
phase's own spec (§21).

Returns None for anything not confidently covered — the caller
(engine.py) always falls through to the real extractor.extract() call in
that case, never guesses.
"""

from __future__ import annotations

from jkr_conversation import policy
from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult


def route(
    *, customer_utterance: str, state: dict, conversation_policy: ConversationPolicySnapshot
) -> ExtractionResult | None:
    # A field pending confirmation takes priority — mirrors extractor.py's
    # own extract()'s precedence (pending confirmation is checked before
    # acknowledgement-only detection, so a short "avunu"/"yes" resolves the
    # confirmation rather than being discarded as filler).
    pending = state.get("pending_confirmation")
    if pending:
        response = policy.detect_confirmation_response(customer_utterance)
        if response in ("confirm", "reject"):
            return ExtractionResult(
                turn_intent="answer", is_mock=False, turn_path="fast_path", confirmation_response=response,
            )
        return None  # ambiguous, or a correction — needs real understanding, not a guess

    # Safety phrases always win, same priority order planner.py itself
    # already enforces (do_not_call / wrong_number checked before anything
    # else). Checking do_not_call before wrong_number here only matters for
    # the (extremely unlikely) case both keyword lists somehow match the
    # same utterance — matches policy.apply_backstop's own field order.
    if policy.detect_do_not_call(customer_utterance):
        return ExtractionResult(turn_intent="other", is_mock=False, turn_path="fast_path", do_not_call=True, sentiment="negative")
    if policy.detect_wrong_number(customer_utterance):
        return ExtractionResult(turn_intent="other", is_mock=False, turn_path="fast_path", wrong_number=True)
    if policy.detect_human_handoff(customer_utterance):
        return ExtractionResult(turn_intent="other", is_mock=False, turn_path="fast_path", wants_human=True)

    # Acknowledgement-only ("hmm", "okay", "achha") — today this still pays
    # for a full LLM call and gets its extracted_fields wiped out
    # afterward (extractor.extract()'s own is_acknowledgement_only check
    # runs post-hoc); catching it here means it never reaches the LLM at all.
    if policy.is_acknowledgement_only(customer_utterance, phrases=conversation_policy.accidental_interruption_phrases):
        return ExtractionResult(turn_intent="acknowledgement", is_mock=False, turn_path="fast_path")

    return None
