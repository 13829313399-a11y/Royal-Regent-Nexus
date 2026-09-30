"""Supplier-scoped collaboration. All mutations use the existing carton factory lock."""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from app.services.carton_purchase_batches import group_purchase_documents, load_purchase_batch, purchase_batch
from app.models.carton_mark import CartonMarkDocument, CartonMarkTemplate
from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonSupplier, CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine, CartonAuditEvent
from app.models.carton_supplier_portal import SupplierCommitment, SupplierShipment, SupplierShipmentLine, SupplierShipmentUnmatchedLine, SupplierAttachment
from app.schemas.carton_supplier_portal import CommitmentSave, BatchCommitmentSave, ShipmentCreate, ShipmentReceive, SampleReceiptLink, ShipmentLineLink, SupplierMarkTemplateOut, SupplierDocumentExport
from app.schemas.carton_procurement import CartonReceiptCreate, CartonReceiptLineCreate, CartonReceiptConfirmRequest
from app.services.auth import AuthContext, authorization_decision, has_permission_in_scope
from app.services import carton_positions as positions
from app.services import carton_supplier_notifications as shipment_notifications
from app.services.carton_procurement_imports import _dongkang_identity, _dimension_identity
from app.services.carton_material_identity import material_conflicts, dimension_identity
from app.services.carton_procurement import (CARTON_DEPARTMENTS, require_carton_factory, _lock_receipt_factory,
    _purchase_order_issues, _purchase_order_snapshot, _purchase_order_pending_change, get_order_lines,
    fulfilled_by_line, _pending_received_by_line, _refresh_order_statuses, _audit, now_text, _create_receipt, confirm_receipt)

OPEN_STATES = {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}
VISIBLE_STATES = OPEN_STATES | {"COMPLETED", "CANCELLED"}
MAX_FILE = 10 * 1024 * 1024
TABLES = ("carton_supplier_members", "carton_supplier_commitments", "carton_supplier_shipments", "carton_supplier_shipment_lines", "carton_supplier_unmatched_lines", "carton_supplier_attachments")


def _sample_link_id(receipt_line_id):
    return f"CAE-SAMPLE-LINK-{receipt_line_id}"


def _dimension_unit(value):
    match = re.search(r"(inch|in|英寸|cm|厘米)\s*$", str(value or ""), re.IGNORECASE)
    if not match:
        return ""
    return "in" if match.group(1).casefold() in {"inch", "in", "英寸"} else "cm"


def internal_permission(user, factory, *permissions):
    factory = require_carton_factory(factory)
    for permission in permissions:
        if not any(has_permission_in_scope(user, permission, factory, dept) for dept in CARTON_DEPARTMENTS):
            raise HTTPException(403, "没有当前厂区的供应商协同管理权限")
    return factory


def fixed_supplier(db, factory):
    supplier = db.scalar(select(CartonSupplier).where(CartonSupplier.factory_id == factory,
        CartonSupplier.supplier_code == "HEYUAN-DONGKANG", CartonSupplier.status == "ACTIVE"))
    if not supplier:
        raise HTTPException(409, "当前厂区未配置有效的河源东康供应商")
    return supplier


def supplier_factories(db, user):
    """Dongkang service factories with issued orders, gated by the global module permission."""
    if not supplier_permission(user, "carton_supplier:read", "*"):
        return []
    suppliers = db.scalars(select(CartonSupplier).where(CartonSupplier.supplier_code == "HEYUAN-DONGKANG",
        CartonSupplier.status == "ACTIVE").order_by(CartonSupplier.factory_id)).all()
    return [supplier for supplier in suppliers if supplier_permission(
        user, "carton_supplier:read", supplier.factory_id) and db.scalar(
        select(CartonOrder.id).join(CartonPurchaseOrderIssue, and_(
            CartonPurchaseOrderIssue.order_id == CartonOrder.id,
            CartonPurchaseOrderIssue.factory_id == CartonOrder.factory_id)).where(
                CartonOrder.factory_id == supplier.factory_id,
                CartonOrder.supplier_id == supplier.id,
                CartonOrder.status.in_(VISIBLE_STATES)).limit(1))]


def supplier_permission(user, permission, factory):
    # This module uses the evaluated IAM decision even during the legacy rollout;
    # its dedicated global overrides never change authorization in other modules.
    return (authorization_decision(user, permission, "*", "*")[0]
        and authorization_decision(user, permission, factory, "*")[0])


def supplier_access(db, user, factory, permission="carton_supplier:read"):
    factory = require_carton_factory(factory)
    supplier = next((item for item in supplier_factories(db, user) if item.factory_id == factory), None)
    if supplier is None or not supplier_permission(user, permission, factory):
        raise HTTPException(403, "账号无权访问此厂区的供应商订单")
    return supplier


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def latest_issue(db, order):
    return next((issue for issue in _purchase_order_issues(db, order.id)
        if not _purchase_order_snapshot(issue).get("replenishment")), None)


def acceptance_summary(db, order, lines):
    """Internal read projection of supplier confirmation for the current ordinary issue."""
    issue = latest_issue(db, order)
    positive_ids = [line.id for line in lines if line.required_quantity > 0]
    result = dict(status="NOT_ISSUED", label="尚未发送供应商",
        issue_id=issue.id if issue else "", document_no=issue.document_no if issue else "",
        total_line_count=len(positive_ids), accepted_line_count=0, accepted_at="")
    if order.status == "CANCELLED":
        result.update(status="CANCELLED", label="订单已取消")
    elif not issue or order.status not in VISIBLE_STATES:
        pass
    elif _purchase_order_pending_change(order, lines, issue)[0] != "NONE":
        result.update(status="PENDING_CHANGE", label="变更待发行")
    elif not positive_ids:
        result.update(status="NOT_REQUIRED", label="无需接单")
    else:
        commitments = list(db.scalars(select(SupplierCommitment).where(
            SupplierCommitment.factory_id == order.factory_id,
            SupplierCommitment.issue_id == issue.id,
            SupplierCommitment.order_line_id.in_(positive_ids))).all())
        accepted = len(commitments)
        status, label = ("ACCEPTED", "供应商已接单") if accepted == len(positive_ids) else (
            ("PARTIAL", "供应商部分接单") if accepted else ("PENDING", "供应商待接单"))
        result.update(status=status, label=label, accepted_line_count=accepted,
            accepted_at=max((row.accepted_at for row in commitments), default=""))
    return result


def supplier_order(db, order_id, factory, supplier_id):
    order = db.scalar(select(CartonOrder).where(CartonOrder.id == order_id, CartonOrder.factory_id == factory,
        CartonOrder.supplier_id == supplier_id, CartonOrder.status.in_(VISIBLE_STATES)))
    if order is None or latest_issue(db, order) is None:
        raise HTTPException(404, "未找到可访问的已下单订单")
    return order


def _mark_identity(customer_name, po, item, contract_number):
    return tuple(" ".join(value.strip().split()).casefold() for value in
        (customer_name, po, item, contract_number))


def _visible_supplier_mark_templates(db, user, factory):
    supplier = supplier_access(db, user, factory)
    orders = db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.supplier_id == supplier.id,
        CartonOrder.status.in_(OPEN_STATES | {"COMPLETED"}))).all()
    issued_identities = set()
    for order in orders:
        issue = latest_issue(db, order)
        if issue is None:
            continue
        header = _purchase_order_snapshot(issue).get("order", {})
        if not isinstance(header, dict) or header.get("supplier_id") != supplier.id:
            continue
        issued_identities.add(_mark_identity(str(header.get("customer_name") or ""),
            str(header.get("customer_po") or header.get("contract_no") or ""),
            str(header.get("item_no") or ""), str(header.get("contract_no") or "")))
    if not issued_identities:
        return []
    candidates = db.scalars(select(CartonMarkTemplate).where(
        CartonMarkTemplate.factory_id == factory)).all()
    latest_by_identity = {}
    for template in candidates:
        identity = _mark_identity(template.customer_name, template.po, template.item,
            template.contract_number)
        if identity not in issued_identities:
            continue
        previous = latest_by_identity.get(identity)
        if previous is None or (template.version, template.created_at, template.id) > (
            previous.version, previous.created_at, previous.id):
            latest_by_identity[identity] = template
    return sorted((template for template in latest_by_identity.values()
        if not template.is_archived and (template.check_status == "核对通过" or template.manual_released_at)),
        key=lambda template: (template.created_at, template.id), reverse=True)


def supplier_mark_templates(db, user, factory):
    templates = _visible_supplier_mark_templates(db, user, factory)
    if not templates:
        return []
    documents = {}
    for template_id, kind, filename in db.execute(select(
        CartonMarkDocument.template_id, CartonMarkDocument.kind, CartonMarkDocument.file_name).where(
        CartonMarkDocument.factory_id == factory,
        CartonMarkDocument.template_id.in_([template.id for template in templates]))):
        documents.setdefault(template_id, {})[kind] = filename
    return [SupplierMarkTemplateOut(id=template.id, customer_name=template.customer_name,
        po=template.po, item=template.item, contract_number=template.contract_number,
        version=template.version, check_status=template.check_status,
        manual_released=bool(template.manual_released_at),
        excel_file_name=documents[template.id]["source_excel"],
        pdf_file_name=documents[template.id]["print_pdf"], created_at=template.created_at)
        for template in templates if {"source_excel", "print_pdf"} <= documents.get(template.id, {}).keys()]


