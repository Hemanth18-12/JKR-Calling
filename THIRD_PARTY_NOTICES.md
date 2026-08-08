# Third-Party Notices

JKR AI Calling reimplements architectural patterns from the reference repositories below inside
this codebase's own module structure. No large files were copied verbatim; where a specific
pattern (a validation routine, a state-machine shape, a pipeline stage ordering) was closely
adapted from a reference implementation, that is called out inline as a code comment at the
adaptation site, plus listed here.

## 1. CALLE-AI/awesome-phone-call-agents
- License: check upstream repository at time of integration; treat as MIT-compatible unless
  verified otherwise before production use.
- Patterns reimplemented (not copied): consent-first dispatch ordering, dry-run-as-default
  posture, E.164 normalization step placement, do-not-call suppression precedence, idempotent
  dispatch keying, structured call-result shape, retry/human-review queue states.
- Where: `services/campaign-worker/app/safety_gate.py`,
  `packages/db/jkr_db/models/campaigns.py` (state enums),
  `docs/SECURITY_AND_COMPLIANCE.md` §2.

## 2. bolna-ai/bolna
- License: check upstream repository (Bolna is Elastic License 2.0 / dual-licensed in parts as of
  its public repo — **do not** treat as permissively-licensed without re-verifying at time of any
  production ship; only architectural ideas, not code, were used here).
- Patterns reimplemented (not copied): STT→LLM→TTS streaming orchestration boundary, barge-in /
  interruption state machine shape, turn-latency measurement points, user/agent-speaking state
  tracking.
- Where: `services/voice-worker/app/turn_manager.py`,
  `docs/VOICE_ARCHITECTURE.md` §4.

## 3. Shubhamsaboo/awesome-llm-apps
- License: MIT (per upstream repository).
- Patterns reimplemented (not copied): RAG ingest→chunk→embed→retrieve pipeline shape,
  structured-extraction / missing-field / next-best-question loop, multi-stage post-call analysis
  pipeline pattern.
- Where: `services/api/app/modules/knowledge/`, `services/intelligence-worker/app/`,
  `docs/VOICE_ARCHITECTURE.md` §5.

## 4. blackdwarftech/siphon
- License: check upstream repository at time of integration (early-stage project; license terms
  should be re-verified before any production use of even the architectural ideas below).
- Patterns reimplemented (not copied): LiveKit-based SIP/WebRTC voice infra shape, worker-based
  call processing, provider-plugin boundary, self-hosted/data-sovereignty framing.
- Where: `services/voice-worker/` service boundary, `MediaRuntime` interface,
  `docs/DECISIONS/0002-voice-runtime.md`.

## 5. Direct dependencies

Standard OSS dependency licenses (MIT/Apache-2.0/BSD, as applicable) apply to every package
pulled via `pnpm`/`uv` and are not individually re-stated here; run `pnpm licenses list` and
`uv pip list --format=freeze` (or `pip-licenses`) before any production release to generate a
full dependency license manifest, and attach that manifest alongside this file at ship time.

## 6. Maintenance note

This file must be updated whenever a new external pattern, snippet, or dependency with
non-trivial licensing terms is introduced. If a future contributor copies a non-trivial code
block from any external source, the original license header must be preserved in the copied file
and a corresponding entry added here.
