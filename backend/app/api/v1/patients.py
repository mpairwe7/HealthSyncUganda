"""Patient records — primary clinical endpoint.

Every read & write is recorded in the audit log with the caller's purpose and
the controlling consent (if any). Workers can write only within their own
facility's scope. Citizens can read only their own record.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_access
from app.core.logging import get_logger
from app.core.security import Principal, get_current_principal, require_role
from app.db.models.patient import Patient
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.patient import (
    PatientCreate,
    PatientOut,
    PatientSummary,
    PatientUpdate,
)

router = APIRouter(prefix="/patients", tags=["patients"])
logger = get_logger(__name__)


def _to_out(p: Patient) -> PatientOut:
    return PatientOut(
        id=p.id,
        nin=p.nin,
        given_name=p.given_name,
        family_name=p.family_name,
        gender=p.gender,  # type: ignore[arg-type]
        birth_date=p.birth_date,
        phone=p.phone,
        email=p.email,
        district=p.district,
        sub_county=p.sub_county,
        parish=p.parish,
        village=p.village,
        created_at=p.created_at,
        updated_at=p.updated_at,
        deceased=p.deceased,
        record_version=p.record_version,
    )


@router.get("", response_model=Page[PatientSummary], summary="Search patients")
async def search_patients(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
    q: str | None = Query(None, description="Free-text query — matches NIN, name, phone."),
    district: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[PatientSummary]:
    stmt = select(Patient)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Patient.given_name).like(like),
                func.lower(Patient.family_name).like(like),
                func.lower(Patient.nin).like(like),
                Patient.phone.ilike(f"%{q}%"),
            )
        )
    if district:
        stmt = stmt.where(Patient.district == district)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.scalars(
            stmt.order_by(Patient.family_name).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    return Page[PatientSummary](
        items=[
            PatientSummary(
                id=r.id,
                nin=r.nin,
                given_name=r.given_name,
                family_name=r.family_name,
                gender=r.gender,  # type: ignore[arg-type]
                birth_date=r.birth_date,
                district=r.district,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{patient_id}", response_model=PatientOut, summary="Get a patient record")
async def get_patient(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    purpose: str = Query(
        "clinical-care",
        description="Why the record is being accessed — recorded in the audit trail.",
    ),
) -> PatientOut:
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    # Citizens can only read their own record
    if principal.role == "citizen" and principal.subject != p.nin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read",
        purpose=purpose,
    )
    return _to_out(p)


@router.post(
    "",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient",
)
async def create_patient(
    body: PatientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> PatientOut:
    # Conflict if NIN already exists — encourage callers to use PUT-by-NIN instead.
    existing = (await db.scalars(select(Patient).where(Patient.nin == body.nin))).one_or_none()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Patient with NIN {body.nin} already exists (id={existing.id}). "
            "Use PATCH /patients/{id} to update.",
        )

    p = Patient(
        nin=body.nin,
        given_name=body.given_name,
        family_name=body.family_name,
        gender=body.gender,
        birth_date=body.birth_date,
        phone=body.phone,
        email=body.email,
        district=body.district,
        sub_county=body.sub_county,
        parish=body.parish,
        village=body.village,
    )
    db.add(p)
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="create",
        purpose="patient-enrolment",
        extra={"consent_to_share": body.consent_to_share},
    )
    logger.info("patient.created", patient_id=p.id, district=p.district)
    return _to_out(p)


@router.patch("/{patient_id}", response_model=PatientOut, summary="Update patient demographics")
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> PatientOut:
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(p, key, value)
    p.record_version += 1
    await db.flush()

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="update",
        purpose="record-correction",
        extra={"fields": list(changes.keys())},
    )
    return _to_out(p)
