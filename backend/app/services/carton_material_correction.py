"""Bilateral, immutable material corrections. No new demand or stock is posted."""
import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrder, CartonOrderLine, CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierCommitment, SupplierShipment, SupplierShipmentLine

ENTITY = 'carton_material_correction'
FIELDS = ('packaging_type', 'paper_quality', 'specification', 'dimension_unit')
HOLD = {'PENDING', 'RETURNED'}


def material(line):
    return {key: getattr(line, key) for key in FIELDS}


def records(db, factory, order_id=None):
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == ENTITY).order_by(CartonAuditEvent.sequence)
    result = {}
    for event in db.scalars(query):
        data = json.loads(event.detail_json)
        if 'record' in data:
            result.pop(event.entity_id, None)
            result[event.entity_id] = data['record']
    return [row for row in result.values() if not order_id or row['order_id'] == order_id]


def blocked_lines(db, factory, ids):
    ids = set(ids)
    return {row['order_line_id']: row for row in records(db, factory)
        if row['status'] in HOLD and row['order_line_id'] in ids} if ids else {}


def guard_lines(db, factory, ids):
    held = blocked_lines(db, factory, ids)
    if held:
        raise HTTPException(409, '纸品资料更正待双方确认，暂停本纸品发货和正式入库；请处理资料更正待办')


def guard_issue(db, order):
    if any(row['status'] in HOLD for row in records(db, order.factory_id, order.id)):
        raise HTTPException(409, '订单有资料更正待核实，请先完成或撤回更正，再生成其他采购变更')


def internal_access(db, user, factory, *, write=False):
    # Reuse canonical warehouse adjustment permissions; supplier rights never grant these.
    from app.api.carton_procurement import _ensure_permission, _ensure_order_adjustment_permission
    _ensure_permission(db, user, 'carton_procurement:read', factory)
    if write:
        _ensure_permission(db, user, 'carton_procurement:order_write', factory)
        _ensure_order_adjustment_permission(db, user, factory)


def get_order(db, factory, number):
    from app.services.carton_procurement import get_order_by_no
    return get_order_by_no(db, factory, number)


def context(db, user, factory, number):
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    from app.services.carton_customer_assignment import ensure_customer_operation
    internal_access(db, user, factory)
    order = get_order(db, factory, number)
    ensure_customer_operation(db, user, factory, order.customer_code)
    issue = portal.latest_issue(db, order)
    return {'order_no': number, 'factory_id': factory, 'revision': order.revision,
        'issue_id': issue.id if issue else '', 'status': order.status,
        'lines': [{'id': line.id, **material(line)} for line in core._order_lines(db, order.id)],
        'records': records(db, factory, order.id)}


def fingerprint(payload, target):
    return hashlib.sha256(json.dumps([target, payload.model_dump(mode='json')], sort_keys=True).encode()).hexdigest()


def replay(db, user, payload, target):
    key = 'CAE-MC-' + hashlib.sha256(json.dumps([payload.factory_id, user.id, payload.request_id]).encode()).hexdigest()
    event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == key))
    digest = fingerprint(payload, target)
    if event:
        data = json.loads(event.detail_json)
        if data.get('fingerprint') != digest:
            raise HTTPException(409, '提交标识已用于其他内容，请核对原结果')
        return key, digest, data['record']
    return key, digest, None


def save_event(db, user, factory, row, key, digest, event_type):
    from app.services.carton_procurement import _audit
    event = _audit(db, user, factory, event_type, ENTITY, row['id'], {'record': row, 'fingerprint': digest})
    event.id = key


