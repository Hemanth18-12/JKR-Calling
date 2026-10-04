"""Real Sarvam text-to-speech client for the live real-call path — replaces
Twilio's built-in <Say>, which cannot pronounce Telugu/Hindi at all. See
docs.sarvam.ai (Bulbul model) for the REST contract this mirrors.
"""

import base64
import logging
import os

from app.live_providers._shared_http import get_shared_http_client

logger = logging.getLogger(__name__)


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_TTS_API_KEY is absent and no fallback TTS is available."""


def _clean_text_for_tts(text: str) -> str:
    cleaned = text.replace(" 's", "'s").replace(" '", "'")
    cleaned = cleaned.replace("AI assistantని", "AI అసిస్టెంట్‌ని")
    cleaned = cleaned.replace("AI assistant", "AI అసిస్టెంట్")
    import re
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def _fallback_synthesize_openai(*, text: str) -> bytes | None:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return None
    cleaned_text = _clean_text_for_tts(text)
    client = get_shared_http_client()
    try:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"},
            json={"model": "tts-1-hd", "input": cleaned_text, "voice": "nova", "speed": 0.92, "response_format": "wav"},
            timeout=25.0,
        )
        response.raise_for_status()
        logger.info("OpenAI TTS-HD fallback successfully synthesized audio (%d bytes)", len(response.content))
        return response.content
    except Exception as exc:
        logger.exception("OpenAI TTS fallback synthesis failed: %s", exc)
        return None


class SarvamTTS:
    def __init__(self, *, api_key: str, speaker: str = "kavitha", model: str = "bulbul:v3", pace: float = 1.0):
        if not api_key and not os.getenv("OPENAI_API_KEY"):
            raise NotConfiguredError("Neither SARVAM_TTS_API_KEY nor OPENAI_API_KEY is set")
        self._api_key = api_key
        self._speaker = speaker
        self._model = model
        self._pace = pace

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        """Returns raw WAV bytes for the given text. Falls back to OpenAI TTS-HD
        if Sarvam is unavailable or out of credits."""
        cleaned_text = _clean_text_for_tts(text)
        if self._api_key:
            client = get_shared_http_client()
            try:
                response = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": self._api_key, "Content-Type": "application/json"},
                    json={"text": cleaned_text, "language_code": language_code, "speaker": self._speaker, "model": self._model, "pace": self._pace},
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                return base64.b64decode(data["audios"][0])
            except Exception as exc:
                logger.warning("Sarvam TTS failed (%s), attempting OpenAI TTS fallback...", exc)

        fallback = await _fallback_synthesize_openai(text=text)
        if fallback is not None:
            return fallback

        raise RuntimeError("Both Sarvam TTS and OpenAI TTS fallback failed to synthesize speech")

