# P9 — The Response Identity Model

`services/api/app/modules/live_call/transport/identity.py`. See `docs/REPLAY_PROTECTION_ARCHITECTURE.md`
for how this is used across the pipeline, and `docs/P9_REPLAY_PROTECTION_AUDIT.md` for why it was needed.

## `ResponseIdentity`

```python
@dataclass(frozen=True)
class ResponseIdentity:
    call_id: uuid.UUID
    turn_id: str
    response_id: str
    generation_id: str
    sequence_id: str
    epoch: int
```

One canonical, immutable structure — not five loose strings threaded independently through the stack
(this phase's own explicit instruction). Frozen by construction: a new response always means a new
`ResponseIdentity`, never a mutated one (`test_response_identity_is_frozen` proves the dataclass itself
rejects mutation, not just a convention nobody violates).

`ActiveResponseContext.identity` (in `coordinator.py`) is a **property**, not a stored field — it's
constructed on demand from the context's own `call_id`/`turn_id`/`response_id`/`generation_id`/
`sequence_id`/`response_epoch`. This means it can never drift out of sync with the context it describes;
there is exactly one place these five-plus-one values live.

## What each field means

- **`call_id`** — the `RealtimeMediaSession`'s own `call_session_id`. Never optional, never compared alone
  (spec §59: two calls could coincidentally mint the same local `response_id` counter values in principle,
  though in practice `uuid4()`-derived IDs make that astronomically unlikely — `call_id` is still checked
  first, unconditionally, as the cheap, structural guarantee rather than relying on ID entropy).
- **`turn_id`** — which customer turn this response answers. Minted by `TurnManager` as
  `turn_{call_session_id}_{n}` (a per-call monotonic counter — see `manager.py`), except for the one
  synthetic value `"greeting"` used for the call-opening response, which has no corresponding customer
  turn.
- **`response_id`** — the logical customer-facing response. Minted once, in `begin_response()`, as
  `resp_{uuid4().hex[:12]}`. This implementation found no case where a single logical response needed to
  split into multiple sub-sequences (see `sequence_id` below), so this is the identifier most other
  boundaries key off of directly.
- **`generation_id`** — minted alongside `response_id`, as `gen_{uuid4().hex[:12]}`. Kept distinct from
  `response_id` per the spec's own recommended semantics (`response_id` = logical intent, `generation_id`
  = a specific generation attempt) even though, like `sequence_id`, this implementation has never needed
  a response to regenerate under the same `response_id` — the field exists so a future phase that does
  need that doesn't have to add it.
- **`sequence_id`** — set equal to `response_id` in this implementation (same finding P7 already made and
  documented — see `docs/REALTIME_PIPELINE_COORDINATOR.md`'s own "what sequence_id actually is" section).
  Kept as a separate field on both `ResponseIdentity` and `PlaybackUnit` for the same forward-compatibility
  reason.
- **`epoch`** (new in P9) — the call-scoped `response_epoch` counter, incremented once per
  `begin_response()`, captured at mint time. A cheap integer comparison that answers "is this identity
  from a strictly different response generation than the one currently active" — see "Two epochs" below
  for why this is a genuinely useful *addition* to the string comparisons above, not a replacement for them.

## Two epochs, not one

Spec §11/§12 asks for a `response_epoch` and separately a `playback_epoch`. Both exist, deliberately kept
distinct because they answer different questions:

- **`response_epoch`** (`RealtimePipelineCoordinator._response_epoch`) — increments once per
  `begin_response()`. Answers: *which response generation is this artifact from?*
- **`playback_epoch`** — this is the formal P9 name for what P7 already built and tested as `_clear_epoch`
  (exposed via a new `RealtimePipelineCoordinator.playback_epoch` property rather than renamed, to avoid
  touching P7's own already-tested `PlaybackUnit.clear_epoch_at_creation` bookkeeping for a purely cosmetic
  change). Increments once per Twilio clear (`_on_playback_clear()`). Answers: *has a clear happened since
  this audio was minted?*

Why both matter independently: in this implementation, a clear only ever happens as part of
`interrupt_active_response()`, which *also* transitions the response to `INTERRUPTED` — so in practice,
by the time a clear has happened, `is_identity_active()` would already reject the old response's identity
on its own. The `playback_epoch` check on `OutboundAudioChunk` is kept as an **independent, second check**
anyway (`can_send_media()` checks both) — defense in depth against a hypothetical future code path where a
clear could happen without also invalidating the response identity, not something the current architecture
can actually produce today. Documented explicitly here rather than silently relied upon.

## Immutability and "never reuse an ID"

Spec §5/§7/§55 — `response_id`/`generation_id`/`sequence_id` are never mutated on an existing artifact, and
never reused: `begin_response()` always mints fresh `uuid4()`-derived values, `response_epoch` always
increments (never resets, never decrements, even across the same call's many turns). A new response
requires a new identity — enforced by construction (there is no method anywhere in `coordinator.py` that
assigns a new `response_id` to an existing `ActiveResponseContext`) and proven by
`test_response_epoch_increments_across_responses`.

## Connection-generation identity is NOT response identity

Spec §13/§25/§61 — kept deliberately separate, and never conflated:

- **Sarvam's own `request_id`** is scoped to the whole streaming-TTS *connection*, not to a response (a
  finding from P6's live-verified contract testing — see `docs/SARVAM_STREAMING_TTS_CONTRACT.md`). This
  codebase's `ResponseIdentity` is what provides response-level correlation around the provider's
  send/receive lifecycle; Sarvam's own `request_id` is never used for ownership decisions anywhere.
- **`TTSStreamingSession._connection_generation`** (P7) — increments on a successful reconnect. Audio
  arriving from an old, pre-reconnect provider instance is already structurally impossible to misattribute:
  `_run_consumer_with_reconnect()` only reconnects when idle (never mid-response — spec §144, verified by
  `test_tts_reconnect.py`), and a fresh provider instance's `events()` generator is a completely separate
  async iterator from the old one's, so there is no shared state an old event could leak through even if
  the old connection somehow still had bytes in flight.
- **Twilio stream generation** — this implementation does not currently model an explicit
  `twilio_stream_generation` counter (spec §62). A `RealtimeMediaSession` is 1:1 with one Media Streams
  WebSocket connection for its entire lifetime (see `session.py`) — there is no reconnect-to-a-new-stream
  concept in the current architecture for the Twilio leg specifically (unlike the STT and TTS provider
  connections, which do reconnect independently). If a future phase adds Twilio-side stream reconnection,
  *that* phase should add this counter; P9 does not fabricate one for a mechanism that doesn't exist yet
  (same "don't build for a hypothetical" discipline the audit already applied to tool/RAG staleness).

## What this is not

Not a replacement for `is_current()` (the pre-P9, `response_id`-only ownership check) — `is_current()` is
kept, unchanged, everywhere it was already used; `is_identity_active()` is the strictly stronger, additive
check new P9 boundaries use when they have a full `ResponseIdentity` available. Not a cryptographic or
tamper-proof identity — every field is server-generated and never accepted from an external WebSocket
message (spec §148); the model's job is structural correctness against races and staleness, not against an
adversarial client.
