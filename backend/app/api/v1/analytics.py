"""Analytics & M&E endpoints — aggregations for district and ministry dashboards.

Reads are cached in Redis (60-second TTL by default) because dashboards are
typically polled by many concurrent users. The cache layer degrades open: if
Redis is down, results are computed fresh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.security import Principal, require_role
from app.db.models.encounter import Encounter, Observation
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.models.supply import StockBatch, SupplyItem
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = get_logger(__name__)

_CACHE_TTL = 60


async def _cached(key: str, build):
    try:
        redis = await get_redis()
        raw = await redis.get(key)
        if raw:
            return orjson.loads(raw)
    except Exception as exc:
        logger.warning("analytics.cache_unavailable", error=str(exc))
        return await build()
    fresh = await build()
    try:
        await redis.set(key, orjson.dumps(fresh), ex=_CACHE_TTL)  # type: ignore[possibly-undefined]
    except Exception:  # noqa: S110
        pass
    return fresh


class DistrictEncounterCount(BaseModel):
    district: str
    encounter_count: int
    patient_count: int


@router.get(
    "/encounters-by-district",
    response_model=list[DistrictEncounterCount],
    summary="Encounter and patient counts by district (last 30 days)",
)
async def encounters_by_district(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("district_admin"))],
    since_days: int = Query(30, ge=1, le=365),
) -> list[DistrictEncounterCount]:
    cache_key = f"analytics:enc-by-district:{since_days}"

    async def build() -> list[dict]:
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        stmt = (
            select(
                Patient.district.label("district"),
                func.count(Encounter.id).label("encounter_count"),
                func.count(func.distinct(Encounter.patient_id)).label("patient_count"),
            )
            .join(Encounter, Encounter.patient_id == Patient.id)
            .where(Encounter.started_at >= cutoff)
            .group_by(Patient.district)
            .order_by(func.count(Encounter.id).desc())
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "district": r.district,
                "encounter_count": int(r.encounter_count),
                "patient_count": int(r.patient_count),
            }
            for r in rows
        ]

    data = await _cached(cache_key, build)
    return [DistrictEncounterCount(**d) for d in data]


class ImmunisationCoverage(BaseModel):
    district: str
    antigen: str
    doses_administered: int


@router.get(
    "/immunisation-coverage",
    response_model=list[ImmunisationCoverage],
    summary="Doses administered by district & antigen (LOINC code observations)",
)
async def immunisation_coverage(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("district_admin"))],
    since_days: int = Query(180, ge=1, le=365),
) -> list[ImmunisationCoverage]:
    cache_key = f"analytics:imm:{since_days}"

    async def build() -> list[dict]:
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        stmt = (
            select(
                Patient.district.label("district"),
                Observation.display.label("antigen"),
                func.count(Observation.id).label("doses_administered"),
            )
            .join(Observation, Observation.patient_id == Patient.id)
            .where(
                Observation.effective_at >= cutoff,
                Observation.code_system == "http://snomed.info/sct",
            )
            .group_by(Patient.district, Observation.display)
            .order_by(Patient.district, Observation.display)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "district": r.district,
                "antigen": r.antigen or "unspecified",
                "doses_administered": int(r.doses_administered),
            }
            for r in rows
        ]

    data = await _cached(cache_key, build)
    return [ImmunisationCoverage(**d) for d in data]


class StockOutRisk(BaseModel):
    facility_id: str
    facility_name: str
    district: str
    item_code: str
    item_name: str
    on_hand: int
    reorder_threshold: int
    days_of_cover_estimated: float | None = None


@router.get(
    "/stock-out-risk",
    response_model=list[StockOutRisk],
    summary="Items below reorder threshold, grouped by facility",
)
async def stock_out_risk(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("district_admin"))],
) -> list[StockOutRisk]:
    cache_key = "analytics:stockout"

    async def build() -> list[dict]:
        stmt = (
            select(
                Facility.id,
                Facility.name,
                Facility.district,
                SupplyItem.code,
                SupplyItem.name.label("item_name"),
                func.coalesce(func.sum(StockBatch.remaining), 0).label("on_hand"),
                SupplyItem.reorder_threshold,
            )
            .join(StockBatch, StockBatch.facility_id == Facility.id)
            .join(SupplyItem, SupplyItem.id == StockBatch.supply_item_id)
            .group_by(Facility.id, SupplyItem.id)
            .having(
                func.coalesce(func.sum(StockBatch.remaining), 0) < SupplyItem.reorder_threshold
            )
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "facility_id": r.id,
                "facility_name": r.name,
                "district": r.district,
                "item_code": r.code,
                "item_name": r.item_name,
                "on_hand": int(r.on_hand),
                "reorder_threshold": r.reorder_threshold,
            }
            for r in rows
        ]

    data = await _cached(cache_key, build)
    return [StockOutRisk(**d) for d in data]
