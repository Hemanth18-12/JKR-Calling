from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthContext, require_permission, workspace_db_for
from app.modules.experiments import service
from app.modules.experiments.schemas import (
    AssignmentOut,
    ConversionCreate,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentOut,
    ExperimentVariantOut,
    LiftResult,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _detail(experiment, variants) -> ExperimentDetail:
    return ExperimentDetail(
        id=experiment.id, name=experiment.name, campaign_id=experiment.campaign_id, status=experiment.status,
        hypothesis=experiment.hypothesis, started_at=experiment.started_at, ended_at=experiment.ended_at,
        variants=[
            ExperimentVariantOut(id=v.id, name=v.name, variant_type=v.variant_type, config=v.config, allocation_pct=v.allocation_pct)
            for v in variants
        ],
    )


@router.post("", response_model=ExperimentDetail, status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> ExperimentDetail:
    experiment = await service.create_experiment(
        db, workspace_id=auth.workspace_id, name=payload.name, campaign_id=payload.campaign_id, hypothesis=payload.hypothesis,
        variants=[v.model_dump() for v in payload.variants],
    )
    _, variants = await service.get_experiment_detail(db, workspace_id=auth.workspace_id, experiment_id=experiment.id)
    return _detail(experiment, variants)


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> list[ExperimentOut]:
    experiments = await service.list_experiments(db, workspace_id=auth.workspace_id)
    return [
        ExperimentOut(
            id=e.id, name=e.name, campaign_id=e.campaign_id, status=e.status, hypothesis=e.hypothesis,
            started_at=e.started_at, ended_at=e.ended_at,
        )
        for e in experiments
    ]


@router.get("/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(
    experiment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> ExperimentDetail:
    experiment, variants = await service.get_experiment_detail(db, workspace_id=auth.workspace_id, experiment_id=experiment_id)
    return _detail(experiment, variants)


@router.post("/{experiment_id}/start", response_model=ExperimentOut)
async def start_experiment(
    experiment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> ExperimentOut:
    e = await service.start_experiment(db, workspace_id=auth.workspace_id, experiment_id=experiment_id)
    return ExperimentOut(id=e.id, name=e.name, campaign_id=e.campaign_id, status=e.status, hypothesis=e.hypothesis, started_at=e.started_at, ended_at=e.ended_at)


@router.post("/{experiment_id}/stop", response_model=ExperimentOut)
async def stop_experiment(
    experiment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> ExperimentOut:
    e = await service.stop_experiment(db, workspace_id=auth.workspace_id, experiment_id=experiment_id)
    return ExperimentOut(id=e.id, name=e.name, campaign_id=e.campaign_id, status=e.status, hypothesis=e.hypothesis, started_at=e.started_at, ended_at=e.ended_at)


@router.post("/{experiment_id}/assign/{contact_id}", response_model=AssignmentOut)
async def assign_contact(
    experiment_id: uuid.UUID,
    contact_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> AssignmentOut:
    assignment = await service.assign_contact(db, workspace_id=auth.workspace_id, experiment_id=experiment_id, contact_id=contact_id)
    variants_result = await service.get_experiment_detail(db, workspace_id=auth.workspace_id, experiment_id=experiment_id)
    variant = next(v for v in variants_result[1] if v.id == assignment.variant_id)
    return AssignmentOut(contact_id=assignment.contact_id, variant_id=assignment.variant_id, variant_name=variant.name, assigned_at=assignment.assigned_at)


@router.post("/{experiment_id}/conversions", status_code=201)
async def record_conversion(
    experiment_id: uuid.UUID,
    payload: ConversionCreate,
    auth: AuthContext = Depends(require_permission("campaigns:edit")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:edit")),
) -> dict:
    event = await service.record_conversion(
        db, workspace_id=auth.workspace_id, experiment_id=experiment_id, contact_id=payload.contact_id,
        conversion_type=payload.conversion_type, value_paise=payload.value_paise, call_session_id=payload.call_session_id,
    )
    return {"id": str(event.id)}


@router.get("/{experiment_id}/lift", response_model=LiftResult)
async def lift(
    experiment_id: uuid.UUID,
    auth: AuthContext = Depends(require_permission("campaigns:view")),
    db: AsyncSession = Depends(workspace_db_for("campaigns:view")),
) -> LiftResult:
    result = await service.compute_lift(db, workspace_id=auth.workspace_id, experiment_id=experiment_id)
    return LiftResult(**result)
