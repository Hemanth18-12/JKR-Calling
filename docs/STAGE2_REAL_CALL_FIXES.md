# Stage 2 — Real-Call Correctness/Quality Fixes

Three audit-identified bugs fixed on the real direct-call path
(`POST /api/v1/live-call`, `TWILIO_VOICE_TRANSPORT=record` — the active
default transport) before any streaming/realtime runtime flag is touched.
Baseline going in: 600/600 tests passing repo-wide, HEAD `8d65d26` plus the
P10 report-tool RLS fix. No runtime flags, TurnManager, LLM model, RAG, or
P2–P9 streaming architecture were touched.

---

## Fix 1 — `book_appointment` / `contact_id` / false success

**Audit finding:** a real call could reach `book_appointment` with no
`contact_id`, the booking could silently fail, and the customer could still
hear a canned "noted/confirmed" line.

**Root cause (traced, not assumed):**

1. `LiveTestCallCreate` (the `/api/v1/live-call` request schema) only ever
   carried `agent_id` + `to_number` — no contact identity at all.
   `CallSession.contact_id` was therefore `None` for every real call,
   unconditionally, from creation (`live_call/service.py`).
2. `execute_tool(...)` at both webhook call sites
   (`handle_recording_webhook`, `handle_closing_grace_webhook`) never even
   passed a `contact_id=` kwarg — a second, independent instance of the same
   gap, on top of (1).
3. Deeper structural issue: `process_turn()` builds the spoken reply
   (`engine.py`, canned `objectives.py` closing text for
   `COMPLETE_OBJECTIVE`) **before** `tool_calls_requested` is even
   constructed, let alone executed. The caller executed the tool
   *afterward* and did nothing on failure — `reply = result.reply_text` was
   spoken unconditionally, regardless of tool outcome.
4. Incidental finding while fixing (1)–(3): `_run_book_appointment` /
   `_run_send_message` trusted a caller-supplied `contact_id` without
   verifying it belonged to the executing workspace — a cross-tenant
   `contact_id` would have been silently accepted.

**Contact ID source:** `Contact` (unique on `workspace_id, phone_e164`) —
the codebase's existing canonical identity for a phone number, already used
by the campaign path. Not derived from name/workspace search — resolved
once via find-or-create against the number actually being dialed.

**Fix:**
- `_get_or_create_contact()` (`live_call/service.py`) resolves/creates the
  `Contact` for `to_e164` at call creation; `CallSession.contact_id` is now
  populated for every real call.
- `_execute_tool_calls()` (new shared helper, replaces the duplicated inline
  loop in both webhook handlers) passes `contact_id=call_session.contact_id`
  into every tool call, and returns `True` if any
  `REAL_SIDE_EFFECT_TOOLS` call (`book_appointment` etc. — the existing
  set with genuine business consequences) failed.
- Both handlers now do: `reply = _tool_failure_reply(language_code) if
  tool_failed else result.reply_text` — a truthful, non-overpromising
  fallback (te/hi/en) instead of the canned success line. Does not claim a
  callback/retry guarantee that isn't backed by an actual process. Does not
  change `call_should_end`/closing behavior — only what's spoken.
- `_get_workspace_contact()` (`tools_engine.py`) now validates `contact_id`
  belongs to `workspace_id` before `book_appointment`/`send_whatsapp`/
  `send_sms` proceed — the same pattern `_get_workspace_appointment`
  already used for `appointment_id`. A cross-tenant `contact_id` now fails
  identically to a missing one (no existence leak).

**Tool success contract (unchanged, just now actually consulted):**
`ToolExecution.status` — `"succeeded"` / `"failed"`, with `.output` /
`.error` set accordingly. Idempotency (`ToolExecution.idempotency_key`,
unique per `call-{call_session_id}-{tool}`) already existed and needed no
new architecture — verified with a repeated-call test instead.

