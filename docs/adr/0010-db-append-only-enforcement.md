# ADR 0010: Database-layer append-only enforcement

- **Status:** Proposed
- **Date:** 2026-05-25
- **Closes residual risks:** [RR-01](../THREAT_MODEL.md#6-residual-risk-register) (DB UPDATE bypasses audit), [RR-03](../THREAT_MODEL.md#6-residual-risk-register) (`audit_log` append-only app-only), [RR-05](../THREAT_MODEL.md#6-residual-risk-register) (migration can rewrite `stock_events`).
- **Deciders:** Architecture Review Board + DPO

## Context

`audit_log` and `stock_events` are **append-only by application convention** today. The application's `record_access` only INSERTs. The hash-chain verifier in `app/services/supply_ledger.py` detects breakage post-hoc.

This is correct as the *primary* line of defence (application convention is checked at every code review), but it leaves three residual risks open: a direct DBA `UPDATE`, a careless Alembic migration, and a compromised application account with `UPDATE` permission. Each of these has a different remediation; all three converge on the same need: **enforce the invariant at the database layer**.

[SECURITY.md](../SECURITY.md) has noted a planned Postgres `RULE` since the prototype was written. This ADR turns that note into a specific migration with a least-privilege DB role.

## Decision

Three layered controls, all delivered in a single migration:

### Layer 1 — INSERT-only triggers

Per-table `BEFORE UPDATE` and `BEFORE DELETE` triggers on `audit_log` and `stock_events` that raise an exception. Triggers are owned by the `postgres` superuser and cannot be dropped by the application role.

```sql
-- backend/alembic/versions/0010_db_append_only.sql

CREATE OR REPLACE FUNCTION raise_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Table % is append-only; % is prohibited',
    TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
  BEFORE UPDATE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION raise_append_only();
CREATE TRIGGER audit_log_no_delete
  BEFORE DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION raise_append_only();

CREATE TRIGGER stock_events_no_update
  BEFORE UPDATE ON stock_events
  FOR EACH ROW EXECUTE FUNCTION raise_append_only();
CREATE TRIGGER stock_events_no_delete
  BEFORE DELETE ON stock_events
  FOR EACH ROW EXECUTE FUNCTION raise_append_only();
```

### Layer 2 — Least-privilege application role

Provision two database roles:

| Role               | Grants                                                                                                              | Used by                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `healthsync_app`   | `SELECT, INSERT, UPDATE, DELETE` on most tables; **`SELECT, INSERT` only** on `audit_log` and `stock_events`         | The FastAPI application (every request).      |
| `healthsync_admin` | All privileges including migrations; UPDATE/DELETE on append-only tables (forensic operations + recovery only).      | Alembic migrations; explicit forensic action with two-person sign-off. |

```sql
-- backend/alembic/versions/0010_db_append_only.sql (continued)

REVOKE UPDATE, DELETE ON audit_log    FROM healthsync_app;
REVOKE UPDATE, DELETE ON stock_events FROM healthsync_app;
-- INSERT and SELECT remain granted.
```

The deployment runs the application as `healthsync_app`; migrations and any forensic operation run as `healthsync_admin` and require a separate, audit-logged credential.

### Layer 3 — Alembic migration discipline

The Alembic migration that touches `audit_log` or `stock_events` runs as `healthsync_admin` (because Layer 1 triggers fire even for the application user). Migrations that touch append-only tables additionally require:

1. Manual review by a maintainer + DPO sign-off in the PR.
2. A **chain-verify** step in the migration itself: after the migration body, run `supply_ledger.verify()` and abort the migration if the chain breaks. This makes a chain-breaking migration *impossible to apply* — it rolls back on its own check.

```python
# Alembic migration helper (illustrative)

def upgrade() -> None:
    # ... migration body ...
    op.execute("SELECT 1")  # placeholder for the actual operation

    # Post-migration invariant check
    conn = op.get_bind()
    result = conn.exec_driver_sql(
        "SELECT count(*) AS broken FROM supply_chain_verify()"
    ).scalar()
    if result and result > 0:
        raise Exception("Migration broke the supply hash chain — rolling back")
```

`supply_chain_verify()` is a stored procedure introduced by the same migration that recomputes the chain.

## Rationale

- **Defence in depth.** A DBA who connects directly with the `healthsync_app` credentials cannot mutate the append-only tables (no grant). A DBA who connects with `healthsync_admin` triggers Layer 1 and is reminded by the exception that this is a privileged operation. A DBA who disables the triggers (only possible as superuser) leaves a clear audit trail in the Postgres log.
- **Trigger-based vs. RULE-based.** Triggers are the modern Postgres idiom for this; `RULE` is older, less predictable in combination with multi-row UPDATEs. The SECURITY.md note that mentioned `RULE` is updated to "trigger" by this ADR.
- **Chain-verify in the migration itself** turns a *historical* invariant check into a *gate*. The migration cannot be applied if it broke the chain.

## Alternatives considered

- **Logical-replication-only `audit_log`** (stream every insert to a read-only replica that is the canonical store). Overkill for the pilot; reconsidered post-national.
- **External-blockchain anchor of chain head.** Mentioned in [SECURITY.md "What is *not* in this prototype"](../SECURITY.md). Orthogonal; this ADR makes that future addition easier (the chain head becomes provably append-only at the source).
- **Drop application UPDATE/DELETE entirely, even on plaintext tables.** Too restrictive; we legitimately UPDATE `patients.record_version` and `stock_batches.remaining`.

## Consequences

**Positive.**
- Three residual risks closed by a single migration.
- Application-bug fault-tolerance: if a future PR accidentally calls `UPDATE audit_log SET ...`, the database rejects the statement instead of silently corrupting the trail.
- Migration safety: chain-verify-in-migration prevents a class of operator error.

**Negative.**
- An emergency "fix the audit log" or "fix the supply ledger" requires `healthsync_admin` credentials and explicit two-person sign-off. **This is the desired behaviour** for these tables, but it must be documented in [RUNBOOK.md RB-07](../RUNBOOK.md#rb-07--supply-ledger-verification-failed) and [INCIDENT_RESPONSE.md IR-21](../INCIDENT_RESPONSE.md#ir-21--supply-ledger-broken) — adding "use `healthsync_admin` only; expect Layer 1 to fire if you UPDATE".
- The CI test suite needs a tiny addition: a test that `UPDATE audit_log` raises (asserts the trigger is in place).

## Implementation sketch

```sql
-- infra/postgres/init.sql — append at end (idempotent CREATE OR REPLACE)

CREATE ROLE healthsync_app   LOGIN PASSWORD :app_password;
CREATE ROLE healthsync_admin LOGIN PASSWORD :admin_password;

GRANT CONNECT ON DATABASE healthsync TO healthsync_app, healthsync_admin;
GRANT USAGE   ON SCHEMA public        TO healthsync_app, healthsync_admin;

-- Default privileges for the application
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public
  TO healthsync_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO healthsync_app;

-- Reserved append-only constraint applied after table creation in Alembic 0010.
```

```python
# backend/tests/test_append_only.py — sketch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

@pytest.mark.asyncio
async def test_audit_log_update_rejected(db_session):
    await db_session.execute(
        text("INSERT INTO audit_log (id, actor_id, actor_role, resource_type, "
             "resource_id, action, created_at, updated_at) "
             "VALUES ('01', 'u', 'worker', 'P', 'p', 'read', now(), now())")
    )
    await db_session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(
            text("UPDATE audit_log SET action='changed' WHERE id='01'")
        )

@pytest.mark.asyncio
async def test_stock_events_delete_rejected(db_session):
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(text("DELETE FROM stock_events"))
```

## Migration

1. Add `0010_db_append_only.sql` Alembic migration (creates triggers + revokes UPDATE/DELETE from `healthsync_app`).
2. Update `infra/postgres/init.sql` to provision the two roles.
3. Update deployment overlays to use `healthsync_app` as the runtime user; reserve `healthsync_admin` for migrations.
4. Add the `test_append_only.py` tests.
5. Update [SECURITY.md "Audit log is append-only by application convention"](../SECURITY.md) → "by application convention **and** database trigger".
6. Update [DATA_MODEL.md §3.8 stock_events](../DATA_MODEL.md#38-stock_events--append-only-hash-chain-ledger) and §3.11 audit_log notes.
7. Update [THREAT_MODEL.md §6](../THREAT_MODEL.md#6-residual-risk-register) — move RR-01, RR-03, RR-05 to "closed pre-pilot, ADR 0010".

## Rollout

- **Phase 1 (dev).** Apply migration; run the new tests; observe.
- **Phase 2 (staging).** Apply migration; perform a deliberate `UPDATE audit_log` attempt; confirm rejection.
- **Phase 3 (pilot production).** Apply during the pre-pilot maintenance window. No application code change required (we never UPDATE these tables; if we ever did, we already broke the application convention).
- **Phase 4 (continuous).** Every future migration touching these tables requires DPO sign-off in the PR.

## References

- [SECURITY.md §"Audit & accountability"](../SECURITY.md).
- [DATA_MODEL.md §3.8 stock_events](../DATA_MODEL.md#38-stock_events--append-only-hash-chain-ledger), §3.11 audit_log.
- [THREAT_MODEL.md §6 RR-01, RR-03, RR-05](../THREAT_MODEL.md#6-residual-risk-register).
- [RUNBOOK.md RB-07](../RUNBOOK.md#rb-07--supply-ledger-verification-failed); [RB-12](../RUNBOOK.md#rb-12--schema-migration-to-apply).
- [ADR 0004 — supply hash-chain ledger](./0004-supply-hash-chain-ledger.md) (this ADR strengthens its enforcement).
