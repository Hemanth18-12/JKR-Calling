"""stream_openai_chat_completion() SSE parsing — the fake client below
mirrors the shape services/api/tests/test_sarvam_stt.py's _FakeAsyncClient
already uses for the non-streaming provider fakes in this codebase, extended
with the async-context-manager `.stream()` shape real httpx.AsyncClient
exposes (verified against the live API — see docs/P5_STREAMING_LLM_AUDIT.md).
"""

from __future__ import annotations

import httpx
import pytest
from jkr_conversation.streaming_llm import (
    LLMFailureClass,
    LLMResponseCompleted,
    LLMResponseFailed,
    LLMResponseStarted,
    LLMUsage,
    TextDelta,
    stream_openai_chat_completion,
)


class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, response: _FakeStreamResponse | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise_exc = raise_exc

    async def __aenter__(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response

    async def __aexit__(self, *exc):
        return False


class _FakeAsyncClient:
    def __init__(self, status_code: int = 200, lines: list[str] | None = None, raise_exc: Exception | None = None):
        self._status_code = status_code
        self._lines = lines or []
        self._raise_exc = raise_exc
        self.captured_calls: list[dict] = []

    def stream(self, method, url, *, headers, json):
        self.captured_calls.append({"method": method, "url": url, "headers": headers, "json": json})
        if self._raise_exc is not None:
            return _FakeStreamCtx(raise_exc=self._raise_exc)
        return _FakeStreamCtx(response=_FakeStreamResponse(self._status_code, self._lines))


_HAPPY_PATH_LINES = [
    'data: {"id":"chatcmpl-abc","choices":[{"delta":{"role":"assistant","content":""},"finish_reason":null}]}',
    'data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
    'data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
    'data: {"id":"chatcmpl-abc","choices":[{"delta":{},"finish_reason":"stop"}]}',
    'data: {"id":"chatcmpl-abc","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2}}',
    "data: [DONE]",
]


async def _collect(client, **kwargs):
    events = []
    async for event in stream_openai_chat_completion(
        api_key="fake-key", model="gpt-4o-mini", system="sys", user="usr", max_tokens=150, **kwargs
    ):
        events.append(event)
    return events


async def test_happy_path_yields_started_deltas_usage_completed_in_order(monkeypatch):
    fake_client = _FakeAsyncClient(lines=_HAPPY_PATH_LINES)
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    assert isinstance(events[0], LLMResponseStarted)
    assert events[0].request_id == "chatcmpl-abc"
    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    assert [d.text for d in text_deltas] == ["Hello", " world"]
    usage_events = [e for e in events if isinstance(e, LLMUsage)]
    assert usage_events == [LLMUsage(input_tokens=10, output_tokens=2)]
    assert isinstance(events[-1], LLMResponseCompleted)
    assert events[-1].full_text == "Hello world"


async def test_request_body_pins_stream_and_include_usage(monkeypatch):
    fake_client = _FakeAsyncClient(lines=_HAPPY_PATH_LINES)
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    await _collect(fake_client)

    assert len(fake_client.captured_calls) == 1
    call = fake_client.captured_calls[0]
    assert call["json"]["stream"] is True
    assert call["json"]["stream_options"] == {"include_usage": True}
    assert call["json"]["model"] == "gpt-4o-mini"
    assert call["json"]["max_tokens"] == 150
    assert call["headers"]["Authorization"] == "Bearer fake-key"


@pytest.mark.parametrize(
    "status_code,expected_class",
    [(401, LLMFailureClass.AUTH_ERROR), (403, LLMFailureClass.AUTH_ERROR), (429, LLMFailureClass.RATE_LIMIT),
     (500, LLMFailureClass.PROVIDER_INTERNAL), (503, LLMFailureClass.PROVIDER_INTERNAL), (400, LLMFailureClass.INVALID_REQUEST)],
)
async def test_http_status_codes_classified_correctly(monkeypatch, status_code, expected_class):
    fake_client = _FakeAsyncClient(status_code=status_code, lines=[])
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    assert len(events) == 1
    assert isinstance(events[0], LLMResponseFailed)
    assert events[0].failure_class == expected_class


async def test_timeout_exception_classified_and_never_raises(monkeypatch):
    fake_client = _FakeAsyncClient(raise_exc=httpx.TimeoutException("took too long"))
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    assert len(events) == 1
    assert isinstance(events[0], LLMResponseFailed)
    assert events[0].failure_class == LLMFailureClass.TIMEOUT


async def test_connect_error_classified_and_never_raises(monkeypatch):
    fake_client = _FakeAsyncClient(raise_exc=httpx.ConnectError("could not connect"))
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    assert len(events) == 1
    assert isinstance(events[0], LLMResponseFailed)
    assert events[0].failure_class == LLMFailureClass.CONNECTION_ERROR


async def test_unknown_exception_classified_and_never_raises(monkeypatch):
    fake_client = _FakeAsyncClient(raise_exc=RuntimeError("something unexpected"))
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    assert len(events) == 1
    assert isinstance(events[0], LLMResponseFailed)
    assert events[0].failure_class == LLMFailureClass.UNKNOWN


async def test_malformed_json_line_is_skipped_not_fatal(monkeypatch):
    lines = [
        "data: not-valid-json{{{",
        'data: {"id":"chatcmpl-x","choices":[{"delta":{"content":"still works"},"finish_reason":null}]}',
        "data: [DONE]",
    ]
    fake_client = _FakeAsyncClient(lines=lines)
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    assert [d.text for d in text_deltas] == ["still works"]
    assert isinstance(events[-1], LLMResponseCompleted)


async def test_non_data_lines_are_ignored(monkeypatch):
    lines = [
        "",
        ": keep-alive comment",
        'data: {"id":"chatcmpl-y","choices":[{"delta":{"content":"hi"},"finish_reason":null}]}',
        "data: [DONE]",
    ]
    fake_client = _FakeAsyncClient(lines=lines)
    monkeypatch.setattr("jkr_conversation.streaming_llm.get_shared_http_client", lambda: fake_client)

    events = await _collect(fake_client)

    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    assert [d.text for d in text_deltas] == ["hi"]
