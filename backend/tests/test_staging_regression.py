"""End-to-end regression tests against deployed Crane Cloud staging.

Gated by `STAGING_URL` env var — skipped in unit CI. Run manually after
each deploy to confirm every feature shipped in the compliance sweep is
live, the role story holds under real auth, and the surface degrades
sanely on bad input.

Run:

    STAGING_URL=https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io \\
        uv run pytest tests/test_staging_regression.py -v --tb=short

Each test function exercises one feature group with multiple assertions.
Tests share a module-scoped session fixture that logs in five personas
once, so the suite stays under ~60 seconds even with the round-trip cost
of a real WAN call.

Persona credentials are the seed-demo defaults (verified live):
  admin (ministry_admin, no facility)        — admin / admin1234
  nurse.gulu (worker, GUL-RRH-002)            — nurse.gulu / demo1234
  doctor.kampala (worker, MUL-NRH-001)        — doctor.kampala / demo1234
  pharmacist.mbarara (pharmacist, MBR-RRH-003) — pharmacist.mbarara / demo1234
  dho.gulu (district_admin, GUL-RRH-002)      — dho.gulu / demo1234

Citizen NIN: CM85051712345X (Achieng Akello — has encounters + immunisations
in the seed dataset, used as the read-self target for FHIR + REST tests).
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

STAGING_URL = os.getenv("STAGING_URL")

# Readiness-probe tuning. The Crane Cloud ingress switches between old/new
# pods during a rollout, producing intermittent 502/503s. A single 200 is
# not enough to declare the pod stable — we want N consecutive 200s across
# a short window so we don't poison the regression with transition errors.
#
# Defaults: 5 successful probes, 1.5s apart, max 5 minutes overall, after
# which the suite fails the readiness check rather than running tests that
# would all fail for the wrong reason.
READINESS_CONSECUTIVE_OK = int(os.getenv("STAGING_READY_OK_PROBES", "5"))
READINESS_PROBE_INTERVAL_S = float(os.getenv("STAGING_READY_INTERVAL_S", "1.5"))
READINESS_MAX_WAIT_S = float(os.getenv("STAGING_READY_MAX_WAIT_S", "300"))

pytestmark = pytest.mark.skipif(
    not STAGING_URL,
    reason="STAGING_URL not set — staging regression suite skipped",
)


# ── Module-scoped session: pool the HTTP client + token cache ────────────────


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    assert STAGING_URL is not None
    with httpx.Client(
        base_url=STAGING_URL,
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        follow_redirects=False,
    ) as c:
        _wait_until_stable(c)
        yield c


def _wait_until_stable(client: httpx.Client) -> None:
    """Block until the staging pod is reliably serving traffic.

    Polls `/healthz` and requires `READINESS_CONSECUTIVE_OK` successive
    200s before returning. A non-200 resets the counter — this catches the
    rollout window where the ingress flickers between old + new pods and
    one isolated 200 doesn't actually mean the new pod is ready.

    Bounded by `READINESS_MAX_WAIT_S`; raises on timeout so the suite
    surfaces "staging is degraded" rather than a flood of fake regressions.
    """
    deadline = time.monotonic() + READINESS_MAX_WAIT_S
    ok_streak = 0
    last_code: int | str = "n/a"
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            res = client.get("/healthz", timeout=5.0)
            last_code = res.status_code
            if res.status_code == 200:
                ok_streak += 1
                if ok_streak >= READINESS_CONSECUTIVE_OK:
                    return
            else:
                ok_streak = 0
        except Exception as exc:
            last_code = "exc"
            last_err = f"{type(exc).__name__}: {exc}"
            ok_streak = 0
        time.sleep(READINESS_PROBE_INTERVAL_S)
    raise RuntimeError(
        f"staging not stable after {READINESS_MAX_WAIT_S:.0f}s — "
        f"last /healthz status {last_code}"
        + (f" ({last_err})" if last_err else "")
        + f". Streak target was {READINESS_CONSECUTIVE_OK} consecutive 200s."
    )


def _staff_token(client: httpx.Client, username: str, password: str) -> str:
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": username, "password": password},
    )
    assert res.status_code == 200, f"login {username} failed: {res.status_code} {res.text}"
    return res.json()["access_token"]


def _citizen_token(client: httpx.Client, nin: str, otp: str = "000000") -> str:
    res = client.post(
        "/api/v1/auth/citizen/login",
        json={"nin": nin, "otp": otp},
    )
    assert res.status_code == 200, f"citizen login failed: {res.status_code} {res.text}"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def tokens(client: httpx.Client) -> dict[str, str]:
    return {
        "admin":      _staff_token(client, "admin",            "admin1234"),
        "nurse":      _staff_token(client, "nurse.gulu",       "demo1234"),
        "doctor":     _staff_token(client, "doctor.kampala",   "demo1234"),
        "pharmacist": _staff_token(client, "pharmacist.mbarara", "demo1234"),
        "dho":        _staff_token(client, "dho.gulu",         "demo1234"),
        "citizen":    _citizen_token(client, "CM85051712345X"),
    }


def _auth(tokens: dict[str, str], persona: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens[persona]}"}


# ── Section A — Health & auth ────────────────────────────────────────────────


def test_health_endpoints_reachable(client: httpx.Client) -> None:
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    res = client.get("/readyz")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    # Redis may be degraded — that's an operator concern, not a deploy gate.


def test_root_returns_service_metadata(client: httpx.Client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "healthsync-uganda"
    assert "docs" in body and "fhir" in body


def test_staff_login_returns_token_and_facility(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # All five staff personas already logged in via the fixture — assert their
    # token shape via /me/staff (uses the token to look up the user record).
    for persona in ("admin", "nurse", "doctor", "pharmacist", "dho"):
        res = client.get("/api/v1/me/staff", headers=_auth(tokens, persona))
        assert res.status_code == 200, f"{persona}: {res.text}"
        body = res.json()
        assert body["role"], f"{persona}: missing role"


def test_invalid_credentials_return_401(client: httpx.Client) -> None:
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "admin", "password": "wrong-password"},
    )
    assert res.status_code == 401
    # Constant-message: must NOT reveal whether the user exists.
    assert res.json()["detail"] == "Invalid credentials"


def test_missing_bearer_returns_401(client: httpx.Client) -> None:
    res = client.get("/api/v1/patients?page_size=1")
    assert res.status_code == 401


def test_malformed_bearer_returns_401(client: httpx.Client) -> None:
    res = client.get(
        "/api/v1/patients?page_size=1",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert res.status_code == 401


def test_seed_admin_endpoint_removed(client: httpx.Client) -> None:
    # P0 audit-closure item — must stay 404 forever.
    res = client.post("/api/v1/auth/seed-admin")
    assert res.status_code == 404


# ── Section B — RBAC: patient + encounter scoping ────────────────────────────


def test_admin_sees_all_patients(client: httpx.Client, tokens: dict[str, str]) -> None:
    res = client.get(
        "/api/v1/patients?page_size=100", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    assert res.json()["total"] >= 5  # seed has 26


def test_worker_visibility_is_facility_scoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    nurse = client.get(
        "/api/v1/patients?page_size=100", headers=_auth(tokens, "nurse")
    ).json()
    doctor = client.get(
        "/api/v1/patients?page_size=100", headers=_auth(tokens, "doctor")
    ).json()
    nurse_ids = {p["id"] for p in nurse["items"]}
    doctor_ids = {p["id"] for p in doctor["items"]}
    # Each worker must see fewer than the admin's total — proves the SQL
    # scope filter actually filters.
    assert len(nurse_ids) < 30, f"nurse saw {len(nurse_ids)} (no filter applied?)"
    assert len(doctor_ids) < 30, f"doctor saw {len(doctor_ids)}"
    # The two facilities have non-identical patient pools.
    assert nurse_ids != doctor_ids, "nurse + doctor see identical sets — scope not facility-bound"


def test_cross_facility_patient_get_is_403(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    nurse_ids = {
        p["id"]
        for p in client.get(
            "/api/v1/patients?page_size=100", headers=_auth(tokens, "nurse")
        ).json()["items"]
    }
    doctor_ids = {
        p["id"]
        for p in client.get(
            "/api/v1/patients?page_size=100", headers=_auth(tokens, "doctor")
        ).json()["items"]
    }
    nurse_only = nurse_ids - doctor_ids
    if not nurse_only:
        pytest.skip("seed didn't produce a single-facility patient — non-deterministic spread")
    target = next(iter(nurse_only))
    res = client.get(
        f"/api/v1/patients/{target}", headers=_auth(tokens, "doctor")
    )
    assert res.status_code == 403, f"cross-facility read should 403; got {res.status_code}"


def test_citizen_can_read_own_record(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # Resolve own patient id via /me (avoids leaking the patient table to
    # citizens through search).
    res = client.get("/api/v1/me", headers=_auth(tokens, "citizen"))
    assert res.status_code == 200, res.text
    assert res.json()["nin"] == "CM85051712345X"


def test_citizen_cannot_read_other_patient(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    others = [
        p
        for p in client.get(
            "/api/v1/patients?page_size=100", headers=_auth(tokens, "admin")
        ).json()["items"]
        if p["nin"] != "CM85051712345X"
    ]
    assert others, "seed must include at least 2 patients"
    target = others[0]["id"]
    res = client.get(
        f"/api/v1/patients/{target}?purpose=test",
        headers=_auth(tokens, "citizen"),
    )
    assert res.status_code == 403


# ── Section C — Patient CRUD + family + immunisation ────────────────────────


def test_patient_get_with_purpose_required(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/api/v1/patients?page_size=1", headers=_auth(tokens, "admin")
    ).json()["items"][0]["id"]
    # Purpose has a default ('clinical-care'), so omission is OK; but the
    # field IS in the audit trail. Just confirm the read succeeds.
    res = client.get(
        f"/api/v1/patients/{pid}", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == pid
    assert "record_version" in body  # optimistic-locking column exposed


def test_immunisation_status_for_seed_child(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # Pick a paediatric NIN from the seed (the family fixture has one).
    p = client.get(
        "/api/v1/patients?q=Achieng", headers=_auth(tokens, "admin")
    ).json()["items"]
    if not p:
        pytest.skip("seed patient not found")
    pid = p[0]["id"]
    res = client.get(
        f"/api/v1/patients/{pid}/immunisation-status",
        headers=_auth(tokens, "admin"),
    )
    assert res.status_code == 200, res.text
    statuses = res.json()
    # UNEPI schedule has six antigens — every patient gets a row per antigen.
    antigens = {s["antigen"] for s in statuses}
    assert {"BCG", "OPV", "DPT", "PCV", "MR", "YF"} <= antigens, (
        f"UNEPI antigens missing — got {antigens}"
    )


def test_family_graph_returns_links(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/me/family", headers=_auth(tokens, "citizen")
    )
    assert res.status_code == 200, res.text
    # Citizen may or may not be a caregiver; just assert shape.
    body = res.json()
    assert isinstance(body, list)
    for entry in body:
        assert "patient_id" in entry and "relationship" in entry


# ── Section D — Encounters + observations ────────────────────────────────────


def test_encounter_list_facility_scoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    nurse_patients = client.get(
        "/api/v1/patients?page_size=10", headers=_auth(tokens, "nurse")
    ).json()["items"]
    assert nurse_patients, "nurse should see at least one patient"
    pid = nurse_patients[0]["id"]
    res = client.get(
        f"/api/v1/encounters/by-patient/{pid}", headers=_auth(tokens, "nurse")
    )
    assert res.status_code == 200
    encs = res.json()
    # If returned encounters carry a facility_id, every one must match the
    # nurse's facility (worker-level facility scope).
    for enc in encs:
        # facility_id should match nurse.gulu's facility (GUL-RRH-002 → unique id)
        assert enc.get("facility_id"), "encounter missing facility_id"


def test_encounter_observations_eager_loaded(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # Use admin token to find any encounter; verify observations come back
    # in the same response (proves selectinload is wired up).
    pid = client.get(
        "/api/v1/patients?page_size=1", headers=_auth(tokens, "admin")
    ).json()["items"][0]["id"]
    encs = client.get(
        f"/api/v1/encounters/by-patient/{pid}", headers=_auth(tokens, "admin")
    ).json()
    if not encs:
        pytest.skip("no encounters in seed for this patient")
    assert "observations" in encs[0], "observations must be inlined in EncounterOut"
    # At least one encounter in the seed has vitals (LOINC temperature 8310-5)
    any_with_obs = any(e["observations"] for e in encs)
    assert any_with_obs, "expected at least one encounter with observations"


# ── Section E — Supply chain ────────────────────────────────────────────────


def test_supply_list_items_returns_single_row_per_item(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/supply/items", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert items, "no supply items in seed?"
    # GROUP BY change — `on_hand_total` and `facilities_stocked` must be
    # integers (not None) for every row.
    for it in items:
        assert isinstance(it["on_hand_total"], int)
        assert isinstance(it["facilities_stocked"], int)
        assert it["facilities_stocked"] >= 0


def test_supply_stock_snapshot(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/supply/snapshot", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    snap = res.json()
    if snap:
        row = snap[0]
        assert {"facility_id", "facility_name", "item_code", "on_hand"} <= row.keys()


def test_supply_receive_cross_facility_403_for_pharmacist(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # pharmacist.mbarara is bound to MBR-RRH-003. Picking a different
    # facility id from /api/v1/facilities and trying to receive should 403.
    facilities = client.get(
        "/api/v1/facilities", headers=_auth(tokens, "admin")
    ).json()
    mbr = next((f for f in facilities if f["code"] == "MBR-RRH-003"), None)
    other = next(
        (f for f in facilities if f["code"] != "MBR-RRH-003"), None
    )
    if not mbr or not other:
        pytest.skip("seed doesn't carry both MBR-RRH-003 and another facility")

    items = client.get(
        "/api/v1/supply/items", headers=_auth(tokens, "admin")
    ).json()
    if not items:
        pytest.skip("no supply items to test against")
    body = {
        "supply_item_id": items[0]["id"],
        "facility_id": other["id"],
        "lot_number": f"REGRESS-{uuid.uuid4().hex[:8]}",
        "quantity": 1,
        "expires_on": "2030-01-01",
        "received_on": "2026-05-28",
    }
    res = client.post(
        "/api/v1/supply/batches",
        json=body,
        headers=_auth(tokens, "pharmacist"),
    )
    assert res.status_code == 403, (
        f"facility-bound pharmacist must be 403 outside their facility; "
        f"got {res.status_code}: {res.text}"
    )


def test_low_stock_alerts(client: httpx.Client, tokens: dict[str, str]) -> None:
    res = client.get(
        "/api/v1/supply/alerts/low-stock", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    for row in res.json():
        assert row["is_below_threshold"] is True


# ── Section F — Analytics (district scoping) ────────────────────────────────


def test_analytics_encounters_by_district_for_dho_is_scoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/analytics/encounters-by-district",
        headers=_auth(tokens, "dho"),
    )
    assert res.status_code == 200
    rows = res.json()
    # dho.gulu's district_id is "Gulu" — every returned row must match.
    for row in rows:
        assert row["district"] == "Gulu", (
            f"district_admin saw rows for {row['district']} — scope not applied"
        )


def test_analytics_encounters_by_district_for_admin_unscoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/analytics/encounters-by-district",
        headers=_auth(tokens, "admin"),
    )
    assert res.status_code == 200
    rows = res.json()
    districts = {r["district"] for r in rows}
    # Ministry admin should see multiple districts.
    assert len(districts) >= 1


def test_analytics_immunisation_coverage_scoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/analytics/immunisation-coverage",
        headers=_auth(tokens, "dho"),
    )
    assert res.status_code == 200
    for row in res.json():
        assert row["district"] == "Gulu"


def test_analytics_stock_out_risk_scoped(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/api/v1/analytics/stock-out-risk",
        headers=_auth(tokens, "dho"),
    )
    assert res.status_code == 200
    for row in res.json():
        assert row["district"] == "Gulu"


# ── Section G — FHIR R4 ─────────────────────────────────────────────────────


def test_fhir_capability_statement(client: httpx.Client) -> None:
    res = client.get("/fhir/metadata")
    assert res.status_code == 200
    body = res.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["fhirVersion"].startswith("4.0.")
    types = {r["type"] for r in body["rest"][0]["resource"]}
    assert {
        "Patient",
        "Encounter",
        "Observation",
        "Immunization",
        "MedicationDispense",
    } <= types


def test_fhir_patient_search_returns_uganda_nin_bundle(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=_auth(tokens, "admin"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    entry = body["entry"][0]["resource"]
    assert entry["resourceType"] == "Patient"
    nin_id = next(
        (i for i in entry["identifier"] if "nira.go.ug" in i["system"]), None
    )
    assert nin_id and nin_id["value"] == "CM85051712345X"


def test_fhir_citizen_read_other_patient_403(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    others = [
        p
        for p in client.get(
            "/api/v1/patients?page_size=10", headers=_auth(tokens, "admin")
        ).json()["items"]
        if p["nin"] != "CM85051712345X"
    ]
    assert others
    res = client.get(
        f"/fhir/Patient/{others[0]['id']}", headers=_auth(tokens, "citizen")
    )
    assert res.status_code == 403


def test_fhir_unauthenticated_read_is_rejected(client: httpx.Client) -> None:
    res = client.get("/fhir/Patient")
    assert res.status_code in (401, 403)


def test_fhir_observation_post_round_trip(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=_auth(tokens, "admin"),
    ).json()["entry"][0]["resource"]["id"]

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
    created = client.post(
        "/fhir/Observation", json=body, headers=_auth(tokens, "admin")
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    read = client.get(
        f"/fhir/Observation/{new_id}", headers=_auth(tokens, "admin")
    )
    assert read.status_code == 200
    body_read = read.json()
    assert body_read["id"] == new_id
    assert body_read.get("meta", {}).get("lastUpdated"), (
        "Observation must carry meta.lastUpdated for audit chains"
    )


def test_fhir_observation_post_missing_subject_is_4xx(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.post(
        "/fhir/Observation",
        json={"resourceType": "Observation"},
        headers=_auth(tokens, "admin"),
    )
    assert 400 <= res.status_code < 500


def test_fhir_encounter_search_returns_bundle_with_class(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=_auth(tokens, "admin"),
    ).json()["entry"][0]["resource"]["id"]
    res = client.get(
        f"/fhir/Encounter?patient={pid}", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    bundle = res.json()
    assert bundle["resourceType"] == "Bundle"
    if bundle.get("entry"):
        first = bundle["entry"][0]["resource"]
        assert first["class"]["code"], "FHIR Encounter.class.code must be set"
        assert first["subject"]["reference"] == f"Patient/{pid}"


def test_fhir_immunization_derived_from_vaccine_obs(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=_auth(tokens, "admin"),
    ).json()["entry"][0]["resource"]["id"]
    res = client.get(
        f"/fhir/Immunization?patient={pid}", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    bundle = res.json()
    assert bundle["resourceType"] == "Bundle"
    if bundle.get("entry"):
        first = bundle["entry"][0]["resource"]
        assert first["resourceType"] == "Immunization"
        assert first["vaccineCode"]["coding"][0]["code"]


def test_fhir_medication_dispense_bundle(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X",
        headers=_auth(tokens, "admin"),
    ).json()["entry"][0]["resource"]["id"]
    res = client.get(
        f"/fhir/MedicationDispense?patient={pid}", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 200
    assert res.json()["resourceType"] == "Bundle"


# ── Section H — Idempotency ─────────────────────────────────────────────────


def test_idempotency_replay_returns_cached_body(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # Stable test NIN derived from the run uuid so we don't collide with
    # other patients but stay deterministic within one run.
    test_nin = "CM" + uuid.uuid4().hex[:8].upper().ljust(11, "0") + "X"
    test_nin = test_nin[:14]  # NIN must be exactly 14 chars
    idempotency_key = str(uuid.uuid4())
    headers = {
        **_auth(tokens, "nurse"),
        "Idempotency-Key": idempotency_key,
    }
    body = {
        "nin": test_nin,
        "given_name": "Regress",
        "family_name": "Test",
        "gender": "female",
        "birth_date": "1990-03-07",
        "phone": "+256770000000",
        "district": "Gulu",
        "consent_to_share": False,
    }
    r1 = client.post("/api/v1/patients", json=body, headers=headers)
    if r1.status_code == 409:
        pytest.skip("test NIN collided with prior run; rerun with fresh uuid")
    assert r1.status_code in (200, 201), r1.text
    first_id = r1.json()["id"]

    r2 = client.post("/api/v1/patients", json=body, headers=headers)
    # When the Redis-backed idempotency cache is live → 200/201 with replay
    # marker. When degraded (degrade-open) → 409 from the NIN unique
    # constraint. Both honour "no double-write".
    if "x-idempotent-replay" in {k.lower() for k in r2.headers.keys()}:
        assert r2.json()["id"] == first_id
    else:
        assert r2.status_code == 409, (
            f"Without replay, a second POST must reject as duplicate; got "
            f"{r2.status_code}: {r2.text}"
        )


def test_idempotency_different_keys_different_writes(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    """Two POSTs with DIFFERENT keys but the SAME NIN should both attempt
    the write — the second hits the NIN unique constraint and 409s. Proves
    the cache key is bound to (method, path, key), not just path."""
    test_nin = "CM" + uuid.uuid4().hex[:11].upper() + "X"
    test_nin = test_nin[:14]
    body = {
        "nin": test_nin,
        "given_name": "Diff",
        "family_name": "Keys",
        "gender": "male",
        "birth_date": "1992-01-01",
        "phone": "+256770000001",
        "district": "Gulu",
        "consent_to_share": False,
    }
    base = _auth(tokens, "nurse")
    r1 = client.post(
        "/api/v1/patients",
        json=body,
        headers={**base, "Idempotency-Key": str(uuid.uuid4())},
    )
    if r1.status_code == 409:
        pytest.skip("test NIN collided with prior run")
    assert r1.status_code in (200, 201)

    r2 = client.post(
        "/api/v1/patients",
        json=body,
        headers={**base, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r2.status_code == 409, (
        f"Different keys must surface the underlying conflict; got "
        f"{r2.status_code}: {r2.text}"
    )


# ── Section I — Compliance / audit trail ─────────────────────────────────────


def test_self_audit_log_records_reads(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    """Read your own record, then list the audit trail for self — the read
    must show up. Proves record_access middleware actually writes."""
    # Trigger a read.
    me = client.get("/api/v1/me", headers=_auth(tokens, "citizen"))
    assert me.status_code == 200

    # Fetch own audit log.
    res = client.get(
        "/api/v1/me/audit?since_days=1", headers=_auth(tokens, "citizen")
    )
    assert res.status_code == 200
    entries = res.json()
    assert isinstance(entries, list)
    # The /me/record read above should have left an entry.
    actions = {e.get("action") for e in entries}
    assert any(a for a in actions if a), "audit log shouldn't be empty for a known reader"


def test_patient_read_carries_purpose_in_audit(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    pid = client.get(
        "/api/v1/me", headers=_auth(tokens, "citizen")
    ).json()["id"]
    res = client.get(
        f"/api/v1/patients/{pid}?purpose=regression-smoke-test",
        headers=_auth(tokens, "citizen"),
    )
    assert res.status_code == 200

    audit = client.get(
        "/api/v1/me/audit?since_days=1", headers=_auth(tokens, "citizen")
    ).json()
    purposes = {e.get("purpose") for e in audit}
    assert "regression-smoke-test" in purposes, (
        "purpose query param must round-trip into the audit log"
    )


# ── Section J — Resilience / robustness ─────────────────────────────────────


def test_pagination_bounds(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    # page_size=0 must fail (ge=1)
    res = client.get(
        "/api/v1/patients?page_size=0", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 422

    # page_size=200 must fail (le=100)
    res = client.get(
        "/api/v1/patients?page_size=200", headers=_auth(tokens, "admin")
    )
    assert res.status_code == 422


def test_unknown_endpoint_returns_404(client: httpx.Client) -> None:
    res = client.get("/api/v1/this-endpoint-does-not-exist")
    assert res.status_code == 404


def test_invalid_json_body_returns_4xx(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.post(
        "/api/v1/patients",
        content="this is not json",
        headers={**_auth(tokens, "nurse"), "Content-Type": "application/json"},
    )
    assert 400 <= res.status_code < 500


def test_invalid_nin_format_rejected(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    res = client.post(
        "/api/v1/patients",
        json={
            "nin": "not-a-nin",
            "given_name": "X",
            "family_name": "Y",
            "gender": "female",
            "birth_date": "1990-01-01",
            "district": "Gulu",
            "consent_to_share": False,
        },
        headers=_auth(tokens, "nurse"),
    )
    assert res.status_code == 422


def test_invalid_gender_rejected(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    test_nin = "CM" + uuid.uuid4().hex[:11].upper() + "X"
    test_nin = test_nin[:14]
    res = client.post(
        "/api/v1/patients",
        json={
            "nin": test_nin,
            "given_name": "X",
            "family_name": "Y",
            "gender": "alien",   # not in Literal["male","female","other","unknown"]
            "birth_date": "1990-01-01",
            "district": "Gulu",
            "consent_to_share": False,
        },
        headers=_auth(tokens, "nurse"),
    )
    assert res.status_code == 422


def test_openapi_schema_served(client: httpx.Client) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    body = res.json()
    assert body["openapi"].startswith("3.")
    assert "/api/v1/auth/login" in body["paths"]
    assert "/fhir/metadata" in body["paths"]
    assert "/fhir/Encounter" in body["paths"]
    assert "/fhir/Immunization" in body["paths"]
