"""P4 — BackchannelClassifier (spec §29-30). Deliberately a small, local
phrase list here rather than importing jkr_conversation.policy's
CONFIRMATION_YES/NO_TRIGGERS or accidental_interruption_phrases directly:
this module answers a transport-layer TIMING question ("is this utterance
short/filler-shaped enough that TurnManager should treat completion
evidence more cautiously"), not the conversation engine's own acknowledgement/
confirmation semantics (jkr_conversation.extractor's is_acknowledgement_only
already owns that, downstream, unchanged by P4 — see manager.py's docstring
for why the two layers deliberately don't share one list).

Context-aware per spec §30: the same "haa" means different things depending
on whether the caller is currently expecting a direct yes/no answer
(TurnManager is told this via `expecting_confirmation`, sourced from the
call's `pending_confirmation` state) — never a global "always discard
acknowledgements" rule.
"""

from __future__ import annotations

from dataclasses import dataclass

_BACKCHANNEL_PHRASES = frozenset({
    "hmm", "hm", "haa", "haan", "achha", "acha", "okay", "ok", "right", "avunu",
    "sare", "yeah", "yes", "no", "kaadu", "nahi", "theek hai", "ok ok",
})
_MAX_BACKCHANNEL_WORDS = 3


@dataclass(frozen=True)
class BackchannelClassification:
    is_backchannel_shaped: bool
    likely_real_answer: bool


def classify(text: str, *, expecting_confirmation: bool) -> BackchannelClassification:
    normalized = text.strip().lower()
    word_count = len(normalized.split())
    is_backchannel_shaped = 0 < word_count <= _MAX_BACKCHANNEL_WORDS and normalized in _BACKCHANNEL_PHRASES
    likely_real_answer = is_backchannel_shaped and expecting_confirmation
    return BackchannelClassification(is_backchannel_shaped=is_backchannel_shaped, likely_real_answer=likely_real_answer)
