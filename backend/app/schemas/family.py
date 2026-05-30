"""DTOs for the immunisation-status + caregiver-link endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusLevel = Literal["complete", "due", "due-soon", "overdue", "not-yet"]


class AntigenStatusOut(BaseModel):
    """One row in the immunisation-status response — per antigen."""

    antigen: str                          # short label e.g. "BCG", "DPT"
    display: str                          # human-readable antigen name
    snomed_code: str
    series_size: int                      # total doses in the series
    doses_given: int                      # how many already administered
    next_dose_number: int | None = None   # 1-based; None when complete
    next_due_date: date | None = None     # absolute calendar date
    overdue_days: int = 0                 # positive when overdue
    last_dose_at: datetime | None = None
    status: StatusLevel


class FamilyMemberOut(BaseModel):
    """A linked family member — caregiver's view of a child, or vice versa."""

    link_id: str
    patient_id: str
    nin: str
    given_name: str
    family_name: str
    birth_date: date
    gender: str
    relationship: str
    # Quick summary so the family list can show "3 vaccines overdue"
    # without a per-child round-trip.
    overdue_antigen_count: int = 0


CaregiverRelationship = Literal[
    "mother", "father", "guardian", "grandparent",
    "sibling", "aunt", "uncle", "other",
]


class CaregiverLinkIn(BaseModel):
    """POST body for linking a caregiver to a child.

    The `caregiver_nin` is supplied by the worker (who searches by NIN).
    The child id comes from the URL path so the worker explicitly
    states which patient they're modifying.
    """
    model_config = ConfigDict(str_strip_whitespace=True)
    caregiver_nin: str = Field(..., min_length=14, max_length=14)
    relationship: CaregiverRelationship = "guardian"


class CaregiverLinkOut(BaseModel):
    """Result of a caregiver-link mutation."""
    id: str
    caregiver_id: str
    child_id: str
    relationship: str
    created_at: datetime
