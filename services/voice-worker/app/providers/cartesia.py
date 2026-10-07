"""Cartesia Text-to-Speech provider adapter for voice-worker.

Implements the TextToSpeechProvider Protocol (app.providers.base)
for real-time multilingual voice synthesis (Telugu, Hindi, Indian English).
Integrates with Cartesia's Sonic model family.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import NotConfiguredError, SynthesisResult, VoiceConfig

logger = logging.getLogger(__name__)

CARTESIA_API_URL = "https://api.cartesia.ai/tts/bytes"
DEFAULT_CARTESIA_MODEL = "sonic-3.6"
DEFAULT_CARTESIA_VOICE = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
CARTESIA_VERSION = "2024-11-13"


def _map_language_code(lang: str) -> str:
    """Map language codes (e.g. te-IN, hi-IN, en-IN) to Cartesia ISO 639-1 codes."""
    clean = lang.lower().strip()
    if clean.startswith("te"):
        return "te"
    if clean.startswith("hi"):
        return "hi"
    if clean.startswith("en"):
        return "en"
    return clean.split("-")[0]


class CartesiaTTS:
    """Cartesia TextToSpeechProvider implementation for voice-worker.

    Satisfies the TextToSpeechProvider protocol in app.providers.base.
    Uses CARTESIA_API_KEY from environment or settings.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_CARTESIA_MODEL,
        default_voice_id: str = DEFAULT_CARTESIA_VOICE,
    ) -> None:
        settings = get_settings()
        key = api_key or getattr(settings, "cartesia_api_key", "") or os.environ.get("CARTESIA_API_KEY", "")
        self.api_key = key
        self.model = model
        self.default_voice_id = default_voice_id
        self._stopped_sessions: set[str] = set()

    async def synthesize(self, *, text: str, voice: VoiceConfig) -> SynthesisResult:
        """Synthesize text using Cartesia TTS and return SynthesisResult with actual audio duration."""
        if not self.api_key:
            raise NotConfiguredError("CARTESIA_API_KEY is not configured")

        if not text or not text.strip():
            return SynthesisResult(audio_duration_ms=0, is_simulated=False)

        voice_id = voice.voice_id or self.default_voice_id
        lang = _map_language_code(voice.language or "en")
        speed = voice.speaking_speed if voice.speaking_speed else 1.0

        headers = {
            "X-API-Key": self.api_key,
            "Cartesia-Version": CARTESIA_VERSION,
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model_id": self.model,
            "transcript": text.strip(),
            "voice": {
                "mode": "id",
                "id": voice_id,
            },
            "output_format": {
                "container": "wav",
                "encoding": "pcm_s16le",
                "sample_rate": 8000,
            },
            "language": lang,
        }
        if speed != 1.0:
            body["generation_config"] = {"speed": speed}

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(CARTESIA_API_URL, headers=headers, json=body)
                res.raise_for_status()
                audio_bytes = res.content
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("Cartesia TTS API error status %s", status)
            if status in (401, 403):
                raise RuntimeError(f"Cartesia authentication failed ({status})") from exc
            if status == 429:
                raise RuntimeError("Cartesia rate limit reached (429)") from exc
            raise RuntimeError(f"Cartesia TTS synthesis failed with status {status}") from exc
        except httpx.TimeoutException as exc:
            logger.error("Cartesia TTS synthesis request timed out")
            raise RuntimeError("Cartesia TTS synthesis request timed out") from exc
        except Exception as exc:
            logger.error("Cartesia TTS network error: %s", type(exc).__name__)
            raise RuntimeError(f"Cartesia TTS network error: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Cartesia TTS synthesis completed: %d bytes in %d ms (lang=%s, voice=%s)",
            len(audio_bytes),
            elapsed_ms,
            lang,
            voice_id,
        )

        # 8000 Hz, 16-bit mono = 16,000 bytes/sec; 44 bytes WAV header
        pcm_bytes = max(len(audio_bytes) - 44, 0)
        duration_ms = int((pcm_bytes / 16000.0) * 1000)
        if duration_ms <= 0:
            from app.turn_manager import estimate_speaking_duration_ms

            duration_ms = estimate_speaking_duration_ms(text)

        return SynthesisResult(audio_duration_ms=duration_ms, is_simulated=False)

    async def stop(self, *, session_id: str) -> None:
        self._stopped_sessions.add(session_id)