def supplier_mark_document(db, user, factory, template_id, kind):
    if kind not in {"source_excel", "print_pdf"}:
        raise HTTPException(422, "箱唛文档类型无效")
    if not any(template.id == template_id for template in _visible_supplier_mark_templates(db, user, factory)):
        raise HTTPException(404, "未找到可查看的箱唛资料")
    available_kinds = set(db.scalars(select(CartonMarkDocument.kind).where(
        CartonMarkDocument.factory_id == factory,
        CartonMarkDocument.template_id == template_id)).all())
    if not {"source_excel", "print_pdf"} <= available_kinds:
        raise HTTPException(404, "箱唛文档不完整")
    document = db.scalar(select(CartonMarkDocument).where(
        CartonMarkDocument.factory_id == factory,
        CartonMarkDocument.template_id == template_id, CartonMarkDocument.kind == kind))
    if document is None:
        raise HTTPException(404, "箱唛文档不存在")
    return document


def executable(db, order, issue_id):
    if order.status not in OPEN_STATES:
        raise HTTPException(409, "订单当前状态不允许接单或发货")
    issue = latest_issue(db, order)
    if not issue or issue.id != issue_id:
        raise HTTPException(409, "采购版本已变更，请刷新后重新确认接单")
    if _purchase_order_pending_change(order, get_order_lines(db, order.id), issue)[0] != "NONE":
        raise HTTPException(409, "订单存在未发行变更，旧承诺暂停执行，请等待内部发行后重新接单")
    return issue


def _accepted_reservation(shipment, paper):
    original_id = json.loads(paper.snapshot_json).get("original_unmatched_line_id")
    accepted = next((item for item in json.loads(shipment.acceptance_json or "{}").get("lines", [])
        if item["shipment_line_id"] in {paper.id, original_id}), {})
    return max(Decimal(0), Decimal(str(accepted.get("received_quantity") or 0))
        - sum(Decimal(str(accepted.get(key) or 0)) for key in ("damaged_quantity", "rejected_quantity", "unusable_quantity")))


def outstanding(db, line_ids):
    if not line_ids:
        return {}
    rows = db.execute(select(SupplierShipmentLine, SupplierShipment, CartonReceipt.status)
        .join(SupplierShipment, SupplierShipment.id == SupplierShipmentLine.shipment_id)
        .outerjoin(CartonReceipt, CartonReceipt.id == SupplierShipment.receipt_id)
        .where(or_(SupplierShipment.status == "SENT", and_(SupplierShipment.status == "RECEIVED", CartonReceipt.status == "REVERSED")),
            SupplierShipmentLine.order_line_id.in_(line_ids))).all()
    result = {}
    for paper, shipment, receipt_status in rows:
        reserved = paper.quantity
        if receipt_status == "REVERSED":
            # Reserve the invalidated effective acceptance, not previously rejected/short quantities.
            reserved = _accepted_reservation(shipment, paper)
        result[paper.order_line_id] = result.get(paper.order_line_id, Decimal(0)) + reserved
    return result


def _shipment_sources(db, shipment):
    formal = list(db.scalars(select(SupplierShipmentLine).where(
        SupplierShipmentLine.shipment_id == shipment.id).order_by(SupplierShipmentLine.id)).all())
    linked = {json.loads(line.snapshot_json).get("original_unmatched_line_id") for line in formal}
    unmatched = [line for line in db.scalars(select(SupplierShipmentUnmatchedLine).where(
        SupplierShipmentUnmatchedLine.shipment_id == shipment.id).order_by(SupplierShipmentUnmatchedLine.id)).all()
        if line.id not in linked]
    return formal, unmatched


def blocked_replacement_lines(db, factory, line_ids):
    from app.services.carton_replenishment_receipts import options_by_line, legacy_review_lines
    return set(options_by_line(db, factory, line_ids)) | legacy_review_lines(db, factory, line_ids)


def attachment_out(row):
    return {key: getattr(row, key) for key in ("id", "filename", "version", "size", "sha256", "created_at")}


def order_out(db, order, *, internal=False):
    issue = latest_issue(db, order)
    if not issue and not internal:
        return None
    snapshot = _purchase_order_snapshot(issue) if issue else _purchase_order_pending_change(order, get_order_lines(db, order.id), None)[3]
    header = snapshot.get("order", {})
    current_lines = get_order_lines(db, order.id)
    ids = [line.id for line in current_lines]
    fulfilled = fulfilled_by_line(db, ids)
    pending = _pending_received_by_line(db, ids)
    shipped = outstanding(db, ids)
    blocked = blocked_replacement_lines(db, order.factory_id, ids)
    changed = _purchase_order_pending_change(order, current_lines, issue)[0] != "NONE"
    result = {key: header.get(key, "") for key in ("order_no", "customer_name", "contract_no", "customer_po", "item_no", "product_name")}
    result.update(id=order.id, status=order.status, revision=order.revision,
        issue_id=issue.id if issue else "", document_no=issue.document_no if issue else "尚未发行",
        order_date=header.get("order_date") or order.order_date,
        planned_date=snapshot.get("after_due_date", ""), awaiting_issue=changed, lines=[])
    if internal:
        from app.services.carton_order_split import plans
        result["customer_code"] = order.customer_code
        result["split_records"] = plans(db, order.factory_id, order.id)
    for item in snapshot.get("lines", []):
        line_id = str(item["id"])
        required = Decimal(str(item["after_required_quantity"]))
        commitment = db.get(SupplierCommitment, line_id)
        accepted = bool(issue and commitment and commitment.issue_id == issue.id and not changed)
        line = {key: item.get(key, "") for key in ("id", "line_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "unit")}
        line.update(child_no=f"{order.order_no}/{item['line_no']:02d}", required_quantity=str(required),
            received_quantity=str(fulfilled.get(line_id, 0)), in_transit_quantity=str(shipped.get(line_id, 0)),
            remaining_to_ship=str(max(Decimal(0), required - fulfilled.get(line_id, 0) - pending.get(line_id, 0) - shipped.get(line_id, 0))),
            shipping_blocked_reason="此纸品有补单待核对，请联系内部仓库按原补单流程处理" if line_id in blocked else "",
            accepted=accepted, commitment_revision=commitment.revision if commitment else 0,
            promised_date=commitment.promised_date if commitment else "")
        if internal:
            line.update(unit_price=item.get("unit_price", "0"), currency=item.get("currency", "CNY"))
        result["lines"].append(line)
    result["attachments"] = [attachment_out(row) for row in db.scalars(select(SupplierAttachment).where(
        SupplierAttachment.order_id == order.id, SupplierAttachment.factory_id == order.factory_id).order_by(SupplierAttachment.created_at.desc())).all()]
    return result


def workspace(db, user, factory, *, internal=False):
    if internal:
        internal_permission(user, factory, "carton_procurement:read")
        supplier_id = fixed_supplier(db, factory).id
    else:
        supplier_id = supplier_access(db, user, factory).id
    orders = db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory, CartonOrder.supplier_id == supplier_id,
        CartonOrder.deleted_at.is_(None),
        CartonOrder.status.in_(VISIBLE_STATES | {"DRAFT", "CONFIRMED"} if internal else VISIBLE_STATES)).order_by(CartonOrder.due_date, CartonOrder.order_no)).all()
    result = [order_out(db, row, internal=internal) for row in orders]
    shipments = db.scalars(select(SupplierShipment).where(SupplierShipment.factory_id == factory,
        SupplierShipment.supplier_id == supplier_id).order_by(SupplierShipment.created_at.desc())).all()
    return {"factory_id": factory, "supplier_name": db.get(CartonSupplier, supplier_id).supplier_name,
        "orders": [row for row in result if row], "shipments": [shipment_out(db, row, internal=internal) for row in shipments]}


