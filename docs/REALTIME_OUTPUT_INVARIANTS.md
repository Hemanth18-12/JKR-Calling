# P9 — Realtime Output Invariants

The eight invariants P9 exists to make architecturally true, each with where it's enforced and how it's
tested. See `docs/REPLAY_PROTECTION_ARCHITECTURE.md` for the full design, `docs/RESPONSE_IDENTITY_MODEL.md`
for the identity model these invariants are stated in terms of.

## Invariant 1 — No audio without a valid active `ResponseIdentity`

> No customer-facing audio is sent without a valid active `ResponseIdentity`.

Enforced by: `RealtimePipelineCoordinator.can_send_media()` (the output gate), called unconditionally from
`_send_loop` before every `websocket.send_json()`. Legacy (no-coordinator) chunks are the one documented
exception (§161).
Tested by: `test_can_send_media_allows_current_response_first_send`,
`test_can_send_media_blocks_unknown_response`, `tests/voice/replay/test_replay_chaos.py`.

## Invariant 2 — A terminal response can never produce new audio

Enforced by: `is_identity_active()`'s `not self._active.is_terminal()` check (the output gate) and
`VALID_RESPONSE_STATE_TRANSITIONS` (no code path can move a context back out of a terminal state).
Tested by: `test_is_identity_active_false_once_response_is_terminal`,
`test_transition_out_of_terminal_state_is_rejected`.

## Invariant 3 — A cancelled/interrupted/superseded sequence cannot send after invalidation

Enforced by: atomic invalidation in `_stop_response()` (state transition + `cancellation_token.cancel()`,
both synchronous, before any `await`) plus the output gate's live re-check at send time.
Tested by: `test_can_send_media_blocks_stale_response_after_cancel`,
`test_late_audio_chunk_after_interrupt_never_reaches_outbound_queue` (P8, still passing under P9),
`test_ten_rapid_interruptions_no_leaked_provider_cancels_no_stale_audio`.

## Invariant 4 — A media chunk can be sent at most once

Enforced by: `can_send_media()`'s `chunk.chunk_index in ctx.sent_media_chunk_indices` check, plus two
upstream independent duplicate checks (`check_chunk_index()` at the `SpeakableChunk` and `TTSAudioChunk`
boundaries).
Tested by: `test_can_send_media_blocks_duplicate_chunk_index`,
`test_duplicate_audio_chunk_index_is_dropped_not_forwarded_twice`,
`test_duplicate_text_chunk_index_is_dropped`.

## Invariant 5 — Cleared playback can never later be classified as played

Enforced by: `VALID_PLAYBACK_UNIT_TRANSITIONS` (no edge from `CLEARED` to `ACKNOWLEDGED`) plus
`_on_mark_acknowledged()`'s own guard (P7, generalized in P9 to route through `_transition_unit()`).
Tested by: `test_cleared_can_never_become_acknowledged`,
`test_interrupt_after_partial_playback_marks_pending_units_cleared_not_acknowledged` (P8, still passing).

## Invariant 6 — Old provider connection events cannot mutate the current response

Enforced by: `TTSStreamingSession`'s `pending.event.is_set()` guard (P6/P7, unchanged) plus P9's
duplicate/conflict/gap detection on `TTSAudioChunk.audio_chunk_index`; TTS reconnect generation isolation
(P7 — a fresh provider instance per reconnect, never mid-response).
Tested by: `test_stale_tts_audio_dropped` (existing P8 coverage),
`test_duplicate_audio_chunk_index_is_dropped_not_forwarded_twice`,
`test_conflicting_audio_chunk_index_fails_the_response`, `test_tts_reconnect.py` (P7, unchanged).

## Invariant 7 — Old user-turn/tool/RAG results cannot generate speech after a newer turn is authoritative

Enforced by: `_dispatch_commit()`'s `latest_committed_turn_sequence` guard (new, defense-in-depth — see
`docs/REPLAY_PROTECTION_ARCHITECTURE.md`'s honest scoping note); tool/RAG staleness found structurally not
applicable to this codebase's current (fully-synchronous, no speculative-prefetch) call patterns.
Tested by: reasoning documented in `docs/P9_REPLAY_PROTECTION_AUDIT.md`, not a dedicated failing-without-
the-fix test (the scenario cannot currently be constructed given the surrounding architecture).

