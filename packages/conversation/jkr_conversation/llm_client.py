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
from dataclasses import dataclass
from typing import Protocol


class LLMClient(Protocol):
    async def complete_json(self, *, system: str, user: str, max_tokens: int = 300) -> dict | None: ...
    async def complete_text(self, *, system: str, user: str, max_tokens: int = 150) -> str | None: ...


@dataclass
class OpenAILLMClient:
    api_key: str
    model: str = "gpt-4o-mini"

    async def complete_json(self, *, system: str, user: str, max_tokens: int = 300) -> dict | None:
        """Returns None on any failure (network, non-2xx, unparseable JSON)
        — callers must treat None exactly like "no LLM configured" and fall
        back to their heuristic, never propagate the exception into a live
        phone call."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
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
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        "temperature": 0.6,
                        "max_tokens": max_tokens,
                    },
                )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:  # noqa: BLE001 — see docstring
            return None


def get_default_client() -> LLMClient | None:
    """None means "no real LLM configured" — every caller in this package
    must treat that as a first-class, expected mode, not an error path."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAILLMClient(api_key=api_key)