def create(db, user, number, payload):
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    from app.services.carton_customer_assignment import ensure_customer_operation
    from app.services.carton_material_identity import dimension_unit
    core._lock_receipt_factory(db, payload.factory_id)
    internal_access(db, user, payload.factory_id, write=True)
    order = get_order(db, payload.factory_id, number)
    ensure_customer_operation(db, user, order.factory_id, order.customer_code)
    key, digest, prior = replay(db, user, payload, number)
    if prior:
        return prior
    if order.revision != payload.expected_revision:
        raise HTTPException(409, '订单已变化，请刷新后重新核实')
    issue = portal.executable(db, order, payload.issue_id)
    if any(row['status'] in HOLD for row in records(db, order.factory_id, order.id)):
        raise HTTPException(409, '此订单已有待处理更正，请先完成或撤回后再提出')
    from app.services.carton_order_split import guard_order_change
    guard_order_change(db, order)
    line = db.get(CartonOrderLine, payload.order_line_id)
    if not line or line.order_id != order.id or line.factory_id != order.factory_id or line.required_quantity <= 0:
        raise HTTPException(404, '未找到本订单有效纸品')
    if portal.blocked_replacement_lines(db, order.factory_id, [line.id]):
        raise HTTPException(409, '此纸品有补单待处理，请先核实补单')
    if db.scalar(select(CartonReceiptLine.id).join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id).where(
            CartonReceipt.factory_id == order.factory_id, CartonReceipt.status == 'PENDING_CONFIRMATION',
            CartonReceiptLine.order_line_id == line.id).limit(1)):
        raise HTTPException(409, '此纸品有待确认收料草稿，请先作废草稿后提出更正')
    after = payload.after.model_dump()
    if material(line) == after:
        raise HTTPException(422, '更正前后资料相同')
    embedded = dimension_unit(after['specification'])
    if not embedded and len(after['specification'] + ' ' + after['dimension_unit']) > 255:
        raise HTTPException(422, '规格加尺寸单位不能超过 255 字，请精简规格')
    if embedded and embedded != after['dimension_unit']:
        raise HTTPException(422, '规格内单位与所选单位冲突，请核对')
    row = dict(id='CMC-' + uuid4().hex, factory_id=order.factory_id, supplier_id=order.supplier_id,
        order_id=order.id, order_no=number, contract_no=order.contract_no, item_no=order.item_no,
        order_line_id=line.id, issue_id=issue.id, document_no=issue.document_no,
        before=material(line), after=after, reason=payload.reason, status='PENDING', revision=1,
        created_by=user.id, created_by_name=user.display_name, created_at=core.now_text(),
        resolved_by_name='', resolved_at='', response_note='', corrected_document_no='')
    order.revision += 1
    order.updated_at = core.now_text()
    save_event(db, user, order.factory_id, row, key, digest, 'MATERIAL_CORRECTION_REQUESTED')
    db.commit()
    return row


def supplier_records(db, user, factory):
    from app.services import carton_supplier_portal as portal
    supplier = portal.supplier_access(db, user, factory)
    visible = set(db.scalars(select(CartonOrder.id).where(CartonOrder.factory_id == factory,
        CartonOrder.supplier_id == supplier.id, CartonOrder.deleted_at.is_(None), CartonOrder.status.in_(portal.VISIBLE_STATES))))
    return [row for row in records(db, factory) if row['supplier_id'] == supplier.id and row['order_id'] in visible]


