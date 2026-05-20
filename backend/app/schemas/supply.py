"""Supply-chain DTOs — items, batches, transfers, ledger events."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SupplyCategory = Literal["medicine", "vaccine", "consumable", "equipment", "reagent"]
StockEventType = Literal[
    "received", "dispensed", "transferred_out", "transferred_in", "expired", "adjustment"
]


class SupplyItemBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(..., description="Uganda EMHSLU code (e.g. ACT-AL-001).")
    name: str = Field(..., min_length=2, max_length=120)
    category: SupplyCategory
    unit: str = Field(..., description="dose, tablet, vial, sachet, ml, kit…")
    reorder_threshold: int = Field(..., ge=0)
    requires_cold_chain: bool = False


class SupplyItemCreate(SupplyItemBase):
    pass


class SupplyItemOut(SupplyItemBase):
    id: str
    on_hand_total: int = Field(..., ge=0)
    facilities_stocked: int = Field(..., ge=0)


class StockBatchIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    supply_item_id: str
    facility_id: str
    lot_number: str = Field(..., min_length=1, max_length=80)
    quantity: int = Field(..., gt=0)
    expires_on: date
    received_on: date
    cost_ugx: int | None = Field(default=None, ge=0)


class StockBatchOut(StockBatchIn):
    id: str
    remaining: int
    is_expired: bool


class StockTransferCreate(BaseModel):
    from_facility_id: str
    to_facility_id: str
    supply_item_id: str
    quantity: int = Field(..., gt=0)
    reason: str = Field(..., min_length=2, max_length=200)


class StockTransferOut(StockTransferCreate):
    id: str
    status: Literal["in-progress", "completed", "abandoned"]
    initiated_by: str
    initiated_at: datetime
    completed_at: datetime | None


class FacilityStockSnapshot(BaseModel):
    facility_id: str
    facility_name: str
    item_code: str
    item_name: str
    on_hand: int
    reorder_threshold: int
    earliest_expiry: date | None
    is_below_threshold: bool
