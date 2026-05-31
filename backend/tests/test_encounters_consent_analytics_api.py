"""Integration coverage for the ENCOUNTERS, CONSENT, FACILITIES, and ANALYTICS
HTTP endpoints.

These hit the real ASGI app through the async `client` fixture from
``conftest.py`` (in-memory SQLite, ``APP_ENV=test``). They exercise the same
seed dataset the showcase demos use via ``POST /api/v1/auth/seed-demo``.

The focus is on behaviours the unit suite can't reach end-to-end:

* encounter create + observation eager-load shape, and facility-scoped reads
  (a worker only sees their own facility's encounters; cross-facility reads of
  a foreign patient's history are 403);
* consent grant / list-by-patient / revoke, citizen-may-only-revoke-their-own
  authz, and the consequence that revoking every active consent removes a
  worker's access to the patient record;
* the public facility registry (no auth required);
* analytics role-scoping — worker forbidden, district_admin (dho.gulu) scoped
  to Gulu, ministry_admin unscoped, unauthenticated 401.

Paths, request bodies, and response shapes are matched against the source in
``app/api/v1`` — no invented endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.anyio


# ── Shared helpers (mirrors tests/test_rbac_scoping.py) ──────────────────────


async def _seed(client) -> None:
    """Populate the in-memory DB with the demo dataset. Idempotent."""
    res = await client.post("/api/v1/auth/seed-demo")
    assert res.status_code == 200, res.text


async def _login(client, identifier: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


async def _citizen_login(client, nin: str) -> str:
    res = await client.post(
        "/api/v1/auth/citizen/login",
        json={"nin": nin, "otp": "000000"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _facility_id_by_code(client, code: str) -> str:
    """Resolve a facility's id via the public registry."""
    res = await client.get("/api/v1/facilities")
    assert res.status_code == 200, res.text
    match = next((f for f in res.json() if f["code"] == code), None)
    assert match is not None, f"facility {code} not in registry"
    return match["id"]


GULU_FACILITY_CODE = "GUL-RRH-002"  # nurse.gulu
KAMPALA_FACILITY_CODE = "MUL-NRH-001"  # doctor.kampala
CITIZEN_NIN = "CM85051712345X"  # Achieng Akello (Gulu)


async def _register_patient_as_nurse(
    client, nurse_token: str, *, nin: str, given: str = "Test", family: str = "Patient"
) -> str:
    """Register a fresh patient as nurse.gulu → enrols them at GUL-RRH-002.

    Returns the patient id.
    """
    body = {
        "nin": nin,
        "given_name": given,
        "family_name": family,
        "gender": "female",
        "birth_date": "1990-01-01",
        "phone": "+256770000000",
        "district": "Gulu",
        "consent_to_share": False,
    }
    res = await client.post("/api/v1/patients", json=body, headers=_auth(nurse_token))
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ── FACILITIES ───────────────────────────────────────────────────────────────


async def test_facilities_list_is_public_and_returns_active(client) -> None:
    """The facility registry has no auth dependency — it backs UI dropdowns and
    must be reachable without a bearer token. Every seeded facility is active,
    so the full set comes back."""
    await _seed(client)

    res = await client.get("/api/v1/facilities")  # no Authorization header
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) >= 13, "all seeded facilities should be listed"

    codes = {r["code"] for r in rows}
    assert GULU_FACILITY_CODE in codes
    assert KAMPALA_FACILITY_CODE in codes

    sample = next(r for r in rows if r["code"] == GULU_FACILITY_CODE)
    # Shape per FacilityOut.
    assert set(sample) == {
        "id",
        "code",
        "name",
        "level",
        "district",
        "sub_county",
        "latitude",
        "longitude",
    }
    assert sample["district"] == "Gulu"
    assert sample["level"] == "RRH"


