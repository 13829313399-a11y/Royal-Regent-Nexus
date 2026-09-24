"""Supplier-scoped collaboration. All mutations use the existing carton factory lock."""
import hashlib
import json
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
from app.models.auth import AuthUser
from app.models.carton_mark import CartonMarkDocument, CartonMarkTemplate
from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonSupplier, CartonPurchaseOrderIssue, CartonReceipt, CartonAuditEvent
from app.models.carton_supplier_portal import SupplierMember, SupplierCommitment, SupplierShipment, SupplierShipmentLine, SupplierAttachment
from app.schemas.carton_supplier_portal import MemberSave, CommitmentSave, BatchCommitmentSave, ShipmentCreate, ShipmentReceive, SupplierMarkTemplateOut, SupplierDocumentExport
from app.schemas.carton_procurement import CartonReceiptCreate, CartonReceiptLineCreate, CartonReceiptConfirmRequest
from app.services.auth import AuthContext, authorization_decision, has_permission_in_scope, build_auth_context
from app.services import carton_positions as positions
from app.services.carton_procurement import (CARTON_DEPARTMENTS, require_carton_factory, _lock_receipt_factory,
    _purchase_order_issues, _purchase_order_snapshot, _purchase_order_pending_change, get_order_lines,
    fulfilled_by_line, _pending_received_by_line, _audit, now_text, _create_receipt, confirm_receipt)

OPEN_STATES = {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}
VISIBLE_STATES = OPEN_STATES | {"COMPLETED", "CANCELLED"}
MAX_FILE = 10 * 1024 * 1024
TABLES = ("carton_supplier_members", "carton_supplier_commitments", "carton_supplier_shipments", "carton_supplier_shipment_lines", "carton_supplier_attachments")


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
    """Factories with a confirmed order snapshot for an authorized external supplier."""
    # Registration creates an EmployeeProfile even for external applicants; only
    # effective internal role/permission bindings make the account ineligible.
    if user.role_codes or user.grants or user.permissions:
        return []
    codes = set(db.scalars(select(CartonSupplier.supplier_code).join(SupplierMember, and_(
        SupplierMember.supplier_id == CartonSupplier.id,
        SupplierMember.factory_id == CartonSupplier.factory_id)).where(
            SupplierMember.user_id == user.id, SupplierMember.status == "ACTIVE",
            CartonSupplier.status == "ACTIVE")).all())
    if not codes:
        return []
    # An explicit inactive factory row remains a local denial even if another factory opened the account.
    denied = set(db.scalars(select(SupplierMember.factory_id).where(
        SupplierMember.user_id == user.id, SupplierMember.status == "INACTIVE")).all())
    suppliers = db.scalars(select(CartonSupplier).where(CartonSupplier.supplier_code.in_(codes),
        CartonSupplier.status == "ACTIVE").order_by(CartonSupplier.factory_id)).all()
    return [supplier for supplier in suppliers if supplier.factory_id not in denied and db.scalar(
        select(CartonOrder.id).join(CartonPurchaseOrderIssue, and_(
            CartonPurchaseOrderIssue.order_id == CartonOrder.id,
            CartonPurchaseOrderIssue.factory_id == CartonOrder.factory_id)).where(
                CartonOrder.factory_id == supplier.factory_id,
                CartonOrder.supplier_id == supplier.id,
                CartonOrder.status.in_(VISIBLE_STATES)).limit(1))]


def supplier_access(db, user, factory):
    factory = require_carton_factory(factory)
    supplier = next((item for item in supplier_factories(db, user) if item.factory_id == factory), None)
    if supplier is None:
        raise HTTPException(403, "账号无权访问此厂区的供应商订单")
    return supplier


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def latest_issue(db, order):
    return next((issue for issue in _purchase_order_issues(db, order.id)
        if not _purchase_order_snapshot(issue).get("replenishment")), None)


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


