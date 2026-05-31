"""Integration coverage for the citizen self-service (`/api/v1/me/*`) and
interop (`/api/v1/interop/*`) endpoints.

Mirrors the pattern in ``tests/test_rbac_scoping.py``: every test runs against
the in-memory SQLite app from ``conftest.py``, seeds the demo dataset via
``POST /api/v1/auth/seed-demo``, then drives the real HTTP surface.

The endpoints under test resolve a *citizen* from the JWT subject (the 14-char
NIN), so citizen-only routes are exercised with a token minted by the
NIN + OTP-stub flow (``/api/v1/auth/citizen/login`` with otp ``000000``).

Seed personas exercised here:
  * Achieng Akello — NIN ``CM85051712345X`` (the "self-service" citizen;
    Gulu district; has seeded encounters + a default cross-facility consent +
    synthetic prior worker audit reads). She is NOT a caregiver, so her family
    list is empty — that empty-but-200 shape is itself asserted.
  * A seeded mother — NIN ``CF93081244778K`` — who IS a caregiver for two
    children, used to assert a populated family view.
  * nurse.gulu (worker @ GUL-RRH-002), dho.gulu (district_admin),
    admin (ministry_admin).
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.anyio


# ── Personas / constants ─────────────────────────────────────────────────────

CITIZEN_NIN = "CM85051712345X"          # Achieng Akello — the self-service demo citizen
CITIZEN_GIVEN = "Achieng"
CITIZEN_FAMILY = "Akello"
CITIZEN_DISTRICT = "Gulu"

CAREGIVER_NIN = "CF93081244778K"        # seeded mother, caregiver for two children

# A syntactically valid Ugandan NIN (CM/CF + 12 alnum + checkletter) that the
# seed never creates — used to assert the 404 path on citizen login.
UNKNOWN_NIN = "CM99999999999Z"

_VACCINE_CODE_SYSTEM = "http://snomed.info/sct"


# ── Auth / seed helpers (local copies, mirroring test_rbac_scoping.py) ────────


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


async def _seed(client) -> None:
    """Populate the in-memory DB with the demo dataset. Idempotent."""
    res = await client.post("/api/v1/auth/seed-demo")
    assert res.status_code == 200, res.text


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# A minimal async stand-in for the Redis list ops the DHIS2 drain uses. The
# test stack has no Redis (conftest mocks it away), and the drain endpoint
# calls get_redis() directly — not via FastAPI DI — so we monkeypatch the
# symbol the client module imported.
class _FakeRedis:
    def __init__(self, seed: dict[str, list[str]] | None = None) -> None:
        self.store: dict[str, list[str]] = dict(seed or {})

    async def lpop(self, key: str) -> str | None:
        q = self.store.get(key, [])
        return q.pop(0) if q else None

    async def rpush(self, key: str, *values: str) -> int:
        self.store.setdefault(key, []).extend(values)
        return len(self.store[key])

    async def lpush(self, key: str, *values: str) -> int:
        for v in values:
            self.store.setdefault(key, []).insert(0, v)
        return len(self.store[key])


# ── /me — own patient record ─────────────────────────────────────────────────


async def test_me_returns_own_patient_record(client) -> None:
    """A citizen token resolves to their own Patient record via the NIN claim."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)

    res = await client.get("/api/v1/me", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nin"] == CITIZEN_NIN
    assert body["given_name"] == CITIZEN_GIVEN
    assert body["family_name"] == CITIZEN_FAMILY
    assert body["district"] == CITIZEN_DISTRICT
    # PatientOut surfaces these flags/versioning fields.
    assert body["deceased"] is False
    assert body["record_version"] >= 1
    assert body.get("id")


async def test_me_requires_authentication(client) -> None:
    """No bearer token → 401 (handled by the security dependency)."""
    await _seed(client)
    res = await client.get("/api/v1/me")
    assert res.status_code == 401, res.text


async def test_me_rejects_staff_token(client) -> None:
    """`/me` is citizen-only; a worker token is refused with 403."""
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get("/api/v1/me", headers=_auth(staff))
    assert res.status_code == 403, res.text


# ── /me/encounters ───────────────────────────────────────────────────────────


async def test_me_encounters_returns_own_history(client) -> None:
    """The citizen sees only their own encounters, each with observations and
    the EncounterOut shape."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)

    # Resolve own patient id to assert ownership of every returned row.
    me = (await client.get("/api/v1/me", headers=_auth(token))).json()
    own_id = me["id"]

    res = await client.get("/api/v1/me/encounters", headers=_auth(token))
    assert res.status_code == 200, res.text
    encounters = res.json()
    # The seed's "general" persona always gets >= 2 finished encounters.
    assert isinstance(encounters, list) and encounters
    for enc in encounters:
        assert enc["patient_id"] == own_id
        assert {"id", "facility_id", "reason", "status", "started_at",
                "diagnosis_codes", "observations", "created_at"} <= enc.keys()
        assert isinstance(enc["observations"], list)
        for obs in enc["observations"]:
            assert obs["patient_id"] == own_id
            assert obs["encounter_id"] == enc["id"]


async def test_me_encounters_requires_citizen(client) -> None:
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get("/api/v1/me/encounters", headers=_auth(staff))
    assert res.status_code == 403, res.text

    res = await client.get("/api/v1/me/encounters")
    assert res.status_code == 401, res.text


# ── /me/immunisations ────────────────────────────────────────────────────────


async def test_me_immunisations_returns_vaccine_observations(client) -> None:
    """Immunisations are the citizen's SNOMED-coded vaccine observations.

    The seed administers vaccines probabilistically for an adult "general"
    persona, so the list may be empty — but when present each row carries the
    ImmunisationOut shape and is SNOMED-coded.
    """
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    me = (await client.get("/api/v1/me", headers=_auth(token))).json()
    own_id = me["id"]

    res = await client.get("/api/v1/me/immunisations", headers=_auth(token))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert isinstance(rows, list)
    for imm in rows:
        assert {"id", "encounter_id", "patient_id", "code_system", "code",
                "administered_at", "facility_id"} <= imm.keys()
        assert imm["patient_id"] == own_id
        # Only vaccines (SNOMED) are surfaced — LOINC vitals are excluded.
        assert imm["code_system"] == _VACCINE_CODE_SYSTEM


async def test_me_immunisations_authz(client) -> None:
    await _seed(client)
    staff = await _login(client, "dho.gulu", "demo1234")
    assert (await client.get("/api/v1/me/immunisations", headers=_auth(staff))).status_code == 403
    assert (await client.get("/api/v1/me/immunisations")).status_code == 401


# ── /me/family ───────────────────────────────────────────────────────────────


async def test_me_family_empty_for_non_caregiver(client) -> None:
    """Achieng is not registered as anyone's caregiver — her family list is an
    empty list (200, not 404)."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    res = await client.get("/api/v1/me/family", headers=_auth(token))
    assert res.status_code == 200, res.text
    assert res.json() == []


async def test_me_family_lists_children_for_caregiver(client) -> None:
    """A seeded mother sees a card per linked child with the FamilyMemberOut
    shape (incl. overdue antigen summary)."""
    await _seed(client)
    token = await _citizen_login(client, CAREGIVER_NIN)
    res = await client.get("/api/v1/me/family", headers=_auth(token))
    assert res.status_code == 200, res.text
    family = res.json()
    # Seed links this caregiver to two children.
    assert len(family) == 2
    for member in family:
        assert {"link_id", "patient_id", "nin", "given_name", "family_name",
                "birth_date", "gender", "relationship",
                "overdue_antigen_count"} <= member.keys()
        assert member["relationship"] == "mother"
        assert isinstance(member["overdue_antigen_count"], int)
        assert member["overdue_antigen_count"] >= 0


async def test_me_family_authz(client) -> None:
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    assert (await client.get("/api/v1/me/family", headers=_auth(staff))).status_code == 403
    assert (await client.get("/api/v1/me/family")).status_code == 401


# ── /me/audit — who accessed my record ───────────────────────────────────────


async def test_me_audit_lists_accesses_to_own_record(client) -> None:
    """The citizen sees the access log for their PII. The seed injects prior
    worker reads, so the feed is non-empty and includes worker actors."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    me = (await client.get("/api/v1/me", headers=_auth(token))).json()
    own_id = me["id"]

    res = await client.get("/api/v1/me/audit", headers=_auth(token))
    assert res.status_code == 200, res.text
    entries = res.json()
    assert isinstance(entries, list) and entries
    for e in entries:
        assert {"id", "actor_role", "action", "resource_type", "resource_id",
                "occurred_at"} <= e.keys()
        # Every entry is about THIS citizen's own Patient resource.
        assert e["resource_type"] == "Patient"
        assert e["resource_id"] == own_id
    # Seeded synthetic reads are by workers.
    assert any(e["actor_role"] == "worker" for e in entries)


async def test_me_audit_since_days_is_validated(client) -> None:
    """`since_days` is bounded 1..365 — out-of-range values are rejected."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    # Valid bound passes.
    ok = await client.get(
        "/api/v1/me/audit", params={"since_days": 30}, headers=_auth(token)
    )
    assert ok.status_code == 200, ok.text
    # Below the floor (ge=1) → 422.
    bad = await client.get(
        "/api/v1/me/audit", params={"since_days": 0}, headers=_auth(token)
    )
    assert bad.status_code == 422, bad.text


async def test_me_audit_authz(client) -> None:
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    assert (await client.get("/api/v1/me/audit", headers=_auth(staff))).status_code == 403
    assert (await client.get("/api/v1/me/audit")).status_code == 401


# ── /me/consent/grant + consent list/revoke (citizen-owned) ──────────────────


async def test_citizen_lists_own_consents(client) -> None:
    """The seed grants each patient a default cross-facility consent, which the
    citizen can read back via the consents endpoint (own-record guarded)."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    me = (await client.get("/api/v1/me", headers=_auth(token))).json()
    own_id = me["id"]

    res = await client.get(
        f"/api/v1/consents/by-patient/{own_id}", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    consents = res.json()
    assert isinstance(consents, list) and consents
    assert all(c["patient_id"] == own_id for c in consents)
    assert any(
        c["scope"] == "share_records_across_facilities" for c in consents
    )


async def test_citizen_grants_then_revokes_own_consent(client) -> None:
    """Full self-service consent lifecycle: grant (201) → appears in list →
    revoke (200, revoked_at set)."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    me = (await client.get("/api/v1/me", headers=_auth(token))).json()
    own_id = me["id"]

    grant = await client.post(
        "/api/v1/me/consent/grant",
        headers=_auth(token),
        json={
            "scope": "share_with_emergency_services",
            "purpose": "emergency access for ambulance crews",
        },
    )
    assert grant.status_code == 201, grant.text
    created = grant.json()
    # The grant is attributed to the caller's OWN patient record.
    assert created["patient_id"] == own_id
    assert created["scope"] == "share_with_emergency_services"
    assert created["revoked_at"] is None
    consent_id = created["id"]

    # It now shows up in the citizen's own consent list.
    listing = await client.get(
        f"/api/v1/consents/by-patient/{own_id}", headers=_auth(token)
    )
    assert listing.status_code == 200, listing.text
    assert any(c["id"] == consent_id for c in listing.json())

    # Revoke it — citizens may revoke consents on their own record.
    revoke = await client.post(
        f"/api/v1/consents/{consent_id}/revoke", headers=_auth(token)
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["revoked_at"] is not None


async def test_consent_grant_rejects_invalid_body(client) -> None:
    """OwnConsentGrant enforces a 4-char purpose floor and a closed scope
    enum — both surface as 422 before any DB write."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)

    short_purpose = await client.post(
        "/api/v1/me/consent/grant",
        headers=_auth(token),
        json={"scope": "share_with_research", "purpose": "x"},
    )
    assert short_purpose.status_code == 422, short_purpose.text

    bad_scope = await client.post(
        "/api/v1/me/consent/grant",
        headers=_auth(token),
        json={"scope": "share_with_aliens", "purpose": "a valid purpose string"},
    )
    assert bad_scope.status_code == 422, bad_scope.text


async def test_consent_grant_requires_citizen(client) -> None:
    """`/me/consent/grant` is a citizen-only route — staff/unauth are refused."""
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    body: dict[str, Any] = {
        "scope": "share_with_research",
        "purpose": "worker should not reach this",
    }
    assert (
        await client.post(
            "/api/v1/me/consent/grant", headers=_auth(staff), json=body
        )
    ).status_code == 403
    assert (
        await client.post("/api/v1/me/consent/grant", json=body)
    ).status_code == 401


async def test_citizen_cannot_touch_another_citizens_consents(client) -> None:
    """A citizen may neither LIST nor REVOKE consents belonging to a different
    patient — both must 403 even though authentication succeeds."""
    await _seed(client)

    # The caregiver mother grants a consent on her own record.
    caregiver = await _citizen_login(client, CAREGIVER_NIN)
    caregiver_me = (
        await client.get("/api/v1/me", headers=_auth(caregiver))
    ).json()
    caregiver_pid = caregiver_me["id"]
    grant = await client.post(
        "/api/v1/me/consent/grant",
        headers=_auth(caregiver),
        json={
            "scope": "share_with_research",
            "purpose": "longitudinal child-health research",
        },
    )
    assert grant.status_code == 201, grant.text
    foreign_consent_id = grant.json()["id"]

    # Achieng (a different citizen) tries to reach the caregiver's consents.
    achieng = await _citizen_login(client, CITIZEN_NIN)

    listing = await client.get(
        f"/api/v1/consents/by-patient/{caregiver_pid}", headers=_auth(achieng)
    )
    assert listing.status_code == 403, listing.text

    revoke = await client.post(
        f"/api/v1/consents/{foreign_consent_id}/revoke", headers=_auth(achieng)
    )
    assert revoke.status_code == 403, revoke.text

    # And the caregiver's consent is untouched (still active).
    still = await client.get(
        f"/api/v1/consents/by-patient/{caregiver_pid}", headers=_auth(caregiver)
    )
    assert still.status_code == 200, still.text
    assert any(
        c["id"] == foreign_consent_id and c["revoked_at"] is None
        for c in still.json()
    )


# ── /me/profile — self-service contact update ────────────────────────────────


async def test_citizen_updates_own_profile(client) -> None:
    """A citizen may patch their own contact fields; record_version bumps and
    the change is reflected on the next read."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    before = (await client.get("/api/v1/me", headers=_auth(token))).json()

    patch = await client.patch(
        "/api/v1/me/profile",
        headers=_auth(token),
        json={"phone": "+256700999888", "village": "Kanyagoga North"},
    )
    assert patch.status_code == 200, patch.text
    updated = patch.json()
    assert updated["phone"] == "+256700999888"
    assert updated["village"] == "Kanyagoga North"
    assert updated["record_version"] == before["record_version"] + 1
    # Immutable identity fields are untouched.
    assert updated["nin"] == CITIZEN_NIN
    assert updated["district"] == CITIZEN_DISTRICT


async def test_profile_update_requires_citizen(client) -> None:
    await _seed(client)
    staff = await _login(client, "nurse.gulu", "demo1234")
    res = await client.patch(
        "/api/v1/me/profile", headers=_auth(staff), json={"phone": "+256700111222"}
    )
    assert res.status_code == 403, res.text


# ── /me/staff — staff-side mirror ────────────────────────────────────────────


async def test_me_staff_returns_profile_and_facility(client) -> None:
    """`/me/staff` returns the calling worker's profile + facility context, and
    never leaks the password hash."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get("/api/v1/me/staff", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["username"] == "nurse.gulu"
    assert body["role"] == "worker"
    assert body["facility_id"]
    assert body["facility_name"]  # resolved from the Facility row
    assert body["active"] is True
    assert "password_hash" not in body


async def test_me_staff_rejects_citizen_token(client) -> None:
    """The staff mirror refuses citizen tokens (the counterpart of `/me`
    refusing staff tokens)."""
    await _seed(client)
    token = await _citizen_login(client, CITIZEN_NIN)
    res = await client.get("/api/v1/me/staff", headers=_auth(token))
    assert res.status_code == 403, res.text


async def test_me_staff_requires_auth(client) -> None:
    await _seed(client)
    res = await client.get("/api/v1/me/staff")
    assert res.status_code == 401, res.text


# ── Nearby facilities (public reference data the citizen UI consumes) ─────────


async def test_facilities_listing_and_filters(client) -> None:
    """The facilities reference endpoint (the "nearby facilities" picker) lists
    active facilities with geo coords and supports district/level filters."""
    await _seed(client)

    res = await client.get("/api/v1/facilities")
    assert res.status_code == 200, res.text
    facilities = res.json()
    assert isinstance(facilities, list) and facilities
    sample = facilities[0]
    assert {"id", "code", "name", "level", "district",
            "sub_county", "latitude", "longitude"} <= sample.keys()

    # District filter restricts the set.
    gulu = await client.get("/api/v1/facilities", params={"district": CITIZEN_DISTRICT})
    assert gulu.status_code == 200, gulu.text
    gulu_rows = gulu.json()
    assert gulu_rows
    assert {r["district"] for r in gulu_rows} == {CITIZEN_DISTRICT}
    assert len(gulu_rows) < len(facilities)

    # Level filter restricts to a single level value.
    level = sample["level"]
    by_level = await client.get("/api/v1/facilities", params={"level": level})
    assert by_level.status_code == 200, by_level.text
    assert {r["level"] for r in by_level.json()} == {level}


# ── Citizen login edge cases (NIN/OTP stub boundary) ─────────────────────────


async def test_citizen_login_rejects_bad_otp(client) -> None:
    await _seed(client)
    res = await client.post(
        "/api/v1/auth/citizen/login",
        json={"nin": CITIZEN_NIN, "otp": "111111"},
    )
    assert res.status_code == 401, res.text


async def test_citizen_login_unknown_nin_is_404(client) -> None:
    """A well-formed NIN with no NIRA/Patient match → 404 (no token issued)."""
    await _seed(client)
    res = await client.post(
        "/api/v1/auth/citizen/login",
        json={"nin": UNKNOWN_NIN, "otp": "000000"},
    )
    assert res.status_code == 404, res.text


# ── Interop — mock NIRA verify ───────────────────────────────────────────────


async def test_mock_nira_verify_returns_expected_shape(client) -> None:
    """The mock NIRA endpoint reflects the seeded Patient back as a NIRA-style
    identity record."""
    await _seed(client)
    res = await client.get(f"/api/v1/interop/mock/nira/verify/{CITIZEN_NIN}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {
        "full_name": f"{CITIZEN_GIVEN} {CITIZEN_FAMILY}",
        "gender": "female",
        "date_of_birth": "1985-05-17",
        "district": CITIZEN_DISTRICT,
    }


async def test_mock_nira_verify_unknown_nin_is_404(client) -> None:
    await _seed(client)
    res = await client.get(f"/api/v1/interop/mock/nira/verify/{UNKNOWN_NIN}")
    assert res.status_code == 404, res.text


# ── Interop — mock DHIS2 dataValueSets ───────────────────────────────────────


async def test_mock_dhis2_data_value_sets_imports_count(client) -> None:
    """The mock DHIS2 sink reports SUCCESS and echoes the count of dataValues."""
    await _seed(client)
    payload = {
        "dataValues": [
            {"dataElement": "DE1", "period": "2026Q1", "orgUnit": "OU1", "value": 3},
            {"dataElement": "DE2", "period": "2026Q1", "orgUnit": "OU1", "value": 7},
        ]
    }
    res = await client.post(
        "/api/v1/interop/mock/dhis2/dataValueSets", json=payload
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"status": "SUCCESS", "imported": 2}


async def test_mock_dhis2_empty_payload_imports_zero(client) -> None:
    await _seed(client)
    res = await client.post("/api/v1/interop/mock/dhis2/dataValueSets", json={})
    assert res.status_code == 200, res.text
    assert res.json() == {"status": "SUCCESS", "imported": 0}


# ── Interop — circuit-breaker status + controls ──────────────────────────────


async def test_circuits_status_requires_ministry_admin(client) -> None:
    """Listing circuit breakers is a ministry_admin action; a worker is 403 and
    an anonymous caller is 401."""
    await _seed(client)
    worker = await _login(client, "nurse.gulu", "demo1234")
    assert (
        await client.get("/api/v1/interop/circuits", headers=_auth(worker))
    ).status_code == 403
    assert (await client.get("/api/v1/interop/circuits")).status_code == 401


async def test_circuit_trip_then_status_shows_open(client) -> None:
    """Tripping a breaker via the demo control flips it OPEN, and the status
    endpoint reflects the new state + failure count at threshold."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")

    trip = await client.post(
        "/api/v1/interop/circuits/dhis2/trip", headers=_auth(admin)
    )
    assert trip.status_code == 200, trip.text
    assert trip.json() == {"breaker": "dhis2", "state": "open"}

    listing = await client.get("/api/v1/interop/circuits", headers=_auth(admin))
    assert listing.status_code == 200, listing.text
    breakers = {b["name"]: b for b in listing.json()}
    assert "dhis2" in breakers
    dhis2 = breakers["dhis2"]
    assert dhis2["state"] == "open"
    assert dhis2["failures"] == dhis2["failure_threshold"]
    # BreakerStatus shape.
    assert {"name", "state", "failures", "failure_threshold"} <= dhis2.keys()


async def test_circuit_trip_requires_ministry_admin(client) -> None:
    await _seed(client)
    worker = await _login(client, "nurse.gulu", "demo1234")
    res = await client.post(
        "/api/v1/interop/circuits/dhis2/trip", headers=_auth(worker)
    )
    assert res.status_code == 403, res.text


# ── Interop — DHIS2 queue drain ──────────────────────────────────────────────


async def test_dhis2_drain_queue_requires_district_admin(client) -> None:
    """The drain endpoint is gated at district_admin: a worker is 403 and an
    anonymous caller is 401. (No Redis needed — the guard fires first.)"""
    await _seed(client)
    worker = await _login(client, "nurse.gulu", "demo1234")
    assert (
        await client.post("/api/v1/interop/dhis2/drain-queue", headers=_auth(worker))
    ).status_code == 403
    assert (
        await client.post("/api/v1/interop/dhis2/drain-queue")
    ).status_code == 401


async def test_dhis2_drain_queue_drains_empty_outbox(client) -> None:
    """With an empty outbox the drain returns ``{"delivered": 0}``.

    The endpoint talks to Redis directly (not via FastAPI DI) and the test
    stack has no Redis, so we monkeypatch the DHIS2 client's ``get_redis`` with
    an in-memory fake whose queue is empty.
    """
    import app.services.dhis2_client as dhis2_mod

    fake = _FakeRedis()
    original = dhis2_mod.get_redis

    async def _fake_get_redis() -> _FakeRedis:
        return fake

    dhis2_mod.get_redis = _fake_get_redis  # type: ignore[assignment]
    try:
        await _seed(client)
        dho = await _login(client, "dho.gulu", "demo1234")
        res = await client.post(
            "/api/v1/interop/dhis2/drain-queue", headers=_auth(dho)
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"delivered": 0}
    finally:
        dhis2_mod.get_redis = original  # type: ignore[assignment]
