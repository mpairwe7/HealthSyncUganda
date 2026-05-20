"""Encounter & Observation DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EncounterStatus = Literal[
    "planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled"
]


class ObservationIn(BaseModel):
    """A vital sign, lab result, or immunisation event."""

    model_config = ConfigDict(str_strip_whitespace=True)
    code_system: str
    code: str
    display: str | None = None
    value_quantity: float | None = None
    value_unit: str | None = None
    value_string: str | None = None
    effective_at: datetime


class ObservationOut(ObservationIn):
    id: str
    encounter_id: str
    patient_id: str
    recorded_by: str | None = None


class EncounterCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    patient_id: str
    facility_id: str
    reason: str = Field(..., min_length=2, max_length=400)
    started_at: datetime
    ended_at: datetime | None = None
    observations: list[ObservationIn] = Field(default_factory=list)
    diagnosis_codes: list[str] = Field(
        default_factory=list,
        description="ICD-10 codes; multiple allowed for co-morbidities.",
    )


class EncounterOut(BaseModel):
    id: str
    patient_id: str
    facility_id: str
    reason: str
    status: EncounterStatus
    started_at: datetime
    ended_at: datetime | None
    diagnosis_codes: list[str]
    observations: list[ObservationOut]
    created_at: datetime
