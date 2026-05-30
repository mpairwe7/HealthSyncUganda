"""FHIR R4 Immunization resource.

Derived on-the-fly from internal Observation rows whose `code_system` is
SNOMED CT and whose code matches the UNEPI vaccine schedule. We don't
maintain a separate Immunization table — the Observation is the single
source of truth and we project it into FHIR shape on read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.fhir.primitives import (
    CodeableConcept,
    FhirModel,
    Meta,
    Quantity,
    Reference,
)


class ImmunizationResource(FhirModel):
    """https://hl7.org/fhir/R4/immunization.html"""

    resourceType: Literal["Immunization"] = "Immunization"
    id: str | None = None
    meta: Meta | None = None
    status: Literal["completed", "entered-in-error", "not-done"] = "completed"
    vaccineCode: CodeableConcept
    patient: Reference
    encounter: Reference | None = None
    occurrenceDateTime: datetime
    primarySource: bool = True
    lotNumber: str | None = None
    site: CodeableConcept | None = None
    route: CodeableConcept | None = None
    doseQuantity: Quantity | None = None
    performer: list[Reference] = Field(default_factory=list)
    note: list[str] = Field(default_factory=list)