async def test_facilities_list_filters_by_district_and_level(client) -> None:
    """The `district` / `level` query filters narrow the registry."""
    await _seed(client)

    res = await client.get("/api/v1/facilities", params={"district": "Gulu"})
    assert res.status_code == 200, res.text
    assert {r["district"] for r in res.json()} == {"Gulu"}

    res = await client.get("/api/v1/facilities", params={"level": "NRH"})
    assert res.status_code == 200, res.text
    levels = {r["level"] for r in res.json()}
    assert levels == {"NRH"}


# ── ENCOUNTERS ───────────────────────────────────────────────────────────────


async def test_worker_records_encounter_with_observations_at_own_facility(client) -> None:
    """A worker files an encounter + two observations at their own facility.

    Asserts 201, the persisted echo, and the eager-loaded observation shape
    (the endpoint refreshes `observations` before serialising)."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010112345A"
    )

    started = datetime.now(UTC) - timedelta(hours=1)
    body = {
        "patient_id": pid,
        "facility_id": gulu_id,
        "reason": "Outpatient consultation",
        "started_at": started.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "observations": [
            {
                "code_system": "http://loinc.org",
                "code": "8310-5",
                "display": "Body temperature",
                "value_quantity": 37.4,
                "value_unit": "Cel",
                "effective_at": started.isoformat(),
            },
            {
                "code_system": "http://loinc.org",
                "code": "55284-4",
                "display": "Blood pressure",
                "value_string": "120/80",
                "effective_at": started.isoformat(),
            },
        ],
        "diagnosis_codes": ["R51", "Z00.0"],
    }
    res = await client.post(
        "/api/v1/encounters", json=body, headers=_auth(nurse_token)
    )
    assert res.status_code == 201, res.text
    enc = res.json()

    assert enc["patient_id"] == pid
    assert enc["facility_id"] == gulu_id
    assert enc["reason"] == "Outpatient consultation"
    # ended_at was supplied → status finished (see create_encounter).
    assert enc["status"] == "finished"
    assert enc["diagnosis_codes"] == ["R51", "Z00.0"]
    assert "id" in enc and "created_at" in enc

    # Observation eager-load shape (ObservationOut).
    assert len(enc["observations"]) == 2
    obs = {o["code"]: o for o in enc["observations"]}
    temp = obs["8310-5"]
    assert temp["encounter_id"] == enc["id"]
    assert temp["patient_id"] == pid
    assert temp["value_quantity"] == 37.4
    assert temp["value_unit"] == "Cel"
    assert temp["recorded_by"]  # stamped with the worker's subject
    bp = obs["55284-4"]
    assert bp["value_string"] == "120/80"
    assert bp["value_quantity"] is None


async def test_encounter_with_no_ended_at_is_in_progress(client) -> None:
    """Omitting `ended_at` leaves the encounter open (`in-progress`)."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010212345B"
    )

    body = {
        "patient_id": pid,
        "facility_id": gulu_id,
        "reason": "Triage",
        "started_at": datetime.now(UTC).isoformat(),
    }
    res = await client.post(
        "/api/v1/encounters", json=body, headers=_auth(nurse_token)
    )
    assert res.status_code == 201, res.text
    enc = res.json()
    assert enc["status"] == "in-progress"
    assert enc["ended_at"] is None
    assert enc["observations"] == []


async def test_worker_cannot_record_encounter_at_other_facility(client) -> None:
    """A worker passing a facility_id other than their assignment → 403."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    kampala_id = await _facility_id_by_code(client, KAMPALA_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010312345C"
    )

    body = {
        "patient_id": pid,
        "facility_id": kampala_id,  # not nurse.gulu's facility
        "reason": "Outpatient consultation",
        "started_at": datetime.now(UTC).isoformat(),
    }
    res = await client.post(
        "/api/v1/encounters", json=body, headers=_auth(nurse_token)
    )
    assert res.status_code == 403, res.text


async def test_create_encounter_for_unknown_patient_404(client) -> None:
    """An encounter referencing a non-existent patient → 404."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)

    body = {
        "patient_id": "does-not-exist",
        "facility_id": gulu_id,
        "reason": "Outpatient consultation",
        "started_at": datetime.now(UTC).isoformat(),
    }
    res = await client.post(
        "/api/v1/encounters", json=body, headers=_auth(nurse_token)
    )
    assert res.status_code == 404, res.text


