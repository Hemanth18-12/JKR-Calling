"""DB-aware domain-vocabulary loader — the one other DB-touching module in
this package besides engine.py itself, mirroring rag.py's own pattern of a
fresh query every turn rather than inventing new caching plumbing (an
agent's vocabulary assignment can change between calls; a stale cache would
be a real, silent bug).
"""

from __future__ import annotations

import uuid

from jkr_db.models.agents import Agent, DomainTerm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jkr_conversation.schemas import DomainTermSnapshot


async def load_domain_terms(db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> list[DomainTermSnapshot]:
    """Returns an empty list when the agent has no vocabulary assigned —
    a normal, valid state, not an error."""
    vocabulary_id = (
        await db.execute(select(Agent.domain_vocabulary_id).where(Agent.id == agent_id, Agent.workspace_id == workspace_id))
    ).scalar_one_or_none()
    if vocabulary_id is None:
        return []

    rows = (
        await db.execute(select(DomainTerm).where(DomainTerm.vocabulary_id == vocabulary_id, DomainTerm.workspace_id == workspace_id))
    ).scalars().all()
    return [
        DomainTermSnapshot(
            id=t.id, canonical=t.canonical, aliases=list(t.aliases), category=t.category,
            criticality=t.criticality, languages=list(t.languages),
        )
        for t in rows
    ]