def outstanding(db, line_ids):
    if not line_ids:
        return {}
    return dict(db.execute(select(SupplierShipmentLine.order_line_id, func.sum(SupplierShipmentLine.quantity))
        .join(SupplierShipment, SupplierShipment.id == SupplierShipmentLine.shipment_id)
        .where(SupplierShipment.status == "SENT", SupplierShipmentLine.order_line_id.in_(line_ids))
        .group_by(SupplierShipmentLine.order_line_id)).all())


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
    result.update(id=order.id, status=order.status, issue_id=issue.id if issue else "", document_no=issue.document_no if issue else "尚未发行",
        order_date=header.get("order_date") or order.order_date,
        planned_date=snapshot.get("after_due_date", ""), awaiting_issue=changed, lines=[])
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
        CartonOrder.status.in_(VISIBLE_STATES | {"DRAFT", "CONFIRMED"} if internal else VISIBLE_STATES)).order_by(CartonOrder.due_date, CartonOrder.order_no)).all()
    result = [order_out(db, row, internal=internal) for row in orders]
    shipments = db.scalars(select(SupplierShipment).where(SupplierShipment.factory_id == factory,
        SupplierShipment.supplier_id == supplier_id).order_by(SupplierShipment.created_at.desc())).all()
    return {"factory_id": factory, "supplier_name": db.get(CartonSupplier, supplier_id).supplier_name,
        "orders": [row for row in result if row], "shipments": [shipment_out(db, row, internal=internal) for row in shipments]}


def shipment_out(db, row, *, internal=False):
    result = {key: getattr(row, key) for key in ("id", "delivery_note_no", "delivery_date", "status", "revision", "created_at", "confirmed_at")}
    result["lines"] = []
    for line in db.scalars(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id == row.id).order_by(SupplierShipmentLine.id)).all():
        snapshot = json.loads(line.snapshot_json)
        item = {key: snapshot.get(key, "") for key in ("order_no", "contract_no", "customer_po", "item_no", "customer_name", "child_no", "packaging_type", "paper_quality", "specification", "unit")}
        item.update(id=line.id, order_line_id=line.order_line_id, quantity=str(line.quantity))
        if internal:
            item.update(unit_price=snapshot.get("unit_price", "0"), currency=snapshot.get("currency", "CNY"))
        result["lines"].append(item)
    accepted = json.loads(row.acceptance_json or "{}")
    result["acceptance_date"] = accepted.get("acceptance_date")
    # Supplier sees actual quantities/discrepancies, never internal cost or warehouse IDs.
    result["acceptance_lines"] = [{key: item.get(key) for key in ("shipment_line_id", "received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity", "difference_reason")} for item in accepted.get("lines", [])]
    if internal:
        result["receipt_id"] = row.receipt_id
        result["receipt_status"] = db.get(CartonReceipt, row.receipt_id).status if row.receipt_id else None
    return result


