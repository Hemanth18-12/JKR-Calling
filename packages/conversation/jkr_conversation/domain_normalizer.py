"""Conservative, stdlib-only domain-term correction. Pure — no I/O, no
mutation of its inputs, never auto-selects a value on the caller's behalf;
it only ranks candidates.

Important, honest limitation: `difflib.SequenceMatcher` compares character
sequences, so it can catch same-script spelling drift/abbreviations/
romanization variants ("rootcanal", "RCT", "route canal") but CANNOT bridge
cross-script phonetic corruption (Telugu-script "ఫ్రూట్ కెనాల్స్" vs.
Latin-script "root canal" share almost no characters — no similarity-ratio
algorithm connects them). The real fix for that class of error is fixing
STT configuration at the source (pinned language_code + codemix mode, see
services/api/app/live_providers/sarvam_stt.py) plus curated literal aliases
in a workspace's own vocabulary (see the seed data) — this module's fuzzy
matching is one layer of the fix, not the whole fix.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from jkr_conversation.schemas import DomainTermSnapshot

FUZZY_MATCH_THRESHOLD = 0.72

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


@dataclass(frozen=True)
class NormalizationCandidate:
    canonical: str
    matched_alias: str
    ratio: float
    category: str
    criticality: str
    domain_term_id: uuid.UUID | None = None


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _best_window_ratio(raw_text: str, term: str) -> float:
    """Extracted field values are often full sentences ("నేను ఫ్రూట్ కెనాల్స్
    చేపించుకోవడం అనుకుంటున్నాను"), not bare terms — a naive whole-string ratio
    against a short alias would almost never score high enough. This slides
    a window the same word-length as `term` across `raw_text`'s tokens and
    keeps the best-scoring window, plus a plain substring-containment check
    for the common case where the alias appears verbatim inside a longer
    value."""
    raw_lower = raw_text.lower()
    term_lower = term.lower()
    if term_lower and term_lower in raw_lower:
        return 1.0

    term_words = _tokens(term)
    raw_words = _tokens(raw_text)
    if not term_words or not raw_words:
        return SequenceMatcher(a=raw_lower, b=term_lower).ratio()

    window = len(term_words)
    best = 0.0
    for start in range(max(len(raw_words) - window + 1, 1)):
        candidate = " ".join(raw_words[start : start + window])
        ratio = SequenceMatcher(a=candidate, b=term_lower).ratio()
        best = max(best, ratio)
    # Also compare against the whole value, in case the field is already
    # short (shorter than or equal to the term itself).
    best = max(best, SequenceMatcher(a=raw_lower, b=term_lower).ratio())
    return best


def normalize(
    raw_text: str, *, vocabulary_terms: list[DomainTermSnapshot], top_k: int = 3
) -> list[NormalizationCandidate]:
    if not raw_text.strip() or not vocabulary_terms:
        return []

    candidates: list[NormalizationCandidate] = []
    for term in vocabulary_terms:
        surface_forms = [term.canonical, *term.aliases]
        best_ratio = 0.0
        best_alias = term.canonical
        for surface in surface_forms:
            if not surface.strip():
                continue
            ratio = _best_window_ratio(raw_text, surface)
            if ratio > best_ratio:
                best_ratio = ratio
                best_alias = surface
        if best_ratio >= FUZZY_MATCH_THRESHOLD:
            candidates.append(
                NormalizationCandidate(
                    canonical=term.canonical, matched_alias=best_alias, ratio=best_ratio,
                    category=term.category, criticality=term.criticality, domain_term_id=term.id,
                )
            )

    candidates.sort(key=lambda c: c.ratio, reverse=True)
    return candidates[:top_k]