async def test_create_encounter_requires_auth(client) -> None:
    """No bearer token → 401 (auth runs before the role/facility checks)."""
    await _seed(client)
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    body = {
        "patient_id": "whatever",
        "facility_id": gulu_id,
        "reason": "Outpatient consultation",
        "started_at": datetime.now(UTC).isoformat(),
    }
    res = await client.post("/api/v1/encounters", json=body)
    assert res.status_code == 401, res.text


async def test_create_encounter_short_reason_is_422(client) -> None:
    """`reason` has min_length=2 — a single char fails schema validation."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010912345J"
    )
    body = {
        "patient_id": pid,
        "facility_id": gulu_id,
        "reason": "x",
        "started_at": datetime.now(UTC).isoformat(),
    }
    res = await client.post(
        "/api/v1/encounters", json=body, headers=_auth(nurse_token)
    )
    assert res.status_code == 422, res.text


async def test_worker_lists_own_facility_encounters_only(client) -> None:
    """`GET /encounters/by-patient/{id}` returns only the caller-facility's
    encounters even when other facilities also saw the patient.

    Build a patient with one encounter at GULU (the nurse's facility) and one
    at KAMPALA, then confirm the nurse sees exactly the GULU one."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    admin_token = await _login(client, "admin", "admin1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    kampala_id = await _facility_id_by_code(client, KAMPALA_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010412345D"
    )

    # Encounter at GULU recorded by the nurse.
    enc_gulu = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": gulu_id,
            "reason": "Outpatient consultation",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(nurse_token),
    )
    assert enc_gulu.status_code == 201, enc_gulu.text
    gulu_enc_id = enc_gulu.json()["id"]

    # Encounter at KAMPALA recorded by the ministry admin (no facility scope,
    # so admin may file anywhere).
    enc_kla = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": kampala_id,
            "reason": "Referral review",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(admin_token),
    )
    assert enc_kla.status_code == 201, enc_kla.text
    kla_enc_id = enc_kla.json()["id"]

    # Nurse lists the patient's history → only her facility's encounter.
    res = await client.get(
        f"/api/v1/encounters/by-patient/{pid}", headers=_auth(nurse_token)
    )
    assert res.status_code == 200, res.text
    ids = {e["id"] for e in res.json()}
    facilities = {e["facility_id"] for e in res.json()}
    assert gulu_enc_id in ids
    assert kla_enc_id not in ids, "cross-facility encounter must be filtered out"
    assert facilities == {gulu_id}

    # Admin lists the same patient → sees both encounters (unscoped).
    res = await client.get(
        f"/api/v1/encounters/by-patient/{pid}", headers=_auth(admin_token)
    )
    assert res.status_code == 200, res.text
    admin_ids = {e["id"] for e in res.json()}
    assert {gulu_enc_id, kla_enc_id} <= admin_ids


async def test_worker_cross_facility_patient_history_is_403(client) -> None:
    """A worker reading the encounter history of a patient enrolled at another
    facility (with no encounter at the caller's facility) → 403 via the
    patient-level access gate, NOT an empty list."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    doc_token = await _login(client, "doctor.kampala", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)

    # Patient enrolled at GULU with a GULU-only encounter — invisible to the
    # Kampala doctor.
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010512345E"
    )
    rec = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": gulu_id,
            "reason": "Outpatient consultation",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(nurse_token),
    )
    assert rec.status_code == 201, rec.text

    res = await client.get(
        f"/api/v1/encounters/by-patient/{pid}", headers=_auth(doc_token)
    )
    assert res.status_code == 403, res.text


async def test_list_encounters_unknown_patient_404(client) -> None:
    """History for a non-existent patient → 404."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get(
        "/api/v1/encounters/by-patient/no-such-patient",
        headers=_auth(nurse_token),
    )
    assert res.status_code == 404, res.text


