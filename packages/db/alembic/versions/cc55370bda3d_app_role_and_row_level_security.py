"""app role and row level security

Revision ID: cc55370bda3d
Revises: 7d401bf9df66
Create Date: 2026-08-07 11:05:52.487558

Implements docs/DECISIONS/0004-tenant-isolation.md: a non-superuser
application role (`jkr_app`) that every service connects as, and a
`tenant_isolation` RLS policy on every workspace-owned table, keyed off
`current_setting('app.current_workspace_id')` which `jkr_db.session.
workspace_scoped_session` sets via `SET LOCAL` at the start of each
request/job transaction.

Tables with a NOT NULL workspace_id use a strict equality policy. The three
tables with a nullable workspace_id (audit_logs, security_events,
feature_flags — platform-level rows coexist with workspace rows there) use
the same equality policy, which means a workspace-scoped session cannot see
the platform-level (NULL workspace_id) rows; those are only visible via the
superuser migrations/admin connection. That is the intended behavior: a
workspace operator's audit log view should never include platform-wide
entries.

`workspace_members` is the one exception to the plain equality policy: a
caller must be able to list every workspace *they* belong to before any one
workspace is "active" (the workspace switcher, `GET /workspaces`, and
workspace creation all need this), which a single-workspace-scoped session
can never satisfy. It gets `workspace_id = current_workspace_id OR user_id =
current_user_id` instead, backed by a second session variable
(`app.current_user_id`, set by `jkr_db.session.user_scoped_session`). This
still blocks a user from reading another user's row in a workspace neither
session variable names; the two app-layer checks that matter
(`require_membership_with_permission` resolving the caller's own row, and
route handlers only calling workspace-wide member listing after that check
passes) are documented next to `workspace_db_from_path` in
services/api/app/db.py.
"""
import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cc55370bda3d'
down_revision: str | None = '7d401bf9df66'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every table with a workspace_id column, generated from information_schema
# against the schema this migration follows (see docs/DATA_MODEL.md §2), MINUS
# workspace_members which gets the special dual-condition policy below.
TENANT_TABLES = [
    "agent_tools", "agent_versions", "agents", "appointments", "audit_logs",
    "call_events", "call_latency_metrics", "call_outcomes", "call_participants",
    "call_recordings", "call_sessions", "call_summaries", "call_transcripts",
    "call_turns", "campaign_attempts", "campaign_contacts", "campaign_schedules",
    "campaign_versions", "campaigns", "consent_events", "contact_fields",
    "contact_tags", "contacts", "conversation_policies", "conversion_events",
    "experiment_assignments", "experiment_variants", "experiments",
    "extracted_fields", "feature_flags", "follow_up_tasks", "human_handoffs",
    "integration_credentials", "integrations", "interruption_events", "invoices",
    "knowledge_chunks", "knowledge_collections", "knowledge_document_versions",
    "knowledge_documents", "knowledge_reviews", "messages", "phone_numbers",
    "pronunciation_entries", "provider_accounts", "provider_costs",
    "provider_credentials", "provider_health", "quality_evaluations",
    "retrieval_events", "retry_jobs", "revenue_events", "security_events",
    "segment_members", "segments", "suppression_entries", "tool_definitions",
    "tool_executions", "usage_events", "voice_personas", "webhook_deliveries",
    "webhook_endpoints",
]

USER_OR_WORKSPACE_SCOPED_TABLES = ["workspace_members"]

APP_ROLE = "jkr_app"


def upgrade() -> None:
    app_db_password = os.environ.get("APP_DB_PASSWORD", "jkr_app_local_dev")

    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{app_db_password}'
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
        END
        $$;
        """
    )
    db_name = os.environ.get("POSTGRES_DB", "jkr_ai_calling")
    op.execute(f"GRANT CONNECT ON DATABASE {db_name} TO {APP_ROLE};")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE};")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE jkr IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE jkr IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE};"
    )

    # NULLIF(..., '') matters here, not just belt-and-suspenders: Postgres
    # resets an unprivileged custom GUC to '' (empty string), not NULL, once
    # it has been `SET LOCAL`'d and committed even a single time on a given
    # physical connection — current_setting(name, true) alone only returns
    # NULL for a GUC that has *never* been touched on that connection. Under
    # connection pooling, a connection previously used by a differently-scoped
    # session (e.g. user_scoped_session, which never sets
    # app.current_workspace_id) carries that '' residue forward, and casting
    # '' to uuid raises rather than comparing as NULL. Confirmed live: a
    # SET LOCAL x = '...'; COMMIT; cycle leaves current_setting('x', true)
    # equal to '' (not NULL) for the rest of that connection's life.
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid);
            """
        )

    for table in USER_OR_WORKSPACE_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (
                workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
                OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
              );
            """
        )


def downgrade() -> None:
    for table in TENANT_TABLES + USER_OR_WORKSPACE_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};")
    op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {APP_ROLE};")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE};")