def shipment_out(db, row, *, internal=False):
    result = {key: getattr(row, key) for key in ("id", "delivery_note_no", "delivery_date", "status", "revision", "created_at", "confirmed_at")}
    receipt = db.get(CartonReceipt, row.receipt_id) if row.receipt_id else None
    correction = bool(receipt and receipt.status == "REVERSED")
    result["requires_correction"] = correction
    if correction:
        result["status"] = "RECEIPT_REVERSED"
    result["lines"] = []
    result["source_filename"] = ""
    result["source_sha256"] = ""
    formal, unmatched = _shipment_sources(db, row)
    for line in formal:
        snapshot = json.loads(line.snapshot_json)
        source_file = snapshot.get("source_file") or {}
        result["source_filename"] = result["source_filename"] or source_file.get("filename", "")
        result["source_sha256"] = result["source_sha256"] or source_file.get("sha256", "")
        item = {key: snapshot.get(key, "") for key in ("order_no", "contract_no", "customer_po", "item_no", "customer_name", "child_no", "packaging_type", "paper_quality", "specification", "unit")}
        item.update(id=line.id, order_line_id=line.order_line_id, quantity=str(line.quantity), source_type="FORMAL_ORDER")
        if internal:
            item.update(unit_price=snapshot.get("unit_price", "0"),
                delivery_unit_price=snapshot.get("delivery_unit_price"), currency=snapshot.get("currency", "CNY"))
            original = snapshot.get("original_source_material")
            if original:
                item["source_material"] = {key: original.get(key) for key in ("packaging_type", "paper_quality", "specification", "source_sheet", "source_row")}
                if original.get("packaging_type_explicit") is False:
                    item["source_material"]["packaging_type"] = ""
        result["lines"].append(item)
    for line in unmatched:
        snapshot = json.loads(line.snapshot_json)
        source_file = snapshot.get("source_file") or {}
        result["source_filename"] = result["source_filename"] or source_file.get("filename", "")
        result["source_sha256"] = result["source_sha256"] or source_file.get("sha256", "")
        item = {key: snapshot.get(key, "") for key in ("order_no", "contract_no", "customer_po", "item_no", "customer_name", "child_no", "packaging_type", "paper_quality", "specification", "unit")}
        item.update(id=line.id, order_line_id=None, quantity=str(line.quantity), source_type="AD_HOC_REVIEW")
        if internal:
            item.update(unit_price=str(snapshot.get("unit_price") or "0"), currency="CNY")
        result["lines"].append(item)
    accepted = json.loads(row.acceptance_json or "{}")
    result["acceptance_date"] = accepted.get("acceptance_date")
    # Supplier sees actual quantities/discrepancies, never internal cost or warehouse IDs.
    result["acceptance_lines"] = [{key: item.get(key) for key in ("shipment_line_id", "received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity", "difference_reason", "no_order_decision")} for item in accepted.get("lines", [])]
    result["acceptance_history"] = []
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == row.factory_id,
        CartonAuditEvent.entity_type == "supplier_shipment", CartonAuditEvent.entity_id == row.id,
        CartonAuditEvent.event_type.in_({"SUPPLIER_SHIPMENT_RECEIVED", "SUPPLIER_SHIPMENT_NOT_RECEIVED"}))
        .order_by(CartonAuditEvent.sequence)).all()
    for event in events:
        detail = json.loads(event.detail_json)
        prior = db.get(CartonReceipt, detail.get("receipt_id")) if detail.get("receipt_id") else None
        acceptance = detail.get("acceptance") or {}
        result["acceptance_history"].append({"confirmed_at": event.created_at,
            "acceptance_date": acceptance.get("acceptance_date"), "status": prior.status if prior else ("NOT_RECEIVED" if event.event_type == "SUPPLIER_SHIPMENT_NOT_RECEIVED" else "RECEIVED"),
            "lines": [{key: item.get(key) for key in ("shipment_line_id", "received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity", "difference_reason", "no_order_decision")}
                for item in acceptance.get("lines", [])]})
    if correction:
        result["acceptance_date"] = None
        result["acceptance_lines"] = []  # Old acceptance is history, not current received quantity.
    if internal:
        result["receipt_id"] = row.receipt_id
        result["receipt_status"] = receipt.status if receipt else None
        receipt_lines = db.scalars(select(CartonReceiptLine).where(
            CartonReceiptLine.receipt_id == row.receipt_id,
            CartonReceiptLine.source_type == "AD_HOC").order_by(CartonReceiptLine.line_no)).all() if row.receipt_id else []
        result["sample_receipts"] = []
        for receipt_line in receipt_lines:
            link = db.scalar(select(CartonAuditEvent).where(
                CartonAuditEvent.id == _sample_link_id(receipt_line.id),
                CartonAuditEvent.factory_id == row.factory_id))
            result["sample_receipts"].append({
                "receipt_line_id": receipt_line.id, "customer_code": receipt_line.customer_code,
                "customer_name": receipt_line.customer_name, "contract_no": receipt_line.contract_no,
                "item_no": receipt_line.item_no, "packaging_type": receipt_line.packaging_type,
                "paper_quality": receipt_line.paper_quality, "specification": receipt_line.specification,
                "unit": receipt_line.unit, "quantity": str(receipt_line.effective_quantity),
                "linked_order_line_id": link.entity_id if link else "",
            })
    return result


def documents(db, user, factory):
    """Issued purchase snapshots and supplier-authored notes only, within one authorized factory."""
    supplier = supplier_access(db, user, factory)
    orders = db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.supplier_id == supplier.id,
        CartonOrder.status.in_(VISIBLE_STATES))).all()
    order_ids = [order.id for order in orders]
    result = []
    batches = {}
    if order_ids:
        issues = db.scalars(select(CartonPurchaseOrderIssue).where(
            CartonPurchaseOrderIssue.factory_id == factory,
            CartonPurchaseOrderIssue.order_id.in_(order_ids),
            CartonPurchaseOrderIssue.document_type != "LEGACY_BASELINE")
            .order_by(CartonPurchaseOrderIssue.generated_at.desc())).all()
        for issue in issues:
            snapshot = _purchase_order_snapshot(issue)
            batches[issue.id] = purchase_batch(issue)
            header = snapshot.get("order", {})
            result.append({
                "id": issue.id, "kind": "PURCHASE", "factory_id": factory,
                "document_no": issue.document_no, "document_type": issue.document_type,
                "date": issue.generated_at[:10], "created_at": issue.generated_at,
                "status": "已发行", "replenishment": bool(snapshot.get("replenishment")),
                "orders": [{
                    "order_no": issue.order_no, "customer_name": header.get("customer_name") or "",
                    "contract_no": header.get("contract_no") or "", "customer_po": header.get("customer_po") or "",
                    "item_no": header.get("item_no") or "", "product_name": header.get("product_name") or "",
                    "order_date": header.get("order_date") or "",
                    "planned_date": snapshot.get("after_due_date") or "",
                }],
                "lines": [{
                    "order_no": issue.order_no, "child_no": f"{issue.order_no}/{int(line.get('line_no', 0)):02d}",
                    "packaging_type": line.get("packaging_type", ""),
                    "paper_quality": line.get("paper_quality", ""),
                    "specification": line.get("specification", ""),
                    "unit": line.get("unit", ""),
                    "before_quantity": str(line.get("before_required_quantity", "0")),
                    "change_quantity": str(line.get("required_quantity_delta", "0")),
                    "quantity": str(line.get("after_required_quantity", "0")),
                } for line in snapshot.get("lines", [])],
            })
    result = group_purchase_documents(result, batches)
    shipments = db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory, SupplierShipment.supplier_id == supplier.id)
        .order_by(SupplierShipment.created_at.desc())).all()
    for shipment in shipments:
        visible = shipment_out(db, shipment)
        orders_by_no = {}
        for line in visible["lines"]:
            if not line["order_no"]:
                continue
            orders_by_no.setdefault(line["order_no"], {
                "order_no": line["order_no"], "customer_name": line["customer_name"],
                "contract_no": line["contract_no"], "customer_po": line["customer_po"],
                "item_no": line["item_no"], "product_name": "", "order_date": "", "planned_date": "",
            })
        accepted = {row["shipment_line_id"]: row for row in visible["acceptance_lines"]}
        result.append({
            "id": shipment.id, "kind": "DELIVERY", "factory_id": factory,
            "document_no": shipment.delivery_note_no, "document_type": "DELIVERY",
            "date": shipment.delivery_date, "created_at": shipment.created_at,
            "status": visible["status"], "replenishment": False,
            "source_filename": visible["source_filename"], "source_sha256": visible["source_sha256"],
            "orders": list(orders_by_no.values()),
            "unmatched_line_count": sum(line["source_type"] == "AD_HOC_REVIEW" for line in visible["lines"]),
            "lines": [{
                **{key: line.get(key, "") for key in (
                    "order_no", "child_no", "contract_no", "item_no", "customer_name",
                    "packaging_type", "paper_quality", "specification", "unit")},
                "quantity": line["quantity"],
                "received_quantity": str(accepted.get(line["id"], {}).get("received_quantity") or "0"),
            } for line in visible["lines"]],
        })
    if result:
        purchase_ids = [row["id"] for row in result if row["kind"] == "PURCHASE" and not row.get("is_batch")]
        batch_ids = [row["id"] for row in result if row.get("is_batch")]
        delivery_ids = [row["id"] for row in result if row["kind"] == "DELIVERY"]
        export_counts = {
            (entity_type, entity_id): count for entity_type, entity_id, count in db.execute(
                select(CartonAuditEvent.entity_type, CartonAuditEvent.entity_id,
                       func.count(CartonAuditEvent.id)).where(
                    CartonAuditEvent.factory_id == factory,
                    CartonAuditEvent.event_type == "SUPPLIER_DOCUMENT_EXPORTED",
                    or_(and_(CartonAuditEvent.entity_type == "carton_purchase_order_issue",
                            CartonAuditEvent.entity_id.in_(purchase_ids)),
                        and_(CartonAuditEvent.entity_type == "supplier_shipment",
                             CartonAuditEvent.entity_id.in_(delivery_ids)),
                        and_(CartonAuditEvent.entity_type == "carton_purchase_order_batch",
                             CartonAuditEvent.entity_id.in_(batch_ids))),
                ).group_by(CartonAuditEvent.entity_type, CartonAuditEvent.entity_id)).all()
        }
        for row in result:
            entity_type = _document_entity_type(row)
            row["export_count"] = export_counts.get((entity_type, row["id"]), 0)
    return sorted(result, key=lambda item: (item["created_at"], item["document_no"]), reverse=True)


