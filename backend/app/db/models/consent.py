"""Consent record — explicit, granular, revocable."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Consent(Base, IdMixin, TimestampMixin):
    __tablename__ = "consents"

    patient_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(80), index=True)
    purpose: Mapped[str] = mapped_column(String(300))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_by: Mapped[str] = mapped_column(String(80))  # who recorded the consent

    patient = relationship("Patient", back_populates="consents")
