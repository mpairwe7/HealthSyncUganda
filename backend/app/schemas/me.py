"""DTOs for the `/api/v1/me/*` citizen-self-serve endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import UgandaPhone
from app.schemas.consent import ConsentScope


class ImmunisationOut(BaseModel):
    """A single vaccine administration, distilled from an Observation row."""

    id: str
    encounter_id: str
    patient_id: str
    code_system: str
    code: str
    display: str | None = None
    administered_at: datetime
    facility_id: str | None = None


class AuditEntryOut(BaseModel):
    """An access-log entry the citizen can review under DPPA 2019 §14."""

    id: str
    actor_role: str
    actor_facility_id: str | None = None
    action: str
    purpose: str | None = None
    resource_type: str
    resource_id: str
    consent_id: str | None = None
    occurred_at: datetime


class OwnConsentGrant(BaseModel):
    """Citizen self-grant — narrower than the worker ConsentCreate; the
    patient_id is the caller's own record (inferred from the JWT subject)."""

    model_config = ConfigDict(str_strip_whitespace=True)
    scope: ConsentScope
    purpose: str = Field(..., min_length=4, max_length=300)
    expires_at: datetime | None = None


class ProfileUpdate(BaseModel):
    """Fields a citizen is allowed to change about themselves.

    Deliberately excludes NIN, names, gender, birth_date, district, and the
    derived flags — those are NIRA-authoritative or worker-mediated.
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    phone: UgandaPhone | None = None
    email: EmailStr | None = None
    sub_county: str | None = Field(default=None, max_length=80)
    parish: str | None = Field(default=None, max_length=80)
    village: str | None = Field(default=None, max_length=80)


AuditWindow = Literal[7, 30, 90]