**Tests added:**
- `packages/db/tests/test_tools_engine.py` — valid booking creates a real
  `Appointment` row (Case A); missing `contact_id` fails with no
  `Appointment` row (Case B); cross-workspace `contact_id` is rejected, no
  leak (Case D); unconfigured/disabled tool raises cleanly (Case C
  variant); repeated `execute_tool` call is idempotent, one `Appointment`
  only (Case E).
- `services/api/tests/test_live_call_appointment_booking.py` (new) —
  `_get_or_create_contact` find-or-create + per-workspace isolation;
  `_execute_tool_calls` books for a real contact, reports failure and books
  nothing without one, treats an unconfigured tool as not-a-failure
  (matches prior behavior), and is idempotent across a simulated webhook
  retry.
- `services/api/tests/test_live_call_service.py` — `_tool_failure_reply` is
  language-specific, never contains a success claim, and falls back to
  English for an unrecognized language code.

---

## Fix 2 — `SpokenResponseFormatter` acknowledgement repetition

**Audit finding:** `engine.py` (~line 375) constructs a fresh
`SpokenResponseFormatter` every turn, resetting `_last_acknowledgement` to
`None` each time — `pick_acknowledgement()` then deterministically returns
the same (first) pool entry on every `ASK_FIELD`/`CLARIFY`/`CONFIRM_FIELD`
turn of a call ("సరే అండి" / "Sure." verbatim, repeatedly).

**Old lifetime:** per-turn (reconstructed inside `process_turn()`, which is
itself a plain function called fresh every turn — there is no
`ConversationEngine` class/instance anywhere in the repo).

**New lifetime:** per-call, via the state container that *already* exists
and is already call-scoped: `CallSession.state` (a JSON dict, reloaded
fresh from Postgres every turn and written back after — the same pattern
`known_fields`/`field_confidence`/etc. already use, threaded through both
call sites identically). `SpokenResponseFormatter` is now seeded with
`_last_acknowledgement=new_state.get("last_acknowledgement")` at
construction, and `new_state["last_acknowledgement"]` is written back after
formatting whenever an acknowledgement was actually used. No new
architecture, no class, no registry — three lines in `engine.py`.

**Cross-call isolation:** automatic — `new_state` is `state` for exactly
one `call_session_id`'s own DB row; no module-level or shared state exists
(confirmed: no module-level `SpokenResponseFormatter` instance anywhere in
the repo before or after this fix).

**Example before:** Turn 1/2/3 ASK_FIELD → "Sure. ..." / "Sure. ..." /
"Sure. ..." (identical every time, provably — `_last_acknowledgement`
starts `None` every construction, so `pick_acknowledgement()` always
returns `pool[0]`).

**Example after:** Turn 1 ASK_FIELD → "Sure. ..."; Turn 2 CLARIFY → "No
problem. ..." (or another pool entry — never `pool[0]` again immediately);
Turn 3 ASK_FIELD → differs from Turn 2 again. Contract is "never repeat the
*immediately previous* one," not full-history uniqueness — matched exactly
by what the tests assert.

**Not touched:** whether an acknowledgement is used at all is unchanged —
`prepend_ack = decision.action in ("ASK_FIELD", "CLARIFY",
"CONFIRM_FIELD")` already existed and already leaves every other action
(`COMPLETE_OBJECTIVE`, `HUMAN_HANDOFF`, etc.) unprefixed; no new
"skip the acknowledgement" heuristic was added — that would have been a
conversational-style redesign, out of scope for this stage.

**Tests added** (`packages/conversation/tests/test_engine.py`):
- Three real turns of one call (`ASK_FIELD` → `CLARIFY` → `ASK_FIELD`,
  driven via mock-mode's documented `awaiting_field`-dump extraction, not
  hand-waved) — consecutive acknowledgements never repeat.
- `CONFIRM_FIELD` → `ASK_FIELD` (chaining the two already-proven
  domain-correction scenarios with state threaded through) — same proof
  for the third gated action type.
