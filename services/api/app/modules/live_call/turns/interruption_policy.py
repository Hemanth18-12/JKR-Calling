"""P8 — InterruptionPolicy: the pure decision function behind automatic
barge-in (see docs/P8_BARGE_IN_AUDIT.md, docs/INTERRUPTION_POLICY.md).

Deliberately follows the exact same shape TurnManager (manager.py) and
SemanticCompletenessEvaluator (semantic.py) already established in P4:
pure, synchronous, takes an explicit `now: float` rather than reading the
clock itself, does no I/O, no asyncio, and — the P8 spec's own explicit
requirement — no LLM call. This is what makes it safe to call from a hot
signal path (a VAD transition, a partial transcript) without adding
latency or a network dependency, and what makes it fake-clock-testable
with zero real sleeps (see tests/voice/barge_in/test_interruption_policy.py).

This module does NOT decide *how* to carry out an interruption (cancel
order, Twilio clear, task cancellation) — that orchestration lives in
RealtimePipelineCoordinator.interrupt_active_response() (coordinator.py).
InterruptionPolicy only answers "given what we currently know about this
customer speech burst and the agent's current state, what should happen
next" — IGNORE / MONITOR / WAIT_FOR_MORE_AUDIO / BACKCHANNEL / INTERRUPT /
INTERRUPT_CRITICAL. The caller (streaming_bridge.py) re-evaluates this on
every new piece of evidence (VAD transition, provider speech event, partial
transcript) for the same candidate, rather than this module holding any
mutable state itself — same "caller owns the clock and the state, the
function is pure" split TurnManager uses for its own on_timer_tick().

Reuses, rather than rebuilds (per the spec's explicit instruction):
  - turns.backchannel.classify() — the exact context-aware backchannel-vs-
    real-answer distinction already built for turn-completion in P4, now
    also used for interruption classification.
  - jkr_conversation.policy.detect_do_not_call/wrong_number/human_handoff —
    the existing, already-enforced local keyword backstop, reused as the
    CRITICAL-priority cue detector so there is one DNC/handoff phrase list
    in this codebase, not two that can drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jkr_conversation.language import lang_prefix
from jkr_conversation.policy import detect_do_not_call, detect_human_handoff, detect_wrong_number

from app.modules.live_call.turns import backchannel

# --- language-aware high-priority cues (spec: "stop / wait / one minute /
# no / wrong / don't / actually" family) — same curated, small,
# substring-matched style semantic.py's own continuation-marker table uses.
# Deliberately NOT exhaustive NLU — these are early, low-latency signals
# meant to fire on a short partial transcript, before a full final exists.
_HIGH_PRIORITY_CUES_BY_PREFIX: dict[str, tuple[str, ...]] = {
    "en": ("stop", "wait", "one minute", "one min", "hold on", "no ", "no,", "wrong", "don't", "dont", "actually", "excuse me"),
    "te": ("ఆగండి", "ఆగు", "wait", "ఒక్క నిమిషం", "okka nimisham", "vaddu", "వద్దు", "తప్పు", "tappu", "kaani", "కానీ"),
    "hi": ("रुको", "ruko", "रुकिए", "rukiye", "एक मिनट", "ek minute", "नहीं", "nahi", "galat", "गलत"),
}


class InterruptionAction(StrEnum):
    IGNORE = "ignore"
    MONITOR = "monitor"
    WAIT_FOR_MORE_AUDIO = "wait_for_more_audio"
    BACKCHANNEL = "backchannel"
    INTERRUPT = "interrupt"
    INTERRUPT_CRITICAL = "interrupt_critical"


class InterruptionPriority(StrEnum):
    NONE = "none"
    BACKCHANNEL = "backchannel"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class InterruptionDecision:
    action: InterruptionAction
    priority: InterruptionPriority
    confidence: float
    reason: str


@dataclass(frozen=True)
class SensitivityThresholds:
    qualification_window_ms: int
    sustained_speech_escalation_ms: int
    min_words_for_new_utterance: int


# Conservative starting points, not measured-optimal — same honest framing
# turns/policies.py's own preset table uses. BALANCED is the only preset
# ever defaulted to automatically; HIGH must be opted into deliberately
# (spec: "never default to HIGH without real-call false-positive
# measurement").
_THRESHOLDS: dict[str, SensitivityThresholds] = {
    "low": SensitivityThresholds(qualification_window_ms=400, sustained_speech_escalation_ms=1200, min_words_for_new_utterance=2),
    "balanced": SensitivityThresholds(qualification_window_ms=250, sustained_speech_escalation_ms=900, min_words_for_new_utterance=2),
    "high": SensitivityThresholds(qualification_window_ms=120, sustained_speech_escalation_ms=600, min_words_for_new_utterance=1),
}
# A response that has produced no audio yet (still generating text, or TTS
# hasn't sent anything to Twilio) costs nothing to stop early — halving the
# qualification window here is not "being more sensitive," it's recognizing
# there is no already-delivered audio to protect against a false positive.
_NO_AUDIO_YET_WINDOW_DIVISOR = 2
_MIN_QUALIFICATION_WINDOW_MS = 60

# Response states (mirrors coordinator.ResponseState's values, duplicated as
# plain strings here rather than importing coordinator.py — turns/ has no
# dependency on transport/ anywhere else, and this keeps InterruptionPolicy
# importable/testable with zero transport-layer setup).
_NO_AUDIO_YET_STATES = frozenset({"created", "generating_text", "text_streaming"})
_INACTIVE_STATES = frozenset({"playback_complete", "cancelled", "superseded", "failed", "interrupted"})


def get_thresholds(sensitivity: str) -> SensitivityThresholds:
    return _THRESHOLDS.get(sensitivity, _THRESHOLDS["balanced"])


def _has_critical_cue(text: str) -> bool:
    return detect_do_not_call(text) or detect_wrong_number(text) or detect_human_handoff(text)


def _has_high_priority_cue(text: str, *, language_code: str) -> bool:
    # Every profile in this codebase is code-mixed by default (te-en-IN,
    # hi-en-IN — see jkr_conversation.language) — a customer speaking
    # Telugu naturally drops in an English "wait" or "one minute" mid-
    # sentence, so the English cue list is always checked in addition to
    # (never instead of) the language-specific one, not selected exclusively
    # by lang_prefix() the way semantic.py's continuation markers are.
    lowered = text.lower()
    prefix = lang_prefix(language_code)
    cues = _HIGH_PRIORITY_CUES_BY_PREFIX.get(prefix, ())
    if prefix != "en":
        cues = cues + _HIGH_PRIORITY_CUES_BY_PREFIX["en"]
    else:
        cues = _HIGH_PRIORITY_CUES_BY_PREFIX["en"]
    return any(cue in lowered for cue in cues)


@dataclass(frozen=True)
class InterruptionEvidence:
    """Everything InterruptionPolicy.decide() needs, gathered by the caller
    from P4/P7 primitives already reused unchanged (see module docstring).
    One instance per decide() call — the caller re-builds this fresh as new
    evidence arrives for the same candidate; nothing here is mutated."""

    now: float
    candidate_started_at: float  # when customer speech evidence first appeared while the agent was active
    local_vad_speech: bool  # EnergyVAD currently thinks the customer is speaking
    provider_speech: bool  # provider's own SpeechStarted/SpeechEnded currently thinks the customer is speaking
    partial_text: str | None  # latest STT partial for this burst, if any
    final_text: str | None  # a just-committed STT final, if decide() is being called for one
    language_code: str
    expecting_confirmation: bool  # sourced from redis_state["pending_confirmation"] — same input backchannel.classify() already uses
    agent_response_state: str | None  # coordinator ActiveResponseContext.state.value, or None if no active response
    interruptible: bool = True  # False only for legally-required non-interruptible compliance units
    sensitivity: str = "balanced"


def decide(evidence: InterruptionEvidence) -> InterruptionDecision:
    if evidence.agent_response_state is None or evidence.agent_response_state in _INACTIVE_STATES:
        return InterruptionDecision(InterruptionAction.IGNORE, InterruptionPriority.NONE, 1.0, "no_active_response")

    text = (evidence.final_text or evidence.partial_text or "").strip()

    if not evidence.interruptible:
        # Spec: DNC/wrong-number/human-handoff must ALWAYS override a
        # non-interruptible compliance notice; nothing else may interrupt it.
        if text and _has_critical_cue(text):
            return InterruptionDecision(InterruptionAction.INTERRUPT_CRITICAL, InterruptionPriority.CRITICAL, 0.95, "critical_cue_overrides_non_interruptible")
        return InterruptionDecision(InterruptionAction.MONITOR, InterruptionPriority.NONE, 0.5, "non_interruptible_response_active")

    thresholds = get_thresholds(evidence.sensitivity)
    window_ms = thresholds.qualification_window_ms
    if evidence.agent_response_state in _NO_AUDIO_YET_STATES:
        window_ms = max(_MIN_QUALIFICATION_WINDOW_MS, window_ms // _NO_AUDIO_YET_WINDOW_DIVISOR)
    elapsed_ms = (evidence.now - evidence.candidate_started_at) * 1000

    # Early critical/high-priority cues interrupt as soon as they appear in
    # a partial transcript, deliberately bypassing the qualification window
    # (spec: "interrupt before waiting for full transcript") — a customer
    # who has said "one minute" doesn't need to keep talking for 250ms more
    # before we start reacting.
    if text and _has_critical_cue(text):
        return InterruptionDecision(InterruptionAction.INTERRUPT_CRITICAL, InterruptionPriority.CRITICAL, 0.95, "critical_cue_detected")
    if text and _has_high_priority_cue(text, language_code=evidence.language_code):
        return InterruptionDecision(InterruptionAction.INTERRUPT, InterruptionPriority.HIGH, 0.85, "high_priority_cue_detected")

    if text:
        classification = backchannel.classify(text, expecting_confirmation=evidence.expecting_confirmation)
        if classification.is_backchannel_shaped:
            if classification.likely_real_answer:
                # e.g. "haa" while the agent asked a direct yes/no question —
                # a genuine answer, not a filler (spec's explicit example).
                return InterruptionDecision(InterruptionAction.INTERRUPT, InterruptionPriority.NORMAL, 0.8, "direct_answer_to_pending_confirmation")
            return InterruptionDecision(InterruptionAction.BACKCHANNEL, InterruptionPriority.BACKCHANNEL, 0.8, "backchannel_shaped_not_expected_as_answer")

        word_count = len(text.split())
        if elapsed_ms < window_ms and word_count < thresholds.min_words_for_new_utterance:
            return InterruptionDecision(InterruptionAction.MONITOR, InterruptionPriority.NONE, 0.4, "within_qualification_window")
        return InterruptionDecision(InterruptionAction.INTERRUPT, InterruptionPriority.NORMAL, 0.75, "new_utterance_detected")

    # No transcript text yet — decide purely from speech-duration evidence.
    speech_ongoing = evidence.local_vad_speech or evidence.provider_speech
    if not speech_ongoing and elapsed_ms < window_ms:
        # VAD/provider speech already ended, below the qualification
        # window, with no transcript ever produced — the noise/cough case.
        return InterruptionDecision(InterruptionAction.IGNORE, InterruptionPriority.NONE, 0.6, "speech_ended_before_qualification_no_transcript")
    if elapsed_ms < window_ms:
        return InterruptionDecision(InterruptionAction.MONITOR, InterruptionPriority.NONE, 0.3, "within_qualification_window_no_transcript")
    if elapsed_ms < thresholds.sustained_speech_escalation_ms:
        return InterruptionDecision(InterruptionAction.WAIT_FOR_MORE_AUDIO, InterruptionPriority.NONE, 0.5, "past_qualification_window_awaiting_transcript")
    if speech_ongoing:
        # Sustained speech well past the qualification window with STT still
        # producing nothing — real evidence on its own (spec: duration is a
        # meaningful input even without transcript text).
        return InterruptionDecision(InterruptionAction.INTERRUPT, InterruptionPriority.NORMAL, 0.55, "sustained_speech_no_transcript_yet")
    return InterruptionDecision(InterruptionAction.IGNORE, InterruptionPriority.NONE, 0.4, "speech_ended_no_transcript_ever_produced")