def supplier_activity(db, user, factory):
    supplier = supplier_access(db, user, factory)
    order_rows = db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.supplier_id == supplier.id,
        CartonOrder.status.in_(VISIBLE_STATES))).all()
    order_nos = {row.id: row.order_no for row in order_rows}
    order_ids = set(order_nos)
    issue_rows = db.scalars(select(CartonPurchaseOrderIssue).where(
        CartonPurchaseOrderIssue.factory_id == factory,
        CartonPurchaseOrderIssue.order_id.in_(order_ids),
        CartonPurchaseOrderIssue.document_type != "LEGACY_BASELINE")).all()
    issue_nos = {row.id: row.document_no for row in issue_rows}
    shipments = db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory, SupplierShipment.supplier_id == supplier.id)).all()
    shipment_nos = {row.id: row.delivery_note_no for row in shipments}
    if not order_ids and not issue_nos and not shipment_nos:
        return []
    allowed = {
        "PURCHASE_ORDER_ISSUED": ("carton_purchase_order_issue", issue_nos, "采购单已发行"),
        "SUPPLIER_PAPER_ACCEPTED": ("carton_order", order_nos, "纸品已确认接单"),
        "SUPPLIER_SHIPMENT_CREATED": ("supplier_shipment", shipment_nos, "供应商已确认发货"),
        "SUPPLIER_SHIPMENT_RECEIVED": ("supplier_shipment", shipment_nos, "仓库已核实送货"),
        "SUPPLIER_SHIPMENT_NOT_RECEIVED": ("supplier_shipment", shipment_nos, "仓库反馈未收到"),
        "SUPPLIER_SHIPMENT_RECEIPT_REVERSED": ("supplier_shipment", shipment_nos, "原收料已冲销，等待仓库更正"),
        "SUPPLIER_SHIPMENT_LINE_LINKED": ("supplier_shipment", shipment_nos, "无单纸品已关联正式订单"),
    }
    rows = db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type.in_(allowed),
        or_(
            and_(CartonAuditEvent.entity_type == "carton_order", CartonAuditEvent.entity_id.in_(order_ids)),
            and_(CartonAuditEvent.entity_type == "carton_purchase_order_issue", CartonAuditEvent.entity_id.in_(issue_nos)),
            and_(CartonAuditEvent.entity_type == "supplier_shipment", CartonAuditEvent.entity_id.in_(shipment_nos)),
        )).order_by(CartonAuditEvent.sequence.desc()).limit(500)).all()
    result = []
    for row in rows:
        rule = allowed.get(row.event_type)
        if not rule or row.entity_type != rule[0] or row.entity_id not in rule[1]:
            continue
        result.append({
            "id": row.id, "created_at": row.created_at, "action": rule[2],
            "reference_no": rule[1][row.entity_id], "actor_name": row.actor_name or "系统",
            "factory_id": factory,
        })
    return result


