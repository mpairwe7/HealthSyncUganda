"""Comprehensive coverage for the PATIENT endpoints (app/api/v1/patients.py).

Covers search/list, get-by-id, create, update, the caregiver/family-link
graph, and per-antigen immunisation status — across every relevant role and
the authz / validation / not-found branches.

Integration style (mirrors tests/test_rbac_scoping.py): the in-memory SQLite
app from conftest's `client` fixture, populated via POST /api/v1/auth/seed-demo.
Helpers are defined locally per the project convention.

Design note on determinism
--------------------------
The seed's encounter generator picks each visit's facility at random, and a
patient's `enrolling_district` / `enrolling_facility_id` are denormalised from
that *first* encounter — so which seed patients a worker / district_admin can
see is NOT deterministic across runs. (Note in particular that the residence
`district` shown in a PatientSummary is the patient's home district, which is
independent of `enrolling_district`; scoping keys off the latter.)

Where scoping / authz must be asserted exactly, these tests therefore ENROL
their own patients via `POST /patients` as a chosen worker — that anchors the
new record at the worker's facility/district deterministically — instead of
relying on whichever seed rows happened to land at a given site. Seed data is
still used where it is deterministic (the self-service citizen's own record,
the seeded caregiver→child links, and free-text search by known name/NIN).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.anyio


# ── Local helpers (same contract as tests/test_rbac_scoping.py) ──────────────

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


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Known seed constants (from app/seed/data.py).
CITIZEN_NIN = "CM85051712345X"          # Achieng Akello — self-service citizen
SEED_CAREGIVER_NIN = "CF93081244778K"   # Namaganda Nakitende — mother of 2 children
SEED_CHILD_NIN = "CM23071955443Q"       # Kintu Ssempa — Wakiso toddler (her child)


def _unique_nin(prefix: str = "CM") -> str:
    """Build a fresh, schema-valid NIN (14 chars, starts CM/CF, then digits).

    Random tail so repeated POSTs in one test never collide on the unique NIN.
    """
    tail = f"{uuid.uuid4().int % 10**12:012d}"
    return f"{prefix}{tail}"


def _patient_body(nin: str, **overrides) -> dict:
    body = {
        "nin": nin,
        "given_name": "Test",
        "family_name": "Patient",
        "gender": "male",
        "birth_date": "1980-01-15",
        "district": "Gulu",
        "consent_to_share": False,
    }
    body.update(overrides)
    return body


async def _enrol(client, token: str, nin: str, **overrides) -> dict:
    """Enrol a patient via POST /patients as `token`'s worker and return it.

    Anchors the new patient at that worker's facility/district — the only
    deterministic way to control RBAC scope for the assertions below.
    """
    res = await client.post(
        "/api/v1/patients", json=_patient_body(nin, **overrides), headers=_h(token)
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _find_own_patient_id(client, admin_token: str, nin: str) -> str:
    """Resolve a patient's id by NIN via the admin (sees everything) search.

    Citizens can't use the worker search endpoint, so this is how a test
    discovers the citizen's own record id to then read it as the citizen.
    """
    res = await client.get(
        "/api/v1/patients", params={"q": nin, "page_size": 100}, headers=_h(admin_token)
    )
    assert res.status_code == 200, res.text
    hits = [p for p in res.json()["items"] if p["nin"] == nin]
    assert hits, f"expected a seeded patient with NIN {nin}"
    return hits[0]["id"]


# ── search / list ────────────────────────────────────────────────────────────

async def test_search_admin_sees_all_patients(client) -> None:
    """ministry_admin has unrestricted Patient visibility — total reflects the
    full seed population (26 demo patients)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")

    res = await client.get("/api/v1/patients", params={"page_size": 100}, headers=_h(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["page"] == 1
    assert body["page_size"] == 100
    assert body["total"] == 26
    assert len(body["items"]) == 26
    # PatientSummary shape — lightweight list payload.
    assert set(body["items"][0].keys()) == {
        "id", "nin", "given_name", "family_name", "gender", "birth_date", "district",
    }


async def test_search_worker_is_facility_scoped(client) -> None:
    """A worker sees only patients in their facility scope. A patient enrolled
    at another facility (no encounter at the worker's site) must not appear,
    while one enrolled at the worker's own facility must."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")          # GUL-RRH-002
    doctor = await _login(client, "doctor.kampala", "demo1234")     # MUL-NRH-001
    admin = await _login(client, "admin", "admin1234")

    mine = await _enrol(client, nurse, _unique_nin(), given_name="Gulu", family_name="Local")
    theirs = await _enrol(
        client, doctor, _unique_nin(), district="Kampala",
        given_name="Kla", family_name="Elsewhere",
    )

    res = await client.get("/api/v1/patients", params={"page_size": 100}, headers=_h(nurse))
    assert res.status_code == 200, res.text
    visible = {p["id"] for p in res.json()["items"]}
    assert mine["id"] in visible, "worker must see a patient enrolled at her facility"
    assert theirs["id"] not in visible, "worker must NOT see a patient enrolled elsewhere"

    # Sanity: admin sees both, confirming `theirs` really exists.
    res = await client.get("/api/v1/patients", params={"page_size": 100}, headers=_h(admin))
    all_ids = {p["id"] for p in res.json()["items"]}
    assert {mine["id"], theirs["id"]} <= all_ids


async def test_search_district_admin_is_district_scoped(client) -> None:
    """district_admin (Gulu) sees patients whose enrolling district is Gulu and
    not those enrolled in another district. Enrolment via a worker at a Gulu
    facility vs a Kampala facility makes the scope deterministic."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")          # Gulu
    doctor = await _login(client, "doctor.kampala", "demo1234")     # Kampala
    dho = await _login(client, "dho.gulu", "demo1234")              # district_admin, Gulu

    gulu_patient = await _enrol(
        client, nurse, _unique_nin(), given_name="Dho", family_name="InGulu"
    )
    kla_patient = await _enrol(
        client, doctor, _unique_nin(), district="Kampala",
        given_name="Dho", family_name="InKla",
    )

    res = await client.get("/api/v1/patients", params={"page_size": 100}, headers=_h(dho))
    assert res.status_code == 200, res.text
    visible = {p["id"] for p in res.json()["items"]}
    assert gulu_patient["id"] in visible, "district_admin must see same-district enrolment"
    assert kla_patient["id"] not in visible, "district_admin must not see other districts"


async def test_search_citizen_forbidden(client) -> None:
    """The search endpoint requires role >= worker; a citizen token is 403."""
    await _seed(client)
    citizen = await _citizen_login(client, CITIZEN_NIN)
    res = await client.get("/api/v1/patients", headers=_h(citizen))
    assert res.status_code == 403, res.text


async def test_search_unauthenticated_rejected(client) -> None:
    """No bearer token → 401 (search is not public)."""
    await _seed(client)
    res = await client.get("/api/v1/patients")
    assert res.status_code == 401, res.text


async def test_search_free_text_by_name_nin_and_phone(client) -> None:
    """Free-text `q` matches given/family name, NIN, and phone. Use admin so the
    visibility filter never hides the target, and a freshly-enrolled patient with
    known fields so the match is exact and deterministic."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    nin = _unique_nin()
    created = await _enrol(
        client, admin, nin,
        given_name="Zaphod", family_name="Beeblebrox",
        phone="+256770424242", district="Gulu",
    )

    # by family name (case-insensitive — endpoint lower-cases both sides)
    res = await client.get("/api/v1/patients", params={"q": "beeblebrox"}, headers=_h(admin))
    assert res.status_code == 200, res.text
    assert created["id"] in {p["id"] for p in res.json()["items"]}

    # by given name
    res = await client.get("/api/v1/patients", params={"q": "Zaphod"}, headers=_h(admin))
    assert created["id"] in {p["id"] for p in res.json()["items"]}

    # by NIN
    res = await client.get("/api/v1/patients", params={"q": nin}, headers=_h(admin))
    assert created["id"] in {p["id"] for p in res.json()["items"]}

    # by phone fragment (stored normalised to +256770424242)
    res = await client.get("/api/v1/patients", params={"q": "770424242"}, headers=_h(admin))
    assert created["id"] in {p["id"] for p in res.json()["items"]}


async def test_search_empty_results(client) -> None:
    """A query that matches nothing returns an empty page with total 0, not an
    error."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.get(
        "/api/v1/patients", params={"q": "zzz-no-such-patient-xyz"}, headers=_h(admin)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_search_pagination_bounds_and_paging(client) -> None:
    """page_size is clamped to 1..100 (422 outside), page must be >= 1, and
    paging actually walks distinct, non-overlapping result windows."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")

    # page_size below the minimum
    res = await client.get("/api/v1/patients", params={"page_size": 0}, headers=_h(admin))
    assert res.status_code == 422, res.text
    # page_size above the maximum (le=100)
    res = await client.get("/api/v1/patients", params={"page_size": 101}, headers=_h(admin))
    assert res.status_code == 422, res.text
    # page below the minimum (ge=1)
    res = await client.get("/api/v1/patients", params={"page": 0}, headers=_h(admin))
    assert res.status_code == 422, res.text

    # Valid small page_size limits the item count and echoes the paging params.
    res = await client.get(
        "/api/v1/patients", params={"page": 1, "page_size": 5}, headers=_h(admin)
    )
    assert res.status_code == 200, res.text
    p1 = res.json()
    assert p1["page"] == 1 and p1["page_size"] == 5
    assert p1["total"] == 26
    assert len(p1["items"]) == 5

    res = await client.get(
        "/api/v1/patients", params={"page": 2, "page_size": 5}, headers=_h(admin)
    )
    assert res.status_code == 200, res.text
    p2 = res.json()
    assert p2["page"] == 2
    assert len(p2["items"]) == 5
    # Distinct windows — no overlap between page 1 and page 2.
    assert not ({i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]})


async def test_search_district_query_param_filters(client) -> None:
    """The `district` query param narrows results by residence district. Admin
    bypasses scope so the filter itself is what is exercised."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.get(
        "/api/v1/patients", params={"district": "Mbarara", "page_size": 100}, headers=_h(admin)
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items, "seed includes Mbarara residents"
    assert all(p["district"] == "Mbarara" for p in items)


# ── get-by-id ────────────────────────────────────────────────────────────────

async def test_get_by_id_admin_ok(client) -> None:
    """ministry_admin can read any record by id; PatientOut shape is returned."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    pid = await _find_own_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/api/v1/patients/{pid}", headers=_h(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == pid
    assert body["nin"] == CITIZEN_NIN
    # PatientOut carries the full demographic + audit-ish fields.
    for key in ("given_name", "family_name", "gender", "birth_date",
                "district", "created_at", "updated_at", "deceased", "record_version"):
        assert key in body


async def test_get_by_id_worker_own_facility_ok_other_facility_403(client) -> None:
    """A worker reads a patient enrolled at her facility (200) but is forbidden
    from one enrolled at another facility with no local encounter (403)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    doctor = await _login(client, "doctor.kampala", "demo1234")

    mine = await _enrol(client, nurse, _unique_nin())
    theirs = await _enrol(client, doctor, _unique_nin(), district="Kampala")

    res = await client.get(f"/api/v1/patients/{mine['id']}", headers=_h(nurse))
    assert res.status_code == 200, res.text

    res = await client.get(f"/api/v1/patients/{theirs['id']}", headers=_h(nurse))
    assert res.status_code == 403, res.text


async def test_get_by_id_district_admin_scope(client) -> None:
    """district_admin (Gulu) gets 200 for a Gulu-enrolled patient and 403 for a
    Kampala-enrolled one."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    doctor = await _login(client, "doctor.kampala", "demo1234")
    dho = await _login(client, "dho.gulu", "demo1234")

    gulu_patient = await _enrol(client, nurse, _unique_nin())
    kla_patient = await _enrol(client, doctor, _unique_nin(), district="Kampala")

    res = await client.get(f"/api/v1/patients/{gulu_patient['id']}", headers=_h(dho))
    assert res.status_code == 200, res.text
    res = await client.get(f"/api/v1/patients/{kla_patient['id']}", headers=_h(dho))
    assert res.status_code == 403, res.text


async def test_get_by_id_citizen_own_200_other_403(client) -> None:
    """A citizen can read their own record (200) but not a stranger's (403),
    even though authentication succeeds."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen = await _citizen_login(client, CITIZEN_NIN)

    own_id = await _find_own_patient_id(client, admin, CITIZEN_NIN)
    res = await client.get(f"/api/v1/patients/{own_id}", headers=_h(citizen))
    assert res.status_code == 200, res.text
    assert res.json()["nin"] == CITIZEN_NIN

    other_id = await _find_own_patient_id(client, admin, SEED_CHILD_NIN)
    res = await client.get(f"/api/v1/patients/{other_id}", headers=_h(citizen))
    assert res.status_code == 403, res.text


async def test_get_by_id_404_for_missing(client) -> None:
    """An unknown patient id returns 404 (not 403/500)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.get("/api/v1/patients/01JZZZZZZZZZZZZZZZZZZZZZZZZ", headers=_h(admin))
    assert res.status_code == 404, res.text


async def test_get_by_id_accepts_purpose_audit_query_param(client) -> None:
    """The `purpose` query param (recorded in the audit trail) is accepted and
    does not change the 200 outcome."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    pid = await _find_own_patient_id(client, admin, CITIZEN_NIN)
    res = await client.get(
        f"/api/v1/patients/{pid}", params={"purpose": "research-audit"}, headers=_h(admin)
    )
    assert res.status_code == 200, res.text
    assert res.json()["id"] == pid


async def test_get_by_id_unauthenticated_rejected(client) -> None:
    """No bearer token → 401 even before the record is looked up."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    pid = await _find_own_patient_id(client, admin, CITIZEN_NIN)
    res = await client.get(f"/api/v1/patients/{pid}")
    assert res.status_code == 401, res.text


# ── create ───────────────────────────────────────────────────────────────────

async def test_create_worker_enrols_at_own_facility(client) -> None:
    """A worker enrols a new patient (201). The record is anchored at the
    worker's facility/district: the worker can read it back, a worker at a
    different facility cannot, and the same-district admin can."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    doctor = await _login(client, "doctor.kampala", "demo1234")
    dho = await _login(client, "dho.gulu", "demo1234")

    nin = _unique_nin()
    res = await client.post(
        "/api/v1/patients", json=_patient_body(nin, given_name="Enrol", family_name="Me"),
        headers=_h(nurse),
    )
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["nin"] == nin
    assert created["given_name"] == "Enrol"
    assert created["record_version"] == 1
    assert created["deceased"] is False
    pid = created["id"]

    # Anchored at GUL-RRH-002: enrolling worker reads it, Kampala worker 403s.
    assert (await client.get(f"/api/v1/patients/{pid}", headers=_h(nurse))).status_code == 200
    assert (await client.get(f"/api/v1/patients/{pid}", headers=_h(doctor))).status_code == 403
    # Gulu district_admin sees it (enrolling_district == Gulu).
    assert (await client.get(f"/api/v1/patients/{pid}", headers=_h(dho))).status_code == 200


async def test_create_nin_conflict_returns_409(client) -> None:
    """Enrolling a NIN that already exists returns 409 Conflict."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    nin = _unique_nin()

    res = await client.post("/api/v1/patients", json=_patient_body(nin), headers=_h(nurse))
    assert res.status_code == 201, res.text

    res = await client.post("/api/v1/patients", json=_patient_body(nin), headers=_h(nurse))
    assert res.status_code == 409, res.text
    assert nin in res.json()["detail"]


async def test_create_conflict_with_seeded_nin(client) -> None:
    """A seed NIN already exists, so a create with it is a 409 too (covers the
    'patient already enrolled by seed' path)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    res = await client.post(
        "/api/v1/patients", json=_patient_body(CITIZEN_NIN, district="Gulu"), headers=_h(nurse)
    )
    assert res.status_code == 409, res.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("nin", "NOTANIN"),            # fails NIN regex (must start CM/CF, 14 chars)
        ("nin", "CM12345"),           # right prefix, wrong length
        ("gender", "alien"),          # not in {male,female,other,unknown}
        ("birth_date", "not-a-date"),  # unparseable date
        ("given_name", ""),           # min_length=1
        ("district", ""),             # min_length=1
    ],
)
async def test_create_invalid_payload_returns_422(client, field, value) -> None:
    """Schema validation (NIN format, gender enum, date parsing, required-field
    length) rejects bad input with 422."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    body = _patient_body(_unique_nin())
    body[field] = value
    res = await client.post("/api/v1/patients", json=body, headers=_h(nurse))
    assert res.status_code == 422, f"{field}={value!r}: {res.text}"


async def test_create_missing_required_field_returns_422(client) -> None:
    """Omitting a required field (e.g. family_name) is a 422."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    body = _patient_body(_unique_nin())
    del body["family_name"]
    res = await client.post("/api/v1/patients", json=body, headers=_h(nurse))
    assert res.status_code == 422, res.text


