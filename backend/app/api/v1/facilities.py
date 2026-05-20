"""Facility endpoints — reference data for the UI dropdowns."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.facility import Facility
from app.db.session import get_db

router = APIRouter(prefix="/facilities", tags=["facilities"])


class FacilityOut(BaseModel):
    id: str
    code: str
    name: str
    level: str
    district: str
    sub_county: str | None
    latitude: float | None
    longitude: float | None


@router.get("", response_model=list[FacilityOut])
async def list_facilities(
    db: Annotated[AsyncSession, Depends(get_db)],
    district: str | None = Query(None),
    level: str | None = Query(None),
) -> list[FacilityOut]:
    stmt = select(Facility).where(Facility.active.is_(True))
    if district:
        stmt = stmt.where(Facility.district == district)
    if level:
        stmt = stmt.where(Facility.level == level)
    rows = (await db.scalars(stmt.order_by(Facility.district, Facility.name))).all()
    return [
        FacilityOut(
            id=r.id,
            code=r.code,
            name=r.name,
            level=r.level,
            district=r.district,
            sub_county=r.sub_county,
            latitude=r.latitude,
            longitude=r.longitude,
        )
        for r in rows
    ]