## Invariant 8 — If ownership cannot be proven, fail closed

Enforced by: every boundary's default branch is "reject," never "assume it's probably fine" — the output
gate's `unknown_response` branch, `submit_speakable_chunk`'s `is_current()` check, `_run_sender`'s
dequeue-time check. No boundary anywhere in this codebase treats "I don't recognize this identity" as
equivalent to "there's only one active response, so it's probably that one" (spec §141's explicit
prohibition).
Tested by: `test_can_send_media_blocks_unknown_response`, and by construction (no code path exists that
implements a "best guess" fallback to audit against).

## Metrics vocabulary

`services/api/app/modules/live_call/transport/replay_metrics.py` — one process-wide
`ReplayProtectionMetrics` singleton, same pattern as `TurnMetrics`/`BargeInMetrics`:

```
stale_llm_delta_dropped_total           stale_tts_audio_dropped_total
stale_speakable_chunk_dropped_total     duplicate_tts_audio_dropped_total
duplicate_speakable_chunk_dropped_total audio_identity_conflict_total
chunk_identity_conflict_total           stale_twilio_media_dropped_total
stale_tts_text_dropped_total            duplicate_twilio_media_dropped_total
stale_mark_ignored_total                duplicate_mark_ignored_total
stale_turn_result_dropped_total         queue_stale_items_purged_total
unknown_response_artifact_dropped_total invalid_state_transition_total
replay_attempt_blocked_total            stale_audio_sent_total
```

`record_blocked(specific_field)` increments the named counter **and** the umbrella
`replay_attempt_blocked_total` together, in one call — spec §90's "fires alongside every specific drop,"
guaranteed to never drift apart from a missed second increment.

**`stale_audio_sent_total` has no code path that increments it, by construction.** The output gate runs
unconditionally before every real Twilio send and blocks anything that would need this counter — its value
staying at 0 across every test in this codebase (including the randomized chaos tests) is *itself* the
proof the gate works, not a separately "wired" detector waiting to fire. If a future change ever needed to
increment it, that would mean the gate had a real hole — a bug to fix immediately, not a code path to
maintain.

**`stale_llm_delta_dropped_total` also has no current code path.** `StreamingResponseAssembler`'s own
`cancellation_token.is_cancelled` check (P5, now actually wired — see the architecture doc) stops
consumption entirely rather than producing a delta that would then need to be "dropped" downstream; there
is no separate boundary in this codebase that receives an already-produced-but-stale delta. Kept in the
metrics vocabulary for the spec's own completeness (§95) and because a future change to the assembler's
own internal structure could introduce exactly this boundary.

## Event vocabulary (`log_event()`)

Logical lifecycle events only — never per-frame/per-signal spam (spec §90's "no per-VAD-frame DB writes"
extended to every boundary here):

```
stale_audio_blocked            invalid_response_state_transition
stale_tts_text_dropped         invalid_playback_unit_state_transition
stale_tts_audio_dropped        stale_turn_result_dropped
duplicate_tts_audio_dropped    stale_tts_text_purged
audio_identity_conflict        stale_twilio_media_purged
chunk_identity_conflict        pipeline_chunk_dropped_stale
duplicate_speakable_chunk_dropped
```

Structured, no raw audio, no PII — matching spec §147's example shape:

```json
{
  "event": "stale_audio_blocked", "boundary": "twilio_output_gate", "call_session_id": "...",
  "response_id": "...", "audio_chunk_index": 3, "reason": "stale_response"
}
```

## Debug trace

No dedicated new debug panel was built this pass (see `docs/P9_REPLAY_PROTECTION_RESULTS.md`'s honest
gaps) — the event log above, read in call-session order, already reconstructs the exact trace shape spec
§98-99 describes (response created → chunks generated → audio sent → interrupt → sequence invalidated →
queue purged → late packet dropped), the same posture P8 took for its own barge-in trace ("the event log
IS the trace").
