"""Pragmatic patient DTOs — used by the API & UI. Mapped to/from FHIR.

These DTOs are flat, ergonomic shapes that the UI consumes directly. They are
not a substitute for the FHIR resources (those are emitted by the /fhir routes
for interop). Keeping the two layers separated prevents UI churn from leaking
into the wire format other systems depend on.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import NIN, UgandaPhone

Gender = Literal["male", "female", "other", "unknown"]


class PatientBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nin: NIN
    given_name: str = Field(..., min_length=1, max_length=80)
    family_name: str = Field(..., min_length=1, max_length=80)
    gender: Gender
    birth_date: date
    phone: UgandaPhone | None = None
    email: EmailStr | None = None
    district: str = Field(..., min_length=1, max_length=80)
    sub_county: str | None = Field(default=None, max_length=80)
    parish: str | None = Field(default=None, max_length=80)
    village: str | None = Field(default=None, max_length=80)


class PatientCreate(PatientBase):
    consent_to_share: bool = Field(
        default=False,
        description="Citizen has consented to share the record across facilities.",
    )


class PatientUpdate(BaseModel):
    """Partial update — every field optional, NIN is immutable."""

    model_config = ConfigDict(str_strip_whitespace=True)
    given_name: str | None = Field(default=None, min_length=1, max_length=80)
    family_name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: UgandaPhone | None = None
    email: EmailStr | None = None
    district: str | None = None
    sub_county: str | None = None
    parish: str | None = None
    village: str | None = None


class PatientOut(PatientBase):
    id: str
    created_at: datetime
    updated_at: datetime
    deceased: bool = False
    record_version: int = 1


class PatientSummary(BaseModel):
    """Lightweight payload for list views / autocomplete."""

    id: str
    nin: str
    given_name: str
    family_name: str
    gender: Gender
    birth_date: date
    district: str