def _excel_text(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _document_entity_type(row):
    if row.get("is_batch"):
        return "carton_purchase_order_batch"
    return "carton_purchase_order_issue" if row["kind"] == "PURCHASE" else "supplier_shipment"


def _record_document_export(db, user, row, **details):
    _audit(db, user, row["factory_id"], "SUPPLIER_DOCUMENT_EXPORTED", _document_entity_type(row), row["id"],
           {"document_no": row["document_no"], "kind": row["kind"], **details})


def export_documents(db, user, payload: SupplierDocumentExport):
    visible_by_factory = {}
    selected = []
    for item in payload.documents:
        if item.factory_id not in visible_by_factory:
            visible_by_factory[item.factory_id] = {
                (row["kind"], row["id"]): row for row in documents(db, user, item.factory_id)
            }
        row = visible_by_factory[item.factory_id].get((item.kind, item.id))
        if row is None:
            raise HTTPException(404, "所选单据不存在或不属于当前供应商")
        selected.append(row)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for kind, title, headers in (
        ("PURCHASE", "采购单", ["厂区", "采购单号", "发行日期", "变更类型", "订单号", "客户", "合同号",
                              "客户PO", "货号", "计划交期", "纸品子单", "纸品类型", "纸质", "规格",
                              "变更前", "本次变化", "变更后", "单位", "原采购单号"]),
        ("DELIVERY", "送货单", ["送货厂区", "送货单号", "送货日期", "仓库状态", "订单号", "客户", "合同号",
                              "客户PO", "货号", "纸品子单", "纸品类型", "纸质", "规格",
                              "发货数量", "仓库实收", "单位"]),
    ):
        subset = [row for row in selected if row["kind"] == kind]
        if not subset:
            continue
        sheet = workbook.create_sheet(title)
        sheet.append(headers)
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="087F74")
            cell.alignment = Alignment(wrap_text=True)
        for document in subset:
            orders = {row["order_no"]: row for row in document["orders"]}
            for line in document["lines"]:
                order = orders.get(line["order_no"], {})
                if kind == "PURCHASE":
                    values = [
                        document["factory_id"], document["document_no"], document["date"],
                        "补单" if document["replenishment"] else document["document_type"],
                        line["order_no"], order.get("customer_name"), order.get("contract_no"),
                        order.get("customer_po"), order.get("item_no"), order.get("planned_date"),
                        line["child_no"], line["packaging_type"], line["paper_quality"],
                        line["specification"], line["before_quantity"], line["change_quantity"],
                        line["quantity"], line["unit"], line.get("source_document_no", document["document_no"]),
                    ]
                else:
                    values = [
                        document["factory_id"], document["document_no"], document["date"],
                        document["status"], line["order_no"], order.get("customer_name") or line.get("customer_name"),
                        order.get("contract_no") or line.get("contract_no"), order.get("customer_po"), order.get("item_no") or line.get("item_no"),
                        line["child_no"], line["packaging_type"], line["paper_quality"],
                        line["specification"], line["quantity"], line["received_quantity"], line["unit"],
                    ]
                numeric_columns = {14, 15, 16} if kind == "PURCHASE" else {13, 14}
                cells = []
                for index, value in enumerate(values):
                    if index in numeric_columns:
                        try:
                            cells.append(float(Decimal(str(value))))
                            continue
                        except (ValueError, ArithmeticError):
                            pass
                    cells.append(_excel_text(value))
                sheet.append(cells)
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(30, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    content = output.getvalue()
    for row in selected:
        _record_document_export(db, user, row)
    db.commit()
    return content


SUPPLIER_ORDER_IMPORT_HEADERS = [
    "客户单号", "客户料号", "型号", "长", "宽", "高", "数量", "材质名称", "箱型",
    "尺寸单位", "单价", "交期", "生产备注", "送货备注", "单位", "生产长", "生产宽",
    "生产高", "备注1", "备注2", "备注3",
]


def _supplier_import_dimensions(specification: str, document_no: str) -> list[float | None]:
    value = str(specification or "").strip()
    parts = re.split(r"\s*[*×xX＊]\s*", re.sub(r"\s*(?:cm|厘米|inch|in|英寸)\s*$", "", value, flags=re.IGNORECASE))
    if len(parts) not in (2, 3) or any(not re.fullmatch(r"\d+(?:\.\d+)?", part) for part in parts):
        raise HTTPException(422, f"采购单 {document_no} 的规格“{value or '空'}”无法拆成长、宽、高；请先在纸箱采购单补正规格")
    dimensions = [float(part) for part in parts]
    if any(part <= 0 for part in dimensions):
        raise HTTPException(422, f"采购单 {document_no} 的规格尺寸必须大于 0")
    return dimensions + [None] * (3 - len(dimensions))


def export_supplier_order_import(db, user, payload: SupplierDocumentExport):
    """Dongkang ERP rows use issued deltas, including B replacements, never cumulative totals."""
    if len({selection.factory_id for selection in payload.documents}) != 1:
        raise HTTPException(422, "对方导入模板一次只能包含一个送货厂区；请按厂区分别导出")
    visible_by_factory = {}
    issue_rows = []
    selected = []
    for selection in payload.documents:
        if selection.kind != "PURCHASE":
            raise HTTPException(422, "对方订单导入模板只能选择采购单")
        if selection.factory_id not in visible_by_factory:
            visible_by_factory[selection.factory_id] = {
                row["id"]: row for row in documents(db, user, selection.factory_id)
                if row["kind"] == "PURCHASE"
            }
        document = visible_by_factory[selection.factory_id].get(selection.id)
        if document is None:
            raise HTTPException(404, "所选采购单不存在或不属于当前供应商")
        selected.append(document)
        if document.get("is_batch"):
            _batch, sources = load_purchase_batch(db, selection.factory_id, selection.id)
        else:
            issue = db.get(CartonPurchaseOrderIssue, selection.id)
            if issue is None or issue.factory_id != selection.factory_id:
                raise HTTPException(404, "采购单发行快照不存在")
            sources = [issue]
        issue_rows.extend((issue, _purchase_order_snapshot(issue), document) for issue in sources)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "006 (2)"
    sheet.append(SUPPLIER_ORDER_IMPORT_HEADERS)
    sheet.freeze_panes = "A2"
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="087F74")
    for issue, snapshot, document in issue_rows:
        header = snapshot.get("order", {})
        lines = snapshot.get("lines", [])
        if not isinstance(header, dict) or not isinstance(lines, list):
            raise HTTPException(422, f"采购单 {issue.document_no} 的发行快照不完整")
        replenishment = snapshot.get("replenishment")
        if replenishment and (not isinstance(replenishment, dict)
                              or replenishment.get("responsibility") not in {"OWN", "SUPPLIER"}):
            raise HTTPException(422, f"采购单 {issue.document_no} 的补单责任不明确，请先核对发行快照")
        changes = [Decimal(str(line.get("required_quantity_delta") or 0)) for line in lines]
        if any(change < 0 for change in changes) or not any(change > 0 for change in changes):
            raise HTTPException(422, f"采购单 {issue.document_no} 含减量或仅交期变更，不能作为新增订单导入；请单独与供应商处理变更")
        contract_no = str(header.get("contract_no") or "").strip()
        item_no = str(header.get("item_no") or "").strip()
        if not contract_no or not item_no:
            raise HTTPException(422, f"采购单 {issue.document_no} 缺少合同号或货号")
        try:
            promised_date = date.fromisoformat(str(snapshot.get("after_due_date") or ""))
        except ValueError as exc:
            raise HTTPException(422, f"采购单 {issue.document_no} 缺少有效交期") from exc
        for line, change in zip(lines, changes):
            if change <= 0:
                continue
            specification = str(line.get("specification") or "")
            declared_unit = str(line.get("dimension_unit") or "").strip().lower()
            if declared_unit and declared_unit not in {"cm", "厘米", "in", "inch", "英寸"}:
                raise HTTPException(422, f"采购单 {issue.document_no} 的尺寸单位为 {declared_unit}，请核对后再导出对方模板")
            suffix = re.search(r"(cm|厘米|inch|in|英寸)\s*$", specification, re.IGNORECASE)
            suffix_unit = ("cm" if suffix.group(1).lower() in {"cm", "厘米"} else "inch") if suffix else ""
            supplier_unit = ("cm" if declared_unit in {"cm", "厘米"} else "inch") if declared_unit else (suffix_unit or "cm")
            if suffix_unit and suffix_unit != supplier_unit:
                raise HTTPException(422, f"采购单 {issue.document_no} 的规格单位与尺寸单位不一致，请先核对")
            length, width, height = _supplier_import_dimensions(specification, issue.document_no)
            if replenishment:
                responsibility = replenishment["responsibility"]
                settlement_note = "供应商责任，免费换补" if responsibility == "SUPPLIER" else "我方责任，按实收结算"
                delivery_note = f"补单 {issue.document_no}；{settlement_note}；送货单请注明补单号；交期沿用原单，请确认实际送货日期"
            else:
                delivery_note = ""
            unit_price = 0 if replenishment and replenishment["responsibility"] == "SUPPLIER" else float(
                Decimal(str(line.get("unit_price") or 0)))
            sheet.append([
                _excel_text(contract_no), _excel_text(item_no), _excel_text(header.get("product_name")),
                length, width, height, float(change), _excel_text(line.get("paper_quality")),
                _excel_text(line.get("packaging_type")), supplier_unit, unit_price,
                promised_date, _excel_text(line.get("note")), _excel_text(delivery_note),
                _excel_text(line.get("unit")), None, None, None, _excel_text(issue.document_no),
                _excel_text(document["document_no"]) if document.get("is_batch") else "", "",
            ])
            sheet.cell(sheet.max_row, 12).number_format = "yyyy-mm-dd"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        column[0].parent.column_dimensions[column[0].column_letter].width = min(30, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    for document in selected:
        _record_document_export(db, user, document, format="SUPPLIER_ORDER_IMPORT")
    db.commit()
    return output.getvalue()


def accept_line(db, user, line_id, payload: CommitmentSave):
    result = accept_lines(db, user, BatchCommitmentSave(factory_id=payload.factory_id, lines=[{
        "order_line_id": line_id, "issue_id": payload.issue_id,
        "expected_revision": payload.expected_revision, "promised_date": payload.promised_date,
    }]))
    return order_out(db, db.get(CartonOrder, result[0]))


def accept_lines(db, user, payload: BatchCommitmentSave):
    _lock_receipt_factory(db, payload.factory_id)
    supplier = supplier_access(db, user, payload.factory_id, "carton_supplier:approve")
    validated = []
    for item in payload.lines:
        line = db.get(CartonOrderLine, item.order_line_id)
        if not line or line.factory_id != payload.factory_id:
            raise HTTPException(404, "未找到纸品子单")
        order = supplier_order(db, line.order_id, payload.factory_id, supplier.id)
        executable(db, order, item.issue_id)
        if line.required_quantity <= 0:
            raise HTTPException(409, f"纸品 {order.order_no}/{line.line_no} 需求已取消")
        row = db.get(SupplierCommitment, line.id)
        if (row.revision if row else 0) != item.expected_revision:
            raise HTTPException(409, f"纸品 {order.order_no}/{line.line_no} 接单版本已变更，请刷新")
        validated.append((item, line, order, row))
    order_ids = []
    for item, line, order, row in validated:
        if not row:
            row = SupplierCommitment(order_line_id=line.id, factory_id=payload.factory_id, revision=0)
            db.add(row)
        row.issue_id = item.issue_id; row.promised_date = item.promised_date.isoformat(); row.revision += 1
        row.accepted_by = user.id; row.accepted_at = now_text()
        _audit(db, user, payload.factory_id, "SUPPLIER_PAPER_ACCEPTED", "carton_order", order.id,
            {"line_id": line.id, "issue_id": row.issue_id, "promised_date": row.promised_date, "revision": row.revision})
        if order.id not in order_ids:
            order_ids.append(order.id)
    db.commit()
    return order_ids


def create_shipment(db, user, payload: ShipmentCreate, *, commit=True, source=None):
    _lock_receipt_factory(db, payload.factory_id)
    supplier = supplier_access(db, user, payload.factory_id, "carton_supplier:edit")
    if payload.unmatched_lines and not source:
        raise HTTPException(422, "无单明细只能来自已预览的原始送货单")
    digest = fingerprint(payload)
    previous = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == payload.factory_id,
        SupplierShipment.created_by == user.id, SupplierShipment.request_id == payload.request_id))
    if previous:
        if previous.supplier_id != supplier.id or previous.fingerprint != digest:
            raise HTTPException(409, "此发货提交标识已用于其他内容")
        return shipment_out(db, previous)
    if db.scalar(select(SupplierShipment.id).where(SupplierShipment.factory_id == payload.factory_id,
        SupplierShipment.supplier_id == supplier.id, SupplierShipment.delivery_note_no == payload.delivery_note_no)):
        raise HTTPException(409, "此供应商送货单号已经登记")
    if db.scalar(select(CartonReceipt.id).where(CartonReceipt.factory_id == payload.factory_id,
        CartonReceipt.supplier_id == supplier.id, CartonReceipt.delivery_note_no == payload.delivery_note_no)):
        raise HTTPException(409, "此送货单已有收料记录，请核对原单，不可再次登记发货")
    if payload.unmatched_lines:
        active_keys = {(_dongkang_identity(order.contract_no), _dongkang_identity(order.item_no))
            for order in db.scalars(select(CartonOrder).where(
                CartonOrder.factory_id == payload.factory_id, CartonOrder.status != "CANCELLED")).all()}
        if any(item.contract_no and (_dongkang_identity(item.contract_no),
                _dongkang_identity(item.item_no)) in active_keys for item in payload.unmatched_lines):
            raise HTTPException(409, "无单纸品已有相同合同和货号的正式订单，请重新预览并核对")
    ids = [item.order_line_id for item in payload.lines]
    authorized_ids = set(db.scalars(select(CartonOrderLine.id).join(CartonOrder,
        CartonOrder.id == CartonOrderLine.order_id).where(CartonOrderLine.id.in_(ids),
            CartonOrderLine.factory_id == payload.factory_id, CartonOrder.factory_id == payload.factory_id,
            CartonOrder.supplier_id == supplier.id, CartonOrder.status.in_(VISIBLE_STATES))).all())
    if authorized_ids != set(ids):
        raise HTTPException(404, "未找到可访问的纸品子单")
    fulfilled = fulfilled_by_line(db, ids); reserved = outstanding(db, ids); pending = _pending_received_by_line(db, ids)
    blocked = blocked_replacement_lines(db, payload.factory_id, ids)
    snapshots = []
    checked_orders = set()
    for item in payload.lines:
        line = db.get(CartonOrderLine, item.order_line_id)
        if not line or line.factory_id != payload.factory_id:
            raise HTTPException(404, "未找到纸品子单")
        order = supplier_order(db, line.order_id, payload.factory_id, supplier.id)
        issue = executable(db, order, item.issue_id)
        if order.id not in checked_orders:
            for paper in _purchase_order_snapshot(issue).get("lines", []):
                if Decimal(str(paper.get("after_required_quantity", "0"))) <= 0:
                    continue
                commitment = db.get(SupplierCommitment, str(paper["id"]))
                if not commitment or commitment.issue_id != issue.id:
                    raise HTTPException(409, f"订单 {order.order_no} 尚有纸品未确认接单，请先完成整单接单")
            checked_orders.add(order.id)
        if line.id in blocked:
            raise HTTPException(409, "此纸品有补单待核对，请联系内部仓库按原补单流程处理")
        commitment = db.get(SupplierCommitment, line.id)
        if not commitment or commitment.issue_id != issue.id:
            raise HTTPException(409, "请先确认当前版本纸品子单及承诺交期")
        available = line.required_quantity - fulfilled.get(line.id, 0) - reserved.get(line.id, 0) - pending.get(line.id, 0)
        if item.quantity > available:
            raise HTTPException(409, f"纸品 {order.order_no}/{line.line_no} 超过当前未送数量")
        snapshots.append({"order_no": order.order_no, "contract_no": order.contract_no, "customer_po": order.customer_po,
            "item_no": order.item_no, "customer_name": order.customer_name, "child_no": f"{order.order_no}/{line.line_no:02d}",
            **{key: str(getattr(line, key)) for key in ("packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency")},
            **({"delivery_unit_price": str(source["delivery_unit_prices"][line.id])}
                if source and line.id in source.get("delivery_unit_prices", {}) else {}),
            **({"original_source_material": source["delivery_materials"][line.id]}
                if source and line.id in source.get("delivery_materials", {}) else {}),
            **({"source_file": {key: source[key] for key in ("filename", "sha256", "rows") if key in source}}
                if source else {})})
    row = SupplierShipment(id=f"CSS-{uuid4().hex}", factory_id=payload.factory_id, supplier_id=supplier.id,
        delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(), status="SENT", revision=1,
        request_id=payload.request_id, fingerprint=digest, created_by=user.id, created_at=now_text())
    db.add(row); db.flush()
    for index, item in enumerate(payload.lines):
        db.add(SupplierShipmentLine(id=f"{row.id}-{index+1:03d}", shipment_id=row.id, factory_id=payload.factory_id,
            order_line_id=item.order_line_id, issue_id=item.issue_id, quantity=item.quantity,
            snapshot_json=json.dumps(snapshots[index], ensure_ascii=False)))
    for index, item in enumerate(payload.unmatched_lines):
        snapshot = item.model_dump(mode="json") | {"order_no": "", "child_no": "", "customer_name": "",
            "customer_po": "", "source_file": source or {}}
        db.add(SupplierShipmentUnmatchedLine(id=f"{row.id}-U{index+1:03d}", shipment_id=row.id,
            factory_id=payload.factory_id, source_sheet=item.source_sheet, source_row=item.source_row,
            quantity=item.quantity, snapshot_json=json.dumps(snapshot, ensure_ascii=False)))
    _audit(db, user, payload.factory_id, "SUPPLIER_SHIPMENT_CREATED", "supplier_shipment", row.id,
        {"delivery_note_no": row.delivery_note_no, "lines": [item.model_dump(mode="json") for item in payload.lines],
         "unmatched_lines": [item.model_dump(mode="json") for item in payload.unmatched_lines],
         **({"source_file": source} if source else {})})
    shipment_notifications.create_notification(db, row)
    if commit:
        db.commit()
    else:
        db.flush()
    return shipment_out(db, row)


