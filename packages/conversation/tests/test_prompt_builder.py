from jkr_conversation import objectives, prompt_builder
from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult, PlannerDecision
from jkr_conversation.state import new_conversation_state

_POLICY = ConversationPolicySnapshot()


class _FakeLLMClient:
    def __init__(self, text_response: str | None):
        self._text_response = text_response

    async def complete_json(self, *, system, user, max_tokens=300):
        return None

    async def complete_text(self, *, system, user, max_tokens=150):
        return self._text_response


def _extraction(**overrides) -> ExtractionResult:
    defaults = dict(turn_intent="answer", is_mock=True)
    defaults.update(overrides)
    return ExtractionResult(**defaults)


async def test_mock_mode_ask_field_matches_objective_text_byte_exact():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=None,
    )
    expected = objectives.get_objective("book_appointment").fields[1].question["en"]
    assert text == expected


async def test_safety_stop_always_uses_canned_text_even_with_a_real_llm_client():
    # Structural guarantee, not a prompt instruction: SAFETY_STOP never calls
    # the LLM at all — the fake client's complete_text would return this
    # string if it were called, so its absence proves the LLM path was
    # skipped entirely.
    decision = PlannerDecision(action="SAFETY_STOP", reason="do_not_call_requested")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="THIS SHOULD NEVER APPEAR")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(do_not_call=True), state=state, rag_chunks=[],
        conversation_policy=_POLICY, business_identity="Aaha Dental Care", language="en-IN",
        recent_turns=None, llm_client=fake,
    )
    assert "THIS SHOULD NEVER APPEAR" not in text
    assert "won't call you again" in text


async def test_tool_backed_objective_completion_never_overclaims_even_with_a_real_llm_client():
    # The actual safety property under test: book_appointment's completion
    # text must never claim the booking is confirmed, since the tool hasn't
    # run yet at generation time — enforced structurally (canned text always
    # used here), not by hoping the model followed an instruction.
    decision = PlannerDecision(action="COMPLETE_OBJECTIVE", reason="all_fields_collected")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="Great news, your appointment is booked and confirmed!")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert "booked" not in text.lower()
    assert "confirmed" not in text.lower()
    assert text == objectives.get_objective("book_appointment").closing_text["en"]


async def test_non_tool_backed_objective_completion_uses_real_generation_when_available():
    decision = PlannerDecision(action="COMPLETE_OBJECTIVE", reason="all_fields_collected")
    state = new_conversation_state(objective="qualify_lead", language="en-IN")
    fake = _FakeLLMClient(text_response="Thanks so much for sharing all that — we'll be in touch soon!")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="JKR Creatives", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert text == "Thanks so much for sharing all that — we'll be in touch soon!"


async def test_generation_falls_back_to_canned_text_when_llm_returns_none():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="topic")
    state = new_conversation_state(objective="qualify_and_route", language="en-IN")
    fake = _FakeLLMClient(text_response=None)
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Test Biz", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert text == objectives.get_objective("qualify_and_route").fields[0].question["en"]


async def test_human_handoff_uses_canned_ack_not_llm_generation():
    decision = PlannerDecision(action="HUMAN_HANDOFF", reason="customer_requested_human")
    state = new_conversation_state(objective="book_appointment", language="te-IN")
    fake = _FakeLLMClient(text_response="SHOULD NOT BE USED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(wants_human=True), state=state, rag_chunks=[],
        conversation_policy=_POLICY, business_identity="Aaha Dental Care", language="te-IN",
        recent_turns=None, llm_client=fake,
    )
    assert text != "SHOULD NOT BE USED"
