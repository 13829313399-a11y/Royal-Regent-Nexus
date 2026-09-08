"""Read-only moving-average valuation of the immutable carton quantity ledger.

Raw receipt prices remain evidence. Decimal amounts (not rounded display prices)
are carried forward; a full depletion consumes the complete carrying amount.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement


def cost_key(row: CartonInventoryMovement) -> tuple[str, ...]:
    identity = (row.order_line_id,) if row.order_line_id else (
        row.contract_no, row.item_no, row.packaging_type, row.paper_quality, row.specification,
    )
    raw_currency = row.currency.strip().upper()
    currency = {"RMB": "CNY", "人民币": "CNY", "人民币元": "CNY", "¥": "CNY", "￥": "CNY",
                "港币": "HKD", "港元": "HKD", "HK$": "HKD"}.get(raw_currency, raw_currency or "CNY")
    return (row.factory_id, row.customer_code, *identity, row.unit, currency)


@dataclass
class CostBalance:
    quantity: Decimal = Decimal(0)
    amount: Decimal = Decimal(0)


@dataclass
class Valuation:
    balances: dict[tuple[str, ...], CostBalance] = field(default_factory=dict)
    amounts: dict[str, Decimal] = field(default_factory=dict)
    missing: list[CartonInventoryMovement] = field(default_factory=list)
    errors: list[tuple[CartonInventoryMovement, str]] = field(default_factory=list)


def load_valuation(db: Session, factory_id: str, *, before: str | None = None) -> Valuation:
    query = select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory_id)
    if before:
        query = query.where(CartonInventoryMovement.occurred_at < before)
    rows = list(db.scalars(query).all())
    events = list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory_id,
    ).order_by(CartonAuditEvent.sequence)).all())
    return value_movements(rows, events)


def value_movements(rows: list[CartonInventoryMovement], events: list[CartonAuditEvent]) -> Valuation:
    sequence: dict[str, int] = {}
    prices: dict[str, Decimal] = {}
    for event in events:
        detail = json.loads(event.detail_json or "{}")
        if event.event_type == "INVENTORY_PRICE_CONFIRMED":
            prices[event.entity_id] = Decimal(str(detail["unit_price"]))
        elif event.event_type == "INVENTORY_MOVEMENT_CREATED":
            sequence[event.entity_id] = event.sequence
        elif event.event_type == "RECEIPT_CONFIRMED":
            sequence[event.entity_id] = event.sequence
        elif event.event_type == "INVENTORY_MOVEMENT_REVERSED":
            sequence[detail.get("reversal_id", "")] = event.sequence
        elif event.event_type in {"ORDER_RETURNED", "INVENTORY_BULK_OUTBOUND_CREATED"}:
            for movement_id in detail.get("movement_ids", []):
                sequence.setdefault(movement_id, event.sequence)

    def order_key(row: CartonInventoryMovement):
        seq = sequence.get(row.id, sequence.get(row.source_id, 0))
        # Unsequenced legacy receipts/initial balances precede issues at the same
        # second. Ambiguous interleaved legacy transactions are not guessed.
        return (row.occurred_at, seq, row.quantity < 0, row.id)

    ordered = sorted(rows, key=order_key)
    by_id = {row.id: row for row in rows}
    result = Valuation()
    ambiguous: dict[tuple, list[CartonInventoryMovement]] = defaultdict(list)
    for row in rows:
        if not sequence.get(row.id, sequence.get(row.source_id, 0)):
            ambiguous[(row.occurred_at, cost_key(row))].append(row)
    for group in ambiguous.values():
        if any(r.quantity < 0 for r in group) and any(r.quantity > 0 for r in group):
            result.errors.append((group[0], "旧流水同秒发生不同进价与出库，缺少可确认的先后顺序"))

    with localcontext() as ctx:
        ctx.prec = 48
        for row in ordered:
            key = cost_key(row)
            balance = result.balances.setdefault(key, CostBalance())
            qty = Decimal(row.quantity)
            price = prices.get(row.id, Decimal(row.unit_price))
            if row.reversal_of_movement_id:
                original = by_id.get(row.reversal_of_movement_id)
                if original is None or original.id not in result.amounts or cost_key(original) != key:
                    result.errors.append((row, "冲销缺少同一物料、币种的原计价记录"))
                    amount = qty * price
                else:
                    amount = -result.amounts[original.id]
            elif qty > 0:
                amount = qty * price
                if price == 0 and row.id not in prices:
                    result.missing.append(row)
            else:
                if balance.quantity <= 0 or balance.quantity + qty < 0:
                    result.errors.append((row, "计价库存不足，请核对该物料和币种的入库记录"))
                    amount = qty * price
                elif balance.quantity + qty == 0:
                    amount = -balance.amount
                else:
                    amount = qty * balance.amount / balance.quantity
            balance.quantity += qty
            balance.amount += amount
            result.amounts[row.id] = amount
            if balance.quantity < 0 or balance.amount < Decimal("-0.00000001"):
                result.errors.append((row, "冲销或历史交易导致数量或计价金额为负，请先核对后续交易"))
            elif balance.quantity == 0 and abs(balance.amount) > Decimal("0.00000001"):
                result.errors.append((row, "冲销后数量为零但金额未对平，请先核对后续交易"))
    # An untouched canceled opening contributes neither stock nor cost. If any
    # issue consumed the pool before cancellation, its unknown price affected
    # that issue's average cost and still needs explicit price evidence.
    positions = {row.id: index for index, row in enumerate(ordered)}
    reversals = {row.reversal_of_movement_id: row for row in ordered if row.reversal_of_movement_id}
    result.missing = [row for row in result.missing if row.id not in reversals or any(
        candidate.quantity < 0 and cost_key(candidate) == cost_key(row)
        for candidate in ordered[positions[row.id] + 1:positions[reversals[row.id].id]]
    )]
    return result
