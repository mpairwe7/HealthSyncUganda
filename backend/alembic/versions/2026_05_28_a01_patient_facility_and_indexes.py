"""patient enrolling facility + composite indexes

Revision ID: a01_patient_facility
Revises: c07e02b0024b
Create Date: 2026-05-28

Phase 3 Revision A — additive schema changes only. Safe to deploy ahead of
code changes that read these columns; old code ignores them.

Adds:
- patients.enrolling_facility_id (FK → facilities.id, nullable, indexed)
- patients.enrolling_district (denormalised from facility.district, indexed)
- composite indexes for analytics + encounter listing
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a01_patient_facility"
down_revision: Union[str, Sequence[str], None] = "c07e02b0024b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- patients: enrolling_facility_id + enrolling_district ----------------
    op.add_column(
        "patients",
        sa.Column("enrolling_facility_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("enrolling_district", sa.String(length=80), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_patients_enrolling_facility_id_facilities"),
        "patients",
        "facilities",
        ["enrolling_facility_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_patients_enrolling_facility_id"),
        "patients",
        ["enrolling_facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_patients_enrolling_district"),
        "patients",
        ["enrolling_district"],
        unique=False,
    )

    # --- composite indexes for analytics + encounter listing ----------------
    op.create_index(
        "ix_stock_batches_facility_item_expires",
        "stock_batches",
        ["facility_id", "supply_item_id", "expires_on"],
        unique=False,
    )
    op.create_index(
        "ix_encounters_patient_started",
        "encounters",
        ["patient_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_observations_patient_code",
        "observations",
        ["patient_id", "code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_observations_patient_code", table_name="observations")
    op.drop_index("ix_encounters_patient_started", table_name="encounters")
    op.drop_index(
        "ix_stock_batches_facility_item_expires", table_name="stock_batches"
    )
    op.drop_index(
        op.f("ix_patients_enrolling_district"), table_name="patients"
    )
    op.drop_index(
        op.f("ix_patients_enrolling_facility_id"), table_name="patients"
    )
    op.drop_constraint(
        op.f("fk_patients_enrolling_facility_id_facilities"),
        "patients",
        type_="foreignkey",
    )
    op.drop_column("patients", "enrolling_district")
    op.drop_column("patients", "enrolling_facility_id")
