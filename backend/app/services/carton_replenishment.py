"""Replacement procurement: immutable demand, immediate warehouse issue, later receipt."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine
from app.schemas.carton_procurement import CartonInventoryMovementCreate, CartonReplenishmentOut


def replenished_by_line(db, line_ids):
    if not line_ids:
        return {}
    return {line_id: -total for line_id, total in db.execute(select(
        CartonInventoryMovement.order_line_id, func.sum(CartonInventoryMovement.quantity),
    ).where(CartonInventoryMovement.order_line_id.in_(line_ids),
            CartonInventoryMovement.source_type == "ORDER_REPLENISHMENT")
        .group_by(CartonInventoryMovement.order_line_id))}


def _posted_linked_samples(db, line_ids):
    if not line_ids:
        return
    events = list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.event_type == "SUPPLIER_SAMPLE_LINKED",
        CartonAuditEvent.entity_type == "carton_order_line",
        CartonAuditEvent.entity_id.in_(line_ids))))
    links = [(event, json.loads(event.detail_json).get("sample_receipt_line_id")) for event in events]
    samples = {sample.id: (sample, receipt) for sample, receipt in db.execute(select(CartonReceiptLine, CartonReceipt)
        .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(CartonReceiptLine.id.in_({sample_id for _, sample_id in links if sample_id})))} if links else {}
    for event, sample_id in links:
        sample, receipt = samples.get(sample_id, (None, None))
        if sample and receipt and sample.factory_id == event.factory_id == receipt.factory_id \
                and sample.source_type == "AD_HOC" and receipt.status == "POSTED":
            yield event.entity_id, sample


def fulfilled_by_line(db, line_ids):
    from app.services.carton_procurement import _posted_received_by_line, quantity
    received = _posted_received_by_line(db, line_ids)
    # A later formal order may reconcile an already-posted sample receipt. The
    # original AD_HOC receipt and inbound remain immutable and are counted once.
    for line_id, sample in _posted_linked_samples(db, line_ids):
        received[line_id] = received.get(line_id, Decimal(0)) + sample.effective_quantity
    replaced = replenished_by_line(db, line_ids)
    result = {line_id: quantity(received.get(line_id, Decimal(0)) - replaced.get(line_id, Decimal(0))) for line_id in line_ids}
    if any(value < 0 for value in result.values()):
        raise HTTPException(409, "有效收料不能少于已提交补单的出库数量，请先核对补单和收料记录")
    return result


def posted_receipt_sources(db, line_ids):
    result = defaultdict(dict)
    for line_id, receipt_line_id, qty in db.execute(select(
        CartonReceiptLine.order_line_id, CartonReceiptLine.id, CartonReceiptLine.effective_quantity,
    ).join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id).where(
        CartonReceipt.status == "POSTED", CartonReceiptLine.order_line_id.in_(line_ids),
    )):
        result[line_id][receipt_line_id] = str(qty)
    for line_id, sample in _posted_linked_samples(db, line_ids):
        result[line_id][sample.id] = str(sample.effective_quantity)
    return dict(result)


def protected_by_line(db, line_ids):
    """Keep pre-replacement fulfillment protected without counting replacements twice."""
    result = fulfilled_by_line(db, line_ids)
    active_sources = posted_receipt_sources(db, line_ids)
    issue_ids = select(CartonInventoryMovement.source_id).where(
        CartonInventoryMovement.order_line_id.in_(line_ids),
        CartonInventoryMovement.source_type == "ORDER_REPLENISHMENT",
    )
    for raw in db.scalars(select(CartonPurchaseOrderIssue.snapshot_json).where(CartonPurchaseOrderIssue.id.in_(issue_ids))):
        evidence = json.loads(raw).get("replenishment", {})
        for line_id, value in evidence.get("protected_quantities", {}).items():
            if line_id in result:
                reversed_quantity = sum((Decimal(qty) for source_id, qty in evidence.get("receipt_sources", {}).get(line_id, {}).items()
                                         if source_id not in active_sources.get(line_id, {})), Decimal(0))
                result[line_id] = max(result[line_id], Decimal(value) - reversed_quantity)
    return result


def replenish_order(db, order_no, payload, user):
    from app.services import carton_procurement as core
    factory = core.require_carton_factory(payload.factory_id)
    core._lock_receipt_factory(db, factory)
    scope = json.dumps([factory, user.id, payload.request_id], separators=(",", ":"))
    event_id = "CAE-REPL-" + hashlib.sha256(scope.encode()).hexdigest()
    body = payload.model_dump(mode="json", exclude={"request_id"})
    for line in body["lines"]:
        line["quantity"] = format(core.quantity(Decimal(line["quantity"])), "f")
    fingerprint = hashlib.sha256(json.dumps([order_no, body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous:
        evidence = json.loads(previous.detail_json)["request"]
        if evidence["fingerprint"] != fingerprint:
            raise HTTPException(409, "本次提交标识已用于不同的补单内容，请核对原补单")
        return CartonReplenishmentOut.model_validate(evidence["result"])

    order = core.get_order_by_no(db, factory, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(409, "订单已更新，请刷新后重新核对补单")
    if order.status not in {"PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(409, "补单仅适用于已经入库的有效订单")
    core._require_order_complete(db, order)
    lines = core._order_lines(db, order.id)
    line_ids = {line.id for line in lines}
    from app.services.carton_replenishment_receipts import legacy_review_lines
    if legacy_review_lines(db, factory, list(line_ids)):
        raise HTTPException(409, "该订单有未关联补单的历史收料，请先核对并更正关联后再补单")
    totals = defaultdict(Decimal)
    seen = set()
    for item in payload.lines:
        if item.order_line_id not in line_ids:
            raise HTTPException(422, "补单纸品不属于当前订单")
        key = (item.order_line_id, item.location_id)
        if key in seen:
            raise HTTPException(422, "同一纸品仓位不能重复填写")
        seen.add(key)
        totals[item.order_line_id] += item.quantity
    fulfilled = fulfilled_by_line(db, list(line_ids))
    protected = protected_by_line(db, list(line_ids))
    if any(qty > fulfilled[line_id] for line_id, qty in totals.items()):
        raise HTTPException(409, "补单数量不能超过该纸品当前有效收料数量")

    issues = core._purchase_order_issues(db, order.id)
    latest = issues[0] if issues else None
    pending_type, _, _, snapshot = core._purchase_order_pending_change(order, lines, latest)
    if pending_type != "NONE":
        raise HTTPException(409, "原订单有尚未发行的数量或交期变更，请先发行后再补单")
    sequence = (latest.issue_sequence if latest else 0) + 1
    number = 1 + sum(bool(core._purchase_order_snapshot(issue).get("replenishment")) for issue in issues)
    document_no = f"{order.order_no}-B{number:02d}"
    issue_id = "CPOI-" + uuid4().hex
    responsibility_label = "我方问题" if payload.responsibility == "OWN" else "供应商问题"
    reason = f"补单换补；责任：{responsibility_label}" + (f"；{payload.reason}" if payload.reason else "")
    movement_ids = []
    for item in payload.lines:
        movement, _, _ = core._prepare_inventory_movement(db, CartonInventoryMovementCreate(
            factory_id=factory, request_id=payload.request_id, order_line_id=item.order_line_id,
            movement_type="OUTBOUND", quantity=item.quantity, location_id=item.location_id,
            document_no=document_no, issue_kind="OTHER", reason=reason,
        ), user)
        movement.source_type = "ORDER_REPLENISHMENT"
        movement.source_id = issue_id
        movement.source_line_id = movement.id
        movement_ids.append(movement.id)
        db.flush()

    # Keep the ordinary order baseline unchanged. B documents execute replacement
    # quantities only; subsequent A/R/C issues still compare ordinary demand.
    snapshot["before_product_quantity"] = snapshot["after_product_quantity"]
    snapshot["product_quantity_delta"] = "0" if order.product_order_quantity is not None else None
    snapshot["before_due_date"] = snapshot["after_due_date"]
    snapshot["replenishment"] = {"responsibility": payload.responsibility, "responsibility_label": responsibility_label,
                                  "settlement_policy": "SUPPLIER_FREE" if payload.responsibility == "SUPPLIER" else "OWN_PAY_ON_RECEIPT",
                                  "reason": payload.reason, "movement_ids": movement_ids,
                                  "protected_quantities": {key: str(value) for key, value in protected.items() if key in totals},
                                  "receipt_sources": posted_receipt_sources(db, list(totals))}
    for line in snapshot["lines"]:
        line["before_required_quantity"] = line["after_required_quantity"]
        line["required_quantity_delta"] = str(totals.get(line["id"], Decimal(0)))
    order.status = "PARTIALLY_RECEIVED"
    order.revision += 1
    timestamp = core.now_text()
    order.updated_at, order.updated_by, order.updated_by_name = timestamp, user.id, user.display_name
    snapshot["order"]["revision"] = order.revision
    snapshot["order"]["status"] = order.status
    issue = CartonPurchaseOrderIssue(
        id=issue_id, factory_id=factory, order_id=order.id, order_no=order.order_no,
        document_no=document_no, document_type="ADJUSTMENT", issue_sequence=sequence,
        source_order_revision=order.revision, before_product_quantity=order.product_order_quantity,
        after_product_quantity=order.product_order_quantity,
        product_quantity_delta=Decimal(0) if order.product_order_quantity is not None else None,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        generated_by=user.id, generated_by_name=user.display_name, generated_at=timestamp,
    )
    db.add(issue)
    db.flush()
    result = CartonReplenishmentOut(order=core.order_out(db, order), issue=core._purchase_order_issue_out(issue))
    event = core._audit(db, user, factory, "ORDER_REPLENISHED", "carton_order", order.id,
        {"order_no": order_no, "document_no": document_no, "responsibility": responsibility_label,
         "reason": payload.reason, "quantities": {key: str(value) for key, value in totals.items()},
         "movement_ids": movement_ids, "issue_id": issue_id,
         "request": {"fingerprint": fingerprint, "result": result.model_dump(mode="json")}})
    event.id = event_id
    db.commit()
    return result