- Two independent calls — call B's first acknowledgement is identical to
  what call A's *first* acknowledgement was, proving isolation (if state
  had leaked, call B would have inherited call A's rotation and differed).

---

## Fix 3 — Greeting VoicePersona wiring

**Audit finding (as originally described):** the greeting reportedly used
a hardcoded/generic Sarvam voice ("priya") instead of the agent's
configured `VoicePersona`, while normal turns used the correct one.

**What the trace actually found:** this specific greeting-vs-normal-turn
divergence does **not** exist in the current code. `start_live_test_call`
resolves `tts_speaker`/`tts_pace` once via `_resolve_tts_speaker()` /
`_resolve_tts_pace()`, caches both in Redis call state, and the greeting
and every later turn (batch `<Record>` path and the not-yet-activated
`media_stream` path alike) read that identical cached value through the
same `_speak()`/`speak_turn_reply()` helpers. Code comments already
in-place (`service.py:252-255`, pre-dating this stage) document that this
exact bug was fixed in a prior pass (P6/P7) — "previously loaded from the
DB and then silently discarded ... this used to be silently ignored
regardless of configuration." The real reason a live call still hears
"priya" today is that every seeded/demo `VoicePersona` row defaults to
`provider="mock"`, which `_resolve_tts_speaker()` correctly and
intentionally treats as "not configured for Sarvam" — falling back to
Sarvam's own default for *every* turn uniformly, not just the greeting.
That is working as designed, not a wiring bug.

**What genuinely was missing (found during this trace, not previously
flagged):** `_resolve_tts_pace()`'s result was computed and cached in
Redis state (`"tts_pace"`) but **never actually forwarded to `SarvamTTS`**
— `_speak()` only ever passed `speaker`, never `pace`, and `SarvamTTS`
itself had no `pace` parameter at all. A configured
`VoicePersona.speaking_speed` therefore had zero effect on the batch
`<Record>` transport regardless of provider configuration. Sarvam's TTS
API does accept a `pace` field (already used by the streaming client,
`sarvam_streaming_tts.py:126`, and documented in
`docs/SARVAM_STREAMING_TTS_CONTRACT.md`) — the batch REST client just never
sent it.

**Fix:** `SarvamTTS.__init__` now accepts `pace: float = 1.0` and includes
it in the outgoing request; `_speak()` gained a `pace` parameter (default
`1.0`, Sarvam's own natural pace — always forwarded, unlike `speaker`,
since there's no "omit it" case to preserve); all 7 `_speak()` call sites
in `live_call/service.py` now pass `pace=state.get("tts_pace", 1.0)` (or
the local `tts_pace` variable at call-creation time).

**Fallback:** unchanged and still safe — `_resolve_tts_speaker`/
`_resolve_tts_pace` already gate on `provider == SARVAM_TTS`; no persona
or a non-Sarvam persona still falls back to Sarvam's own default voice/pace
exactly as before.

**Language:** derived from `Agent.primary_language` via
`_sarvam_language_code()`, independently per agent — verified against a
real seeded DB, not just asserted from the existing code path.

**Out of scope, left as-is (found, not fixed):** the `media_stream`
transport's own batch-TTS-fallback path (`transitional_bridge.py`'s
`synthesize_for_stream()`/`speak_turn_reply()`) has the identical
unforwarded-`pace` gap in its `SarvamTTS(...)` call — not touched here,
since `media_stream` is P2–P9 realtime architecture explicitly out of
scope for this stage and is not the active default transport
(`TWILIO_VOICE_TRANSPORT` defaults to `"record"`). Worth the same one-line
fix when that transport is staged for activation (Stage 6).

**Tests added:**
- `services/api/tests/test_live_call_service.py` — `_resolve_tts_speaker`/
  `_resolve_tts_pace` produce genuinely different values for two different
  personas (not just "a" correct value in isolation); `_speak()` forwards
  a given `pace` to `SarvamTTS` and defaults to `1.0` when omitted;
  `SarvamTTS` itself stores the `pace` it's constructed with.
