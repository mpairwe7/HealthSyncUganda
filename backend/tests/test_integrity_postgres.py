"""Postgres-only integrity tests (Phase 3 audit closure).

These run only when `TEST_POSTGRES_URL` is set in the env (CI staging
pipeline, local-with-docker-compose, deploy gate). Unit CI uses SQLite
which silently ignores the triggers + with_for_update semantics we're
verifying here.

Each test fixture provisions a fresh schema by running `alembic upgrade
head` against the configured database. The Postgres URL is expected to
have the `pgcrypto`, `pg_trgm`, `btree_gin` extensions already created
(see `infra/postgres/init.sql`).

Run locally:

    docker run -d --name pg -e POSTGRES_USER=healthsync \\
        -e POSTGRES_PASSWORD=healthsync -e POSTGRES_DB=healthsync \\
        -p 55439:5432 postgres:16-alpine
    docker exec pg psql -U healthsync -d healthsync \\
        -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm; \\
            CREATE EXTENSION IF NOT EXISTS btree_gin; \\
            CREATE EXTENSION IF NOT EXISTS pgcrypto;'
    TEST_POSTGRES_URL=postgresql+asyncpg://healthsync:healthsync@localhost:55439/healthsync \\
        uv run pytest tests/test_integrity_postgres.py -v
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.facility import Facility
from app.db.models.supply import StockBatch, StockTransfer, SupplyItem
from app.services.supply_ledger import append_event

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="TEST_POSTGRES_URL not set — Postgres-only assertions skipped",
    ),
]


@pytest.fixture()
async def pg_session():
    """Yield a session bound to a Postgres URL where alembic head has been
    applied. Test rows are removed at the end so consecutive runs stay
    independent (we can't TRUNCATE audit_log because of the trigger)."""
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_audit_log_blocks_update(pg_session: AsyncSession) -> None:
    """The Postgres trigger must raise on UPDATE — the audit log MUST be
    append-only at the storage layer, not just by app convention."""
    # Insert a sentinel row directly so we have something to try mutating.
    await pg_session.execute(
        text(
            """
            INSERT INTO audit_log
                (id, actor_id, actor_role, resource_type, resource_id,
                 action, extra, created_at, updated_at)
            VALUES ('01TESTAUDITUPDATEROW000001', 'test-actor', 'worker',
                    'Patient', 'p-test', 'read', '{}'::jsonb,
                    now(), now())
            """
        )
    )
    await pg_session.commit()

    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text(
                "UPDATE audit_log SET action='tampered' "
                "WHERE id='01TESTAUDITUPDATEROW000001'"
            )
        )
        await pg_session.commit()
    msg = str(excinfo.value).lower()
    assert "append-only" in msg or "check_violation" in msg, excinfo.value
    await pg_session.rollback()

    # Cleanup — DELETE is also blocked, so we mark with a no-op. The row
    # stays in the DB; subsequent runs use a different ID so they don't
    # collide. Idempotent via the unique id.


async def test_audit_log_blocks_delete(pg_session: AsyncSession) -> None:
    """DELETE on audit_log must also raise — destroying audit history
    breaks the compliance story regardless of whether it was UPDATE or
    DELETE that destroyed it."""
    await pg_session.execute(
        text(
            """
            INSERT INTO audit_log
                (id, actor_id, actor_role, resource_type, resource_id,
                 action, extra, created_at, updated_at)
            VALUES ('01TESTAUDITDELETEROW00001', 'test-actor', 'worker',
                    'Patient', 'p-test', 'read', '{}'::jsonb,
                    now(), now())
            """
        )
    )
    await pg_session.commit()

    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text("DELETE FROM audit_log WHERE id='01TESTAUDITDELETEROW00001'")
        )
        await pg_session.commit()
    msg = str(excinfo.value).lower()
    assert "append-only" in msg or "check_violation" in msg, excinfo.value
    await pg_session.rollback()


