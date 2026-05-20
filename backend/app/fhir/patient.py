"""FHIR R4 Patient resource — Uganda profile.

We add a strict NIN identifier slice and validation. Output JSON is FHIR-spec
compliant so clients (DHIS2 Tracker, OpenMRS Sync, HAPI FHIR validators) work
without translation.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from app.fhir.primitives import (
    Address,
    CodeableConcept,
    ContactPoint,
    FhirModel,
    HumanName,
    Identifier,
)
from app.schemas.common import CodeSystems, _validate_nin


class PatientResource(FhirModel):
    """https://hl7.org/fhir/R4/patient.html — Uganda profile."""

    resourceType: Literal["Patient"] = "Patient"
    id: str | None = None
    identifier: list[Identifier] = Field(
        ...,
        min_length=1,
        description=(
            "Must include exactly one Uganda NIN identifier "
            f"with system='{CodeSystems.UG_NIN}'."
        ),
    )
    active: bool = True
    name: list[HumanName] = Field(..., min_length=1)
    telecom: list[ContactPoint] = Field(default_factory=list)
    gender: Literal["male", "female", "other", "unknown"]
    birthDate: date
    deceasedBoolean: bool = False
    address: list[Address] = Field(default_factory=list)
    maritalStatus: CodeableConcept | None = None
    communication: list[CodeableConcept] = Field(default_factory=list)

    @field_validator("identifier")
    @classmethod
    def _must_contain_valid_nin(cls, identifiers: list[Identifier]) -> list[Identifier]:
        nin_ids = [i for i in identifiers if i.system == CodeSystems.UG_NIN]
        if len(nin_ids) != 1:
            raise ValueError(
                f"Patient must carry exactly one NIN identifier (system={CodeSystems.UG_NIN})."
            )
        # Re-validate the actual NIN format
        _validate_nin(nin_ids[0].value)
        return identifiers

    @field_validator("birthDate")
    @classmethod
    def _birthdate_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("birthDate cannot be in the future.")
        return v

    @property
    def nin(self) -> str:
        return next(i.value for i in self.identifier if i.system == CodeSystems.UG_NIN)
