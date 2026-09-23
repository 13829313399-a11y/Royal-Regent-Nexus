"""Supplier-scoped collaboration. All mutations use the existing carton factory lock."""
import hashlib
import json
from decimal import Decimal
from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.auth import AuthUser
from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonSupplier, CartonPurchaseOrderIssue, CartonReceipt
from app.models.carton_supplier_portal import SupplierMember, SupplierCommitment, SupplierShipment, SupplierShipmentLine, SupplierAttachment
from app.schemas.carton_supplier_portal import MemberSave, CommitmentSave, ShipmentCreate, ShipmentReceive
from app.schemas.carton_procurement import CartonReceiptCreate, CartonReceiptLineCreate, CartonReceiptConfirmRequest
from app.services.auth import AuthContext, has_permission_in_scope, build_auth_context
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


def membership(db, user, factory):
    factory = require_carton_factory(factory)
    member = db.scalar(select(SupplierMember).join(CartonSupplier, CartonSupplier.id == SupplierMember.supplier_id).where(
        SupplierMember.user_id == user.id, SupplierMember.factory_id == factory, SupplierMember.status == "ACTIVE",
        CartonSupplier.factory_id == factory, CartonSupplier.status == "ACTIVE"))
    if not member:
        raise HTTPException(403, "账号未绑定此厂区的供应商协同权限")
    return member


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
        supplier_id = membership(db, user, factory).supplier_id
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


def members(db, user, factory):
    internal_permission(user, factory, "carton_procurement:master_manage", "carton_procurement:order_adjust")
    return [{"id": member.id, "username": account.username, "display_name": account.display_name,
        "status": member.status, "revision": member.revision} for member, account in db.execute(
            select(SupplierMember, AuthUser).join(AuthUser, AuthUser.id == SupplierMember.user_id).where(SupplierMember.factory_id == factory)).all()]


def save_member(db, user, payload: MemberSave):
    internal_permission(user, payload.factory_id, "carton_procurement:master_manage", "carton_procurement:order_adjust")
    _lock_receipt_factory(db, payload.factory_id)
    supplier = fixed_supplier(db, payload.factory_id)
    account = db.scalar(select(AuthUser).where(AuthUser.username == payload.username, AuthUser.status == "active"))
    if not account:
        raise HTTPException(404, "请先通过受控账号开通流程创建有效账号，再按准确登录名绑定")
    if payload.status == "ACTIVE" and build_auth_context(db, account).permissions:
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
    _lock_receipt_factory(db, payload.factory_id)
    member = membership(db, user, payload.factory_id)
    line = db.get(CartonOrderLine, line_id)
    if not line or line.factory_id != payload.factory_id:
        raise HTTPException(404, "未找到纸品子单")
    order = supplier_order(db, line.order_id, payload.factory_id, member.supplier_id)
    executable(db, order, payload.issue_id)
    if line.required_quantity <= 0:
        raise HTTPException(409, "此纸品需求已取消")
    row = db.get(SupplierCommitment, line_id)
    if (row.revision if row else 0) != payload.expected_revision:
        raise HTTPException(409, "接单承诺版本已变更，请刷新")
    if not row:
        row = SupplierCommitment(order_line_id=line.id, factory_id=payload.factory_id, revision=0)
        db.add(row)
    row.issue_id = payload.issue_id; row.promised_date = payload.promised_date.isoformat(); row.revision += 1
    row.accepted_by = user.id; row.accepted_at = now_text()
    _audit(db, user, payload.factory_id, "SUPPLIER_PAPER_ACCEPTED", "carton_order", order.id,
        {"line_id": line.id, "issue_id": row.issue_id, "promised_date": row.promised_date, "revision": row.revision})
    db.commit()
    return order_out(db, order)


def create_shipment(db, user, payload: ShipmentCreate):
    _lock_receipt_factory(db, payload.factory_id)
    member = membership(db, user, payload.factory_id)
    digest = fingerprint(payload)
    previous = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == payload.factory_id,
        SupplierShipment.created_by == user.id, SupplierShipment.request_id == payload.request_id))
    if previous:
        if previous.supplier_id != member.supplier_id or previous.fingerprint != digest:
            raise HTTPException(409, "此发货提交标识已用于其他内容")
        return shipment_out(db, previous)
    if db.scalar(select(SupplierShipment.id).where(SupplierShipment.factory_id == payload.factory_id,
        SupplierShipment.supplier_id == member.supplier_id, SupplierShipment.delivery_note_no == payload.delivery_note_no)):
        raise HTTPException(409, "此供应商送货单号已经登记")
    if db.scalar(select(CartonReceipt.id).where(CartonReceipt.factory_id == payload.factory_id,
        CartonReceipt.supplier_id == member.supplier_id, CartonReceipt.delivery_note_no == payload.delivery_note_no)):
        raise HTTPException(409, "此送货单已有收料记录，请核对原单，不可再次登记发货")
    ids = [item.order_line_id for item in payload.lines]
    authorized_ids = set(db.scalars(select(CartonOrderLine.id).join(CartonOrder,
        CartonOrder.id == CartonOrderLine.order_id).where(CartonOrderLine.id.in_(ids),
            CartonOrderLine.factory_id == payload.factory_id, CartonOrder.factory_id == payload.factory_id,
            CartonOrder.supplier_id == member.supplier_id, CartonOrder.status.in_(VISIBLE_STATES))).all())
    if authorized_ids != set(ids):
        raise HTTPException(404, "未找到可访问的纸品子单")
    fulfilled = fulfilled_by_line(db, ids); reserved = outstanding(db, ids); pending = _pending_received_by_line(db, ids)
    blocked = blocked_replacement_lines(db, payload.factory_id, ids)
    snapshots = []
    for item in payload.lines:
        line = db.get(CartonOrderLine, item.order_line_id)
        if not line or line.factory_id != payload.factory_id:
            raise HTTPException(404, "未找到纸品子单")
        order = supplier_order(db, line.order_id, payload.factory_id, member.supplier_id)
        issue = executable(db, order, item.issue_id)
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
    row = SupplierShipment(id=f"CSS-{uuid4().hex}", factory_id=payload.factory_id, supplier_id=member.supplier_id,
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
        member = membership(db, user, factory)
    row = db.scalar(select(SupplierAttachment).where(SupplierAttachment.id == attachment_id, SupplierAttachment.factory_id == factory))
    if not row:
        raise HTTPException(404, "未找到附件")
    if not internal:
        supplier_order(db, row.order_id, factory, member.supplier_id)
    return row
