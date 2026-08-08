"""Minimal real LLM client for the live real-call path — a plain chat
completion per turn (Twilio's TwiML loop needs one full text reply to speak,
not a token stream), not the general streaming LLMProvider Protocol used
elsewhere in the codebase.
"""

from __future__ import annotations

import httpx


class NotConfiguredError(RuntimeError):
    """Raised when OPENAI_API_KEY is absent — callers should surface this as
    a clear 4xx, never fall back to fabricating a reply on a real phone call."""


class OpenAIChat:
    def __init__(self, *, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise NotConfiguredError("OPENAI_API_KEY is not set")
        self._api_key = api_key
        self._model = model

    async def reply(self, *, messages: list[dict[str, str]]) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": messages, "temperature": 0.6, "max_tokens": 150},
            )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
