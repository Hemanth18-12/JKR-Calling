"""add workspace invitations and coin tx unique constraint

Revision ID: e2a48cf1d092
Revises: 744f919d5b3b
Create Date: 2026-10-08 12:00:00.000000

1. Adds unique constraint uq_coin_tx_ws_type_ref on coin_transactions(workspace_id, transaction_type, reference_id)
   to ensure strict idempotency of coin deductions per call.
2. Creates workspace_invitations table with 7-day secure token hash, role, email, and RLS policy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2a48cf1d092'
down_revision: Union[str, None] = '744f919d5b3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Unique constraint for coin idempotency
    op.create_unique_constraint(
        'uq_coin_tx_ws_type_ref',
        'coin_transactions',
        ['workspace_id', 'transaction_type', 'reference_id']
    )

    # 2. Workspace invitations table
    op.create_table(
        'workspace_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('roles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('invited_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(128), nullable=False, unique=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_workspace_invitations_workspace_id', 'workspace_invitations', ['workspace_id'])
    op.create_index('ix_workspace_invitations_email', 'workspace_invitations', ['email'])
    op.create_index('ix_workspace_invitations_token_hash', 'workspace_invitations', ['token_hash'])

    # Enable RLS & App Role Grants
    op.execute("ALTER TABLE workspace_invitations ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jkr_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON workspace_invitations TO jkr_app;
                EXECUTE 'CREATE POLICY tenant_isolation ON workspace_invitations FOR ALL TO jkr_app USING (workspace_id = NULLIF(current_setting(''app.current_workspace_id'', true), '''')::uuid)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jkr_app') THEN
                EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON workspace_invitations';
            END IF;
        END $$;
        """
    )
    op.drop_table('workspace_invitations')
    op.drop_constraint('uq_coin_tx_ws_type_ref', 'coin_transactions', type_='unique')
