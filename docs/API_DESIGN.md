# API Design

## 1. Conventions

- Base path `/api/v1`. JSON in/out. `services/api` is the only backend surface the browser talks
  to (see `docs/ARCHITECTURE.md` §1).
- Auth: httpOnly secure session cookie (`jkr_session`), CSRF double-submit token for
  state-changing requests from the browser. Service-to-service calls (campaign-worker →
  voice-worker, etc.) use a signed internal service token, never the user session.
- Every response includes `X-Request-Id`. Call-related responses include `X-Call-Id` when
  applicable.
- Pagination: cursor-based (`?cursor=&limit=`), default `limit=25`, max `100`.
- Errors: `{ "error": { "code": "...", "message": "...", "details": {...} } }` with matching HTTP
  status; validation errors use `422` with a `details.fields` map.
- All list endpoints accept `workspace_id` implicitly from the session's active workspace — it is
  never a client-supplied filter that can widen scope.
- Idempotent POSTs (call dispatch, tool execution) accept an `Idempotency-Key` header; the server
  is the source of truth for the key when the client omits it (deterministic key derivation per
  `docs/DATA_MODEL.md` §3).

## 2. Route groups (implemented this pass unless noted)

```
/auth            POST /login, POST /logout, POST /signup, GET /me, POST /oauth/google (stub)
/workspaces      GET, POST, GET/{id}, PATCH/{id}, POST/{id}/members, PATCH .../members/{id}

/agents          GET, POST, GET/{id}, PATCH/{id}, POST/{id}/versions, POST/{id}/publish,
                 POST/{id}/test

/providers       GET /catalog, GET/POST /accounts, POST /accounts/{id}/health-check

/campaigns       GET, POST, GET/{id}, PATCH/{id}, POST/{id}/validate, POST/{id}/dry-run,
                 POST/{id}/launch, POST/{id}/pause, POST/{id}/resume, POST/{id}/cancel

/contacts        GET, POST, POST /import, GET/{id}, PATCH/{id}, POST/{id}/suppress
/segments        GET, POST, GET/{id}

/calls           GET, POST /test (Test Lab), POST /outbound (manual dispatch, still gated),
                 GET/{id}, POST/{id}/end, POST/{id}/transfer, POST/{id}/takeover,
                 GET/{id}/events (SSE), GET/{id}/transcript

/knowledge       GET/POST /documents, POST /websites, POST /documents/{id}/process,
                 POST /documents/{id}/approve, POST /search

/tools           GET /definitions, GET /executions (audit view)
/appointments    GET, POST, PATCH/{id}
/handoffs        GET, POST, POST/{id}/resolve
/follow-ups      GET, POST, PATCH/{id}

/analytics       GET /overview, /revenue, /conversations, /providers, /experiments
/compliance      GET/POST /consent, GET/POST /suppression, GET/PATCH /calling-hours, GET /audit
/billing         GET /usage, GET /invoices, GET/PATCH /limits
/integrations    GET, POST, GET/{id}, POST/{id}/test, DELETE/{id}

/webhooks        POST /telephony/{provider}, POST /whatsapp, POST /crm/{integration},
                 POST /meta   (all signature-verified, see SECURITY_AND_COMPLIANCE.md)

/admin           GET /workspaces, /providers, /usage, /system-health   (platform-admin only)
```

Full request/response schemas are defined as Pydantic models colocated with each module's
`schemas.py` and exported to the OpenAPI doc FastAPI generates at `/api/v1/openapi.json`;
`packages/contracts` mirrors the shapes that the frontend needs as Zod schemas (hand-kept in
sync for this pass — see `docs/DECISIONS/0001-tooling-and-monorepo.md` for why full codegen was
deferred).

## 3. Live updates

`GET /calls/{id}/events` is a Server-Sent Events stream. `services/api` polls `call_events` /
`call_turns` for the given `call_id` at a ~500ms interval and forwards new rows as SSE `event:`
frames (`turn`, `state`, `tool`, `knowledge`, `interruption`, `latency`, `ended`). This is a
deliberate simplification over a dedicated pub/sub layer — see
`docs/DECISIONS/0005-live-updates-via-sse-poll.md` for the tradeoff and upgrade path.

## 4. Webhook signing

Outgoing webhooks (to a client's generic webhook endpoint or n8n) are signed with an
HMAC-SHA256 over the raw body using a per-integration secret, sent as `X-JKR-Signature:
sha256=<hex>` plus `X-JKR-Timestamp`; receivers are expected to reject requests outside a 5
minute window to prevent replay. Incoming webhooks (`/webhooks/*`) verify the sending platform's
signature scheme (e.g. Meta's `X-Hub-Signature-256`) before the payload is trusted.
