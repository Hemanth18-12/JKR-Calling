"""Real Sarvam text-to-speech client for the live real-call path — replaces
Twilio's built-in <Say>, which cannot pronounce Telugu/Hindi at all. See
docs.sarvam.ai (Bulbul model) for the REST contract this mirrors.
"""

from __future__ import annotations

import base64

from app.live_providers._shared_http import get_shared_http_client


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_TTS_API_KEY is absent — see openai_llm.NotConfiguredError."""


class SarvamTTS:
    def __init__(self, *, api_key: str, speaker: str = "priya", model: str = "bulbul:v3", pace: float = 1.0):
        if not api_key:
            raise NotConfiguredError("SARVAM_TTS_API_KEY is not set")
        self._api_key = api_key
        self._speaker = speaker
        self._model = model
        self._pace = pace

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        """Returns raw WAV bytes for the given text. Sarvam caps REST requests
        at 2500 characters — callers on a phone call should already be well
        under that (SpokenResponseFormatter-style short turns), so no
        chunking is implemented here."""
        client = get_shared_http_client()
        response = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": self._api_key, "Content-Type": "application/json"},
            json={"text": text, "language_code": language_code, "speaker": self._speaker, "model": self._model, "pace": self._pace},
        )
        response.raise_for_status()
        data = response.json()
        return base64.b64decode(data["audios"][0])
