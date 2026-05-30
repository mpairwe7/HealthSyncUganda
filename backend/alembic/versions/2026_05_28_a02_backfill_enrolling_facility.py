"""backfill patients.enrolling_facility_id from earliest encounter

Revision ID: a02_backfill_enrolling
Revises: a01_patient_facility
Create Date: 2026-05-28

Phase 3 Revision B — data step. Restartable: only updates rows where
`enrolling_facility_id IS NULL`. Idempotent.

For each patient with at least one encounter, fills `enrolling_facility_id`
from the earliest encounter's facility, and `enrolling_district` from that
facility's district. Patients with no encounters are left NULL — they'll be
populated at their first clinical visit.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a02_backfill_enrolling"
down_revision: Union[str, Sequence[str], None] = "a01_patient_facility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Single statement with correlated subquery — selects each patient's
        # earliest encounter facility and its district.
        op.execute(
            """
            UPDATE patients p
            SET
                enrolling_facility_id = sub.facility_id,
                enrolling_district = f.district
            FROM (
                SELECT DISTINCT ON (e.patient_id)
                    e.patient_id, e.facility_id
                FROM encounters e
                ORDER BY e.patient_id, e.started_at ASC
            ) sub
            JOIN facilities f ON f.id = sub.facility_id
            WHERE p.id = sub.patient_id
              AND p.enrolling_facility_id IS NULL
            """
        )
    else:
        # SQLite / others — use a correlated subquery (slower but portable).
        op.execute(
            """
            UPDATE patients
            SET enrolling_facility_id = (
                SELECT e.facility_id FROM encounters e
                WHERE e.patient_id = patients.id
                ORDER BY e.started_at ASC
                LIMIT 1
            )
            WHERE enrolling_facility_id IS NULL
            """
        )
        op.execute(
            """
            UPDATE patients
            SET enrolling_district = (
                SELECT f.district FROM facilities f
                WHERE f.id = patients.enrolling_facility_id
            )
            WHERE enrolling_district IS NULL
              AND enrolling_facility_id IS NOT NULL
            """
        )


def downgrade() -> None:
    # Backfill is a data-only operation; clearing the columns on downgrade
    # would discard correct data. The previous migration's downgrade drops
    # the columns entirely, which is the right surface for rollback.
    pass