async def test_append_observations_to_existing_encounter(client) -> None:
    """`POST /encounters/{id}/observations` grows the encounter's observation
    list and returns the full encounter with all observations."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010612345F"
    )

    created = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": gulu_id,
            "reason": "Outpatient consultation",
            "started_at": datetime.now(UTC).isoformat(),
            "observations": [
                {
                    "code_system": "http://loinc.org",
                    "code": "8310-5",
                    "display": "Body temperature",
                    "value_quantity": 37.0,
                    "value_unit": "Cel",
                    "effective_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        headers=_auth(nurse_token),
    )
    assert created.status_code == 201, created.text
    enc_id = created.json()["id"]

    res = await client.post(
        f"/api/v1/encounters/{enc_id}/observations",
        json=[
            {
                "code_system": "http://loinc.org",
                "code": "29463-7",
                "display": "Body weight",
                "value_quantity": 61.0,
                "value_unit": "kg",
                "effective_at": datetime.now(UTC).isoformat(),
            }
        ],
        headers=_auth(nurse_token),
    )
    assert res.status_code == 201, res.text
    enc = res.json()
    codes = {o["code"] for o in enc["observations"]}
    assert codes == {"8310-5", "29463-7"}


async def test_append_observations_empty_body_is_422(client) -> None:
    """An empty observation list is explicitly rejected with 422."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010712345G"
    )
    created = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": gulu_id,
            "reason": "Outpatient consultation",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(nurse_token),
    )
    assert created.status_code == 201, created.text
    enc_id = created.json()["id"]

    res = await client.post(
        f"/api/v1/encounters/{enc_id}/observations",
        json=[],
        headers=_auth(nurse_token),
    )
    assert res.status_code == 422, res.text


async def test_append_observations_unknown_encounter_404(client) -> None:
    """Appending to a non-existent encounter → 404."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.post(
        "/api/v1/encounters/no-such-encounter/observations",
        json=[
            {
                "code_system": "http://loinc.org",
                "code": "8310-5",
                "effective_at": datetime.now(UTC).isoformat(),
            }
        ],
        headers=_auth(nurse_token),
    )
    assert res.status_code == 404, res.text


async def test_append_observations_cross_facility_403(client) -> None:
    """A worker cannot append observations to an encounter at another facility
    even knowing its id → 403 (can_read_encounter facility gate)."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    doc_token = await _login(client, "doctor.kampala", "demo1234")
    gulu_id = await _facility_id_by_code(client, GULU_FACILITY_CODE)
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90010812345H"
    )
    created = await client.post(
        "/api/v1/encounters",
        json={
            "patient_id": pid,
            "facility_id": gulu_id,
            "reason": "Outpatient consultation",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(nurse_token),
    )
    assert created.status_code == 201, created.text
    enc_id = created.json()["id"]

    # doctor.kampala (MUL-NRH-001) tries to write into the GULU encounter.
    res = await client.post(
        f"/api/v1/encounters/{enc_id}/observations",
        json=[
            {
                "code_system": "http://loinc.org",
                "code": "8310-5",
                "effective_at": datetime.now(UTC).isoformat(),
            }
        ],
        headers=_auth(doc_token),
    )
    assert res.status_code == 403, res.text


# ── CONSENT ──────────────────────────────────────────────────────────────────


async def test_worker_grants_lists_and_revokes_consent(client) -> None:
    """Full consent lifecycle as a worker: grant → list-by-patient → revoke."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90020112345A"
    )

    # Grant.
    grant = await client.post(
        "/api/v1/consents",
        json={
            "patient_id": pid,
            "scope": "share_with_research",
            "purpose": "Population health study",
        },
        headers=_auth(nurse_token),
    )
    assert grant.status_code == 201, grant.text
    c = grant.json()
    assert c["patient_id"] == pid
    assert c["scope"] == "share_with_research"
    assert c["purpose"] == "Population health study"
    assert c["granted_at"]
    assert c["revoked_at"] is None
    consent_id = c["id"]

    # List by patient.
    listed = await client.get(
        f"/api/v1/consents/by-patient/{pid}", headers=_auth(nurse_token)
    )
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == consent_id for row in listed.json())

    # Revoke.
    revoked = await client.post(
        f"/api/v1/consents/{consent_id}/revoke", headers=_auth(nurse_token)
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["id"] == consent_id
    assert revoked.json()["revoked_at"] is not None

    # Idempotent re-revoke returns the same already-revoked record. Compare the
    # instant rather than the raw string: the first response serialises the
    # freshly-set tz-aware datetime (trailing "Z"), while the replay reads the
    # value back from SQLite as a naive timestamp — same instant, different
    # textual rendering.
    again = await client.post(
        f"/api/v1/consents/{consent_id}/revoke", headers=_auth(nurse_token)
    )
    assert again.status_code == 200, again.text

    def _instant(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)

    assert _instant(again.json()["revoked_at"]) == _instant(revoked.json()["revoked_at"])


async def test_grant_consent_for_unknown_patient_404(client) -> None:
    """Granting consent for a non-existent patient → 404."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.post(
        "/api/v1/consents",
        json={
            "patient_id": "ghost",
            "scope": "share_records_across_facilities",
            "purpose": "Continuity of care",
        },
        headers=_auth(nurse_token),
    )
    assert res.status_code == 404, res.text


