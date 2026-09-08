"""Read-only order activity projection; quantities never come from mutable totals."""

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import parse_business_timestamp
from app.models.carton_procurement import (
    CartonAuditEvent, CartonInventoryMovement, CartonOrder, CartonOrderLine,
    CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine,
)
from app.schemas.carton_order_timeline import CartonOrderTimelineEvent as Event, CartonOrderTimelineOut
from app.services.carton_inventory_report import _inventory_identity, _validate_dates


ORDER_LABELS = {
    "ORDER_CREATED": "落单", "HISTORY_ORDER_IMPORTED": "历史订单导入",
    "ORDER_UPDATED": "修改订单", "ORDER_SUBMITTED_SUPPLIER": "确认订单并锁定",
    "ORDER_APPENDED": "追加订单", "ORDER_REDUCED": "减少订单",
    "ORDER_CANCELLED": "取消订单", "ORDER_RETURNED": "退单",
}


def _detail(event):
    try:
        value = json.loads(event.detail_json or "{}")
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _number(value):
    try:
        result = Decimal(str(value))
        return format(result, "f") if result.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def _time(value):
    result = parse_business_timestamp(value)
    if result is None:
        raise HTTPException(409, "订单流水存在无效记录时间，请核对历史数据")
    return result


def _key(row):
    return json.dumps(_inventory_identity(row), ensure_ascii=False, separators=(",", ":"))


