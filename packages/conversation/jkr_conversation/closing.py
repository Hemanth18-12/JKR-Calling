"""Centralized, deterministic closing text — the fix for the abrupt-hangup
bug: a non-tool-backed COMPLETE_OBJECTIVE used to fall through to free LLM
generation with no finality guarantee ("if tomorrow morning works, I can
reinstate it" — then the call hung up immediately). Every reason here maps
to a canned, per-language table — never open generation — and every
template contains an explicit, localized finality phrase ("thank you, have
a good day" / "ధన్యవాదాలు, శుభదినం" / "धन्यवाद, आपका दिन शुभ हो").
"""

from __future__ import annotations

from jkr_conversation import policy
from jkr_conversation.language import lang_prefix
from jkr_conversation.objectives import ObjectiveDefinition

DO_NOT_CALL = "do_not_call"
WRONG_NUMBER = "wrong_number"
HUMAN_HANDOFF = "human_handoff"
OBJECTIVE_COMPLETED = "objective_completed"
CALL_TIME_LIMIT = "call_time_limit"  # covers both max_turns_reached and max_duration_reached — no customer-facing difference
REOPENED_REAFFIRM = "reopened_reaffirm"  # objective re-completes after a grace-period reopen — see build_closing_text

CALL_TIME_LIMIT_CLOSING = {
    "te": "సమయం అయిపోయింది అండి, మీరు ఇచ్చిన వివరాలు నోట్ చేసుకున్నాను.{callback_note} మా టీమ్ మిమ్మల్ని త్వరలో సంప్రదిస్తుంది. ధన్యవాదాలు, శుభదినం!",
    "hi": "समय हो गया है, मैंने आपकी जानकारी नोट कर ली है।{callback_note} हमारी टीम जल्द ही आपसे संपर्क करेगी। धन्यवाद, आपका दिन शुभ हो!",
    "en": "We're almost out of time for this call — I've noted what you've shared.{callback_note} Our team will follow up shortly. Thank you, have a good day!",
}

HUMAN_HANDOFF_CLOSING = {
    "te": "సరే అండి, ఈ విషయం గురించి మా టీమ్ మెంబర్ మీకు తిరిగి కాల్ చేస్తారు. ధన్యవాదాలు, శుభదినం!",
    "hi": "ठीक है, इस बारे में हमारी टीम का कोई सदस्य आपको वापस कॉल करेगा। धन्यवाद, आपका दिन शुभ हो!",
    "en": "Understood — a member of our team will call you back shortly to help with this. Thank you, have a good day!",
}

# Deliberately short — used when the objective re-completes immediately
# after a grace-period reopen (customer kept talking after the first
# closing already played). Repeating the full closing script verbatim
# reads as a broken robot ("Thank you...goodbye" twice); a brief
# reaffirmation still carries a finality marker without the repetition.
REOPENED_REAFFIRM_CLOSING = {
    "te": "సరే అండి, నోట్ చేసుకున్నాను. ధన్యవాదాలు!",
    "hi": "ठीक है, नोट कर लिया है। धन्यवाद!",
    "en": "Got it, noted — thank you!",
}

_FINALITY_ALLOWLIST = (
    "thank you", "have a good day", "goodbye", "bye",
    "ధన్యవాదాలు", "శుభదినం", "ఉంటాను", "నమస్తే",
    "धन्यवाद", "शुभ हो", "नमस्ते",
)


def build_context(state: dict) -> dict:
    """Light slot-filling only — never open generation. One placeholder
    wired up (CALL_TIME_LIMIT's callback_note); more objective-specific
    slots is a natural, low-risk follow-up, not required for the three
    confirmed bugs this module fixes."""
    callback_time = (state.get("known_fields") or {}).get("preferred_callback_time")
    return {"callback_note": f" We'll aim to reach you around {callback_time}." if callback_time else ""}


def build_closing_text(reason: str, *, objective: ObjectiveDefinition, language: str, context: dict | None = None) -> str:
    prefix = lang_prefix(language)
    context = context or {}
    if reason == DO_NOT_CALL:
        text = policy.fallback_text(kind="do_not_call", language=language)
    elif reason == WRONG_NUMBER:
        text = policy.fallback_text(kind="wrong_number", language=language)
    elif reason == HUMAN_HANDOFF:
        text = HUMAN_HANDOFF_CLOSING.get(prefix, HUMAN_HANDOFF_CLOSING["en"])
    elif reason == CALL_TIME_LIMIT:
        text = CALL_TIME_LIMIT_CLOSING.get(prefix, CALL_TIME_LIMIT_CLOSING["en"])
    elif reason == REOPENED_REAFFIRM:
        text = REOPENED_REAFFIRM_CLOSING.get(prefix, REOPENED_REAFFIRM_CLOSING["en"])
    else:  # OBJECTIVE_COMPLETED and any unrecognized reason
        text = objective.closing_text.get(prefix, objective.closing_text["en"])
    for key, value in context.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def has_finality_marker(text: str) -> bool:
    """Used by tests (and available for future runtime validation) to check
    a closing line actually signals the call is ending, rather than trusting
    keyword-matching alone as documentation."""
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in _FINALITY_ALLOWLIST)
