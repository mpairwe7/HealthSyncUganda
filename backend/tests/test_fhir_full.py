"""Comprehensive FHIR R4 endpoint coverage — complements test_fhir_endpoints.py.

`test_fhir_endpoints.py` covers the conformance-harness happy paths (the
CapabilityStatement resource list, one search-returns-a-Bundle per resource,
the Observation POST round-trip, and a couple of negative cases). This module
fills in the scenarios that file deliberately leaves out so every branch of
`app/fhir/endpoints.py` is exercised:

  - /fhir/metadata CapabilityStatement: exact fhirVersion / status / format /
    declared interactions + searchParams.
  - Patient read-by-id: authorised 200, cross-facility 403, citizen-other 403,
    unauthenticated 401, missing 404. Search by `?identifier=` (system|value
    AND bare value forms) and `?family=`, returning a searchset Bundle whose
    entries carry the Uganda NIN identifier slice.
  - Encounter read + search: Bundle shape, class coding, authz, 404.
  - Observation read (authz/404); create round-trip persisting value +
    effectiveDateTime; malformed effectiveDateTime → 400 (NOT 500); missing
    subject → 4xx; non-Observation resourceType → 400.
  - Immunization search derived from a freshly-posted SNOMED vaccine
    Observation (proves the on-the-fly projection).
  - MedicationDispense search: a populated searchset Bundle produced by an
    end-to-end dispense, plus the empty / required-param / authz branches.
  - Authz matrix per resource: a citizen may only touch their own records;
    unauthenticated requests are rejected on every resource.
  - Content negotiation: the JSON resources are served as application/json
    (the endpoints return plain dicts via FastAPI's default encoder).

All tests drive the in-memory SQLite app from conftest.py through the public
HTTP surface and seed via `/api/v1/auth/seed-demo` — no direct DB access, no
app/ or conftest.py changes.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio

# Seeded personas / identifiers (see app/seed/data.py).
ADMIN = ("admin", "admin1234")            # ministry_admin
NURSE_GULU = ("nurse.gulu", "demo1234")   # worker @ GUL-RRH-002
DOCTOR_KLA = ("doctor.kampala", "demo1234")  # worker @ MUL-NRH-001

# Achieng Akello — the self-service citizen with seeded encounters.
CITIZEN_NIN = "CM85051712345X"
NIN_SYSTEM = "https://nira.go.ug/identifiers/nin"


# ── helpers (reused from the existing integration suites) ────────────────────


async def _seed(client) -> None:
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


async def _patient_id_by_nin(client, headers: dict[str, str], nin: str) -> str:
    """Resolve a patient's FHIR id via the identifier search (the canonical
    way callers go from a NIN to a resource id)."""
    res = await client.get(
        f"/fhir/Patient?identifier={NIN_SYSTEM}|{nin}", headers=headers
    )
    assert res.status_code == 200, res.text
    entries = res.json()["entry"]
    assert entries, f"no patient found for NIN {nin}"
    return entries[0]["resource"]["id"]


async def _other_patient_id(client, admin_headers: dict[str, str], not_nin: str) -> str:
    """A patient whose NIN differs from `not_nin` — used to prove a citizen
    can't reach a stranger's record."""
    res = await client.get("/api/v1/patients?page_size=30", headers=admin_headers)
    assert res.status_code == 200, res.text
    others = [p for p in res.json()["items"] if p["nin"] != not_nin]
    assert others, "seed must include at least two patients"
    return others[0]["id"]


# ── CapabilityStatement / metadata ───────────────────────────────────────────


async def test_metadata_capability_statement_shape(client) -> None:
    """The metadata endpoint is the FHIR discovery surface. It must be public
    and declare R4 (4.0.1) with the fhir+json wire format."""
    res = await client.get("/fhir/metadata")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["status"] == "active"
    assert body["kind"] == "instance"
    # Exact R4 version — clients pin on this.
    assert body["fhirVersion"] == "4.0.1"
    assert "application/fhir+json" in body["format"]
    assert body["implementation"]["url"] == "/fhir"


async def test_metadata_is_public_no_token_required(client) -> None:
    """CapabilityStatement must be reachable without authentication so a
    client can negotiate capabilities before logging in."""
    res = await client.get("/fhir/metadata")
    assert res.status_code == 200, res.text
    # And it serializes as JSON (plain dict via FastAPI's default encoder).
    assert res.headers["content-type"].startswith("application/json")


async def test_metadata_declares_interactions_and_search_params(client) -> None:
    """Each routed resource advertises the interactions and search params the
    endpoints actually implement (read/search/create + identifier/family/...)."""
    res = await client.get("/fhir/metadata")
    body = res.json()
    resources = {r["type"]: r for r in body["rest"][0]["resource"]}

    # Patient: read + search + create; identifier/family/birthdate params.
    patient = resources["Patient"]
    p_interactions = {i["code"] for i in patient["interaction"]}
    assert {"read", "search-type", "create"} <= p_interactions
    p_params = {sp["name"] for sp in patient["searchParam"]}
    assert {"identifier", "family", "birthdate"} <= p_params

    # Observation supports create as well as read/search.
    obs = resources["Observation"]
    assert {"read", "search-type", "create"} <= {i["code"] for i in obs["interaction"]}

    # Encounter / Immunization / MedicationDispense are search-only on this server.
    assert {"read", "search-type"} <= {
        i["code"] for i in resources["Encounter"]["interaction"]
    }
    assert {"search-type"} <= {
        i["code"] for i in resources["Immunization"]["interaction"]
    }
    assert {"search-type"} <= {
        i["code"] for i in resources["MedicationDispense"]["interaction"]
    }


# ── Patient: read-by-id ──────────────────────────────────────────────────────


async def test_patient_read_by_id_authorised(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Patient/{pid}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Patient"
    assert body["id"] == pid
    # The Uganda NIN identifier slice must be present and well-formed.
    nin_ids = [i for i in body["identifier"] if i["system"] == NIN_SYSTEM]
    assert len(nin_ids) == 1
    assert nin_ids[0]["value"] == CITIZEN_NIN
    assert nin_ids[0]["use"] == "official"
    # JSON wire format (the endpoint returns a plain dict).
    assert res.headers["content-type"].startswith("application/json")


async def test_patient_read_unknown_id_is_404(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Patient/does-not-exist", headers=admin)
    assert res.status_code == 404, res.text


async def test_patient_read_unauthenticated_is_401(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Patient/{pid}")  # no Authorization header
    assert res.status_code == 401, res.text


async def test_patient_read_citizen_cannot_read_stranger(client) -> None:
    """A citizen token reaching another patient by id must 403 (auth succeeds,
    authorisation does not)."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Patient/{other_id}", headers=citizen)
    assert res.status_code == 403, res.text


