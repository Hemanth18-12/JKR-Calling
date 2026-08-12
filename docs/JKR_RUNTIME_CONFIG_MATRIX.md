# JKR Runtime Config Matrix

**Purpose**: answer, unambiguously, "which architecture runs for every possible major flag combination?" and — most importantly — "what is the CURRENT EFFECTIVE CONFIG, right now, in this repo's `.env`?"

Source of truth: `services/api/app/config.py`'s `Settings` class (pydantic-settings, `env_file` anchored to repo-root `.env`, loaded once via `@lru_cache get_settings()` — process-wide, not per-workspace/agent/call). Verified against `/Users/siva/jkrAICalling/.env` and `.env.example` on 2026-08-11.

---

## THE HEADLINE FACT

> **`.env` sets exactly three things beyond their code defaults: `TWILIO_VOICE_TRANSPORT=media_stream`, `VOICE_MEDIA_DEBUG=true`, and the live-call safety gates (`ENABLE_LIVE_CALLS=true`, `AUTHORIZED_TEST_NUMBERS=...`). Every other P3–P9 flag — `STT_MODE`, `TTS_MODE`, `TURN_DETECTION_MODE`, `CONVERSATION_ENGINE_MODE`, `LLM_RESPONSE_MODE`, `BARGE_IN_ENABLED` — is absent from `.env` and therefore sits at its conservative code default.**

Because `config.py` gates almost every advanced feature behind a *cascade* (a flag must be explicitly set to its non-default value **and** the transport must be `media_stream`), turning on `media_stream` alone does not turn on streaming STT, streaming TTS, hybrid turn detection, streaming LLM, or barge-in. It only switches the wire-level transport from Twilio's `<Record>` webhook loop to a persistent WebSocket — and then, because none of the other flags followed it, the code that actually runs over that WebSocket falls back to `transitional_bridge.py`, an intentionally-simpler "batch STT/TTS bridged onto the new transport" implementation.

---

## Effective configuration table (current `.env`, verified 2026-08-11)

| Flag | Allowed values | Code default (`config.py`) | `.env` value | **Effective value** | What it actually gates |
|---|---|---|---|---|---|
| `TWILIO_VOICE_TRANSPORT` | `record` \| `media_stream` | `record` (:83) | `media_stream` (`.env:92`) | **`media_stream`** | `<Record>`/webhook-per-turn vs. persistent `<Connect><Stream>` WebSocket |
| `STT_MODE` | `batch` \| `streaming` | `batch` (:99) | *unset* | **`batch`** (`effective_stt_mode`, :108-115) | `transitional_bridge.py` (batch REST STT) vs. `streaming_bridge.py` (Sarvam WS STT + `TurnManager`) |
| `TTS_MODE` | `batch` \| `streaming` | `batch` (:125) | *unset* | **`batch`** (`effective_tts_mode`, :135-144) | Single REST `SarvamTTS.synthesize()` per turn vs. persistent Sarvam TTS WebSocket + `RealtimePipelineCoordinator` |
| `TURN_DETECTION_MODE` | `provider` \| `vad` \| `hybrid` | `provider` (:153) | *unset* | **`provider`** (`effective_turn_detection_mode`, :157-167, additionally requires `effective_stt_mode=="streaming"`) | Whether `TurnManager`/`EnergyVAD`/semantic-completeness gating runs at all — **moot**: `TurnManager` is only ever instantiated inside `streaming_bridge.py`, which doesn't run under batch STT |
| `CONVERSATION_ENGINE_MODE` | `legacy` \| `fast` | `legacy` (:75) | *unset* | **`legacy`** | Whether `fast_router.route()` and the canned-response fast path run at all — under `legacy`, `fast_router` is **never called** |
| `LLM_RESPONSE_MODE` | `complete` \| `streaming` | `complete` (:179) | *unset* | **`complete`** | Whether `prompt_builder.generate()` blocks on `complete_text()` vs. streams via `StreamingResponseAssembler`/`SpeakableChunker` |
| `BARGE_IN_ENABLED` | bool | `False` (:188) | *unset* | **`False`** (`effective_barge_in_enabled`, :201-217, additionally requires streaming STT + streaming TTS + vad/hybrid turn detection) | Automatic mid-response interruption handling — quadruply gated off |
| `BARGE_IN_SENSITIVITY` | `low` \| `balanced` \| `high` | `balanced` (:194) | *unset* | `balanced` | Interruption-classification thresholds — inert while barge-in is off |
| `TTS_STREAM_FAILURE_POLICY` | `batch_fallback` \| `fail` | `batch_fallback` (:133) | *unset* | `batch_fallback` | Only relevant under `TTS_MODE=streaming` — inert |
| `STT_STREAM_FAILURE_POLICY` | `fail` \| `batch_next_turn` | `fail` (:106) | *unset* | `fail` | Only relevant under `STT_MODE=streaming` — inert |
| `twilio_media_stream_failure_policy` | `fail` \| `fallback_record` | `fail` (:90) | *unset* | `fail` | What happens if the WS never gets a valid Twilio `start` event in time |
| `VOICE_MEDIA_DEBUG` | bool | `False` (:91) | `true` (`.env:93`) | **`True`** | Verbose per-frame `media_frame_received` logging (never raw audio) |
| `interruption_cancel_timeout_ms` | int (ms) | `2000` (:199) | *unset* | `2000` | Cap on provider-cancel hang during an interruption — only exercised if barge-in ever runs |
| `turn_profile` | `fast`\|`balanced`\|`patient` | `balanced` (:154) | *unset* | `balanced` | "Informational" only under `provider` mode — **zero effect today** |
| `local_vad_enabled` | bool | `False` (:155) | *unset* | `False` | Gates `EnergyVAD` construction inside `streaming_bridge.py` — moot, that module doesn't run |
| `ENABLE_LIVE_CALLS` | bool | `False` | `true` (`.env:58`) | **`True`** | Master safety switch for `/api/v1/live-call` — the one flag that's actually live-enabling something today |
| `AUTHORIZED_TEST_NUMBERS` | CSV of E.164 | `""` | 3 real numbers (`.env:59`) | 3 numbers | Only these numbers can be dialed via Live Test Call — the real safety boundary |

