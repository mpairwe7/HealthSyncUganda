"""Encounter and Observation FHIR resources."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.fhir.primitives import (
    CodeableConcept,
    Coding,
    FhirModel,
    Period,
    Quantity,
    Reference,
)


class EncounterResource(FhirModel):
    """https://hl7.org/fhir/R4/encounter.html"""

    resourceType: Literal["Encounter"] = "Encounter"
    id: str | None = None
    status: Literal[
        "planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled"
    ] = "in-progress"
    class_: Coding = Field(
        default_factory=lambda: Coding(
            system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
            code="AMB",
            display="ambulatory",
        ),
        alias="class",
    )
    type: list[CodeableConcept] = Field(default_factory=list)
    subject: Reference
    participant: list[Reference] = Field(default_factory=list)
    period: Period
    reasonCode: list[CodeableConcept] = Field(default_factory=list)
    diagnosis: list[Reference] = Field(default_factory=list)
    location: list[Reference] = Field(default_factory=list)
    serviceProvider: Reference | None = None


class ObservationResource(FhirModel):
    """https://hl7.org/fhir/R4/observation.html — vitals, labs, immunisations."""

    resourceType: Literal["Observation"] = "Observation"
    id: str | None = None
    status: Literal[
        "registered",
        "preliminary",
        "final",
        "amended",
        "corrected",
        "cancelled",
        "entered-in-error",
    ] = "final"
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference
    encounter: Reference | None = None
    effectiveDateTime: datetime
    issued: datetime | None = None
    performer: list[Reference] = Field(default_factory=list)
    valueQuantity: Quantity | None = None
    valueString: str | None = None
    valueCodeableConcept: CodeableConcept | None = None
