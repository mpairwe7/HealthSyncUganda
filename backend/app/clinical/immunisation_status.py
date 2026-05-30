"""Shared helper for computing a patient's immunisation status.

Lives in `app.clinical` next to `unepi_schedule` rather than in any single
endpoint module so REST patients, FHIR Immunization, and the family-list
view can share it without cross-API imports.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinical.unepi_schedule import (
    CODE_TO_ANTIGEN,
    SNOMED_SYSTEM,
    _ObsLite,
    compute_immunisation_status,
)
from app.db.models.encounter import Observation
from app.db.models.patient import Patient
from app.schemas.family import AntigenStatusOut


async def immunisation_status_for(
    db: AsyncSession, patient: Patient
) -> list[AntigenStatusOut]:
    """Return per-antigen immunisation status for one patient.

    Joins the patient's vaccine Observations against the UNEPI schedule.
    """
    rows = (
        await db.scalars(
            select(Observation).where(
                Observation.patient_id == patient.id,
                Observation.code_system == SNOMED_SYSTEM,
                Observation.code.in_(list(CODE_TO_ANTIGEN.keys())),
            )
        )
    ).all()
    obs_lite = [_ObsLite(snomed_code=o.code, effective_at=o.effective_at) for o in rows]
    statuses = compute_immunisation_status(patient.birth_date, obs_lite)
    return [
        AntigenStatusOut(
            antigen=s.antigen,
            display=s.display,
            snomed_code=s.snomed_code,
            series_size=s.series_size,
            doses_given=s.doses_given,
            next_dose_number=s.next_dose_number,
            next_due_date=s.next_due_date,
            overdue_days=s.overdue_days,
            last_dose_at=s.last_dose_at,
            status=s.status,  # type: ignore[arg-type]
        )
        for s in statuses
    ]


async def immunisation_status_for_many(
    db: AsyncSession, patients: list[Patient]
) -> dict[str, list[AntigenStatusOut]]:
    """Batch variant used by family / cohort views.

    Issues two queries total (regardless of cohort size): one to bulk-load
    all vaccine Observations for the patient IDs, then in-memory grouping +
    schedule computation per patient.
    """
    if not patients:
        return {}
    patient_ids = [p.id for p in patients]
    rows = (
        await db.scalars(
            select(Observation).where(
                Observation.patient_id.in_(patient_ids),
                Observation.code_system == SNOMED_SYSTEM,
                Observation.code.in_(list(CODE_TO_ANTIGEN.keys())),
            )
        )
    ).all()
    by_patient: dict[str, list[_ObsLite]] = {pid: [] for pid in patient_ids}
    for o in rows:
        by_patient.setdefault(o.patient_id, []).append(
            _ObsLite(snomed_code=o.code, effective_at=o.effective_at)
        )

    out: dict[str, list[AntigenStatusOut]] = {}
    for p in patients:
        statuses = compute_immunisation_status(p.birth_date, by_patient.get(p.id, []))
        out[p.id] = [
            AntigenStatusOut(
                antigen=s.antigen,
                display=s.display,
                snomed_code=s.snomed_code,
                series_size=s.series_size,
                doses_given=s.doses_given,
                next_dose_number=s.next_dose_number,
                next_due_date=s.next_due_date,
                overdue_days=s.overdue_days,
                last_dose_at=s.last_dose_at,
                status=s.status,  # type: ignore[arg-type]
            )
            for s in statuses
        ]
    return out
