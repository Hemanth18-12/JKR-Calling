# Implementation Checklist

Living document. Updated as work lands. Tier markers: **Deep** (real logic, tested) / **Medium**
(real CRUD + basic logic) / **Scaffold** (schema + route + minimal UI, explicitly not full logic)
— see `docs/DECISIONS/0007-scope-for-this-pass.md`.

## Phase 0 — Repository audit & docs
- [x] Inspected repo (empty, greenfield)
- [x] docs/MASTER_PLAN.md
- [x] docs/ARCHITECTURE.md
- [x] docs/DATA_MODEL.md
- [x] docs/API_DESIGN.md
- [x] docs/VOICE_ARCHITECTURE.md
- [x] docs/SECURITY_AND_COMPLIANCE.md
- [x] docs/DECISIONS/0001–0007
- [x] docs/IMPLEMENTATION_CHECKLIST.md (this file)
- [x] THIRD_PARTY_NOTICES.md
- [x] .env.example
- [x] Makefile
- [x] docker-compose.yml
- [x] Root workspace tooling (package.json, pnpm-workspace.yaml, turbo.json, pyproject.toml)
- [x] README.md

## Phase 1 — Foundation
- [x] `packages/db` full schema (74 tables, all §24 tables) + Alembic migrations (initial schema,
      app role + RLS, RBAC catalog seed) — **Deep**. Verified live: migrations apply cleanly to a
      fresh Postgres+pgvector database; RLS confirmed to block cross-tenant reads AND reject
      cross-tenant writes when connected as the non-superuser `jkr_app` role (not just the
      superuser used for migrations); `pytest packages/db/tests` passes (9 tests: phone
      normalization/masking, schema completeness against spec §24, workspace_id indexing).
- [x] Auth (signup/login/session/logout), Argon2id hashing, Postgres-backed sessions — **Deep**.
      `services/api/app/modules/identity/*`. Session tokens: random opaque token in an httpOnly
      cookie, only its SHA-256 hash persisted. Verified live end-to-end (signup, login, logout,
      session expiry check, `/auth/me`).
- [x] RBAC (roles/permissions catalog + `require_permission`/`require_membership_with_permission`
      enforcement) — **Deep**. Verified live: a second workspace member with `campaign_manager`
      role correctly gets 403 on `workspaces:manage`-gated `PATCH /workspaces/{id}` while
      succeeding on `workspaces:view`-gated reads; membership `status=invited` correctly blocks
      access until activated.
- [x] Workspaces CRUD + membership (`services/api/app/modules/tenancy/*`) — **Deep**. Verified
      live: create → owner membership auto-created, invite by email → activate → role-gated access.
- [x] Next.js app shell (`apps/web`) — collapsible sidebar with full nav matching spec §6,
      workspace switcher (backed by a real `POST /auth/session/active-workspace` endpoint, not a
      cookie hack), env badge, design tokens (dark-first, CSS-variable based, spec §5 palette) —
      **Deep**. `packages/ui` (shared components), `packages/contracts` (Zod schemas mirroring the
      Pydantic ones), `packages/sdk` (typed fetch client) also stood up this phase.
- [x] Login/signup pages — **Deep**, real forms (react-hook-form + zod) against the live API.
      Onboarding wizard (`/onboarding/*` multi-step flow) — **Scaffold**: workspace creation
      currently happens inline on an empty dashboard rather than a dedicated wizard; noted as a gap.
- [x] Team page (`/app/team`) and Settings page (`/app/settings`) — **Deep**, real invite/
      activate/suspend and workspace-settings-edit flows, since the backing API already existed.
- [x] Stub pages for every other top-level nav route (agents, campaigns, contacts, calls,
      knowledge, follow-ups, handoffs, appointments, analytics, compliance, integrations, billing,
      usage) so the sidebar never 404s — **Scaffold**, explicitly labeled "not built yet" with the
      phase that will build them, not disguised as real.
- [x] Verified end-to-end through the actual running Next.js dev server (not just curl against the
      API): signup → empty-workspace prompt → create workspace → dashboard shows real
      user/workspace data → team page lists the owner → settings page loads → unauthenticated
      `/app/dashboard` correctly redirects to `/login`. `pnpm build`, `pnpm lint`, `pnpm typecheck`
      all pass clean across every package.

### Real bugs found and fixed while building/testing Phase 1 (kept here since they shape the
### session/RLS conventions every later phase must follow)
1. **Naive vs. aware datetimes** — bare `Mapped[datetime]` columns defaulted to non-timezone
   `TIMESTAMP`, but all app code produces timezone-aware datetimes. Fixed at the root:
   `Base.type_annotation_map = {datetime: DateTime(timezone=True)}` in `packages/db/jkr_db/base.py`,
   so every datetime column anywhere is timezone-aware by construction, not by per-column diligence.
2. **`SET LOCAL` cannot take a bind parameter** — Postgres rejects `$1` in a `SET`/`SET LOCAL`
   statement outright (this is a Postgres limitation, not a driver bug). Fixed by validating the
   value is a real UUID (`uuid.UUID(str(value))`) and only then interpolating the canonical string
   directly into the SQL text — safe because a successfully-parsed UUID can only render back as
   `[0-9a-f-]`. See `jkr_db.session._validated_uuid_literal`.
3. **One commit per request, not several** — `SET LOCAL`'s effect ends at `COMMIT`/`ROLLBACK`; a
   service function calling `db.commit()` mid-request silently dropped the RLS context for
   anything queried afterward on the same session. Fixed by making every session dependency wrap
   its body in a single `session.begin()` (commits once, on clean exit) and having all service
   code use `await db.flush()` instead of `commit()`. Documented prominently in
   `jkr_db/session.py`'s module docstring so it isn't reintroduced in Phase 2+.
4. **Empty-string GUC residue under connection pooling (the subtle one)** — confirmed live via
   direct psql reproduction: Postgres resets a custom (`app.*`) GUC to `''` (empty string), not
   `NULL`, once it has been `SET LOCAL`'d and committed even once on a given physical connection;
   `current_setting(name, true) IS NULL` is only true for a GUC *never* touched on that connection.
   Under `services/api`'s pooled engine, a connection previously used by `user_scoped_session`
   (which never sets `app.current_workspace_id`) gets reused later for an ordinary
   `workspace_scoped_session` request, and the leftover `''` fails to cast to `uuid` — a hard
   error, not a harmless non-match. Fixed by wrapping every RLS policy's `current_setting(...)` in
   `NULLIF(..., '')` before the `::uuid` cast; locked in by
   `packages/db/tests/test_rls_policy_sql.py` (fails the build if a future migration adds an
   unguarded cast) and written up in full in `docs/DECISIONS/0004-tenant-isolation.md`.