async def test_patient_read_citizen_can_read_own(client) -> None:
    await _seed(client)
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    # The citizen can resolve their own record via identifier search…
    own_id = await _patient_id_by_nin(client, citizen, CITIZEN_NIN)
    # …and read it by id.
    res = await client.get(f"/fhir/Patient/{own_id}", headers=citizen)
    assert res.status_code == 200, res.text
    assert res.json()["id"] == own_id


async def test_patient_read_cross_facility_worker_403(client) -> None:
    """A worker at facility A reading a patient owned by (and never seen at)
    facility B must 403. We locate a patient visible to the Gulu nurse but not
    the Kampala doctor, then have the doctor read it directly."""
    await _seed(client)
    nurse = _auth(await _login(client, *NURSE_GULU))
    doctor = _auth(await _login(client, *DOCTOR_KLA))

    res = await client.get("/api/v1/patients?page_size=30", headers=nurse)
    nurse_ids = {p["id"] for p in res.json()["items"]}
    res = await client.get("/api/v1/patients?page_size=30", headers=doctor)
    doc_ids = {p["id"] for p in res.json()["items"]}

    nurse_only = nurse_ids - doc_ids
    if not nurse_only:
        pytest.skip("seed produced no single-facility patient for the two workers")
    target = next(iter(nurse_only))

    res = await client.get(f"/fhir/Patient/{target}", headers=doctor)
    assert res.status_code == 403, res.text


# ── Patient: search ──────────────────────────────────────────────────────────


