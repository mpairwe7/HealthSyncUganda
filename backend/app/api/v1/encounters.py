"""Encounter and Observation endpoints — record visits and clinical events."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.access import can_read_encounter, can_read_patient
from app.core.audit import record_access
from app.core.logging import get_logger
from app.core.security import Principal, require_role
from app.db.models.encounter import Encounter, Observation
from app.db.models.patient import Patient
from app.db.session import get_db
from app.schemas.encounter import EncounterCreate, EncounterOut, ObservationIn, ObservationOut

router = APIRouter(prefix="/encounters", tags=["encounters"])
logger = get_logger(__name__)


def _to_out(enc: Encounter) -> EncounterOut:
    return EncounterOut(
        id=enc.id,
        patient_id=enc.patient_id,
        facility_id=enc.facility_id,
        reason=enc.reason,
        status=enc.status,  # type: ignore[arg-type]
        started_at=enc.started_at,
        ended_at=enc.ended_at,
        diagnosis_codes=enc.diagnosis_codes or [],
        observations=[
            ObservationOut(
                id=o.id,
                encounter_id=o.encounter_id,
                patient_id=o.patient_id,
                code_system=o.code_system,
                code=o.code,
                display=o.display,
                value_quantity=o.value_quantity,
                value_unit=o.value_unit,
                value_string=o.value_string,
                effective_at=o.effective_at,
                recorded_by=o.recorded_by,
            )
            for o in enc.observations
        ],
        created_at=enc.created_at,
    )


@router.post(
    "",
    response_model=EncounterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a clinical encounter",
)
async def create_encounter(
    body: EncounterCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> EncounterOut:
    if not await db.get(Patient, body.patient_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    # Workers can only file encounters at their assigned facility
    if principal.facility_id and principal.facility_id != body.facility_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cannot record encounters for a different facility than your assignment.",
        )

    enc = Encounter(
        patient_id=body.patient_id,
        facility_id=body.facility_id,
        reason=body.reason,
        started_at=body.started_at,
        ended_at=body.ended_at,
        diagnosis_codes=body.diagnosis_codes,
        status="finished" if body.ended_at else "in-progress",
        recorded_by=principal.subject,
    )
    db.add(enc)
    await db.flush()

    for o in body.observations:
        db.add(
            Observation(
                encounter_id=enc.id,
                patient_id=body.patient_id,
                code_system=o.code_system,
                code=o.code,
                display=o.display,
                value_quantity=o.value_quantity,
                value_unit=o.value_unit,
                value_string=o.value_string,
                effective_at=o.effective_at,
                recorded_by=principal.subject,
            )
        )

    await db.flush()
    await db.refresh(enc, attribute_names=["observations"])

    await record_access(
        db,
        principal=principal,
        resource_type="Encounter",
        resource_id=enc.id,
        action="create",
        purpose="clinical-care",
        extra={
            "patient_id": body.patient_id,
            "observation_count": len(body.observations),
        },
    )
    return _to_out(enc)


@router.get(
    "/by-patient/{patient_id}",
    response_model=list[EncounterOut],
    summary="List a patient's encounter history",
)
async def list_encounters(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> list[EncounterOut]:
    # Confirm the principal may see the patient at all (own facility scope,
    # district scope, or admin). Without this, a worker could enumerate
    # encounters at other facilities by guessing patient IDs.
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, patient, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your patient")

    # Facility-scope at the *encounter* level — workers/pharmacists see only
    # encounters at their facility even when the patient is shared via
    # cross-facility referral. Admins see all encounters for the patient.
    stmt = (
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .order_by(Encounter.started_at.desc())
        .options(selectinload(Encounter.observations))
    )
    if principal.role in ("worker", "pharmacist") and principal.facility_id:
        stmt = stmt.where(Encounter.facility_id == principal.facility_id)
    elif principal.role == "district_admin" and principal.district_id:
        # district admins limited to patients whose enrolling_district matches
        # (patient-level check already passed; nothing more to filter here)
        pass

    rows = (await db.scalars(stmt)).all()
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=patient_id,
        action="read-history",
        purpose="clinical-care",
    )
    return [_to_out(r) for r in rows]


@router.post(
    "/{encounter_id}/observations",
    response_model=EncounterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Append observations to an existing encounter",
)
async def append_observations(
    encounter_id: str,
    body: list[ObservationIn],
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> EncounterOut:
    """Append one or more Observations to an existing encounter.

    Useful when a clinician adds late-arriving results (lab values, imaging
    reads, follow-up vitals) after the encounter was created. The encounter
    itself is left in-place; only its `observations` relationship grows.
    """
    enc = await db.get(Encounter, encounter_id)
    if enc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
    # Workers/pharmacists can only mutate encounters at their own facility.
    # Without this check, knowing an encounter UUID was enough to write
    # observations into another facility's record.
    if not await can_read_encounter(principal, enc, db):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cannot modify encounters outside your facility scope.",
        )
    if not body:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "At least one observation is required.",
        )

    for ob in body:
        db.add(
            Observation(
                encounter_id=enc.id,
                patient_id=enc.patient_id,
                code_system=ob.code_system,
                code=ob.code,
                display=ob.display,
                value_quantity=ob.value_quantity,
                value_unit=ob.value_unit,
                value_string=ob.value_string,
                effective_at=ob.effective_at,
                recorded_by=principal.subject,
            )
        )
    await db.flush()
    await db.refresh(enc, attribute_names=["observations"])

    await record_access(
        db,
        principal=principal,
        resource_type="Encounter",
        resource_id=enc.id,
        action="append-observations",
        purpose="clinical-care",
        extra={"observation_count": len(body)},
    )
    return _to_out(enc)