5. **`workspace_members` can't use the plain single-workspace RLS policy** — a caller must be able
   to list every workspace they belong to before any one workspace is "active" (workspace
   switcher, `GET /workspaces`, workspace creation itself), which a policy scoped to one
   `app.current_workspace_id` can never satisfy. Gave that one table a dual-condition policy
   (`workspace_id = ... OR user_id = ...`) backed by a second session variable
   (`jkr_db.session.user_scoped_session`) — see ADR-0004 for the full reasoning and the
   application-layer check that keeps this from being a cross-tenant read.
- [x] Docker Compose (postgres+pgvector, redis, minio, livekit, api, workers, web) — ports
      55432/16379 for postgres/redis (not 5432/6379 — this dev machine runs native instances of
      both already; see docker-compose.yml comments)

### Notes / deviations from the original port-standard assumption
- Postgres and Redis are exposed on host ports 55432/16379 instead of 5432/6379 because this
  machine already runs native Postgres and Redis on the standard ports. Container-to-container
  traffic (api ↔ postgres, etc.) is unaffected — it uses the standard ports via Docker service
  DNS. `.env.example` documents this.
- Two Postgres roles are provisioned, not one: `jkr` (superuser, bootstrap + migrations only) and
  `jkr_app` (RLS-enforced, what every service actually connects as) — see
  docs/DECISIONS/0004-tenant-isolation.md and the `cc55370bda3d` migration.

## Phase 2 — Agents & providers
- [x] Agent/version/persona/voice/policy models + API — **Deep**.
      `services/api/app/modules/agents/*`: full CRUD, versioning (immutable once published, clone
      to a new draft), 7 persona templates (spec §8.2) with disclosure-compliant defaults,
      voice-persona + conversation-policy + pronunciation-entry sub-resources, publish-time
      validation (blocks publishing without a disclosure, greeting, or closing — spec §28/§4).
      Verified live end-to-end against the running API: create → get → update policy/voice →
      add pronunciation entry → clone to v2 → publish v1 → agent status flips to `active`.
- [x] Provider accounts (workspace-scoped config, not yet the runtime adapters — those are Phase 3)
      — **Deep** for accounts/catalog/health-check-stub; every new workspace auto-seeds one `mock`
      account per kind (telephony/stt/llm/tts), always `healthy`, matching
      docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md. Provider credentials encrypted at
      rest (Fernet, key derived from `CREDENTIALS_ENCRYPTION_KEY`). The actual `TelephonyProvider`/
      `SpeechToTextProvider`/`LLMProvider`/`TextToSpeechProvider` runtime interfaces and adapters
      live in `services/voice-worker` — **Phase 3**, not this phase; provider router w/ fallback
      is also Phase 3 (needs the runtime adapters to route between).
- [x] Agent Studio UI (`apps/web/app/app/agents/*`) — list, create (persona-template picker),
      tabbed detail (Overview/Persona/Voice/Versions real; Knowledge/Tools/Test Lab stubbed
      pointing at Phases 4/6/3) — **Deep** for the real tabs. Verified live through the actual
      Next.js dev server: empty state → create agent → list shows it → overview/persona/voice/
      versions all render real data → publish button flips status.

### Real bugs found and fixed while building/testing Phase 2
1. **Doubled honorific in greeting text ("గారు గారు")** — `create_agent`'s original fill step used
   `str.format(business=..., name=contact_name_placeholder)`, pre-baking a *literal* placeholder
   string (e.g. "గారు") into `{name}` at agent-creation time. But the templates already write
   "{name} గారు" — the honorific is meant to follow the *contact's actual name*, substituted per
   call, not baked in once at creation. Fixed by only filling `{business}` (static per agent) via
   `.replace()` (not `.format()`, so an unfilled `{name}` doesn't raise `KeyError`) and leaving
   `{name}` as a literal token in the stored text for `voice-worker` (Phase 3) to substitute with
   the real contact name per call. `contact_name_placeholder` removed from the create-agent API
   entirely — it was solving a problem that shouldn't have existed. Locked in by
   `services/api/tests/test_agents_service.py::test_every_persona_template_greeting_keeps_name_placeholder_literal`.
2. **`set_active_workspace`'s membership check ran on the wrong connection** — calling it
   immediately after creating a workspace (same request, not-yet-committed transaction) 403'd,
   because its membership re-check opens a *separate* `user_scoped_session` (different physical
   connection) that — correctly, per Postgres read-committed isolation — can't see a row `db` has
   only flushed, not committed, on another connection. Fixed by not routing the
   "just-created-it-myself" case through that re-check at all: `create_workspace` now sets
   `auth.session.active_workspace_id` directly (that session object lives on its own already-open
   connection for the request's duration and commits normally at request end) — the re-check in
   `identity_service.set_active_workspace` is still correct and still used for the genuine
   "switch to an existing, already-committed workspace" case.

## Phase 3 — Real-time voice core
- [x] `voice-worker` service scaffold (`services/voice-worker`) — **Deep**. Own FastAPI process,
      own DB connection pool, shared-secret (`X-Internal-Token`) auth since only `services/api`
      ever calls it (docs/ARCHITECTURE.md §1). `services/api/app/modules/calls` proxies
      create/user-turn/end and independently reads `call_*` tables for call detail — the browser
      never talks to voice-worker directly.
- [x] `TurnManager` (`app/turn_manager.py`) — **Deep**. Real phrase-list + word-count +
      `min_interruption_ms` timing-floor classification (meaningful / false-positive / none),
      simulated-speaking-window timing derived from formatted text length. 7 unit tests
      (`tests/test_turn_manager.py`).
- [x] `SpokenResponseFormatter` (`app/spoken_formatter.py`) — **Deep** for markdown/URL/
      abbreviation stripping, rupee normalization, sentence-count truncation, non-repeating
      acknowledgement rotation, and the "never silently guess" clarification builder. Full
      number-to-words normalization for mixed Telugu/Hindi/English speech is explicitly **out of
      scope** — narrow, real slice implemented (rupee amounts), not pretended complete. 8 unit
      tests (`tests/test_spoken_formatter.py`).
- [x] Mock STT/LLM/TTS wired end-to-end, call session lifecycle — **Deep**. `MockLLM`
      (`app/providers/mock.py`) is a scripted FSM keyed by the agent's `primary_objective` (5
      scripts covering all 7 persona templates), not a generic chat-completion streamer — a real
      LLM adapter satisfying the general `LLMProvider` Protocol is still a Phase-3-scoped stub
      pending credentials (`docs/VOICE_ARCHITECTURE.md` §2). `conversation_engine.py` persists
      every turn/event/latency-metric/interruption to the real schema; call end writes a basic
      `CallOutcome`/`CallTranscript` (full LLM-based summary/quality-eval is Phase 4's post-call
      intelligence pipeline, not duplicated here). Verified live end-to-end through the real
      Next.js dev server → services/api → voice-worker chain, including a genuine barge-in
      (meaningful interruption cancels the in-flight agent turn) and a filler word ("అవును")
      correctly NOT advancing the script. 3 integration tests against a real Postgres DB
      (`tests/test_conversation_engine.py`), 38/38 Python tests passing project-wide.
- [x] Agent Studio Test Lab (`/app/agents/[agentId]/test`) — **Deep**. Real chat UI (not a mock),
      shows extracted fields live, flags interrupted/filler turns, shows outcome on end.
- [ ] **Known gaps carried forward**: (1) SSE live-tailing endpoint (`GET /calls/{id}/events`) —
      deferred to Phase 7's Live Call Console, which is what actually needs push updates for a
      call it isn't driving turn-by-turn itself (Test Lab gets the agent's reply synchronously in
      the same HTTP response, so it never needed SSE). (2) `infra/docker/*.Dockerfile` for
      api/voice-worker/web don't exist yet — every service has been run and verified natively
      (`uv run uvicorn ...` / `pnpm dev`) this whole phase, matching the Makefile's documented
      `dev-native` path; containerizing is deferred to Phase 10's hardening pass rather than
      built (and untested) speculatively now. (3) Call runtime state
      (`TurnManager`/`MockLLM` script cursor) is in-process memory, lost on a voice-worker
      restart mid-call — documented tradeoff in `session_registry.py`, not silently assumed away.

