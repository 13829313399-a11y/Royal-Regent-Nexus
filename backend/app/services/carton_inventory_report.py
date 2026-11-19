"""Read-only quantity report over the complete authoritative inventory ledger."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import parse_business_timestamp
from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonOrder, CartonOrderLine
from app.schemas.carton_inventory_report import (
    CartonInventoryReportMovement,
    CartonInventoryReportOut,
    CartonInventoryReportRow,
    CartonInventoryOrderReportRow,
)
from app.services.carton_inventory_report_sources import (
    inventory_identity as _inventory_identity, is_unattributed, movement_sources, serialized_key,
)


def _validate_dates(date_from: str, date_to: str) -> None:
    try:
        for value in (date_from, date_to):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="汇总日期必须是有效的 YYYY-MM-DD 日期") from None
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="汇总开始日期不能晚于结束日期")


def _line_identity(line: CartonOrderLine) -> tuple:
    return (line.factory_id, line.customer_code, line.id, line.contract_no,
            line.item_no, line.packaging_type, line.paper_quality, line.specification, line.unit)


def _legacy_return_batches(db, factory_id, movements, formal_lines):
    # Older order returns reused RET-<order number>. Each bulk audit identifies
    # exactly the movements in one handover, including multi-location returns.
    from app.services.carton_supplier_read_inputs import batches

    candidates = defaultdict(set)
    for movement in movements:
        formal = formal_lines.get(movement.order_line_id)
        if (formal and movement.source_type == "MANUAL" and movement.issue_kind == "RETURN"
                and movement.document_no == f"RET-{formal[1].order_no}"):
            candidates[movement.document_no].add(movement.id)
    result = {}
    for numbers in batches(list(candidates)):
        for event in db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.factory_id == factory_id, CartonAuditEvent.entity_type == "carton_inventory_batch",
                CartonAuditEvent.event_type == "INVENTORY_BULK_OUTBOUND_CREATED", CartonAuditEvent.entity_id.in_(numbers))):
            for movement_id in json.loads(event.detail_json).get("movement_ids", []):
                if movement_id in candidates[event.entity_id]:
                    result[movement_id] = event.id
    return result


def _document_identity(movement: CartonInventoryMovement, legacy_return_batches) -> tuple:
    if movement.id in legacy_return_batches:
        return ("RETURN_BATCH", legacy_return_batches[movement.id])
    return ((movement.source_type, movement.movement_type, movement.document_no)
            if movement.source_type == "MANUAL" and movement.document_no
            else (movement.source_type, movement.source_id or movement.document_no or movement.id))


def _order_report(dated_rows, formal_lines, matched_lines, details, date_from, date_to, sources, legacy_return_batches):
    groups: dict[tuple, CartonInventoryOrderReportRow] = {}
    documents: dict[tuple, set[tuple]] = defaultdict(set)
    detail_by_id = {detail.id: detail for detail in details}

    def make_row(identity, customer_name, order=None):
        return CartonInventoryOrderReportRow(
            key=serialized_key(identity),
            order_id=order.id if order else None, order_line_id=identity[2],
            source_request=sources.requests.get(identity), unattributed=is_unattributed(identity),
            order_date=order.order_date if order else "", customer_code=identity[1],
            customer_name=customer_name, contract_no=identity[3], item_no=identity[4],
            product_name=order.product_name if order else "", packaging_type=identity[5],
            paper_quality=identity[6], specification=identity[7], unit=identity[8],
            opening_quantity=0, inbound_quantity=0, outbound_quantity=0,
            adjustment_quantity=0, ending_quantity=0, document_count=0, line_count=0,
            last_movement_at="",
        )

    for timestamp, _, movement in dated_rows:
        day = timestamp.date().isoformat()
        if date_to and day > date_to:
            break
        identity = sources.movement_keys[movement.id]
        formal = formal_lines.get(movement.order_line_id)
        if identity not in groups:
            groups[identity] = make_row(identity, movement.customer_name, formal[1] if formal else None)
        row = groups[identity]
        row.customer_name = movement.customer_name
        row.last_movement_at = timestamp.isoformat()
        row.ending_quantity += Decimal(movement.quantity)
        if date_from and day < date_from:
            row.opening_quantity += Decimal(movement.quantity)
            continue
        detail = detail_by_id[movement.id]
        field = {"INBOUND": "inbound_quantity", "OUTBOUND": "outbound_quantity",
                 "ADJUSTMENT": "adjustment_quantity"}[detail.flow_category]
        setattr(row, field, getattr(row, field) + detail.flow_quantity)
        row.line_count += 1
        documents[identity].add(_document_identity(movement, legacy_return_batches))
        row.document_count = len(documents[identity])

    # Orders without postings are useful in the all-date overview. With dates,
    # include them only when placed in the selected range. Cancelled orders only
    # remain when actual ledger history establishes a reportable balance/activity.
    for line, order in matched_lines:
        identity = _line_identity(line)
        if order.status == "CANCELLED" or identity in groups:
            continue
        if (date_from and order.order_date < date_from) or (date_to and order.order_date > date_to):
            continue
        groups[identity] = make_row(identity, order.customer_name, order)

    def include(row):
        if not date_from and not date_to:
            return True
        if row.line_count or row.opening_quantity:
            return True
        formal = formal_lines.get(row.order_line_id)
        return bool(formal and formal[1].status != "CANCELLED" and
                    (not date_from or row.order_date >= date_from) and
                    (not date_to or row.order_date <= date_to))

    return sorted((row for row in groups.values() if include(row)),
                  key=lambda row: (row.last_movement_at or row.order_date, row.key), reverse=True)


def inventory_report(
    db: Session, factory_id: str, *, customer_code: str = "",
    date_from: str = "", date_to: str = "", search: str = "",
) -> CartonInventoryReportOut:
    _validate_dates(date_from, date_to)
    query = select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory_id)
    if customer_code:
        query = query.where(CartonInventoryMovement.customer_code == customer_code)
    all_rows = list(db.scalars(query))
    by_id = {row.id: row for row in all_rows}
    sources = movement_sources(db, factory_id, all_rows)
    line_query = select(CartonOrderLine, CartonOrder).join(
        CartonOrder, (CartonOrder.id == CartonOrderLine.order_id)
        & (CartonOrder.factory_id == CartonOrderLine.factory_id),
    ).where(CartonOrderLine.factory_id == factory_id)
    if customer_code:
        line_query = line_query.where(CartonOrderLine.customer_code == customer_code)
    formal_lines = {line.id: (line, order) for line, order in db.execute(line_query)}
    matched_lines = list(formal_lines.values())
    keyword = search.strip().casefold()
    if keyword:
        matched_lines = [(line, order) for line, order in matched_lines if keyword in " ".join((
            order.customer_code, order.customer_name, line.contract_no, line.item_no,
            order.product_name, line.packaging_type, line.paper_quality, line.specification,
        )).casefold()]
        matched_line_ids = {line.id for line, _ in matched_lines}
        matched_sources = {key for key, ref in sources.requests.items() if keyword == ref.request_no.casefold()}
        matched = matched_sources or {
            sources.movement_keys[row.id] for row in all_rows
            if row.order_line_id in matched_line_ids or keyword in " ".join((row.document_no, row.customer_code, row.customer_name,
                                     row.contract_no, row.item_no, row.packaging_type,
                                     row.paper_quality, row.specification, row.location)).casefold()
        }
        if not matched_sources:
            matched.update(key for key, ref in sources.requests.items() if keyword in ref.request_no.casefold())
        all_rows = [row for row in all_rows if sources.movement_keys[row.id] in matched]
        # A historical document/location match still displays its formal line,
        # without making unrelated lines of the same order match the keyword.
        matched_lines = [] if matched_sources else [pair for pair in formal_lines.values()
                         if pair[0].id in matched_line_ids or _line_identity(pair[0]) in matched]

    legacy_return_batches = _legacy_return_batches(db, factory_id, all_rows, formal_lines)
    dated_rows = []
    for row in all_rows:
        timestamp = parse_business_timestamp(row.occurred_at)
        if timestamp is None:
            raise HTTPException(status_code=409, detail="库存流水存在无效时间，无法生成可靠汇总")
        dated_rows.append((timestamp, row.id, row))
    dated_rows.sort(key=lambda item: (item[0], item[1]))

    balances: dict[tuple, Decimal] = defaultdict(Decimal)
    groups: dict[tuple, CartonInventoryReportRow] = {}
    documents: dict[tuple, set[tuple]] = defaultdict(set)
    details: list[CartonInventoryReportMovement] = []
    for timestamp, _, movement in dated_rows:
        day = timestamp.date().isoformat()
        if date_to and day > date_to:
            break
        customer_unit = (movement.customer_code, movement.unit)
        amount = Decimal(movement.quantity)
        opening = balances[customer_unit]
        balances[customer_unit] += amount
        if date_from and day < date_from:
            continue

        original = movement
        if movement.movement_type == "REVERSAL":
            original = by_id.get(movement.reversal_of_movement_id)
            if original is None or original.movement_type == "REVERSAL" or (
                _inventory_identity(original) != _inventory_identity(movement)
            ):
                raise HTTPException(status_code=409, detail="库存冲销缺少一致的原始流水，无法生成可靠汇总")
        category = original.movement_type
        flow_quantity = -amount if category == "OUTBOUND" else amount
        group_key = (day, *customer_unit)
        if group_key not in groups:
            groups[group_key] = CartonInventoryReportRow(
                business_date=day, customer_code=movement.customer_code,
                customer_name=movement.customer_name, unit=movement.unit,
                opening_quantity=opening, inbound_quantity=0, outbound_quantity=0,
                adjustment_quantity=0, ending_quantity=opening, document_count=0, line_count=0,
            )
        group = groups[group_key]
        group.customer_name = movement.customer_name
        field = {"INBOUND": "inbound_quantity", "OUTBOUND": "outbound_quantity",
                 "ADJUSTMENT": "adjustment_quantity"}[category]
        setattr(group, field, getattr(group, field) + flow_quantity)
        group.ending_quantity = balances[customer_unit]
        group.line_count += 1
        # Source document identities avoid collapsing distinct receipt documents
        # or correction events which happen to share a printed document number.
        document_identity = _document_identity(movement, legacy_return_batches)
        documents[group_key].add(document_identity)
        group.document_count = len(documents[group_key])
        derived = {"business_date", "occurred_at", "flow_category", "flow_quantity", "source_request", "unattributed"}
        key = sources.movement_keys[movement.id]
        details.append(CartonInventoryReportMovement(
            **{field: getattr(movement, field) for field in CartonInventoryReportMovement.model_fields
               if field not in derived},
            business_date=day, occurred_at=timestamp.isoformat(),
            flow_category=category, flow_quantity=flow_quantity,
            source_request=sources.requests.get(key), unattributed=is_unattributed(key),
        ))

    order_rows = _order_report(dated_rows, formal_lines, matched_lines, details, date_from, date_to, sources, legacy_return_batches)
    _annotate_current_stock(db, factory_id, order_rows, by_id.values(), sources, date_from, date_to)
    return CartonInventoryReportOut(
        factory_id=factory_id, date_from=date_from, date_to=date_to,
        rows=[groups[key] for key in sorted(groups, key=lambda key: (-date.fromisoformat(key[0]).toordinal(), key[1], key[2]))],
        order_rows=order_rows,
        movements=list(reversed(details)),
    )


def _annotate_current_stock(db, factory_id, rows, movements, sources, date_from, date_to):
    from app.services.carton_usage import LABELS, usage_by_key, usage_for_movements
    from app.services.carton_positions import position_balances, inventory_key

    # Preserve inventory-key status for ordinary stock. Shared identities use
    # the same attributed movements as the report, without borrowing usage or
    # physical positions from a different request.
    sourced_pools = {key[:9] for key in sources.requests}
    usage = usage_by_key(db, factory_id)
    sourced_movements = [row for row in movements if sources.movement_keys[row.id][:9] in sourced_pools]
    usage.update(usage_for_movements(sourced_movements, lambda row: sources.movement_keys[row.id]))
    positions = defaultdict(list)
    for position in position_balances(db, factory_id):
        if position.balance > 0:
            positions[position.inventory_key].append(
                {"location": position.latest_location, "quantity": str(position.balance)})
    unresolved = defaultdict(Decimal)
    unresolved_opening = defaultdict(Decimal)
    unresolved_current = defaultdict(Decimal)
    for movement in movements:
        affected = sources.unattributed_sources.get(movement.id)
        if not affected:
            continue
        timestamp = parse_business_timestamp(movement.occurred_at)
        day = timestamp.date().isoformat() if timestamp else ""
        for key in affected:
            unresolved_current[key] += movement.quantity
            if date_from and day < date_from:
                unresolved_opening[key] += movement.quantity
            if not date_to or day <= date_to:
                unresolved[key] += movement.quantity
    for row in rows:
        physical_key = inventory_key(row)
        report_key = tuple(json.loads(row.key))
        base = report_key[:9]
        if base in sourced_pools:
            row.opening_unconfirmed = bool(row.opening_quantity and unresolved_opening[report_key])
            row.balance_unconfirmed = bool(row.ending_quantity and unresolved[report_key])
            owners = sources.current_owners[base]
            row.positions_shared = bool(positions[physical_key]) and (
                len(owners) > 1 or any(is_unattributed(key) for key in owners))
        state = usage.get(report_key if base in sourced_pools else physical_key, {})
        row.current_usage_quantity = state.get("usage", Decimal(0))
        row.current_usage_status = ("UNKNOWN" if row.unattributed or unresolved_current[report_key]
                                    else state.get("status", "NOT_RECEIVED"))
        row.current_usage_label = LABELS[row.current_usage_status]
        if not row.positions_shared and (
                base not in sourced_pools or report_key in sources.current_owners[base]):
            row.current_positions = positions[physical_key]
