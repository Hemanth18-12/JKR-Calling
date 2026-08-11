"""One consolidated language-prefix helper. Previously duplicated inline in
at least three places (services/voice-worker/app/conversation_engine.py
lines 364/416, and providers/mock.py's private _lang_prefix) — each copy
free to drift independently. This is the single source of truth now.

Also the single source of truth for language *profiles* — fixes a real bug:
`lang_prefix("te-IN")` and `lang_prefix("te-en-IN")` both return "te", which
is exactly right for picking a script/pronunciation, but wrong for deciding
WHETHER to code-mix at all — prompt_builder.py used to instruct "mix English
words in, code-switch" unconditionally for every language value, including
the three -only profiles, which is precisely backwards for a customer who
selected strict Telugu/Hindi/English.
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_PREFIXES = ("te", "hi", "en")


def lang_prefix(language: str) -> str:
    """"te-en-IN" -> "te", "hi-IN" -> "hi", anything unrecognized -> "en"."""
    prefix = language.split("-")[0].lower()
    return prefix if prefix in SUPPORTED_PREFIXES else "en"


@dataclass(frozen=True)
class LanguageProfile:
    code: str  # "te-IN" | "hi-IN" | "en-IN" | "te-en-IN" | "hi-en-IN" — matches jkr_db.enums.LanguageCode exactly
    base_language: str  # "te" | "hi" | "en"
    display_name: str  # "Telugu" | "Hindi" | "English"
    code_mixed: bool  # whether English mixing is the expected, natural register for this profile
    strict_language: bool  # true for the three "-only" profiles — no deliberate code-switching


_PROFILES: dict[str, LanguageProfile] = {
    "te-IN": LanguageProfile(code="te-IN", base_language="te", display_name="Telugu", code_mixed=False, strict_language=True),
    "hi-IN": LanguageProfile(code="hi-IN", base_language="hi", display_name="Hindi", code_mixed=False, strict_language=True),
    "en-IN": LanguageProfile(code="en-IN", base_language="en", display_name="English", code_mixed=False, strict_language=True),
    "te-en-IN": LanguageProfile(code="te-en-IN", base_language="te", display_name="Telugu", code_mixed=True, strict_language=False),
    "hi-en-IN": LanguageProfile(code="hi-en-IN", base_language="hi", display_name="Hindi", code_mixed=True, strict_language=False),
}


def get_language_profile(language_code: str) -> LanguageProfile:
    """Exact match against the 5 known profiles first. An unrecognized value
    (should not normally happen — Agent.primary_language/CallSession.language
    are meant to be one of the 5) falls back to the code-mixed variant for
    its base language, matching this system's own long-standing default
    behavior rather than surprising an edge case into sudden strict mode."""
    exact = _PROFILES.get(language_code)
    if exact is not None:
        return exact
    prefix = lang_prefix(language_code)
    return _PROFILES.get(f"{prefix}-en-IN", _PROFILES["en-IN"])