async def test_create_citizen_forbidden(client) -> None:
    """Citizens cannot enrol patients (endpoint requires role >= worker)."""
    await _seed(client)
    citizen = await _citizen_login(client, CITIZEN_NIN)
    res = await client.post(
        "/api/v1/patients", json=_patient_body(_unique_nin()), headers=_h(citizen)
    )
    assert res.status_code == 403, res.text


async def test_create_unauthenticated_rejected(client) -> None:
    """No token → 401."""
    await _seed(client)
    res = await client.post("/api/v1/patients", json=_patient_body(_unique_nin()))
    assert res.status_code == 401, res.text


async def test_create_pharmacist_allowed_by_role(client) -> None:
    """require_role('worker') is a minimum: a pharmacist (ranked above worker)
    may enrol. The record anchors at the pharmacist's facility."""
    await _seed(client)
    pharmacist = await _login(client, "pharmacist.mbarara", "demo1234")  # MBR-RRH-003
    nin = _unique_nin()
    res = await client.post(
        "/api/v1/patients", json=_patient_body(nin, district="Mbarara"), headers=_h(pharmacist)
    )
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    # Pharmacist can read back what they enrolled (own facility scope).
    assert (await client.get(f"/api/v1/patients/{pid}", headers=_h(pharmacist))).status_code == 200