**Not real flags** (mentioned in earlier specs, don't exist in code): `REALTIME_COORDINATOR_ENABLED` — the coordinator activates automatically and *only* when `effective_tts_mode=="streaming"`; there is no separate toggle.

---

## What this means concretely: the active vs. dormant stack

```
                         ACTIVE TODAY                          DORMANT TODAY (built, tested, unreachable)
                         ─────────────                          ──────────────────────────────────────────
Transport                media_stream (WebSocket)               <Record> webhook-per-turn (code default, not used)
Turn boundary             transitional_bridge.TurnBuffer:        streaming_bridge.py + turns/manager.py TurnManager:
                          flat 4.0s trailing-silence RMS          provider/vad/hybrid modes, semantic completeness,
                          buffer (untuned SILENCE_RMS_             thinking-pause extension, backchannel classifier
                          THRESHOLD=300), no semantics
STT                       sarvam_stt.py — one batch REST          sarvam_streaming_stt.py — persistent Sarvam WS,
                          call per turn, no partials, no          partial/final transcripts, SpeechStarted/Ended,
                          confidence, no reconnect                bounded reconnect (3 attempts)
Conversation engine       "legacy" — fast_router never            "fast" — deterministic canned responses for
                          called, every turn pays full             ASK_FIELD/CLARIFY/CONFIRM_FIELD/DEFER_QUESTION,
                          extraction LLM call                      response-generation LLM structurally unreachable
LLM response              "complete" — prompt_builder blocks      "streaming" — StreamingResponseAssembler +
                          on one full completion                  SpeakableChunker, first chunk at first sentence
TTS                       sarvam_tts.py — one batch REST          sarvam_streaming_tts.py — persistent WS,
                          call per turn, "priya" voice             mu-law/8kHz native, VoicePersona pace honored
                          (VoicePersona pace now forwarded —
                          Stage 2 Fix 3; voice/provider still
                          defaults to mock in seed data)
Pipeline coordinator      None — never constructed                RealtimePipelineCoordinator — response identity,
                          (session.pipeline_coordinator            epochs, playback-unit state machine, one
                          stays None all call)                     non-test construction site, fully gated off
Barge-in                 Does not exist on a live call —          InterruptionPolicy — critical/high-priority cue
                          customer interruptions are               lists, backchannel classifier, ~200-450ms
                          silently ignored until the agent's       typical react time if all 4 gates were on
                          batch TTS finishes playing
Replay protection         N/A in practice — chunks carry           ResponseIdentity + CustomerFacingOutputGate
                          identity=None (documented legacy         (can_send_media()) — 5-layer defense, fully
                          exception), nothing to protect            built, exercised only in tests today
                          against since there's only ever
                          one response in flight at a time
```

**The one-sentence version**: this deployment is running the pre-P4 architecture end-to-end (batch STT, blocking LLM, batch TTS, no turn manager, no barge-in, no coordinator) inside a P2-era WebSocket transport shell. The P4–P9 work is real, tested, and sitting one `.env` block away from activating — but as configured today, none of it runs on a real call.

---

## How to actually turn each layer on (for reference — do not flip all at once; see the quality-audit doc's "measure first" guidance)

Per `docs/P10_REAL_CALL_BENCHMARK.md`'s own recommended staging block (not currently applied):

```env
TWILIO_VOICE_TRANSPORT=media_stream
STT_MODE=streaming
TURN_DETECTION_MODE=hybrid
CONVERSATION_ENGINE_MODE=fast
LLM_RESPONSE_MODE=streaming
TTS_MODE=streaming
BARGE_IN_ENABLED=true
BARGE_IN_SENSITIVITY=balanced
```

Each of these is independently gated, so partial activation is possible and meaningful (e.g. `STT_MODE=streaming` alone activates `streaming_bridge.py`'s turn manager and provider-mode STT partials, without touching TTS or barge-in). But `BARGE_IN_ENABLED=true` only has any effect once `STT_MODE=streaming`, `TTS_MODE=streaming`, and `TURN_DETECTION_MODE` is `vad` or `hybrid` are *all* also true — it is the top of the cascade, not an independent switch.

## Config drift found

- **`.env.example` documents none of these flags at all** — `STT_MODE`, `TTS_MODE`, `TURN_DETECTION_MODE`, `CONVERSATION_ENGINE_MODE`, `LLM_RESPONSE_MODE`, `BARGE_IN_ENABLED`/`BARGE_IN_SENSITIVITY`, `*_STREAM_FAILURE_POLICY`, `INTERRUPTION_CANCEL_TIMEOUT_MS`, `TURN_PROFILE`, `LOCAL_VAD_ENABLED` appear nowhere in `.env.example`. An engineer bootstrapping from the example file would never learn these knobs exist.
- **`docker-compose.yml`** passes `.env` through unchanged via `env_file: .env` for every service — no divergent overrides for any of these flags there.
- **Separate DB-role drift** (adjacent to this audit but worth flagging): `docker-compose.yml` builds `DATABASE_URL` from `APP_DB_USER`/`APP_DB_PASSWORD` (the RLS-enforced non-superuser role `.env.example` says application services must use), but `.env` never defines those two vars and instead sets `DATABASE_URL` directly to the **bootstrap superuser** role (`jkr:jkr_local_dev`). Every native (non-Docker) process — which is how this repo is actually run per the README's `dev-native` instructions — connects as superuser, bypassing Postgres RLS entirely.
- **`OPENAI_API_KEY` plumbing is native-startup-fragile**: `embed_text()`/`get_default_client()` (`packages/db/jkr_db/embeddings.py`, `packages/conversation/jkr_conversation/llm_client.py`) read `os.environ` directly, not the pydantic `Settings` object. `Settings(env_file=...)` populates the `Settings` model only — it does not copy values into `os.environ`. Docker Compose's `env_file:` directive does inject real env vars into containers, so this is a non-issue there; the native `uv run uvicorn` startup path documented in the README has no explicit step that re-exports `.env` into the process's `os.environ` for this variable. Confirm operationally (e.g. print `os.environ.get("OPENAI_API_KEY")` at process start) before assuming real embeddings/LLM calls are firing on a given native run — `Settings.openai_api_key`/`Settings.llm_provider_default` are populated but never actually consumed by the gating logic.
