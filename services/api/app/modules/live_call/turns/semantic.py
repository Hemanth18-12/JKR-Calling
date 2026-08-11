"""P4 — SemanticCompletenessEvaluator (spec §17-19). Deliberately rule-based,
zero network calls, zero LLM calls, sub-millisecond: spec §18 is explicit
that this must not "add another 1-2 second model call" and must not
"recreate the latency problem P3.5 just optimized." Everything here is
local string inspection only.

This is a heuristic, not grammar parsing (spec §19: "these are hints, not
absolute rules") — it answers "is there strong evidence this utterance is
INCOMPLETE," and defaults to complete otherwise. That default direction is
deliberate: spec §101's priority order puts "don't cut customers off"
above "reduce latency," but also §102 wants clearly-complete turns
answered promptly — a false "incomplete" on ordinary speech would silently
violate that, so this only flags incompleteness on genuine trailing-
continuation evidence, never guesses incompleteness from mere shortness.
"""

from __future__ import annotations

from dataclasses import dataclass

from jkr_conversation.language import lang_prefix

# Curated, small, per spec §19 — "do not attempt full grammar parsing."
# Telugu-script and romanized forms both included since STT output may be
# either depending on the utterance's own script mixing.
_CONTINUATION_MARKERS_BY_PREFIX: dict[str, tuple[str, ...]] = {
    "te": ("ante", "kani", "inka", "మరి", "కానీ", "ఇంకా", "and", "but", "because", "actually", "అలాగే"),
    "hi": ("matlab", "lekin", "aur", "क्योंकि", "और", "लेकिन", "मतलब", "because", "and", "but"),
    "en": ("actually", "but", "and", "because", "if", "so", "um", "uh", "well"),
}

_TERMINAL_PUNCTUATION = (".", "?", "!", "।")
_ELLIPSIS_MARKERS = ("...", "…")


@dataclass(frozen=True)
class SemanticCompleteness:
    complete: bool
    reason: str


def evaluate(text: str, *, language_code: str) -> SemanticCompleteness:
    stripped = text.strip()
    if not stripped:
        return SemanticCompleteness(complete=False, reason="empty")

    if stripped.endswith(_ELLIPSIS_MARKERS):
        return SemanticCompleteness(complete=False, reason="trailing_ellipsis")

    lowered = stripped.lower()
    prefix = lang_prefix(language_code)
    markers = _CONTINUATION_MARKERS_BY_PREFIX.get(prefix, _CONTINUATION_MARKERS_BY_PREFIX["en"])
    # Strip trailing punctuation before comparing the last word — STT output
    # is inconsistent about whether trailing punctuation is present at all.
    last_word = lowered.rstrip("".join(_TERMINAL_PUNCTUATION) + "…,").split()[-1] if lowered.split() else ""
    if last_word in markers:
        return SemanticCompleteness(complete=False, reason="trailing_continuation_marker")

    if stripped.endswith(_TERMINAL_PUNCTUATION):
        return SemanticCompleteness(complete=True, reason="ends_with_terminal_punctuation")

    # No strong incompleteness evidence — default to complete. STT text
    # commonly arrives with no punctuation at all, so "no period" alone is
    # never treated as evidence of incompleteness (spec §101's priority
    # order: promptness for clearly-complete turns matters too).
    return SemanticCompleteness(complete=True, reason="default_complete")
