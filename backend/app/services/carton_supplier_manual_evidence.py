"""First supplier original for a manually received batch; never repost inventory."""
import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.auth import SystemNotification
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt, CartonReceiptLine
from app.models.carton_special_requests import UnifiedDelivery
from app.services import carton_price_review as prices, carton_procurement as core

EVENT = "SUPPLIER_ORIGINAL_PRICE_ADOPTED"
DOCUMENT_EVENT = "MANUAL_DELIVERY_ORIGINAL_ATTACHED"


def updates(db, factory):
    return {json.loads(event.detail_json)["receipt_line_id"]: dict(json.loads(event.detail_json), occurred_at=event.created_at)
        for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence))}


def adopt(db, user, receipt_line, *, supplier_id, shipment_id, shipment_line_id, source_kind, raw_price, evidence, free=False):
    """Set payable evidence only. Frozen manual receipt and stock valuation survive."""
    from app.services.carton_supplier_settlement import receipt_guard, money, _posting_date
    receipt = db.get(CartonReceipt, receipt_line.receipt_id)
    if receipt.status != "POSTED":
        raise HTTPException(409, "原收料已冲销或未入库，请先处理原记录")
    if receipt.factory_id != receipt_line.factory_id or receipt.supplier_id != supplier_id:
        raise HTTPException(409, "供应商与原收料不一致")
    receipt_guard(db, receipt)
    if receipt_line.effective_quantity <= 0:
        return None
    try:
        value = Decimal(str(raw_price)) if raw_price not in (None, "") else None
        if value is not None and (not value.is_finite() or value < 0 or value >= Decimal("1000000000000") or value.normalize().as_tuple().exponent < -6):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "供应商原单价无效") from None
    if value is None or value == 0 and not free:
        return None  # A missing price or unclassified zero is not a supplier quotation.
    previous = updates(db, receipt.factory_id).get(receipt_line.id)
    if previous:
        if previous["evidence"] != evidence or Decimal(previous["supplier_unit_price"]) != value:
            raise HTTPException(409, "已采用过供应商原价，后续变价请使用价格更正流程")
        return previous
    if receipt_line.id in prices.applied_corrections(db, receipt.factory_id):
        raise HTTPException(409, "该批次已有已生效价格更正，请沿原更正流程核对")
    review = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == receipt_line.id,
        CartonPriceReview.factory_id == receipt.factory_id))
    if review and prices.free_contract(db, review) and value != 0:
        raise HTTPException(409, "免费赠送或供应商责任补货不能转为收费")
    old = review.proposed_unit_price if review else receipt_line.unit_price if receipt_line.unit_price > 0 else None
    if review is None:
        review = CartonPriceReview(id="CPR-" + uuid4().hex, factory_id=receipt.factory_id, supplier_id=supplier_id,
            receipt_line_id=receipt_line.id, source_kind=source_kind, shipment_id=shipment_id,
            shipment_line_id=shipment_line_id, revision=0, created_by=user.id)
        db.add(review)
    review.original_unit_price = value
    review.proposed_unit_price = value
    review.status = "CONFIRMED"
    review.revision += 1
    review.updated_by = user.id
    review.updated_at = core.now_text()
    review.reason = "后补供应商原单已匹配原入库批次，自动采用供应商价；库存原始成本记录保留"
    detail = dict(receipt_line_id=receipt_line.id, receipt_id=receipt.id, document_no=receipt.delivery_note_no,
        manual_unit_price=str(old) if old is not None else None, supplier_unit_price=str(value), quantity=str(receipt_line.effective_quantity),
        amount_difference=str(money(receipt_line.effective_quantity * (value - old))) if old is not None else None, currency=receipt_line.currency,
        period=(receipt.acceptance_date or _posting_date(receipt.confirmed_at))[:7], evidence=evidence,
        revision=review.revision, status=review.status, original_free_confirmed=free, reason=review.reason)
    event = core._audit(db, user, receipt.factory_id, EVENT, "carton_price_review", review.id, detail)
    if old != value:
        db.add(SystemNotification(id="carton-price-original:" + event.id, target_user_id="",
            target_permission="carton_procurement:receipt_write", target_factory_id=receipt.factory_id,
            target_department="pmc-warehouse", type="carton_supplier_price_adopted",
            title=f"送货单 {receipt.delivery_note_no[:90]} 已采用供应商单价",
            message=f"{detail['period']} 手工价 {old if old is not None else '待核实'} → 供应商价 {value} {receipt_line.currency}/{receipt_line.unit}；"
                + (f"货款差额 {detail['amount_difference']}。" if old is not None else "已补齐原缺失价格。") + "沿用原入库数量，请仓库知悉。",
            payload_json=json.dumps(dict(review_id=review.id, factory_id=receipt.factory_id, period=detail["period"]), ensure_ascii=False),
            status="unread", created_at=core.now_text(), read_at="", handled_at=""))
    db.flush()
    return detail