def act(db, user, identifier, payload, *, supplier=False):
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    from app.services.carton_customer_assignment import ensure_customer_operation
    core._lock_receipt_factory(db, payload.factory_id)
    if supplier:
        own = portal.supplier_access(db, user, payload.factory_id, 'carton_supplier:approve')
        if payload.action == 'WITHDRAW':
            raise HTTPException(403, '供应商不能撤回仓库申请')
    else:
        internal_access(db, user, payload.factory_id, write=True)
        if payload.action != 'WITHDRAW':
            raise HTTPException(403, '须由供应商确认或退回，仓库不能代替供应商确认')
    row = next((dict(r) for r in records(db, payload.factory_id) if r['id'] == identifier), None)
    if not row:
        raise HTTPException(404, '未找到此厂区的更正申请')
    order = db.get(CartonOrder, row['order_id'])
    if supplier:
        if not order or order.deleted_at:
            raise HTTPException(404, '订单已不存在')
        portal.supplier_order(db, order.id, payload.factory_id, own.id)
        if row['supplier_id'] != own.id:
            raise HTTPException(404, '未找到本供应商的更正申请')
        if row['created_by'] == user.id:
            raise HTTPException(403, '发起人不能代替另一方确认，请由供应商的另一位授权人员处理')
    else:
        ensure_customer_operation(db, user, order.factory_id, order.customer_code)
    key, digest, prior = replay(db, user, payload, identifier)
    if prior:
        return prior
    if row['revision'] != payload.expected_revision or row['status'] not in HOLD:
        raise HTTPException(409, '更正申请已处理或版本已变化，请刷新')
    if supplier and row['status'] != 'PENDING':
        raise HTTPException(409, '申请已退回仓库核实，请等待重新发起')
    if payload.action == 'WITHDRAW' and not payload.verified:
        raise HTTPException(422, '请确认撤回后恢复原资料执行')
    if payload.action == 'APPROVE':
        if not payload.verified:
            raise HTTPException(422, '请明确确认已核对更正资料和已生产／已到货实物')
        old = portal.executable(db, order, row['issue_id'])
        line = db.get(CartonOrderLine, row['order_line_id'])
        if not line or material(line) != row['before']:
            raise HTTPException(409, '原纸品资料已变化，不能确认旧申请')
        for field, value in row['after'].items():
            setattr(line, field, value)
        order.revision += 1
        order.updated_at = core.now_text()
        order.updated_by = user.id
        order.updated_by_name = user.display_name
        # Only this narrow approved path may issue changed material without internal
        # supplier impersonation. The underlying builder performs no permission bypass.
        corrected = issue_correction(db, user, order, old, row)
        row['corrected_document_no'] = corrected.document_no
        for commitment in db.scalars(select(SupplierCommitment).where(
                SupplierCommitment.factory_id == order.factory_id, SupplierCommitment.issue_id == old.id)):
            commitment.issue_id = corrected.id
            commitment.revision += 1
        # Pending shipments keep their original bytes/snapshots; expire warehouse drafts.
        for shipment in db.scalars(select(SupplierShipment).join(SupplierShipmentLine,
                SupplierShipmentLine.shipment_id == SupplierShipment.id).where(
                SupplierShipment.factory_id == order.factory_id, SupplierShipmentLine.order_line_id == line.id,
                SupplierShipment.status.in_(['SENT', 'RECEIVED']))).unique():
            receipt = db.get(CartonReceipt, shipment.receipt_id) if shipment.receipt_id else None
            if shipment.status == 'SENT' or (receipt and receipt.status == 'REVERSED'):
                shipment.revision += 1
        row['status'] = 'APPROVED'
    else:
        row['status'] = 'RETURNED' if payload.action == 'RETURN' else 'WITHDRAWN'
    row.update(revision=row['revision'] + 1, resolved_by_name=user.display_name,
        resolved_at=core.now_text(), response_note=payload.note)
    save_event(db, user, order.factory_id, row, key, digest, 'MATERIAL_CORRECTION_' + row['status'])
    db.commit()
    return row


def issue_correction(db, user, order, old, row):
    from app.models.carton_procurement import CartonPurchaseOrderIssue
    from app.services import carton_procurement as core
    issues = core._purchase_order_issues(db, order.id)
    snapshot = core._purchase_order_pending_change(order, core._order_lines(db, order.id), old)[3]
    snapshot['material_correction'] = {'id': row['id'], 'order_line_id': row['order_line_id'],
        'before': row['before'], 'after': row['after'], 'reason': row['reason']}
    sequence = max(i.issue_sequence for i in issues) + 1
    count = sum(i.document_type == 'ADJUSTMENT' for i in issues) + 1
    issue = CartonPurchaseOrderIssue(id='CPOI-' + uuid4().hex, factory_id=order.factory_id,
        order_id=order.id, order_no=order.order_no, document_no=f'{order.order_no}-C{count:02d}',
        document_type='ADJUSTMENT', issue_sequence=sequence, source_order_revision=order.revision,
        before_product_quantity=order.product_order_quantity, after_product_quantity=order.product_order_quantity,
        product_quantity_delta=0 if order.product_order_quantity is not None else None,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False), generated_by=user.id,
        generated_by_name=user.display_name, generated_at=core.now_text())
    db.add(issue)
    db.flush()
    core._audit(db, user, order.factory_id, 'PURCHASE_ORDER_ISSUED', 'carton_purchase_order_issue', issue.id,
        {'order_no': order.order_no, 'document_no': issue.document_no, 'document_type': 'ADJUSTMENT',
         'material_correction_id': row['id'], 'product_quantity_delta': '0', 'line_deltas': {line['id']: '0' for line in snapshot['lines']}})
    return issue


def latest_approved(db, factory, line_id):
    rows = [row for row in records(db, factory) if row['order_line_id'] == line_id and row['status'] == 'APPROVED']
    return rows[-1] if rows else None


def receipt_specification(db, line):
    from app.services.carton_material_identity import dimension_unit
    if latest_approved(db, line.factory_id, line.id) and not dimension_unit(line.specification):
        return f'{line.specification} {line.dimension_unit}'.strip()
    return line.specification
