"""Deterministic business-rule backstop — the mechanism that makes "the LLM
cannot override do-not-call" literally true rather than a hopeful prompt
instruction. Consolidates three keyword lists that were previously
independent and could drift: services/voice-worker/app/conversation_engine.py's
HUMAN_HANDOFF_TRIGGERS/NO_MATCH_FALLBACK/HUMAN_HANDOFF_ACK, and
services/intelligence-worker/app/pipeline.py's _DNC_WORDS (which conflated
do-not-call and wrong-number into one signal — split apart here since
jkr_conversation.schemas.ExtractionResult tracks them separately).
"""

from __future__ import annotations

from dataclasses import replace

from jkr_conversation.language import lang_prefix
from jkr_conversation.schemas import ExtractionResult

DO_NOT_CALL_TRIGGERS = [
    "do not call", "don't call", "do not call again", "stop calling", "never call",
    "నాకు వద్దు", "call చేయకండి", "మళ్ళీ కాల్ చేయకండి", "malli call cheyyakandi",
    "मत करो कॉल", "दोबारा कॉल मत करना", "कॉल मत करना",
]

WRONG_NUMBER_TRIGGERS = [
    "wrong number", "తప్పు నంబర్", "tappu number", "गलत नंबर", "galat number",
]

HUMAN_HANDOFF_TRIGGERS = [
    "talk to a person", "talk to someone", "real person", "human agent", "speak to a manager",
    "మనిషితో మాట్లాడాలి", "మనిషిని కలపండి", "इंसान से बात", "किसी आदमी से बात करनी है",
]

# Used when a field's candidate correction is pending confirmation — a short
# yes/no reply resolves it without needing a full extraction call in mock
# mode. Real mode also uses these as a hint alongside the LLM's own
# classification (see extractor.py's _build_prompt).
CONFIRMATION_YES_TRIGGERS = ["yes", "avunu", "అవును", "correct", "ha", "haan", "sari", "సరే", "yeah", "yup"]
CONFIRMATION_NO_TRIGGERS = ["no", "kaadu", "కాదు", "nahi", "not that", "wrong", "nope"]

ACKNOWLEDGEMENT_MAX_WORDS = 3  # mirrors services/voice-worker/app/turn_manager.py's FALSE_INTERRUPTION_MAX_WORDS

DO_NOT_CALL_ACK = {
    "te": "సరే అండి, మిమ్మల్ని మళ్ళీ కాల్ చేయము. ఇబ్బంది కలిగించినందుకు క్షమించండి.",
    "hi": "ठीक है, हम आपको दोबारा कॉल नहीं करेंगे। परेशानी के लिए माफ़ी चाहते हैं।",
    "en": "Understood — we won't call you again. Sorry for the inconvenience.",
}

WRONG_NUMBER_ACK = {
    "te": "క్షమించండి అండి, పొరపాటున కాల్ చేశాము.",
    "hi": "माफ़ कीजिए, हमसे गलती से कॉल हो गया।",
    "en": "Sorry about that — we must have the wrong number.",
}

HUMAN_HANDOFF_ACK = {
    "te": "సరే అండి, నేను మా టీమ్ మెంబర్‌ని కలుపుతున్నాను, ఒక్క నిమిషం.",
    "hi": "ठीक है, मैं आपको हमारी टीम के किसी सदस्य से जोड़ रहा हूँ, एक मिनट रुकिए।",
    "en": "Sure, let me connect you with a member of our team — one moment.",
}

# Spec §16: never invent pricing/medical/eligibility/etc. — if the customer
# asks something knowledge-lookup-shaped and nothing approved matches well
# enough, say so and defer to a human rather than guessing.
NO_MATCH_FALLBACK = {
    "te": "ఆ విషయం గురించి ఖచ్చితంగా చెప్పలేను అండి, మా టీమ్ మీకు వివరాలు తెలియజేస్తుంది.",
    "hi": "उस बारे में मैं अभी पूरी तरह नहीं बता पाऊँगा, हमारी टीम आपको बताएगी।",
    "en": "I'm not fully sure about that — our team will confirm the details with you.",
}

_FALLBACK_TABLES = {
    "do_not_call": DO_NOT_CALL_ACK,
    "wrong_number": WRONG_NUMBER_ACK,
    "human_handoff": HUMAN_HANDOFF_ACK,
    "no_knowledge_match": NO_MATCH_FALLBACK,
}


def detect_do_not_call(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in DO_NOT_CALL_TRIGGERS)


def detect_wrong_number(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in WRONG_NUMBER_TRIGGERS)


def detect_human_handoff(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in HUMAN_HANDOFF_TRIGGERS)


def detect_confirmation_response(text: str) -> str | None:
    """Only meaningful when a field is actually pending confirmation —
    callers check state["pending_confirmation"] before using this. Returns
    "confirm"/"reject"/None; a genuine correction (customer says something
    else entirely) is the caller's fallback when neither matches."""
    lowered = text.strip().lower()
    if any(t in lowered for t in CONFIRMATION_YES_TRIGGERS):
        return "confirm"
    if any(t in lowered for t in CONFIRMATION_NO_TRIGGERS):
        return "reject"
    return None


def is_acknowledgement_only(text: str, *, phrases: list[str]) -> bool:
    """A short filler ("achha achha", "hmm", "okay") that isn't a real
    answer to whatever's pending — mirrors
    services/voice-worker/app/turn_manager.py's TurnManager._is_false_interruption
    word-count + phrase-list logic (that module works over simulated
    real-time timing which this turn-based path doesn't have; the
    phrase-list classification itself is directly portable)."""
    normalized = text.strip().lower()
    if not normalized or len(normalized.split()) > ACKNOWLEDGEMENT_MAX_WORDS:
        return False
    return any(normalized == p.strip().lower() for p in phrases)


def apply_backstop(extraction: ExtractionResult, *, raw_text: str) -> ExtractionResult:
    """A real do-not-call/wrong-number/human-handoff phrase in the customer's
    actual words always wins, regardless of what the LLM (or the mock
    heuristic) classified — called unconditionally in engine.py right after
    extraction, before the planner ever sees the result."""
    do_not_call = extraction.do_not_call or detect_do_not_call(raw_text)
    wrong_number = extraction.wrong_number or detect_wrong_number(raw_text)
    wants_human = extraction.wants_human or detect_human_handoff(raw_text)
    if do_not_call == extraction.do_not_call and wrong_number == extraction.wrong_number and wants_human == extraction.wants_human:
        return extraction
    return replace(extraction, do_not_call=do_not_call, wrong_number=wrong_number, wants_human=wants_human)


def fallback_text(*, kind: str, language: str) -> str:
    """kind: "do_not_call" | "wrong_number" | "human_handoff" | "no_knowledge_match" —
    used both as the mock-mode/no-LLM response and as a last-resort fallback
    if generation fails on the real-LLM path (a live call must always be able
    to say *something* safe)."""
    table = _FALLBACK_TABLES[kind]
    return table.get(lang_prefix(language), table["en"])
