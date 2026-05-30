"""DTOs for the `/api/v1/me/*` self-serve endpoints (citizen + staff)."""

from __future__ import annotations

from datetime import datetime

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


class StaffMeOut(BaseModel):
    """Result of `GET /api/v1/me/staff` — staff profile + facility context.

    Returned to any non-citizen JWT (worker / pharmacist / district_admin /
    ministry_admin). Surfaces only the fields the worker dashboard needs:
    role, facility, JWT expiry — never password_hash or internal flags.
    """

    user_id: str
    username: str
    full_name: str
    role: str
    facility_id: str | None = None
    facility_name: str | None = None
    facility_level: str | None = None
    facility_district: str | None = None
    active: bool = True


