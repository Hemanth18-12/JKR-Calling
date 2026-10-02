from __future__ import annotations

from datetime import UTC, datetime
import pytest

from jkr_conversation import extractor, objections, planner, policy
from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult
from jkr_conversation.state import (
    new_conversation_state,
    READINESS_DISCOVERY,
    READINESS_OBJECTION,
    READINESS_APPOINTMENT_CONFIRMED,
)


def test_detect_individual_objections():
    """Verify that objections across price, trust, competitor, busy, discuss with team are detected."""
    assert objections.CAT_PRICE in objections.detect_objections("What is the price of this service?")
    assert objections.CAT_PRICE in objections.detect_objections("దాని ధర ఎంత అండి? చాలా ఖరీదు.")
    assert objections.CAT_PRICE in objections.detect_objections("यह बहुत महंगा है, कोई डिस्काउंट है?")

    assert objections.CAT_TRUST in objections.detect_objections("Why should I trust you? Is this genuine?")
    assert objections.CAT_TRUST in objections.detect_objections("మీది జెన్యూన్ సర్వీసేనా? నమ్మకం ఎలా?")
    assert objections.CAT_TRUST in objections.detect_objections("मुझे आप पर भरोसा कैसे होगा?")

    assert objections.CAT_COMPETITOR in objections.detect_objections("I already have another solution.")
    assert objections.CAT_COMPETITOR in objections.detect_objections("మేము ఇప్పటికే వేరే సాఫ్ట్‌వేర్ వాడుతున్నాము.")

    assert objections.CAT_TIMING_BUSY in objections.detect_objections("I am busy now, please call later.")
    assert objections.CAT_TIMING_BUSY in objections.detect_objections("నేను ఇప్పుడు డ్రైవింగ్ లో ఉన్నాను, తర్వాత మాట్లాడదాం.")

    assert objections.CAT_DISCUSS_TEAM in objections.detect_objections("I need to discuss with my husband first.")
    assert objections.CAT_DISCUSS_TEAM in objections.detect_objections("మా ఫ్యామిలీతో మాట్లాడి చెప్తాను.")

    assert objections.CAT_SEND_DETAILS in objections.detect_objections("Send me the details on WhatsApp first.")
    assert objections.CAT_SEND_DETAILS in objections.detect_objections("నాకు వాట్సాప్ లో వివరాలు పంపండి.")


def test_detect_multiple_simultaneous_objections():
    """Verify that multiple simultaneous concerns (e.g. Trust + Price) are both detected."""
    utterance = "I don't trust these kinds of services and it's also expensive."
    cats = objections.detect_objections(utterance)
    assert objections.CAT_TRUST in cats
    assert objections.CAT_PRICE in cats
    assert len(cats) >= 2


def test_spoken_counter_framing_multilingual():
    """Verify spoken objection fallback phrasing in Telugu, Hindi, and English."""
    te_price = objections.get_spoken_objection_fallback(objections.CAT_PRICE, language="te")
    assert "ధర" in te_price or "ప్లాన్స్‌" in te_price

    hi_trust = objections.get_spoken_objection_fallback(objections.CAT_TRUST, language="hi")
    assert "संशय" in hi_trust or "ग्राहक" in hi_trust

    en_busy = objections.get_spoken_objection_fallback(objections.CAT_TIMING_BUSY, language="en")
    assert "busy" in en_busy.lower() or "callback" in en_busy.lower()


def test_planner_prioritizes_handle_objection_over_asking_appointment_fields():
    """Verify that when a customer raises an objection, the planner chooses HANDLE_OBJECTION
    instead of aggressively pushing an appointment date/time question."""
    policy_snap = ConversationPolicySnapshot()
    state = new_conversation_state(objective="book_appointment", language="en")
    state["awaiting_field"] = "preferred_date"

    # User raises price objection
    extraction = ExtractionResult(
        turn_intent="objection",
        objection="price",
        detected_question=True,
        rewritten_query="What is the price?",
        question_type="business_knowledge",
    )

    decision = planner.decide(
        extraction=extraction,
        state=state,
        conversation_policy=policy_snap,
        now=datetime.now(UTC),
    )

    # Must NOT blindly return ASK_FIELD
    assert decision.action == "HANDLE_OBJECTION"
    assert "price" in decision.reason


def test_no_false_appointment_confirmation_on_questions():
    """Verify that asking a question like 'what happens during appointment?' does NOT confirm the appointment."""
    assert not policy.detect_appointment_confirmation("What happens during the appointment?")
    assert not policy.detect_appointment_confirmation("Why should I confirm the appointment right now?")
    assert not policy.detect_appointment_confirmation("Appointment lo em jaruguthundi?")
    assert not policy.detect_appointment_confirmation("How much does the appointment cost?")

    # But explicit confirmations MUST trigger
    assert policy.detect_appointment_confirmation("appointment confirmed")
    assert policy.detect_appointment_confirmation("yes, confirm the appointment")
    assert policy.detect_appointment_confirmation("అపాయింట్‌మెంట్ కన్ఫర్మ్")
