"""Supply-chain endpoints — items, batches, transfers, snapshots, alerts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_access
from app.core.logging import get_logger
from app.core.security import Principal, require_role
from app.db.models.facility import Facility
from app.db.models.supply import StockBatch, StockTransfer, SupplyItem
from app.db.session import get_db
from app.schemas.supply import (
    FacilityStockSnapshot,
    StockBatchIn,
    StockBatchOut,
    StockTransferCreate,
    StockTransferOut,
    SupplyItemCreate,
    SupplyItemOut,
)
from app.services.supply_ledger import (
    InsufficientStockError,
    append_event,
    receive_stock,
)

router = APIRouter(prefix="/supply", tags=["supply"])
logger = get_logger(__name__)


@router.get("/items", response_model=list[SupplyItemOut])
async def list_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("worker"))],
) -> list[SupplyItemOut]:
    rows = (await db.scalars(select(SupplyItem).order_by(SupplyItem.name))).all()
    out: list[SupplyItemOut] = []
    for it in rows:
        on_hand = (
            await db.scalar(
                select(func.coalesce(func.sum(StockBatch.remaining), 0)).where(
                    StockBatch.supply_item_id == it.id
                )
            )
        ) or 0
        facility_count = (
            await db.scalar(
                select(func.count(func.distinct(StockBatch.facility_id))).where(
                    StockBatch.supply_item_id == it.id, StockBatch.remaining > 0
                )
            )
        ) or 0
        out.append(
            SupplyItemOut(
                id=it.id,
                code=it.code,
                name=it.name,
                category=it.category,  # type: ignore[arg-type]
                unit=it.unit,
                reorder_threshold=it.reorder_threshold,
                requires_cold_chain=it.requires_cold_chain,
                on_hand_total=int(on_hand),
                facilities_stocked=int(facility_count),
            )
        )
    return out


@router.post(
    "/items",
    response_model=SupplyItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_item(
    body: SupplyItemCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("ministry_admin"))],
) -> SupplyItemOut:
    stmt = select(SupplyItem).where(SupplyItem.code == body.code)
    existing = (await db.scalars(stmt)).one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Item code already registered")
    it = SupplyItem(**body.model_dump())
    db.add(it)
    await db.flush()
    return SupplyItemOut(
        id=it.id,
        code=it.code,
        name=it.name,
        category=it.category,  # type: ignore[arg-type]
        unit=it.unit,
        reorder_threshold=it.reorder_threshold,
        requires_cold_chain=it.requires_cold_chain,
        on_hand_total=0,
        facilities_stocked=0,
    )


@router.post(
    "/batches",
    response_model=StockBatchOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a received stock batch",
)
async def receive_batch(
    body: StockBatchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("pharmacist"))],
) -> StockBatchOut:
    if not await db.get(SupplyItem, body.supply_item_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supply item not found")
    if not await db.get(Facility, body.facility_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Facility not found")
    if body.expires_on <= date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Batch already expired")

    batch = StockBatch(
        supply_item_id=body.supply_item_id,
        facility_id=body.facility_id,
        lot_number=body.lot_number,
        quantity=body.quantity,
        remaining=body.quantity,
        expires_on=body.expires_on,
        received_on=body.received_on,
        cost_ugx=body.cost_ugx,
    )
    db.add(batch)
    await db.flush()
    await receive_stock(db, batch=batch, actor_id=principal.subject)
    await record_access(
        db,
        principal=principal,
        resource_type="StockBatch",
        resource_id=batch.id,
        action="receive",
        purpose="stock-replenishment",
    )
    return StockBatchOut(
        **body.model_dump(),
        id=batch.id,
        remaining=batch.remaining,
        is_expired=False,
    )


@router.post(
    "/transfers",
    response_model=StockTransferOut,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a stock transfer between facilities",
)
async def initiate_transfer(
    body: StockTransferCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("pharmacist"))],
) -> StockTransferOut:
    if body.from_facility_id == body.to_facility_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Source and destination facilities must differ.",
        )

    # Drain source batches (FEFO)
    batches = (
        await db.scalars(
            select(StockBatch)
            .where(
                StockBatch.supply_item_id == body.supply_item_id,
                StockBatch.facility_id == body.from_facility_id,
                StockBatch.remaining > 0,
            )
            .order_by(StockBatch.expires_on.asc())
        )
    ).all()
    total_available = sum(b.remaining for b in batches)
    if total_available < body.quantity:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Source facility has only {total_available}; cannot transfer {body.quantity}.",
        )

    transfer = StockTransfer(
        from_facility_id=body.from_facility_id,
        to_facility_id=body.to_facility_id,
        supply_item_id=body.supply_item_id,
        quantity=body.quantity,
        reason=body.reason,
        status="in-progress",
        initiated_by=principal.subject,
        initiated_at=datetime.now(UTC),
    )
    db.add(transfer)
    await db.flush()

    # Atomic ledger updates: drain source, create destination batch.
    remaining_to_take = body.quantity
    for src in batches:
        if remaining_to_take == 0:
            break
        take = min(src.remaining, remaining_to_take)
        src.remaining -= take
        remaining_to_take -= take
        await append_event(
            db,
            batch_id=src.id,
            supply_item_id=body.supply_item_id,
            facility_id=body.from_facility_id,
            event_type="transferred_out",
            quantity_delta=-take,
            actor_id=principal.subject,
            reference_id=transfer.id,
        )
        dest = StockBatch(
            supply_item_id=body.supply_item_id,
            facility_id=body.to_facility_id,
            lot_number=src.lot_number,
            quantity=take,
            remaining=take,
            expires_on=src.expires_on,
            received_on=date.today(),
            cost_ugx=src.cost_ugx,
        )
        db.add(dest)
        await db.flush()
        await append_event(
            db,
            batch_id=dest.id,
            supply_item_id=body.supply_item_id,
            facility_id=body.to_facility_id,
            event_type="transferred_in",
            quantity_delta=take,
            actor_id=principal.subject,
            reference_id=transfer.id,
        )

    transfer.status = "completed"
    transfer.completed_at = datetime.now(UTC)

    await record_access(
        db,
        principal=principal,
        resource_type="StockTransfer",
        resource_id=transfer.id,
        action="execute",
        purpose=body.reason,
    )
    logger.info(
        "stock.transfer",
        transfer_id=transfer.id,
        from_=body.from_facility_id,
        to=body.to_facility_id,
        quantity=body.quantity,
    )
    return StockTransferOut(
        id=transfer.id,
        from_facility_id=transfer.from_facility_id,
        to_facility_id=transfer.to_facility_id,
        supply_item_id=transfer.supply_item_id,
        quantity=transfer.quantity,
        reason=transfer.reason,
        status=transfer.status,  # type: ignore[arg-type]
        initiated_by=transfer.initiated_by,
        initiated_at=transfer.initiated_at,
        completed_at=transfer.completed_at,
    )


@router.get(
    "/snapshot",
    response_model=list[FacilityStockSnapshot],
    summary="Current stock by facility (low-stock-aware)",
)
async def stock_snapshot(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Principal, Depends(require_role("worker"))],
    district: str | None = Query(None),
    only_below_threshold: bool = Query(False),
) -> list[FacilityStockSnapshot]:
    stmt = (
        select(
            Facility.id.label("facility_id"),
            Facility.name.label("facility_name"),
            SupplyItem.code.label("item_code"),
            SupplyItem.name.label("item_name"),
            func.coalesce(func.sum(StockBatch.remaining), 0).label("on_hand"),
            SupplyItem.reorder_threshold,
            func.min(StockBatch.expires_on).label("earliest_expiry"),
        )
        .join(StockBatch, StockBatch.facility_id == Facility.id)
        .join(SupplyItem, SupplyItem.id == StockBatch.supply_item_id)
        .group_by(Facility.id, SupplyItem.id)
    )
    if district:
        stmt = stmt.where(Facility.district == district)
    rows = (await db.execute(stmt)).all()

    snaps = [
        FacilityStockSnapshot(
            facility_id=r.facility_id,
            facility_name=r.facility_name,
            item_code=r.item_code,
            item_name=r.item_name,
            on_hand=int(r.on_hand),
            reorder_threshold=r.reorder_threshold,
            earliest_expiry=r.earliest_expiry,
            is_below_threshold=int(r.on_hand) < r.reorder_threshold,
        )
        for r in rows
    ]
    if only_below_threshold:
        snaps = [s for s in snaps if s.is_below_threshold]
    return snaps


@router.get("/alerts/low-stock", response_model=list[FacilityStockSnapshot])
async def low_stock_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
    district: str | None = Query(None),
) -> list[FacilityStockSnapshot]:
    return await stock_snapshot(db, principal, district, only_below_threshold=True)


@router.post("/dispense", response_model=dict)
async def dispense_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("pharmacist"))],
    supply_item_id: str = Query(...),
    facility_id: str = Query(...),
    quantity: int = Query(..., gt=0),
    encounter_id: str | None = Query(None),
) -> dict[str, str | int]:
    from app.services.supply_ledger import dispense as _dispense

    try:
        events = await _dispense(
            db,
            supply_item_id=supply_item_id,
            facility_id=facility_id,
            quantity=quantity,
            actor_id=principal.subject,
            encounter_id=encounter_id,
        )
    except InsufficientStockError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return {"dispensed_quantity": quantity, "events_recorded": len(events)}