# ── update (PATCH) ───────────────────────────────────────────────────────────

async def test_update_happy_path_increments_version(client) -> None:
    """A partial update applies only the supplied fields, bumps record_version,
    and leaves untouched fields intact. Phone is normalised by the schema."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    created = await _enrol(client, nurse, _unique_nin(), village="OldVillage")
    pid = created["id"]
    assert created["record_version"] == 1

    res = await client.patch(
        f"/api/v1/patients/{pid}",
        json={"village": "NewVillage", "phone": "0772999888"},
        headers=_h(nurse),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["village"] == "NewVillage"
    assert body["phone"] == "+256772999888"   # normalised to +256 form
    assert body["record_version"] == 2
    # Unsupplied fields unchanged.
    assert body["given_name"] == created["given_name"]
    assert body["nin"] == created["nin"]


async def test_update_authz_other_facility_403(client) -> None:
    """A worker cannot update a patient outside their facility scope (403)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    doctor = await _login(client, "doctor.kampala", "demo1234")
    theirs = await _enrol(client, doctor, _unique_nin(), district="Kampala")

    res = await client.patch(
        f"/api/v1/patients/{theirs['id']}", json={"village": "X"}, headers=_h(nurse)
    )
    assert res.status_code == 403, res.text


async def test_update_citizen_forbidden(client) -> None:
    """Citizens cannot PATCH demographics (endpoint requires role >= worker)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen = await _citizen_login(client, CITIZEN_NIN)
    own_id = await _find_own_patient_id(client, admin, CITIZEN_NIN)
    res = await client.patch(
        f"/api/v1/patients/{own_id}", json={"village": "Nope"}, headers=_h(citizen)
    )
    assert res.status_code == 403, res.text


async def test_update_404_for_missing(client) -> None:
    """PATCH of a non-existent id is 404."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    res = await client.patch(
        "/api/v1/patients/01JZZZZZZZZZZZZZZZZZZZZZZZZ", json={"village": "X"}, headers=_h(nurse)
    )
    assert res.status_code == 404, res.text


