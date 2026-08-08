"""Real Sarvam speech-to-text client for the live real-call path — replaces
Twilio's built-in <Gather input="speech">, which can only recognize English
and returns nothing usable for Telugu/Hindi replies. See docs.sarvam.ai
(Saaras model) for the REST contract this mirrors.
"""

from __future__ import annotations

import httpx


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_API_KEY is absent — see openai_llm.NotConfiguredError."""


class SarvamSTT:
    def __init__(self, *, api_key: str, model: str = "saaras:v3"):
        if not api_key:
            raise NotConfiguredError("SARVAM_API_KEY is not set")
        self._api_key = api_key
        self._model = model

    async def transcribe(self, *, audio_bytes: bytes, filename: str = "recording.wav") -> str:
        """`language_code="unknown"` lets Sarvam auto-detect — the agent's own
        script code-switches Telugu/English, and so will a real customer's
        reply, so pinning a single language would be wrong more often than
        not."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": self._api_key},
                data={"language_code": "unknown", "model": self._model},
                files={"file": (filename, audio_bytes, "audio/wav")},
            )
        response.raise_for_status()
        data = response.json()
        return (data.get("transcript") or "").strip()
