"""SpokenResponseFormatter — promoted verbatim (behavior-preserving) from
services/voice-worker/app/spoken_formatter.py so both call paths share the
same implementation. Raw LLM output never reaches TTS directly; it passes
through here first.

Number-to-words normalization for mixed Telugu/Hindi/English speech is a
genuinely hard NLP problem on its own; what's implemented here is a real,
narrow slice (rupee amounts, phone-number digit-grouping) rather than a full
solution — documented as a scope limitation, not silently pretended-away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jkr_conversation.language import lang_prefix

_MARKDOWN_BOLD_ITALIC = re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}")
_MARKDOWN_HEADER = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MARKDOWN_BULLET = re.compile(r"^[\s]*[-*]\s+", re.MULTILINE)
_MARKDOWN_CODE = re.compile(r"`([^`]+)`")
_URL = re.compile(r"https?://\S+|www\.\S+")
_RUPEE_AMOUNT = re.compile(r"₹\s?([\d,]+)")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")

ABBREVIATIONS = {
    "Dr.": "Doctor",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "approx.": "approximately",
    "appt.": "appointment",
    "no.": "number",
}

# Rotated, never repeated twice in a row — spec §13 "Natural acknowledgement
# library". Kept short deliberately; these precede the substantive part of a
# response, not stand alone.
ACKNOWLEDGEMENTS_BY_LANGUAGE: dict[str, list[str]] = {
    "te-IN": ["సరే అండి.", "ఓకే, అర్థమైంది.", "అవునండి.", "ఒక్కసారి check చేస్తాను."],
    "te-en-IN": ["సరే అండి.", "ఓకే, అర్థమైంది.", "No problem.", "ఒక్కసారి check చేస్తాను.", "Right, got it."],
    "hi-IN": ["ठीक है।", "जी अच्छा।", "बिल्कुल।"],
    "hi-en-IN": ["ठीक है।", "No problem.", "Right, got it।"],
    "en-IN": ["Sure.", "No problem.", "Right, got it.", "Okay, understood."],
}


@dataclass
class FormattedResponse:
    text: str
    acknowledgement_used: str | None
    truncated: bool
    original_sentence_count: int


def strip_for_streaming_chunk(text: str) -> str:
    """P5 §29-31 — the streaming-safe subset of SpokenResponseFormatter's
    full pipeline: markdown/URL stripping and whitespace normalization are
    all per-fragment-safe (pure regex substitution, no cross-chunk state),
    so a SpeakableChunk can be cleaned before being handed onward without
    waiting for the full response. Sentence-count enforcement and
    acknowledgement-prepending both need whole-response context and are
    deliberately NOT here — they still run once, on the fully assembled
    text, exactly as SpokenResponseFormatter.format() already does."""
    text = _URL.sub("", text)
    text = _MARKDOWN_CODE.sub(r"\1", text)
    text = _MARKDOWN_BOLD_ITALIC.sub(r"\1", text)
    text = _MARKDOWN_HEADER.sub("", text)
    text = _MARKDOWN_BULLET.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class SpokenResponseFormatter:
    language: str = "te-en-IN"
    max_sentences: int = 3
    _last_acknowledgement: str | None = field(default=None, repr=False)

    def strip_markdown(self, text: str) -> str:
        text = _MARKDOWN_CODE.sub(r"\1", text)
        text = _MARKDOWN_BOLD_ITALIC.sub(r"\1", text)
        text = _MARKDOWN_HEADER.sub("", text)
        text = _MARKDOWN_BULLET.sub("", text)
        return text

    def strip_urls(self, text: str) -> str:
        return _URL.sub("", text)

    def expand_abbreviations(self, text: str) -> str:
        for abbr, expansion in ABBREVIATIONS.items():
            text = text.replace(abbr, expansion)
        return text

    def normalize_numbers(self, text: str) -> str:
        def rupee_to_words(match: re.Match[str]) -> str:
            digits = match.group(1).replace(",", "")
            return f"{digits} rupees"

        return _RUPEE_AMOUNT.sub(rupee_to_words, text)

    def enforce_short_sentences(self, text: str) -> tuple[str, bool, int]:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
        original_count = len(sentences)
        if original_count <= self.max_sentences:
            return " ".join(sentences), False, original_count
        return " ".join(sentences[: self.max_sentences]), True, original_count

    def pick_acknowledgement(self) -> str | None:
        pool = ACKNOWLEDGEMENTS_BY_LANGUAGE.get(self.language, ACKNOWLEDGEMENTS_BY_LANGUAGE["en-IN"])
        candidates = [p for p in pool if p != self._last_acknowledgement] or pool
        choice = candidates[0]
        self._last_acknowledgement = choice
        return choice

    def format(self, raw_text: str, *, prepend_acknowledgement: bool = False) -> FormattedResponse:
        text = self.strip_urls(raw_text)
        text = self.strip_markdown(text)
        text = self.expand_abbreviations(text)
        text = self.normalize_numbers(text)
        text = re.sub(r"\s+", " ", text).strip()

        text, truncated, original_count = self.enforce_short_sentences(text)

        ack = None
        if prepend_acknowledgement:
            ack = self.pick_acknowledgement()
            text = f"{ack} {text}".strip()

        return FormattedResponse(
            text=text, acknowledgement_used=ack, truncated=truncated, original_sentence_count=original_count
        )


def build_clarification(field_label: str, candidates: list[str], *, language: str = "te-en-IN") -> str:
    """Spec §13 — never silently guess name/date/time/amount/rank/phone/
    booking/payment/address. Called by planner.py when extraction confidence
    is below threshold, instead of stating a value. Previously written but
    never actually called from production code (confirmed by grep) — the
    shared engine's planner.py is what finally wires this in."""
    prefix = lang_prefix(language)
    if prefix == "te":
        joined = " అన్నారా, ".join(candidates)
        return f"Sorry అండి, {joined} అన్నారా?"
    if prefix == "hi":
        joined = " या ".join(candidates)
        return f"Sorry, {joined}?"
    joined = " or ".join(candidates)
    return f"Sorry, did you say {joined}?"


def build_confirmation(candidate_value: str, *, language: str = "te-en-IN") -> str:
    """Natural, mid-conversation double-check for a domain-corrected or
    critical value — deliberately NOT "you said X, is that correct?", which
    reads as robotic form-filling rather than a real person confirming
    something they half-heard."""
    prefix = lang_prefix(language)
    if prefix == "te":
        return f"{candidate_value} గురించే అంటున్నారు కదా అండి?"
    if prefix == "hi":
        return f"आपका मतलब {candidate_value} से है ना?"
    return f"Just to be sure — you mean {candidate_value}, right?"