async def test_update_invalid_phone_returns_422(client) -> None:
    """An invalid phone in the PATCH body fails schema validation (422)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    created = await _enrol(client, nurse, _unique_nin())
    res = await client.patch(
        f"/api/v1/patients/{created['id']}", json={"phone": "12345"}, headers=_h(nurse)
    )
    assert res.status_code == 422, res.text


# ── immunisation / antigen status ────────────────────────────────────────────

async def test_immunisation_status_worker_returns_antigen_rows(client) -> None:
    """A worker reads per-antigen immunisation status for an in-scope patient.
    The seeded self-service citizen has immunisation observations, so the
    response is a non-empty list of AntigenStatusOut rows."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen_pid = await _find_own_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/api/v1/patients/{citizen_pid}/immunisation-status", headers=_h(admin))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert isinstance(rows, list) and rows, "seed patient has vaccine observations"
    row = rows[0]
    for key in ("antigen", "display", "snomed_code", "series_size",
                "doses_given", "status"):
        assert key in row
    assert row["status"] in {"complete", "due", "due-soon", "overdue", "not-yet"}


async def test_immunisation_status_citizen_own_record(client) -> None:
    """A citizen can read their own immunisation status (200)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen = await _citizen_login(client, CITIZEN_NIN)
    own_id = await _find_own_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/api/v1/patients/{own_id}/immunisation-status", headers=_h(citizen))
    assert res.status_code == 200, res.text
    assert isinstance(res.json(), list)


async def test_immunisation_status_authz_other_facility_403(client) -> None:
    """Immunisation status is gated by the same patient-read check: a worker is
    forbidden for an out-of-scope patient (403)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    doctor = await _login(client, "doctor.kampala", "demo1234")
    theirs = await _enrol(client, doctor, _unique_nin(), district="Kampala")

    res = await client.get(
        f"/api/v1/patients/{theirs['id']}/immunisation-status", headers=_h(nurse)
    )
    assert res.status_code == 403, res.text


