"""Real Sarvam speech-to-text client for the live real-call path — replaces
Twilio's built-in <Gather input="speech">, which can only recognize English
and returns nothing usable for Telugu/Hindi replies. See docs.sarvam.ai
(Saaras model) for the REST contract this mirrors.

`language_code` is a REQUIRED parameter, deliberately — this used to default
to "unknown" (auto-detect), which Sarvam's own docs say is less accurate
than a pinned code, and which was directly observed picking the wrong
language/script entirely mid-call (a Telugu-English conversation produced
one turn transcribed in Bengali script). Removing the default means a call
site can no longer silently regress back to "unknown". `mode="codemix"` is
Sarvam's mode built specifically for code-switched speech (e.g.
Telugu-English), matching this product's actual use case.
"""

import logging
import os
from dataclasses import dataclass

from app.live_providers._shared_http import get_shared_http_client

logger = logging.getLogger(__name__)


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_API_KEY is absent and no fallback STT is available."""


@dataclass(frozen=True)
class SttTranscript:
    text: str
    detected_language_code: str | None
    language_probability: float | None
    raw_response: dict


async def _fallback_transcribe_whisper(
    *, audio_bytes: bytes, language_code: str, filename: str = "recording.wav"
) -> SttTranscript | None:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return None
    client = get_shared_http_client()
    data = {"model": "whisper-1"}
    try:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            data=data,
            files={"file": (filename, audio_bytes, "audio/wav")},
            timeout=15.0,
        )
        response.raise_for_status()
        res_data = response.json()
        transcript_text = (res_data.get("text") or "").strip()
        logger.info("OpenAI Whisper fallback successfully transcribed audio: '%s'", transcript_text)
        return SttTranscript(
            text=transcript_text,
            detected_language_code=language_code,
            language_probability=1.0,
            raw_response=res_data,
        )
    except Exception as exc:
        logger.exception("OpenAI Whisper fallback transcription failed: %s", exc)
        return None


class SarvamSTT:
    def __init__(self, *, api_key: str, model: str = "saaras:v4"):
        if not api_key and not os.getenv("OPENAI_API_KEY"):
            raise NotConfiguredError("Neither SARVAM_API_KEY nor OPENAI_API_KEY is set")
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self, *, audio_bytes: bytes, language_code: str, filename: str = "recording.wav", mode: str = "codemix"
    ) -> SttTranscript:
        if self._api_key:
            client = get_shared_http_client()
            try:
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": self._api_key},
                    data={"language_code": language_code, "model": self._model, "mode": mode},
                    files={"file": (filename, audio_bytes, "audio/wav")},
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                return SttTranscript(
                    text=(data.get("transcript") or "").strip(),
                    detected_language_code=data.get("language_code"),
                    language_probability=data.get("language_probability"),
                    raw_response=data,
                )
            except Exception as exc:
                logger.warning("Sarvam STT failed (%s), attempting OpenAI Whisper fallback...", exc)

        # Fallback to OpenAI Whisper
        fallback = await _fallback_transcribe_whisper(
            audio_bytes=audio_bytes, language_code=language_code, filename=filename
        )
        if fallback is not None:
            return fallback

        raise RuntimeError("Both Sarvam STT and OpenAI Whisper fallback failed to transcribe audio")

