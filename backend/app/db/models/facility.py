"""Healthcare facility. Uganda hierarchy: HC II, HC III, HC IV, HC, GH, RRH, NRH."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Facility(Base, IdMixin, TimestampMixin):
    __tablename__ = "facilities"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    level: Mapped[str] = mapped_column(String(40), index=True)  # HC II/III/IV/HC/GH/RRH/NRH
    district: Mapped[str] = mapped_column(String(80), index=True)
    sub_county: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    users = relationship("User", back_populates="facility")
    encounters = relationship("Encounter", back_populates="facility")
    stock_batches = relationship("StockBatch", back_populates="facility")