def manual_group(db, factory, supplier, note):
    groups = list(db.scalars(select(UnifiedDelivery).where(UnifiedDelivery.factory_id == factory,
        UnifiedDelivery.supplier_id == supplier, UnifiedDelivery.delivery_note_no == note)))
    return next((group for group in groups if json.loads(group.children_json).get("source_origin") == "WAREHOUSE_MANUAL"), None)


def match(db, user, group, rows, day):
    from app.services.carton_unified_deliveries import project
    from app.services.carton_material_identity import material_conflicts
    from app.services.carton_procurement_imports import _dongkang_identity
    from app.services.carton_supplier_settlement import receipt_guard
    data = project(db, user, group.factory_id, group.id, external=True)
    if day != group.delivery_date or len(rows) != len(data["lines"]) or not rows:
        raise HTTPException(409, "后补原单的日期、纸品行数与原手工收料不一致，请核对原单")
    if data["status"] != "RECEIVED" or data["requires_correction"]:
        raise HTTPException(409, "原手工收料尚未完成或已冲销，请先处理原记录")
    for batch in data["receipts"]:
        receipt = db.get(CartonReceipt, batch.get("receipt_id") or batch.get("id"))
        if not receipt or receipt.status != "POSTED" or receipt.factory_id != group.factory_id or receipt.supplier_id != group.supplier_id:
            raise HTTPException(409, "原手工收料状态或来源异常，请先核实")
        receipt_guard(db, receipt)  # Includes all-rejected batches without a price review.
    used, result = set(), []
    for row in rows:
        if any(not row.get(key) or row[key] == "待复核" for key in ("paper_quality", "specification")):
            raise HTTPException(409, "后补原单缺少纸质或规格，不能自动匹配")
        matches = [paper for paper in data["lines"] if paper["id"] not in used
            and not material_conflicts(row, paper, dongkang_delivery=True)
            and all(_dongkang_identity(row.get(key)) == _dongkang_identity(paper.get(key)) for key in ("contract_no", "item_no"))
            and row.get("unit") == paper.get("unit") and paper.get("currency", "CNY") == "CNY"
            and Decimal(str(row["delivered_quantity"])) == Decimal(str(paper["quantity"]))]
        if len(matches) != 1:
            raise HTTPException(409, "后补原单与原收料的纸品、合同、货号、数量或单位不一致，或存在重复纸品，不能自动关联")
        paper = matches[0]; used.add(paper["id"])
        reviews = list(db.scalars(select(CartonPriceReview).where(CartonPriceReview.factory_id == group.factory_id,
            CartonPriceReview.supplier_id == group.supplier_id, CartonPriceReview.shipment_line_id == paper["id"])))
        for review in reviews:
            receipt = db.get(CartonReceipt, db.get(CartonReceiptLine, review.receipt_line_id).receipt_id)
            if receipt.status != "POSTED":
                raise HTTPException(409, "原收料包含冲销记录，请沿原验收记录核实")
            receipt_guard(db, receipt)
        if Decimal(str(paper.get("effective_quantity", "0"))) > 0 and not reviews:
            raise HTTPException(409, "原收料价格关联不完整，请核实后补证")
        result.append((paper, row, reviews))
    return result


def attach(db, user, group, rows, day, evidence):
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    old = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == group.factory_id,
        CartonAuditEvent.event_type == DOCUMENT_EVENT, CartonAuditEvent.entity_id == group.id))
    if old:
        saved = json.loads(old.detail_json)
        if saved["evidence"] != evidence:
            raise HTTPException(409, "此手工收料已补供应商原单，后续更改请沿原价格更正流程处理")
        return dict(id=group.id, delivery_note_no=group.delivery_note_no, linked_existing_receipt=True)
    ensure_evidence_open(db, group.factory_id, group.supplier_id, day)
    pairs = match(db, user, group, rows, day)
    for paper, row, reviews in pairs:
        for review in reviews:
            adopt(db, user, db.get(CartonReceiptLine, review.receipt_line_id), supplier_id=group.supplier_id,
                shipment_id=review.shipment_id, shipment_line_id=review.shipment_line_id, source_kind=review.source_kind,
                raw_price=row.get("unit_price"), evidence=evidence, free=False)
    core._audit(db, user, group.factory_id, DOCUMENT_EVENT, "carton_unified_delivery", group.id,
        {"evidence": evidence, "rows": [{"shipment_line_id": paper["id"], **row} for paper, row, _ in pairs]})
    return dict(id=group.id, delivery_note_no=group.delivery_note_no, linked_existing_receipt=True)
