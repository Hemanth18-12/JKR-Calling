"""add tools:edit permission

Revision ID: 056036cf0e79
Revises: 81ba970ac969
Create Date: 2026-08-07 18:32:26.075009

Phase 5's RBAC catalog seed shipped `tools:view`/`tools:view_audit` but
nothing to gate enabling/disabling a tool definition or an agent's tool
list — that's an edit action, not a view, and had no permission key to
require. Adding it here (a new migration) rather than editing
`81ba970ac969` because that migration has already run against every
existing environment; editing an applied migration in place doesn't get
re-run and would silently drift dev/prod schemas apart.
"""
import uuid

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '056036cf0e79'
down_revision: str | None = '81ba970ac969'
branch_labels: str | None = None
depends_on: str | None = None

PERMISSION = ("tools:edit", "tools", "Enable/disable tool definitions and per-agent tool configuration")

# Roles that get tools:edit. workspace_owner/workspace_admin already have
# every non-billing/non-platform permission as a standing rule (see
# 81ba970ac969's ROLE_PERMISSIONS comment); agent_operator already has
# tools:view since it builds agents, and enabling/disabling a tool for an
# agent is squarely part of that job.
GRANTED_TO_ROLES = ["platform_super_admin", "jkr_admin", "workspace_owner", "workspace_admin", "agent_operator"]


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO permissions (id, key, module, description, created_at, updated_at)
            VALUES (:id, :key, :module, :description, now(), now())
            ON CONFLICT (key) DO NOTHING
            """
        ),
        {"id": uuid.uuid4(), "key": PERMISSION[0], "module": PERMISSION[1], "description": PERMISSION[2]},
    )

    permission_id = conn.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION[0]}).scalar_one()
    role_ids = conn.execute(
        sa.text("SELECT id FROM roles WHERE key = ANY(:keys)"), {"keys": GRANTED_TO_ROLES}
    ).scalars().all()

    for role_id in role_ids:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (:role_id, :permission_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    permission_id = conn.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION[0]}).scalar_one_or_none()
    if permission_id is not None:
        conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
        conn.execute(sa.text("DELETE FROM permissions WHERE id = :id"), {"id": permission_id})
