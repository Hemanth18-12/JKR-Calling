"""seed rbac catalog

Revision ID: 81ba970ac969
Revises: cc55370bda3d
Create Date: 2026-08-07 11:09:41.564743

Seeds the fixed platform role catalog (spec §4) and a permission catalog used
by `require_permission(...)` dependencies across services/api/app/modules/*.
This is reference/lookup data, not demo data — every environment (including
production) needs it, unlike the three demo workspaces seeded separately by
`jkr_db.seed` (docs/IMPLEMENTATION_CHECKLIST.md Phase 10).
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '81ba970ac969'
down_revision: str | None = 'cc55370bda3d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    ("platform_super_admin", "Platform Super Admin", "Full cross-workspace platform access.", True),
    ("jkr_admin", "JKR Admin", "JKR staff supporting client workspaces.", True),
    ("workspace_owner", "Workspace Owner", "Full control of a single workspace, including billing.", False),
    ("workspace_admin", "Workspace Admin", "Manages a workspace short of billing/ownership changes.", False),
    ("campaign_manager", "Campaign Manager", "Builds and launches campaigns.", False),
    ("sales_manager", "Sales Manager", "Manages contacts and handles handoffs/appointments.", False),
    ("agent_operator", "Agent Operator", "Builds and tests agents and knowledge.", False),
    ("analyst", "Analyst", "Read-only analytics and reporting access.", False),
    ("viewer", "Viewer", "Read-only access across the workspace.", False),
]

# (key, module, description)
PERMISSIONS = [
    ("workspaces:view", "tenancy", "View workspace settings"),
    ("workspaces:manage", "tenancy", "Edit workspace settings"),
    ("workspaces:manage_members", "tenancy", "Invite/remove workspace members"),
    ("agents:view", "agents", "View agents and versions"),
    ("agents:create", "agents", "Create agents"),
    ("agents:edit", "agents", "Edit agent versions"),
    ("agents:publish", "agents", "Publish an agent version"),
    ("agents:test", "agents", "Use the Agent Studio Test Lab"),
    ("agents:delete", "agents", "Archive/delete agents"),
    ("campaigns:view", "campaigns", "View campaigns"),
    ("campaigns:create", "campaigns", "Create campaigns"),
    ("campaigns:edit", "campaigns", "Edit campaign configuration"),
    ("campaigns:validate", "campaigns", "Run campaign dry-run validation"),
    ("campaigns:launch", "campaigns", "Launch/resume a campaign (safety-critical)"),
    ("campaigns:pause", "campaigns", "Pause a campaign"),
    ("campaigns:cancel", "campaigns", "Cancel a campaign"),
    ("contacts:view", "contacts", "View contacts (masked phone numbers)"),
    ("contacts:view_unmasked", "contacts", "View unmasked phone numbers (audit-logged)"),
    ("contacts:create", "contacts", "Create/import contacts"),
    ("contacts:edit", "contacts", "Edit contact records"),
    ("contacts:suppress", "contacts", "Add a suppression entry"),
    ("calls:view", "calls", "View call sessions, transcripts, recordings"),
    ("calls:test", "calls", "Start a Test Lab / mock call"),
    ("calls:outbound_dispatch", "calls", "Manually dispatch an outbound call"),
    ("calls:transfer", "calls", "Transfer a live call"),
    ("calls:takeover", "calls", "Take over a live call as a human operator"),
    ("calls:end", "calls", "End a live call"),
    ("knowledge:view", "knowledge", "View knowledge documents"),
    ("knowledge:create", "knowledge", "Upload/create knowledge documents"),
    ("knowledge:edit", "knowledge", "Edit knowledge documents"),
    ("knowledge:approve", "knowledge", "Approve/reject knowledge content"),
    ("knowledge:delete", "knowledge", "Archive/delete knowledge documents"),
    ("tools:view", "tools", "View tool definitions"),
    ("tools:view_audit", "tools", "View tool execution audit log"),
    ("analytics:view", "analytics", "View analytics dashboards"),
    ("compliance:view", "compliance", "View compliance settings and audit log"),
    ("compliance:manage", "compliance", "Edit consent/suppression/calling-hours policy"),
    ("billing:view", "billing", "View usage and invoices"),
    ("billing:manage", "billing", "Edit budgets and payment settings"),
    ("integrations:view", "integrations", "View integrations"),
    ("integrations:manage", "integrations", "Connect/configure integrations"),
    ("admin:platform_manage", "admin", "Platform admin console access"),
]

# role_key -> list of permission keys
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "platform_super_admin": [p[0] for p in PERMISSIONS],
    "jkr_admin": [p[0] for p in PERMISSIONS],
    "workspace_owner": [p[0] for p in PERMISSIONS if p[0] != "admin:platform_manage"],
    "workspace_admin": [
        p[0] for p in PERMISSIONS
        if p[0] not in ("admin:platform_manage", "billing:manage")
    ],
    "campaign_manager": [
        "workspaces:view", "agents:view", "campaigns:view", "campaigns:create", "campaigns:edit",
        "campaigns:validate", "campaigns:launch", "campaigns:pause", "campaigns:cancel",
        "contacts:view", "contacts:create", "contacts:edit", "contacts:suppress",
        "calls:view", "calls:test", "knowledge:view", "analytics:view", "compliance:view",
    ],
    "sales_manager": [
        "workspaces:view", "contacts:view", "contacts:view_unmasked", "contacts:create", "contacts:edit",
        "contacts:suppress", "calls:view", "calls:transfer", "calls:takeover", "campaigns:view",
        "analytics:view", "compliance:view",
    ],
    "agent_operator": [
        "workspaces:view", "agents:view", "agents:create", "agents:edit", "agents:publish",
        "agents:test", "knowledge:view", "knowledge:create", "knowledge:edit", "knowledge:approve",
        "calls:view", "calls:test", "tools:view",
    ],
    "analyst": [
        "workspaces:view", "agents:view", "campaigns:view", "contacts:view", "calls:view",
        "knowledge:view", "analytics:view", "compliance:view",
    ],
    "viewer": [
        "workspaces:view", "agents:view", "campaigns:view", "contacts:view", "calls:view",
        "knowledge:view", "analytics:view",
    ],
}


def upgrade() -> None:
    conn = op.get_bind()

    for key, name, description, is_platform_role in ROLES:
        conn.execute(
            sa.text(
                """
                INSERT INTO roles (id, key, name, description, is_platform_role, created_at, updated_at)
                VALUES (:id, :key, :name, :description, :is_platform_role, now(), now())
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"id": uuid.uuid4(), "key": key, "name": name, "description": description, "is_platform_role": is_platform_role},
        )

    for key, module, description in PERMISSIONS:
        conn.execute(
            sa.text(
                """
                INSERT INTO permissions (id, key, module, description, created_at, updated_at)
                VALUES (:id, :key, :module, :description, now(), now())
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"id": uuid.uuid4(), "key": key, "module": module, "description": description},
        )

    role_ids = {row.key: row.id for row in conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    permission_ids = {row.key: row.id for row in conn.execute(sa.text("SELECT id, key FROM permissions")).fetchall()}

    for role_key, perm_keys in ROLE_PERMISSIONS.items():
        for perm_key in perm_keys:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (:role_id, :permission_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_ids[role_key], "permission_id": permission_ids[perm_key]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions"))
    conn.execute(sa.text("DELETE FROM permissions"))
    conn.execute(sa.text("DELETE FROM roles"))
