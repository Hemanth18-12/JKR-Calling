from jkr_conversation import objectives, prompt_builder
from jkr_conversation.schemas import ConversationPolicySnapshot, ExtractionResult, PlannerDecision
from jkr_conversation.state import new_conversation_state
from jkr_conversation.streaming_llm import (
    LLMFailureClass,
    LLMResponseCompleted,
    LLMResponseFailed,
    LLMResponseStarted,
    TextDelta,
)

_POLICY = ConversationPolicySnapshot()


class _FakeLLMClient:
    def __init__(self, text_response: str | None):
        self._text_response = text_response
        self.last_system: str | None = None
        self.complete_text_call_count = 0

    async def complete_json(self, *, system, user, max_tokens=300):
        return None

    async def complete_text(self, *, system, user, max_tokens=150):
        self.complete_text_call_count += 1
        self.last_system = system
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


async def test_non_tool_backed_objective_completion_never_uses_free_generation():
    # This used to assert the opposite (free LLM generation winning here) —
    # that was the exact root cause of the abrupt-hangup bug: a freely
    # generated closing ("if tomorrow morning works...") could sound
    # non-final right before the call hung up. Every COMPLETE_OBJECTIVE now
    # goes through closing.py's deterministic, per-language templates,
    # tool-backed or not — proven here the same way SAFETY_STOP already was,
    # by handing it an LLM client whose response must never appear.
    decision = PlannerDecision(action="COMPLETE_OBJECTIVE", reason="all_fields_collected")
    state = new_conversation_state(objective="qualify_lead", language="en-IN")
    fake = _FakeLLMClient(text_response="THIS SHOULD NEVER APPEAR")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="JKR Creatives", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert "THIS SHOULD NEVER APPEAR" not in text
    assert text == objectives.get_objective("qualify_lead").closing_text["en"]


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


def test_language_instruction_strict_profiles_forbid_code_switching():
    # The bug: strict "-only" profiles used to get the exact same "mix
    # English words in" instruction as the code-mixed profiles.
    te_only = prompt_builder._language_instruction("te-IN")
    hi_only = prompt_builder._language_instruction("hi-IN")
    en_only = prompt_builder._language_instruction("en-IN")
    assert "do not deliberately code-switch" in te_only.lower()
    assert "do not deliberately code-switch" in hi_only.lower()
    assert "do not mix in telugu or hindi" in en_only.lower()


def test_language_instruction_mixed_profiles_allow_code_switching():
    te_en = prompt_builder._language_instruction("te-en-IN")
    hi_en = prompt_builder._language_instruction("hi-en-IN")
    assert "code-switches" in te_en.lower() and "telugu" in te_en.lower()
    assert "code-switches" in hi_en.lower() and "hindi" in hi_en.lower()


def test_language_instruction_is_distinct_across_all_five_profiles():
    instructions = {code: prompt_builder._language_instruction(code) for code in ("te-IN", "hi-IN", "en-IN", "te-en-IN", "hi-en-IN")}
    assert len(set(instructions.values())) == 5


def test_language_instruction_mixed_profiles_forbid_fully_english_sentences():
    # Real-call bug: under the old looser code-mixed instruction, the LLM
    # produced an entire English sentence ("Sure. Can you please let me
    # know when it's convenient for us to call you back?") mid Telugu-
    # English conversation — technically "code-mixing" but reads as a
    # jarring language switch to the customer.
    te_en = prompt_builder._language_instruction("te-en-IN")
    hi_en = prompt_builder._language_instruction("hi-en-IN")
    assert "fully english sentence" in te_en.lower()
    assert "fully english sentence" in hi_en.lower()


async def test_reopened_from_closing_uses_short_reaffirm_not_the_full_closing_script():
    # Real-call bug: a customer speaking again during the grace-listen
    # window after the closing already played got the exact same closing
    # text repeated verbatim ("Thank you...goodbye" twice) when the
    # objective re-completed with nothing new to add.
    decision = PlannerDecision(action="COMPLETE_OBJECTIVE", reason="all_fields_collected")
    state = new_conversation_state(objective="qualify_lead", language="en-IN")
    state["reopened_from_closing"] = True
    fake = _FakeLLMClient(text_response="THIS SHOULD NEVER APPEAR")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="JKR Creatives", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert "THIS SHOULD NEVER APPEAR" not in text
    assert text != objectives.get_objective("qualify_lead").closing_text["en"]
    assert "thank you" in text.lower()


async def test_generate_actually_sends_the_profile_specific_language_instruction_to_the_llm():
    # End-to-end: not just that the helper produces the right text, but that
    # generate() actually threads it into the real system prompt sent out.
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="te-IN")
    fake = _FakeLLMClient(text_response="some reply")
    await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="te-IN", recent_turns=None, llm_client=fake,
    )
    assert fake.last_system is not None
    assert "do not deliberately code-switch" in fake.last_system.lower()


# --- P10 §42: adaptive brevity ------------------------------------------


def test_brevity_instruction_empty_below_threshold():
    assert prompt_builder._brevity_instruction(0) == ""
    assert prompt_builder._brevity_instruction(prompt_builder.ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD - 1) == ""