def receive_shipment(db, user, shipment_id, payload: ShipmentReceive):
    internal_permission(user, payload.factory_id, "carton_procurement:receipt_write", "carton_procurement:inventory_write")
    _lock_receipt_factory(db, payload.factory_id)
    row = db.scalar(select(SupplierShipment).where(SupplierShipment.id == shipment_id, SupplierShipment.factory_id == payload.factory_id))
    if not row:
        raise HTTPException(404, "未找到此厂区的发货单")
    digest = fingerprint(payload)
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == payload.factory_id,
        CartonAuditEvent.entity_type == "supplier_shipment", CartonAuditEvent.entity_id == row.id,
        CartonAuditEvent.event_type.in_({"SUPPLIER_SHIPMENT_RECEIVED", "SUPPLIER_SHIPMENT_NOT_RECEIVED"}))).all():
        saved = json.loads(event.detail_json)
        if event.actor_user_id == user.id and saved.get("acceptance", {}).get("request_id") == payload.request_id:
            saved_fingerprint = saved.get("request_fingerprint") or fingerprint(ShipmentReceive.model_validate(saved["acceptance"]))
            if saved_fingerprint != digest:
                raise HTTPException(409, "此收料提交标识已用于其他内容，请核对原记录")
            return shipment_out(db, row, internal=True)
    previous_receipt = db.get(CartonReceipt, row.receipt_id) if row.receipt_id else None
    correction = bool(previous_receipt and previous_receipt.status == "REVERSED")
    if correction and len(payload.correction_reason.strip()) < 4:
        raise HTTPException(422, "原收料已冲销，更正验收须填写至少四字原因")
    if row.status in {"RECEIVED", "NOT_RECEIVED"} and not correction:
        if row.confirmed_by == user.id and row.confirmation_request_id == payload.request_id and row.confirmation_fingerprint == digest:
            return shipment_out(db, row, internal=True)
        raise HTTPException(409, "此发货单已确认收料，不可重复入库")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "发货单版本已变更，请刷新")
    formal, unmatched = _shipment_sources(db, row)
    source = formal + unmatched
    supplied = {item.shipment_line_id: item for item in payload.lines}
    if len(supplied) != len(payload.lines) or set(supplied) != {item.id for item in source}:
        raise HTTPException(422, "必须逐条核对整张发货单，不可漏行或混入其他单据")
    active_order_keys = {(_dongkang_identity(order.contract_no), _dongkang_identity(order.item_no))
        for order in db.scalars(select(CartonOrder).where(
            CartonOrder.factory_id == payload.factory_id, CartonOrder.status != "CANCELLED")).all()} if any(
                isinstance(line, SupplierShipmentUnmatchedLine) for line in source) else set()
    reject_all = all(item.received_quantity == 0 for item in payload.lines)
    formal_ids = [line.order_line_id for line in formal]
    fulfilled = fulfilled_by_line(db, formal_ids)
    pending = _pending_received_by_line(db, formal_ids)
    reserved = outstanding(db, formal_ids)
    own_reservations = {}
    for shipped in formal:
        own_reservations[shipped.order_line_id] = _accepted_reservation(row, shipped) if correction else shipped.quantity
    receipt_lines = []
    for shipped in source:
        item = supplied[shipped.id]
        if item.received_quantity > shipped.quantity:
            raise HTTPException(422, "实收不能超过本次发货数量")
        effective = item.received_quantity - item.damaged_quantity - item.rejected_quantity - item.unusable_quantity
        if effective < 0:
            raise HTTPException(422, "不可用数量不能超过实收")
        if isinstance(shipped, SupplierShipmentUnmatchedLine):
            snapshot = json.loads(shipped.snapshot_json)
            if item.received_quantity == 0:
                if item.no_order_decision:
                    raise HTTPException(422, "未到货的无单纸品不能标记为样板箱或送错货")
                if len(item.difference_reason.strip()) < 4:
                    raise HTTPException(422, "无单纸品未到货须填写至少四字原因")
                continue
            if item.no_order_decision == "WRONG_DELIVERY":
                if effective != 0 or len(item.difference_reason.strip()) < 4:
                    raise HTTPException(422, "送错货必须全部拒收并填写至少四字原因")
                continue
            if item.no_order_decision != "SAMPLE":
                raise HTTPException(422, "无单纸品须明确选择确需入库的样板箱或送错货")
            if not item.customer_code or len(item.sample_purpose.strip()) < 4 or len(item.requested_by.strip()) < 2:
                raise HTTPException(422, "样板箱须选择客户，并填写用途和需求人")
            if effective <= 0:
                raise HTTPException(422, "样板箱有效入库数量须大于 0；全部拒收请选择送错货")
            # A formal order entered after vendor import must be reconciled as a formal receipt.
            if snapshot.get("contract_no") and (
                _dongkang_identity(snapshot["contract_no"]), _dongkang_identity(snapshot["item_no"])) in active_order_keys:
                raise HTTPException(409, "此无单纸品已存在相同合同和货号的正式订单，请先核对，不得按样板箱入库")
            if item.unit_price == 0:
                raise HTTPException(422, "样板箱入库须填写大于 0 的单价；免费样板请先核实价格及结算方式")
            if not item.location_allocations:
                raise HTTPException(422, "样板箱有效入库须分配实际仓位")
            positions.validate_allocations(db, payload.factory_id,
                [allocation.model_dump(mode="json") for allocation in item.location_allocations], effective)
            receipt_lines.append(CartonReceiptLineCreate(source_type="AD_HOC", customer_code=item.customer_code,
                contract_no=snapshot.get("contract_no") or row.delivery_note_no, item_no=snapshot["item_no"],
                packaging_type=snapshot["packaging_type"], paper_quality=snapshot["paper_quality"],
                specification=snapshot["specification"], unit=item.unit or snapshot["unit"], currency="CNY",
                delivered_quantity=shipped.quantity, received_quantity=item.received_quantity,
                damaged_quantity=item.damaged_quantity, rejected_quantity=item.rejected_quantity,
                unusable_quantity=item.unusable_quantity, unit_price=item.unit_price,
                location_allocations=item.location_allocations,
                feedback_note=f"无正式订单样板箱；用途：{item.sample_purpose}；需求人：{item.requested_by}；{item.difference_reason}"))
            continue
        if item.no_order_decision or item.customer_code or item.sample_purpose or item.requested_by:
            raise HTTPException(422, "正式订单纸品不得选择无单处理")
        line = db.get(CartonOrderLine, shipped.order_line_id)
        order = supplier_order(db, line.order_id, payload.factory_id, row.supplier_id)
        if order.status not in OPEN_STATES and not reject_all:
            raise HTTPException(409, "关联订单当前不允许收料")
        available = line.required_quantity - fulfilled.get(line.id, 0) - pending.get(line.id, 0) - (reserved.get(line.id, 0) - own_reservations.get(line.id, 0))
        if effective > available:
            raise HTTPException(409, "有效实收超过剩余需求，其他待确认送货或收料数量已受保护")
        if effective > 0:
            if not item.location_allocations:
                raise HTTPException(422, "有效入库数量大于 0 时必须选择实际入库仓位并分配数量")
            positions.validate_allocations(db, payload.factory_id,
                [allocation.model_dump(mode="json") for allocation in item.location_allocations], effective)
        if effective != shipped.quantity and len(item.difference_reason.strip()) < 4:
            raise HTTPException(422, "短收、破损或拒收必须填写至少四字的差异原因")
        if item.received_quantity == 0:
            continue  # Non-arrival remains shipment evidence, never a fabricated receipt line.
        receipt_lines.append(CartonReceiptLineCreate(order_line_id=line.id, delivered_quantity=shipped.quantity,
            received_quantity=item.received_quantity, damaged_quantity=item.damaged_quantity, rejected_quantity=item.rejected_quantity,
            unusable_quantity=item.unusable_quantity, unit_price=item.unit_price, paper_quality=item.paper_quality,
            specification=item.specification, location_allocations=item.location_allocations, feedback_note=item.difference_reason))
    try:
        if correction:
            row.status = "SENT"  # Also recovers reversed notes recorded before the reversal hook existed.
            db.flush()
        receipt = None
        if receipt_lines:
            receipt = _create_receipt(db, CartonReceiptCreate(factory_id=payload.factory_id, supplier_id=row.supplier_id,
                delivery_note_no=row.delivery_note_no, delivery_date=row.delivery_date, acceptance_date=payload.acceptance_date.isoformat(),
                note=f"供应商发货单 {row.id}，逐纸品核实实际收到，差异保留待收需求" +
                    (f"；更正原收料 {previous_receipt.receipt_no}：{payload.correction_reason}" if correction else ""),
                lines=receipt_lines), user, commit=False, supplier_shipment_id=row.id,
                corrects_receipt_id=previous_receipt.id if correction else None)
            confirm_receipt(db, receipt.id, CartonReceiptConfirmRequest(factory_id=payload.factory_id, expected_revision=receipt.revision, split_confirmation=payload.split_confirmation), user, commit=False)
        # The core lock helper expires ORM state, so update the shipment only after core posting.
        row.status = "NOT_RECEIVED" if reject_all else "RECEIVED"; row.revision += 1; row.receipt_id = receipt.id if receipt else None
        row.confirmed_by = user.id; row.confirmed_at = now_text()
        row.confirmation_request_id = payload.request_id; row.confirmation_fingerprint = digest
        row.acceptance_json = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        _audit(db, user, payload.factory_id, "SUPPLIER_SHIPMENT_NOT_RECEIVED" if reject_all else "SUPPLIER_SHIPMENT_RECEIVED", "supplier_shipment", row.id,
            {"receipt_id": receipt.id if receipt else None, "acceptance": payload.model_dump(mode="json"),
             "request_fingerprint": digest, "supersedes_receipt_id": previous_receipt.id if correction else None})
        shipment_notifications.handle_notification(db, row)
        db.commit()
        return shipment_out(db, row, internal=True)
    except Exception:
        db.rollback()
        raise


