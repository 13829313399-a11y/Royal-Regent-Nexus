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
from app.services.carton_ledger_time import ledger_rows, ledger_time


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
    unpriced_movements: set[str] = field(default_factory=set)
    unpriced_pools: set[tuple[str, ...]] = field(default_factory=set)
    missing: list[CartonInventoryMovement] = field(default_factory=list)
    errors: list[tuple[CartonInventoryMovement, str]] = field(default_factory=list)


def load_valuation(db: Session, factory_id: str, *, before: str | None = None) -> Valuation:
    rows = ledger_rows(db, factory_id, before=before)
    events = list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory_id,
    ).order_by(CartonAuditEvent.sequence)).all())
    return value_movements(rows, events)


def value_movements(rows: list[CartonInventoryMovement], events: list[CartonAuditEvent]) -> Valuation:
    sequence: dict[str, int] = {}
    split_sources: dict[str, str] = {}
    split_order: dict[str, int] = {}
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
        elif event.event_type == "ORDER_SPLIT_STOCK_MOVED":
            for index, pair in enumerate(detail["pairs"]):
                split_sources[pair["to_id"]] = pair["from_id"]
                for rank, identifier in enumerate((pair["from_id"], pair["to_id"])):
                    sequence[identifier] = event.sequence
                    split_order[identifier] = 2 * index + rank
        elif event.event_type in {"ORDER_RETURNED", "INVENTORY_BULK_OUTBOUND_CREATED"}:
            for movement_id in detail.get("movement_ids", []):
                sequence.setdefault(movement_id, event.sequence)

    def order_key(row: CartonInventoryMovement):
        seq = sequence.get(row.id, sequence.get(row.source_id, 0))
        # Unsequenced legacy receipts/initial balances precede issues at the same
        # second. Ambiguous interleaved legacy transactions are not guessed.
        return (ledger_time(row.occurred_at), seq, split_order.get(row.id, 0), row.quantity < 0, row.id)

    ordered = sorted(rows, key=order_key)
    by_id = {row.id: row for row in rows}
    result = Valuation()
    # Unknown source prices are independent variables. Carry their quantity
    # coefficients with the same averaging/reversal arithmetic as real costs.
    dependencies: dict[tuple[str, ...], dict[str, Decimal]] = defaultdict(dict)
    movement_dependencies: dict[str, dict[str, Decimal]] = {}
    ambiguous: dict[tuple, list[CartonInventoryMovement]] = defaultdict(list)
    for row in rows:
        if not sequence.get(row.id, sequence.get(row.source_id, 0)):
            ambiguous[(ledger_time(row.occurred_at), cost_key(row))].append(row)
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
            pool_dependencies = dependencies[key]
            unknown: dict[str, Decimal] = {}
            if row.reversal_of_movement_id:
                unknown = {source: -coefficient for source, coefficient in movement_dependencies.get(row.reversal_of_movement_id, {}).items()}
                original = by_id.get(row.reversal_of_movement_id)
                if original is None or original.id not in result.amounts or cost_key(original) != key:
                    result.errors.append((row, "冲销缺少同一物料、币种的原计价记录"))
                    amount = qty * price
                else:
                    amount = -result.amounts[original.id]
            elif row.id in split_sources:
                source = split_sources[row.id]
                if source not in result.amounts:
                    result.errors.append((row, "拆单库存缺少原归属扣减金额，不能按显示单价猜测"))
                    amount = qty * price
                else:
                    amount = -result.amounts[source]
                    unknown = {identifier: -coefficient for identifier, coefficient in movement_dependencies[source].items()}
            elif qty > 0:
                amount = qty * price
                if price == 0 and row.id not in prices:
                    result.missing.append(row)
                    unknown = {row.id: qty}
            else:
                if balance.quantity > 0:
                    unknown = {source: (-coefficient if balance.quantity + qty == 0 else coefficient * qty / balance.quantity)
                               for source, coefficient in pool_dependencies.items()}
                if balance.quantity <= 0 or balance.quantity + qty < 0:
                    result.errors.append((row, "计价库存不足，请核对该物料和币种的入库记录"))
                    amount = qty * price
                elif balance.quantity + qty == 0:
                    amount = -balance.amount
                else:
                    amount = qty * balance.amount / balance.quantity
            movement_dependencies[row.id] = unknown
            if unknown:
                result.unpriced_movements.add(row.id)
            for source, coefficient in unknown.items():
                updated = pool_dependencies.get(source, Decimal(0)) + coefficient
                if updated:
                    pool_dependencies[source] = updated
                else:
                    pool_dependencies.pop(source, None)
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
    result.unpriced_pools = {key for key, sources in dependencies.items() if sources}
    return result
