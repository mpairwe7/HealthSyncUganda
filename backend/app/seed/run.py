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
    ANC_REASONS,
    CHRONIC_REASONS,
    DIAGNOSIS_BY_PERSONA,
    FACILITIES,
    GENERAL_REASONS,
    PAEDIATRIC_REASONS,
    PATIENTS,
    SUPPLY_ITEMS,
    USERS,
    VACCINE_CODES,
)
from app.services.supply_ledger import receive_stock

logger = get_logger(__name__)


def _persona_for(birth_date: date, gender: str) -> str:
    """Classify a patient for biased encounter generation."""
    age_years = (date.today() - birth_date).days // 365
    if age_years <= 5:
        return "paediatric"
    if age_years >= 50:
        return "chronic"
    if gender == "female" and 18 <= age_years <= 40:
        return "anc"
    return "general"


def _reason_pool(persona: str) -> list[str]:
    return {
        "anc":        ANC_REASONS,
        "paediatric": PAEDIATRIC_REASONS,
        "chronic":    CHRONIC_REASONS,
        "general":    GENERAL_REASONS,
    }[persona]


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
    """Spread batches across facilities so the demo has interesting stock-out signals.

    Idempotent: skips (facility, item) pairs that already have any batch on
    record. Allows re-runs without inflating stock to absurd levels.
    """
    rnd = random.Random(42)
    today = date.today()
    for fac_code, fac_id in facilities.items():
        for item_code, item_id in items.items():
            # Skip vaccines at non-vaccine-ready HCs to mimic reality
            if item_code.startswith("VAC-") and ("HC2" in fac_code):
                continue
            # Idempotency: skip if any batch already exists for this pair
            existing = (
                await s.scalars(
                    select(StockBatch).where(
                        StockBatch.facility_id == fac_id,
                        StockBatch.supply_item_id == item_id,
                    ).limit(1)
                )
            ).first()
            if existing is not None:
                continue
            qty = rnd.randint(100, 4_000)
            # Storyline: make Mbarara low on ACT-AL + critically low on PCV at Gulu
            if fac_code == "MBR-RRH-003" and item_code == "ACT-AL-001":
                qty = 120
            if fac_code == "GUL-RRH-002" and item_code == "VAC-PCV-001":
                qty = 35   # below reorder_threshold of 60
            if fac_code == "ARU-RRH-005" and item_code == "MED-AMOX-001":
                qty = 480  # below reorder_threshold of 1000
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
    """Generate persona-aware encounter histories across the last 180 days.

    Idempotent: a patient who already has any encounter on record is
    skipped — this prevents re-running seed-demo from inflating the
    history to unrealistic depths.

    Each patient gets 3-7 encounters biased by clinical persona:
      • ANC women     → quarterly antenatal visits + postnatal review
      • Paediatric    → routine immunisations + acute episodes
      • Chronic       → monthly follow-ups
      • General       → 2-3 episodic OPD visits

    Every encounter carries vitals (temperature, blood pressure) and
    persona-appropriate diagnosis codes; ANC + paediatric encounters
    also emit immunisation observations so the analytics charts have
    real signal.
    """
    # Look up the seeded patients to determine persona for each
    patients_by_id = {
        p.id: p for p in (await s.scalars(select(Patient))).all()
        if p.id in patient_ids.values()
    }

    rnd = random.Random(7)
    facilities = list(facility_ids.values())
    now = datetime.now(UTC)

    for _nin, pid in patient_ids.items():
        # Idempotency: skip patients that already have encounters
        existing = (
            await s.scalars(
                select(Encounter).where(Encounter.patient_id == pid).limit(1)
            )
        ).first()
        if existing is not None:
            continue

        patient = patients_by_id.get(pid)
        if patient is None:
            continue

        persona = _persona_for(patient.birth_date, patient.gender)
        reasons = _reason_pool(persona)
        diagnoses = DIAGNOSIS_BY_PERSONA[persona]

        # How many visits, spaced how?
        if persona == "anc":
            visit_count = 5    # ANC schedule
            day_offsets = [180, 120, 60, 30, 7]
        elif persona == "paediatric":
            visit_count = rnd.randint(4, 7)
            day_offsets = sorted(rnd.sample(range(2, 180), visit_count), reverse=True)
        elif persona == "chronic":
            visit_count = 6    # roughly monthly
            day_offsets = [150, 120, 90, 60, 30, 10]
        else:
            visit_count = rnd.randint(2, 4)
            day_offsets = sorted(rnd.sample(range(2, 180), visit_count), reverse=True)

        for i, days_ago in enumerate(day_offsets[:visit_count]):
            started = now - timedelta(days=days_ago, hours=rnd.randint(8, 16))
            # ANC visits go to the nearest RRH; others rotate facilities
            facility_id = rnd.choice(facilities)
            enc = Encounter(
                patient_id=pid,
                facility_id=facility_id,
                reason=(
                    reasons[i] if persona == "anc" and i < len(reasons)
                    else rnd.choice(reasons)
                ),
                started_at=started,
                ended_at=started + timedelta(minutes=rnd.randint(15, 75)),
                status="finished",
                diagnosis_codes=[rnd.choice(diagnoses)],
            )
            s.add(enc)
            await s.flush()

            # Vitals: always temperature + blood pressure
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
                    value_string=f"{rnd.randint(95, 145)}/{rnd.randint(60, 95)}",
                    effective_at=enc.started_at,
                )
            )
            # Weight + height for paediatric growth monitoring
            if persona == "paediatric":
                age_yr = (started.date() - patient.birth_date).days / 365
                s.add(
                    Observation(
                        encounter_id=enc.id,
                        patient_id=pid,
                        code_system="http://loinc.org",
                        code="29463-7",
                        display="Body weight",
                        value_quantity=round(3.0 + age_yr * 2.2 + rnd.uniform(-0.5, 0.5), 1),
                        value_unit="kg",
                        effective_at=enc.started_at,
                    )
                )

            # Immunisation: paediatric every visit; ANC ~50% (tetanus etc.); general 20%
            roll = rnd.random()
            should_immunise = (
                persona == "paediatric"
                or (persona == "anc" and roll < 0.5)
                or (persona == "general" and roll < 0.2)
            )
            if should_immunise:
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
    """Grant a default cross-facility share consent to each patient.

    Idempotent: patients who already have any consent record are skipped.
    """
    for _, pid in patient_ids.items():
        existing = (
            await s.scalars(
                select(Consent).where(Consent.patient_id == pid).limit(1)
            )
        ).first()
        if existing is not None:
            continue
        s.add(
            Consent(
                patient_id=pid,
                scope="share_records_across_facilities",
                purpose="Continuity of care",
                granted_at=datetime.now(UTC),
                granted_by=admin_id,
            )
        )


