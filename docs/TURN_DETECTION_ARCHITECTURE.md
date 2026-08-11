# P4 — Turn Detection Architecture

See `docs/P4_TURN_DETECTION_AUDIT.md` for what this replaces and why, and
`docs/P4_TURN_DETECTION_RESULTS.md` for verification status.

## Where it lives

```
services/api/app/modules/live_call/turns/
    __init__.py
    signals.py     — TurnSignal / TurnSignalType: the normalized evidence model
    state.py       — TurnState, TurnDecision, TranscriptSegment, UserTurnCommitted, TurnDebugTrace
    policies.py     — TurnPolicy + FAST/BALANCED/PATIENT presets
    semantic.py     — SemanticCompletenessEvaluator (rule-based, no LLM)
    backchannel.py  — BackchannelClassifier (context-aware)
    vad.py          — VADProvider protocol + EnergyVAD (local, no ML dependency)
    manager.py      — TurnManager: the single authority for turn boundaries
    metrics.py      — process-wide counters (spec §97)
```

`services/api`, not a new package, because turn detection is inherently coupled to the live Twilio
Media Stream session (`RealtimeMediaSession`, `streaming_bridge.py`) it observes — there's no
cross-service reuse need the way `jkr_conversation` has (shared between real calls and Test Lab).

## The core design decision: TurnManager is pure and synchronous

Every `TurnManager` method takes an explicit `now: float` (or a `TurnSignal` whose own `timestamp`
is caller-supplied) and does zero I/O, zero `asyncio`, zero clock reads of its own. This one decision
answers three of the spec's own requirements at once:

1. **Fake-clock testability (spec §110-111)** — every unit test passes explicit timestamps; nothing
   sleeps for real. `docs/P4_TURN_DETECTION_AUDIT.md`'s thinking-pause/max-timeout/user-resume
   scenarios are all deterministic, sub-millisecond tests.
2. **Safe to call from two concurrent asyncio tasks without a lock.** `streaming_bridge.py` has two
   tasks reading the same inbound audio: the STT-event-consuming loop (feeds `PROVIDER_SPEECH_START/
   END`, `STT_PARTIAL`, `STT_FINAL`) and the audio-forwarding loop (feeds local VAD signals, when
   enabled). A synchronous method call never yields control mid-method in a single-threaded event
   loop, so two calls from different tasks can never interleave — no lock, no race, by construction.
3. **CPU-cheap by construction (spec §87-90)** — no network call, no LLM call, ever, per audio frame
   or per transcript. `semantic.py`/`backchannel.py` are pure string inspection; `EnergyVAD` is RMS
   arithmetic over a ~160-sample frame.

## The signal model

`TurnSignal(type, timestamp, confidence=None, source="", text=None, utterance_idx=None)`. Only
`LOCAL_VAD_SPEECH_START/END`, `PROVIDER_SPEECH_START/END`, `STT_PARTIAL`, `STT_FINAL` are fed in
externally via `on_signal()`. `SEMANTIC_COMPLETE/INCOMPLETE`, `BACKCHANNEL`, `CUSTOMER_RESUMED`,
`SILENCE_TIMER`, `MAX_ENDPOINT_WAIT` are computed internally by `TurnManager` itself (calling
`semantic.py`/`backchannel.py` directly) and surfaced only through the debug trace — this avoids a
caller needing to orchestrate "compute a signal, then re-feed it back into the thing that would have
computed it anyway."

## The state machine

`IDLE → USER_SPEECH_STARTING → USER_SPEAKING → USER_PAUSED → POSSIBLE_END → (WAITING_FOR_CONTINUATION
⇄ POSSIBLE_END) → TURN_COMMITTED → IDLE`. Not enforced via a hard transition-validation table the way
`transport/base.py`'s `MediaSessionStatus` is — that table exists because Twilio's wire protocol
genuinely only allows a fixed sequence; turn detection legitimately jumps between non-adjacent states
depending on which evidence arrives (a resume during `POSSIBLE_END` goes straight back to
`USER_SPEAKING`). `TurnManager`'s own decision logic is what enforces correctness (tested directly),
not a transition table.