async def test_immunisation_status_404_for_missing(client) -> None:
    """Immunisation status for an unknown patient id is 404."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.get(
        "/api/v1/patients/01JZZZZZZZZZZZZZZZZZZZZZZZZ/immunisation-status", headers=_h(admin)
    )
    assert res.status_code == 404, res.text


# ── caregiver / family links ─────────────────────────────────────────────────

async def test_family_caregiver_side_lists_children(client) -> None:
    """For a seeded caregiver, direction='children' lists their linked children
    with FamilyMemberOut fields (including overdue_antigen_count)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    caregiver_id = await _find_own_patient_id(client, admin, SEED_CAREGIVER_NIN)

    res = await client.get(
        f"/api/v1/patients/{caregiver_id}/family",
        params={"direction": "children"}, headers=_h(admin),
    )
    assert res.status_code == 200, res.text
    members = res.json()
    assert members, "seed links this caregiver to children"
    member = members[0]
    for key in ("link_id", "patient_id", "nin", "given_name", "family_name",
                "birth_date", "gender", "relationship", "overdue_antigen_count"):
        assert key in member
    # The seeded child is among the listed children.
    assert SEED_CHILD_NIN in {m["nin"] for m in members}


async def test_family_child_side_lists_caregivers(client) -> None:
    """For a seeded child, direction='caregivers' lists the linked caregiver(s),
    and the seeded mother appears among them."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    child_id = await _find_own_patient_id(client, admin, SEED_CHILD_NIN)

    res = await client.get(
        f"/api/v1/patients/{child_id}/family",
        params={"direction": "caregivers"}, headers=_h(admin),
    )
    assert res.status_code == 200, res.text
    members = res.json()
    assert members, "seed links this child to a caregiver"
    assert SEED_CAREGIVER_NIN in {m["nin"] for m in members}


async def test_family_404_for_missing(client) -> None:
    """Family graph for an unknown patient id is 404."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.get(
        "/api/v1/patients/01JZZZZZZZZZZZZZZZZZZZZZZZZ/family", headers=_h(admin)
    )
    assert res.status_code == 404, res.text


