"""integrity constraints, missing FK, append-only triggers

Revision ID: a03_integrity
Revises: a02_backfill_enrolling
Create Date: 2026-05-28

Phase 3 Revision C — the risky migration. Adds CHECK constraints, the
missing observations.patient_id FK, and Postgres-only append-only triggers
on audit_log + stock_events.

If this fails on existing data (orphan observations, garbage enum values),
isolate the failure to this revision so additive work in A/B stays
applied.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a03_integrity"
down_revision: Union[str, Sequence[str], None] = "a02_backfill_enrolling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Centralised so app/db/models/* and these migrations agree.
GENDER_VALUES = ("male", "female", "other", "unknown")
ROLE_VALUES = (
    "citizen",
    "worker",
    "pharmacist",
    "district_admin",
    "ministry_admin",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- CHECK constraints ---------------------------------------------------
    op.create_check_constraint(
        "ck_patients_gender",
        "patients",
        f"gender IN ({', '.join(repr(v) for v in GENDER_VALUES)})",
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        f"role IN ({', '.join(repr(v) for v in ROLE_VALUES)})",
    )
    op.create_check_constraint(
        "ck_stock_batches_remaining_nonneg",
        "stock_batches",
        "remaining >= 0",
    )
    op.create_check_constraint(
        "ck_stock_batches_remaining_le_quantity",
        "stock_batches",
        "remaining <= quantity",
    )
    op.create_check_constraint(
        "ck_caregiver_links_no_self",
        "caregiver_links",
        "caregiver_id != child_id",
    )

    # --- observations.patient_id FK -----------------------------------------
    # Clean orphans first so the constraint applies cleanly. Defensive — if
    # the app has been writing correctly there will be zero rows to delete.
    op.execute(
        """
        DELETE FROM observations
        WHERE patient_id NOT IN (SELECT id FROM patients)
        """
    )
    op.create_foreign_key(
        op.f("fk_observations_patient_id_patients"),
        "observations",
        "patients",
        ["patient_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- Postgres append-only triggers (skipped on SQLite tests) ------------
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION healthsync_block_mutate()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION
                    'Table % is append-only; UPDATE/DELETE forbidden.',
                    TG_TABLE_NAME
                    USING ERRCODE = 'check_violation';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_log_append_only
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION healthsync_block_mutate();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_stock_events_append_only
            BEFORE UPDATE OR DELETE ON stock_events
            FOR EACH ROW EXECUTE FUNCTION healthsync_block_mutate();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_stock_events_append_only ON stock_events")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS healthsync_block_mutate()")

    op.drop_constraint(
        op.f("fk_observations_patient_id_patients"),
        "observations",
        type_="foreignkey",
    )
    op.drop_constraint("ck_caregiver_links_no_self", "caregiver_links", type_="check")
    op.drop_constraint(
        "ck_stock_batches_remaining_le_quantity", "stock_batches", type_="check"
    )
    op.drop_constraint(
        "ck_stock_batches_remaining_nonneg", "stock_batches", type_="check"
    )
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint("ck_patients_gender", "patients", type_="check")
