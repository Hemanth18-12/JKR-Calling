# P8 — InterruptionPolicy

`services/api/app/modules/live_call/turns/interruption_policy.py`. See `docs/BARGE_IN_ARCHITECTURE.md` for
how this fits into the rest of the pipeline, and `tests/voice/barge_in/test_interruption_policy.py` (23
tests) for the executable spec this doc describes.

## Contract

Pure, synchronous, takes an explicit `now: float` rather than reading the clock — the same discipline
`TurnManager` (P4) and `SemanticCompletenessEvaluator` (P4) already established, for the same reasons:
fake-clock-testable with zero real sleeps, and safe to call from a hot signal path (a VAD transition, a
partial transcript) without adding latency. **No LLM call, no I/O, no network** — every input is either
already-computed local state or a small local keyword/phrase table.

```python
def decide(evidence: InterruptionEvidence) -> InterruptionDecision: ...
```

```python
@dataclass(frozen=True)
class InterruptionEvidence:
    now: float
    candidate_started_at: float       # when this speech burst's evidence first appeared
    local_vad_speech: bool
    provider_speech: bool
    partial_text: str | None
    final_text: str | None
    language_code: str
    expecting_confirmation: bool      # sourced from redis_state["pending_confirmation"]
    agent_response_state: str | None  # coordinator ResponseState.value, or None
    interruptible: bool = True
    sensitivity: str = "balanced"

@dataclass(frozen=True)
class InterruptionDecision:
    action: InterruptionAction   # IGNORE | MONITOR | WAIT_FOR_MORE_AUDIO | BACKCHANNEL | INTERRUPT | INTERRUPT_CRITICAL
    priority: InterruptionPriority  # NONE | BACKCHANNEL | NORMAL | HIGH | CRITICAL
    confidence: float
    reason: str
```

The caller (`streaming_bridge.py`) owns the mutable `_InterruptionCandidate` across repeated calls for the
same burst — `interruption_policy.py` itself holds no state between calls, matching `TurnManager`'s own
"pure function, caller owns state and the clock" split.

## What's reused, not reinvented

- **`turns/backchannel.classify(text, expecting_confirmation=...)`** (P4) — the context-aware
  backchannel-vs-real-answer distinction. `is_backchannel_shaped and not likely_real_answer` → `BACKCHANNEL`
  (never interrupts); `is_backchannel_shaped and likely_real_answer` (e.g. "haa" while the agent is mid
  yes/no question) → `INTERRUPT` at `NORMAL` priority, reason `direct_answer_to_pending_confirmation`. This
  is the exact mechanism that already prevents "hmm" from closing a *turn* in `TurnManager`, now reused for
  a different decision (interrupting a *response*) rather than rebuilt.
- **`jkr_conversation.policy.detect_do_not_call/wrong_number/human_handoff`** — the existing, already-
  enforced local keyword backstop. Reused as the `CRITICAL`-priority cue detector so there is one DNC/
  handoff phrase list in the codebase, not two that can drift apart.

## What's genuinely new: the high-priority cue table

No generic "stop / wait / one minute / no / actually" interruption-urgency list existed anywhere before
P8. `_HIGH_PRIORITY_CUES_BY_PREFIX` (English, Telugu, Hindi), modeled on `semantic.py`'s existing per-
language continuation-marker table style — small, curated, substring-matched. **English cues are always
checked in addition to the language-specific list**, never selected exclusively by `lang_prefix()`: every
profile in this codebase is code-mixed by default (`te-en-IN`, `hi-en-IN`), and a customer speaking Telugu
naturally drops in an English "wait" or "one minute" mid-sentence — a lookup that only checked the Telugu
list would miss exactly the phrases this feature most needs to catch quickly.

## The decision table

