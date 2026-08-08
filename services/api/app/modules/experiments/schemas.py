from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ExperimentVariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    variant_type: str = Field(pattern=r"^(control|treatment)$")
    config: dict = Field(default_factory=dict)
    allocation_pct: float = Field(ge=0, le=100)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    campaign_id: uuid.UUID | None = None
    hypothesis: str | None = None
    variants: list[ExperimentVariantCreate] = Field(min_length=2)

    @field_validator("variants")
    @classmethod
    def _validate_variants(cls, variants: list[ExperimentVariantCreate]) -> list[ExperimentVariantCreate]:
        if abs(sum(v.allocation_pct for v in variants) - 100) > 0.01:
            raise ValueError("Variant allocation_pct must sum to 100")
        if sum(1 for v in variants if v.variant_type == "control") != 1:
            raise ValueError("Exactly one variant must be variant_type='control'")
        return variants


class ExperimentVariantOut(BaseModel):
    id: uuid.UUID
    name: str
    variant_type: str
    config: dict
    allocation_pct: float


class ExperimentOut(BaseModel):
    id: uuid.UUID
    name: str
    campaign_id: uuid.UUID | None
    status: str
    hypothesis: str | None
    started_at: datetime | None
    ended_at: datetime | None


class ExperimentDetail(ExperimentOut):
    variants: list[ExperimentVariantOut]


class AssignmentOut(BaseModel):
    contact_id: uuid.UUID
    variant_id: uuid.UUID
    variant_name: str
    assigned_at: datetime


class ConversionCreate(BaseModel):
    contact_id: uuid.UUID
    conversion_type: str = Field(min_length=1, max_length=64)
    value_paise: int | None = None
    call_session_id: uuid.UUID | None = None


class VariantLift(BaseModel):
    variant_id: uuid.UUID
    variant_name: str
    variant_type: str
    assignment_count: int
    conversion_count: int
    conversion_rate: float | None
    lift_vs_control_pct: float | None


class LiftResult(BaseModel):
    experiment_id: uuid.UUID
    variants: list[VariantLift]
