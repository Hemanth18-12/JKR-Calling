# Security & Compliance

## 1. No real calls by default

`ENABLE_LIVE_CALLS` env var defaults to `false`. Every workspace defaults every provider account
to `mock`. Even with a real telephony provider configured, dialing a real number requires **all**
of: `ENABLE_LIVE_CALLS=true`, `APP_ENV != "local"` or the number present in
`AUTHORIZED_TEST_NUMBERS`, an `active` campaign, and valid provider credentials. See
`docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md`.

## 2. Outbound safety gate (`campaigns` module `service.py::run_safety_gate`)

Executed for every contact before dispatch, in this order (first failure short-circuits and
records the reason on `campaign_attempts`):

1. Campaign status is `active`
2. Contact status is dispatchable (not already `dialing`/`completed`/`suppressed`)
3. Consent: an unexpired `consent_events` row covering the campaign's purpose category
4. Phone number passes E.164 validation/normalization (`packages/db` shared util,
   `phonenumbers`-backed)
5. Not present in `suppression_entries` for this workspace
6. Within the campaign's configured calling-hours window (workspace timezone aware)
7. `attempt_count < campaign.max_attempts`
8. No other dispatch in flight for this `(campaign_id, contact_id)` — Redis lock
9. Workspace usage is within its balance/budget limit
10. Workspace/campaign rate limit not exceeded (Redis token bucket)

Only after all ten pass: reserve the contact (status → `reserved`), generate the deterministic
idempotency key, and dispatch. Any failure is logged as a structured `DryRunResult`/attempt
record — never silently dropped — so the campaign results view always explains "why wasn't this
contact called."

## 3. Consent & suppression

- A `do_not_call` / opt-out signal (spoken, WhatsApp, or manual) takes effect **immediately** —
  it's written synchronously to `suppression_entries` before the triggering call/flow continues,
  not queued.
- No retry, schedule, or campaign relaunch can call a suppressed contact; the safety gate checks
  suppression on every attempt, not just at campaign launch.
- Silence is never treated as consent — a `consent_events` row requires an explicit source
  (signed form, recorded verbal opt-in reference, checkbox event) and purpose category.

## 4. AI disclosure

Every agent persona's opening script is validated at publish time
(`agents.service.py::validate_disclosure`) to contain a disclosure clause before any information
gathering — publishing an agent version without one is a blocking validation error, not a
warning. The quality evaluator (`intelligence` module) also checks disclosure presence against
the actual transcript after each call and flags its absence as a quality failure requiring human
review, catching cases where the agent deviated from script.

## 5. Tenant isolation & RBAC

See `docs/ARCHITECTURE.md` §6 for the two-layer (app + RLS) model. Roles (`platform_super_admin`,
`jkr_admin`, `workspace_owner`, `workspace_admin`, `campaign_manager`, `sales_manager`,
`agent_operator`, `analyst`, `viewer`) map to a `role_permissions` table checked by a FastAPI
dependency (`require_permission("campaigns:launch")`-style) on every mutating route.

## 6. Data protection

- Argon2id password hashing; Redis-backed server-side sessions, httpOnly + secure + SameSite=Lax
  cookies.
- Provider credentials encrypted at rest (Fernet, key from `CREDENTIALS_ENCRYPTION_KEY`env var —
  documented as a TODO to move to a KMS in production).
- Recordings and exports served via short-lived signed URLs, never public object storage paths.
- Structured logs never include: API keys, full phone numbers (masked to `+91••••••1234`
  server-side before logging), transcript text, customer PII fields — enforced by a logging
  filter (`packages/observability`) that redacts a fixed set of field names regardless of call
  site.
- Phone numbers are masked in the UI by default; viewing an unmasked number requires a permission
  (`contacts:view_unmasked`) and is itself an audit-logged action.
- Recording/transcript retention is a per-workspace configurable number of days (default 90),
  enforced by a scheduled purge job in `integration-worker`.

## 7. Input & transport safety

- All request bodies validated by Pydantic models (reject-by-default, no passthrough dicts).
- Website-crawling for knowledge ingestion (`knowledge` module) resolves the target host and
  rejects RFC1918/loopback/link-local ranges before fetching (SSRF guard), and only follows
  redirects within the same registrable domain.
- File uploads for knowledge ingestion are validated by content-sniffed MIME type (not just
  extension) and size-capped; a `malware_scan_status` column exists on `knowledge_documents` with
  a pluggable scan hook (no-op scanner by default, documented as a TODO for a real AV integration
  in production).
- Incoming webhooks verify the source platform's signature before the payload is parsed into
  domain objects. Outgoing webhooks are HMAC-signed (`docs/API_DESIGN.md` §4).
- Rate limiting (Redis token bucket) on auth endpoints and on the public webhook endpoints.

## 8. Compliance posture (India-first)

Configurable per workspace: consent policy text, calling-hours window, campaign purpose
categories, suppression list, retention days, recording notice text, AI disclosure script
requirement, data export/deletion request handling. A `legal_review_checklist` boolean set on a
campaign (`campaigns.legal_reviewed_at`) is required before a campaign can be switched to a real
(non-mock) provider — this is enforced in the safety gate, not just presented as UI copy.

The platform will not: hide AI identity, ignore opt-out, dial without a consent basis,
impersonate protected identities (doctors/banks/government) — the persona builder blocks a
`business_identity` value matching a denylist of protected-identity terms unless the workspace is
independently verified (`workspaces.identity_verified_at`, a manual JKR-admin action, not
self-serve) — use unauthorized voice cloning, make unsupported medical/financial/legal claims (the
knowledge answer policy in `docs/VOICE_ARCHITECTURE.md` §5 refuses to answer outside approved
knowledge for these categories), or continue after repeated refusal (three consecutive
not-interested/refusal signals in one call force `next_best_action = close_conversation`).

## 9. Audit logging

Every mutating action across every module writes an `audit_logs` row
(`actor_id, workspace_id, action, resource_type, resource_id, before, after, ip, request_id`) via
a shared decorator/dependency, not ad hoc per-route calls — this is what keeps §36's "all
important actions must be auditable" true by construction rather than by discipline.
