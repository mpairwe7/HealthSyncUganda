"""Consent DTOs — explicit, granular, revocable."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConsentScope = Literal[
    "share_records_across_facilities",
    "share_with_district_health_office",
    "share_with_research",
    "share_with_emergency_services",
]


class ConsentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    patient_id: str
    scope: ConsentScope
    purpose: str = Field(..., min_length=4, max_length=300)
    expires_at: datetime | None = None


class ConsentOut(ConsentCreate):
    id: str
    granted_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        if self.revoked_at:
            return False
        if self.expires_at and self.expires_at < datetime.now():
            return False
        return True