def documents(db, user, factory):
    """Issued purchase snapshots and supplier-authored notes only, within one authorized factory."""
    supplier = supplier_access(db, user, factory)
    orders = db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.supplier_id == supplier.id,
        CartonOrder.status.in_(VISIBLE_STATES))).all()
    order_ids = [order.id for order in orders]
    result = []
    if order_ids:
        issues = db.scalars(select(CartonPurchaseOrderIssue).where(
            CartonPurchaseOrderIssue.factory_id == factory,
            CartonPurchaseOrderIssue.order_id.in_(order_ids),
            CartonPurchaseOrderIssue.document_type != "LEGACY_BASELINE")
            .order_by(CartonPurchaseOrderIssue.generated_at.desc())).all()
        for issue in issues:
            snapshot = _purchase_order_snapshot(issue)
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
    shipments = db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory, SupplierShipment.supplier_id == supplier.id)
        .order_by(SupplierShipment.created_at.desc())).all()
    for shipment in shipments:
        visible = shipment_out(db, shipment)
        orders_by_no = {}
        for line in visible["lines"]:
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
            "status": shipment.status, "replenishment": False,
            "orders": list(orders_by_no.values()),
            "lines": [{
                **{key: line.get(key, "") for key in (
                    "order_no", "child_no", "packaging_type", "paper_quality", "specification", "unit")},
                "quantity": line["quantity"],
                "received_quantity": str(accepted.get(line["id"], {}).get("received_quantity") or "0"),
            } for line in visible["lines"]],
        })
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
        "SUPPLIER_SHIPMENT_CREATED": ("supplier_shipment", shipment_nos, "送货单已登记"),
        "SUPPLIER_SHIPMENT_RECEIVED": ("supplier_shipment", shipment_nos, "仓库已核实送货"),
        "SUPPLIER_SHIPMENT_NOT_RECEIVED": ("supplier_shipment", shipment_nos, "仓库反馈未收到"),
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
                              "变更前", "本次变化", "变更后", "单位"]),
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
                        line["quantity"], line["unit"],
                    ]
                else:
                    values = [
                        document["factory_id"], document["document_no"], document["date"],
                        document["status"], line["order_no"], order.get("customer_name"),
                        order.get("contract_no"), order.get("customer_po"), order.get("item_no"),
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
    return output.getvalue()


def members(db, user, factory):
    internal_permission(user, factory, "carton_procurement:master_manage", "carton_procurement:order_adjust")
    return [{"id": member.id, "username": account.username, "display_name": account.display_name,
        "status": member.status, "revision": member.revision} for member, account in db.execute(
            select(SupplierMember, AuthUser).join(AuthUser, AuthUser.id == SupplierMember.user_id).where(SupplierMember.factory_id == factory)).all()]


def save_member(db, user, payload: MemberSave):
    internal_permission(user, payload.factory_id, "carton_procurement:master_manage", "carton_procurement:order_adjust")
    if payload.status == "ACTIVE" and authorization_decision(
            user, "carton_procurement:master_manage", payload.factory_id, "pmc-warehouse")[1] != "superadmin":
        raise HTTPException(403, "开通跨厂区供应商账号须由系统管理员操作")
    _lock_receipt_factory(db, payload.factory_id)
    supplier = fixed_supplier(db, payload.factory_id)
    account = db.scalar(select(AuthUser).where(AuthUser.username == payload.username, AuthUser.status == "active"))
    if not account:
        raise HTTPException(404, "请先通过受控账号开通流程创建有效账号，再按准确登录名绑定")
    if payload.status == "ACTIVE":
        context = build_auth_context(db, account)
        if context.role_codes or context.grants or context.permissions:
            raise HTTPException(409, "请使用没有内部业务权限的独立供应商账号，不能将内部员工账号作为供应商账号绑定")
    row = db.scalar(select(SupplierMember).where(SupplierMember.user_id == account.id, SupplierMember.factory_id == payload.factory_id))
    if (row.revision if row else 0) != payload.expected_revision:
        raise HTTPException(409, "供应商成员版本已变更，请刷新")
    if row and row.supplier_id != supplier.id:
        raise HTTPException(409, "已有其他供应商绑定，不能直接改绑")
    if not row:
        row = SupplierMember(id=f"CSM-{uuid4().hex}", user_id=account.id, factory_id=payload.factory_id, supplier_id=supplier.id, revision=0)
        db.add(row)
    row.status = payload.status; row.revision += 1; row.updated_by = user.id; row.updated_at = now_text()
    _audit(db, user, payload.factory_id, "SUPPLIER_MEMBER_CHANGED", "supplier_member", row.id,
        {"user_id": account.id, "username": account.username, "supplier_id": supplier.id, "status": row.status, "reason": payload.reason})
    db.commit()
    return members(db, user, payload.factory_id)


def accept_line(db, user, line_id, payload: CommitmentSave):
    result = accept_lines(db, user, BatchCommitmentSave(factory_id=payload.factory_id, lines=[{
        "order_line_id": line_id, "issue_id": payload.issue_id,
        "expected_revision": payload.expected_revision, "promised_date": payload.promised_date,
    }]))
    return order_out(db, db.get(CartonOrder, result[0]))


def accept_lines(db, user, payload: BatchCommitmentSave):
    _lock_receipt_factory(db, payload.factory_id)
    supplier = supplier_access(db, user, payload.factory_id)
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


def create_shipment(db, user, payload: ShipmentCreate):
    _lock_receipt_factory(db, payload.factory_id)
    supplier = supplier_access(db, user, payload.factory_id)
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
            **{key: str(getattr(line, key)) for key in ("packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency")}})
    row = SupplierShipment(id=f"CSS-{uuid4().hex}", factory_id=payload.factory_id, supplier_id=supplier.id,
        delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(), status="SENT", revision=1,
        request_id=payload.request_id, fingerprint=digest, created_by=user.id, created_at=now_text())
    db.add(row); db.flush()
    for index, item in enumerate(payload.lines):
        db.add(SupplierShipmentLine(id=f"{row.id}-{index+1:03d}", shipment_id=row.id, factory_id=payload.factory_id,
            order_line_id=item.order_line_id, issue_id=item.issue_id, quantity=item.quantity,
            snapshot_json=json.dumps(snapshots[index], ensure_ascii=False)))
    _audit(db, user, payload.factory_id, "SUPPLIER_SHIPMENT_CREATED", "supplier_shipment", row.id,
        {"delivery_note_no": row.delivery_note_no, "lines": [item.model_dump(mode="json") for item in payload.lines]})
    db.commit()
    return shipment_out(db, row)


