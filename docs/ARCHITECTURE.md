# Architecture

## 1. Service topology

```
                         ┌─────────────────────┐
                         │   apps/web (Next.js) │
                         │  dashboards, studio,  │
                         │  live console, admin  │
                         └──────────┬───────────┘
                                    │ REST + SSE (cookie session)
                                    ▼
                         ┌─────────────────────┐
                         │   services/api        │  FastAPI — the only service
                         │   (business API)       │  the browser ever talks to
                         └──┬───────┬───────┬────┘
                             │       │       │
              enqueue jobs   │       │       │ HTTP (internal)
             (Redis/Dramatiq)│       │       │
       ┌─────────────────────┘       │       └───────────────────────┐
       ▼                             ▼                               ▼
┌─────────────────┐        ┌──────────────────┐            ┌──────────────────┐
│ campaign-worker   │        │ intelligence-worker│            │ integration-worker│
│ dialer loop,       │        │ post-call pipeline  │            │ webhooks, calendar/│
│ safety gate,       │        │ (summary, outcome,  │            │ CRM/WhatsApp sync  │
│ retries            │        │ scoring, follow-up) │            │                    │
└─────────┬─────────┘        └──────────────────┘            └──────────────────┘
          │ dispatch (HTTP)
          ▼
┌─────────────────────┐
│  voice-worker         │  FastAPI — its own process, its own failure domain
│  TurnManager,          │  never writes campaign state directly, only call_* tables
│  provider adapters,    │
│  SSE per call session  │
└─────────────────────┘

        all Python services import the shared schema from packages/db (SQLAlchemy + Alembic)
        Postgres (+pgvector) ◄──────────────────────────────────────────────┘
        Redis (queues, locks, idempotency keys, sessions)
        MinIO / S3-compatible object storage (recordings, exports, documents)
```

**Why `voice-worker` is a separate process from `services/api`:** a crash, stuck event loop, or
provider outage in real-time call handling must never block campaign CRUD, dashboard reads, or
auth. The API and voice-worker share only the database schema (`packages/db`), not an in-process
call stack. A `voice-worker` crash mid-call surfaces as an incomplete `call_sessions` row that
campaign-worker's reconciliation step can retry — it cannot corrupt `campaign_contacts` state,
because campaign-worker only transitions a contact to a terminal state on an explicit,
idempotent call-outcome callback.

## 2. Bounded modules (services/api/app/modules/*)

Each module owns its slice of `packages/db` models, exposes a FastAPI `router.py`, and keeps
business rules in `service.py` (never in the router). Modules: `identity`, `tenancy`, `agents`,
`providers`, `contacts`, `campaigns`, `compliance`, `knowledge`, `tools`, `calls`, `intelligence`,
`analytics`, `billing`, `integrations`, `admin`. Cross-module calls go through each module's
`service.py` functions, never through raw ORM queries reaching into another module's tables —
this is what keeps "a campaign retry must not create duplicate calls" and similar invariants
enforceable in one place.

## 3. Request flow example — starting a mock outbound call from a campaign

1. Browser calls `POST /campaigns/{id}/launch` on `services/api` (campaigns module).
2. Campaigns module flips `campaigns.status = active`, enqueues a Dramatiq message to
   `campaign-worker`.
3. `campaign-worker`'s dialer loop reads `campaign_contacts` in `pending` state, and for each one
   runs the **safety gate** (`docs/SECURITY_AND_COMPLIANCE.md` §2) — this is the only path by
   which a call is ever dispatched.
4. On success, campaign-worker calls `POST /internal/voice-sessions` on `voice-worker` with the
   agent config snapshot, contact, and campaign objective. `voice-worker` creates a
   `call_sessions` row and returns a `call_id` immediately (async).
5. `voice-worker` runs the conversation loop (§`docs/VOICE_ARCHITECTURE.md`), persisting
   `call_turns` / `call_events` / `interruption_events` / `call_latency_metrics` as it goes.
6. Browser (or the Live Console) subscribes to `GET /calls/{id}/events` (SSE) on `services/api`,
   which tails the same tables `voice-worker` is writing — the browser never talks to
   `voice-worker` directly, keeping the "single service the browser trusts" boundary intact.
7. On call completion, `voice-worker` writes `call_outcomes` and publishes a completion event;
   `campaign-worker` picks it up, transitions the `campaign_contacts` row (idempotently, keyed on
   `call_id`), and applies retry policy if the outcome warrants it.
8. Completion also enqueues `intelligence-worker` for the post-call pipeline
   (summary → extraction validation → outcome classification → lead scoring → quality evaluation
   → follow-up planning → revenue attribution).

## 4. Frontend

Next.js App Router, TypeScript strict. Server Components fetch initial data from `services/api`
using a request-scoped session cookie; Client Components handle the Live Console, Test Lab, and
any form with optimistic/interactive state. `packages/sdk` is a small typed fetch client (not a
full OpenAPI-codegen pipeline, to keep the build deterministic without a network-dependent
generation step) whose request/response shapes come from `packages/contracts` (Zod schemas
shared between client-side validation and the SDK's runtime parsing).

## 5. Data layer

- PostgreSQL 16 + `pgvector` extension — structured data and embeddings in one database for this
  build (an adapter boundary exists in `knowledge` module for swapping in Qdrant later).
- Redis — Dramatiq broker, distributed locks (dialer duplicate-call prevention), idempotency key
  store, session store.
- MinIO (S3-compatible) — recordings, knowledge source uploads, exports.

## 6. Tenant isolation (defense in depth)

1. **Application layer** — every module's repository functions require a `workspace_id` and
   filter on it; there is no "list all" query path that skips this.
2. **Database layer** — Postgres Row-Level Security policies on every tenant-owned table, keyed
   off `current_setting('app.current_workspace_id')`, set via `SET LOCAL` at the start of each
   request transaction in `services/api`'s DB session dependency. See
   `docs/DECISIONS/0004-tenant-isolation.md`.

## 7. Observability

Structured JSON logs (`packages/observability` provides the Python logger config and a TS
equivalent for `apps/web`/Node contexts), a request ID + call ID + trace ID threaded through every
log line, and OpenTelemetry instrumentation on `services/api` and `voice-worker` exporting to an
OTLP collector (configurable; no-op by default in local dev). PII (full phone numbers, transcript
text, credentials) is never placed in log lines — see `docs/SECURITY_AND_COMPLIANCE.md` §6.

## 8. Voice runtime abstraction

`voice-worker` depends only on interfaces (`TelephonyProvider`, `SpeechToTextProvider`,
`LLMProvider`, `TextToSpeechProvider`, `MediaRuntime`) defined in `packages/db`-adjacent shared
code (`services/voice-worker/app/providers/base.py`). The default `MediaRuntime` implementation
is `MockMediaRuntime` (text-simulated, no external dependency). A `LiveKitMediaRuntime` adapter
stub exists so the platform can move to real LiveKit/SIP without touching `TurnManager` or the
conversation engine. See `docs/VOICE_ARCHITECTURE.md` and `docs/DECISIONS/0002-voice-runtime.md`.
