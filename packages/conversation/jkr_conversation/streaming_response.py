"""P5 — StreamingResponseAssembler: ties StreamingLLMProvider events to
SpeakableChunker to the streaming-safe formatter, producing SpeakableChunk
events with full timing/usage/cancellation tracking. No business rules
here (spec §12) — this module only knows how to turn a token stream into
speakable text; what the text SAYS is entirely prompt_builder.py's/the
planner's concern, unchanged.
"""

from __future__ import annotations

import inspect
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from jkr_conversation.formatter import strip_for_streaming_chunk
from jkr_conversation.speakable_chunker import SpeakableChunker
from jkr_conversation.streaming_llm import (
    LLMResponseCompleted,
    LLMResponseFailed,
    LLMResponseStarted,
    LLMStreamEvent,
    LLMUsage,
    TextDelta,
)


@dataclass(frozen=True)
class SpeakableChunk:
    response_id: str
    generation_id: str
    chunk_index: int
    text: str
    is_final: bool
    created_at: float


class CancellationToken:
    """P5 §36-39 — the primitive P8 will later call on user barge-in. A
    plain flag, not asyncio.Event: StreamingResponseAssembler checks it
    synchronously between events (no need to await it), and setting it is
    itself synchronous too — no race between "check" and "act" since both
    happen in the same task's control flow, same reasoning as
    TurnManager's own synchronous-by-design safety (see manager.py)."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass
class StreamingGenerationResult:
    """What the assembler hands back once a generation is done, one way or
    another. `full_text` is always the text actually assembled up to
    whatever point generation stopped — the caller (prompt_builder.py)
    decides whether that's usable or whether to fall back to canned text."""

    response_id: str
    generation_id: str
    full_text: str
    chunks: list[SpeakableChunk]
    cancelled: bool
    failed: bool
    failure_message: str | None
    input_tokens: int | None
    output_tokens: int | None
    # Timing, spec §50 — None if the corresponding event never arrived
    # (e.g. failed before any token, or usage never supplied).
    ttft_ms: int | None
    first_speakable_chunk_ms: int | None
    full_generation_ms: int


