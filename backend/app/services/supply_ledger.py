"""Stock ledger — append-only event log with hash chaining.

Every quantity change is recorded as a `StockEvent`. The hash of each event
includes the hash of its predecessor, making the chain tamper-evident. A
future deployment can notarise the chain head to a public ledger (Hyperledger
Iroha, Stellar, or a Merkle anchor) without altering the application logic.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.supply import StockBatch, StockEvent

logger = get_logger(__name__)

if TYPE_CHECKING:
    pass


def _hash_event(prev_hash: str | None, payload: dict[str, object]) -> str:
    base = (prev_hash or "GENESIS") + "|" + "|".join(f"{k}={payload[k]}" for k in sorted(payload))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


async def _latest_hash(session: AsyncSession, facility_id: str) -> str | None:
    row = await session.scalar(
        select(StockEvent.event_hash)
        .where(StockEvent.facility_id == facility_id)
        .order_by(desc(StockEvent.created_at))
        .limit(1)
    )
    return row


async def append_event(
    session: AsyncSession,
    *,
    batch_id: str | None,
    supply_item_id: str,
    facility_id: str,
    event_type: str,
    quantity_delta: int,
    actor_id: str,
    reference_id: str | None = None,
    extra: dict | None = None,
) -> StockEvent:
    """Append a single event to the ledger. Caller commits."""
    prev = await _latest_hash(session, facility_id)
    occurred_at = datetime.now(UTC)
    payload = {
        "batch_id": batch_id or "",
        "supply_item_id": supply_item_id,
        "facility_id": facility_id,
        "event_type": event_type,
        "quantity_delta": quantity_delta,
        "actor_id": actor_id,
        "reference_id": reference_id or "",
        "occurred_at": occurred_at.isoformat(),
    }
    event_hash = _hash_event(prev, payload)
    event = StockEvent(
        batch_id=batch_id,
        supply_item_id=supply_item_id,
        facility_id=facility_id,
        event_type=event_type,
        quantity_delta=quantity_delta,
        actor_id=actor_id,
        reference_id=reference_id,
        occurred_at=occurred_at,
        prev_hash=prev,
        event_hash=event_hash,
        extra=extra or {},
    )
    session.add(event)
    return event


async def receive_stock(
    session: AsyncSession,
    *,
    batch: StockBatch,
    actor_id: str,
) -> StockEvent:
    return await append_event(
        session,
        batch_id=batch.id,
        supply_item_id=batch.supply_item_id,
        facility_id=batch.facility_id,
        event_type="received",
        quantity_delta=batch.quantity,
        actor_id=actor_id,
        reference_id=batch.lot_number,
    )


async def dispense(
    session: AsyncSession,
    *,
    supply_item_id: str,
    facility_id: str,
    quantity: int,
    actor_id: str,
    encounter_id: str | None = None,
) -> list[StockEvent]:
    """Dispense from oldest-expiry batch first (FEFO). Raises if insufficient."""
    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    batches = (
        await session.scalars(
            select(StockBatch)
            .where(
                StockBatch.supply_item_id == supply_item_id,
                StockBatch.facility_id == facility_id,
                StockBatch.remaining > 0,
            )
            .order_by(StockBatch.expires_on.asc())
            .with_for_update()
        )
    ).all()

    remaining_to_take = quantity
    events: list[StockEvent] = []
    for batch in batches:
        if remaining_to_take == 0:
            break
        take = min(batch.remaining, remaining_to_take)
        batch.remaining -= take
        remaining_to_take -= take
        events.append(
            await append_event(
                session,
                batch_id=batch.id,
                supply_item_id=supply_item_id,
                facility_id=facility_id,
                event_type="dispensed",
                quantity_delta=-take,
                actor_id=actor_id,
                reference_id=encounter_id,
            )
        )

    if remaining_to_take > 0:
        raise InsufficientStock(
            f"Not enough stock at facility: requested {quantity}, "
            f"short by {remaining_to_take}."
        )
    return events


class InsufficientStock(Exception):
    """Raised when a dispense or transfer cannot be satisfied."""


async def verify_chain(session: AsyncSession, facility_id: str) -> bool:
    """Walk the ledger for a facility and verify each hash links correctly."""
    rows = (
        await session.scalars(
            select(StockEvent)
            .where(StockEvent.facility_id == facility_id)
            .order_by(StockEvent.created_at.asc())
        )
    ).all()
    prev: str | None = None
    for ev in rows:
        if ev.prev_hash != prev:
            logger.error(
                "ledger.chain_broken",
                facility=facility_id,
                event=ev.id,
                expected=prev,
                actual=ev.prev_hash,
            )
            return False
        prev = ev.event_hash
    return True