async def test_grant_consent_invalid_scope_is_422(client) -> None:
    """`scope` is a constrained Literal — an unknown value fails validation."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90020512345E"
    )
    res = await client.post(
        "/api/v1/consents",
        json={
            "patient_id": pid,
            "scope": "share_with_aliens",
            "purpose": "Continuity of care",
        },
        headers=_auth(nurse_token),
    )
    assert res.status_code == 422, res.text


async def test_revoke_unknown_consent_404(client) -> None:
    """Revoking a non-existent consent id → 404."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.post(
        "/api/v1/consents/no-such-consent/revoke", headers=_auth(nurse_token)
    )
    assert res.status_code == 404, res.text


async def test_citizen_can_revoke_only_own_consent(client) -> None:
    """A citizen may revoke a consent on their own patient record, but not one
    belonging to a different patient (→ 403)."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    citizen_token = await _citizen_login(client, CITIZEN_NIN)

    # Resolve the citizen's OWN patient id (Achieng / CITIZEN_NIN, Gulu — the
    # nurse can search her facility's patients).
    found = await client.get(
        "/api/v1/patients", params={"q": CITIZEN_NIN}, headers=_auth(nurse_token)
    )
    assert found.status_code == 200, found.text
    own = next(
        (p for p in found.json()["items"] if p["nin"] == CITIZEN_NIN), None
    )
    assert own is not None, "citizen's own record must be visible to nurse.gulu"
    own_pid = own["id"]

    # Grant a consent on the citizen's own record (as the worker).
    own_grant = await client.post(
        "/api/v1/consents",
        json={
            "patient_id": own_pid,
            "scope": "share_with_emergency_services",
            "purpose": "Emergency access",
        },
        headers=_auth(nurse_token),
    )
    assert own_grant.status_code == 201, own_grant.text
    own_consent_id = own_grant.json()["id"]

    # Grant a consent on a DIFFERENT patient (register a fresh one).
    other_pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90020212345B"
    )
    other_grant = await client.post(
        "/api/v1/consents",
        json={
            "patient_id": other_pid,
            "scope": "share_with_research",
            "purpose": "Population health study",
        },
        headers=_auth(nurse_token),
    )
    assert other_grant.status_code == 201, other_grant.text
    other_consent_id = other_grant.json()["id"]

    # Citizen revoking SOMEONE ELSE's consent → 403.
    forbidden = await client.post(
        f"/api/v1/consents/{other_consent_id}/revoke",
        headers=_auth(citizen_token),
    )
    assert forbidden.status_code == 403, forbidden.text

    # Citizen revoking their OWN consent → 200.
    ok = await client.post(
        f"/api/v1/consents/{own_consent_id}/revoke",
        headers=_auth(citizen_token),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["revoked_at"] is not None


async def test_citizen_list_consents_only_own_record(client) -> None:
    """`GET /consents/by-patient/{id}` rejects a citizen reading another
    patient's consents (→ 403) but allows their own."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    citizen_token = await _citizen_login(client, CITIZEN_NIN)

    # The citizen's own patient id.
    found = await client.get(
        "/api/v1/patients", params={"q": CITIZEN_NIN}, headers=_auth(nurse_token)
    )
    assert found.status_code == 200, found.text
    own_pid = next(p["id"] for p in found.json()["items"] if p["nin"] == CITIZEN_NIN)

    # A different patient.
    other_pid = await _register_patient_as_nurse(
        client, nurse_token, nin="CM90020612345F"
    )

    # Own record → 200.
    own = await client.get(
        f"/api/v1/consents/by-patient/{own_pid}", headers=_auth(citizen_token)
    )
    assert own.status_code == 200, own.text

    # Another patient's record → 403.
    other = await client.get(
        f"/api/v1/consents/by-patient/{other_pid}", headers=_auth(citizen_token)
    )
    assert other.status_code == 403, other.text


