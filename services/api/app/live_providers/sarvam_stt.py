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

from __future__ import annotations

from dataclasses import dataclass

from app.live_providers._shared_http import get_shared_http_client


class NotConfiguredError(RuntimeError):
    """Raised when SARVAM_API_KEY is absent — see openai_llm.NotConfiguredError."""


@dataclass(frozen=True)
class SttTranscript:
    text: str
    detected_language_code: str | None
    language_probability: float | None
    raw_response: dict


class SarvamSTT:
    def __init__(self, *, api_key: str, model: str = "saaras:v4"):
        if not api_key:
            raise NotConfiguredError("SARVAM_API_KEY is not set")
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self, *, audio_bytes: bytes, language_code: str, filename: str = "recording.wav", mode: str = "codemix"
    ) -> SttTranscript:
        client = get_shared_http_client()
        response = await client.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": self._api_key},
            data={"language_code": language_code, "model": self._model, "mode": mode},
            files={"file": (filename, audio_bytes, "audio/wav")},
        )
        response.raise_for_status()
        data = response.json()
        return SttTranscript(
            text=(data.get("transcript") or "").strip(),
            detected_language_code=data.get("language_code"),
            language_probability=data.get("language_probability"),
            raw_response=data,
        )
