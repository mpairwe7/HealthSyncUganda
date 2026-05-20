"""Shared types, validators, and small DTOs."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

T = TypeVar("T")

# Uganda National Identification Number (NIN) — 14 alphanumeric chars, starts with CM or CF.
# Reference: NIRA spec. We accept upper-case only and tolerate input whitespace.
_NIN_RE = re.compile(r"^C[MF][A-Z0-9]{12}$")

# Uganda phone numbers — accepted in either +256XXXXXXXXX or 0XXXXXXXXX form.
_UG_PHONE_RE = re.compile(r"^(?:\+256|0)?(7\d{8}|3\d{8}|4\d{8})$")


def _validate_nin(v: str) -> str:
    if not isinstance(v, str):
        raise TypeError("NIN must be a string")
    cleaned = v.strip().upper().replace(" ", "")
    if not _NIN_RE.match(cleaned):
        raise ValueError(
            "Invalid Uganda NIN. Expected 14 uppercase alphanumerics beginning with CM or CF."
        )
    return cleaned


def _validate_ug_phone(v: str) -> str:
    if not isinstance(v, str):
        raise TypeError("Phone must be a string")
    cleaned = v.replace(" ", "").replace("-", "")
    m = _UG_PHONE_RE.match(cleaned)
    if not m:
        raise ValueError(
            "Invalid Uganda phone. Use +256… or 0… formats (mobile 7x, landline 3x/4x)."
        )
    return "+256" + m.group(1)


NIN = Annotated[str, BeforeValidator(_validate_nin)]
UgandaPhone = Annotated[str, BeforeValidator(_validate_ug_phone)]


class Page[T](BaseModel):
    """Cursor-friendly paginated response. Total is *approximate* on hot tables."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=200)

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    """RFC-7807-ish problem detail. Stable contract for clients."""

    detail: str
    errors: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None


def utcnow() -> datetime:
    return datetime.now()


# Common code systems used by Uganda's Ministry of Health.
class CodeSystems:
    LOINC = "http://loinc.org"
    SNOMED = "http://snomed.info/sct"
    ICD10 = "http://hl7.org/fhir/sid/icd-10"
    UG_NIN = "https://nira.go.ug/identifiers/nin"
    UG_FACILITY = "https://moh.go.ug/identifiers/facility-code"
    UG_DRUGS = "https://moh.go.ug/code/essential-medicines"


__all__ = [
    "NIN",
    "CodeSystems",
    "ErrorDetail",
    "ErrorResponse",
    "Page",
    "UgandaPhone",
    "date",
    "utcnow",
]
