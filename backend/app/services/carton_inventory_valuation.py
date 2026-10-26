"""Read-only moving-average valuation of the immutable carton quantity ledger.

Raw receipt prices remain evidence. Decimal amounts (not rounded display prices)
are carried forward; a full depletion consumes the complete carrying amount.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
from app.services.carton_ledger_time import ledger_rows, ledger_time

SPECIAL_REPLACEMENT_EVENT = "SPECIAL_RECEIPT_REPLENISHMENT_LINKED"


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
    """Correction versions revalue exact downstream B sources, preserving old freezes.

    Each B batch remembers the valuation available when its immutable link was
    recorded. Only subsequent correction deltas are inherited, so a B received
    after an earlier correction never receives that difference twice.
    """
    corrections = [event for event in events if event.event_type == "INVENTORY_PRICE_CORRECTED"]
    by_line = {row.source_line_id: row for row in rows if row.source_type == "RECEIPT" and row.quantity > 0}
    by_id = {row.id: row for row in rows}
    special_links, special_errors = _special_replacement_links(rows, events, by_line, by_id)
    split_edges = []
    for event in events:
        if event.event_type == "ORDER_SPLIT_STOCK_MOVED":
            for pair in json.loads(event.detail_json or "{}").get("pairs", []):
                if pair["from_id"] in by_id and pair["to_id"] in by_id: split_edges.append((cost_key(by_id[pair["from_id"]]),cost_key(by_id[pair["to_id"]])))
    def affected_keys(since, cutoff):
        result={cost_key(by_id[event.entity_id]) for event in corrections if since < event.sequence <= cutoff and event.entity_id in by_id}
        while True:
            more={target for source,target in split_edges if source in result}-result
            if not more: return result
            result.update(more)
    links = []
    for event in events:
        if event.event_type != "RECEIPT_REPLENISHMENT_LINKED": continue
        data = json.loads(event.detail_json or "{}")
        row = by_line.get(event.entity_id)
        if row is not None and data.get("responsibility") == "SUPPLIER": links.append((event, data, row))
    cache = {}
    def build(cutoff):
        if cutoff in cache: return cache[cutoff]
        selected = [event for event in events if event.event_type != "INVENTORY_PRICE_CORRECTED" or event.sequence <= cutoff]
        latest = max((event.sequence for event in corrections if event.sequence <= cutoff), default=0)
        replacements, invalid = {}, []
        for event, data, row in links:
            if event.sequence >= latest: continue
            originals = [item for item in rows if item.source_type == "ORDER_REPLENISHMENT"
                and item.source_id == data.get("replenishment_issue_id") and item.order_line_id == row.order_line_id
                and item.quantity < 0 and cost_key(item) == cost_key(row)]
            total = -sum((item.quantity for item in originals), Decimal(0))
            if not originals or total <= 0:
                if cost_key(row) in affected_keys(event.sequence,cutoff): invalid.append(row)
                continue
            reference = build(event.sequence)
            replacements[row.id] = ([item.id for item in originals], total, reference.amounts)
        invalid_special = []
        for identifier, link in special_links.items():
            if link["event"].sequence >= latest:
                continue
            reference = build(link["event"].sequence)
            replacements[identifier] = (link["sources"], link["quantity"], reference.amounts)
            if (any(source in reference.unpriced_movements for source in link["sources"])
                or any(bad.id in link["sources"] for bad, _ in reference.errors)):
                invalid_special.append(by_id[identifier])
        result = _value_movements(rows, selected, replacements, special_links)
        result.errors.extend(special_errors)
        result.errors.extend((row, "样板杂单免费补货原出库在冻结时尚无可靠成本，请核对历史凭证") for row in invalid_special)
        result.errors.extend((row, "免费补货缺少可验证的原补单出库成本来源，不能自动承接单价更正") for row in invalid)
        cache[cutoff] = result
        return result
    return build(max((event.sequence for event in corrections), default=0))


def _special_replacement_links(rows, events, by_line, by_id):
    """Validate exact SPECIAL debit evidence; pooled stock is never a source link."""
    links, errors, seen = {}, [], set()
    sequence = {event.entity_id: event.sequence for event in events
                if event.event_type == "INVENTORY_MOVEMENT_CREATED"}
    reversed_ids = {row.reversal_of_movement_id for row in rows if row.reversal_of_movement_id}
    active_quantities = defaultdict(Decimal)
    linked_rows = defaultdict(list)
    for event in events:
        if event.event_type != SPECIAL_REPLACEMENT_EVENT:
            continue
        row = by_line.get(event.entity_id)
        if row is None:
            continue  # A historical cutoff may intentionally exclude this receipt.
        try:
            data = json.loads(event.detail_json or "{}")
            if not isinstance(data, dict) or data.get("responsibility") not in {"OWN", "SUPPLIER"}:
                raise ValueError
            if row.id in seen:
                raise ValueError
            seen.add(row.id)
            if data["responsibility"] == "OWN":
                continue  # Actual receipt prices retain the ordinary valuation policy.
            identifiers = data["source_movement_ids"]
            total = Decimal(str(data["source_quantity"]))
            amount = Decimal(str(data["inventory_amount"]))
            accepted = Decimal(str(data["quantity"]))
            if (not isinstance(identifiers, list) or len(identifiers) != 1
                or any(not isinstance(identifier, str) for identifier in identifiers)
                or len(identifiers) != len(set(identifiers))
                or not total.is_finite() or total <= 0 or not amount.is_finite() or amount < 0
                or not accepted.is_finite() or accepted != row.quantity or accepted > total
                or Decimal(str(data["settlement_unit_price"])) != 0
                or not data.get("child_request_id") or not data.get("parent_request_id")
                or event.factory_id != row.factory_id or data.get("receipt_id") != row.source_id):
                raise ValueError
            originals = [by_id[identifier] for identifier in identifiers]
            if any(original.factory_id != row.factory_id or original.source_type != "SPECIAL_REPLENISHMENT"
                   or original.movement_type != "OUTBOUND" or original.quantity >= 0
                   or original.source_id != data["child_request_id"] or original.id in reversed_ids
                   or cost_key(original) != cost_key(row)
                   or not sequence.get(original.id) or sequence[original.id] >= event.sequence
                   for original in originals):
                raise ValueError
            if -sum((original.quantity for original in originals), Decimal(0)) != total:
                raise ValueError
            links[row.id] = {"event": event, "sources": identifiers, "quantity": total, "amount": amount}
            key = tuple(sorted(identifiers))
            linked_rows[key].append(row)
            if row.id not in reversed_ids:
                active_quantities[key] += row.quantity
        except (KeyError, TypeError, ValueError, InvalidOperation):
            errors.append((row, "样板杂单免费补货成本来源缺失或不一致，请核对原补单出库及收料凭证"))
    for key, sources in linked_rows.items():
        if active_quantities[key] > links[sources[0].id]["quantity"]:
            errors.extend((row, "样板杂单免费补货有效收料超过原补单出库额度") for row in sources)
    return links, errors


def _value_movements(rows, events, replacements=None, special_links=None):
    replacements = replacements or {}
    special_links = special_links or {}
    sequence: dict[str, int] = {}
    split_sources: dict[str, str] = {}
    split_order: dict[str, int] = {}
    prices: dict[str, Decimal] = {}
    for event in events:
        if event.event_type == SPECIAL_REPLACEMENT_EVENT:
            continue  # Parsed and validated separately, including malformed evidence.
        detail = json.loads(event.detail_json or "{}")
        if event.event_type in {"INVENTORY_PRICE_CONFIRMED", "INVENTORY_PRICE_CORRECTED"}:
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
                special = special_links.get(row.id)
                if special:
                    amount = qty * special["amount"] / special["quantity"]
                    reference = replacements.get(row.id, (None, None, result.amounts))[2]
                    sources = special["sources"]
                    if (any(identifier not in result.amounts or identifier not in reference
                            or identifier in result.unpriced_movements for identifier in sources)
                        or any(cost_key(bad) == key for bad, _ in result.errors)
                        or -sum((reference.get(identifier, Decimal(0)) for identifier in sources), Decimal(0)) != special["amount"]):
                        result.errors.append((row, "样板杂单免费补货冻结成本与原出库计价不一致，不能自动估价"))
                        unknown = {row.id: qty}
                if row.id in replacements:
                    sources, total, previous = replacements[row.id]
                    if any(identifier not in result.amounts or identifier not in previous for identifier in sources):
                        result.errors.append((row, "免费补货先于其原出库或缺少成本来源，不能自动承接单价更正"))
                    else:
                        delta = -sum((result.amounts[identifier] - previous[identifier] for identifier in sources), Decimal(0))
                        amount += qty * delta / total
                if not special and price == 0 and row.id not in prices:
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
