"""Unit tests for app.core.access gates the HTTP suite can't easily reach.

Covers the district_admin encounter fail-closed fix (H1) and worker encounter
reads honouring consent (C3b), exercised directly against the access functions
with an in-memory session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.access import can_read_encounter
from app.core.security import Principal
from app.db.models.consent import Consent
from app.db.models.encounter import Encounter
from app.db.models.facility import Facility
from app.db.models.patient import Patient

pytestmark = pytest.mark.anyio


async def _patient_with_encounter(db, *, district: str = "Gulu"):
    fac = Facility(code="HC-TST-1", name="Test HC III", level="HC III", district=district)
    db.add(fac)
    await db.flush()
    pt = Patient(
        nin="CM00000000001X",
        given_name="Aa",
        family_name="Bb",
        gender="female",
        birth_date=date(2000, 1, 1),
        district=district,
        enrolling_facility_id=fac.id,
        enrolling_district=district,
    )
    db.add(pt)
    await db.flush()
    enc = Encounter(
        patient_id=pt.id,
        facility_id=fac.id,
        reason="checkup",
        status="finished",
        started_at=datetime.now(UTC),
    )
    db.add(enc)
    await db.flush()
    return fac, pt, enc


async def test_district_admin_without_district_cannot_read_encounter(db_session):
    """H1: a district_admin token lacking the district claim must fail CLOSED on
    encounter reads. This path previously returned True (nationwide leak)."""
    _, _, enc = await _patient_with_encounter(db_session)
    principal = Principal(subject="da", role="district_admin", district_id=None)
    assert await can_read_encounter(principal, enc, db_session) is False


async def test_district_admin_in_district_can_read_encounter(db_session):
    _, _, enc = await _patient_with_encounter(db_session, district="Gulu")
    principal = Principal(subject="da", role="district_admin", district_id="Gulu")
    assert await can_read_encounter(principal, enc, db_session) is True


async def test_worker_encounter_read_requires_active_consent(db_session):
    """C3b: a worker at the encounter's facility loses encounter access once the
    patient's only consent is revoked."""
    fac, pt, enc = await _patient_with_encounter(db_session)
    worker = Principal(subject="w", role="worker", facility_id=fac.id, district_id="Gulu")

    # No consent rows → allowed (baseline purpose-of-care).
    assert await can_read_encounter(worker, enc, db_session) is True

    # Active consent → still allowed.
    consent = Consent(
        patient_id=pt.id,
        scope="share",
        purpose="care",
        granted_at=datetime.now(UTC),
        granted_by="admin",
    )
    db_session.add(consent)
    await db_session.flush()
    assert await can_read_encounter(worker, enc, db_session) is True

    # Revoked → denied.
    consent.revoked_at = datetime.now(UTC)
    await db_session.flush()
    assert await can_read_encounter(worker, enc, db_session) is False


async def test_worker_other_facility_encounter_denied(db_session):
    """A worker at a different facility can't read the encounter regardless of consent."""
    _, _, enc = await _patient_with_encounter(db_session)
    other = Principal(
        subject="w2", role="worker", facility_id="other-facility", district_id="Gulu"
    )
    assert await can_read_encounter(other, enc, db_session) is False