## Timing model — three genuinely distinct budgets, not three competing ones

An earlier draft of this had `min_endpoint_delay`, `max_endpoint_delay`, and `thinking_pause_extension`
independently triggering commits, which made `thinking_pause_extension` effectively dead weight
whenever it was smaller than `max_endpoint_delay` (it always fired first, so `max_endpoint_delay`
never mattered). The shipped model:

- **`min_endpoint_delay_ms`** — the floor. Nothing commits before this many ms have passed since the
  most recent final, even if the text looks complete.
- **`max_endpoint_delay_ms`** — the ceiling for text that already looks complete. In practice this
  rarely binds (complete text commits at `min_endpoint_delay`), but it's the number that matters if
  semantic evaluation is disabled (`vad` mode).
- **`thinking_pause_extension_ms`** — **added** to `max_endpoint_delay_ms` specifically while the
  text still looks incomplete: `effective_ceiling = max_endpoint_delay_ms + thinking_pause_extension_ms
  if not is_complete else max_endpoint_delay_ms`. This is what gives a genuinely incomplete utterance
  ("I need root canal but...") real extra room before the hard `MAX_ENDPOINT_WAIT` fallback fires —
  distinct from, not competing with, the two above.
- **`fragment_coalesce_ms`** — not a timer threshold at all. A **structural** check applied only when
  a *new* final actually arrives while a turn is still pending: if the gap since the previous final
  exceeds this, the new final starts a fresh turn instead of joining the pending one (spec §26/§71,
  "don't over-coalesce independent turns"). In practice `thinking_pause_extension`/`max_endpoint_delay`
  normally force a commit before this gap could ever be reached; it's a defensive fallback for a
  policy tuned with `fragment_coalesce_ms` smaller than the other two.

## Local VAD: `EnergyVAD`, not a neural model

Checked before writing any code: no Silero/onnxruntime/webrtcvad/LiveKit dependency exists anywhere
in this repository. Adding one properly means model bundling, an ONNX runtime dependency, and real
CPU/latency profiling to satisfy spec §87-88 — a substantial, separate piece of work this pass
couldn't verify. `EnergyVAD` is the same `audioop.rms()` energy-thresholding approach
`transitional_bridge.TurnBuffer` already uses in production (P2/batch mode), restructured as a
frame-by-frame `VADProvider` emitting normalized signals on state transitions only (not one event per
frame). `VADProvider` is a real `Protocol` specifically so a neural VAD can be substituted later with
zero `TurnManager` changes — this is the deliberate seam, not a placeholder that does nothing.

`activation_threshold=300` (PCM16 RMS amplitude) is inherited from `transitional_bridge`'s own
documented-as-untuned starting point — real PSTN-audio calibration is still outstanding (see results
doc).

## Semantic completeness — rule-based, not a model call

`semantic.evaluate(text, language_code)` checks, in order: empty → incomplete; ends with `...`/`…` →
incomplete (defensive — real STT rarely emits literal ellipsis, so this mostly won't fire on live
audio, only kept for safety); last word matches a curated per-language continuation marker (`"but"`,
`"kani"`, `"lekin"`, etc., spec §19) → incomplete; ends with `.`/`?`/`!`/`।` → complete; otherwise →
complete by default. That last default is deliberate: STT text commonly arrives with no punctuation
at all, so *absence* of a period must never itself be read as incompleteness — spec §101's own
priority order values responding promptly to clearly-complete turns, not just avoiding cutoffs.

## Backchannel classification — a timing hint, not a duplicate of extractor.py's own logic

