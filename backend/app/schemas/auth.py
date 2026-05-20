"""Auth DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import NIN

Role = Literal["citizen", "worker", "pharmacist", "district_admin", "ministry_admin"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    identifier: str = Field(..., description="NIN for citizens, username for staff.")
    password: str = Field(..., min_length=6, max_length=128)


class CitizenLoginRequest(BaseModel):
    """Demo-grade citizen sign-in via NIN + OTP-stub.

    In production this is replaced by NIRA OIDC.
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    nin: NIN
    otp: str = Field(..., min_length=4, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 — OAuth 2.0 token-type label
    expires_in: int
    role: Role
    subject: str
    name: str | None = None
    facility_id: str | None = None
