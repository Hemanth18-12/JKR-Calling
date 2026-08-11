"""P5 — provider-neutral streaming LLM response generation. Lives alongside
llm_client.py (not in services/api) because response generation is a
jkr_conversation concern, shared by both the real-call path and Test Lab —
same reasoning `OpenAILLMClient` itself already follows.

No `openai` SDK dependency — checked before writing this (see
docs/P5_STREAMING_LLM_AUDIT.md): none is installed anywhere in this
workspace, and every existing provider integration in this codebase
(Sarvam STT/TTS/streaming-STT, OpenAI batch chat/embeddings) hand-rolls raw
`httpx` calls. `stream_openai_chat_completion` continues that pattern
rather than introducing a new one, parsing OpenAI's SSE format exactly as
verified against the live API (not guessed) in the audit doc.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jkr_conversation._shared_http import get_shared_http_client


@dataclass(frozen=True)
class LLMResponseStarted:
    request_id: str | None


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class LLMResponseCompleted:
    full_text: str


class LLMFailureClass(StrEnum):
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_INTERNAL = "provider_internal"
    INVALID_REQUEST = "invalid_request"
    STREAM_INTERRUPTED = "stream_interrupted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LLMResponseFailed:
    failure_class: LLMFailureClass
    message: str


LLMStreamEvent = LLMResponseStarted | TextDelta | LLMUsage | LLMResponseCompleted | LLMResponseFailed


class StreamingLLMProvider(Protocol):
    def stream_response(self, *, system: str, user: str, max_tokens: int) -> AsyncIterator[LLMStreamEvent]: ...


async def stream_openai_chat_completion(
    *, api_key: str, model: str, system: str, user: str, max_tokens: int, temperature: float = 0.6,
) -> AsyncIterator[LLMStreamEvent]:
    """Yields LLMResponseStarted once, then TextDelta per content fragment,
    then LLMUsage (if the provider supplies it — requested via
    stream_options.include_usage, only ever arrives once, after the final
    content chunk, per the verified contract), then exactly one of
    LLMResponseCompleted or LLMResponseFailed. Never raises — every failure
    mode becomes an LLMResponseFailed event, matching this package's
    established "never propagate a provider exception into a live call"
    contract (see llm_client.py's own docstring)."""
    import httpx

    client = get_shared_http_client()
    full_text_parts: list[str] = []
    try:
        async with client.stream(
            "POST", "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as response:
            if response.status_code in (401, 403):
                yield LLMResponseFailed(failure_class=LLMFailureClass.AUTH_ERROR, message=f"HTTP {response.status_code}")
                return
            if response.status_code == 429:
                yield LLMResponseFailed(failure_class=LLMFailureClass.RATE_LIMIT, message=f"HTTP {response.status_code}")
                return
            if response.status_code >= 500:
                yield LLMResponseFailed(failure_class=LLMFailureClass.PROVIDER_INTERNAL, message=f"HTTP {response.status_code}")
                return
            if response.status_code >= 400:
                yield LLMResponseFailed(failure_class=LLMFailureClass.INVALID_REQUEST, message=f"HTTP {response.status_code}")
                return

            started = False
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except (TypeError, ValueError):
                    continue
                if not started:
                    started = True
                    yield LLMResponseStarted(request_id=data.get("id"))
                choices = data.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        full_text_parts.append(content)
                        yield TextDelta(text=content)
                usage = data.get("usage")
                if usage:
                    yield LLMUsage(input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))
            yield LLMResponseCompleted(full_text="".join(full_text_parts))
    except httpx.TimeoutException as exc:
        yield LLMResponseFailed(failure_class=LLMFailureClass.TIMEOUT, message=str(exc))
    except httpx.ConnectError as exc:
        yield LLMResponseFailed(failure_class=LLMFailureClass.CONNECTION_ERROR, message=str(exc))
    except Exception as exc:  # noqa: BLE001 — must never raise into a live call, same contract as complete_text()
        yield LLMResponseFailed(failure_class=LLMFailureClass.UNKNOWN, message=str(exc))
