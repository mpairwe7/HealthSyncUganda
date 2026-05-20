"""Seed the database with demo data.

Usage:
    uv run python -m app.seed.run

Idempotent: re-running upserts records keyed by NIN / code.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.consent import Consent
from app.db.models.encounter import Encounter, Observation
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.models.supply import StockBatch, SupplyItem
from app.db.models.user import User
from app.db.session import dispose_engine, get_engine, get_session_factory
from app.seed.data import (
    FACILITIES,
    PATIENTS,
    SUPPLY_ITEMS,
    USERS,
    VACCINE_CODES,
)
from app.services.supply_ledger import receive_stock

logger = get_logger(__name__)


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_facilities(s: AsyncSession) -> dict[str, str]:
    """Returns code -> id mapping."""
    out: dict[str, str] = {}
    for fac in FACILITIES:
        existing = (
            await s.scalars(select(Facility).where(Facility.code == fac["code"]))
        ).one_or_none()
        if existing:
            out[fac["code"]] = existing.id
            continue
        f = Facility(**fac)
        s.add(f)
        await s.flush()
        out[fac["code"]] = f.id
    return out


async def _seed_users(s: AsyncSession, facility_ids: dict[str, str]) -> None:
    for u in USERS:
        existing = (
            await s.scalars(select(User).where(User.username == u["username"]))
        ).one_or_none()
        if existing:
            continue
        s.add(
            User(
                username=u["username"],
                full_name=u["full_name"],
                role=u["role"],
                password_hash=hash_password(u["password"]),
                facility_id=facility_ids.get(u["facility_code"]) if u["facility_code"] else None,
            )
        )


async def _seed_supply_items(s: AsyncSession) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in SUPPLY_ITEMS:
        existing = (
            await s.scalars(select(SupplyItem).where(SupplyItem.code == item["code"]))
        ).one_or_none()
        if existing:
            out[item["code"]] = existing.id
            continue
        si = SupplyItem(**item)
        s.add(si)
        await s.flush()
        out[item["code"]] = si.id
    return out


async def _seed_patients(s: AsyncSession) -> dict[str, str]:
    out: dict[str, str] = {}
    for pat in PATIENTS:
        existing = (
            await s.scalars(select(Patient).where(Patient.nin == pat["nin"]))
        ).one_or_none()
        if existing:
            out[pat["nin"]] = existing.id
            continue
        p = Patient(**pat)
        s.add(p)
        await s.flush()
        out[pat["nin"]] = p.id

        # Mock NIRA register entry so /auth/citizen/login works
        from app.api.v1.interop import register_mock_nin

        register_mock_nin(
            pat["nin"],
            {
                "full_name": f"{pat['given_name']} {pat['family_name']}",
                "gender": pat["gender"],
                "date_of_birth": pat["birth_date"].isoformat(),
                "district": pat["district"],
            },
        )
    return out


async def _seed_stock(
    s: AsyncSession, facilities: dict[str, str], items: dict[str, str], admin_id: str
) -> None:
    """Spread batches across facilities so the demo has interesting stock-out signals."""
    rnd = random.Random(42)
    today = date.today()
    for fac_code, fac_id in facilities.items():
        for item_code, item_id in items.items():
            # Skip vaccines at non-vaccine-ready HCs to mimic reality
            if item_code.startswith("VAC-") and "HC4" in fac_code:
                continue
            qty = rnd.randint(100, 4_000)
            # Make Mbarara low on ACT-AL for the demo storyline
            if fac_code == "MBR-RRH-003" and item_code == "ACT-AL-001":
                qty = 120
            batch = StockBatch(
                supply_item_id=item_id,
                facility_id=fac_id,
                lot_number=f"LOT-{fac_code[:3]}-{item_code[:6]}-{rnd.randint(1000,9999)}",
                quantity=qty,
                remaining=qty,
                expires_on=today + timedelta(days=rnd.randint(60, 540)),
                received_on=today - timedelta(days=rnd.randint(7, 60)),
                cost_ugx=rnd.randint(500, 5000) * qty,
            )
            s.add(batch)
            await s.flush()
            await receive_stock(s, batch=batch, actor_id=admin_id)


async def _seed_encounters(
    s: AsyncSession, patient_ids: dict[str, str], facility_ids: dict[str, str]
) -> None:
    rnd = random.Random(7)
    facilities = list(facility_ids.values())
    now = datetime.now(UTC)
    diagnosis_pool = ["B54", "A09.9", "J06.9", "E11.9", "O09.5"]  # ICD-10
    for _nin, pid in patient_ids.items():
        for _ in range(rnd.randint(1, 3)):
            started = now - timedelta(days=rnd.randint(1, 60), hours=rnd.randint(0, 23))
            enc = Encounter(
                patient_id=pid,
                facility_id=rnd.choice(facilities),
                reason=rnd.choice(
                    [
                        "Antenatal visit",
                        "Outpatient consultation",
                        "Vaccination",
                        "Fever and chills",
                        "Routine check-up",
                    ]
                ),
                started_at=started,
                ended_at=started + timedelta(minutes=rnd.randint(15, 90)),
                status="finished",
                diagnosis_codes=[rnd.choice(diagnosis_pool)],
            )
            s.add(enc)
            await s.flush()

            # Add vitals + sometimes a vaccination observation
            s.add(
                Observation(
                    encounter_id=enc.id,
                    patient_id=pid,
                    code_system="http://loinc.org",
                    code="8310-5",
                    display="Body temperature",
                    value_quantity=round(rnd.uniform(36.4, 39.2), 1),
                    value_unit="Cel",
                    effective_at=enc.started_at,
                )
            )
            s.add(
                Observation(
                    encounter_id=enc.id,
                    patient_id=pid,
                    code_system="http://loinc.org",
                    code="55284-4",
                    display="Blood pressure",
                    value_string=f"{rnd.randint(95, 135)}/{rnd.randint(60, 90)}",
                    effective_at=enc.started_at,
                )
            )
            if rnd.random() < 0.4:
                antigen = rnd.choice(list(VACCINE_CODES.keys()))
                system, code, display = VACCINE_CODES[antigen]
                s.add(
                    Observation(
                        encounter_id=enc.id,
                        patient_id=pid,
                        code_system=system,
                        code=code,
                        display=display,
                        effective_at=enc.started_at,
                    )
                )


async def _seed_consents(s: AsyncSession, patient_ids: dict[str, str], admin_id: str) -> None:
    for _, pid in patient_ids.items():
        s.add(
            Consent(
                patient_id=pid,
                scope="share_records_across_facilities",
                purpose="Continuity of care",
                granted_at=datetime.now(UTC),
                granted_by=admin_id,
            )
        )


async def main() -> None:
    configure_logging("INFO", json_output=False)
    logger.info("seed.start")
    await _ensure_schema()
    factory = get_session_factory()
    async with factory() as s:
        async with s.begin():
            facility_ids = await _seed_facilities(s)
            await _seed_users(s, facility_ids)
            items = await _seed_supply_items(s)
            patients = await _seed_patients(s)
            admin = (
                await s.scalars(select(User).where(User.username == "admin"))
            ).one()
            await _seed_stock(s, facility_ids, items, admin.id)
            await _seed_encounters(s, patients, facility_ids)
            await _seed_consents(s, patients, admin.id)
    logger.info(
        "seed.done",
        facilities=len(facility_ids),
        patients=len(patients),
        items=len(items),
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
