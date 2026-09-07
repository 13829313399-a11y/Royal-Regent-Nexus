"""Read-only quantity report over the complete authoritative inventory ledger."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import parse_business_timestamp
from app.models.carton_procurement import CartonInventoryMovement, CartonOrder, CartonOrderLine
from app.schemas.carton_inventory_report import (
    CartonInventoryReportMovement,
    CartonInventoryReportOut,
    CartonInventoryReportRow,
    CartonInventoryOrderReportRow,
)


def _inventory_identity(row: CartonInventoryMovement) -> tuple:
    # Preserve the ledger's formal-line/standalone distinction, plus explicit
    # customer/material/unit scope so malformed legacy IDs cannot widen a match.
    return (row.factory_id, row.customer_code, row.order_line_id, row.contract_no,
            row.item_no, row.packaging_type, row.paper_quality, row.specification, row.unit)


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


def _document_identity(movement: CartonInventoryMovement) -> tuple:
    return ((movement.source_type, movement.movement_type, movement.document_no)
            if movement.source_type == "MANUAL" and movement.document_no
            else (movement.source_type, movement.source_id or movement.document_no or movement.id))


def _order_report(dated_rows, formal_lines, matched_lines, details, date_from, date_to):
    groups: dict[tuple, CartonInventoryOrderReportRow] = {}
    documents: dict[tuple, set[tuple]] = defaultdict(set)
    detail_by_id = {detail.id: detail for detail in details}

    def make_row(identity, customer_name, order=None):
        return CartonInventoryOrderReportRow(
            key=json.dumps(identity, ensure_ascii=False, separators=(",", ":")),
            order_id=order.id if order else None, order_line_id=identity[2],
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
        identity = _inventory_identity(movement)
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
        documents[identity].add(_document_identity(movement))
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
        matched = {
            _inventory_identity(row) for row in all_rows
            if row.order_line_id in matched_line_ids or keyword in " ".join((row.document_no, row.customer_code, row.customer_name,
                                     row.contract_no, row.item_no, row.packaging_type,
                                     row.paper_quality, row.specification, row.location)).casefold()
        }
        all_rows = [row for row in all_rows if _inventory_identity(row) in matched]
        # A historical document/location match still displays its formal line,
        # without making unrelated lines of the same order match the keyword.
        matched_lines = [pair for pair in formal_lines.values()
                         if pair[0].id in matched_line_ids or _line_identity(pair[0]) in matched]

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
        document_identity = _document_identity(movement)
        documents[group_key].add(document_identity)
        group.document_count = len(documents[group_key])
        derived = {"business_date", "occurred_at", "flow_category", "flow_quantity"}
        details.append(CartonInventoryReportMovement(
            **{field: getattr(movement, field) for field in CartonInventoryReportMovement.model_fields
               if field not in derived},
            business_date=day, occurred_at=timestamp.isoformat(),
            flow_category=category, flow_quantity=flow_quantity,
        ))

    return CartonInventoryReportOut(
        factory_id=factory_id, date_from=date_from, date_to=date_to,
        rows=[groups[key] for key in sorted(groups, key=lambda key: (-date.fromisoformat(key[0]).toordinal(), key[1], key[2]))],
        order_rows=_order_report(dated_rows, formal_lines, matched_lines, details, date_from, date_to),
        movements=list(reversed(details)),
    )
