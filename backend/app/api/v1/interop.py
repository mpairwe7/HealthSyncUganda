"""Interop / mock endpoints — NIRA, DHIS2 stubs + admin controls.

The mock endpoints let the demo run end-to-end without internet, while the
admin actions let presenters toggle upstream availability live ("watch the
circuit breaker trip") at the showcase.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.resilience import BreakerState, _breakers, get_breaker
from app.core.security import Principal, require_role
from app.db.models.patient import Patient
from app.db.session import get_db
from app.services.dhis2_client import Dhis2Client, get_dhis2_client

router = APIRouter(prefix="/interop", tags=["interop"])
logger = get_logger(__name__)


class BreakerStatus(BaseModel):
    name: str
    state: BreakerState
    failures: int
    failure_threshold: int


@router.get("/circuits", response_model=list[BreakerStatus])
async def list_circuits(
    _: Annotated[Principal, Depends(require_role("ministry_admin"))],
) -> list[BreakerStatus]:
    return [
        BreakerStatus(
            name=b.name,
            state=b.state,
            failures=b._failures,
            failure_threshold=b.failure_threshold,
        )
        for b in _breakers.values()
    ]


@router.post("/circuits/{name}/trip", include_in_schema=False)
async def trip_circuit(
    name: str,
    _: Annotated[Principal, Depends(require_role("ministry_admin"))],
) -> dict[str, str]:
    """Demo helper — manually trip a breaker so the audience can see the
    fallback path kick in. Production builds strip this route."""
    cb = get_breaker(name)
    cb._state = BreakerState.OPEN
    cb._failures = cb.failure_threshold
    import time as _t

    cb._opened_at = _t.monotonic()
    return {"breaker": name, "state": cb.state.value}


@router.post("/dhis2/drain-queue")
async def drain_dhis2_queue(
    dhis2: Annotated[Dhis2Client, Depends(get_dhis2_client)],
    _: Annotated[Principal, Depends(require_role("district_admin"))],
) -> dict[str, int]:
    return await dhis2.drain_queue()


# ── Mock upstreams (would be replaced by NIRA / DHIS2 in production) ─────────


_mock_nira_extra: dict[str, dict[str, str]] = {
    # Optional in-process overrides used during the seed step. The primary
    # source of truth is the Patient table — the mock NIRA endpoint queries
    # it directly so the demo survives process restarts after seeding.
}


class _MockNiraResponse(BaseModel):
    full_name: str
    gender: str
    date_of_birth: date
    district: str


@router.get("/mock/nira/verify/{nin}", response_model=_MockNiraResponse, include_in_schema=False)
async def mock_nira(
    nin: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> _MockNiraResponse:
    if nin in _mock_nira_extra:
        return _MockNiraResponse(**_mock_nira_extra[nin])

    patient = (await db.scalars(select(Patient).where(Patient.nin == nin))).one_or_none()
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NIN not found in mock NIRA")
    return _MockNiraResponse(
        full_name=f"{patient.given_name} {patient.family_name}",
        gender=patient.gender,
        date_of_birth=patient.birth_date,
        district=patient.district,
    )


def register_mock_nin(nin: str, data: dict[str, str]) -> None:
    """Used by the seed script for in-process testing. Production paths look
    up the Patient table directly."""
    _mock_nira_extra[nin] = data


@router.post("/mock/dhis2/dataValueSets", include_in_schema=False)
async def mock_dhis2(payload: dict) -> dict[str, str | int]:
    logger.info("mock.dhis2.received", value_count=len(payload.get("dataValues", [])))
    return {"status": "SUCCESS", "imported": len(payload.get("dataValues", []))}