1. **No active response, or the active response is already terminal** → `IGNORE`, reason `no_active_response`.
2. **Non-interruptible response** (`interruptible=False` — a legally-required compliance notice):
   - A critical cue anywhere in the available text → `INTERRUPT_CRITICAL` anyway (spec: DNC/wrong-number/
     human-handoff always overrides).
   - Otherwise → `MONITOR` (never interrupts on ordinary speech).
3. **Critical cue detected** (DNC/wrong-number/human-handoff) → `INTERRUPT_CRITICAL`, priority `CRITICAL`,
   **bypasses the qualification window entirely** — a customer saying "don't call me" doesn't need to keep
   talking for the window to elapse first.
4. **High-priority cue detected** ("stop"/"wait"/"one minute"/"no"/"actually"/...) → `INTERRUPT`, priority
   `HIGH`, also bypasses the window.
5. **Backchannel-shaped text** (see above) → `BACKCHANNEL` or `INTERRUPT`/`NORMAL`, per the
   `expecting_confirmation` split.
6. **Any other non-empty text**:
   - If word count is already at or above the sensitivity preset's `min_words_for_new_utterance` → treated
     as strong-enough evidence on its own, `INTERRUPT`/`NORMAL` immediately, **regardless of the
     qualification window** (a two-word non-backchannel phrase is already unlikely to be noise; waiting
     further only adds latency without improving accuracy).
   - Otherwise, still within the qualification window → `MONITOR` (not enough evidence yet).
7. **No transcript text at all yet** (only VAD/provider speech evidence):
   - Evidence already ended (`local_vad_speech=False, provider_speech=False`) before the window elapsed,
     with never any transcript → `IGNORE`, reason `speech_ended_before_qualification_no_transcript` (the
     cough/noise case).
   - Still within the window → `MONITOR`.
   - Past the window but before the sensitivity preset's escalation threshold → `WAIT_FOR_MORE_AUDIO`.
   - Past the escalation threshold, speech still ongoing → `INTERRUPT`/`NORMAL`, reason
     `sustained_speech_no_transcript_yet` — duration alone is meaningful evidence once it's sustained this
     long, even with STT still catching up.
   - Past the escalation threshold, speech already ended → `IGNORE`.

## Sensitivity presets

```python
_THRESHOLDS = {
    "low":      SensitivityThresholds(qualification_window_ms=400, sustained_speech_escalation_ms=1200, min_words_for_new_utterance=2),
    "balanced": SensitivityThresholds(qualification_window_ms=250, sustained_speech_escalation_ms=900,  min_words_for_new_utterance=2),
    "high":     SensitivityThresholds(qualification_window_ms=120, sustained_speech_escalation_ms=600,  min_words_for_new_utterance=1),
}
```

Conservative starting points, explicitly **not** presented as measured-optimal (same honest framing
`turns/policies.py`'s own FAST/BALANCED/PATIENT presets carry from P4) — real-call benchmarking is still
outstanding. `BALANCED` is the only preset ever defaulted to automatically; `HIGH` must be opted into
deliberately (`BARGE_IN_SENSITIVITY=high`), per the spec's own explicit "never default to HIGH without
real-call false-positive measurement."

A response with `agent_response_state` in `{created, generating_text, text_streaming}` (no audio produced
yet) gets its qualification window **halved** (floor 60ms) — there's nothing already delivered to protect
against a false positive, so waiting the full window before stopping an as-yet-silent response only adds
latency for no accuracy benefit.

## What this module deliberately does not do

- Decide *how* to cancel anything — that's `RealtimePipelineCoordinator.interrupt_active_response()`
  (`docs/BARGE_IN_ARCHITECTURE.md`).
- Track candidates across calls to `decide()` — the caller does that (`_InterruptionCandidate` in
  `streaming_bridge.py`).
- Full grammar/intent parsing — same "hints, not absolute rules" posture `semantic.py` already established
  for a different decision; a false negative here just means the customer's evidence keeps accumulating
  until it's unambiguous (`MONITOR`/`WAIT_FOR_MORE_AUDIO` are not failures, they're "not yet").
