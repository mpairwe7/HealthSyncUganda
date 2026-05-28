"""Patient records — primary clinical endpoint.

Every read & write is recorded in the audit log with the caller's purpose and
the controlling consent (if any). Workers can write only within their own
facility's scope. Citizens can read only their own record.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinical.immunisation_status import (
    immunisation_status_for,
    immunisation_status_for_many,
)
from app.core.access import (
    can_read_patient,
    patient_visibility_filter,
)
from app.core.audit import record_access
from app.core.logging import get_logger
from app.core.security import Principal, get_current_principal, require_role
from app.db.models.caregiver import CaregiverLink
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.family import (
    AntigenStatusOut,
    CaregiverLinkIn,
    CaregiverLinkOut,
    FamilyMemberOut,
)
from app.schemas.patient import (
    PatientCreate,
    PatientDeceased,
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

    # RBAC scope: workers see their facility's patients (enrolled here OR with
    # an encounter here); district_admins see their district; ministry_admins
    # see everything.
    scope_clauses = patient_visibility_filter(principal)
    if scope_clauses:
        stmt = stmt.where(and_(*scope_clauses))

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

    if not await can_read_patient(principal, p, db):
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

    # Anchor the patient at the worker's facility so future RBAC checks have
    # a definite enrolling-facility to scope against. Pulled from the
    # principal — workers can't enrol someone at a facility they don't belong
    # to. Higher roles enrol via /admin paths (not this endpoint).
    enrolling_facility_id = principal.facility_id
    enrolling_district = principal.district_id
    if enrolling_district is None and enrolling_facility_id is not None:
        # Best-effort lookup when the JWT predates the district claim.
        fac = await db.get(Facility, enrolling_facility_id)
        if fac is not None:
            enrolling_district = fac.district

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
        enrolling_facility_id=enrolling_facility_id,
        enrolling_district=enrolling_district,
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
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

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


@router.patch(
    "/{patient_id}/deceased",
    response_model=PatientOut,
    summary="Mark a patient as deceased (or revive — reversible)",
)
async def set_deceased(
    patient_id: str,
    body: PatientDeceased,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> PatientOut:
    """Set the patient's `deceased` flag. Audited under `mark-deceased`.

    This is reversible (workers can clear the flag too) but every change is
    recorded — DPPA §22 + clinical-data-integrity controls. The encounter
    history is preserved either way.
    """
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    p.deceased = body.deceased
    p.record_version += 1
    await db.flush()

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="mark-deceased" if body.deceased else "clear-deceased",
        purpose=body.purpose or "vital-status-update",
    )
    return _to_out(p)


# ── Immunisation status (derived) ───────────────────────────────────────────


@router.get(
    "/{patient_id}/immunisation-status",
    response_model=list[AntigenStatusOut],
    summary="Per-antigen immunisation status (done, due, overdue, complete)",
)
async def immunisation_status(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> list[AntigenStatusOut]:
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read-immunisation-status",
        purpose="clinical-care",
    )
    return await immunisation_status_for(db, p)


# ── Caregiver links / family graph ──────────────────────────────────────────


def _to_family_member_out(
    link: CaregiverLink, other: Patient, overdue: int = 0
) -> FamilyMemberOut:
    return FamilyMemberOut(
        link_id=link.id,
        patient_id=other.id,
        nin=other.nin,
        given_name=other.given_name,
        family_name=other.family_name,
        birth_date=other.birth_date,
        gender=other.gender,
        relationship=link.relationship,
        overdue_antigen_count=overdue,
    )


@router.get(
    "/{patient_id}/family",
    response_model=list[FamilyMemberOut],
    summary="Linked family members (caregiver's children, or child's caregivers)",
)
async def list_family(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    direction: str = Query(
        "auto",
        description="'children' (caregiver-side), 'caregivers' (child-side), or 'auto' (both).",
    ),
) -> list[FamilyMemberOut]:
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    out: list[FamilyMemberOut] = []

    if direction in ("auto", "children"):
        # patient is the caregiver → list children. Bulk-load: one query for
        # the links, one for the child Patient rows, one for all child
        # Observations (in immunisation_status_for_many). Total: 3 queries
        # regardless of family size (was previously N+1 per child).
        links = (
            await db.scalars(
                select(CaregiverLink).where(CaregiverLink.caregiver_id == p.id)
            )
        ).all()
        if links:
            child_ids = [link.child_id for link in links]
            children = (
                await db.scalars(select(Patient).where(Patient.id.in_(child_ids)))
            ).all()
            by_id = {c.id: c for c in children}
            statuses = await immunisation_status_for_many(db, list(children))
            for link in links:
                child = by_id.get(link.child_id)
                if child is None:
                    continue
                child_status = statuses.get(child.id, [])
                overdue = sum(1 for s in child_status if s.status == "overdue")
                out.append(_to_family_member_out(link, child, overdue))

    if direction in ("auto", "caregivers"):
        links = (
            await db.scalars(
                select(CaregiverLink).where(CaregiverLink.child_id == p.id)
            )
        ).all()
        if links:
            adult_ids = [link.caregiver_id for link in links]
            adults = (
                await db.scalars(select(Patient).where(Patient.id.in_(adult_ids)))
            ).all()
            by_id = {a.id: a for a in adults}
            for link in links:
                adult = by_id.get(link.caregiver_id)
                if adult is None:
                    continue
                out.append(_to_family_member_out(link, adult, 0))

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read-family",
        purpose="family-coordination",
    )
    return out


@router.post(
    "/{patient_id}/caregivers",
    response_model=CaregiverLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Link a caregiver to this patient (child)",
)
async def link_caregiver(
    patient_id: str,
    body: CaregiverLinkIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> CaregiverLinkOut:
    child = await db.get(Patient, patient_id)
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Child patient not found")

    # Resolve caregiver by NIN — the worker searches by what's printed on
    # the ID card, not by internal patient ULIDs.
    caregiver = (
        await db.scalars(select(Patient).where(Patient.nin == body.caregiver_nin))
    ).one_or_none()
    if caregiver is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Caregiver with NIN {body.caregiver_nin} not enrolled — register them first.",
        )
    if caregiver.id == child.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A patient cannot be their own caregiver.",
        )

    # Idempotency: if the pair already exists, return it instead of 409.
    existing = (
        await db.scalars(
            select(CaregiverLink).where(
                CaregiverLink.caregiver_id == caregiver.id,
                CaregiverLink.child_id == child.id,
            )
        )
    ).one_or_none()
    if existing is not None:
        # Allow updating the relationship label without a new row.
        if existing.relationship != body.relationship:
            existing.relationship = body.relationship
            await db.flush()
        link = existing
    else:
        link = CaregiverLink(
            caregiver_id=caregiver.id,
            child_id=child.id,
            relationship=body.relationship,
        )
        db.add(link)
        await db.flush()

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=child.id,
        action="link-caregiver",
        purpose="family-coordination",
        extra={"caregiver_id": caregiver.id, "relationship": body.relationship},
    )
    return CaregiverLinkOut(
        id=link.id,
        caregiver_id=link.caregiver_id,
        child_id=link.child_id,
        relationship=link.relationship,
        created_at=link.created_at,
    )


@router.delete(
    "/{patient_id}/caregivers/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a caregiver from this patient",
)
async def unlink_caregiver(
    patient_id: str,
    link_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> None:
    link = await db.get(CaregiverLink, link_id)
    if link is None or link.child_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caregiver link not found")
    await db.delete(link)
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=patient_id,
        action="unlink-caregiver",
        purpose="family-coordination",
        extra={"caregiver_id": link.caregiver_id},
    )
