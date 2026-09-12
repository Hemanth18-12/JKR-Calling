"""Content safety and abusive language sanitization for Agent Studio persona fields.

Guards user-entered greeting_text, ai_disclosure_text, and closing_text against
profanity, abuse, slurs, and inappropriate injections across English, Telugu, and Hindi
before text can be persisted or spoken on live calls.
"""

from __future__ import annotations

import re
import unicodedata
from fastapi import HTTPException, status

# Abusive, profane, vulgar, and derogatory terms across supported languages
# 1. Telugu (Telugu script and Romanized transliterations)
_TELUGU_ABUSIVE_TERMS = {
    # Telugu script
    "దెంగు", "దెంగ", "దెంగే", "దెంగించు", "లంజ", "లంజకొడుకు", "లంజా",
    "లవడ", "లవడే", "లవడా", "మోడ్డ", "మొడ్డ", "మోడ్డా", "గుద్ద", "గుద్దల",
    "నాకొడక", "నాకొడుకా", "నాకొడుకు", "పూకు", "పుకు", "బోడి", "వెధవ", "వెధవా",
    "గాడిద", "చావండి", "దవడ",
    # Romanized Telugu
    "dengu", "denga", "dengey", "denginchu", "lanja", "lanjakodaka", "lanjakoduku",
    "lavada", "lawada", "lavade", "modda", "madda", "moddala", "gudha", "guddha",
    "gudhalo", "naakodaka", "nakodaka", "naakoduka", "pooku", "puku", "bodi",
    "vedhava", "vedava", "chavandi",
}

# 2. English profanity, slurs, and abusive language
_ENGLISH_ABUSIVE_TERMS = {
    "fuck", "fucking", "fucker", "fucked", "shit", "bitch", "bitching",
    "asshole", "bastard", "cunt", "dick", "dickhead", "pussy", "slut",
    "whore", "motherfucker", "cock", "bullshit", "prick", "wanker",
}

# 3. Hindi (Devanagari and Romanized)
_HINDI_ABUSIVE_TERMS = {
    "मादरचोद", "बहनचोद", "चूतिया", "गांड", "भोसड़ी", "लौड़ा", "लंड", "हरामी",
    "madarchod", "bhenchod", "behenchod", "chutiya", "gand", "gaand",
    "bhosadi", "bhosadike", "lauda", "lodu", "harami",
}

_ALL_BLOCKED_TERMS = _TELUGU_ABUSIVE_TERMS | _ENGLISH_ABUSIVE_TERMS | _HINDI_ABUSIVE_TERMS

# Regex patterns for Latin word boundaries
_LATIN_WORD_RE = re.compile(r"\b[a-zA-Z]+\b")


def sanitize_text(text: str) -> str:
    """Strip control characters, zero-width spaces, normalize unicode, and collapse whitespace."""
    if not text:
        return ""
    # Normalize unicode to NFC
    normalized = unicodedata.normalize("NFC", text)
    # Remove control characters except standard line breaks
    cleaned = "".join(ch for ch in normalized if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\r", "\t"))
    # Collapse multiple whitespace characters into a single space per line
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


def detect_abusive_content(text: str) -> str | None:
    """Returns the offending term if abusive/inappropriate text is detected, else None."""
    if not text:
        return None

    lowered = text.lower()

    # 1. Direct substring checks for native Indian scripts (Telugu, Hindi)
    for term in _TELUGU_ABUSIVE_TERMS | _HINDI_ABUSIVE_TERMS:
        # If term contains non-ASCII characters, check substring directly
        if any(ord(c) > 127 for c in term) and term in lowered:
            return term

    # 2. Word-boundary checks for Romanized/Latin words
    words = set(_LATIN_WORD_RE.findall(lowered))
    for word in words:
        if word in _ALL_BLOCKED_TERMS:
            return word

    return None


def validate_and_sanitize_persona_field(text: str | None, field_name: str) -> str:
    """Sanitizes text and validates that it contains no abusive, vulgar, or inappropriate content.

    Raises HTTPException(422) if abusive text is detected.
    """
    if text is None:
        return ""

    cleaned = sanitize_text(text)
    if not cleaned:
        return ""

    offending = detect_abusive_content(cleaned)
    if offending:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} contains inappropriate or abusive language.",
        )

    return cleaned
