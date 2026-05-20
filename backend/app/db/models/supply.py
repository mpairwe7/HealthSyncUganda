"""Supply chain ORM — items, batches, transfers, ledger events."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class SupplyItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "supply_items"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    unit: Mapped[str] = mapped_column(String(40))
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=0)
    requires_cold_chain: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    batches = relationship(
        "StockBatch", back_populates="supply_item", cascade="all, delete-orphan"
    )


class StockBatch(Base, IdMixin, TimestampMixin):
    __tablename__ = "stock_batches"

    supply_item_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("supply_items.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    lot_number: Mapped[str] = mapped_column(String(80), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    remaining: Mapped[int] = mapped_column(Integer)
    expires_on: Mapped[date] = mapped_column(Date, index=True)
    received_on: Mapped[date] = mapped_column(Date)
    cost_ugx: Mapped[int | None] = mapped_column(Integer)

    supply_item = relationship("SupplyItem", back_populates="batches")
    facility = relationship("Facility", back_populates="stock_batches")

    __table_args__ = (
        Index("ix_stock_batches_facility_item", "facility_id", "supply_item_id"),
    )


class StockEvent(Base, IdMixin, TimestampMixin):
    """Append-only ledger of stock changes — blockchain-ready abstraction.

    Every quantity change creates an immutable event. Computing on-hand is a
    pure folding operation over this ledger, which makes audits trivial and
    leaves a clean path to a notarised / Merkle-proof variant later.
    """

    __tablename__ = "stock_events"

    batch_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("stock_batches.id", ondelete="SET NULL"), index=True
    )
    supply_item_id: Mapped[str] = mapped_column(String(26), index=True)
    facility_id: Mapped[str] = mapped_column(String(26), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    quantity_delta: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reference_id: Mapped[str | None] = mapped_column(String(80))  # encounter/transfer id
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), index=True)
    extra: Mapped[dict] = mapped_column(default=dict)


class StockTransfer(Base, IdMixin, TimestampMixin):
    __tablename__ = "stock_transfers"

    from_facility_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("facilities.id", ondelete="RESTRICT")
    )
    to_facility_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("facilities.id", ondelete="RESTRICT")
    )
    supply_item_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("supply_items.id", ondelete="RESTRICT")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="in-progress")
    initiated_by: Mapped[str] = mapped_column(String(80))
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
