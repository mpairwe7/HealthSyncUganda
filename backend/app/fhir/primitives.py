"""FHIR R4 primitive/complex data types — slim, strict, Pydantic v2.

We intentionally implement only the subset HealthSync exercises. Each type
mirrors the FHIR JSON shape so payloads validate against the spec.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FhirModel(BaseModel):
    """Common config — strict, no extras, JSON-by-default."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class Coding(FhirModel):
    """https://hl7.org/fhir/R4/datatypes.html#Coding"""

    system: str
    code: str
    display: str | None = None


class CodeableConcept(FhirModel):
    """https://hl7.org/fhir/R4/datatypes.html#CodeableConcept"""

    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Identifier(FhirModel):
    """https://hl7.org/fhir/R4/datatypes.html#Identifier"""

    use: Literal["usual", "official", "temp", "secondary", "old"] | None = None
    system: str
    value: str
    type: CodeableConcept | None = None


class HumanName(FhirModel):
    """https://hl7.org/fhir/R4/datatypes.html#HumanName"""

    use: Literal["usual", "official", "temp", "nickname", "anonymous", "old", "maiden"] | None = (
        "official"
    )
    text: str | None = None
    family: str | None = None
    given: list[str] = Field(default_factory=list)


class ContactPoint(FhirModel):
    """https://hl7.org/fhir/R4/datatypes.html#ContactPoint"""

    system: Literal["phone", "fax", "email", "pager", "url", "sms", "other"]
    value: str
    use: Literal["home", "work", "temp", "old", "mobile"] | None = None


class Address(FhirModel):
    """Simplified to Uganda's geographic units."""

    use: Literal["home", "work", "temp", "old", "billing"] | None = "home"
    line: list[str] = Field(default_factory=list)
    city: str | None = None          # urban authority / town council
    district: str | None = None      # Uganda district (e.g. "Kampala", "Gulu")
    state: str | None = None         # region (e.g. "Northern")
    country: str = "UG"


class Reference(FhirModel):
    """Resource reference — `Patient/abc-123` form."""

    reference: str
    display: str | None = None


class Period(FhirModel):
    start: datetime | None = None
    end: datetime | None = None


class Quantity(FhirModel):
    value: float
    unit: str | None = None
    system: str | None = None
    code: str | None = None


class Meta(FhirModel):
    """https://hl7.org/fhir/R4/resource.html#Meta — resource-level audit data.

    `lastUpdated` is the most commonly consumed field (HAPI validators check
    for it; the conformance harness asserts presence). `versionId` is the
    record_version where the ORM model tracks one.
    """

    lastUpdated: datetime | None = None
    versionId: str | None = None


# Helpful re-exports
__all__ = [
    "Address",
    "CodeableConcept",
    "Coding",
    "ContactPoint",
    "FhirModel",
    "HumanName",
    "Identifier",
    "Meta",
    "Period",
    "Quantity",
    "Reference",
    "date",
    "datetime",
]