## Phase 4 — Knowledge & intelligence
- [x] Ingestion pipeline (manual FAQ, text, PDF, docx, csv, website) + chunking + embedding —
      **Deep**. `services/api/app/modules/knowledge/extraction.py`: SSRF-guarded website fetch
      (`_assert_public_host` resolves the hostname and rejects private/loopback/reserved/link-local
      ranges, then re-validates on every redirect hop rather than trusting the first check), PDF/
      docx/csv text extraction, paragraph-aware chunking with overlap. Documents are accepted as
      base64-in-JSON, not multipart — original file bytes are not persisted to object storage this
      pass (documented in `schemas.py`'s `DocumentCreate.file_base64` docstring).
- [x] Approval workflow — **Deep**. `draft → processing → needs_review → approved/rejected`;
      only `approved` chunks are ever returned by retrieval, enforced in the query itself
      (`approval_state == "approved"`), not just hidden in the UI.
- [x] Retrieval w/ workspace+approval filtering — **Deep**. pgvector cosine-distance search,
      `RETRIEVAL_DISTANCE_THRESHOLD = 0.75` — below it the caller gets `above_threshold: false` and
      must not answer from it. Every query logs a `RetrievalEvent` (hit or miss) for the
      knowledge-grounding-rate analytics in spec §22. **Known limitation, not a regression**:
      `mock_embed()` (`packages/db/jkr_db/embeddings.py`) is a deterministic bag-of-hashed-words
      vector, not a real semantic embedding, so even closely related mock-data queries often score
      below the 0.75 threshold (verified live: "how much does root canal cost" against an approved
      chunk containing "Root canal treatment costs... rupees" scored 0.18, i.e. correctly refused
      rather than guessed). A real `OPENAI_API_KEY` swaps in true embeddings via the same
      `embed_text()` call with no code change elsewhere.
- [x] Structured extraction / next-best-action selector — **Deep**, done as part of the post-call
      pipeline below (`_validate_extracted_fields`) rather than as a separate module — the spec's
      "next-best-action" concept is realized as `conversation_engine`'s per-turn script-state
      advance plus the knowledge-lookup fallback, not a standalone selector service.
- [x] Post-call intelligence actors (summary, extraction validation, outcome, lead score, quality
      eval, follow-up) — **Deep**. `services/intelligence-worker/app/pipeline.py`, run as a
      Dramatiq actor (`run_post_call_pipeline`) enqueued by `calls.service.end_call` via the shared
      `packages/messaging` producer/consumer package (producer never imports the worker's code,
      only constructs a raw `dramatiq.Message`). Rule-based outcome classification
      (`_classify_outcome`, DNC-word + monologue-length heuristics), quality evaluation
      (`_evaluate_quality`, disclosure-marker + frustration-word checks), summary generation, and
      follow-up channel selection (`OUTCOME_FOLLOWUP_CHANNEL`) all write to the real schema.
      11 unit tests on the pure logic functions (`tests/test_pipeline.py`).
- [x] Knowledge frontend (`/app/knowledge/documents`) — **Deep**. Single unified page (not four
      separate `/documents` `/websites` `/review` `/collections` routes as originally sketched —
      one page covers document list w/ approval badges, a source-type-driven create form
      (raw-text textarea for manual_faq/text, URL input for website, file→base64 for pdf/docx/csv),
      inline approve/reject, and a live retrieval test panel) plus a read-only "workspace
      knowledge" view on each agent's Knowledge tab (`/app/agents/[agentId]/knowledge`) — honestly
      labeled as workspace-wide rather than agent-scoped, since retrieval genuinely isn't scoped
      per agent this pass. Verified live through the real Next.js dev server + API chain: created
      a manual-FAQ document, processed it (1 chunk), approved it, confirmed it renders with an
      `approved` badge on both the Knowledge page and the agent's Knowledge tab, and confirmed
      search correctly reports `above_threshold: false` for the mock-embedding case above rather
      than fabricating an answer. `pnpm typecheck` / `lint` / `build` all pass.

### Real bugs found and fixed while building/testing Phase 4
1. **Doubled sentence-ending punctuation in knowledge answers** — concatenating a retrieved chunk
   with a follow-up question could produce `"...9 AM to 8 PM..Anything else?"` when the chunk
   already ended in punctuation. Fixed by checking whether the snippet already ends in `.`/`!`/`?`
   before appending more.
2. **Ruff B007 unused loop variable** in the SSRF guard's address-family iteration (`family`)
   — renamed to `_family` per the existing convention for intentionally-unused loop variables.
3. **Apparent "pipeline didn't run" false alarm** — Redis-side inspection right after `end_call`
   showed no visible queue entry and dramatiq's own success log line didn't match the grep pattern
   used to check it, which looked like the actor silently failed. Not a bug: a direct Postgres
   query for the test `call_id` showed `quality_evaluations`, `call_summaries`
   (`generated_by='intelligence_worker_rules'`), `call_outcomes`, and `extracted_fields`
   (`is_validated=true`) rows all present — the queue entry had simply already been consumed and
   deleted by the time it was inspected. Worth recording so a future pass doesn't "fix" a
   non-issue by grep-driven debugging instead of querying actual state.

## Phase 5 — Campaign engine
- [x] Contacts + consent + suppression — **Deep**. `services/api/app/modules/contacts/*`:
      CRUD (E.164 normalization + dedup by phone), consent events (purpose/source/expiry,
      unexpired-and-unrevoked lookups), suppression entries (written synchronously — takes effect
      before the request that created it even returns, per docs/SECURITY_AND_COMPLIANCE.md §3),
      static segments (a named list of contact_ids — dynamic query-based segments are explicitly
      **out of scope** this pass). Verified live: creating a contact whose phone already has a
      suppression entry auto-sets `is_suppressed=true` at creation time, not just on next gate check.
- [x] Campaign CRUD + versions — **Deep**. `services/api/app/modules/campaigns/*`: campaigns pin
      `agent_version_id` at creation (rejects agents with no published version), auto-create a
      `CampaignSchedule` from the workspace's calling-hours defaults, immutable `CampaignVersion`
      snapshot written at every launch.
- [x] Safety gate (10 checks, docs/SECURITY_AND_COMPLIANCE.md §2) — **Deep**, and moved to
      `packages/db/jkr_db/safety_gate.py` (not `services/api`) specifically so `/dry-run` and
      campaign-worker's real dispatch loop share the literal same implementation — see that
      module's docstring and `docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md`. Pure/
      read-only (only ever peeks at the two Redis-backed checks — dispatch lock, rate limit —
      never mutates them); the "reserve" side effects doc §2 describes happen once, only in
      campaign-worker, strictly after all ten pass. One deliberate deviation from the doc's literal
      wording: check #1 accepts `draft` **or** `active` campaign status (not just `active`) so
      `/dry-run` is actually usable pre-launch, which is its whole stated purpose; the real dialer
      only ever calls the gate once a campaign is already `active`, so this doesn't loosen live
      dispatch. Verified live: a contact with no consent record is correctly blocked at check 3
      while a consented contact clears all ten.
- [x] Dry-run endpoint (no side effects) — **Deep**. `POST /campaigns/{id}/dry-run` evaluates every
      campaign_contact through the shared gate and reports would-dispatch/blocked-and-why without
      reserving or dispatching anything.
- [x] `campaign-worker` dialer loop + retry policy — **Deep**. New service
      (`services/campaign-worker`), a Dramatiq actor (`run_campaign_dispatch_batch`) that
      self-reschedules (via `jkr_messaging.enqueue(..., delay_seconds=...)`) to drain a batch,
      pick up due `retry_jobs`, or wake at the next retry's `scheduled_for` — no cron needed.
      Since this pass has no real telephony adapter wired into voice-worker at all (a Phase 3
      scope boundary, not new here), every dispatch is a mock call; a campaign call has no human
      typing the customer's side the way Test Lab does, so campaign-worker auto-plays a small
      round-robin set of generic customer replies to drive the call to a genuine completion (real
      turns, extraction, and post-call intelligence) — documented as a deliberate simplification of
      "who plays the customer," not a hidden shortcut. Connect outcomes (`answered`/`no_answer`/
      `busy`/`provider_error`) are simulated deterministically (hash of contact+attempt, biased
      toward `answered`) so retries and the backoff schedule (`campaign.retry_policy`) genuinely
      get exercised. Redis dispatch-lock + rate-limit counters are real (not simulated).
- [x] Frontend — **Deep**. `/app/contacts` (list with consent/suppression badges, add contact,
      per-contact "record consent" inline form, suppress-a-number form + suppression list panel),
      `/app/campaigns` (list, create), `/app/campaigns/[id]` (status/contact-count badges,
      launch/pause/cancel, live dry-run panel showing per-contact pass/fail-and-why, add-contacts
      checklist). `pnpm typecheck`/`lint`/`build` all pass.

### Real bugs found and fixed while building/testing Phase 5 (both caught by actually launching a
### campaign against the live stack, not by unit tests — kept here since they'd bite any future
### background-job or automated-caller work on this codebase)
1. **Two Dramatiq worker services silently traded each other's jobs** — `intelligence-worker` and
   the new `campaign-worker` both consumed from Dramatiq's default `"default"` Redis queue.
   `jkr_messaging.enqueue()` only requires the queue name to match between producer and consumer,
   not the actor — so `run_post_call_pipeline` messages were sometimes delivered to
   campaign-worker's consumer (which has no such actor) and vice versa, and Dramatiq moved both to
   the dead-letter queue instead of ever running them. Caught live: launching a campaign showed the
   dial actually happen (voice-worker's HTTP calls all `200 OK`) but the post-call pipeline's
   tables stayed empty, and both workers' logs showed `ActorNotFound`. Fixed by giving each worker
   its own dedicated queue name (`"intelligence"`, `"campaigns"`) on both the `@dramatiq.actor(...,
   queue_name=...)` declaration and every `enqueue(..., queue_name=...)` call site — `enqueue()`
   itself gained a `delay_seconds` parameter in the same pass (needed for campaign-worker's
   self-rescheduling), mapped to Dramatiq's native `delay` option.
2. **Auto-played campaign calls always resolved "unreachable" despite every HTTP call succeeding**
   — campaign-worker's mock-customer loop posted the next reply immediately after receiving the
   agent's turn. `TurnManager.handle_user_utterance` (services/voice-worker/app/turn_manager.py)
   correctly classifies any utterance arriving before the agent's simulated speaking window
   elapses (`elapsed_ms < min_interruption_ms`, default 250ms) as a `false_positive` filler, and
   `conversation_engine.submit_user_turn` correctly early-returns on that classification without
   advancing the script (spec §11) — so every one of the six auto-played replies was silently
   discarded, `known_fields` stayed empty, and the call outcome always classified as `unreachable`.
   This is the *same class* of timing assumption noted in Phase 3's fixture fix, just hit for real
   this time by a non-human caller with no natural pacing. Fixed by having `/sessions` and
   `/sessions/{id}/user-turn` return each agent turn's `estimated_duration_ms`
   (`turn_manager.estimate_speaking_duration_ms`) and having campaign-worker's `_run_mock_call`
   `await asyncio.sleep()` that long (+150ms margin) before posting the next reply — verified live:
   the same campaign that previously produced `category=unreachable` with empty `score_reasons` now
   produces `category=qualified, lead_score=warm` with both script fields captured in
   `extracted_fields`, and the post-call pipeline (summary/quality/extraction) runs on it.

### Notes / deviations
- Consent purpose is inferred from `campaign.objective` via a fixed mapping
  (`jkr_db.safety_gate.OBJECTIVE_TO_CONSENT_PURPOSE`) rather than a configurable per-workspace
  setting — spec §8 mentions "campaign purpose categories" as workspace-configurable but doesn't
  pin down the mapping; documented as a conservative simplification, not a gap in the gate itself.
- The budget check (safety gate #9) compares against real `call_sessions.cost_paise`, which is
  always 0 for mock calls — real, working comparison logic on real data, trivially satisfied until
  Phase 9's usage/billing tracking gives non-mock calls an actual cost.
- Dynamic/query-based contact segments, and a full campaign-versions UI (beyond the snapshot
  written at launch), are **Scaffold**: the schema and snapshot exist, but there's no UI to browse
  past versions or define a segment by filter rather than a fixed contact list.

## Phase 6 — Business tools
- [x] Tool framework (definition, permission, idempotency, audit) — **Deep**. Execution engine
      (`jkr_db.tools_engine.execute_tool`) lives in `packages/db`, not any one service — shared
      verbatim by `services/voice-worker` (in-call tools) and `services/intelligence-worker`
      (post-call follow-up tools), same reasoning as the safety gate. Idempotent by construction
      (`idempotency_key` lookup short-circuits a replay rather than re-running), checks both the
      workspace-wide `ToolDefinition.is_enabled` and — when a caller passes `agent_version_id` — the
      per-agent-version `AgentTool.enabled` toggle from the new Agent Studio Tools tab. Every
      workspace auto-seeds the full 10-tool catalog (`services/api/app/modules/tools`, mirroring
      `providers_service.seed_default_accounts`); every new/cloned agent version auto-seeds
      `AgentTool` rows (all enabled, or copied from the source version when cloning). Added a new
      `tools:edit` RBAC permission via migration `056036cf0e79` (the existing `81ba970ac969` seed
      only shipped `tools:view`/`tools:view_audit`, nothing for the enable/disable action this
      phase needed — edited via a new migration, not in place, since `81ba970ac969` had already run).
- [x] Calendar/CRM/WhatsApp/callback mock tools — **Deep** for the six with real local side effects
      (`book_appointment`/`reschedule_appointment`/`cancel_appointment` → `appointments`;
      `create_human_callback` → `human_handoffs`; `send_whatsapp`/`send_sms` → `messages`) —
      **mock-only** and explicitly labeled as such in the Tools tab for the other four
      (`check_calendar_slots`, `create_crm_lead`, `update_crm_stage`, `send_email`), since there's
      no real calendar/CRM/email integration built this pass; they return a synthetic response and
      write nothing beyond the audit row. `book_appointment`'s date/time parsing
      (`jkr_db.tools_engine.parse_fuzzy_datetime`) is a deliberately forgiving best-effort parser
      (day-name/relative-day/time-of-day recognition, falling back to +3 days at 11:00), not real
      NLU — documented, not silently wrong, and 7 unit tests cover it directly.
- [x] Human handoff packet generation — **Deep**. A small keyword-based detector
      (`conversation_engine._wants_human_handoff`, spec §18) fires mid-call when the customer asks
      for a human, gated on the agent version's `ConversationPolicy.human_transfer_enabled`;
      creates a real `HumanHandoff` row via `create_human_callback` with a packet snapshotting
      `known_fields` and the triggering utterance, and the agent's spoken reply switches to a
      handoff acknowledgement instead of continuing the script. `book_appointment` gets the same
      real-trigger treatment: completing all required booking fields calls the tool automatically
      (spec §33 demo beats 13-15), not just marking the script "done." Intelligence-worker's
      post-call pipeline now *acts* on the `FollowUpTask` it creates rather than leaving it pending
      forever — `whatsapp` sends a real templated message and marks the task `sent`,
      `human_callback` creates a real handoff and marks it `completed`, `suppress` writes a real
      `SuppressionEntry` — since this pass has no task scheduler, "follow up later" is realized as
      "follow up now" (documented simplification; `reminder`/`close` genuinely have nothing to do
      yet and are left as-is).
- [x] Frontend — **Deep** for what exists: Agent Studio's Tools tab (`/app/agents/[agentId]/tools`,
      previously a ComingSoon stub) is a real per-agent-version enable/disable checklist against
      the live `AgentTool` state, with a badge distinguishing live-effect tools from mock-only
      ones. No dedicated tool-execution-log viewer or workspace-level tool-catalog management page
      this pass — **Scaffold**; the backend (`GET /tools`, `PATCH /tools/{id}`,
      `GET /tools/executions/by-call/{id}`) is ready for Phase 7's call detail page to surface
      execution history alongside turns/interruptions.

### Real bugs found and fixed while building/testing Phase 6 (both found by reasoning through the
### live data before running anything, not by the tests — kept here since they're the kind of gap
### that stays invisible until an agent actually tries to use a tool)
1. **A brand-new agent version couldn't use any tool at all** — `AgentTool` rows are how a tool
   gets enabled *for a specific agent version*, but nothing created them at agent/version creation
   time, so `list_agent_tools` (no matching row → defaults to `enabled: false`) reported every tool
   off on a freshly created agent, and the Tools tab would have shown everything unchecked out of
   the box. Would have silently broken the spec §33 demo's book_appointment beat on any new agent
   until an operator manually flipped every toggle. Fixed by seeding `AgentTool` (all enabled) in
   `agents.service.create_agent`, and in `create_version` either copying the source version's
   enablement state (clone) or seeding fresh (brand new version with no source).
2. **`execute_tool` checked the workspace-wide toggle but not the per-agent one** — the first
   version of the voice-worker triggers (book_appointment / create_human_callback) called
   `execute_tool` without ever passing which agent version was asking, so disabling a tool for one
   specific agent via the Tools tab UI would have had no effect on whether that agent could still
   use it — the UI would lie about what was actually enforced. Fixed by adding an optional
   `agent_version_id` parameter to `execute_tool` that additionally checks `AgentTool.enabled`
   (missing row = enabled, matching the seed default) and wiring `call_session.agent_version_id`
   through both call sites.

### Notes / deviations
- `required_permission` on each seeded `ToolDefinition` documents which workspace permission a
  human reviewing that tool's use should hold (spec §17) — it is not itself enforced as a gate on
  automatic in-call tool execution (the agent, not a human operator, is the one invoking it
  mid-call); it exists for future admin/audit UI and is real, seeded data, not a placeholder.
- Appointment/message/handoff tools require a real `contact_id`/`call_session_id` as appropriate
  (matching the schema's `NOT NULL` constraints) — a Test Lab call with no attached contact simply
  can't book a real appointment or send a real message; `book_appointment`'s trigger explicitly
  checks `call_session.contact_id is not None` and no-ops otherwise rather than crashing.

## Phase 7 — Operations UI
- [x] Live Call Console — **Deep**. `GET /calls/{id}/events` implements
      `docs/DECISIONS/0005-live-updates-via-sse-poll.md` for real: an SSE endpoint
      (`sse-starlette`) that polls `call_turns`/`interruption_events`/`call_events` every 500ms
      through a **fresh** `workspace_scoped_session` each tick (deliberately not the
      request-scoped session `workspace_db_for` hands back — that one is meant to commit once and
      close, not stay open for a whole streaming connection's lifetime and see stale snapshots),
      closing itself once the call reaches a terminal status. `/app/calls/live` lists in-progress
      calls and opens an `EventSource` (`withCredentials: true`, since apps/web:3000 and
      services/api:8000 are different origins) onto the selected one. Verified live end-to-end via
      raw `curl -N` against a real Test Lab call: streamed the greeting turn immediately, streamed
      the next turn + `call_ended` events after ending the call, and closed cleanly.
- [x] Call detail page (tabs + timeline) — **Deep**, single-page sections rather than literal tabs
      (transcript as chat bubbles, outcome, interruptions, tool executions) — reuses the `GET
      /calls/{id}` endpoint built in Phase 3 plus Phase 6's `GET /tools/executions/by-call/{id}`
      (extended to return `tool_name`, not just `tool_definition_id`, so the UI doesn't need a
      second round trip to label an execution). `/app/calls` lists every call with a status/outcome
      badge linking into it.
- [x] Follow-ups / handoffs / appointments pages — **Deep**. New `services/api/app/modules/operations`
      module (list + one action each): `/app/follow-ups` (mark complete), `/app/handoffs`
      (accept/resolve — reuses the `calls:transfer` permission, since accepting a handoff is
      operationally the same act as taking over a call), `/app/appointments` (cancel). All three
      read real Phase 6 data (FollowUpTask/HumanHandoff/Appointment) — verified live against the
      book_appointment and human-handoff calls exercised while testing Phase 6: the WhatsApp
      follow-up shows `sent`, the human-callback shows `pending` with the triggering utterance and
      an Accept button, the booked appointment shows `scheduled` with a Cancel button.

### Real bugs found and fixed while building/testing Phase 7
1. **A genuinely flaky test, caught by re-running it** — `test_simulate_connect_outcome_varies_by_attempt_number`
   (Phase 5) used `uuid.uuid4()` for `contact_id`, so `simulate_connect_outcome`'s hash-of-(contact,attempt)
   had a real (~0.15%) chance per test run of landing every one of 29 attempts in the 80%-wide
   "answered" bucket — which is exactly what happened on one run of the full suite. Not a logic bug
   (the function itself is fine and IS documented as deterministic specifically so tests don't need
   real randomness), but the test contradicted its own premise by seeding with real randomness.
   Fixed by switching to a fixed UUID and widening the attempt range to 100 (making a false failure
   astronomically unlikely rather than merely rare). A good reminder that "deterministic function,
   tested with random inputs" is a latent flake even when the function is correct.

## Phase 8 — Analytics
- [x] Business/call/conversation/provider analytics endpoints + dashboard — **Deep**. New
      `services/api/app/modules/analytics` — deliberately **no separate analytics/fact-table
      schema**: every number is a live aggregation query over `call_sessions`/`call_outcomes`/
      `quality_evaluations`/`call_latency_metrics`/`appointments`/`human_handoffs`/`revenue_events`,
      so a dashboard figure can never silently drift from what the rest of the product actually
      recorded. Four endpoints: `/analytics/overview` (business KPIs: connect rate, appointments
      booked, contacts reached, active campaigns, pending handoffs, revenue), `/analytics/calls`
      (status/outcome/lead-score breakdowns, avg duration, mock-vs-real split, a 4-stage
      dialed→connected→qualified→appointment_booked funnel), `/analytics/conversation-quality`
      (aggregates straight off `quality_evaluations`: avg overall score, disclosure-present rate,
      interruption-quality avg, human-review rate), `/analytics/providers` (latency by pipeline
      stage from real `call_latency_metrics`, provider account health). `/app/analytics` (real page,
      no charting library — CSS-width bars) plus the workspace dashboard's KPI cards, which were
      explicitly stubbed with "—" placeholders and an EmptyState pointing at "Phase 8" in the code
      itself — now wired to the same `analyticsApi.overview()` call. **Known limitation, honestly
      surfaced, not hidden**: `revenue_paise`/`revenue_event_count` are real queries against
      `revenue_events`, which nothing in the product writes to yet (no producer this pass) — they
      correctly show 0 rather than a fabricated number. Verified live: created book_appointment,
      human-callback, and unreachable calls in earlier phases' testing, confirmed the funnel,
      outcome breakdown, and quality averages all reflect them correctly through both
      `/app/analytics` and the dashboard.
- [x] Experiments (assignment + lift calc) — **Medium**, exactly as scoped: `services/api/app/modules/experiments`
      is a real, working A/B-test engine (create with 2+ variants incl. exactly one `control`,
      allocation percentages must sum to 100; start/stop; deterministic hash-bucket assignment
      keyed on `(experiment_id, contact_id)` — same "reproducible, not truly random" pattern as
      campaign-worker's `simulate_connect_outcome`, verified over 2000 samples to respect a
      configured 20/80 split within tolerance; conversion recording; lift-vs-control % calculation)
      — but nothing in `campaign-worker` or `voice-worker` calls `assign_contact` to actually vary
      agent behavior per variant during a real call, and there's no frontend page (no nav slot for
      it either — this pass's Analytics nav item is the dashboard, not experiments). Verified live
      via the API directly: created a 50/50 experiment, started it, assigned a real contact
      (deterministically bucketed into `short_greeting`), recorded a conversion, and confirmed
      `/experiments/{id}/lift` correctly computed a 100% conversion rate for that variant and
      correctly returned `lift_vs_control_pct: null` for the untested control (no assignments yet,
      not a fabricated number).

### Real bugs found and fixed while building/testing Phase 8
1. **Same flake pattern as Phase 7, ruled out proactively this time** — `_bucket_variant`'s test
   suite initially risked the identical "deterministic function tested with `uuid.uuid4()`"
   flakiness Phase 7 hit for `simulate_connect_outcome`. Written correctly from the start this
   time (fixed UUIDs, 2000-sample tolerance band for the allocation-weighting check) rather than
   discovered by a failing run — the earlier incident directly shaped how this one was written.

## Phase 9 — Compliance, billing, security
- [x] Compliance pages (consent/suppression/calling-hours/audit) — **Deep**. New
      `services/api/app/audit.py`: a single ASGI middleware (not per-route calls, per
      docs/SECURITY_AND_COMPLIANCE.md §9's explicit requirement) writes an `audit_logs` row for
      every successful (2xx) mutating request across every module — actor resolved from the
      session cookie, resource type/id parsed from the URL path, IP + request ID captured.
      **Deliberate, RLS-forced scope boundary**: only workspace-scoped actions are logged (every
      mutating route in this codebase already requires `?workspace_id=`) — platform-level actions
      (signup, login, workspace creation) are not, because `audit_logs` carries the same
      `tenant_isolation` RLS policy as every tenant table, and without an explicit `WITH CHECK`
      Postgres reuses `USING` for inserts too, so a `workspace_id IS NULL` row can never satisfy
      `workspace_id = current_setting(...)::uuid` (NULL never equals anything) under the
      non-superuser `jkr_app` role every service connects as — writing those would need the
      superuser connection reserved for migrations, deliberately not given to request handling.
      Doesn't capture per-field before/after diffs either (would need deep coupling to every
      module's ORM state) — captures who did what to which resource, which is what most audit
      consumption actually needs. New `services/api/app/modules/compliance` module surfaces this
      plus consent-purpose/suppression counts and the calling-hours policy on `/app/compliance`
      (previously a ComingSoon stub). Verified live: created a contact (audited, no resource_id —
      correct, the ID doesn't exist yet at request time) and toggled a tool definition (audited
      with the correct resource_id from the URL); a failed 409 pause-campaign request correctly
      produced no audit row.
- [x] Billing/usage tracking + budget limits — **Medium**, exactly as scoped. Real
      `usage_events` now has a real producer: every completed call writes a `telephony_seconds`
      event (`services/voice-worker/app/conversation_engine.py::end_session`) — previously the
      table existed but nothing wrote to it. `services/api/app/modules/billing` aggregates real
      usage by type plus per-campaign daily-budget spend (the exact same `call_sessions.cost_paise`
      query the safety gate's check #9 already enforces at dispatch time — one source of truth, not
      two). `/app/billing` and `/app/usage` (both previously ComingSoon) share one component. What's
      not built: invoicing, plan/subscription management, a persisted per-workspace budget (only
      per-campaign budgets exist in the schema).
- [x] Integrations (generic webhook + mock CRM deep; OAuth-based stubbed) — **Medium**, exactly as
      scoped. New `jkr_db.webhook_engine` (packages/db — shared with intelligence-worker, same
      reasoning as `safety_gate.py`/`tools_engine.py`): register an endpoint (SSRF-guarded URL,
      reusing the exact same guard knowledge-ingestion uses — extracted to `app/security.py` as
      `assert_public_host` so there's one implementation, not two), HMAC-sign every payload,
      deliver, record a `WebhookDelivery` row per attempt. Real trigger: intelligence-worker's
      pipeline fires `call.completed` after every call. "Mock CRM" isn't a separate connectable
      integration — `create_crm_lead`/`update_crm_stage` (Phase 6) already are that path, not
      duplicated here. OAuth-based integrations (Google Calendar/Sheets, Meta Lead Ads, WhatsApp,
      n8n) are catalog entries only, same inert-until-configured posture as the Google-login stub.
      `/app/integrations` (previously ComingSoon) lists the catalog and manages webhooks. Verified
      live end-to-end: registering `http://127.0.0.1:9999/hook` was correctly rejected by the SSRF
      guard; registering `https://httpbin.org/post` succeeded, and ending a real Test Lab call
      produced a genuine signed HTTP POST with a recorded `WebhookDelivery` row (a transient 503
      from httpbin.org itself, not a defect — the delivery mechanics up to and including a real
      response being received are what's being verified here).
      Moved `encrypt_secret`/`decrypt_secret` from `services/api/app/security.py` into
      `jkr_db.crypto` in the same pass (pure functions, no FastAPI coupling) so intelligence-worker
      can decrypt a webhook secret without duplicating the Fernet-derivation logic.
- [x] Security hardening pass — **Deep** for what applies to this codebase's actual surface,
      explicitly not for items with no real target to harden yet:
      - **Rate limiting**: new `services/api/app/rate_limit.py`, a Redis fixed-window limiter
        applied to `/auth/signup` and `/auth/login` (20 req/min/IP). Verified live: 20 requests
        through normally, then real `429`s.
      - **SSRF guard**: already existed for knowledge-ingestion (Phase 4); this phase reused the
        identical guard for webhook registration rather than writing a second one, and verified
        both call sites live.
      - **Input validation**: already enforced everywhere via Pydantic (reject-by-default) — no
        new work needed, confirmed still true.
      - **Webhook signing**: real (see Integrations above) — the doc's ask was for *outgoing*
        webhook HMAC signing, which now exists; there is no *incoming* webhook receiver in this
        pass (nothing calls into this product from an external system yet), so incoming-signature
        verification has no real target — not built, not pretended.
      - **Log redaction filter**: **explicitly not built, and explained why rather than silently
        skipped** — grep-verified that the entire Python codebase has exactly one application-level
        logging call (`app/audit.py`'s failure-path `logger.exception`, which logs only an HTTP
        method + path, never PII), so a redaction filter would have no real logging surface to
        prove itself against. Building one anyway would be untested, speculative infrastructure;
        recorded here as a deliberate call, to revisit once/if real application logging exists.
      - **Recording/transcript retention purge job**: still a carried-forward gap — would live in
        `integration-worker`, which this pass never builds as its own service (consistent with
        every earlier phase's honest scope notes on `integration-worker`).

## Phase 10 — Hardening
- [x] Seed data: `packages/db/jkr_db/seed.py` (`make seed`) — three fictional workspaces (Aaha
      Dental Care, Adarsh Educational Institutions, JKR Creatives), each with its own owner login
      (`owner@<slug>.demo` / `DemoPassword123!`), a published agent with business-specific
      greeting/disclosure/closing text (not generic placeholder copy — three genuinely different
      personas, languages, and objectives: book_appointment in Telugu-English, qualify_lead in
      Hindi-English, collect_feedback in English), one approved knowledge document with real
      mock-embedded chunks, two consented contacts, and a draft demo campaign. Idempotent (checks
      workspace slug before inserting; safe to re-run against an already-seeded database).
      Verified live, twice in a row (`[ok]` then `[skip]`), then logged in as the seeded Aaha
      Dental Care owner and confirmed the agent/knowledge/campaign are all real and usable — not
      just rows that exist but don't actually work together.
- [x] pytest unit/integration suite — 97 tests across `packages/db` (32), `services/api` (18),
      `services/voice-worker` (23), `services/intelligence-worker` (11), `services/campaign-worker`
      (13), all passing, `ruff check` clean across `packages`/`services`/`scripts`. Coverage spans
      every phase's core logic: RLS policy safety, phone normalization, tool-execution engine
      (idempotency, fuzzy date parsing), safety-gate bucketing/calling-hours, campaign dialer pure
      functions, TurnManager interruption classification, SpokenResponseFormatter, knowledge
      retrieval/extraction, post-call intelligence classification, experiment variant bucketing,
      audit-log resource parsing.
- [x] Playwright e2e (demo flow) — `tests/e2e` (new pnpm workspace member, `make e2e`): one spec
      driving signup → workspace creation → agent creation + publish → knowledge document → contact
      + consent → campaign creation + add contact → safety-gate dry-run, entirely through the real
      running UI (no mocked network layer). Deliberately stops before waiting on the async dialer
      loop to place and complete a mock call — `scripts/run_demo.py` proves that part faster and
      more reliably than a UI poll loop with no visible progress indicator would.
      **Real bug this caught that no amount of curl-based testing across the whole project could
      have**: the long-running Next.js dev server (up since Phase 1, survived ~10 hours and
      hundreds of hot-reloads across every later phase) had silently started 404ing on its own
      `_next/static/*` chunks. With no JS loaded, every form on the site was silently falling back
      to native browser form submission (a GET request with form fields as query params) instead
      of calling the API — invisible to any test that talks to the API directly, since the API
      itself was never at fault. Fixed by restarting the dev server with a cleared `.next` cache;
      documented here because it's a strong argument for why a real-browser test belongs in the
      suite even when API-level testing is extensive. **Operational gotcha found while chasing a
      recurrence of the same symptom**: running `pnpm --filter web build` (production build) while
      a `next dev` process is also running against the same `apps/web/.next` directory corrupts
      that directory for the live dev server — the two write to and read from it differently, and
      the dev server starts silently 404ing its own chunks again immediately afterward. Not a
      product bug; a verification-workflow note — run `next build` in isolation (or against a
      worktree/CI runner without a live dev server sharing the same `.next`), and restart the dev
      server (with `.next` cleared) afterward if one needs to keep running.
- [x] `make demo` manual walkthrough verified — `scripts/run_demo.py`: logs into the seeded Aaha
      Dental Care workspace, creates a fresh contact + campaign each run (so it's safely
      re-runnable), dry-runs the safety gate, launches, polls campaign-worker's dialer loop to
      completion, and confirms a real appointment was booked and a real WhatsApp follow-up was
      sent. Ran successfully twice in a row. Genuinely hit (and correctly navigated) the
      calling-hours check when run outside the workspace's 09:00–20:00 IST window — the script
      widens that one campaign's schedule for the demo run rather than skipping the check, so the
      safety gate's real behavior is what gets exercised, not a bypassed one.
- [ ] Platform admin section — **Scaffold** (not built this pass — no `/admin/*` routes or
      platform-cross-workspace views exist; `is_platform_super_admin`/`admin:platform_manage`
      exist in the RBAC model and are honored by every `require_permission` check, but there's no
      UI surface for a platform operator).
- [ ] Voice Benchmark Lab — **Scaffold** (not built this pass — spec §30's blind-review tooling has
      no schema, endpoint, or UI; would need its own comparison/scoring data model).

## Demo flow (spec §33) — actual end state, verified live
1. Log in (seeded owner or fresh signup) → 2. Workspace with real KPI dashboard → 3. Published
agent with tailored greeting/disclosure/closing → 4. Approved knowledge (real pgvector retrieval,
correctly refuses to guess below the confidence threshold) → 5. Campaign created, contact added →
6. Dry-run runs the real 10-check safety gate, shows would-dispatch/blocked-and-why per contact →
7. Launch → campaign-worker's dialer loop reserves the contact, runs the real safety gate again,
dispatches a mock call → 8. voice-worker's TurnManager + MockLLM run a real scripted conversation
(campaign calls auto-play a generic customer via campaign-worker; Test Lab calls take real typed
input) with real interruption classification and knowledge-grounded answers → 9. Completing the
booking script's fields calls the real `book_appointment` tool, which books a real `Appointment`
row → 10. Call ends → intelligence-worker's pipeline computes a rule-based summary/outcome/lead
score/quality evaluation from the real transcript, plans a follow-up, and immediately actions it
(a real signed `send_whatsapp` tool call) → 11. A generic webhook subscriber (if configured) gets a
real signed `call.completed` HTTP POST → 12. Analytics (`/app/analytics` and the dashboard) reflect
the real funnel/outcome/quality numbers, computed live from the same rows every other page reads —
no separate analytics copy to drift. Revenue attribution is the one genuine placeholder: the
`revenue_events` table and its analytics query are real, but nothing produces a `RevenueEvent` yet
(no real payment/CRM integration exists to attribute from) — correctly shows 0, not a fabricated
number.

## Known gaps at end of this pass
Kept honest and current rather than silently narrowed. Everything below is a deliberate, documented
scope boundary — not a bug, and not something claimed to work that doesn't.

- **`services/integration-worker` was never built as its own process.** The architecture and
  Makefile/docker-compose reference it (scheduled webhook retries, recording/transcript retention
  purge), but every real background job this pass needed (post-call intelligence, campaign
  dispatch) fit naturally into `intelligence-worker`/`campaign-worker` instead. Nothing currently
  needs a fourth worker process badly enough to justify standing one up speculatively.
- **No Dockerfiles** (`infra/docker/*.Dockerfile`) — every service has been built, tested, and
  demoed running natively (`uv run uvicorn`/`dramatiq`, `pnpm dev`) via the `dev-native` path the
  whole build, matching what the Makefile documents. `docker-compose.yml`'s service definitions
  reference Dockerfiles that don't exist; `make dev` (the Docker path) will not build until these
  are written.
- **Experiments has no frontend** and isn't wired into campaign dispatch to actually vary agent
  behavior per variant — the assignment/lift-calculation engine is real and tested (Phase 8,
  **Medium** tier as scoped), reachable only via its own API.
- **Dynamic/query-based contact segments** don't exist — segments are a fixed, named list of
  contact_ids (Phase 5); defining one by filter criteria is unbuilt.
- **Audit logging doesn't capture per-field before/after diffs**, and doesn't cover platform-level
  actions (signup, login, workspace creation) — both deliberate, documented boundaries of the
  Phase 9 middleware (see `app/audit.py`'s docstring for the RLS reasoning on the latter).
- **No log-redaction filter** — not built because grep-verified there is currently no
  PII-bearing application log line anywhere in the codebase to redact (Phase 9); worth building
  the moment that stops being true.
- **Recording/transcript retention purge job** doesn't run anywhere (would live in
  `integration-worker`, per the gap above) — `recording_retention_days`/`transcript_retention_days`
  are real, configurable workspace settings that nothing currently enforces.
- **OAuth-based integrations** (Google Calendar/Sheets, Meta Lead Ads, WhatsApp Business, n8n) and
  Google login are catalog/UI entries only, inert without real OAuth credentials — by design
  (spec's own "credentials that can't be completed locally" rule), not an oversight.
- **No real telephony, STT, LLM, or TTS provider is wired in** — every call this whole build ever
  ran was mock, and `ENABLE_LIVE_CALLS` was never exercised as true. This is the central safety
  property the entire spec asked for, not a limitation: no real outbound call was ever placed, to
  anyone, at any point in this build.
- **Platform admin section and Voice Benchmark Lab** — schema/routes/UI not built (see Phase 10
  checkboxes above).