- `services/api/tests/test_live_call_voice_persona_greeting.py` (new,
  DB-backed) — two real seeded agents (A: Sarvam/`shubh`/pace 0.8/te-IN, B:
  Sarvam/`anushka`/pace 1.6/hi-IN) resolve to distinct speaker+pace through
  the exact query sequence `start_live_test_call` runs; a third agent with
  no `VoicePersona` row falls back to the provider default; each agent's
  language code resolves independently.

---

## Verification

Before any edit: 600/600 passing repo-wide (confirmed by re-running, not
assumed from the prior session).

| Suite | Before Stage 2 | After Stage 2 |
|---|---|---|
| root (`uv run pytest`) | 221 | 229 |
| services/api | 345 | 362 |
| packages/db (subset of root) | — | +5 tests |
| packages/conversation (subset of root) | — | +3 tests |
| campaign-worker | 13 | 13 |
| intelligence-worker | 11 | 11 |
| voice-worker | 10 | 10 |
| **Total** | **600** | **625** |

All 625 pass. `ruff`/`mypy` remain not installed anywhere in this
environment (not in `uv.lock`, not on `PATH`, no dev dependency group) —
unchanged from the Stage 1 finding; no new tooling was installed, per
instruction. `python -c "import ..."` sanity-compiled every changed module.

The P10 report tool remains RLS-safe and its own test suite (8 tests) is
included in the `services/api` count above, unaffected by this stage's
changes:

```bash
uv run --package jkr-db python tests/tools/real_call_quality_report.py \
    --workspace-id <workspace-id> --call-id <call-session-id>
```

---

## Files changed

- `packages/conversation/jkr_conversation/engine.py` — Fix 2
- `packages/conversation/tests/test_engine.py` — Fix 2 tests
- `packages/db/jkr_db/tools_engine.py` — Fix 1 (cross-tenant contact
  validation)
- `packages/db/tests/test_tools_engine.py` — Fix 1 tests
- `services/api/app/live_providers/sarvam_tts.py` — Fix 3 (`pace` param)
- `services/api/app/modules/live_call/service.py` — Fix 1 (contact
  resolution, truthful tool-failure reply) + Fix 3 (`pace` forwarding)
- `services/api/tests/test_live_call_service.py` — Fix 1 + Fix 3 unit tests
- `services/api/tests/test_live_call_appointment_booking.py` (new) — Fix 1
  DB-backed tests
- `services/api/tests/test_live_call_voice_persona_greeting.py` (new) —
  Fix 3 DB-backed tests

Not committed — per instruction, stopping here for review.

---

## Remaining known quality gaps (explicitly still open)

Confirmed still true by this stage's own code inspection — not touched,
not claimed fixed:

- 4-second legacy `<Record>` silence timeout (`RECORD_SILENCE_TIMEOUT_SECONDS`)
- Batch STT runtime (`STT_MODE` untouched)
- Legacy `ConversationEngine` runtime (`CONVERSATION_ENGINE_MODE` untouched
  — `engine_mode` defaults to `"legacy"` at every real call site)
- Complete (non-streaming) LLM runtime (`LLM_RESPONSE_MODE` untouched)
- Batch TTS runtime (`TTS_MODE` untouched; the `media_stream` transport's
  own streaming-TTS path exists but is not the active default)
- Barge-in disabled (`BARGE_IN_ENABLED` untouched)
- Vertical-specific structured-field schema gap (education/dental) — not
  addressed
- Domain-normalization-into-RAG-query correction (e.g. mis-transcribed
  "root canal") — not addressed
- `media_stream` transport's `pace`-forwarding gap in its own batch-TTS
  fallback (`transitional_bridge.py`) — newly identified during this
  stage's Fix 3 trace, left unfixed as P2–P9 architecture out of scope