async def test_family_authz_citizen_other_record_403(client) -> None:
    """A citizen cannot read another patient's family graph (same read gate)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen = await _citizen_login(client, CITIZEN_NIN)
    other_id = await _find_own_patient_id(client, admin, SEED_CHILD_NIN)

    res = await client.get(f"/api/v1/patients/{other_id}/family", headers=_h(citizen))
    assert res.status_code == 403, res.text


async def test_link_caregiver_happy_path_then_appears_in_family(client) -> None:
    """A worker links a caregiver (by NIN) to a child they enrolled; the link is
    returned (201, CaregiverLinkOut) and then surfaces in the child's family
    listing on the caregivers side."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    # Enrol both child and caregiver at the nurse's facility so she can read both.
    child = await _enrol(client, nurse, _unique_nin(), given_name="Child", family_name="Linkme")
    caregiver_nin = _unique_nin("CF")
    await _enrol(client, nurse, caregiver_nin, given_name="Care", family_name="Giver")

    res = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "mother"},
        headers=_h(nurse),
    )
    assert res.status_code == 201, res.text
    link = res.json()
    assert set(link.keys()) == {"id", "caregiver_id", "child_id", "relationship", "created_at"}
    assert link["child_id"] == child["id"]
    assert link["relationship"] == "mother"
    link_id = link["id"]

    # Now visible from the child's caregivers-side family view.
    res = await client.get(
        f"/api/v1/patients/{child['id']}/family",
        params={"direction": "caregivers"}, headers=_h(nurse),
    )
    assert res.status_code == 200, res.text
    assert caregiver_nin in {m["nin"] for m in res.json()}

    # Cleanup path: unlink returns 204 and removes the link.
    res = await client.delete(
        f"/api/v1/patients/{child['id']}/caregivers/{link_id}", headers=_h(nurse)
    )
    assert res.status_code == 204, res.text
    res = await client.get(
        f"/api/v1/patients/{child['id']}/family",
        params={"direction": "caregivers"}, headers=_h(nurse),
    )
    assert res.status_code == 200, res.text
    assert caregiver_nin not in {m["nin"] for m in res.json()}