async def _seed_self_audit_reads(
    s: AsyncSession,
    patient_ids: dict[str, str],
    facility_ids: dict[str, str],
) -> None:
    """Insert synthetic prior worker reads into the audit log per patient.

    The /api/v1/me/audit endpoint needs rows to display on first login so
    citizens can see who has accessed their record. This generator inserts
    3-5 plausibly-timed reads per patient across the last 60 days, mixing
    actions ("read", "read-history") and purposes ("clinical-care",
    "continuity-of-care") so the citizen-facing audit feed has variety.

    Idempotent: a patient who already has any AuditLog row keyed by
    (resource_type=Patient, resource_id=pid) is skipped — re-running
    seed-demo never inflates the audit history.
    """
    from app.db.models.audit_log import AuditLog

    rnd = random.Random(11)
    now = datetime.now(UTC)
    facility_list = list(facility_ids.values())
    actions = [
        ("read",         "clinical-care"),
        ("read-history", "continuity-of-care"),
        ("read",         "Triage at outpatient"),
        ("read-history", "Pharmacy dispense look-up"),
        ("read",         "ANC visit"),
    ]

    for _nin, pid in patient_ids.items():
        existing = (
            await s.scalars(
                select(AuditLog)
                .where(
                    AuditLog.resource_type == "Patient",
                    AuditLog.resource_id == pid,
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            continue
        for _ in range(rnd.randint(3, 5)):
            action, purpose = rnd.choice(actions)
            days_ago = rnd.randint(1, 60)
            s.add(
                AuditLog(
                    actor_id=f"worker-seed-{rnd.randint(1000, 9999)}",
                    actor_role="worker",
                    actor_facility_id=rnd.choice(facility_list),
                    resource_type="Patient",
                    resource_id=pid,
                    action=action,
                    purpose=purpose,
                    created_at=now - timedelta(days=days_ago, hours=rnd.randint(0, 23)),
                    updated_at=now - timedelta(days=days_ago, hours=rnd.randint(0, 23)),
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
            await _seed_self_audit_reads(s, patients, facility_ids)
    logger.info(
        "seed.done",
        facilities=len(facility_ids),
        patients=len(patients),
        items=len(items),
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
