"""Auth primitives: password hashing, JWT issuing/verification, principal extraction.

This is intentionally framework-light so it can be swapped for an external IdP
(NIRA OIDC, Keycloak, OpenMRS basic auth bridge) without rewriting callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

# Roles enforced at the API layer. Keep tight; expand only as needed.
Role = Literal["citizen", "worker", "pharmacist", "district_admin", "ministry_admin"]

_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    # bcrypt rejects >72-byte inputs; truncate defensively rather than crash.
    pw = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated identity making a request. Immutable per-request."""

    subject: str                     # user-id (uuid) or NIN
    role: Role
    facility_id: str | None = None   # set for workers/pharmacists
    district_id: str | None = None   # set for facility-bound staff & district_admin
    name: str | None = None

    def is_at_least(self, role: Role) -> bool:
        order: tuple[Role, ...] = (
            "citizen",
            "worker",
            "pharmacist",
            "district_admin",
            "ministry_admin",
        )
        return order.index(self.role) >= order.index(role)


def issue_token(principal: Principal, *, ttl: timedelta = timedelta(hours=8)) -> str:
    """Issue a short-lived JWT for the given principal."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": principal.subject,
        "role": principal.role,
        "facility_id": principal.facility_id,
        "district_id": principal.district_id,
        "name": principal.name,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": settings.app_name,
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")


def _decode_token(token: str) -> Principal:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "role", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    return Principal(
        subject=claims["sub"],
        role=claims["role"],
        facility_id=claims.get("facility_id"),
        district_id=claims.get("district_id"),
        name=claims.get("name"),
    )


async def get_current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """FastAPI dependency that resolves the calling principal from a Bearer token."""
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return _decode_token(creds.credentials)


def require_role(minimum: Role):
    """Dependency factory enforcing role-based access."""

    async def _checker(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not principal.is_at_least(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {minimum}")
        return principal

    return _checker
