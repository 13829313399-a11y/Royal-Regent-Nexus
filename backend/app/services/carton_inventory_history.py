"""Filter the complete carton ledger before paging its read-only history."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonCustomer
from app.schemas.carton_inventory_history import (
    CartonInventoryHistoryListOut,
    CartonInventoryHistoryMovementOut,
)
from app.services.carton_inventory_money import annotate_movements
from app.services.carton_ledger_time import ledger_time, ordered_ledger_rows
from app.services.carton_procurement import _movement_key, _movement_out


MOVEMENT_LABELS = {"INBOUND": "入库", "OUTBOUND": "出库", "ADJUSTMENT": "调整", "REVERSAL": "冲销"}


def _date_filter(value: date | str | None) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "库存流水日期格式无效") from exc


def inventory_movement_history(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    customer_name: str = "",
    search: str = "",
    movement_type: str = "",
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> CartonInventoryHistoryListOut:
    # The API caller holds the same factory lock as balances and cost projections.
    # Date comparison happens after normalization: legacy local, Z and offsets
    # cannot safely be filtered using raw persisted timestamp strings in SQL.
    first_day, last_day = _date_filter(date_from), _date_filter(date_to)
    if first_day and last_day and first_day > last_day:
        raise HTTPException(422, "库存流水开始日期不能晚于结束日期")
    if movement_type and movement_type not in MOVEMENT_LABELS:
        raise HTTPException(422, "库存流水类型无效")
    if not 1 <= limit <= 500 or offset < 0:
        raise HTTPException(422, "库存流水分页参数无效")

    rows = ordered_ledger_rows(db, factory_id)
    from app.services.carton_return_dates import dates
    return_dates = dates(db, factory_id)
    reversed_ids = {row.reversal_of_movement_id for row in rows if row.reversal_of_movement_id}
    balances: dict[str, Decimal] = defaultdict(Decimal)
    matches = []
    keyword = search.strip().casefold()
    customer_code = customer_code.strip()
    customer_name = customer_name.strip()
    named_customer_codes = set(db.scalars(select(CartonCustomer.customer_code).where(
        CartonCustomer.factory_id == factory_id, CartonCustomer.customer_name == customer_name,
    ))) if customer_name else set()
    for row in rows:
        key = _movement_key(row)
        balances[key] += row.quantity
        if customer_code and row.customer_code != customer_code:
            continue
        # Printed names are immutable historical snapshots; a current customer
        # rename must not hide older rows of that same stable customer code.
        if customer_name and row.customer_name != customer_name and row.customer_code not in named_customer_codes:
            continue
        if movement_type and row.movement_type != movement_type:
            continue
        timestamp = ledger_time(row.occurred_at)
        business_day = timestamp.date()
        if first_day and business_day < first_day or last_day and business_day > last_day:
            continue
        label = "期初" if row.source_type == "HISTORY_INVENTORY" else MOVEMENT_LABELS[row.movement_type]
        if keyword and keyword not in " ".join((
            timestamp.strftime("%Y-%m-%d %H:%M"), row.document_no, row.customer_code,
            row.customer_name, row.contract_no, row.item_no, row.packaging_type,
            row.paper_quality, row.specification, label, row.location,
            row.actor_name, row.reason, row.workshop_name,
        )).casefold():
            continue
        matches.append(CartonInventoryHistoryMovementOut(
            **_movement_out(row, balances[key], return_dates=return_dates).model_dump(),
            is_reversed=row.id in reversed_ids,
        ))
    matches.reverse()
    items = annotate_movements(db, factory_id, matches[offset:offset + limit])
    return CartonInventoryHistoryListOut(
        factory_id=factory_id, total=len(matches), limit=limit, offset=offset, items=items,
    )
