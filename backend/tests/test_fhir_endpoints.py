"""FHIR R4 endpoint conformance — ties the in-process API to the
expectations the standalone `scripts/fhir-conformance.sh` harness checks.

Coverage:
  - CapabilityStatement advertises every routed resource
  - Encounter/Observation/Immunization/MedicationDispense search returns Bundles
  - Patient FHIR read enforces citizen self-access (covered in test_rbac_scoping)
  - POST /fhir/Observation round-trip: create → read → search
  - Negative tests: missing required fields → 4xx, unauthenticated → 401
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def _login(client, identifier: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


async def _seed(client) -> None:
    res = await client.post("/api/v1/auth/seed-demo")
    assert res.status_code == 200, res.text


async def test_capability_statement_advertises_all_resources(client) -> None:
    res = await client.get("/fhir/metadata")
    assert res.status_code == 200
    body = res.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["fhirVersion"].startswith("4.0.")
    types = {r["type"] for r in body["rest"][0]["resource"]}
    assert {"Patient", "Encounter", "Observation", "Immunization", "MedicationDispense"} <= types


async def test_unauthenticated_fhir_read_is_rejected(client) -> None:
    res = await client.get("/fhir/Patient")
    # Either 401 (missing token) or 403 are acceptable. 200 is a bug.
    assert res.status_code in (401, 403), res.text


async def test_fhir_observation_post_round_trip(client) -> None:
    """The conformance harness creates a heart-rate Observation, reads it
    back, and verifies meta.lastUpdated. We mirror that here."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    headers = {"Authorization": f"Bearer {admin}"}

    # Find a patient with a known NIN — the seed data has Achieng.
    res = await client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    pid = res.json()["entry"][0]["resource"]["id"]

    body = {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "8867-4",
                    "display": "Heart rate",
                }
            ]
        },
        "subject": {"reference": f"Patient/{pid}"},
        "valueQuantity": {
            "value": 78,
            "unit": "beats/min",
            "system": "http://unitsofmeasure.org",
            "code": "/min",
        },
    }
    created = await client.post("/fhir/Observation", json=body, headers=headers)
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]
    assert new_id

    read = await client.get(f"/fhir/Observation/{new_id}", headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["id"] == new_id
    assert read.json().get("meta", {}).get("lastUpdated"), (
        "FHIR Observation read must expose meta.lastUpdated for audit chains"
    )


async def test_fhir_observation_post_missing_fields_returns_4xx(client) -> None:
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    res = await client.post(
        "/fhir/Observation",
        json={"resourceType": "Observation"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert 400 <= res.status_code < 500, res.text


async def test_fhir_encounter_search_returns_bundle(client) -> None:
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    headers = {"Authorization": f"Bearer {admin}"}

    # Resolve a patient ID via search.
    res = await client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=headers,
    )
    pid = res.json()["entry"][0]["resource"]["id"]

    res = await client.get(f"/fhir/Encounter?patient={pid}", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    # Encounters should reference the patient as subject.
    if body.get("entry"):
        first = body["entry"][0]["resource"]
        assert first["subject"]["reference"] == f"Patient/{pid}"
        # FHIR Encounter must have a class coding (v3 ActCode) — harness test.
        assert first.get("class", {}).get("code")


async def test_fhir_observation_search_returns_bundle_with_loinc(client) -> None:
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    headers = {"Authorization": f"Bearer {admin}"}

    pres = await client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=headers,
    )
    pid = pres.json()["entry"][0]["resource"]["id"]

    res = await client.get(
        f"/fhir/Observation?patient={pid}&_count=5", headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    if body.get("entry"):
        # At least one entry should be LOINC-coded (vitals are seeded that way).
        loincs = [
            e["resource"]["code"]["coding"][0]["system"]
            for e in body["entry"]
            if e["resource"].get("code", {}).get("coding")
        ]
        assert any(s == "http://loinc.org" for s in loincs)


async def test_fhir_immunization_search_returns_bundle(client) -> None:
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    headers = {"Authorization": f"Bearer {admin}"}

    pres = await client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=headers,
    )
    pid = pres.json()["entry"][0]["resource"]["id"]

    res = await client.get(f"/fhir/Immunization?patient={pid}", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    if body.get("entry"):
        first = body["entry"][0]["resource"]
        assert first["resourceType"] == "Immunization"
        assert first["vaccineCode"]["coding"][0]["code"]


async def test_fhir_medication_dispense_search_returns_bundle(client) -> None:
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    headers = {"Authorization": f"Bearer {admin}"}

    pres = await client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=headers,
    )
    pid = pres.json()["entry"][0]["resource"]["id"]

    res = await client.get(
        f"/fhir/MedicationDispense?patient={pid}", headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resourceType"] == "Bundle"
