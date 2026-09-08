"""Read-only money fields using the same full-ledger valuation as monthly closing."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, localcontext
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent
from app.services.carton_ledger_time import ledger_rows
from app.services.carton_inventory_identity import inventory_key
from app.services.carton_inventory_valuation import value_movements, cost_key


def projection(db, factory):
    rows = ledger_rows(db, factory)
    events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory).order_by(CartonAuditEvent.sequence)))
    value = value_movements(rows, events)
    return rows, value


def money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def annotate_balances(db, factory, balances):
    rows, value = projection(db, factory)
    keys = defaultdict(set)
    for row in rows:
        keys[inventory_key(row)].add(cost_key(row))
    bad = {cost_key(row) for row, _ in value.errors}
    grouped = defaultdict(list)
    for balance in balances:
        grouped[balance.inventory_key].append(balance)
    with localcontext() as ctx:
        ctx.prec = 48
        for identity, positions in grouped.items():
            candidates = [key for key in keys[identity] if value.balances[key].quantity != 0]
            for position in positions:
                position.cost_status = "待核算"
            if len(candidates) != 1:
                for position in positions:
                    if position.balance == 0:
                        position.cost_amount = Decimal(0)
                        position.cost_status = "无库存"
                continue
            key = candidates[0]
            pool = value.balances[key]
            status = "待核算" if key in bad or pool.quantity <= 0 else "待核价" if key in value.unpriced_pools else "已计价"
            if sum(p.balance for p in positions) != pool.quantity or any(p.balance < 0 for p in positions):
                status = "待核算"
            # Largest remainder allocation keeps tiny positive positions
            # nonnegative while every displayed cent reconciles to the pool.
            exact = {p.position_key: p.balance * pool.amount / pool.quantity * 100 for p in positions}
            cents = {key: amount.to_integral_value(rounding=ROUND_FLOOR) for key, amount in exact.items()}
            if status == "已计价":
                remainder = int(money(pool.amount) * 100 - sum(cents.values()))
                ranked = sorted(positions, key=lambda p: (-(exact[p.position_key] - cents[p.position_key]), p.position_key))
                for position in ranked[:remainder]:
                    cents[position.position_key] += 1
            for position in positions:
                position.cost_currency = key[-1]
                position.cost_status = status
                if status != "已计价":
                    continue
                position.cost_unit_price = pool.amount / pool.quantity
                position.cost_amount = cents[position.position_key] / 100
    return balances


def annotate_movements(db, factory, items):
    rows, value = projection(db, factory)
    by_id = {row.id: row for row in rows}
    bad = {cost_key(row) for row, _ in value.errors}
    with localcontext() as ctx:
        ctx.prec = 48
        for item in items:
            row = by_id.get(item.id)
            if not row:
                continue
            key = cost_key(row)
            item.cost_currency = key[-1]
            item.cost_status = "待核算" if key in bad else "待核价" if row.id in value.unpriced_movements else "已计价"
            if item.cost_status == "已计价":
                amount = value.amounts[row.id]
                item.cost_amount = money(amount)
                item.cost_unit_price = abs(amount / row.quantity) if row.quantity else Decimal(0)
    return items