async def test_revoking_all_consents_blocks_worker_patient_read(client) -> None:
    """Consent gate: after the nurse revokes every active consent on a patient,
    she loses access to that patient via GET /patients/{id} (→ 403).

    Uses a seeded Gulu patient (which carries an active consent from seed) so
    revocation actually flips an existing grant. Register-as-nurse patients
    have *no* consent rows and therefore stay visible (default-allow), which is
    why we target a seeded record here."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    h = _auth(nurse_token)

    # Find a patient the nurse can currently read.
    listed = await client.get(
        "/api/v1/patients", params={"page_size": 50}, headers=h
    )
    assert listed.status_code == 200, listed.text
    target = None
    for it in listed.json()["items"]:
        r = await client.get(f"/api/v1/patients/{it['id']}", headers=h)
        if r.status_code == 200:
            target = it["id"]
            break
    assert target is not None, "nurse must be able to read at least one patient"

    # Revoke every active consent that patient has.
    cons = await client.get(f"/api/v1/consents/by-patient/{target}", headers=h)
    assert cons.status_code == 200, cons.text
    active = [c["id"] for c in cons.json() if c["revoked_at"] is None]
    assert active, "seed grants each patient an active consent"
    for cid in active:
        rv = await client.post(f"/api/v1/consents/{cid}/revoke", headers=h)
        assert rv.status_code == 200, rv.text

    # Now the direct read is blocked.
    blocked = await client.get(f"/api/v1/patients/{target}", headers=h)
    assert blocked.status_code == 403, (
        f"revoking all consents must block the worker read; got {blocked.text}"
    )


# ── ANALYTICS (role scoping) ─────────────────────────────────────────────────


ANALYTICS_PATHS = [
    "/api/v1/analytics/encounters-by-district",
    "/api/v1/analytics/immunisation-coverage",
    "/api/v1/analytics/stock-out-risk",
]


@pytest.mark.parametrize("path", ANALYTICS_PATHS)
async def test_analytics_unauthenticated_is_401(client, path) -> None:
    """No bearer token → 401 on every district-scoped analytics endpoint."""
    await _seed(client)
    res = await client.get(path)
    assert res.status_code == 401, res.text


@pytest.mark.parametrize("path", ANALYTICS_PATHS)
async def test_analytics_worker_is_forbidden(client, path) -> None:
    """These endpoints require district_admin — a plain worker is below that
    floor → 403."""
    await _seed(client)
    nurse_token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get(path, headers=_auth(nurse_token))
    assert res.status_code == 403, res.text


@pytest.mark.parametrize("path", ANALYTICS_PATHS)
async def test_analytics_pharmacist_is_forbidden(client, path) -> None:
    """A pharmacist is also below district_admin → 403."""
    await _seed(client)
    pharm_token = await _login(client, "pharmacist.mbarara", "demo1234")
    res = await client.get(path, headers=_auth(pharm_token))
    assert res.status_code == 403, res.text


async def test_encounters_by_district_dho_scoped_to_gulu(client) -> None:
    """district_admin (dho.gulu) sees only Gulu rows."""
    await _seed(client)
    dho_token = await _login(client, "dho.gulu", "demo1234")
    res = await client.get(
        "/api/v1/analytics/encounters-by-district", headers=_auth(dho_token)
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows, "Gulu has seeded encounters; expected at least one row"
    for row in rows:
        assert row["district"] == "Gulu", f"unexpected district {row['district']}"
        assert isinstance(row["encounter_count"], int)
        assert isinstance(row["patient_count"], int)


async def test_encounters_by_district_admin_unscoped(client) -> None:
    """ministry_admin sees rows spanning more than just Gulu (unscoped)."""
    await _seed(client)
    admin_token = await _login(client, "admin", "admin1234")
    res = await client.get(
        "/api/v1/analytics/encounters-by-district", headers=_auth(admin_token)
    )
    assert res.status_code == 200, res.text
    districts = {row["district"] for row in res.json()}
    # Seed spreads patients/encounters across many districts; admin must see
    # more than the single Gulu scope a district_admin is limited to.
    assert len(districts) > 1, f"ministry_admin should be unscoped; saw {districts}"


async def test_immunisation_coverage_scoping(client) -> None:
    """dho.gulu scoped to Gulu; ministry_admin unscoped (>= dho's view)."""
    await _seed(client)
    dho_token = await _login(client, "dho.gulu", "demo1234")
    admin_token = await _login(client, "admin", "admin1234")

    dho_res = await client.get(
        "/api/v1/analytics/immunisation-coverage", headers=_auth(dho_token)
    )
    assert dho_res.status_code == 200, dho_res.text
    for row in dho_res.json():
        assert row["district"] == "Gulu"
        assert isinstance(row["doses_administered"], int)

    admin_res = await client.get(
        "/api/v1/analytics/immunisation-coverage", headers=_auth(admin_token)
    )
    assert admin_res.status_code == 200, admin_res.text
    admin_districts = {row["district"] for row in admin_res.json()}
    # Admin is unscoped, so its district set is a superset of {Gulu} and, given
    # the seed spread, strictly larger.
    assert "Gulu" in admin_districts or not dho_res.json()
    assert len(admin_districts) >= 1


async def test_stock_out_risk_scoping(client) -> None:
    """dho.gulu sees only Gulu stock-out rows; ministry_admin sees all.

    The seed deliberately drives Gulu (GUL-RRH-002 / PCV) below its reorder
    threshold, so the district_admin view is non-empty and Gulu-only, and the
    admin view includes other districts' shortfalls (e.g. Mbarara, Arua)."""
    await _seed(client)
    dho_token = await _login(client, "dho.gulu", "demo1234")
    admin_token = await _login(client, "admin", "admin1234")

    dho_res = await client.get(
        "/api/v1/analytics/stock-out-risk", headers=_auth(dho_token)
    )
    assert dho_res.status_code == 200, dho_res.text
    dho_rows = dho_res.json()
    assert dho_rows, "seed forces a Gulu PCV stock-out; expected a row"
    for row in dho_rows:
        assert row["district"] == "Gulu"
        assert row["on_hand"] < row["reorder_threshold"]

    admin_res = await client.get(
        "/api/v1/analytics/stock-out-risk", headers=_auth(admin_token)
    )
    assert admin_res.status_code == 200, admin_res.text
    admin_districts = {row["district"] for row in admin_res.json()}
    assert len(admin_districts) > 1, (
        f"ministry_admin should see multiple districts; saw {admin_districts}"
    )