async def test_patient_search_by_identifier_system_value_form(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))

    res = await client.get(
        f"/fhir/Patient?identifier={NIN_SYSTEM}|{CITIZEN_NIN}", headers=admin
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 1
    entry = body["entry"][0]
    assert entry["fullUrl"].endswith(f"/{entry['resource']['id']}")
    assert entry["search"]["mode"] == "match"
    # The Uganda NIN slice must be present on the returned resource.
    nin_ids = [
        i for i in entry["resource"]["identifier"] if i["system"] == NIN_SYSTEM
    ]
    assert nin_ids and nin_ids[0]["value"] == CITIZEN_NIN


async def test_patient_search_by_identifier_bare_value_form(client) -> None:
    """The `identifier` param also accepts a bare value (no `system|` prefix);
    the endpoint matches it against the NIN, case-insensitively."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))

    res = await client.get(
        f"/fhir/Patient?identifier={CITIZEN_NIN.lower()}", headers=admin
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert body["entry"][0]["resource"]["identifier"][0]["value"] == CITIZEN_NIN


async def test_patient_search_by_family(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))

    res = await client.get("/fhir/Patient?family=Akello", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] >= 1
    families = {
        e["resource"]["name"][0]["family"]
        for e in body["entry"]
        if e["resource"].get("name")
    }
    # ilike("%Akello%") match — every returned row carries the family name.
    assert all("Akello" in f for f in families)


async def test_patient_search_unauthenticated_is_rejected(client) -> None:
    await _seed(client)
    res = await client.get(f"/fhir/Patient?identifier={NIN_SYSTEM}|{CITIZEN_NIN}")
    assert res.status_code in (401, 403), res.text


async def test_patient_search_citizen_scoped_to_self(client) -> None:
    """A citizen searching Patient by family only sees rows they're entitled to
    (own record / caregiver-linked) — the SQL visibility filter, not a 403."""
    await _seed(client)
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))

    res = await client.get("/fhir/Patient?family=Akello", headers=citizen)
    assert res.status_code == 200, res.text
    body = res.json()
    nins = {
        i["value"]
        for e in body.get("entry", [])
        for i in e["resource"]["identifier"]
        if i["system"] == NIN_SYSTEM
    }
    # The citizen must never receive a stranger's record in their bundle.
    assert nins <= {CITIZEN_NIN}


# ── Encounter: read + search ─────────────────────────────────────────────────


async def test_encounter_search_returns_bundle_with_class_and_subject(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Encounter?patient={pid}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] >= 1, "the seeded citizen has encounters"
    enc = body["entry"][0]["resource"]
    assert enc["resourceType"] == "Encounter"
    assert enc["subject"]["reference"] == f"Patient/{pid}"
    # FHIR R4 Encounter.class is a v3 ActCode coding (default AMB/ambulatory).
    assert enc["class"]["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    assert enc["class"]["code"]
    # serviceProvider points at the facility Organization.
    assert enc["serviceProvider"]["reference"].startswith("Organization/")


async def test_encounter_search_requires_patient_param(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Encounter", headers=admin)
    assert res.status_code == 422, res.text


async def test_encounter_search_unknown_patient_is_empty_bundle(client) -> None:
    """A non-existent patient yields an empty searchset, not a 404/403."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Encounter?patient=ghost", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["type"] == "searchset"
    assert body["total"] == 0
    assert body.get("entry", []) == []


async def test_encounter_read_by_id_authorised(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)
    res = await client.get(f"/fhir/Encounter?patient={pid}", headers=admin)
    eid = res.json()["entry"][0]["resource"]["id"]

    res = await client.get(f"/fhir/Encounter/{eid}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Encounter"
    assert body["id"] == eid
    assert body["subject"]["reference"] == f"Patient/{pid}"
    # Encounter read exposes meta.lastUpdated for audit chains.
    assert body.get("meta", {}).get("lastUpdated")


async def test_encounter_read_unknown_id_is_404(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Encounter/does-not-exist", headers=admin)
    assert res.status_code == 404, res.text


async def test_encounter_read_unauthenticated_is_401(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)
    eid = (
        await client.get(f"/fhir/Encounter?patient={pid}", headers=admin)
    ).json()["entry"][0]["resource"]["id"]

    res = await client.get(f"/fhir/Encounter/{eid}")
    assert res.status_code == 401, res.text


async def test_encounter_citizen_search_own_and_denied_other(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    own_id = await _patient_id_by_nin(client, citizen, CITIZEN_NIN)
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Encounter?patient={own_id}", headers=citizen)
    assert res.status_code == 200, res.text
    assert res.json()["type"] == "searchset"

    res = await client.get(f"/fhir/Encounter?patient={other_id}", headers=citizen)
    assert res.status_code == 403, res.text


async def test_encounter_read_citizen_denied_other(client) -> None:
    """Reading a stranger's Encounter by id as a citizen must 403."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)
    other_enc = (
        await client.get(f"/fhir/Encounter?patient={other_id}", headers=admin)
    ).json().get("entry", [])
    if not other_enc:
        pytest.skip("the chosen other patient has no encounters to read")
    eid = other_enc[0]["resource"]["id"]

    res = await client.get(f"/fhir/Encounter/{eid}", headers=citizen)
    assert res.status_code == 403, res.text


# ── Observation: read ────────────────────────────────────────────────────────


async def test_observation_read_unauthenticated_is_401(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)
    obs = (
        await client.get(f"/fhir/Observation?patient={pid}&_count=1", headers=admin)
    ).json().get("entry", [])
    if not obs:
        pytest.skip("seeded citizen has no observations")
    oid = obs[0]["resource"]["id"]

    res = await client.get(f"/fhir/Observation/{oid}")
    assert res.status_code == 401, res.text


async def test_observation_read_unknown_id_is_404(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Observation/does-not-exist", headers=admin)
    assert res.status_code == 404, res.text


async def test_observation_read_citizen_denied_other(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)
    other_obs = (
        await client.get(f"/fhir/Observation?patient={other_id}&_count=1", headers=admin)
    ).json().get("entry", [])
    if not other_obs:
        pytest.skip("the chosen other patient has no observations")
    oid = other_obs[0]["resource"]["id"]

    res = await client.get(f"/fhir/Observation/{oid}", headers=citizen)
    assert res.status_code == 403, res.text


# ── Observation: search ──────────────────────────────────────────────────────


async def test_observation_search_requires_patient_param(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Observation", headers=admin)
    assert res.status_code == 422, res.text


async def test_observation_search_by_code_token(client) -> None:
    """A `code=system|code` token narrows the search to matching observations.
    We post a known LOINC heart-rate observation, then query for exactly it."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "valueQuantity": {"value": 81, "unit": "beats/min"},
    }
    created = await client.post("/fhir/Observation", json=body, headers=admin)
    assert created.status_code == 201, created.text

    res = await client.get(
        f"/fhir/Observation?patient={pid}&code=http://loinc.org|8867-4", headers=admin
    )
    assert res.status_code == 200, res.text
    bundle = res.json()
    assert bundle["type"] == "searchset"
    assert bundle["total"] >= 1
    for e in bundle["entry"]:
        coding = e["resource"]["code"]["coding"][0]
        assert coding["system"] == "http://loinc.org"
        assert coding["code"] == "8867-4"


async def test_observation_search_count_param_out_of_range_is_422(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Observation?patient={pid}&_count=0", headers=admin)
    assert res.status_code == 422, res.text
    res = await client.get(
        f"/fhir/Observation?patient={pid}&_count=100000", headers=admin
    )
    assert res.status_code == 422, res.text


async def test_observation_search_citizen_denied_other(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Observation?patient={other_id}", headers=citizen)
    assert res.status_code == 403, res.text


# ── Observation: create (POST) ───────────────────────────────────────────────


async def test_observation_create_round_trip_persists_value_and_date(client) -> None:
    """Happy path: POST a fully-specified Observation, then read it back and
    confirm the value + effectiveDateTime survived the ORM round-trip."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "8310-5",
                    "display": "Body temperature",
                }
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "effectiveDateTime": "2026-01-15T09:30:00Z",
        "valueQuantity": {"value": 37.2, "unit": "Cel"},
    }
    created = await client.post("/fhir/Observation", json=body, headers=admin)
    assert created.status_code == 201, created.text
    out = created.json()
    new_id = out["id"]
    assert new_id
    assert out["subject"]["reference"] == f"Patient/{pid}"
    assert out["valueQuantity"]["value"] == 37.2
    assert out["valueQuantity"]["unit"] == "Cel"
    # ISO-8601 effective time is parsed and echoed back.
    assert out["effectiveDateTime"].startswith("2026-01-15T09:30:00")
    assert created.headers["content-type"].startswith("application/json")

    read = await client.get(f"/fhir/Observation/{new_id}", headers=admin)
    assert read.status_code == 200, read.text
    rb = read.json()
    assert rb["id"] == new_id
    assert rb["code"]["coding"][0]["code"] == "8310-5"
    assert rb["valueQuantity"]["value"] == 37.2
    assert rb.get("meta", {}).get("lastUpdated")


async def test_observation_create_value_string_round_trip(client) -> None:
    """valueString observations (e.g. blood-pressure text) round-trip too."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "55284-4",
                    "display": "Blood pressure",
                }
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "valueString": "120/80",
    }
    created = await client.post("/fhir/Observation", json=body, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["valueString"] == "120/80"


async def test_observation_create_malformed_effective_datetime_is_400(client) -> None:
    """A non-ISO effectiveDateTime must be a clean 400 — NOT a 500. The handler
    catches the parse error and raises a BAD_REQUEST."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "effectiveDateTime": "15th January, 2026",  # not ISO-8601
        "valueQuantity": {"value": 70, "unit": "beats/min"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=admin)
    assert res.status_code == 400, res.text
    assert "effectiveDateTime" in res.json()["detail"]


async def test_observation_create_missing_subject_is_4xx(client) -> None:
    """Missing subject.reference → 4xx (the handler raises 400)."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))

    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        # no subject
        "valueQuantity": {"value": 70, "unit": "beats/min"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=admin)
    assert 400 <= res.status_code < 500, res.text
    assert res.status_code == 400


async def test_observation_create_wrong_resource_type_is_400(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Patient",  # not Observation
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        "subject": {"reference": f"Patient/{pid}"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=admin)
    assert res.status_code == 400, res.text


async def test_observation_create_missing_code_coding_is_400(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "subject": {"reference": f"Patient/{pid}"},
        # no code.coding
        "valueQuantity": {"value": 70, "unit": "beats/min"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=admin)
    assert res.status_code == 400, res.text


async def test_observation_create_unknown_patient_is_404(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))

    body = {
        "resourceType": "Observation",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        "subject": {"reference": "Patient/does-not-exist"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=admin)
    assert res.status_code == 404, res.text


async def test_observation_create_unauthenticated_is_401(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        "subject": {"reference": f"Patient/{pid}"},
    }
    res = await client.post("/fhir/Observation", json=body)  # no token
    assert res.status_code == 401, res.text


async def test_observation_create_citizen_denied_for_other_patient(client) -> None:
    """A citizen posting an Observation against a stranger's record → 403."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        "subject": {"reference": f"Patient/{other_id}"},
        "valueQuantity": {"value": 70, "unit": "beats/min"},
    }
    res = await client.post("/fhir/Observation", json=body, headers=citizen)
    assert res.status_code == 403, res.text


# ── Immunization (derived from SNOMED vaccine Observations) ───────────────────


async def test_immunization_search_derived_from_posted_vaccine_observation(client) -> None:
    """Post a SNOMED-coded UNEPI vaccine Observation, then confirm it surfaces
    in the Immunization search — proving the on-the-fly Observation→
    Immunization projection (no separate Immunization table)."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    # BCG vaccine — SNOMED 42284007, in the UNEPI schedule.
    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "42284007",
                    "display": "BCG vaccine product",
                }
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "valueString": "administered",
    }
    created = await client.post("/fhir/Observation", json=body, headers=admin)
    assert created.status_code == 201, created.text

    res = await client.get(f"/fhir/Immunization?patient={pid}", headers=admin)
    assert res.status_code == 200, res.text
    bundle = res.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] >= 1
    bcg = [
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["vaccineCode"]["coding"][0]["code"] == "42284007"
    ]
    assert bcg, "the posted BCG vaccine must appear as an Immunization"
    imm = bcg[0]
    assert imm["resourceType"] == "Immunization"
    assert imm["status"] == "completed"
    assert imm["patient"]["reference"] == f"Patient/{pid}"
    assert imm["occurrenceDateTime"]


async def test_immunization_excludes_non_vaccine_observations(client) -> None:
    """A plain LOINC vital must NOT be projected into the Immunization view —
    only SNOMED UNEPI codes are."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    body = {
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "valueQuantity": {"value": 77, "unit": "beats/min"},
    }
    assert (
        await client.post("/fhir/Observation", json=body, headers=admin)
    ).status_code == 201

    res = await client.get(f"/fhir/Immunization?patient={pid}", headers=admin)
    assert res.status_code == 200, res.text
    codes = [
        e["resource"]["vaccineCode"]["coding"][0]["code"]
        for e in res.json().get("entry", [])
    ]
    assert "8867-4" not in codes


async def test_immunization_search_requires_patient_param(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/Immunization", headers=admin)
    assert res.status_code == 422, res.text


async def test_immunization_search_citizen_denied_other(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/Immunization?patient={other_id}", headers=citizen)
    assert res.status_code == 403, res.text


async def test_immunization_search_unauthenticated_is_rejected(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)
    res = await client.get(f"/fhir/Immunization?patient={pid}")
    assert res.status_code in (401, 403), res.text


# ── MedicationDispense (derived from dispensed StockEvents) ───────────────────


async def _dispense_for_patient(client, admin: dict[str, str], pid: str) -> bool:
    """Drive a real dispense through the public API so the patient has a
    dispensed StockEvent linked to one of their encounters. Returns True if a
    dispense succeeded. ministry_admin satisfies the pharmacist gate and
    bypasses facility scoping."""
    encs = (
        await client.get(f"/fhir/Encounter?patient={pid}", headers=admin)
    ).json().get("entry", [])
    if not encs:
        return False

    items = (await client.get("/api/v1/supply/items", headers=admin)).json()
    code_to_id = {it["code"]: it["id"] for it in items}
    snaps = (await client.get("/api/v1/supply/snapshot", headers=admin)).json()

    for ent in encs:
        enc = ent["resource"]
        eid = enc["id"]
        fac_id = enc["serviceProvider"]["reference"].split("/")[-1]
        stocked = [
            s for s in snaps if s["facility_id"] == fac_id and s["on_hand"] > 0
        ]
        for s in stocked:
            item_id = code_to_id.get(s["item_code"])
            if not item_id:
                continue
            res = await client.post(
                f"/api/v1/supply/dispense?supply_item_id={item_id}"
                f"&facility_id={fac_id}&quantity=2&encounter_id={eid}&patient_id={pid}",
                headers=admin,
            )
            if res.status_code == 200:
                return True
    return False


async def test_medication_dispense_search_populated_bundle(client) -> None:
    """End-to-end: dispense a supply item against the patient's encounter, then
    confirm it surfaces as a MedicationDispense with the patient as subject."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    dispensed = await _dispense_for_patient(client, admin, pid)
    assert dispensed, "expected at least one facility with stock for the patient"

    res = await client.get(f"/fhir/MedicationDispense?patient={pid}", headers=admin)
    assert res.status_code == 200, res.text
    bundle = res.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] >= 1
    md = bundle["entry"][0]["resource"]
    assert md["resourceType"] == "MedicationDispense"
    assert md["status"] == "completed"
    # The search path overrides subject to point at the real patient.
    assert md["subject"]["reference"] == f"Patient/{pid}"
    assert md["medicationCodeableConcept"]["coding"][0]["code"]
    assert md["quantity"]["value"] == 2
    assert md["location"]["reference"].startswith("Organization/")
    assert bundle["entry"][0]["fullUrl"].endswith(f"/{md['id']}")


async def test_medication_dispense_search_empty_when_no_dispenses(client) -> None:
    """Before any dispense, the bundle is a valid empty searchset (total 0)."""
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)

    res = await client.get(f"/fhir/MedicationDispense?patient={pid}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 0


async def test_medication_dispense_search_requires_patient_param(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/MedicationDispense", headers=admin)
    assert res.status_code == 422, res.text


async def test_medication_dispense_unknown_patient_is_empty_bundle(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    res = await client.get("/fhir/MedicationDispense?patient=ghost", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["type"] == "searchset"
    assert body["total"] == 0


async def test_medication_dispense_citizen_denied_other(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    citizen = _auth(await _citizen_login(client, CITIZEN_NIN))
    other_id = await _other_patient_id(client, admin, CITIZEN_NIN)

    res = await client.get(
        f"/fhir/MedicationDispense?patient={other_id}", headers=citizen
    )
    assert res.status_code == 403, res.text


async def test_medication_dispense_unauthenticated_is_rejected(client) -> None:
    await _seed(client)
    admin = _auth(await _login(client, *ADMIN))
    pid = await _patient_id_by_nin(client, admin, CITIZEN_NIN)
    res = await client.get(f"/fhir/MedicationDispense?patient={pid}")
    assert res.status_code in (401, 403), res.text
