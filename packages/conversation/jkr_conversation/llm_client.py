"""OPENAI_API_KEY-gated real/mock LLM client swap — same pattern as
jkr_db.embeddings.embed_text: check the env var, try a real call, fall back
cleanly on absence or failure. Every LLM-touching module in this package
(extractor.py, prompt_builder.py) depends only on the small `LLMClient`
Protocol here, never on `httpx`/OpenAI specifics directly — this is what
lets a mock-mode workspace (the default, per docs/DECISIONS/0002-voice-runtime.md
— "no credentials, no network calls, no cost") keep working unchanged, and
lets tests inject a fake implementation with no network at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from jkr_conversation._shared_http import get_shared_http_client as _get_http_client

if TYPE_CHECKING:
    from jkr_conversation.streaming_llm import LLMStreamEvent

# P3.5 §34 — a direct provider probe (docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md
# §3) showed connection reuse is NOT the dominant cost here (a realistic
# extraction-shaped call was ~1.9-2s whether the connection was warm or
# freshly opened) — but constructing a brand-new httpx.AsyncClient (and
# therefore a brand-new TCP+TLS connection) on every single call was still a
# real, free-to-fix correctness issue, so it's fixed regardless. The shared
# client itself lives in _shared_http.py (not here) specifically so
# streaming_llm.py can depend on it without creating a llm_client.py <->
# streaming_llm.py import cycle now that OpenAILLMClient.stream_text()
# below needs streaming_llm's event types.


class LLMClient(Protocol):
    async def complete_json(self, *, system: str, user: str, max_tokens: int = 300) -> dict | None: ...
    async def complete_text(self, *, system: str, user: str, max_tokens: int = 150) -> str | None: ...


@dataclass
class OpenAILLMClient:
    api_key: str
    # P3.5 §12/§13 — configurable rather than hardcoded so a faster/cheaper
    # model can be tried for the latency-sensitive extraction call without
    # touching call sites; get_default_client() below reads the env override
    # fresh on every call (same freshness as api_key), so these class-level
    # defaults only matter for direct construction (e.g. tests).
    model: str = "gpt-4o-mini"
    response_model: str = "gpt-4o-mini"

    async def complete_json(self, *, system: str, user: str, max_tokens: int = 300) -> dict | None:
        """Returns None on any failure (network, non-2xx, unparseable JSON)
        — callers must treat None exactly like "no LLM configured" and fall
        back to their heuristic, never propagate the exception into a live
        phone call."""
        try:
            client = _get_http_client()
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:  # noqa: BLE001 — see docstring, must never raise into a live call
            return None

    async def complete_text(self, *, system: str, user: str, max_tokens: int = 150) -> str | None:
        try:
            client = _get_http_client()
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.response_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.6,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:  # noqa: BLE001 — see docstring
            return None

    def stream_text(self, *, system: str, user: str, max_tokens: int = 150) -> AsyncIterator[LLMStreamEvent]:
        """P5 — streaming counterpart to complete_text(). Delegates to
        streaming_llm.stream_openai_chat_completion rather than duplicating
        the SSE parsing here; imported lazily to avoid a module-level
        import cycle (streaming_llm.py itself never imports llm_client.py,
        but keeping the import local keeps that invariant obviously true
        without relying on import order)."""
        from jkr_conversation.streaming_llm import stream_openai_chat_completion

        return stream_openai_chat_completion(
            api_key=self.api_key, model=self.response_model, system=system, user=user, max_tokens=max_tokens,
        )


def get_default_client() -> LLMClient | None:
    """None means "no real LLM configured" — every caller in this package
    must treat that as a first-class, expected mode, not an error path."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAILLMClient(
        api_key=api_key,
        model=os.environ.get("TURN_UNDERSTANDING_MODEL", "gpt-4o-mini"),
        response_model=os.environ.get("CONVERSATION_RESPONSE_MODEL", "gpt-4o-mini"),
    )