async def test_link_caregiver_is_idempotent(client) -> None:
    """Re-linking the same caregiver→child pair returns the existing link
    (same id) rather than erroring, and can update the relationship label."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    child = await _enrol(client, nurse, _unique_nin())
    caregiver_nin = _unique_nin("CF")
    await _enrol(client, nurse, caregiver_nin)

    res1 = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "guardian"},
        headers=_h(nurse),
    )
    assert res1.status_code == 201, res1.text

    res2 = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "mother"},
        headers=_h(nurse),
    )
    assert res2.status_code == 201, res2.text
    assert res2.json()["id"] == res1.json()["id"]        # same row, no duplicate
    assert res2.json()["relationship"] == "mother"        # label updated in place


async def test_link_caregiver_unknown_caregiver_nin_404(client) -> None:
    """Linking a caregiver whose NIN isn't enrolled returns 404."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    child = await _enrol(client, nurse, _unique_nin())
    res = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": _unique_nin("CF"), "relationship": "guardian"},
        headers=_h(nurse),
    )
    assert res.status_code == 404, res.text


async def test_link_caregiver_unknown_child_404(client) -> None:
    """Linking against a non-existent child patient id returns 404."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    caregiver_nin = _unique_nin("CF")
    await _enrol(client, nurse, caregiver_nin)
    res = await client.post(
        "/api/v1/patients/01JZZZZZZZZZZZZZZZZZZZZZZZZ/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "guardian"},
        headers=_h(nurse),
    )
    assert res.status_code == 404, res.text


async def test_link_caregiver_self_link_422(client) -> None:
    """A patient cannot be linked as their own caregiver (422)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    nin = _unique_nin()
    p = await _enrol(client, nurse, nin)
    res = await client.post(
        f"/api/v1/patients/{p['id']}/caregivers",
        json={"caregiver_nin": nin, "relationship": "guardian"},
        headers=_h(nurse),
    )
    assert res.status_code == 422, res.text