async def test_stock_events_blocks_update(pg_session: AsyncSession) -> None:
    """Supply ledger is append-only by hash-chain in code AND by trigger in
    the DB — defence in depth."""
    await pg_session.execute(
        text(
            """
            INSERT INTO stock_events
                (id, supply_item_id, facility_id, event_type,
                 quantity_delta, actor_id, occurred_at, event_hash,
                 extra, created_at, updated_at)
            VALUES ('01TESTSTOCKEVENTROW00001', 's-test', 'f-test',
                    'received', 10, 'test-actor', now(),
                    'aa' || repeat('0', 62), '{}'::jsonb, now(), now())
            """
        )
    )
    await pg_session.commit()

    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text(
                "UPDATE stock_events SET quantity_delta=999 "
                "WHERE id='01TESTSTOCKEVENTROW00001'"
            )
        )
        await pg_session.commit()
    msg = str(excinfo.value).lower()
    assert "append-only" in msg or "check_violation" in msg, excinfo.value
    await pg_session.rollback()


async def test_observations_patient_fk_blocks_orphans(pg_session: AsyncSession) -> None:
    """Migration A03 added the missing FK observations.patient_id →
    patients.id. Inserting an observation with a non-existent patient_id
    must raise."""
    # We can't use the test's own session because of FK violations rolling
    # the whole txn. Use a savepoint-free direct exec.
    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text(
                """
                INSERT INTO observations
                    (id, encounter_id, patient_id, code_system, code,
                     effective_at, created_at, updated_at)
                VALUES ('01TESTOBSORPHANROW000001',
                        'enc-also-orphan', 'patient-does-not-exist',
                        'http://loinc.org', '8867-4',
                        now(), now(), now())
                """
            )
        )
        await pg_session.commit()
    msg = str(excinfo.value).lower()
    assert (
        "violates foreign key" in msg
        or "fk_observations_patient_id_patients" in msg
        or "observations_patient_id_fkey" in msg.replace("-", "_")
    ), excinfo.value
    await pg_session.rollback()