def reopen_reversed_shipment(db, receipt, user, reason):
    """Reopen the original vendor evidence atomically with the receipt reversal."""
    shipment = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == receipt.factory_id,
        SupplierShipment.supplier_id == receipt.supplier_id, SupplierShipment.receipt_id == receipt.id))
    if not shipment:
        return
    shipment.status = "SENT"
    shipment.revision += 1
    _audit(db, user, receipt.factory_id, "SUPPLIER_SHIPMENT_RECEIPT_REVERSED", "supplier_shipment", shipment.id,
        {"receipt_id": receipt.id, "delivery_note_no": shipment.delivery_note_no, "reason": reason,
         "acceptance": json.loads(shipment.acceptance_json or "{}")})
    notification = shipment_notifications.create_notification(db, shipment)
    notification.status = "unread"
    notification.title = f"供应商送货单 {shipment.delivery_note_no[:100]} 收料已冲销，待更正"
    notification.message = "请沿原送货单重新核实数量、价格及仓位；旧验收记录已保留。"
    notification.read_at = notification.handled_at = ""
    notification.created_at = now_text()


def link_shipment_line(db, user, shipment_id, line_id, payload: ShipmentLineLink):
    internal_permission(user, payload.factory_id, "carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write")
    _lock_receipt_factory(db, payload.factory_id)
    shipment = db.scalar(select(SupplierShipment).where(SupplierShipment.id == shipment_id,
        SupplierShipment.factory_id == payload.factory_id))
    source = db.get(SupplierShipmentUnmatchedLine, line_id)
    if not shipment or not source or source.shipment_id != shipment.id or source.factory_id != payload.factory_id:
        raise HTTPException(404, "未找到本厂区的无单送货明细")
    event_id = f"CAE-SHIP-LINK-{source.id}"
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous:
        if previous.actor_user_id == user.id and json.loads(previous.detail_json).get("fingerprint") == fingerprint(payload):
            return shipment_out(db, shipment, internal=True)
        raise HTTPException(409, "此无单明细已经关联，不可重复或更换目标")
    prior_receipt = db.get(CartonReceipt, shipment.receipt_id) if shipment.receipt_id else None
    correction = bool(prior_receipt and prior_receipt.status == "REVERSED")
    if (shipment.status != "SENT" and not correction) or shipment.revision != payload.expected_revision or (shipment.receipt_id and not correction):
        raise HTTPException(409, "送货单状态或版本已变化，仅待验收或收料已冲销的无单行可关联")
    target = db.get(CartonOrderLine, payload.order_line_id)
    order = db.get(CartonOrder, target.order_id) if target else None
    if not target or target.factory_id != payload.factory_id or not order or order.factory_id != payload.factory_id or order.supplier_id != shipment.supplier_id:
        raise HTTPException(404, "目标纸品不属于此厂区与供应商")
    from app.services.carton_procurement import get_active_customer
    customer = get_active_customer(db, payload.factory_id, payload.customer_code)
    if customer.customer_code != order.customer_code:
        raise HTTPException(422, "所选客户与正式订单客户不一致")
    if order.revision != payload.expected_order_revision:
        raise HTTPException(409, "正式订单版本已变化，请刷新后重新核对")
    issue = executable(db, order, latest_issue(db, order).id if latest_issue(db, order) else "")
    snapshot = json.loads(source.snapshot_json)
    target_material = {key: getattr(target, key) for key in ("packaging_type", "paper_quality", "specification", "dimension_unit")}
    if not snapshot.get("contract_no") or _dongkang_identity(snapshot["contract_no"]) != _dongkang_identity(order.contract_no) or _dongkang_identity(snapshot["item_no"]) != _dongkang_identity(order.item_no):
        raise HTTPException(422, "合同号或货号与正式订单不一致")
    if not all(snapshot.get(key) not in (None, "", "待复核", "纸箱", "普通箱") for key in ("packaging_type", "paper_quality", "specification")) or not dimension_identity(snapshot["specification"]) or material_conflicts(snapshot, target_material):
        raise HTTPException(422, "纸品类型、纸质、规格或尺寸单位与正式订单不一致")
    if target.id in blocked_replacement_lines(db, payload.factory_id, [target.id]):
        raise HTTPException(409, "此纸品存在补单待核对，请按补单流程收货")
    formal, _ = _shipment_sources(db, shipment)
    if any(line.order_line_id == target.id for line in formal):
        raise HTTPException(409, "本送货单已有此纸品明细，不可重复关联")
    available = target.required_quantity - fulfilled_by_line(db, [target.id]).get(target.id, 0) - outstanding(db, [target.id]).get(target.id, 0) - _pending_received_by_line(db, [target.id]).get(target.id, 0)
    if source.quantity > available:
        raise HTTPException(409, "本次送货数量超过正式订单未收且未在途需求")
    linked_snapshot = {"order_no": order.order_no, "contract_no": order.contract_no, "customer_po": order.customer_po,
        "item_no": order.item_no, "customer_name": order.customer_name, "child_no": f"{order.order_no}/{target.line_no:02d}",
        **{key: str(getattr(target, key)) for key in ("packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency")},
        "delivery_unit_price": snapshot.get("unit_price"), "source_file": snapshot.get("source_file") or {},
        "original_unmatched_line_id": source.id, "original_source_material": snapshot}
    db.add(SupplierShipmentLine(id=f"{source.id}-L", shipment_id=shipment.id, factory_id=payload.factory_id,
        order_line_id=target.id, issue_id=issue.id, quantity=source.quantity,
        snapshot_json=json.dumps(linked_snapshot, ensure_ascii=False)))
    shipment.revision += 1
    event = _audit(db, user, payload.factory_id, "SUPPLIER_SHIPMENT_LINE_LINKED", "supplier_shipment", shipment.id,
        {"source_line_id": source.id, "source_snapshot": snapshot, "order_line_id": target.id, "issue_id": issue.id,
         "customer_code": customer.customer_code, "order_revision": order.revision, "reason": payload.reason,
         "fingerprint": fingerprint(payload)})
    event.id = event_id
    db.commit()
    return shipment_out(db, shipment, internal=True)