async def test_link_caregiver_invalid_relationship_422(client) -> None:
    """An out-of-enum relationship label fails schema validation (422)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    child = await _enrol(client, nurse, _unique_nin())
    caregiver_nin = _unique_nin("CF")
    await _enrol(client, nurse, caregiver_nin)
    res = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "best-friend"},
        headers=_h(nurse),
    )
    assert res.status_code == 422, res.text


async def test_link_caregiver_citizen_forbidden(client) -> None:
    """Citizens cannot create caregiver links (endpoint requires role >= worker)."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    citizen = await _citizen_login(client, CITIZEN_NIN)
    own_id = await _find_own_patient_id(client, admin, CITIZEN_NIN)
    res = await client.post(
        f"/api/v1/patients/{own_id}/caregivers",
        json={"caregiver_nin": SEED_CAREGIVER_NIN, "relationship": "guardian"},
        headers=_h(citizen),
    )
    assert res.status_code == 403, res.text


async def test_unlink_caregiver_wrong_child_404(client) -> None:
    """Deleting a link via a child id that doesn't own it returns 404 (the link
    must belong to the path's child)."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    child = await _enrol(client, nurse, _unique_nin())
    other_child = await _enrol(client, nurse, _unique_nin())
    caregiver_nin = _unique_nin("CF")
    await _enrol(client, nurse, caregiver_nin)

    res = await client.post(
        f"/api/v1/patients/{child['id']}/caregivers",
        json={"caregiver_nin": caregiver_nin, "relationship": "guardian"},
        headers=_h(nurse),
    )
    assert res.status_code == 201, res.text
    link_id = res.json()["id"]

    # Right link id, wrong child in the path → 404.
    res = await client.delete(
        f"/api/v1/patients/{other_child['id']}/caregivers/{link_id}", headers=_h(nurse)
    )
    assert res.status_code == 404, res.text


async def test_unlink_caregiver_missing_link_404(client) -> None:
    """Deleting a non-existent caregiver link is 404."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    child = await _enrol(client, nurse, _unique_nin())
    res = await client.delete(
        f"/api/v1/patients/{child['id']}/caregivers/01JZZZZZZZZZZZZZZZZZZZZZZZZ",
        headers=_h(nurse),
    )
    assert res.status_code == 404, res.text
