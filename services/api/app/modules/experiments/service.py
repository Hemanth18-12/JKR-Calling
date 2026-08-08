"""Experiment CRUD, deterministic variant assignment, and a simple lift
calculation. **Medium** tier (docs/DECISIONS/0007-scope-for-this-pass.md):
real assignment/conversion/lift logic against the real schema, but nothing
in campaign-worker or voice-worker actually calls `assign_contact` yet to
vary agent behavior per variant — that integration (e.g. "campaign X runs
agent version A for the control group, version B for treatment") is future
work. What's built here is the experimentation *engine*, exercisable via
its own API today, not yet wired as a dispatch-time decision.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jkr_db.models.experiments import (
    ConversionEvent,
    Experiment,
    ExperimentAssignment,
    ExperimentVariant,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_experiment(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str, campaign_id: uuid.UUID | None, hypothesis: str | None, variants: list[dict],
) -> Experiment:
    experiment = Experiment(workspace_id=workspace_id, campaign_id=campaign_id, name=name, status="draft", hypothesis=hypothesis)
    db.add(experiment)
    await db.flush()

    for v in variants:
        db.add(
            ExperimentVariant(
                workspace_id=workspace_id, experiment_id=experiment.id, variant_type=v["variant_type"],
                name=v["name"], config=v["config"], allocation_pct=v["allocation_pct"],
            )
        )
    await db.flush()
    return experiment


async def list_experiments(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Experiment]:
    result = await db.execute(select(Experiment).where(Experiment.workspace_id == workspace_id).order_by(Experiment.created_at.desc()))
    return list(result.scalars().all())


async def _get_experiment_or_404(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
    result = await db.execute(select(Experiment).where(Experiment.id == experiment_id, Experiment.workspace_id == workspace_id))
    experiment = result.scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return experiment


async def get_experiment_detail(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> tuple[Experiment, list[ExperimentVariant]]:
    experiment = await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    variants_result = await db.execute(select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment_id).order_by(ExperimentVariant.name))
    return experiment, list(variants_result.scalars().all())


async def start_experiment(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
    experiment = await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    if experiment.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot start an experiment in status '{experiment.status}'")
    experiment.status = "running"
    experiment.started_at = datetime.now(UTC)
    await db.flush()
    return experiment


async def stop_experiment(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
    experiment = await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    if experiment.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a running experiment can be stopped")
    experiment.status = "completed"
    experiment.ended_at = datetime.now(UTC)
    await db.flush()
    return experiment


def _bucket_variant(contact_id: uuid.UUID, experiment_id: uuid.UUID, variants: list[ExperimentVariant]) -> ExperimentVariant:
    """Deterministic (same contact always lands in the same variant for a
    given experiment — not truly random) hash-bucketing weighted by
    `allocation_pct`, same reasoning as campaign-worker's
    `simulate_connect_outcome`: reproducible in tests, no RNG state to track."""
    digest = hashlib.sha256(f"{experiment_id}:{contact_id}".encode()).digest()
    roll = int.from_bytes(digest[:4], "big") % 10000
    cumulative = 0.0
    for variant in sorted(variants, key=lambda v: v.id):
        cumulative += variant.allocation_pct * 100
        if roll < cumulative:
            return variant
    return variants[-1]


async def assign_contact(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID, contact_id: uuid.UUID) -> ExperimentAssignment:
    existing = await db.execute(
        select(ExperimentAssignment).where(
            ExperimentAssignment.workspace_id == workspace_id, ExperimentAssignment.experiment_id == experiment_id,
            ExperimentAssignment.contact_id == contact_id,
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        return existing_row

    experiment = await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    if experiment.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "Experiment is not running")

    variants_result = await db.execute(select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment_id))
    variants = list(variants_result.scalars().all())
    if not variants:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Experiment has no variants")

    variant = _bucket_variant(contact_id, experiment_id, variants)
    assignment = ExperimentAssignment(
        workspace_id=workspace_id, experiment_id=experiment_id, variant_id=variant.id, contact_id=contact_id,
        assigned_at=datetime.now(UTC),
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def record_conversion(
    db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID, contact_id: uuid.UUID,
    conversion_type: str, value_paise: int | None, call_session_id: uuid.UUID | None,
) -> ConversionEvent:
    await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    event = ConversionEvent(
        workspace_id=workspace_id, experiment_id=experiment_id, contact_id=contact_id, call_session_id=call_session_id,
        conversion_type=conversion_type, value_paise=value_paise, occurred_at=datetime.now(UTC),
    )
    db.add(event)
    await db.flush()
    return event


async def compute_lift(db: AsyncSession, *, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> dict:
    await _get_experiment_or_404(db, workspace_id=workspace_id, experiment_id=experiment_id)
    variants_result = await db.execute(select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment_id).order_by(ExperimentVariant.name))
    variants = list(variants_result.scalars().all())

    rows = []
    control_rate: float | None = None
    for variant in variants:
        assignment_count_result = await db.execute(
            select(func.count(ExperimentAssignment.id)).where(ExperimentAssignment.experiment_id == experiment_id, ExperimentAssignment.variant_id == variant.id)
        )
        assignment_count = assignment_count_result.scalar_one()

        conversion_count_result = await db.execute(
            select(func.count(func.distinct(ConversionEvent.contact_id)))
            .join(ExperimentAssignment, ExperimentAssignment.contact_id == ConversionEvent.contact_id)
            .where(
                ExperimentAssignment.experiment_id == experiment_id, ExperimentAssignment.variant_id == variant.id,
                ConversionEvent.experiment_id == experiment_id,
            )
        )
        conversion_count = conversion_count_result.scalar_one()

        conversion_rate = round(conversion_count / assignment_count, 4) if assignment_count else None
        if variant.variant_type == "control":
            control_rate = conversion_rate

        rows.append(
            {
                "variant_id": variant.id, "variant_name": variant.name, "variant_type": variant.variant_type,
                "assignment_count": assignment_count, "conversion_count": conversion_count, "conversion_rate": conversion_rate,
                "lift_vs_control_pct": None,
            }
        )

    for row in rows:
        if row["variant_type"] != "control" and control_rate is not None and control_rate > 0 and row["conversion_rate"] is not None:
            row["lift_vs_control_pct"] = round((row["conversion_rate"] - control_rate) / control_rate * 100, 2)

    return {"experiment_id": experiment_id, "variants": rows}