def test_brevity_instruction_present_at_and_above_threshold():
    at_threshold = prompt_builder._brevity_instruction(prompt_builder.ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD)
    above_threshold = prompt_builder._brevity_instruction(prompt_builder.ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD + 5)
    assert "short" in at_threshold.lower()
    assert "short" in above_threshold.lower()


async def test_generate_sends_the_brevity_hint_when_recently_interrupted_often():
    # End-to-end, same pattern as the language-instruction proof above: not
    # just that the helper produces the right text, but that generate()
    # actually threads recent_interrupt_count into the real system prompt.
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="some reply")
    await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        recent_interrupt_count=prompt_builder.ADAPTIVE_BREVITY_INTERRUPT_THRESHOLD,
    )
    assert fake.last_system is not None
    assert "interrupted you several times" in fake.last_system


async def test_generate_omits_the_brevity_hint_when_rarely_interrupted():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="some reply")
    await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        recent_interrupt_count=0,
    )
    assert fake.last_system is not None
    assert "interrupted you several times" not in fake.last_system


async def test_generate_default_recent_interrupt_count_omits_brevity_hint():
    # Every existing call site (which never passes recent_interrupt_count)
    # must be byte-for-byte unaffected — the default is 0, below threshold.
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="some reply")
    await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert fake.last_system is not None
    assert "interrupted you several times" not in fake.last_system


# --- P3.5: fast canned-response path (engine_mode="fast") -------------------


async def test_fast_mode_ask_field_skips_the_llm_entirely():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="SHOULD NEVER BE CALLED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        engine_mode="fast",
    )
    assert fake.complete_text_call_count == 0
    assert text == objectives.get_objective("book_appointment").fields[1].question["en"]


async def test_fast_mode_confirm_field_skips_the_llm_entirely():
    decision = PlannerDecision(action="CONFIRM_FIELD", reason="pending_domain_confirmation", target_field="reason_for_visit")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    state["pending_confirmation"] = {"field": "reason_for_visit", "candidate_value": "root canal treatment"}
    fake = _FakeLLMClient(text_response="SHOULD NEVER BE CALLED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        engine_mode="fast",
    )
    assert fake.complete_text_call_count == 0
    assert "root canal treatment" in text


async def test_fast_mode_clarify_and_defer_question_also_skip_the_llm():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="SHOULD NEVER BE CALLED")

    clarify_decision = PlannerDecision(action="CLARIFY", reason="low_confidence_extraction", target_field="reason_for_visit")
    text = await prompt_builder.generate(
        decision=clarify_decision, extraction=_extraction(uncertain_fields={"reason_for_visit": ["filling", "feeling"]}),
        state=state, rag_chunks=[], conversation_policy=_POLICY, business_identity="Aaha Dental Care",
        language="en-IN", recent_turns=None, llm_client=fake, engine_mode="fast",
    )
    assert fake.complete_text_call_count == 0
    assert "SHOULD NEVER BE CALLED" not in text

    defer_decision = PlannerDecision(action="DEFER_QUESTION", reason="unanswered_question_before_close")
    text2 = await prompt_builder.generate(
        decision=defer_decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake, engine_mode="fast",
    )
    assert fake.complete_text_call_count == 0
    assert "SHOULD NEVER BE CALLED" not in text2


async def test_legacy_mode_still_calls_the_llm_for_the_same_decision():
    # The exact same decision that skips the LLM under "fast" must still
    # call it under "legacy" (the default) — proves the flag actually
    # gates behavior rather than always taking the fast path.
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="a real generated reply")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        engine_mode="legacy",
    )
    assert fake.complete_text_call_count == 1
    assert text == "a real generated reply"


async def test_fast_mode_still_uses_canned_text_for_safety_and_completion_actions():
    # SAFETY_STOP/HUMAN_HANDOFF/COMPLETE_OBJECTIVE were already canned-only
    # before P3.5 (structural safety rule) — fast mode must not change that.
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="SHOULD NEVER BE CALLED")
    decision = PlannerDecision(action="SAFETY_STOP", reason="do_not_call_requested")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(do_not_call=True), state=state, rag_chunks=[],
        conversation_policy=_POLICY, business_identity="Aaha Dental Care", language="en-IN",
        recent_turns=None, llm_client=fake, engine_mode="fast",
    )
    assert fake.complete_text_call_count == 0
    assert "won't call you again" in text


# --- P5: streaming response_mode ---------------------------------------


class _FakeStreamingLLMClient:
    """A client that satisfies LLMClient (complete_json/complete_text) AND
    exposes stream_text — the shape OpenAILLMClient has after P5. Tests
    that want to prove response_mode="streaming" gracefully degrades for a
    client WITHOUT stream_text use plain _FakeLLMClient instead."""

    def __init__(self, events: list, complete_text_response: str | None = "COMPLETE MODE FALLBACK RESPONSE"):
        self._events = events
        self._complete_text_response = complete_text_response
        self.stream_text_call_count = 0
        self.complete_text_call_count = 0
        self.last_system: str | None = None

    async def complete_json(self, *, system, user, max_tokens=300):
        return None

    async def complete_text(self, *, system, user, max_tokens=150):
        self.complete_text_call_count += 1
        self.last_system = system
        return self._complete_text_response

    def stream_text(self, *, system, user, max_tokens=150):
        self.stream_text_call_count += 1
        self.last_system = system
        return self._events_gen()

    async def _events_gen(self):
        for event in self._events:
            yield event


