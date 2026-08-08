from jkr_conversation import extractor
from jkr_conversation.state import new_conversation_state


class _FakeLLMClient:
    def __init__(self, json_response=None, text_response=None, raise_on_json=False):
        self._json_response = json_response
        self._text_response = text_response
        self._raise_on_json = raise_on_json

    async def complete_json(self, *, system, user, max_tokens=300):
        if self._raise_on_json:
            raise RuntimeError("simulated network failure")
        return self._json_response

    async def complete_text(self, *, system, user, max_tokens=150):
        return self._text_response


# --- mock mode (no llm_client) ---------------------------------------------


async def test_mock_mode_fills_only_the_single_awaiting_field():
    # Honest documentation of mock mode's real limitation: it CANNOT multi-
    # field-extract without a real LLM — it reproduces the pre-refactor
    # "dump the raw utterance into whatever field was pending" behavior.
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    result = await extractor.extract(
        customer_utterance="CSE kavali, rank 28000, hostel kuda kavali", state=state, llm_client=None
    )
    assert result.is_mock is True
    assert len(result.extracted_fields) == 1
    assert result.extracted_fields[state["awaiting_field"]] == "CSE kavali, rank 28000, hostel kuda kavali"


async def test_mock_mode_detects_question_via_keyword_heuristic():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    result = await extractor.extract(customer_utterance="root canal cost enta?", state=state, llm_client=None)
    assert result.detected_question is True
    assert result.rewritten_query == "root canal cost enta?"


async def test_mock_mode_detects_do_not_call_keyword():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    result = await extractor.extract(customer_utterance="please do not call again", state=state, llm_client=None)
    assert result.do_not_call is True


async def test_mock_mode_detects_do_not_call_romanized_telugu():
    state = new_conversation_state(objective="book_appointment", language="te-en-IN")
    result = await extractor.extract(customer_utterance="malli call cheyyakandi", state=state, llm_client=None)
    assert result.do_not_call is True


async def test_mock_mode_detects_human_handoff_keyword():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    result = await extractor.extract(customer_utterance="I want to talk to a real person", state=state, llm_client=None)
    assert result.wants_human is True


async def test_mock_mode_no_awaiting_field_extracts_nothing():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    state["awaiting_field"] = None
    result = await extractor.extract(customer_utterance="just chatting", state=state, llm_client=None)
    assert result.extracted_fields == {}


# --- real mode (fake llm_client, no network) -------------------------------


async def test_real_mode_extracts_multiple_fields_from_one_utterance():
    # This is the actual new capability the whole refactor exists for.
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(
        json_response={
            "turn_intent": "answer",
            "extracted_fields": {"reason_for_visit": "root canal", "preferred_date": "tomorrow", "preferred_time": "evening"},
            "field_confidence": {"reason_for_visit": 0.95, "preferred_date": 0.9, "preferred_time": 0.85},
            "uncertain_fields": {},
            "detected_question": False,
            "rewritten_query": None,
            "objection": None,
            "wants_human": False,
            "wrong_number": False,
            "do_not_call": False,
            "sentiment": "neutral",
        }
    )
    result = await extractor.extract(customer_utterance="root canal, tomorrow evening", state=state, llm_client=fake)
    assert result.is_mock is False
    assert len(result.extracted_fields) == 3
    assert result.extracted_fields["preferred_date"] == "tomorrow"


async def test_real_mode_drops_hallucinated_field_keys():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(
        json_response={
            "turn_intent": "answer",
            "extracted_fields": {"reason_for_visit": "root canal", "made_up_field": "nonsense"},
            "field_confidence": {},
            "uncertain_fields": {},
            "detected_question": False,
            "rewritten_query": None,
            "objection": None,
            "wants_human": False,
            "wrong_number": False,
            "do_not_call": False,
            "sentiment": "neutral",
        }
    )
    result = await extractor.extract(customer_utterance="root canal", state=state, llm_client=fake)
    assert "made_up_field" not in result.extracted_fields
    assert "reason_for_visit" in result.extracted_fields


async def test_real_mode_falls_back_to_heuristic_on_llm_exception():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(raise_on_json=True)
    result = await extractor.extract(customer_utterance="root canal please", state=state, llm_client=fake)
    assert result.is_mock is True  # gracefully degraded, never raised into the caller


async def test_real_mode_falls_back_to_heuristic_on_none_response():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(json_response=None)
    result = await extractor.extract(customer_utterance="root canal please", state=state, llm_client=fake)
    assert result.is_mock is True


async def test_real_mode_falls_back_on_malformed_json_shape():
    state = new_conversation_state(objective="book_appointment", language="en-IN")
    fake = _FakeLLMClient(json_response={"extracted_fields": "not a dict"})
    result = await extractor.extract(customer_utterance="root canal please", state=state, llm_client=fake)
    # Malformed extracted_fields (a string, not a dict) must not crash — parsing
    # treats it as empty rather than raising.
    assert result.extracted_fields == {}
    assert result.is_mock is False  # the call succeeded and returned parseable (if odd) JSON