def order_timeline(db: Session, factory_id: str, *, customer_code: str = "", date_from: str = "",
                   date_to: str = "", search: str = "", order_id: str = "",
                   inventory_key: str = "") -> CartonOrderTimelineOut:
    _validate_dates(date_from, date_to)
    if order_id and inventory_key:
        raise HTTPException(422, "订单和无单库存筛选不能同时指定")

    def scoped(model):
        return list(db.scalars(select(model).where(model.factory_id == factory_id)))

    orders = {row.id: row for row in scoped(CartonOrder)
              if not customer_code or row.customer_code == customer_code}
    lines = {row.id: row for row in scoped(CartonOrderLine) if row.order_id in orders}
    movements = [row for row in scoped(CartonInventoryMovement)
                 if (not customer_code or row.customer_code == customer_code)
                 and (not row.order_line_id or row.order_line_id in lines)]
    movements_by_id = {row.id: row for row in movements}
    receipts = {row.id: row for row in scoped(CartonReceipt)}
    receipt_lines = defaultdict(list)
    for row in scoped(CartonReceiptLine):
        if (not customer_code or row.customer_code == customer_code) and (
                not row.order_line_id or row.order_line_id in lines):
            receipt_lines[row.receipt_id].append(row)
    issues = {row.id: row for row in scoped(CartonPurchaseOrderIssue) if row.order_id in orders}
    audits = sorted(scoped(CartonAuditEvent), key=lambda row: row.sequence)
    details = {row.id: _detail(row) for row in audits}
    sequences = {}
    for audit in audits:
        detail = details[audit.id]
        if audit.event_type in {"INVENTORY_MOVEMENT_CREATED", "RECEIPT_CONFIRMED"}:
            sequences[audit.entity_id] = audit.sequence
        elif audit.event_type == "INVENTORY_MOVEMENT_REVERSED":
            sequences[detail.get("reversal_id", "")] = audit.sequence
        elif audit.event_type in {"ORDER_RETURNED", "INVENTORY_BULK_OUTBOUND_CREATED"}:
            for identity in detail.get("movement_ids", []):
                sequences.setdefault(identity, audit.sequence)

    result = []

    def add(event, sequence=0):
        timestamp = _time(event.occurred_at)
        event.occurred_at = timestamp.isoformat()
        result.append((timestamp, sequence, event.id, event))

    def identity(order=None, row=None):
        source = row or order
        return dict(order_id=order.id if order else None,
                    customer_code=source.customer_code, customer_name=getattr(source, "customer_name", ""),
                    contract_no=source.contract_no, item_no=source.item_no,
                    product_name=order.product_name if order else "")

    def linked_order(row):
        line = lines.get(row.order_line_id)
        return orders.get(line.order_id) if line else None

    for audit in audits:
        detail = details[audit.id]
        base = dict(id=f"audit:{audit.id}", occurred_at=audit.created_at,
                    event_type=audit.event_type, actor_name=audit.actor_name,
                    reason=str(detail.get("reason") or ""))
        if audit.entity_type == "carton_order" and audit.event_type in ORDER_LABELS:
            order = orders.get(audit.entity_id)
            if not order:
                continue
            event = Event(**base, **identity(order), event_label=ORDER_LABELS[audit.event_type])
            before, after = None, None
            if audit.event_type in {"ORDER_APPENDED", "ORDER_REDUCED"}:
                before, after = _number(detail.get("before_quantity")), _number(detail.get("after_quantity"))
            elif audit.event_type == "ORDER_UPDATED":
                old, new = detail.get("before") or {}, detail.get("after") or {}
                before = _number(old.get("product_order_quantity"))
                after = _number(new.get("product_order_quantity"))
                changes = []
                for field, label in (("contract_no", "合同"), ("item_no", "货号"),
                                     ("customer_code", "客户编码"), ("order_date", "下单日期"),
                                     ("customer_due_date", "客户交期"), ("due_date", "计划交期")):
                    if field in old and field in new and old[field] != new[field]:
                        changes.append(f"{label}：{old[field] or '未填写'} → {new[field] or '未填写'}")
                if "lines" in old and "lines" in new and old["lines"] != new["lines"]:
                    changes.append("纸品明细已修改")
                if "note" in old and "note" in new and old["note"] != new["note"]:
                    changes.append(f"备注：{old['note'] or '未填写'} → {new['note'] or '未填写'}")
                event.description = "；".join(changes)
            elif audit.event_type in {"ORDER_CREATED", "HISTORY_ORDER_IMPORTED"}:
                after = _number(detail.get("product_order_quantity"))
                before = "0" if after is not None else None
                if after is None:
                    event.description = "历史落单记录未保存当时产品数量，未以当前数量回填。"
                for field in ("customer_code", "customer_name", "contract_no", "item_no", "product_name"):
                    if field in detail:
                        setattr(event, field, str(detail[field] or ""))
            if before is not None and after is not None:
                event.quantity_before, event.quantity_after = before, after
                event.quantity_change = format(Decimal(after) - Decimal(before), "f")
                event.quantity_basis, event.unit = "ORDER_PRODUCT", "件"
            if audit.event_type == "ORDER_RETURNED":
                event.description = "订单退单；实际库存减少见关联退单出库流水。"
            add(event, audit.sequence)
        elif audit.event_type == "PURCHASE_ORDER_ISSUED" and audit.entity_id in issues:
            issue = issues[audit.entity_id]
            add(Event(**base, **identity(orders[issue.order_id]), event_label="发行供应商采购单",
                      document_no=issue.document_no,
                      description="已发行不可变采购单；发行本身不改变订单数量或库存。"), audit.sequence)
        elif audit.entity_type == "carton_receipt" and audit.entity_id in receipts:
            receipt = receipts[audit.entity_id]
            if audit.event_type not in {"RECEIPT_DRAFT_CREATED", "RECEIPT_CONFIRMED", "RECEIPT_REVERSED"}:
                continue
            # Posted confirmations and reversals are represented exactly once by
            # their quantity movements; zero-effective lines retain state evidence.
            for row in receipt_lines[audit.entity_id]:
                if audit.event_type == "RECEIPT_CONFIRMED" and row.effective_quantity > 0:
                    continue
                if audit.event_type == "RECEIPT_REVERSED" and detail.get("previous_status") == "POSTED" and row.effective_quantity > 0:
                    continue
                label = {"RECEIPT_DRAFT_CREATED": "保存收料单", "RECEIPT_CONFIRMED": "确认收料（无有效入库）",
                         "RECEIPT_REVERSED": "作废收料单"}[audit.event_type]
                event = Event(**{**base, "id": f"audit:{audit.id}:{row.id}"}, **identity(linked_order(row), row),
                              inventory_key=_key(row), event_label=label, document_no=receipt.delivery_note_no,
                              material_label=f"{row.packaging_type} {row.paper_quality} / {row.specification}",
                              description=f"有效收料 {row.effective_quantity} {row.unit}；本条仅记录收料单状态，不计库存变化。")
                add(event, audit.sequence)
        elif audit.event_type in {"INVENTORY_LOCATION_CHANGED", "INVENTORY_PRICE_CONFIRMED"}:
            reference = detail.get("reference_movement_id") if audit.event_type == "INVENTORY_LOCATION_CHANGED" else audit.entity_id
            row = movements_by_id.get(reference)
            if not row:
                continue
            relocation = audit.event_type == "INVENTORY_LOCATION_CHANGED"
            if relocation:
                change = f"调仓 {detail['quantity']} {detail.get('unit', '')}，总数量不变。" if detail.get('quantity') is not None else "数量不变。"
                description = f"仓位：{detail.get('from_location') or '未填写'} → {detail.get('to_location') or '未填写'}；{change}"
            else:
                description = f"核价：{detail.get('unit_price', '—')} {detail.get('currency', '')}/{row.unit}；数量不变。"
            add(Event(**base, **identity(linked_order(row), row), inventory_key=_key(row),
                      event_label="调仓" if relocation else "入库核价", document_no=row.document_no,
                      material_label=f"{row.packaging_type} {row.paper_quality} / {row.specification}",
                      description=description), audit.sequence)

    def movement_sequence(row):
        return sequences.get(row.id, sequences.get(row.source_id, 0))

    dated = sorted(movements, key=lambda row: (_time(row.occurred_at), movement_sequence(row), row.id))
    unsequenced = defaultdict(list)
    for row in dated:
        if not movement_sequence(row):
            unsequenced[(_key(row), _time(row.occurred_at))].append(row)
    ambiguous = {key for key, group in unsequenced.items() if len(group) > 1}
    balances = defaultdict(Decimal)
    for row in dated:
        key = _key(row)
        before = balances[key]
        balances[key] += Decimal(row.quantity)
        label = {"INBOUND": "确认入库", "OUTBOUND": "出库", "ADJUSTMENT": "库存调整", "REVERSAL": "库存冲销"}[row.movement_type]
        if row.source_type == "ORDER_RETURN":
            label = "退单出库"
        elif row.source_type == "STOCKTAKE":
            label = "盘点调整"
        elif row.source_type == "HISTORY_INVENTORY":
            label = "期初库存导入"
        elif row.reversal_of_movement_id:
            original = movements_by_id.get(row.reversal_of_movement_id)
            label = {"INBOUND": "入库冲销", "OUTBOUND": "出库冲销", "ADJUSTMENT": "调整冲销"}.get(
                original.movement_type if original else "", label)
        event = Event(id=f"movement:{row.id}", occurred_at=row.occurred_at, event_type=row.movement_type,
                      event_label=label, **identity(linked_order(row), row), inventory_key=key,
                      document_no=row.document_no, material_label=f"{row.packaging_type} {row.paper_quality} / {row.specification}",
                      quantity_change=_number(row.quantity), quantity_before=_number(before), quantity_after=_number(balances[key]),
                      unit=row.unit, quantity_basis="INVENTORY", reason=row.reason, actor_name=row.actor_name)
        if (key, _time(row.occurred_at)) in ambiguous:
            event.quantity_before = event.quantity_after = None
            event.description = "同秒旧流水缺少操作先后证据，仅展示实际变动数量。"
        add(event, movement_sequence(row))

    keyword = search.strip().casefold()
    matched_orders, matched_stock = set(), set()
    if keyword:
        for _, _, _, event in result:
            if keyword in " ".join((event.customer_code, event.customer_name, event.contract_no, event.item_no,
                                     event.product_name, event.document_no, event.material_label)).casefold():
                if event.order_id:
                    matched_orders.add(event.order_id)
                else:
                    matched_stock.add(event.inventory_key)
    events = []
    for timestamp, _, _, event in sorted(result, key=lambda row: row[:3]):
        if order_id and event.order_id != order_id:
            continue
        if inventory_key and (event.order_id is not None or event.inventory_key != inventory_key):
            continue
        if keyword and event.order_id not in matched_orders and event.inventory_key not in matched_stock:
            continue
        day = timestamp.date().isoformat()
        if (date_from and day < date_from) or (date_to and day > date_to):
            continue
        events.append(event)
    return CartonOrderTimelineOut(events=events, total=len(events))
