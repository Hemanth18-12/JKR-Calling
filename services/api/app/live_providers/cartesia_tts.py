"""Real Cartesia text-to-speech client for the live real-call path.

Replaces Sarvam TTS / Twilio's built-in <Say> with Cartesia's Sonic TTS model.
Supports Telugu, Hindi, Indian English, and Hinglish.
Returns raw WAV bytes matching the existing live_call audio caching and playback pipeline.
"""

from __future__ import annotations

import logging
import os
import re

from app.live_providers._shared_http import get_shared_http_client

logger = logging.getLogger(__name__)

CARTESIA_API_URL = "https://api.cartesia.ai/tts/bytes"
DEFAULT_CARTESIA_MODEL = "sonic-3.6"
DEFAULT_CARTESIA_VOICE = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
CARTESIA_VERSION = "2024-11-13"


class NotConfiguredError(RuntimeError):
    """Raised when CARTESIA_API_KEY is absent and no fallback TTS is available."""


def _clean_text_for_tts(text: str) -> str:
    cleaned = text.replace(" 's", "'s").replace(" '", "'")
    cleaned = cleaned.replace("AI assistantని", "AI అసిస్టెంట్‌ని")
    cleaned = cleaned.replace("AI assistant", "AI అసిస్టెంట్")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _map_language_code(code: str) -> str:
    clean = code.lower().strip()
    if clean.startswith("te"):
        return "te"
    if clean.startswith("hi"):
        return "hi"
    if clean.startswith("en"):
        return "en"
    return clean.split("-")[0]


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


class CartesiaTTS:
    """Batch Cartesia TTS client returning raw WAV bytes.

    Satisfies the same contract as SarvamTTS:
    synthesize(text=..., language_code=...) -> bytes (WAV format)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        speaker: str | None = None,
        voice_id: str | None = None,
        model: str = DEFAULT_CARTESIA_MODEL,
        pace: float = 1.0,
    ):
        key = api_key or os.getenv("CARTESIA_API_KEY", "")
        if not key and not os.getenv("OPENAI_API_KEY"):
            raise NotConfiguredError("Neither CARTESIA_API_KEY nor OPENAI_API_KEY is set")
        self._api_key = key
        self._speaker = voice_id or speaker or os.getenv("CARTESIA_VOICE_ID") or DEFAULT_CARTESIA_VOICE
        self._model = model
        self._pace = pace

    async def synthesize(self, *, text: str, language_code: str) -> bytes:
        """Returns raw WAV bytes for the given text. Falls back to OpenAI TTS-HD
        if Cartesia is unavailable or encounters an error."""
        cleaned_text = _clean_text_for_tts(text)
        if self._api_key:
            client = get_shared_http_client()
            lang = _map_language_code(language_code)
            headers = {
                "X-API-Key": self._api_key,
                "Cartesia-Version": CARTESIA_VERSION,
                "Content-Type": "application/json",
            }
            body = {
                "model_id": self._model,
                "transcript": cleaned_text,
                "voice": {
                    "mode": "id",
                    "id": self._speaker,
                },
                "output_format": {
                    "container": "wav",
                    "encoding": "pcm_s16le",
                    "sample_rate": 8000,
                },
                "language": lang,
            }
            if self._pace != 1.0:
                body["generation_config"] = {"speed": self._pace}

            try:
                response = await client.post(
                    CARTESIA_API_URL,
                    headers=headers,
                    json=body,
                    timeout=15.0,
                )
                response.raise_for_status()
                logger.info(
                    "Cartesia TTS successfully synthesized audio (%d bytes, lang=%s)",
                    len(response.content),
                    lang,
                )
                return response.content
            except Exception as exc:
                logger.warning("Cartesia TTS failed (%s), attempting OpenAI TTS fallback...", exc)

        fallback = await _fallback_synthesize_openai(text=text)
        if fallback is not None:
            return fallback

        raise RuntimeError("Both Cartesia TTS and OpenAI TTS fallback failed to synthesize speech")
