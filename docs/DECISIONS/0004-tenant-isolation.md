# ADR-0004: Two-layer tenant isolation (app filtering + Postgres RLS)

## Status
Accepted

## Context
Spec §24/§27 requires tenant isolation "at both application layer and database layer" with RLS
"where practical."

## Decision
Every tenant-owned table gets a `workspace_id` column, a btree index on it, and an RLS policy:
```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <table>
  USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid);
```
`services/api`'s DB session dependency issues `SET LOCAL app.current_workspace_id = '<id>'` at the
start of every request transaction (`jkr_db.session.workspace_scoped_session`), derived from the
authenticated session's active workspace — never from a client-supplied header/query param.
Background workers (`campaign-worker`, `intelligence-worker`, `integration-worker`) set the same
session variable per job, derived from the job payload's `workspace_id`. The database role these
services connect as (`jkr_app`) is **not** `BYPASSRLS` — verified live, not just configured (see
`docs/IMPLEMENTATION_CHECKLIST.md` Phase 1). A separate, more privileged superuser role (`jkr`,
used only by migrations) can bypass RLS entirely — that role is never used by a running service.

One table, `workspace_members`, cannot use the plain single-workspace policy: a caller must be
able to list every workspace *they* belong to before any one workspace is "active" (workspace
switcher, `GET /workspaces`, workspace creation), which a policy scoped to one
`app.current_workspace_id` can never satisfy. It carries `workspace_id = ... OR user_id =
NULLIF(current_setting('app.current_user_id', true), '')::uuid` instead, backed by a second
session variable set by `jkr_db.session.user_scoped_session`. The application-layer check that
makes this safe (a caller only ever sees their *own* row via the `user_id` branch unless a
workspace-scoped session has already confirmed their membership) is documented next to
`workspace_db_from_path` in `services/api/app/db.py`.

**The `NULLIF(..., '')` is load-bearing, not defensive styling** — this was a real bug caught live
during Phase 1 build/testing, not a hypothetical: Postgres resets an unprivileged custom GUC
(`app.*` namespace, never declared in `postgresql.conf`) to `''` (empty string), **not** `NULL`,
after it has been `SET LOCAL`'d and the transaction has committed even once on a given physical
connection — `current_setting(name, true) IS NULL` is only true for a GUC that has *never* been
touched on that connection at all. Under `services/api`'s pooled `AsyncEngine`
(`pool_size=10`), a physical connection previously used for a `user_scoped_session` (which never
touches `app.current_workspace_id`) gets reused later for an ordinary `workspace_scoped_session`
request; without the `NULLIF` guard, the leftover `''` from the *other* variable fails to cast to
`uuid` and the query errors outright rather than merely (harmlessly) failing to match. Confirmed
by direct psql reproduction: `SET LOCAL x = '...'; COMMIT;` then, in a fresh transaction on the
same session, `current_setting('x', true) IS NULL` returns `false` and the value is `''`. Every
custom-GUC-based RLS policy in this codebase must use `NULLIF(current_setting(...), '')`, never a
bare `current_setting(...)::uuid` — this is enforced by convention (this ADR) since Postgres gives
no schema-level way to make the unguarded form a hard error.

Application-layer filtering (every repository function requires and applies `workspace_id`) is
kept as the first line of defense rather than relying on RLS alone, so a bug is caught by a test
against the ORM layer before it would ever reach the database boundary.

## Consequences
Every new table added after this pass must remember both the column and the policy — a
migration-time checklist item, and a test (`tests/integration/test_tenant_isolation.py`) that
enumerates all tables with `workspace_id` and asserts each has RLS enabled, so a forgotten policy
fails CI rather than shipping silently.