`backchannel.classify(text, expecting_confirmation)` deliberately keeps its own small phrase list
rather than importing `jkr_conversation.policy`'s `CONFIRMATION_YES/NO_TRIGGERS` or
`accidental_interruption_phrases` — this module answers a transport-layer *timing* question ("should
TurnManager be more cautious about calling this utterance complete"), not the conversation engine's
own acknowledgement/confirmation semantics, which `jkr_conversation.extractor.py`'s
`is_acknowledgement_only` and `_resolve_pending_confirmation` already own, unchanged by P4. When
`expecting_confirmation=False` and the text is backchannel-shaped, `TurnManager` treats it as
evidence of incompleteness (extends the wait) rather than committing it as confidently as ordinary
speech — but it still commits eventually (never blocks forever), and once it reaches
`ConversationEngine`, that layer's own acknowledgement handling is what actually decides what the
text means.

**Known simplification**: `TurnManager.expecting_confirmation` is a plain attribute the caller can
set; `streaming_bridge.py` does not currently wire it to the call's real `pending_confirmation` DB
state (that would mean an extra DB read on the hot audio-processing path per turn). It defaults to
`False` — the safe direction (treats backchannels more cautiously, never less). Wiring this to real
state is a documented follow-up, not silently dropped.

## Integration with `streaming_bridge.py`

`_handle_final_transcript()` still does the exact P3 dedup check (same utterance_idx + normalized
text) before anything reaches `TurnManager` — Sarvam-specific retransmit dedup stays a transport
concern, layered *under* turn-coalescing, not replaced by it. A genuinely-new final becomes an
`STT_FINAL` signal; `TurnManager.on_signal()`'s return value decides what happens next:

- **`provider` mode** (default): `on_signal()` returns `COMMIT_TURN` synchronously, every time — same
  dedup, same immediate-commit timing as pre-P4. This is what makes `TURN_DETECTION_MODE=provider`
  byte-behavior-identical to P3 (verified in `test_turn_detection_integration.py`).
- **`vad`/`hybrid` modes**: `on_signal()` may return `MAYBE_END` instead — no engine call yet.
  `_run_one_streaming_generation`'s loop then polls `turn_manager.on_timer_tick()` every
  `TURN_TIMER_POLL_SECONDS` (0.1s — tight enough to honor a 150ms `min_endpoint_delay`; `provider`
  mode keeps the coarser 1.0s poll it never actually needs for commits). A `COMMIT_TURN` from either
  path reaches the exact same `_commit_turn_to_engine()` function — one code path from "a turn is
  ready" to `ConversationEngine`, regardless of which mode decided it was ready.

`PROVIDER_SPEECH_START`/`PROVIDER_SPEECH_END` are fed from Sarvam's `SpeechStarted`/`SpeechEnded`
events — this also **fixes the audit-identified bug** where `SpeechEnded` was previously received and
silently dropped with no handling at all.

One `TurnManager` (and one `EnergyVAD`, if enabled) is created per call in `run_streaming_turn_loop()`
and persists across STT reconnects — a reconnect only replaces the Sarvam WebSocket; a turn already in
progress keeps its accumulated segments rather than losing them.

## Feature flags

| Setting | Default | Values |
|---|---|---|
| `TURN_DETECTION_MODE` | `provider` | `provider` \| `vad` \| `hybrid` |
| `TURN_PROFILE` | `balanced` | `fast` \| `balanced` \| `patient` — informational under `provider` |
| `LOCAL_VAD_ENABLED` | `false` | only meaningful under `vad`/`hybrid` |

`Settings.effective_turn_detection_mode` silently degrades to `provider` unless
`effective_stt_mode == "streaming"` — `vad`/`hybrid` react to Sarvam's partial/final/speech event
stream, which doesn't exist under `STT_MODE=batch`. Same "don't accept a config combination nothing
implements" pattern as `effective_stt_mode` itself.

## What P4 explicitly does not do (per spec, restated)

- No streaming response generation (P5), no streaming TTS (P6).
- No automatic barge-in — `TurnManager` produces `USER_SPEECH_STARTED` reliably during any state,
  which is exactly the signal P8 will need to interrupt agent playback, but nothing calls
  `clear_agent_audio()` automatically from this signal yet.
- No strict stale-audio/replay enforcement (P9) — unchanged.
- No speculative/preemptive LLM generation on `TURN_LIKELY_COMPLETE`-shaped signals — the hook point
  exists (`MAYBE_END`/`WAITING_FOR_CONTINUATION` decisions are observable) but nothing acts on it
  before a real commit.
