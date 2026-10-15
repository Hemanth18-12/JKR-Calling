"""add knowledge agent scoping and chunk approval index

Revision ID: c1f9b3a7d2e4
Revises: e2a48cf1d092
Create Date: 2026-10-15 12:00:00.000000

1. Adds scope column to knowledge_documents ('workspace' vs 'agents').
2. Creates knowledge_document_agents join table with RLS tenant isolation.
3. Adds composite index on knowledge_chunks(workspace_id, approval_state) for fast retrieval.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1f9b3a7d2e4'
down_revision: Union[str, None] = 'e2a48cf1d092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add scope column to knowledge_documents
    op.add_column(
        'knowledge_documents',
        sa.Column('scope', sa.String(24), server_default='workspace', nullable=False)
    )

    # 2. Create knowledge_document_agents join table
    op.create_table(
        'knowledge_document_agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_knowledge_document_agent',
        'knowledge_document_agents',
        ['document_id', 'agent_id']
    )
    op.create_index('ix_knowledge_document_agents_workspace_id', 'knowledge_document_agents', ['workspace_id'])
    op.create_index('ix_knowledge_document_agents_document_id', 'knowledge_document_agents', ['document_id'])
    op.create_index('ix_knowledge_document_agents_agent_id', 'knowledge_document_agents', ['agent_id'])

    # Enable RLS & App Role Grants
    op.execute("ALTER TABLE knowledge_document_agents ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jkr_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_document_agents TO jkr_app;
                EXECUTE 'CREATE POLICY tenant_isolation ON knowledge_document_agents FOR ALL TO jkr_app USING (workspace_id = NULLIF(current_setting(''app.current_workspace_id'', true), '''')::uuid)';
            END IF;
        END $$;
        """
    )

    # 3. Add composite index on knowledge_chunks for vector retrieval speed
    op.create_index(
        'ix_knowledge_chunks_workspace_approval',
        'knowledge_chunks',
        ['workspace_id', 'approval_state']
    )


def downgrade() -> None:
    op.drop_index('ix_knowledge_chunks_workspace_approval', table_name='knowledge_chunks')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jkr_app') THEN
                EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON knowledge_document_agents';
            END IF;
        END $$;
        """
    )
    op.drop_table('knowledge_document_agents')
    op.drop_column('knowledge_documents', 'scope')