@dataclass
class StreamingResponseAssembler:
    chunker: SpeakableChunker = field(default_factory=SpeakableChunker)

    async def run(
        self, event_stream, *, cancellation_token: CancellationToken | None = None,
        on_chunk: Callable[[SpeakableChunk], Awaitable[None] | None] | None = None,
    ) -> StreamingGenerationResult:
        """`event_stream` is an AsyncIterator[LLMStreamEvent] — typically
        `streaming_llm.stream_openai_chat_completion(...)`, kept untyped
        here (rather than importing StreamingLLMProvider) so tests can
        hand in a plain async generator without constructing a full
        provider object.

        `on_chunk`, if given, is invoked synchronously as each SpeakableChunk
        is produced — DURING this coroutine's run, not after it returns —
        so a caller that wants the first chunk as early as possible (e.g. to
        start TTS on it, in a later phase) doesn't have to wait for the
        whole generation to finish first. Both sync and async callables are
        accepted. run()'s own return value remains the full aggregate
        result regardless, for callers that only care about the end state."""
        response_id = f"resp_{uuid.uuid4().hex[:12]}"
        generation_id = f"gen_{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()
        ttft_ms: int | None = None
        first_chunk_ms: int | None = None
        chunks: list[SpeakableChunk] = []
        text_parts: list[str] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        failed = False
        failure_message: str | None = None
        cancelled = False

        gen = event_stream.__aiter__()
        try:
            async for event in gen:
                if cancellation_token is not None and cancellation_token.is_cancelled:
                    cancelled = True
                    break
                outcome = self._handle_event(
                    event, response_id=response_id, generation_id=generation_id, t0=t0, chunk_index=len(chunks),
                )
                if outcome.ttft_ms is not None and ttft_ms is None:
                    ttft_ms = outcome.ttft_ms
                for new_chunk in outcome.new_chunks:
                    chunks.append(new_chunk)
                    text_parts.append(new_chunk.text)
                    if first_chunk_ms is None:
                        first_chunk_ms = int((time.monotonic() - t0) * 1000)
                    await self._invoke_on_chunk(on_chunk, new_chunk)
                if outcome.usage is not None:
                    input_tokens, output_tokens = outcome.usage
                if outcome.failed:
                    failed = True
                    failure_message = outcome.failure_message
                    break
                # A completed response that never hit a boundary character
                # (e.g. very short) leaves text sitting in the chunker's
                # buffer — the trailing flush() below always picks it up,
                # so LLMResponseCompleted itself needs no special handling
                # here beyond letting the loop end naturally.
        finally:
            await gen.aclose()

        if not cancelled and not failed:
            leftover = self.chunker.flush()
            if leftover:
                chunk = SpeakableChunk(
                    response_id=response_id, generation_id=generation_id, chunk_index=len(chunks),
                    text=strip_for_streaming_chunk(leftover), is_final=True, created_at=time.monotonic(),
                )
                chunks.append(chunk)
                text_parts.append(chunk.text)
                if first_chunk_ms is None:
                    first_chunk_ms = int((time.monotonic() - t0) * 1000)
                await self._invoke_on_chunk(on_chunk, chunk)
            elif chunks:
                # Mark the last emitted chunk final in-place — a fresh
                # instance since SpeakableChunk is frozen.
                last = chunks[-1]
                chunks[-1] = SpeakableChunk(
                    response_id=last.response_id, generation_id=last.generation_id, chunk_index=last.chunk_index,
                    text=last.text, is_final=True, created_at=last.created_at,
                )

        full_generation_ms = int((time.monotonic() - t0) * 1000)
        return StreamingGenerationResult(
            response_id=response_id, generation_id=generation_id, full_text=" ".join(text_parts).strip(),
            chunks=chunks, cancelled=cancelled, failed=failed, failure_message=failure_message,
            input_tokens=input_tokens, output_tokens=output_tokens, ttft_ms=ttft_ms,
            first_speakable_chunk_ms=first_chunk_ms, full_generation_ms=full_generation_ms,
        )

    @staticmethod
    async def _invoke_on_chunk(
        on_chunk: Callable[[SpeakableChunk], Awaitable[None] | None] | None, chunk: SpeakableChunk,
    ) -> None:
        if on_chunk is None:
            return
        maybe_awaitable = on_chunk(chunk)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    @dataclass(frozen=True)
    class _EventOutcome:
        ttft_ms: int | None = None
        new_chunks: list[SpeakableChunk] = field(default_factory=list)
        usage: tuple[int | None, int | None] | None = None
        failed: bool = False
        failure_message: str | None = None

    def _handle_event(
        self, event: LLMStreamEvent, *, response_id: str, generation_id: str, t0: float, chunk_index: int,
    ) -> StreamingResponseAssembler._EventOutcome:
        if isinstance(event, LLMResponseStarted):
            return self._EventOutcome()
        if isinstance(event, TextDelta):
            ttft_ms = int((time.monotonic() - t0) * 1000)
            raw_chunks = self.chunker.feed(event.text)
            # feed() can in principle return more than one completed chunk
            # for a single delta (e.g. a delta containing "end of sentence
            # one. start and end of sentence two.") — every one of them is
            # surfaced, none silently dropped.
            new_chunks = [
                SpeakableChunk(
                    response_id=response_id, generation_id=generation_id, chunk_index=chunk_index + i,
                    text=strip_for_streaming_chunk(raw), is_final=False, created_at=time.monotonic(),
                )
                for i, raw in enumerate(raw_chunks)
            ]
            return self._EventOutcome(ttft_ms=ttft_ms, new_chunks=new_chunks)
        if isinstance(event, LLMUsage):
            return self._EventOutcome(usage=(event.input_tokens, event.output_tokens))
        if isinstance(event, LLMResponseCompleted):
            return self._EventOutcome()  # full_text already tracked via TextDelta accumulation; nothing further to do
        if isinstance(event, LLMResponseFailed):
            return self._EventOutcome(failed=True, failure_message=f"{event.failure_class.value}: {event.message}")
        return self._EventOutcome()
