"""Attribute report movements without changing shared inventory identities."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import groupby
import json

from sqlalchemy import select

from app.core.time import parse_business_timestamp
from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
from app.schemas.carton_inventory_report import CartonInventoryReportSource
from app.services.carton_source_links import line_sources


UNATTRIBUTED = "UNATTRIBUTED"
SPECIAL_DEBITS = {"SPECIAL_RETURN", "SPECIAL_REPLENISHMENT"}


def inventory_identity(row) -> tuple:
    # Keep the formal line, customer, material and unit boundaries of the
    # existing report even when separate requests share a physical stock key.
    return (row.factory_id, row.customer_code, row.order_line_id, row.contract_no,
            row.item_no, row.packaging_type, row.paper_quality, row.specification, row.unit)


def serialized_key(identity: tuple) -> str:
    return json.dumps(identity, ensure_ascii=False, separators=(",", ":"))


def is_unattributed(identity: tuple) -> bool:
    return identity[9:] == (UNATTRIBUTED,)


@dataclass
class ReportSources:
    movement_keys: dict[str, tuple]
    requests: dict[tuple, CartonInventoryReportSource]
    receipt_keys: dict[str, tuple]
    relocation_keys: dict[str, tuple]
    unattributed_sources: dict[str, set[tuple]]
    current_owners: dict[tuple, set[tuple]]


def movement_sources(db, factory: str, movements: list[CartonInventoryMovement],
                     *, relocations: dict[str, tuple[str, str]] | None = None) -> ReportSources:
    """Resolve exact evidence first, then assign only provably exclusive debits."""
    receipt_movements = {row.source_line_id: row for row in movements
                         if not row.order_line_id and row.source_type == "RECEIPT"
                         and row.movement_type == "INBOUND" and row.quantity > 0}
    refs = line_sources(db, factory, list(receipt_movements))
    base_keys = {row.id: inventory_identity(row) for row in movements}
    relocation_keys = {event_id: base_keys[movement_id] for event_id, (movement_id, _) in (relocations or {}).items()}
    projected = ReportSources(base_keys.copy(), {}, {}, relocation_keys, {}, {})
    exact = {}
    for line_id, ref in refs.items():
        if not ref.get("id") or not ref.get("line_id"):
            continue
        row = receipt_movements[line_id]
        source = CartonInventoryReportSource.model_validate(ref)
        key = (*base_keys[row.id], "SPECIAL", source.id, source.line_id)
        projected.requests[key] = source
        projected.receipt_keys[line_id] = exact[row.id] = key
    if not exact:
        return projected

    by_id = {row.id: row for row in movements}
    debit_ids = [row.id for row in movements
                 if row.source_type in SPECIAL_DEBITS and row.movement_type == "OUTBOUND"]
    if debit_ids:
        events = db.scalars(select(CartonAuditEvent).where(
            CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.event_type == "SPECIAL_STOCK_SOURCE_LINKED",
            CartonAuditEvent.entity_type == "carton_inventory_movement",
            CartonAuditEvent.entity_id.in_(debit_ids)))
        for event in events:
            try:
                part = json.loads(event.detail_json)
                quantity = Decimal(str(part["quantity"]))
            except (TypeError, ValueError, KeyError, InvalidOperation):
                continue
            original = receipt_movements.get(part.get("receipt_line_id"))
            debit = by_id[event.entity_id]
            if (original and original.id in exact and part.get("movement_id") == original.id
                    and part.get("debit_movement_id") == debit.id
                    and base_keys[debit.id] == base_keys[original.id]
                    and quantity.is_finite() and -debit.quantity == quantity):
                exact[debit.id] = exact[original.id]

    sourced_pools = {key[:9] for key in projected.requests}
    pools = defaultdict(list)
    for row in movements:
        base = base_keys[row.id]
        if base in sourced_pools:
            pools[base].append(row)
    checkpoints = defaultdict(list)
    for event_id, (_, occurred_at) in (relocations or {}).items():
        base = relocation_keys[event_id]
        if base in sourced_pools:
            checkpoints[base].append((event_id, occurred_at))
    for base, rows in pools.items():
        balances = _assign_pool(base, rows, exact, by_id, checkpoints[base], projected)
        projected.current_owners[base] = {key for key, quantity in balances.items() if quantity != 0}
    return projected


def _assign_pool(base, rows, exact, by_id, checkpoints, projection):
    keys = projection.movement_keys
    unassigned = (*base, UNATTRIBUTED)
    dated = [(parse_business_timestamp(row.occurred_at), row, None) for row in rows]
    dated.extend((parse_business_timestamp(occurred_at), None, event_id)
                 for event_id, occurred_at in checkpoints)
    valid_dates = all(timestamp is not None for timestamp, _, _ in dated)
    if valid_dates:
        dated.sort(key=lambda entry: entry[0])
    else:
        # The report rejects invalid timestamps when displaying those rows.
        # Keep exact links, but do not infer ownership using incomplete order.
        dated = [(None, row, event_id) for _, row, event_id in dated]
    balances = defaultdict(Decimal)
    for _, entries in groupby(dated, key=lambda entry: entry[0]):
        entries = list(entries)
        batch = [row for _, row, _ in entries if row is not None]
        checks = [event_id for _, _, event_id in entries if event_id is not None]
        pending = []
        reversal_rows = []
        previously_shared = bool(balances[unassigned])
        candidates = {key for key, balance in balances.items() if key != unassigned and balance > 0}
        for row in batch:
            if row.movement_type == "REVERSAL":
                reversal_rows.append(row)
                continue
            if row.id not in exact and row.quantity < 0:
                pending.append(row)
                continue
            key = keys[row.id] = exact.get(row.id, base)
            if row.quantity > 0:
                candidates.add(key)
            balances[key] += row.quantity
        pending_ids = {row.id for row in pending}
        deferred = []
        for row in reversal_rows:
            original = by_id.get(row.reversal_of_movement_id)
            if original is None or inventory_identity(original) != base:
                continue
            if original.id in pending_ids:
                deferred.append(row)
                continue
            key = keys[row.id] = exact.get(original.id, keys[original.id])
            if key == unassigned:
                projection.unattributed_sources[row.id] = projection.unattributed_sources.get(original.id, set())
            balances[key] += row.quantity
            if row.quantity > 0 and key != unassigned:
                candidates.add(key)
        owner = next(iter(candidates), None) if len(candidates) == 1 else None
        # Treat equal-time debits as a batch so random IDs cannot decide which
        # debit used the last available units from a request.
        if (not valid_dates or owner is None or balances[unassigned] != 0
                or balances[owner] + sum(row.quantity for row in pending) < 0
                or any(row.source_type in SPECIAL_DEBITS for row in pending)):
            owner = unassigned if candidates - {base} or balances[unassigned] != 0 else base
            if any(row.source_type in SPECIAL_DEBITS for row in pending):
                owner = unassigned
        for row in pending:
            keys[row.id] = owner
            balances[owner] += row.quantity
            if owner == unassigned:
                projection.unattributed_sources[row.id] = candidates
        for row in deferred:
            key = keys[row.id] = keys[row.reversal_of_movement_id]
            balances[key] += row.quantity
            if key == unassigned:
                projection.unattributed_sources[row.id] = projection.unattributed_sources[row.reversal_of_movement_id]
        for event_id in checks:
            # Relocation changes positions only. The reference doesn't identify
            # a lot, so attribute it only when the pool has a single owner.
            projection.relocation_keys[event_id] = next(iter(candidates)) if (
                valid_dates and len(candidates) == 1
                and not previously_shared and balances[unassigned] == 0
            ) else unassigned
        if sum(balances.values()) == 0:
            balances.clear()
    return balances
