# P8 — Interrupted Response History: What Gets Remembered, and How

The specific problem this doc covers: once a response is interrupted, what goes into
`redis_state["recent_turns"]` (the rolling window fed into the *next* turn's LLM context via
`process_turn(recent_turns=...)`) for that turn? Getting this wrong either fabricates something the
customer never heard, or silently drops their own words from context. See
`docs/BARGE_IN_ARCHITECTURE.md` for where this sits in the overall flow, and
`tests/voice/barge_in/test_coordinator_interruption.py` for the executable proof.

## The bug this closes

`transitional_bridge.process_known_transcript_turn()` appends `{"speaker": "agent", "text": reply}` — the
**full** generated reply — to `redis_state["recent_turns"]` immediately after `process_turn()` returns,
before TTS/playback has even started. Pre-P8, this was always correct (nothing could interrupt a response
after that point). Post-P8, if that response is later interrupted mid-playback, `recent_turns` would
already contain the full, possibly-never-fully-heard text with no marker — exactly what the spec's "do not
store the full generated response as if it were spoken" instruction is about.

## Why `PlaybackUnit.text` doesn't solve this

P7 deliberately left `PlaybackUnit.text` unset (`docs/PLAYBACK_ACCOUNTING.md`) — Sarvam's own internal
buffering doesn't preserve a 1:1 boundary between a `SpeakableChunk` (text) and the raw audio messages it
produces, so asserting "this audio chunk == this text" would be a false precision. P8 needed a way to
answer "roughly how much of the generated text was conservatively known to be delivered" without
inventing that false precision.

## The mechanism: chunk_log vs. the last acknowledged unit

`ActiveResponseContext.chunk_log: list[tuple[str, float]]` — one `(text, submitted_at)` entry per chunk
actually forwarded to TTS, appended in `RealtimePipelineCoordinator.submit_speakable_chunk()` at zero extra
cost (the timestamp is already being taken there). This is real, chunk-boundary-accurate data — it just
isn't audio-boundary-accurate, which is the honest limitation this whole design works around rather than
hides.

```python
def _conservative_delivered_text(self, ctx: ActiveResponseContext) -> str:
    acknowledged_sent_ats = [u.sent_at for u in ctx.playback_units if u.state == ACKNOWLEDGED and u.sent_at is not None]
    if not acknowledged_sent_ats:
        return ""
    last_ack_sent_at = max(acknowledged_sent_ats)
    return "".join(text for text, submitted_at in ctx.chunk_log if submitted_at <= last_ack_sent_at)
```

**The rule, stated plainly**: every text chunk submitted to TTS at or before the moment the *last
acknowledged* `PlaybackUnit` was sent counts as conservatively delivered. A chunk submitted after that
point cannot possibly be reflected in audio we have positive evidence played, so it's excluded — never
guessed at a word boundary. If no unit was ever acknowledged, the result is `""`, not a guess.

This is deliberately the same *direction* of conservatism P7's own PLAYED-vs-CLEARED rule already chose
(`docs/PLAYBACK_ACCOUNTING.md`: "better to undercount confirmed-heard audio than to overcount it") — P8
inherits that posture rather than picking a new one.

**Why no separate `partial_unit_unknown` flag**: at this pipeline's tracked granularity, a `PlaybackUnit`
is binary — `ACKNOWLEDGED` or `CLEARED` (once a clear happens, every non-acknowledged `SENT` unit becomes
`CLEARED` immediately, per P7's existing `_on_playback_clear`). There is no genuinely "half-played" unit to
represent; the chunk-timestamp filter above already *is* the "unknown middle ground" handling the spec's
`partial_unit_unknown` concept describes, just implemented via exclusion rather than a flag.

## `InterruptionSnapshot.delivered_text`

`interrupt_active_response()` now returns `delivered_text` alongside the existing `generated_text`/
`tts_committed_text` — three genuinely different strings, never collapsed into one:

```python
generated_text     # everything the LLM produced — customer may not have heard any of it
tts_committed_text  # everything actually submitted to TTS — still doesn't mean it was heard
delivered_text      # conservatively-known-delivered, per the rule above — this is the one safe to reuse
```

## The repair, in `streaming_bridge.py`

`process_known_transcript_turn()` appends the customer+agent pair **together, synchronously, with no
`await` in between** (confirmed by reading the function — this is what makes the repair deterministic
rather than a guess). `_dispatch_commit()` captures `len(redis_state["recent_turns"])` immediately before
starting the response's background task. `_repair_interrupted_turn_history()` then does exactly one of two
things, based purely on that length delta — no timing assumptions needed:

- **+2 (both entries present)**: `process_turn()` had already returned before the interruption landed.
  Repair the agent entry: if `delivered_text` is non-empty, set `text = delivered_text` and
  `interrupted = True`; if empty (nothing was ever acknowledged), **remove the entry entirely** rather than
  leave a fabricated-looking empty assistant turn in context.
- **+0 (neither entry present)**: generation itself was cut off before producing a reply — there's no reply
  text to repair, but the customer's own triggering utterance must not simply vanish from context. Append
  `{"speaker": "customer", "text": committed_text}` on its own (no agent counterpart, since none exists).

Example of the repaired shape, matching the spec's own illustration:

```json
{"speaker": "customer", "text": "One minute, tomorrow appointment undha?"}
{"speaker": "agent", "text": "Root canal cost case బట్టి vary అవుతుంది అండి.", "interrupted": true}
```

## What this is not

Not a rewrite of the DB-persisted `CallTurn`/`CallEvent` audit trail — `_persist_turn()` already wrote the
customer's utterance to Postgres unconditionally, near the top of `process_known_transcript_turn()`, before
any of this runs; that historical record is left untouched. This doc is specifically about
`redis_state["recent_turns"]`, the rolling window that feeds the *next* LLM call's context — the one place
"never claim the full response was delivered" actually matters for behavior, not just for record-keeping.
