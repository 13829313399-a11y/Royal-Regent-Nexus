"""Shared business-time boundaries for carton quantity and cost projections."""
import json
from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import parse_business_timestamp
from app.models.carton_procurement import CartonInventoryMovement, CartonAuditEvent


def ledger_time(value):
    # Existing callers use YYYY-MM-DDT for an exclusive midnight boundary.
    parsed = parse_business_timestamp(str(value).removesuffix("T"))
    if parsed is None:
        raise HTTPException(409, "库存流水存在无效时间，请先核对历史记录")
    return parsed


def ledger_rows(db, factory, *, before=None, customer=None):
    query = select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)
    if customer is not None:
        query = query.where(CartonInventoryMovement.customer_code == customer)
    cutoff = ledger_time(before) if before else None
    rows = list(db.scalars(query))
    # Raw SQL string comparison cannot order equivalent Z/local/offset instants.
    return [row for row in rows if cutoff is None or ledger_time(row.occurred_at) < cutoff]


def ordered_ledger_rows(db, factory):
    sequence = {}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory)):
        detail = json.loads(event.detail_json or "{}")
        if event.event_type in {"INVENTORY_MOVEMENT_CREATED", "RECEIPT_CONFIRMED"}:
            sequence[event.entity_id] = event.sequence
        elif event.event_type == "INVENTORY_MOVEMENT_REVERSED":
            sequence[detail.get("reversal_id", "")] = event.sequence
        elif event.event_type in {"ORDER_RETURNED", "INVENTORY_BULK_OUTBOUND_CREATED"}:
            for identifier in detail.get("movement_ids", []):
                sequence[identifier] = event.sequence
    return sorted(ledger_rows(db, factory), key=lambda row: (
        ledger_time(row.occurred_at), sequence.get(row.id, sequence.get(row.source_id, 0)), row.quantity < 0, row.id))