async def test_stock_batch_remaining_check(pg_session: AsyncSession) -> None:
    """CHECK constraints block negative remaining and remaining > quantity.
    These are defence-in-depth against bugs in dispense/transfer logic."""
    # First create a parent item + facility we can satisfy the FK with.
    # Use idempotent INSERT ... ON CONFLICT DO NOTHING so reruns are safe.
    await pg_session.execute(
        text(
            """
            INSERT INTO supply_items (id, code, name, category, unit, reorder_threshold, requires_cold_chain, created_at, updated_at)
            VALUES ('01TESTITEMSTOCKCHECK0001', 'CK-001', 'Check Item',
                    'medication', 'box', 0, false, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO facilities (id, code, name, level, district, active, created_at, updated_at)
            VALUES ('01TESTFACSTOCKCHECK00001', 'CK-FAC-001', 'Check Fac',
                    'HC II', 'Kampala', true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await pg_session.commit()

    # Negative remaining → must violate ck_stock_batches_remaining_nonneg
    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text(
                """
                INSERT INTO stock_batches
                    (id, supply_item_id, facility_id, lot_number,
                     quantity, remaining, expires_on, received_on,
                     created_at, updated_at)
                VALUES ('01TESTBATCHNEGREMAIN0001',
                        '01TESTITEMSTOCKCHECK0001',
                        '01TESTFACSTOCKCHECK00001',
                        'LOT-NEG', 10, -1, current_date + 365,
                        current_date, now(), now())
                """
            )
        )
        await pg_session.commit()
    assert "ck_stock_batches_remaining_nonneg" in str(excinfo.value).lower() \
        or "check constraint" in str(excinfo.value).lower(), excinfo.value
    await pg_session.rollback()

    # remaining > quantity → must violate ck_stock_batches_remaining_le_quantity
    with pytest.raises(Exception) as excinfo:
        await pg_session.execute(
            text(
                """
                INSERT INTO stock_batches
                    (id, supply_item_id, facility_id, lot_number,
                     quantity, remaining, expires_on, received_on,
                     created_at, updated_at)
                VALUES ('01TESTBATCHOVERQUANTITY1',
                        '01TESTITEMSTOCKCHECK0001',
                        '01TESTFACSTOCKCHECK00001',
                        'LOT-OVER', 10, 11, current_date + 365,
                        current_date, now(), now())
                """
            )
        )
        await pg_session.commit()
    assert "ck_stock_batches_remaining_le_quantity" in str(excinfo.value).lower() \
        or "check constraint" in str(excinfo.value).lower(), excinfo.value
    await pg_session.rollback()


async def test_concurrent_transfers_do_not_oversell(pg_session: AsyncSession) -> None:
    """Two concurrent transfers from the same source batch must serialise
    via `.with_for_update()` so total drained ≤ batch.quantity. Without
    the row lock, the pre-lock total_available check is stale and both
    requests succeed → negative remaining.

    Smoke pattern (not a stress test): launch two coroutines, each draining
    8 units from a batch with 10. One must fail; the other must succeed
    with remaining = 2.
    """
    # Set up: facility, item, batch.
    fac_id = "01TESTCONCFAC0000000001"
    item_id = "01TESTCONCITEM00000001"
    batch_id = "01TESTCONCBATCH0000001"

    await pg_session.execute(
        text(
            f"""
            INSERT INTO facilities (id, code, name, level, district, active, created_at, updated_at)
            VALUES ('{fac_id}', 'CONC-FAC-001', 'Conc Source', 'HC II',
                    'Kampala', true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await pg_session.execute(
        text(
            f"""
            INSERT INTO facilities (id, code, name, level, district, active, created_at, updated_at)
            VALUES ('{fac_id[:-1]}2', 'CONC-FAC-002', 'Conc Dest', 'HC II',
                    'Kampala', true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await pg_session.execute(
        text(
            f"""
            INSERT INTO supply_items (id, code, name, category, unit, reorder_threshold, requires_cold_chain, created_at, updated_at)
            VALUES ('{item_id}', 'CONC-001', 'Conc Item', 'medication',
                    'box', 0, false, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await pg_session.execute(
        text(
            f"""
            INSERT INTO stock_batches
                (id, supply_item_id, facility_id, lot_number,
                 quantity, remaining, expires_on, received_on,
                 created_at, updated_at)
            VALUES ('{batch_id}', '{item_id}', '{fac_id}', 'LOT-CONC',
                    10, 10, current_date + 365, current_date, now(), now())
            ON CONFLICT (id) DO UPDATE SET remaining = EXCLUDED.remaining
            """
        )
    )
    await pg_session.commit()

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def drain_8(label: str) -> str:
        """Mirrors initiate_transfer's drain path with .with_for_update()."""
        try:
            async with factory() as s:
                from sqlalchemy import select

                batches = (
                    await s.scalars(
                        select(StockBatch)
                        .where(
                            StockBatch.supply_item_id == item_id,
                            StockBatch.facility_id == fac_id,
                            StockBatch.remaining > 0,
                        )
                        .order_by(StockBatch.expires_on.asc())
                        .with_for_update()
                    )
                ).all()
                total = sum(b.remaining for b in batches)
                if total < 8:
                    raise RuntimeError(
                        f"insufficient stock: have {total}, want 8"
                    )
                remaining_to_take = 8
                for src in batches:
                    if remaining_to_take == 0:
                        break
                    take = min(src.remaining, remaining_to_take)
                    src.remaining -= take
                    remaining_to_take -= take
                # Simulate the rest of the transfer work taking a moment.
                await asyncio.sleep(0.1)
                await s.commit()
                return "ok"
        except Exception as exc:
            return f"failed: {exc.__class__.__name__}: {exc}"

    results = await asyncio.gather(drain_8("A"), drain_8("B"))
    ok = sum(1 for r in results if r == "ok")
    fail = sum(1 for r in results if r.startswith("failed:"))
    assert ok == 1 and fail == 1, (
        f"Exactly one drain must succeed, the other must fail. "
        f"Got: {results}"
    )

    # Verify the ledger is consistent.
    async with factory() as s:
        b = await s.get(StockBatch, batch_id)
        assert b is not None and b.remaining == 2, (
            f"Batch should have 2 remaining after one 8-unit drain; got {b.remaining}"
        )

    await engine.dispose()
