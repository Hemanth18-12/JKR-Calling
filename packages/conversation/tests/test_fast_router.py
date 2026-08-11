from __future__ import annotations

from jkr_conversation import fast_router
from jkr_conversation.schemas import ConversationPolicySnapshot

_POLICY = ConversationPolicySnapshot()


def test_do_not_call_returns_fast_path_result_with_no_llm_involvement():
    result = fast_router.route(customer_utterance="please do not call again", state={}, conversation_policy=_POLICY)
    assert result is not None
    assert result.do_not_call is True
    assert result.is_mock is False
    assert result.turn_path == "fast_path"


def test_wrong_number_detected():
    result = fast_router.route(customer_utterance="wrong number, this isn't him", state={}, conversation_policy=_POLICY)
    assert result is not None
    assert result.wrong_number is True
    assert result.turn_path == "fast_path"


def test_human_handoff_detected():
    result = fast_router.route(customer_utterance="I want to talk to a real person", state={}, conversation_policy=_POLICY)
    assert result is not None
    assert result.wants_human is True
    assert result.turn_path == "fast_path"


def test_pending_confirmation_yes_resolves_without_llm():
    state = {"pending_confirmation": {"field": "reason_for_visit", "candidate_value": "root canal treatment"}}
    result = fast_router.route(customer_utterance="avunu", state=state, conversation_policy=_POLICY)
    assert result is not None
    assert result.confirmation_response == "confirm"
    assert result.extracted_fields == {}  # never dumps the raw utterance into the field itself


def test_pending_confirmation_no_resolves_without_llm():
    state = {"pending_confirmation": {"field": "reason_for_visit", "candidate_value": "root canal treatment"}}
    result = fast_router.route(customer_utterance="kaadu", state=state, conversation_policy=_POLICY)
    assert result is not None
    assert result.confirmation_response == "reject"


def test_pending_confirmation_ambiguous_reply_falls_through_to_real_understanding():
    # A genuine correction ("filling" instead) is neither yes nor no —
    # spec §21: fast paths only cover high-confidence, low-ambiguity cases.
    state = {"pending_confirmation": {"field": "reason_for_visit", "candidate_value": "root canal treatment"}}
    result = fast_router.route(customer_utterance="filling", state=state, conversation_policy=_POLICY)
    assert result is None


def test_acknowledgement_only_detected_without_pending_confirmation():
    result = fast_router.route(customer_utterance="hmm", state={}, conversation_policy=_POLICY)
    assert result is not None
    assert result.turn_intent == "acknowledgement"
    assert result.extracted_fields == {}


def test_pending_confirmation_takes_priority_over_acknowledgement_detection():
    # A short "avunu" during a pending confirmation must resolve the
    # confirmation, never get discarded as mere filler — mirrors
    # extractor.py's own precedence exactly.
    state = {"pending_confirmation": {"field": "x", "candidate_value": "y"}}
    result = fast_router.route(customer_utterance="avunu", state=state, conversation_policy=_POLICY)
    assert result is not None
    assert result.confirmation_response == "confirm"
    assert result.turn_intent != "acknowledgement"


def test_ordinary_substantive_utterance_falls_through_to_real_understanding():
    # A normal multi-field statement is exactly what FastTurnRouter must
    # NOT try to handle — spec §21's "do not overbuild deterministic NLP."
    result = fast_router.route(
        customer_utterance="CSE kavali, rank 28 thousand, hostel kuda kavali.", state={}, conversation_policy=_POLICY,
    )
    assert result is None


def test_plain_field_answer_falls_through_not_misclassified_as_confirmation():
    # No pending_confirmation in state — "tomorrow evening" must not be
    # mistaken for anything fast-path-eligible.
    result = fast_router.route(customer_utterance="tomorrow evening", state={}, conversation_policy=_POLICY)
    assert result is None