_HAPPY_STREAM_EVENTS = [
    LLMResponseStarted(request_id="r1"),
    TextDelta(text="Streamed answer."),
    LLMResponseCompleted(full_text="Streamed answer."),
]


async def test_streaming_mode_returns_full_text_assembled_from_the_stream():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=list(_HAPPY_STREAM_EVENTS))
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming",
    )
    assert text == "Streamed answer."
    assert fake.stream_text_call_count == 1
    assert fake.complete_text_call_count == 0


async def test_streaming_mode_populates_latency_sink():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=list(_HAPPY_STREAM_EVENTS))
    sink: dict[str, int] = {}
    await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming", latency_sink=sink,
    )
    assert "llm_ttft" in sink
    assert "llm_first_speakable_chunk" in sink
    assert "llm_full_generation" in sink


async def test_streaming_mode_invokes_on_speakable_chunk_callback_in_order():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=[
        LLMResponseStarted(request_id="r1"), TextDelta(text="First part."), TextDelta(text="Second part."),
        LLMResponseCompleted(full_text="First part. Second part."),
    ])
    seen: list[str] = []

    async def on_chunk(chunk):
        seen.append(chunk.text)

    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming", on_speakable_chunk=on_chunk,
    )
    assert seen == ["First part.", "Second part."]
    assert text == "First part. Second part."


async def test_streaming_mode_falls_back_to_canned_text_on_stream_failure():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=[
        LLMResponseFailed(failure_class=LLMFailureClass.PROVIDER_INTERNAL, message="down"),
    ])
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming",
    )
    assert text == objectives.get_objective("book_appointment").fields[1].question["en"]


async def test_streaming_mode_pre_cancelled_returns_fallback():
    from jkr_conversation.streaming_response import CancellationToken

    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=list(_HAPPY_STREAM_EVENTS))
    token = CancellationToken()
    token.cancel()
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming", cancellation_token=token,
    )
    assert text == objectives.get_objective("book_appointment").fields[1].question["en"]


async def test_streaming_mode_gracefully_degrades_to_complete_text_when_client_lacks_stream_text():
    # _FakeLLMClient (defined at module top) only implements complete_json/
    # complete_text — the LLMClient Protocol's actual minimum — same as any
    # provider that hasn't added streaming support yet.
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(text_response="non-streaming reply")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming",
    )
    assert text == "non-streaming reply"
    assert fake.complete_text_call_count == 1


async def test_streaming_mode_never_used_for_safety_stop():
    decision = PlannerDecision(action="SAFETY_STOP", reason="do_not_call_requested")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=[TextDelta(text="SHOULD NEVER BE USED")], complete_text_response="SHOULD NEVER BE USED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(do_not_call=True), state=state, rag_chunks=[],
        conversation_policy=_POLICY, business_identity="Aaha Dental Care", language="en-IN",
        recent_turns=None, llm_client=fake, response_mode="streaming",
    )
    assert fake.stream_text_call_count == 0
    assert fake.complete_text_call_count == 0
    assert "won't call you again" in text


async def test_streaming_mode_never_used_for_complete_objective():
    decision = PlannerDecision(action="COMPLETE_OBJECTIVE", reason="all_fields_collected")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=[TextDelta(text="SHOULD NEVER BE USED")], complete_text_response="SHOULD NEVER BE USED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming",
    )
    assert fake.stream_text_call_count == 0
    assert fake.complete_text_call_count == 0
    assert text == objectives.get_objective("book_appointment").closing_text["en"]


async def test_streaming_mode_never_used_when_fast_path_eligible():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=[TextDelta(text="SHOULD NEVER BE USED")], complete_text_response="SHOULD NEVER BE USED")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
        response_mode="streaming", engine_mode="fast",
    )
    assert fake.stream_text_call_count == 0
    assert fake.complete_text_call_count == 0
    assert text == objectives.get_objective("book_appointment").fields[1].question["en"]


async def test_complete_mode_is_still_the_default_response_mode():
    decision = PlannerDecision(action="ASK_FIELD", reason="missing_required_field", target_field="preferred_date")
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeStreamingLLMClient(events=list(_HAPPY_STREAM_EVENTS), complete_text_response="complete mode reply")
    text = await prompt_builder.generate(
        decision=decision, extraction=_extraction(), state=state, rag_chunks=[], conversation_policy=_POLICY,
        business_identity="Aaha Dental Care", language="en-IN", recent_turns=None, llm_client=fake,
    )
    assert text == "complete mode reply"
    assert fake.stream_text_call_count == 0
    assert fake.complete_text_call_count == 1