def receive_shipment(db, user, shipment_id, payload: ShipmentReceive):
    internal_permission(user, payload.factory_id, "carton_procurement:receipt_write", "carton_procurement:inventory_write")
    _lock_receipt_factory(db, payload.factory_id)
    row = db.scalar(select(SupplierShipment).where(SupplierShipment.id == shipment_id, SupplierShipment.factory_id == payload.factory_id))
    if not row:
        raise HTTPException(404, "未找到此厂区的发货单")
    digest = fingerprint(payload)
    if row.status in {"RECEIVED", "NOT_RECEIVED"}:
        if row.confirmed_by == user.id and row.confirmation_request_id == payload.request_id and row.confirmation_fingerprint == digest:
            return shipment_out(db, row, internal=True)
        raise HTTPException(409, "此发货单已确认收料，不可重复入库")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "发货单版本已变更，请刷新")
    source = list(db.scalars(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id == row.id)).all())
    supplied = {item.shipment_line_id: item for item in payload.lines}
    if len(supplied) != len(payload.lines) or set(supplied) != {item.id for item in source}:
        raise HTTPException(422, "必须逐条核对整张发货单，不可漏行或混入其他单据")
    reject_all = all(item.received_quantity == 0 for item in payload.lines)
    receipt_lines = []
    for shipped in source:
        item = supplied[shipped.id]
        line = db.get(CartonOrderLine, shipped.order_line_id)
        order = supplier_order(db, line.order_id, payload.factory_id, row.supplier_id)
        if order.status not in OPEN_STATES and not reject_all:
            raise HTTPException(409, "关联订单当前不允许收料")
        if item.received_quantity > shipped.quantity:
            raise HTTPException(422, "实收不能超过本次发货数量")
        effective = item.received_quantity - item.damaged_quantity - item.rejected_quantity - item.unusable_quantity
        if effective < 0:
            raise HTTPException(422, "不可用数量不能超过实收")
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
        receipt = None
        if not reject_all:
            receipt = _create_receipt(db, CartonReceiptCreate(factory_id=payload.factory_id, supplier_id=row.supplier_id,
                delivery_note_no=row.delivery_note_no, delivery_date=row.delivery_date, acceptance_date=payload.acceptance_date.isoformat(),
                note=f"供应商发货单 {row.id}，逐纸品核实实际收到，差异保留待收需求", lines=receipt_lines), user, commit=False, supplier_shipment_id=row.id)
            confirm_receipt(db, receipt.id, CartonReceiptConfirmRequest(factory_id=payload.factory_id, expected_revision=receipt.revision), user, commit=False)
        # The core lock helper expires ORM state, so update the shipment only after core posting.
        row.status = "NOT_RECEIVED" if reject_all else "RECEIVED"; row.revision += 1; row.receipt_id = receipt.id if receipt else None
        row.confirmed_by = user.id; row.confirmed_at = now_text()
        row.confirmation_request_id = payload.request_id; row.confirmation_fingerprint = digest
        row.acceptance_json = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        _audit(db, user, payload.factory_id, "SUPPLIER_SHIPMENT_NOT_RECEIVED" if reject_all else "SUPPLIER_SHIPMENT_RECEIVED", "supplier_shipment", row.id,
            {"receipt_id": receipt.id if receipt else None, "acceptance": payload.model_dump(mode="json")})
        db.commit()
        return shipment_out(db, row, internal=True)
    except Exception:
        db.rollback()
        raise


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
