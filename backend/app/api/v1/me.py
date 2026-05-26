"""`/api/v1/me/*` — citizen self-serve endpoints.

The JWT subject for a citizen role is the 14-char NIN (not a patient ULID),
so every handler here resolves the calling citizen's Patient by NIN before
acting on it. Non-citizen tokens are rejected outright with 403.

Each read also records itself via ``record_access`` so the citizen's audit
page sees the very act of looking at their own data — useful transparency,
and a free demonstration of the audit trail for showcase reviewers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_access
from app.core.security import Principal, get_current_principal
from app.db.models.audit_log import AuditLog
from app.db.models.consent import Consent
from app.db.models.encounter import Encounter, Observation
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.consent import ConsentOut
from app.schemas.encounter import EncounterOut, ObservationOut
from app.schemas.me import (
    AuditEntryOut,
    ImmunisationOut,
    OwnConsentGrant,
    ProfileUpdate,
    StaffMeOut,
)
from app.schemas.patient import PatientOut

router = APIRouter(prefix="/me", tags=["me"])

# Vaccine observations are identified by SNOMED CT codes in our seed data
# (see backend/app/seed/data.py VACCINE_CODES). Filtering by code_system is
# the simplest reliable way to separate vaccines from vitals (LOINC).
_VACCINE_CODE_SYSTEM = "http://snomed.info/sct"


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _me_patient(
    principal: Principal, db: AsyncSession
) -> Patient:
    """Resolve the calling citizen's Patient record from the JWT subject.

    Raises 403 if the caller is not a citizen, 404 if no Patient row exists
    for the NIN (would mean a stale NIRA token).
    """
    if principal.role != "citizen":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "/me/* endpoints are for citizen tokens only",
        )
    patient = (
        await db.scalars(select(Patient).where(Patient.nin == principal.subject))
    ).one_or_none()
    if patient is None:
        # The JWT is valid but the citizen's patient row doesn't exist
        # locally yet — could happen if a worker never enrolled them.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No patient record found for your NIN — please visit a facility to enrol.",
        )
    return patient


def _patient_to_out(p: Patient) -> PatientOut:
    return PatientOut(
        id=p.id,
        nin=p.nin,
        given_name=p.given_name,
        family_name=p.family_name,
        gender=p.gender,
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


def _consent_to_out(c: Consent) -> ConsentOut:
    return ConsentOut(
        id=c.id,
        patient_id=c.patient_id,
        scope=c.scope,
        purpose=c.purpose,
        granted_at=c.granted_at,
        expires_at=c.expires_at,
        revoked_at=c.revoked_at,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=PatientOut, summary="Get my own patient record")
async def me(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PatientOut:
    p = await _me_patient(principal, db)
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read-self",
        purpose="citizen-self-service",
    )
    return _patient_to_out(p)


@router.get(
    "/encounters",
    response_model=list[EncounterOut],
    summary="List my own encounter history",
)
async def my_encounters(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> list[EncounterOut]:
    p = await _me_patient(principal, db)
    rows = (
        await db.scalars(
            select(Encounter)
            .where(Encounter.patient_id == p.id)
            .order_by(Encounter.started_at.desc())
        )
    ).all()
    for r in rows:
        await db.refresh(r, attribute_names=["observations"])
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read-history-self",
        purpose="citizen-self-service",
    )
    out: list[EncounterOut] = []
    for enc in rows:
        out.append(
            EncounterOut(
                id=enc.id,
                patient_id=enc.patient_id,
                facility_id=enc.facility_id,
                reason=enc.reason,
                status=enc.status,
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
        )
    return out


@router.get(
    "/immunisations",
    response_model=list[ImmunisationOut],
    summary="List my own vaccine administrations",
)
async def my_immunisations(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> list[ImmunisationOut]:
    p = await _me_patient(principal, db)
    # Find observations whose code_system marks them as a vaccine (SNOMED CT
    # in our seed; production would broaden this to UNEPI codings).
    rows = (
        await db.scalars(
            select(Observation)
            .where(
                Observation.patient_id == p.id,
                Observation.code_system == _VACCINE_CODE_SYSTEM,
            )
            .order_by(Observation.effective_at.desc())
        )
    ).all()

    # Encounter → facility lookup (single query)
    encounter_ids = list({o.encounter_id for o in rows})
    facility_by_encounter: dict[str, str] = {}
    if encounter_ids:
        enc_rows = (
            await db.scalars(
                select(Encounter).where(Encounter.id.in_(encounter_ids))
            )
        ).all()
        facility_by_encounter = {e.id: e.facility_id for e in enc_rows}

    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="read-immunisations-self",
        purpose="citizen-self-service",
    )

    return [
        ImmunisationOut(
            id=o.id,
            encounter_id=o.encounter_id,
            patient_id=o.patient_id,
            code_system=o.code_system,
            code=o.code,
            display=o.display,
            administered_at=o.effective_at,
            facility_id=facility_by_encounter.get(o.encounter_id),
        )
        for o in rows
    ]


@router.get(
    "/audit",
    response_model=list[AuditEntryOut],
    summary="Who has accessed my record",
)
async def my_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    since_days: Annotated[int, Query(ge=1, le=365, description="Window in days (1-365)")] = 90,
) -> list[AuditEntryOut]:
    p = await _me_patient(principal, db)
    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.resource_type == "Patient",
                AuditLog.resource_id == p.id,
                AuditLog.created_at >= cutoff,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(500)
        )
    ).all()
    # Note: we do NOT record_access here. /me/audit is itself an access
    # event but auditing it would be infinitely recursive on the next read.
    return [
        AuditEntryOut(
            id=r.id,
            actor_role=r.actor_role,
            actor_facility_id=r.actor_facility_id,
            action=r.action,
            purpose=r.purpose,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            consent_id=r.consent_id,
            occurred_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/consent/grant",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a consent on my own record",
)
async def grant_own_consent(
    body: OwnConsentGrant,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ConsentOut:
    p = await _me_patient(principal, db)
    c = Consent(
        patient_id=p.id,
        scope=body.scope,
        purpose=body.purpose,
        granted_at=datetime.now(UTC),
        expires_at=body.expires_at,
        # granted_by is the citizen themselves (NIN as the actor)
        granted_by=principal.subject,
    )
    db.add(c)
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Consent",
        resource_id=c.id,
        action="grant-self",
        purpose=body.purpose,
    )
    return _consent_to_out(c)


@router.patch(
    "/profile",
    response_model=PatientOut,
    summary="Update my own contact details",
)
async def update_profile(
    body: ProfileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PatientOut:
    p = await _me_patient(principal, db)
    changes: dict[str, str | None] = {}
    if body.phone is not None:
        p.phone = body.phone
        changes["phone"] = body.phone
    if body.email is not None:
        p.email = body.email
        changes["email"] = body.email
    if body.sub_county is not None:
        p.sub_county = body.sub_county
        changes["sub_county"] = body.sub_county
    if body.parish is not None:
        p.parish = body.parish
        changes["parish"] = body.parish
    if body.village is not None:
        p.village = body.village
        changes["village"] = body.village
    p.record_version = p.record_version + 1
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="update-profile-self",
        purpose="citizen-self-service",
        extra={"changed_fields": list(changes.keys())},
    )
    return _patient_to_out(p)


# ── Staff self-serve ────────────────────────────────────────────────────────


@router.get(
    "/staff",
    response_model=StaffMeOut,
    summary="My staff profile + facility context",
)
async def me_staff(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> StaffMeOut:
    """Resolve the calling staff member's User row + their facility name/level.

    The citizen `/me` endpoint is the counterpart for citizen tokens; this is
    its staff-side mirror. Refuses citizen tokens with 403.

    Looks up `User.id == principal.subject` (for staff tokens, the JWT
    subject is the user ULID — confirmed in `app/api/v1/auth.py`
    `staff_login`).
    """
    if principal.role == "citizen":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "/me/staff is for staff tokens only — use /me for citizen profiles",
        )

    user = await db.get(User, principal.subject)
    if user is None:
        # JWT is valid but the staff row was deleted/disabled between login
        # and this call — surface as 404 so the client can sign-out cleanly.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Staff record not found — your session may be stale.",
        )

    facility: Facility | None = None
    if user.facility_id:
        facility = await db.get(Facility, user.facility_id)

    return StaffMeOut(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        facility_id=user.facility_id,
        facility_name=facility.name if facility else None,
        facility_level=facility.level if facility else None,
        facility_district=facility.district if facility else None,
        active=user.active,
    )
