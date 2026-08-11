# Domain Understanding, STT Quality & Safe Call-Closing

## 1. The three bugs this fixes

Diagnosed directly against real call `1482f303-3dc9-4fa2-b32c-83f43f24d7c0`:

1. **Abrupt hangup.** Every objective completion except `book_appointment` fell through to free
   LLM generation for its closing line, with no finality guarantee (e.g. "if tomorrow morning
   works, I can reinstate it"). The call hung up immediately after — the customer's reply was
   captured by nothing. This read as "STT stopped working"; STT was fine, the call had already
   ended without warning.
2. **Domain-term mis-transcription accepted blindly.** Customer said "root canal treatment";
   Sarvam (with `language_code="unknown"`) transcribed it as "ఫ్రూట్ కెనాల్స్" ("fruit canals").
   The extractor stored this at `field_confidence: 1.0` and the agent parroted it back.
   Confidence measured only "did the customer clearly say something," never "is this value
   plausible."
3. **Language auto-detect instability.** One customer turn mid-call was transcribed in Bengali
   script during an otherwise Telugu-English conversation — direct evidence `"unknown"`
   auto-detect is unreliable, not just imprecise.

## 2. Closing system — fixes bug 1

`packages/conversation/jkr_conversation/closing.py` is the single source of truth for every
call-ending line: `DO_NOT_CALL`, `WRONG_NUMBER`, `HUMAN_HANDOFF`, `OBJECTIVE_COMPLETED`,
`CALL_TIME_LIMIT`. Every template, in every language, contains an explicit finality phrase
("thank you, have a good day" / "ధన్యవాదాలు, శుభదినం" / "धन्यवाद, आपका दिन शुभ हो"), checkable at
runtime via `has_finality_marker()`. Light slot-filling only (`build_context()` — currently one
slot, a captured callback time) — never open generation.

`jkr_conversation/prompt_builder.py`'s `generate()` routes **every** `COMPLETE_OBJECTIVE`
decision through `closing.build_closing_text(...)`, tool-backed objective or not — this is the
direct fix for bug 1. `SAFETY_STOP`/`HUMAN_HANDOFF` were already canned; free LLM generation is
now reserved strictly for non-terminal actions (`ASK_FIELD`, `CLARIFY`, `CONFIRM_FIELD`,
`DEFER_QUESTION`).

### Grace period (real calls only)

Twilio's `<Play>` always finishes before the next verb (`<Record>`/`<Hangup>`) executes —
sequential TwiML execution, confirmed not assumed. `services/api/app/modules/live_call/service.py`
exploits this directly: a closing decision no longer emits `<Play>...</Play><Hangup/>`, it emits
`<Play>...</Play><Record maxLength="6" timeout="3" .../>` targeting a new
`POST /webhooks/twilio/closing-grace/{token}` webhook (`handle_closing_grace_webhook`).

- **Silence** in that window → the closing already played in full; the call is finalized for
  real (`_finalize_call`).
- **Real speech**, for a `do_not_call`/`wrong_number` closing → acknowledged, but never resumes
  the conversation. Same "the LLM cannot override do-not-call" guarantee, extended to this
  mechanism — see `handle_closing_grace_webhook`'s explicit short-circuit.
- **Real speech**, for any other closing reason → `_reopen_conversation_state()` flips
  `objective_status` back to `in_progress` and the utterance is fed back through `process_turn`
  like any other turn. If that itself ends in another closing, the grace flow recurses.

No new persisted state machine — which webhook is currently "active" is state enough for this
transport; real-time barge-in during playback remains out of scope, as it always has been for
this non-streaming webhook loop. `handle_status_webhook`'s `"completed"` branch gained a 3-line
idempotent fallback finalize (guarded by `_finalize_call`'s own status check) for the one edge
case the extra hop introduces: the customer hanging up their phone entirely during the grace
window, rather than staying silent or speaking.

## 3. STT configuration — fixes bug 3, half of bug 2

`services/api/app/live_providers/sarvam_stt.py`: `language_code` is now a **required** parameter
(no more silent `"unknown"` default a call site could regress back to), pinned to the same
`_sarvam_language_code(agent.primary_language)` value already computed for TTS. `mode="codemix"`
is Sarvam's mode for code-switched speech (Telugu-English, Hindi-English) — the actual use case
here. Model bumped to `saaras:v4`.

`transcribe()` returns `SttTranscript(text, detected_language_code, language_probability,
raw_response)` instead of a bare string. **Sarvam does not expose a transcription confidence
score** — `language_probability` (confidence in the *detected language*, not the transcription)
is stored separately and never conflated with transcription confidence. This metadata is
persisted into `CallEvent.payload` (`_persist_turn(..., metadata=...)`), not a new `CallTurn`
column — `stt_detected_language_code` vs. `stt_requested_language_code` on the same event row is
what makes bug 3 directly debuggable after the fact.

## 4. Domain vocabulary + normalization — fixes the other half of bug 2

**Not hardcoded to dental.** `domain_vocabularies` (workspace-scoped: `name`, `description`) and
`domain_terms` (`canonical`, `aliases: ARRAY[str]`, `category`, `criticality: "standard" |
"critical"`, `languages`) are generic tables — `packages/db/jkr_db/models/agents.py`. `Agent`
gets a nullable `domain_vocabulary_id`; no vocabulary assigned is a normal, valid state. Seed
data (`packages/db/jkr_db/seed.py`) proves this generalizes across three unrelated domains:

| Workspace | Vocabulary | Attached to agent? |
|---|---|---|
| Aaha Dental Care | Dental Procedures | Yes — includes the literal `"ఫ్రూట్ కెనాల్స్"` alias that fixes the demonstrated bug |
| Adarsh Educational Institutions | Admissions & Programs | Yes |
| JKR Creatives | Real Estate Listings | **No** — deliberately unattached, proving the schema doesn't force an artificial fit |

### Fuzzy matching's honest limitation

`jkr_conversation/domain_normalizer.py` (stdlib `difflib.SequenceMatcher`, substring +
sliding-window matching against every term's canonical + aliases) is same-script variance
detection: spelling drift, abbreviations, romanization ("rootcanal", "RCT", "route canal").
**It cannot bridge cross-script phonetic corruption** — Telugu-script "ఫ్రూట్ కెనాల్స్" and
Latin-script "root canal" share almost no characters; no similarity-ratio algorithm connects
them (empirically verified — removing the seeded alias makes that exact case return no
candidates at all). The real fix is the combination: §3's pinned STT language fixes it at the
source, and a curated literal alias (seeded, or captured via §5's telemetry and reviewed later)
is the backstop for whatever still slips through.

`FUZZY_MATCH_THRESHOLD = 0.72`; `normalize()` never mutates or auto-selects — it only ranks
candidates. `jkr_conversation/extractor.py`'s `_annotate_domain_candidates()` runs every field
extracted in a turn through the agent's vocabulary and attaches a `FieldExtraction`
(`raw_value`, `candidate_value`, `semantic_confidence`, `criticality`, `domain_term_id`) —
additive to `ExtractionResult`, zero risk to existing call sites.

## 5. Confirmation policy enforcement — closes the loop on bug 2

`ConversationPolicy.confirmation_behavior` existed in the DB and was completely unused before
this pass. `jkr_conversation/engine.py`'s `_requires_confirmation()` now actually enforces it —
crossed against each field's `criticality`:

| `confirmation_behavior` | Behavior |
|---|---|
| `confirm_none` | Never confirm |
| `confirm_all` | Always confirm |
| `confirm_low_confidence` | Confirm when `semantic_confidence < STRONG_MATCH_THRESHOLD (0.93)` |
| `confirm_critical` (DB default) | Confirm when the matched term's `criticality == "critical"` |

A field pending confirmation is **not** written to `known_fields` until resolved —
`compute_missing_required_fields()` needed zero changes, since an unwritten field is already
correctly "missing." At most one field is pending confirmation at a time
(`state["pending_confirmation"]`); a second candidate in the same turn is left unwritten and
resurfaces on a later turn.

**Resolution.** The next customer turn is classified as `confirm` / `reject` / `correction` —
`policy.detect_confirmation_response()` (keyword) in mock mode or when the LLM didn't classify;
the real-mode LLM's own classification is trusted when available (unlike do-not-call, this isn't
compliance-critical, so the deterministic backstop only fills gaps rather than overriding). A
`reject`/`correction` never lets the literal "yes"/"no" utterance become the field's value. A
field that exhausts its ask-cap (`planner.MAX_ASKS_PER_FIELD = 2`) while still pending is
accepted at its raw value rather than left stuck forever — same "ask twice, then accept what was
literally said" philosophy used elsewhere.

**Natural phrasing, not robotic.** `formatter.build_confirmation()` produces "Root canal
treatment గురించే అంటున్నారు కదా అండి?" — explicitly not "You said X, is that correct?", which
was the user's own rejected phrasing, enforced both in the canned fallback and in the LLM prompt
guidance (`prompt_builder.py`'s `ACTION GUIDANCE` block for `CONFIRM_FIELD`).

**Acknowledgement handling.** Short filler ("achha achha", "hmm", "okay") matched against
`ConversationPolicy.accidental_interruption_phrases` is tagged `turn_intent="acknowledgement"`
and extracts no field — it can never be mistaken for a real answer. Deliberately skipped
whenever a confirmation is actually pending (confirmation-response detection always takes
precedence there).

**Unanswered questions block completion.** A new planner action, `DEFER_QUESTION`: if
`COMPLETE_OBJECTIVE` would otherwise fire but the customer asked something this turn that wasn't
answered from real knowledge (`rag_above_threshold` is `False` — not merely "no chunks came
back," since `search_knowledge` always returns its top-k nearest regardless of match quality),
`engine.py` downgrades the decision instead of closing mid-question. Reuses the existing honest
"not sure, our team will confirm" fallback — no new template.

## 6. Telemetry

`transcript_correction_events` (`packages/db/jkr_db/models/calls.py`) — one row per domain-term
interaction: `raw_text`/`raw_term`, `candidate_term`, `accepted_term`, `correction_method`,
`confidence`, `customer_confirmed` (`True`/`False`/`None` — `None` means auto-applied without
requiring confirmation). Written by `engine.py`'s `_record_correction_event()`, real data now,
review/curation UI deferred (see §7). This is what turns "a customer says X and we heard Y" from
an anecdote into a queryable table a workspace's vocabulary can be extended from over time.

## 7. Scope — what's deferred

Explicitly out of scope for this pass, flagged for a later one: Agent Studio UI for managing
domain vocabularies/aliases (vocabulary is DB-seeded/managed directly for now), an STT
config/quality screen, a conversation-debug UI, analytics dashboards over
`transcript_correction_events`, multi-STT-provider fallback/A-B experiments, CSV vocabulary
upload, and an admin-approval workflow for auto-suggested aliases (nothing auto-learns into a
vocabulary — that stays a manual, reviewed action).

## 8. Tests

- `packages/conversation/tests/test_closing.py` — every reason/language combination carries a
  finality marker; unrecognized reasons still fall back safely.
- `packages/conversation/tests/test_domain_normalizer.py` — seeded-alias exact match, same-script
  fuzzy match, and the cross-script honest-limitation case (with vs. without the seeded alias).
- `packages/conversation/tests/test_engine.py` — end-to-end against a real DB: mis-transcription
  flagged (not silently trusted), customer confirms, customer rejects, customer states a
  correction, pending-question blocks premature completion.
- `packages/conversation/tests/test_prompt_builder.py` —
  `test_non_tool_backed_objective_completion_never_uses_free_generation` (previously asserted the
  opposite; that assertion *was* the bug).
- `services/api/tests/test_sarvam_stt.py` — `language_code`/`mode`/`model` actually sent over the
  wire, not just accepted as parameters.
- `services/api/tests/test_live_call_service.py` — grace-period TwiML shape (`<Play>` before
  `<Record>`, no `<Hangup>` in between), `_reopen_conversation_state` never touches
  `do_not_call`/`wrong_number`, `_end_reason_for` mapping.
