"""StreamingResponseAssembler — event-stream-to-SpeakableChunk assembly,
cancellation, failure handling, and timing/usage accounting. Every fake
event stream below is a plain async generator (no provider/httpx involved
at all — that boundary is covered separately in test_streaming_llm.py),
matching how StreamingResponseAssembler.run() is documented to accept any
AsyncIterator[LLMStreamEvent].
"""

from __future__ import annotations

from jkr_conversation.streaming_llm import (
    LLMFailureClass,
    LLMResponseCompleted,
    LLMResponseFailed,
    LLMResponseStarted,
    LLMUsage,
    TextDelta,
)
from jkr_conversation.streaming_response import CancellationToken, StreamingResponseAssembler


def test_cancellation_token_defaults_unset_and_cancel_is_one_way():
    token = CancellationToken()
    assert token.is_cancelled is False
    token.cancel()
    assert token.is_cancelled is True


async def _happy_stream():
    yield LLMResponseStarted(request_id="r1")
    yield TextDelta(text="One. Two.")
    yield LLMUsage(input_tokens=10, output_tokens=4)
    yield LLMResponseCompleted(full_text="One. Two.")


async def test_happy_path_assembles_chunks_text_and_timing():
    assembler = StreamingResponseAssembler()
    result = await assembler.run(_happy_stream())

    assert result.failed is False
    assert result.cancelled is False
    assert [c.text for c in result.chunks] == ["One.", "Two."]
    assert result.full_text == "One. Two."
    assert result.input_tokens == 10
    assert result.output_tokens == 4
    assert result.ttft_ms is not None
    assert result.first_speakable_chunk_ms is not None
    assert result.full_generation_ms >= 0
    assert result.chunks[-1].is_final is True
    assert result.chunks[0].is_final is False


async def test_chunk_ids_carry_response_and_generation_id():
    assembler = StreamingResponseAssembler()
    result = await assembler.run(_happy_stream())
    for chunk in result.chunks:
        assert chunk.response_id == result.response_id
        assert chunk.generation_id == result.generation_id
    assert [c.chunk_index for c in result.chunks] == [0, 1]


async def test_leftover_buffer_flushed_as_final_chunk_when_stream_ends_mid_sentence():
    async def _stream():
        yield LLMResponseStarted(request_id="r1")
        yield TextDelta(text="Sentence one. Trailing fragment with no period")
        yield LLMResponseCompleted(full_text="Sentence one. Trailing fragment with no period")

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream())

    assert [c.text for c in result.chunks] == ["Sentence one.", "Trailing fragment with no period"]
    assert result.chunks[-1].is_final is True
    assert result.chunks[0].is_final is False


async def test_failure_before_any_chunk_yields_empty_result():
    async def _stream():
        yield LLMResponseFailed(failure_class=LLMFailureClass.AUTH_ERROR, message="bad key")

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream())

    assert result.failed is True
    assert result.chunks == []
    assert result.full_text == ""
    assert result.failure_message == "auth_error: bad key"


async def test_failure_after_first_chunk_preserves_already_produced_text():
    async def _stream():
        yield LLMResponseStarted(request_id="r1")
        yield TextDelta(text="Partial answer.")
        yield LLMResponseFailed(failure_class=LLMFailureClass.PROVIDER_INTERNAL, message="mid-stream drop")

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream())

    assert result.failed is True
    assert [c.text for c in result.chunks] == ["Partial answer."]
    assert result.full_text == "Partial answer."


async def test_gen_aclose_called_even_when_generator_not_exhausted_by_cancellation():
    closed = {"value": False}

    async def _stream():
        try:
            yield LLMResponseStarted(request_id="r1")
            yield TextDelta(text="Hello.")
            yield TextDelta(text=" This part is never reached.")
            yield LLMResponseCompleted(full_text="Hello. This part is never reached.")
        finally:
            closed["value"] = True

    token = CancellationToken()

    async def cancel_after_first_chunk(_chunk):
        token.cancel()

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream(), cancellation_token=token, on_chunk=cancel_after_first_chunk)

    assert result.cancelled is True
    assert closed["value"] is True  # proves gen.aclose() actually ran, not just that the loop stopped


async def test_late_delta_after_cancellation_is_discarded():
    async def _stream():
        yield LLMResponseStarted(request_id="r1")
        yield TextDelta(text="First.")
        yield TextDelta(text="Second part that should be discarded.")
        yield LLMResponseCompleted(full_text="First. Second part that should be discarded.")

    token = CancellationToken()

    async def cancel_after_first_chunk(_chunk):
        token.cancel()

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream(), cancellation_token=token, on_chunk=cancel_after_first_chunk)

    assert result.cancelled is True
    assert [c.text for c in result.chunks] == ["First."]
    assert "discarded" not in result.full_text


async def test_on_chunk_invoked_in_real_time_with_async_callable():
    seen: list[str] = []

    async def on_chunk(chunk):
        seen.append(chunk.text)

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_happy_stream(), on_chunk=on_chunk)

    assert seen == [c.text for c in result.chunks]


async def test_on_chunk_accepts_plain_sync_callable():
    seen: list[str] = []

    def on_chunk(chunk):
        seen.append(chunk.text)

    assembler = StreamingResponseAssembler()
    await assembler.run(_happy_stream(), on_chunk=on_chunk)

    assert seen == ["One.", "Two."]


async def test_on_chunk_also_fires_for_the_trailing_flush_chunk():
    async def _stream():
        yield LLMResponseStarted(request_id="r1")
        yield TextDelta(text="No trailing punctuation at all")
        yield LLMResponseCompleted(full_text="No trailing punctuation at all")

    seen: list[str] = []

    async def on_chunk(chunk):
        seen.append(chunk.text)

    assembler = StreamingResponseAssembler()
    await assembler.run(_stream(), on_chunk=on_chunk)

    assert seen == ["No trailing punctuation at all"]


async def test_ttft_measured_at_first_text_delta_even_before_a_chunk_boundary():
    async def _stream():
        yield LLMResponseStarted(request_id="r1")
        yield TextDelta(text="No boundary yet")
        yield TextDelta(text=" still no boundary")
        yield TextDelta(text=".")
        yield LLMResponseCompleted(full_text="No boundary yet still no boundary.")

    assembler = StreamingResponseAssembler()
    result = await assembler.run(_stream())

    assert result.ttft_ms is not None
    assert result.first_speakable_chunk_ms is not None
    assert result.ttft_ms <= result.first_speakable_chunk_ms


async def test_two_independent_runs_never_cross_ids_or_chunk_state():
    a1 = StreamingResponseAssembler()
    a2 = StreamingResponseAssembler()
    r1 = await a1.run(_happy_stream())
    r2 = await a2.run(_happy_stream())

    assert r1.response_id != r2.response_id
    assert r1.generation_id != r2.generation_id
    assert all(c.response_id == r1.response_id for c in r1.chunks)
    assert all(c.response_id == r2.response_id for c in r2.chunks)
