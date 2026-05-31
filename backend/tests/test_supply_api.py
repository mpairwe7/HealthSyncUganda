"""Comprehensive coverage for the supply-chain API and the stock ledger service.

Two test surfaces live here:

* Integration tests against the FastAPI app (in-memory SQLite from
  ``conftest.py``) exercising every supply endpoint — items list, stock
  snapshot, low-stock alerts, receive batch, inter-facility transfer (create +
  list), and dispense — across the RBAC role story (worker / pharmacist /
  admin), unauthenticated 401s, validation 422s, not-found 404s, and the
  pharmacist facility-scoping rule (cross-facility → 403).

* Unit tests against ``app.services.supply_ledger`` via the ``db_session``
  fixture: hash-chain integrity across real persisted events, FEFO ordering,
  ``InsufficientStockError`` surfacing, and the append-only contract. These
  complement ``test_supply_ledger.py`` (which only covers the pure
  ``_hash_event`` helper) — the async ledger functions were previously
  untested at the DB level.

Seed personas (password ``demo1234`` unless noted):
  admin / admin1234         — ministry_admin (no facility)
  nurse.gulu                — worker      @ GUL-RRH-002
  doctor.kampala            — worker      @ MUL-NRH-001
  pharmacist.mbarara        — pharmacist  @ MBR-RRH-003
  dho.gulu                  — district_admin @ GUL-RRH-002

Seed storyline invariants we lean on (see app/seed/run.py:_seed_stock):
  * MBR-RRH-003 / ACT-AL-001 seeded at 120  (threshold 500 → below).
  * GUL-RRH-002 / VAC-PCV-001 seeded at 35  (threshold 60  → below).
  * ~6 historical StockTransfer rows seeded for the transfers list.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.supply_ledger import (
    InsufficientStockError,
    append_event,
    dispense,
    receive_stock,
    verify_chain,
)

pytestmark = pytest.mark.anyio


# ── shared helpers (mirror tests/test_rbac_scoping.py) ───────────────────────

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


async def _login_full(client, identifier: str, password: str) -> dict:
    """Return the full token payload (carries facility_id, role, subject)."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _facility_ids_by_code(client) -> dict[str, str]:
    """Resolve seeded facility code → ULID id via the public facilities list."""
    res = await client.get("/api/v1/facilities")
    assert res.status_code == 200, res.text
    return {f["code"]: f["id"] for f in res.json()}


async def _item_ids_by_code(client, token: str) -> dict[str, str]:
    """Resolve supply item code → id from the items list (worker+ may read)."""
    res = await client.get("/api/v1/supply/items", headers=_auth(token))
    assert res.status_code == 200, res.text
    return {it["code"]: it["id"] for it in res.json()}


# ─────────────────────────────────────────────────────────────────────────────
# Supply items list
# ─────────────────────────────────────────────────────────────────────────────

async def test_items_list_one_row_per_item_with_aggregates(client) -> None:
    """GET /supply/items returns exactly one row per SupplyItem, carrying the
    folded on-hand total and the count of facilities currently stocking it."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")

    res = await client.get("/api/v1/supply/items", headers=_auth(token))
    assert res.status_code == 200, res.text
    items = res.json()

    # 14 supply items are seeded; one row each (no duplication from the join).
    assert len(items) == 14
    codes = [it["code"] for it in items]
    assert len(codes) == len(set(codes)), "items must not be duplicated by the batch join"
    assert "ACT-AL-001" in codes

    # Sorted by name (endpoint orders by SupplyItem.name).
    names = [it["name"] for it in items]
    assert names == sorted(names)

    for it in items:
        # Schema shape / non-negativity invariants.
        assert set(it) >= {
            "id", "code", "name", "category", "unit",
            "reorder_threshold", "requires_cold_chain",
            "on_hand_total", "facilities_stocked",
        }
        assert it["on_hand_total"] >= 0
        assert it["facilities_stocked"] >= 0

    # Stock is seeded broadly, so at least one item is stocked somewhere.
    assert any(it["on_hand_total"] > 0 for it in items)
    assert any(it["facilities_stocked"] > 0 for it in items)


async def test_items_list_requires_worker_role(client) -> None:
    """Unauthenticated → 401; citizen would be < worker → 403."""
    await _seed(client)
    # Unauthenticated.
    res = await client.get("/api/v1/supply/items")
    assert res.status_code == 401, res.text


# ─────────────────────────────────────────────────────────────────────────────
# Stock snapshot + facility scoping + low-stock alerts
# ─────────────────────────────────────────────────────────────────────────────

async def test_snapshot_returns_per_facility_per_item_rows(client) -> None:
    """GET /supply/snapshot folds the ledger into (facility, item) rows with a
    correct is_below_threshold flag and an earliest_expiry."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")

    res = await client.get("/api/v1/supply/snapshot", headers=_auth(token))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows, "seed populates stock at every facility"

    sample = rows[0]
    assert set(sample) >= {
        "facility_id", "facility_name", "item_code", "item_name",
        "on_hand", "reorder_threshold", "earliest_expiry", "is_below_threshold",
    }
    # The flag must agree with the numbers it claims to summarise.
    for r in rows:
        assert r["is_below_threshold"] == (r["on_hand"] < r["reorder_threshold"])