def link_sample_receipt(db, user, receipt_line_id: str, payload: SampleReceiptLink):
    """Reconcile a posted sample to a later formal line without posting stock or payable again."""
    internal_permission(user, payload.factory_id, "carton_procurement:order_adjust")
    _lock_receipt_factory(db, payload.factory_id)
    sample = db.get(CartonReceiptLine, receipt_line_id)
    if not sample or sample.factory_id != payload.factory_id or sample.source_type != "AD_HOC":
        raise HTTPException(404, "未找到此厂区的无单收料明细")
    receipt = db.get(CartonReceipt, sample.receipt_id)
    if not receipt or receipt.status != "POSTED" or sample.effective_quantity <= 0:
        raise HTTPException(409, "仅可关联仍有效且已入库的无单收料")
    shipment = db.scalar(select(SupplierShipment).where(
        SupplierShipment.factory_id == payload.factory_id,
        SupplierShipment.supplier_id == receipt.supplier_id,
        SupplierShipment.receipt_id == receipt.id,
        SupplierShipment.status == "RECEIVED"))
    if not shipment:
        raise HTTPException(409, "此收料不属于供应商导入的送货单")
    if db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.id == _sample_link_id(sample.id))):
        raise HTTPException(409, "此无单收料已经关联正式订单，不可再次关联")
    target = db.get(CartonOrderLine, payload.order_line_id)
    if not target or target.factory_id != payload.factory_id:
        raise HTTPException(404, "未找到此厂区的正式订单纸品")
    order = db.get(CartonOrder, target.order_id)
    if not order or order.factory_id != payload.factory_id or order.supplier_id != receipt.supplier_id:
        raise HTTPException(404, "目标订单不属于此厂区与供应商")
    if order.status not in OPEN_STATES or order.revision != payload.expected_order_revision:
        raise HTTPException(409, "目标订单状态或版本已变化，请刷新后重新核对")
    issue = latest_issue(db, order)
    if issue is None or _purchase_order_pending_change(order, get_order_lines(db, order.id), issue)[0] != "NONE":
        raise HTTPException(409, "目标正式订单的当前采购单尚未发行，请先发行再关联")
    matching = (sample.customer_code == order.customer_code
        and _dongkang_identity(sample.item_no) == _dongkang_identity(order.item_no)
        and _dongkang_identity(sample.packaging_type) == _dongkang_identity(target.packaging_type)
        and _dongkang_identity(sample.paper_quality) == _dongkang_identity(target.paper_quality)
        and sample.unit == target.unit
        and _dimension_identity(sample.specification)
        and _dimension_identity(sample.specification) == _dimension_identity(target.specification)
        and (_dimension_unit(sample.specification) or "cm")
            == (_dimension_unit(target.dimension_unit) or _dimension_unit(target.specification) or "cm"))
    if not matching:
        raise HTTPException(422, "客户、货号、纸品类型、材质、规格或单位与目标正式订单不一致")
    used = fulfilled_by_line(db, [target.id]).get(target.id, Decimal(0))
    in_transit = outstanding(db, [target.id]).get(target.id, Decimal(0))
    pending = _pending_received_by_line(db, [target.id]).get(target.id, Decimal(0))
    if sample.effective_quantity > target.required_quantity - used - in_transit - pending:
        raise HTTPException(409, "关联数量超过目标订单未收且未在途的需求，须先核对已发货记录")
    event = _audit(db, user, payload.factory_id, "SUPPLIER_SAMPLE_LINKED", "carton_order_line", target.id,
        {"sample_receipt_line_id": sample.id, "receipt_id": receipt.id,
         "delivery_note_no": receipt.delivery_note_no, "order_no": order.order_no,
         "quantity": str(sample.effective_quantity), "reason": payload.reason})
    event.id = _sample_link_id(sample.id)
    db.flush()
    _refresh_order_statuses(db, {order.id}, user)
    db.commit()
    return {"receipt_line_id": sample.id, "order_line_id": target.id,
            "order_no": order.order_no, "quantity": str(sample.effective_quantity)}


def validate_file(filename, content):
    if not content or len(content) > MAX_FILE:
        raise HTTPException(422, "附件不能为空且单文件最多 10 MB")
    if not filename or len(filename) > 255 or any(char in filename for char in ('/', '\\', '\r', '\n', '\x00')):
        raise HTTPException(422, "附件文件名无效")
    ext = PurePosixPath(filename).suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if not content.startswith(b"%PDF-") or reader.is_encrypted or not reader.pages:
                raise ValueError()
        except Exception:
            raise HTTPException(422, "请选择有效且未加密的 PDF 文件")
        return "application/pdf"
    formats = {".docx": ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".xlsx": ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".pptx": ("ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
    if ext not in formats:
        raise HTTPException(422, "仅支持 PDF、DOCX、XLSX、PPTX，不支持宏或可执行文件")
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(item.file_size for item in infos) > 40 * 1024 * 1024:
                raise ValueError()
            if any(item.flag_bits & 1 or "vbaproject" in item.filename.lower() or ".." in PurePosixPath(item.filename).parts for item in infos):
                raise ValueError()
            ElementTree.fromstring(archive.read("[Content_Types].xml"))
            ElementTree.fromstring(archive.read(formats[ext][0]))
    except (BadZipFile, KeyError, ValueError, ElementTree.ParseError, RuntimeError):
        raise HTTPException(422, "附件内容不是有效的无宏 Office 文档")
    return formats[ext][1]


def upload_attachment(db, user, factory, order_id, filename, content):
    internal_permission(user, factory, "carton_procurement:order_write")
    media = validate_file(filename, content)
    _lock_receipt_factory(db, factory)
    order = db.scalar(select(CartonOrder).where(CartonOrder.id == order_id, CartonOrder.factory_id == factory))
    if not order or order.supplier_id != fixed_supplier(db, factory).id:
        raise HTTPException(404, "未找到此厂区的供应商订单")
    if order.status == "CANCELLED":
        raise HTTPException(409, "已取消订单不能新增附件")
    digest = hashlib.sha256(content).hexdigest()
    previous = db.scalar(select(SupplierAttachment).where(SupplierAttachment.order_id == order.id,
        SupplierAttachment.filename == filename).order_by(SupplierAttachment.version.desc()))
    if previous and previous.sha256 == digest:
        return attachment_out(previous)
    row = SupplierAttachment(id=f"CSA-{uuid4().hex}", factory_id=factory, order_id=order.id, filename=filename,
        media_type=media, version=(previous.version if previous else 0)+1, size=len(content), sha256=digest,
        content=content, created_by=user.id, created_at=now_text())
    db.add(row)
    _audit(db, user, factory, "SUPPLIER_ORDER_ATTACHMENT_ADDED", "carton_order", order.id,
        {"attachment_id": row.id, "filename": filename, "version": row.version, "sha256": digest})
    db.commit()
    return attachment_out(row)


def attachment_download(db, user, factory, attachment_id, *, internal=False):
    if internal:
        internal_permission(user, factory, "carton_procurement:read")
    else:
        supplier = supplier_access(db, user, factory)
    row = db.scalar(select(SupplierAttachment).where(SupplierAttachment.id == attachment_id, SupplierAttachment.factory_id == factory))
    if not row:
        raise HTTPException(404, "未找到附件")
    if not internal:
        supplier_order(db, row.order_id, factory, supplier.id)
    return row
