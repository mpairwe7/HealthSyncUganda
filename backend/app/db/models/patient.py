"""Patient record — canonical, NIN-linked."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Patient(Base, IdMixin, TimestampMixin):
    __tablename__ = "patients"

    nin: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    given_name: Mapped[str] = mapped_column(String(80))
    family_name: Mapped[str] = mapped_column(String(80))
    gender: Mapped[str] = mapped_column(String(10))
    birth_date: Mapped[date] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    # `district` is residence — survey + outreach planning use this.
    district: Mapped[str] = mapped_column(String(80), index=True)
    sub_county: Mapped[str | None] = mapped_column(String(80))
    parish: Mapped[str | None] = mapped_column(String(80))
    village: Mapped[str | None] = mapped_column(String(80))
    # `enrolling_facility_id` is the *clinical* home — drives worker RBAC scope.
    # Nullable: citizens who self-register via the citizen portal aren't bound
    # to any facility until their first encounter.
    enrolling_facility_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("facilities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Denormalised from facility.district so district_admin scoping doesn't
    # always have to join Facility. Kept in sync at create-time + via backfill.
    enrolling_district: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    deceased: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    record_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    encounters = relationship(
        "Encounter", back_populates="patient", cascade="all, delete-orphan"
    )
    consents = relationship(
        "Consent", back_populates="patient", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Trigram index on family_name for fast fuzzy search on Postgres
        Index("ix_patients_family_name_trgm", "family_name",
              postgresql_using="gin", postgresql_ops={"family_name": "gin_trgm_ops"}),
    )
