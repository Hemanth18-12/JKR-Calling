"""add conversation policy turn and duration caps

Revision ID: 0dea857b9d77
Revises: 056036cf0e79
Create Date: 2026-08-08 16:10:46.194904

Turn-taking used to be a hardcoded MAX_AGENT_TURNS=5 constant in
services/api/app/modules/live_call/service.py. The shared conversation
engine (packages/conversation) ends a call normally once the planner
reaches a terminal state (objective completed / do-not-call / wrong
number) — these two columns are now purely a safety-net ceiling,
configurable per agent version like every other conversation-shaping knob
on this table. Additive-only, server_default backfills existing rows
without a separate UPDATE.

Note: autogenerate also detected two pre-existing, unrelated missing
foreign keys (agents.published_version_id, knowledge_documents.current_version_id)
— deliberately NOT included here; that's separate, pre-existing schema
drift outside this migration's scope and needs its own reviewed migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dea857b9d77'
down_revision: Union[str, None] = '056036cf0e79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_policies', sa.Column('max_turns', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('conversation_policies', sa.Column('max_call_duration_seconds', sa.Integer(), nullable=False, server_default='300'))


def downgrade() -> None:
    op.drop_column('conversation_policies', 'max_call_duration_seconds')
    op.drop_column('conversation_policies', 'max_turns')
