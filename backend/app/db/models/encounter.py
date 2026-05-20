"""Encounter + Observation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, JSONBOrJSON, TimestampMixin


class Encounter(Base, IdMixin, TimestampMixin):
    __tablename__ = "encounters"

    patient_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    reason: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(20), default="in-progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnosis_codes: Mapped[list] = mapped_column(JSONBOrJSON, default=list)
    recorded_by: Mapped[str | None] = mapped_column(String(80))

    patient = relationship("Patient", back_populates="encounters")
    facility = relationship("Facility", back_populates="encounters")
    observations = relationship(
        "Observation",
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="Observation.effective_at",
    )


class Observation(Base, IdMixin, TimestampMixin):
    __tablename__ = "observations"

    encounter_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("encounters.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[str] = mapped_column(String(26), index=True)
    code_system: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(80), index=True)
    display: Mapped[str | None] = mapped_column(String(200))
    value_quantity: Mapped[float | None] = mapped_column(Float)
    value_unit: Mapped[str | None] = mapped_column(String(40))
    value_string: Mapped[str | None] = mapped_column(String(400))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_by: Mapped[str | None] = mapped_column(String(80))

    encounter = relationship("Encounter", back_populates="observations")
