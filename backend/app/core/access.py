"""Unified access-control helpers.

Every clinical-data path (REST + FHIR + future GraphQL/MCP) routes through
these two functions instead of inlining role checks. Keeps the access-policy
matrix in one place so audits can read it without grep-ing across endpoints.

Policy summary (read on Patient):

  ministry_admin  — any patient
  district_admin  — patients whose `enrolling_district` matches the
                    district claim on the principal
  worker          — patients enrolled at the worker's facility OR any
  pharmacist        patient with at least one encounter at that facility
                    (covers cross-facility referrals)
  citizen         — own record (NIN match) OR a record they're listed as
                    caregiver for

Policy summary (read on Encounter):

  workers / pharmacists see only their own facility's encounters even
  when the patient is shared with another facility (the patient row is
  visible, but encounter details at facility B are not).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.db.models.caregiver import CaregiverLink
from app.db.models.consent import Consent
from app.db.models.encounter import Encounter
from app.db.models.patient import Patient


async def can_read_patient(
    principal: Principal, patient: Patient, db: AsyncSession
) -> bool:
    """Return True iff the principal is allowed to read the patient record.

    This is the canonical access-control gate for both REST and FHIR.
    """
    role = principal.role
    if role == "ministry_admin":
        return True
    if role == "district_admin":
        # Fail closed for legacy tokens without district claim.
        if principal.district_id is None:
            return False
        return patient.enrolling_district == principal.district_id
    if role in ("worker", "pharmacist"):
        return await _worker_can_access_patient(principal, patient, db)
    if role == "citizen":
        return await _citizen_can_read_patient(principal, patient, db)
    return False


async def has_active_consent_for_worker(
    principal: Principal, patient: Patient, db: AsyncSession
) -> bool:
    """Verify that if the patient has any consent records, at least one is active.
    If they have no consent records at all, we default to allowing facility-scoped access.
    """
    now = datetime.now(UTC)
    stmt = select(Consent).where(Consent.patient_id == patient.id)
    all_consents = (await db.scalars(stmt)).all()
    if not all_consents:
        return True
    for c in all_consents:
        if c.revoked_at is None:
            if c.expires_at is None or c.expires_at > now:
                return True
    return False


async def _worker_can_access_patient(
    principal: Principal, patient: Patient, db: AsyncSession
) -> bool:
    """Worker / pharmacist scope: enrolled-at OR any-encounter-at this facility.

    Workers without a facility_id (uncommon) are denied.
    """
    if principal.facility_id is None:
        return False
    
    # Enforce active consent check
    if not await has_active_consent_for_worker(principal, patient, db):
        return False

    if patient.enrolling_facility_id == principal.facility_id:
        return True
    # Cross-facility referral path: if the patient has any encounter at the
    # caller's facility, they're visible. The encounter records themselves
    # remain facility-scoped (see can_read_encounter).
    has_encounter = await db.scalar(
        select(Encounter.id)
        .where(
            Encounter.patient_id == patient.id,
            Encounter.facility_id == principal.facility_id,
        )
        .limit(1)
    )
    return has_encounter is not None


async def _citizen_can_read_patient(
    principal: Principal, patient: Patient, db: AsyncSession
) -> bool:
    """Citizens see their own record or one they caregive for.

    Citizens are identified by NIN (`principal.subject == patient.nin`),
    or via a CaregiverLink row whose `caregiver_id` resolves to their NIN.
    """
    if patient.nin == principal.subject:
        return True
    me = (
        await db.scalars(select(Patient).where(Patient.nin == principal.subject))
    ).one_or_none()
    if me is None:
        return False
    link = (
        await db.scalars(
            select(CaregiverLink).where(
                CaregiverLink.caregiver_id == me.id,
                CaregiverLink.child_id == patient.id,
            )
        )
    ).one_or_none()
    return link is not None


async def can_read_encounter(
    principal: Principal, encounter: Encounter, db: AsyncSession
) -> bool:
    """Workers and pharmacists see only encounters at their own facility.

    Higher roles (district_admin, ministry_admin) fall back to the
    patient-level check (district scoping + admin override).
    """
    role = principal.role
    if role == "ministry_admin":
        return True
    if role == "district_admin":
        if principal.district_id is None:
            return True
        patient = await db.get(Patient, encounter.patient_id)
        return patient is not None and patient.enrolling_district == principal.district_id
    if role in ("worker", "pharmacist"):
        return encounter.facility_id == principal.facility_id
    if role == "citizen":
        patient = await db.get(Patient, encounter.patient_id)
        if patient is None:
            return False
        return await _citizen_can_read_patient(principal, patient, db)
    return False


def patient_visibility_filter(principal: Principal):
    """Build a SQLAlchemy WHERE clause restricting Patient queries to the
    principal's visibility scope. Returned as a list of expressions for the
    caller to AND together (or empty if the principal has unrestricted view).

    Citizen filter uses a subquery on CaregiverLink — keeps the per-row
    helper out of N+1 territory for FHIR Patient bundles.
    """
    role = principal.role
    if role == "ministry_admin":
        return []
    if role == "district_admin":
        if principal.district_id is None:
            return [Patient.id == "__no_district__"]
        return [Patient.enrolling_district == principal.district_id]
    if role in ("worker", "pharmacist"):
        if principal.facility_id is None:
            # No facility → no patients visible (instead of "all", which
            # would be a silent escalation).
            return [Patient.id == "__no_facility__"]
        # enrolled here OR has an encounter here
        return [
            (Patient.enrolling_facility_id == principal.facility_id)
            | Patient.id.in_(
                select(Encounter.patient_id).where(
                    Encounter.facility_id == principal.facility_id
                )
            )
        ]
    if role == "citizen":
        # own record OR ones linked via CaregiverLink resolved by NIN
        me_id_subq = select(Patient.id).where(Patient.nin == principal.subject)
        return [
            (Patient.nin == principal.subject)
            | Patient.id.in_(
                select(CaregiverLink.child_id).where(
                    CaregiverLink.caregiver_id.in_(me_id_subq)
                )
            )
        ]
    # Unknown role — empty visibility (deny by default).
    return [Patient.id == "__unknown_role__"]