async def test_snapshot_district_filter(client) -> None:
    """The ?district= filter restricts rows to facilities in that district."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")

    res = await client.get(
        "/api/v1/supply/snapshot",
        params={"district": "Mbarara"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows, "Mbarara has seeded stock"

    mbarara_ids = {
        c: i
        for c, i in (await _facility_ids_by_code(client)).items()
        if c.startswith("MBR-")
    }.values()
    assert all(r["facility_id"] in set(mbarara_ids) for r in rows)


async def test_snapshot_only_below_threshold_flag_consistent(client) -> None:
    """?only_below_threshold=true returns a subset where every row is below
    its reorder threshold — and the storyline below-threshold rows survive."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")

    res = await client.get(
        "/api/v1/supply/snapshot",
        params={"only_below_threshold": "true"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert all(r["is_below_threshold"] for r in rows)
    # Seed deliberately puts Mbarara's ACT-AL (120 < 500) below threshold.
    assert any(
        r["item_code"] == "ACT-AL-001" and r["on_hand"] < r["reorder_threshold"]
        for r in rows
    ), "the seeded low-stock storyline row must appear"


async def test_low_stock_alerts_match_below_threshold_snapshot(client) -> None:
    """GET /supply/alerts/low-stock is the below-threshold snapshot view."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")

    alerts = await client.get("/api/v1/supply/alerts/low-stock", headers=_auth(token))
    assert alerts.status_code == 200, alerts.text
    below = await client.get(
        "/api/v1/supply/snapshot",
        params={"only_below_threshold": "true"},
        headers=_auth(token),
    )
    assert below.status_code == 200, below.text

    def _key(r: dict) -> tuple[str, str]:
        return (r["facility_id"], r["item_code"])

    assert {_key(r) for r in alerts.json()} == {_key(r) for r in below.json()}
    assert all(r["is_below_threshold"] for r in alerts.json())
    # Gulu's PCV (35 < 60) is the seeded critical alert.
    assert any(r["item_code"] == "VAC-PCV-001" for r in alerts.json())


async def test_snapshot_requires_auth(client) -> None:
    await _seed(client)
    res = await client.get("/api/v1/supply/snapshot")
    assert res.status_code == 401, res.text


# ─────────────────────────────────────────────────────────────────────────────
# Receive stock (batches) — happy path, authz, scoping, validation, not-found
# ─────────────────────────────────────────────────────────────────────────────

async def test_receive_batch_happy_path_increments_on_hand(client) -> None:
    """A pharmacist receives a batch at their own facility; the item's on-hand
    total grows by the received quantity (ledger folded back into the list)."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    mbarara_id = pharm["facility_id"]
    assert mbarara_id, "pharmacist token must carry a facility_id"

    items = await _item_ids_by_code(client, token)
    item_id = items["ORS-001"]

    before = next(it for it in (await client.get(
        "/api/v1/supply/items", headers=_auth(token)
    )).json() if it["code"] == "ORS-001")["on_hand_total"]

    body = {
        "supply_item_id": item_id,
        "facility_id": mbarara_id,
        "lot_number": "LOT-TEST-0001",
        "quantity": 750,
        "expires_on": (date.today() + timedelta(days=365)).isoformat(),
        "received_on": date.today().isoformat(),
        "cost_ugx": 500000,
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(token))
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["remaining"] == 750
    assert out["is_expired"] is False
    assert out["id"]

    after = next(it for it in (await client.get(
        "/api/v1/supply/items", headers=_auth(token)
    )).json() if it["code"] == "ORS-001")["on_hand_total"]
    assert after == before + 750


async def test_receive_batch_appends_to_ledger(client) -> None:
    """Receiving a batch writes a 'received' ledger event for the facility —
    on-hand reflected in the snapshot for that (facility, item)."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    mbarara_id = pharm["facility_id"]
    item_id = (await _item_ids_by_code(client, token))["DIA-MRDT-001"]

    def _on_hand(rows: list[dict]) -> int | None:
        for r in rows:
            if r["facility_id"] == mbarara_id and r["item_code"] == "DIA-MRDT-001":
                return r["on_hand"]
        return None

    before = _on_hand((await client.get(
        "/api/v1/supply/snapshot", params={"district": "Mbarara"}, headers=_auth(token)
    )).json()) or 0

    body = {
        "supply_item_id": item_id,
        "facility_id": mbarara_id,
        "lot_number": "LOT-MRDT-9999",
        "quantity": 200,
        "expires_on": (date.today() + timedelta(days=200)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(token))
    assert res.status_code == 201, res.text

    after = _on_hand((await client.get(
        "/api/v1/supply/snapshot", params={"district": "Mbarara"}, headers=_auth(token)
    )).json())
    assert after == before + 200


async def test_receive_batch_worker_forbidden(client) -> None:
    """A plain worker (< pharmacist) cannot receive stock → 403."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    facs = await _facility_ids_by_code(client)
    items = await _item_ids_by_code(client, nurse)

    body = {
        "supply_item_id": items["ORS-001"],
        "facility_id": facs["GUL-RRH-002"],
        "lot_number": "LOT-NOPE-0001",
        "quantity": 10,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(nurse))
    assert res.status_code == 403, res.text


async def test_receive_batch_unauthenticated(client) -> None:
    await _seed(client)
    facs = await _facility_ids_by_code(client)
    body = {
        "supply_item_id": "whatever",
        "facility_id": facs["GUL-RRH-002"],
        "lot_number": "LOT",
        "quantity": 10,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body)
    assert res.status_code == 401, res.text


async def test_receive_batch_pharmacist_cross_facility_forbidden(client) -> None:
    """Facility scoping: the Mbarara pharmacist cannot receive at Gulu → 403."""
    await _seed(client)
    pharm = await _login(client, "pharmacist.mbarara", "demo1234")
    facs = await _facility_ids_by_code(client)
    items = await _item_ids_by_code(client, pharm)

    body = {
        "supply_item_id": items["ORS-001"],
        "facility_id": facs["GUL-RRH-002"],  # NOT the pharmacist's facility
        "lot_number": "LOT-XFAC-0001",
        "quantity": 100,
        "expires_on": (date.today() + timedelta(days=120)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(pharm))
    assert res.status_code == 403, res.text
    assert "facility" in res.json()["detail"].lower()


async def test_receive_batch_admin_bypasses_facility_scope(client) -> None:
    """A ministry_admin has no facility and is exempt from the scoping guard —
    can receive at any facility."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    facs = await _facility_ids_by_code(client)
    items = await _item_ids_by_code(client, admin)

    body = {
        "supply_item_id": items["ORS-001"],
        "facility_id": facs["GUL-RRH-002"],
        "lot_number": "LOT-ADMIN-0001",
        "quantity": 300,
        "expires_on": (date.today() + timedelta(days=300)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(admin))
    assert res.status_code == 201, res.text


async def test_receive_batch_unknown_item_404(client) -> None:
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    body = {
        "supply_item_id": "01ABCDEFGHJKMNPQRSTVWXYZ00",  # well-formed but absent
        "facility_id": pharm["facility_id"],
        "lot_number": "LOT-404-0001",
        "quantity": 10,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post(
        "/api/v1/supply/batches", json=body, headers=_auth(pharm["access_token"])
    )
    assert res.status_code == 404, res.text
    assert "supply item" in res.json()["detail"].lower()


async def test_receive_batch_unknown_facility_404(client) -> None:
    """A pharmacist with a facility is scoped first, so use the admin (no
    facility → bypasses scope) to reach the 'Facility not found' branch."""
    await _seed(client)
    admin = await _login(client, "admin", "admin1234")
    item_id = (await _item_ids_by_code(client, admin))["ORS-001"]
    body = {
        "supply_item_id": item_id,
        "facility_id": "01ABCDEFGHJKMNPQRSTVWXYZ00",  # absent facility
        "lot_number": "LOT-404-0002",
        "quantity": 10,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post("/api/v1/supply/batches", json=body, headers=_auth(admin))
    assert res.status_code == 404, res.text
    assert "facility" in res.json()["detail"].lower()


async def test_receive_batch_already_expired_422(client) -> None:
    """A batch whose expiry is today-or-earlier is rejected as expired."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    item_id = (await _item_ids_by_code(client, pharm["access_token"]))["ORS-001"]
    body = {
        "supply_item_id": item_id,
        "facility_id": pharm["facility_id"],
        "lot_number": "LOT-EXP-0001",
        "quantity": 10,
        "expires_on": date.today().isoformat(),  # not strictly in the future
        "received_on": (date.today() - timedelta(days=1)).isoformat(),
    }
    res = await client.post(
        "/api/v1/supply/batches", json=body, headers=_auth(pharm["access_token"])
    )
    assert res.status_code == 422, res.text
    assert "expired" in res.json()["detail"].lower()


async def test_receive_batch_non_positive_quantity_422(client) -> None:
    """quantity must be > 0 (schema-level validation)."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    item_id = (await _item_ids_by_code(client, pharm["access_token"]))["ORS-001"]
    body = {
        "supply_item_id": item_id,
        "facility_id": pharm["facility_id"],
        "lot_number": "LOT-BAD-0001",
        "quantity": 0,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post(
        "/api/v1/supply/batches", json=body, headers=_auth(pharm["access_token"])
    )
    assert res.status_code == 422, res.text


async def test_receive_batch_missing_field_422(client) -> None:
    """Omitting a required field is a 422 validation error, not a 500."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    item_id = (await _item_ids_by_code(client, pharm["access_token"]))["ORS-001"]
    body = {
        "supply_item_id": item_id,
        "facility_id": pharm["facility_id"],
        # lot_number missing
        "quantity": 10,
        "expires_on": (date.today() + timedelta(days=90)).isoformat(),
        "received_on": date.today().isoformat(),
    }
    res = await client.post(
        "/api/v1/supply/batches", json=body, headers=_auth(pharm["access_token"])
    )
    assert res.status_code == 422, res.text


# ─────────────────────────────────────────────────────────────────────────────
# Inter-facility transfers — create, list, status, authz, validation
# ─────────────────────────────────────────────────────────────────────────────

async def test_transfer_create_moves_stock_between_facilities(client) -> None:
    """A pharmacist transfers from their own facility to another. The transfer
    completes synchronously, source on-hand drops, destination on-hand rises."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    src = pharm["facility_id"]
    facs = await _facility_ids_by_code(client)
    dst = facs["GUL-RRH-002"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]

    def _on_hand(rows: list[dict], facility_id: str) -> int:
        for r in rows:
            if r["facility_id"] == facility_id and r["item_code"] == "ORS-001":
                return r["on_hand"]
        return 0

    snap_before = (await client.get("/api/v1/supply/snapshot", headers=_auth(token))).json()
    src_before = _on_hand(snap_before, src)
    dst_before = _on_hand(snap_before, dst)
    assert src_before > 0, "source must have ORS stock to transfer"

    qty = 50
    body = {
        "from_facility_id": src,
        "to_facility_id": dst,
        "supply_item_id": item_id,
        "quantity": qty,
        "reason": "Routine inter-facility balancing",
    }
    res = await client.post("/api/v1/supply/transfers", json=body, headers=_auth(token))
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["status"] == "completed"
    assert out["from_facility_id"] == src
    assert out["to_facility_id"] == dst
    assert out["quantity"] == qty
    assert out["initiated_by"] == pharm["subject"]
    assert out["initiated_at"] is not None
    assert out["completed_at"] is not None

    snap_after = (await client.get("/api/v1/supply/snapshot", headers=_auth(token))).json()
    assert _on_hand(snap_after, src) == src_before - qty
    assert _on_hand(snap_after, dst) == dst_before + qty


async def test_transfer_same_facility_422(client) -> None:
    """Source == destination is rejected before any stock movement."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    src = pharm["facility_id"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]
    body = {
        "from_facility_id": src,
        "to_facility_id": src,
        "supply_item_id": item_id,
        "quantity": 10,
        "reason": "Should be rejected",
    }
    res = await client.post("/api/v1/supply/transfers", json=body, headers=_auth(token))
    assert res.status_code == 422, res.text
    assert "differ" in res.json()["detail"].lower()


async def test_transfer_insufficient_source_stock_422(client) -> None:
    """Transferring more than the source holds is a clean 422, not a 500."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    src = pharm["facility_id"]
    facs = await _facility_ids_by_code(client)
    dst = facs["GUL-RRH-002"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]
    body = {
        "from_facility_id": src,
        "to_facility_id": dst,
        "supply_item_id": item_id,
        "quantity": 10_000_000,  # far more than seeded
        "reason": "Over-draw the source on purpose",
    }
    res = await client.post("/api/v1/supply/transfers", json=body, headers=_auth(token))
    assert res.status_code == 422, res.text
    assert "cannot transfer" in res.json()["detail"].lower()


async def test_transfer_pharmacist_cross_facility_source_forbidden(client) -> None:
    """A pharmacist may only initiate transfers OUT of their own facility.
    Sourcing from a facility they don't own → 403."""
    await _seed(client)
    pharm = await _login(client, "pharmacist.mbarara", "demo1234")
    facs = await _facility_ids_by_code(client)
    item_id = (await _item_ids_by_code(client, pharm))["ORS-001"]
    body = {
        "from_facility_id": facs["GUL-RRH-002"],  # not the pharmacist's facility
        "to_facility_id": facs["MUL-NRH-001"],
        "supply_item_id": item_id,
        "quantity": 10,
        "reason": "Cross-facility source not allowed",
    }
    res = await client.post("/api/v1/supply/transfers", json=body, headers=_auth(pharm))
    assert res.status_code == 403, res.text


async def test_transfer_worker_forbidden(client) -> None:
    """A plain worker cannot initiate a transfer (needs pharmacist+) → 403."""
    await _seed(client)
    nurse = await _login(client, "nurse.gulu", "demo1234")
    facs = await _facility_ids_by_code(client)
    item_id = (await _item_ids_by_code(client, nurse))["ORS-001"]
    body = {
        "from_facility_id": facs["GUL-RRH-002"],
        "to_facility_id": facs["MUL-NRH-001"],
        "supply_item_id": item_id,
        "quantity": 10,
        "reason": "Workers cannot transfer",
    }
    res = await client.post("/api/v1/supply/transfers", json=body, headers=_auth(nurse))
    assert res.status_code == 403, res.text


async def test_transfer_validation_422(client) -> None:
    """Missing required body fields → 422 validation error."""
    await _seed(client)
    pharm = await _login(client, "pharmacist.mbarara", "demo1234")
    res = await client.post(
        "/api/v1/supply/transfers", json={"quantity": 5}, headers=_auth(pharm)
    )
    assert res.status_code == 422, res.text


async def test_transfer_list_returns_seeded_history(client) -> None:
    """GET /supply/transfers lists recent transfers (worker+ may read). The
    seed plants ~6 historical rows, ordered newest-first."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get("/api/v1/supply/transfers", headers=_auth(token))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) >= 6, "seed plants ~6 historical transfers"

    # Newest-first ordering by initiated_at.
    stamps = [r["initiated_at"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)
    for r in rows:
        assert set(r) >= {
            "id", "from_facility_id", "to_facility_id", "supply_item_id",
            "quantity", "reason", "status", "initiated_by",
            "initiated_at", "completed_at",
        }


async def test_transfer_list_facility_filter(client) -> None:
    """?facility_id= filters to transfers where the facility is source OR
    destination. A just-created transfer must surface under both endpoints."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    src = pharm["facility_id"]
    facs = await _facility_ids_by_code(client)
    dst = facs["MUL-NRH-001"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]

    create = await client.post(
        "/api/v1/supply/transfers",
        json={
            "from_facility_id": src,
            "to_facility_id": dst,
            "supply_item_id": item_id,
            "quantity": 25,
            "reason": "Filter test transfer",
        },
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    new_id = create.json()["id"]

    # Filter by the source facility — the new transfer must appear, and every
    # returned row must touch that facility.
    res = await client.get(
        "/api/v1/supply/transfers",
        params={"facility_id": src},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert any(r["id"] == new_id for r in rows)
    assert all(src in (r["from_facility_id"], r["to_facility_id"]) for r in rows)

    # Filter by the destination facility — the same transfer must appear there.
    res2 = await client.get(
        "/api/v1/supply/transfers",
        params={"facility_id": dst},
        headers=_auth(token),
    )
    assert res2.status_code == 200, res2.text
    assert any(r["id"] == new_id for r in res2.json())


async def test_transfer_list_validation_422(client) -> None:
    """since_days is bounded [1, 365]; out-of-range → 422."""
    await _seed(client)
    token = await _login(client, "nurse.gulu", "demo1234")
    res = await client.get(
        "/api/v1/supply/transfers",
        params={"since_days": 9999},
        headers=_auth(token),
    )
    assert res.status_code == 422, res.text


async def test_transfer_list_requires_auth(client) -> None:
    await _seed(client)
    res = await client.get("/api/v1/supply/transfers")
    assert res.status_code == 401, res.text


# ─────────────────────────────────────────────────────────────────────────────
# Dispense / stock-out — happy path, InsufficientStock → 4xx, authz, validation
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispense_happy_path_decrements_on_hand(client) -> None:
    """A pharmacist dispenses at their own facility; on-hand drops by qty and
    the response reports the events recorded."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    facility_id = pharm["facility_id"]

    def _on_hand(rows: list[dict]) -> int:
        for r in rows:
            if r["facility_id"] == facility_id and r["item_code"] == "ORS-001":
                return r["on_hand"]
        return 0

    before = _on_hand((await client.get(
        "/api/v1/supply/snapshot", params={"district": "Mbarara"}, headers=_auth(token)
    )).json())
    assert before > 0

    res = await client.post(
        "/api/v1/supply/dispense",
        params={
            "supply_item_id": (await _item_ids_by_code(client, token))["ORS-001"],
            "facility_id": facility_id,
            "quantity": 5,
            "purpose": "medication-dispense",
        },
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["dispensed_quantity"] == 5
    assert out["events_recorded"] >= 1

    after = _on_hand((await client.get(
        "/api/v1/supply/snapshot", params={"district": "Mbarara"}, headers=_auth(token)
    )).json())
    assert after == before - 5


async def test_dispense_insufficient_stock_is_422_not_500(client) -> None:
    """The headline contract: an over-draw surfaces InsufficientStockError as a
    clean 422 with a descriptive message, never an unhandled 500."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]

    res = await client.post(
        "/api/v1/supply/dispense",
        params={
            "supply_item_id": item_id,
            "facility_id": pharm["facility_id"],
            "quantity": 10_000_000,  # far exceeds stock → stock-out
        },
        headers=_auth(token),
    )
    assert res.status_code == 422, res.text
    detail = res.json()["detail"].lower()
    assert "not enough stock" in detail
    assert "short by" in detail


async def test_dispense_worker_forbidden(client) -> None:
    """A plain worker cannot dispense (needs pharmacist+) → 403."""
    await _seed(client)
    nurse_full = await _login_full(client, "nurse.gulu", "demo1234")
    token = nurse_full["access_token"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]
    res = await client.post(
        "/api/v1/supply/dispense",
        params={
            "supply_item_id": item_id,
            "facility_id": nurse_full["facility_id"],
            "quantity": 1,
        },
        headers=_auth(token),
    )
    assert res.status_code == 403, res.text


async def test_dispense_pharmacist_cross_facility_forbidden(client) -> None:
    """Facility scoping on dispense: Mbarara pharmacist dispensing at Gulu → 403."""
    await _seed(client)
    pharm = await _login(client, "pharmacist.mbarara", "demo1234")
    facs = await _facility_ids_by_code(client)
    item_id = (await _item_ids_by_code(client, pharm))["ORS-001"]
    res = await client.post(
        "/api/v1/supply/dispense",
        params={
            "supply_item_id": item_id,
            "facility_id": facs["GUL-RRH-002"],  # not the pharmacist's facility
            "quantity": 1,
        },
        headers=_auth(pharm),
    )
    assert res.status_code == 403, res.text
    assert "facility" in res.json()["detail"].lower()


async def test_dispense_unauthenticated_401(client) -> None:
    await _seed(client)
    res = await client.post(
        "/api/v1/supply/dispense",
        params={"supply_item_id": "x", "facility_id": "y", "quantity": 1},
    )
    assert res.status_code == 401, res.text


async def test_dispense_non_positive_quantity_422(client) -> None:
    """quantity has gt=0 at the query layer → 422 before the service runs."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]
    res = await client.post(
        "/api/v1/supply/dispense",
        params={
            "supply_item_id": item_id,
            "facility_id": pharm["facility_id"],
            "quantity": 0,
        },
        headers=_auth(token),
    )
    assert res.status_code == 422, res.text


async def test_dispense_missing_required_query_422(client) -> None:
    """Omitting a required query param (facility_id) → 422, not 500."""
    await _seed(client)
    pharm = await _login_full(client, "pharmacist.mbarara", "demo1234")
    token = pharm["access_token"]
    item_id = (await _item_ids_by_code(client, token))["ORS-001"]
    res = await client.post(
        "/api/v1/supply/dispense",
        params={"supply_item_id": item_id, "quantity": 1},
        headers=_auth(token),
    )
    assert res.status_code == 422, res.text


# ─────────────────────────────────────────────────────────────────────────────
# Ledger service unit tests (db_session) — hash chain, FEFO, insufficient,
# append-only. These complement test_supply_ledger.py's pure-hash tests.
# ─────────────────────────────────────────────────────────────────────────────

async def _make_item_and_facility(session) -> tuple[str, str]:
    """Persist one SupplyItem + one Facility, return their ids."""
    from app.db.models.facility import Facility
    from app.db.models.supply import SupplyItem

    item = SupplyItem(
        code="ACT-AL-001",
        name="Artemether/Lumefantrine",
        category="medicine",
        unit="tablet",
        reorder_threshold=500,
    )
    facility = Facility(
        code="GUL-RRH-002",
        name="Gulu Regional Referral Hospital",
        level="RRH",
        district="Gulu",
    )
    session.add_all([item, facility])
    await session.flush()
    return item.id, facility.id


async def _add_batch(
    session, *, item_id: str, facility_id: str, quantity: int, expires_in_days: int, lot: str
):
    from app.db.models.supply import StockBatch

    batch = StockBatch(
        supply_item_id=item_id,
        facility_id=facility_id,
        lot_number=lot,
        quantity=quantity,
        remaining=quantity,
        expires_on=date.today() + timedelta(days=expires_in_days),
        received_on=date.today(),
        cost_ugx=quantity * 100,
    )
    session.add(batch)
    await session.flush()
    return batch


async def test_ledger_receive_then_verify_chain(db_session) -> None:
    """receive_stock appends a 'received' event whose hash chain verifies."""
    from sqlalchemy import select

    from app.db.models.supply import StockEvent

    item_id, facility_id = await _make_item_and_facility(db_session)
    batch = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=400, expires_in_days=200, lot="LOT-1",
    )

    ev = await receive_stock(db_session, batch=batch, actor_id="actor-1")
    await db_session.flush()

    assert ev.event_type == "received"
    assert ev.quantity_delta == 400
    assert ev.prev_hash is None  # genesis for this facility
    assert len(ev.event_hash) == 64

    events = (
        await db_session.scalars(
            select(StockEvent).where(StockEvent.facility_id == facility_id)
        )
    ).all()
    assert len(events) == 1
    assert await verify_chain(db_session, facility_id) is True


async def test_ledger_chain_links_across_multiple_events(db_session) -> None:
    """Successive events on a facility chain prev_hash → predecessor's hash,
    and verify_chain walks them all to True."""
    item_id, facility_id = await _make_item_and_facility(db_session)
    batch = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=100, expires_in_days=200, lot="LOT-CHAIN",
    )

    e1 = await receive_stock(db_session, batch=batch, actor_id="actor-1")
    await db_session.flush()
    e2 = await append_event(
        db_session,
        batch_id=batch.id,
        supply_item_id=item_id,
        facility_id=facility_id,
        event_type="adjustment",
        quantity_delta=-5,
        actor_id="actor-1",
    )
    await db_session.flush()
    e3 = await append_event(
        db_session,
        batch_id=batch.id,
        supply_item_id=item_id,
        facility_id=facility_id,
        event_type="adjustment",
        quantity_delta=-3,
        actor_id="actor-1",
    )
    await db_session.flush()

    # Each event's prev_hash is its predecessor's event_hash.
    assert e1.prev_hash is None
    assert e2.prev_hash == e1.event_hash
    assert e3.prev_hash == e2.event_hash
    # Hashes are distinct (different payloads + linkage).
    assert len({e1.event_hash, e2.event_hash, e3.event_hash}) == 3
    assert await verify_chain(db_session, facility_id) is True


async def test_ledger_chain_is_per_facility(db_session) -> None:
    """Each facility has an independent chain — a second facility's first event
    is its own genesis, not linked to the first facility's head."""
    from app.db.models.facility import Facility

    item_id, fac_a = await _make_item_and_facility(db_session)
    fac_b_obj = Facility(
        code="MBR-RRH-003", name="Mbarara RRH", level="RRH", district="Mbarara"
    )
    db_session.add(fac_b_obj)
    await db_session.flush()
    fac_b = fac_b_obj.id

    batch_a = await _add_batch(
        db_session, item_id=item_id, facility_id=fac_a,
        quantity=100, expires_in_days=100, lot="LOT-A",
    )
    batch_b = await _add_batch(
        db_session, item_id=item_id, facility_id=fac_b,
        quantity=100, expires_in_days=100, lot="LOT-B",
    )
    ea = await receive_stock(db_session, batch=batch_a, actor_id="actor-a")
    await db_session.flush()
    eb = await receive_stock(db_session, batch=batch_b, actor_id="actor-b")
    await db_session.flush()

    assert ea.prev_hash is None
    assert eb.prev_hash is None  # independent genesis, not chained to fac_a
    assert await verify_chain(db_session, fac_a) is True
    assert await verify_chain(db_session, fac_b) is True


async def test_ledger_dispense_fefo_order_and_events(db_session) -> None:
    """dispense drains the earliest-expiry batch first (FEFO), splitting across
    batches as needed, and records one event per batch touched."""
    item_id, facility_id = await _make_item_and_facility(db_session)
    # Earlier-expiry batch (should drain first) has only 30 units.
    early = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=30, expires_in_days=30, lot="LOT-EARLY",
    )
    later = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=100, expires_in_days=300, lot="LOT-LATER",
    )
    await receive_stock(db_session, batch=early, actor_id="seed")
    await db_session.flush()
    await receive_stock(db_session, batch=later, actor_id="seed")
    await db_session.flush()

    # Dispense 50 → fully drains early (30), takes 20 from later.
    events = await dispense(
        db_session,
        supply_item_id=item_id,
        facility_id=facility_id,
        quantity=50,
        actor_id="pharm-1",
        encounter_id="enc-123",
    )
    await db_session.flush()

    assert len(events) == 2
    assert all(e.event_type == "dispensed" for e in events)
    assert all(e.reference_id == "enc-123" for e in events)
    assert early.remaining == 0
    assert later.remaining == 80
    # FEFO: the first event drained the earlier-expiry batch.
    assert events[0].batch_id == early.id
    assert events[0].quantity_delta == -30
    assert events[1].batch_id == later.id
    assert events[1].quantity_delta == -20

    assert await verify_chain(db_session, facility_id) is True


async def test_ledger_dispense_insufficient_raises_and_no_overdraw(db_session) -> None:
    """dispense raises InsufficientStockError when stock can't cover the
    request; the error message reports the shortfall."""
    item_id, facility_id = await _make_item_and_facility(db_session)
    batch = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=10, expires_in_days=90, lot="LOT-SHORT",
    )
    await receive_stock(db_session, batch=batch, actor_id="seed")
    await db_session.flush()

    with pytest.raises(InsufficientStockError) as ei:
        await dispense(
            db_session,
            supply_item_id=item_id,
            facility_id=facility_id,
            quantity=25,
            actor_id="pharm-1",
        )
    msg = str(ei.value).lower()
    assert "requested 25" in msg
    assert "short by 15" in msg  # 25 requested - 10 available


async def test_ledger_dispense_non_positive_quantity_raises_value_error(db_session) -> None:
    """The service rejects non-positive quantities with ValueError (the API
    layer's gt=0 guard normally prevents this from ever reaching here)."""
    item_id, facility_id = await _make_item_and_facility(db_session)
    with pytest.raises(ValueError, match="positive"):
        await dispense(
            db_session,
            supply_item_id=item_id,
            facility_id=facility_id,
            quantity=0,
            actor_id="pharm-1",
        )


async def test_ledger_is_append_only_under_dispense(db_session) -> None:
    """Append-only contract: dispensing never deletes or rewrites prior events
    — the receive event survives intact and the count only grows."""
    from sqlalchemy import select

    from app.db.models.supply import StockEvent

    item_id, facility_id = await _make_item_and_facility(db_session)
    batch = await _add_batch(
        db_session, item_id=item_id, facility_id=facility_id,
        quantity=100, expires_in_days=120, lot="LOT-APPEND",
    )
    recv = await receive_stock(db_session, batch=batch, actor_id="seed")
    await db_session.flush()
    recv_hash = recv.event_hash

    count_after_receive = len(
        (await db_session.scalars(
            select(StockEvent).where(StockEvent.facility_id == facility_id)
        )).all()
    )
    assert count_after_receive == 1

    await dispense(
        db_session,
        supply_item_id=item_id,
        facility_id=facility_id,
        quantity=40,
        actor_id="pharm-1",
    )
    await db_session.flush()

    rows = (await db_session.scalars(
        select(StockEvent)
        .where(StockEvent.facility_id == facility_id)
        .order_by(StockEvent.created_at.asc())
    )).all()
    # Count grew; the original receive event is unchanged (same hash, same
    # type, same delta) — nothing was rewritten or removed.
    assert len(rows) == count_after_receive + 1
    assert rows[0].event_type == "received"
    assert rows[0].event_hash == recv_hash
    assert rows[0].quantity_delta == 100
    assert rows[1].event_type == "dispensed"
    assert await verify_chain(db_session, facility_id) is True
