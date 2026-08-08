"""One consolidated language-prefix helper. Previously duplicated inline in
at least three places (services/voice-worker/app/conversation_engine.py
lines 364/416, and providers/mock.py's private _lang_prefix) — each copy
free to drift independently. This is the single source of truth now.
"""

from __future__ import annotations

SUPPORTED_PREFIXES = ("te", "hi", "en")


def lang_prefix(language: str) -> str:
    """"te-en-IN" -> "te", "hi-IN" -> "hi", anything unrecognized -> "en"."""
    prefix = language.split("-")[0].lower()
    return prefix if prefix in SUPPORTED_PREFIXES else "en"
