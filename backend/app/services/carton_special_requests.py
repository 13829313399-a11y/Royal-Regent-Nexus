"""Versioned lightweight requests; all stock and payables still originate in receipts."""
import hashlib
import json
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.auth import AuthUser, SystemNotification
from app.models.carton_procurement import CartonAuditEvent, CartonCustomer, CartonReceipt, CartonReceiptLine
from app.models.carton_master import CartonMasterRecord
from app.models.carton_special_requests import (SpecialRequest, SpecialLine, SpecialVersion, SpecialAttachment,
    SpecialMessage, SpecialShipment, SpecialShipmentLine, SpecialReceiptLink)
from app.schemas import carton_special_requests as schema
from app.schemas.carton_procurement import CartonReceiptCreate, CartonReceiptLineCreate, CartonReceiptConfirmRequest
from app.services import carton_procurement as core, carton_supplier_portal as portal, carton_positions as positions
from app.services.auth import build_auth_context, authorization_decision


def uid(prefix):
    return prefix + uuid4().hex


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def allowed(user, factory, permission):
    return any(authorization_decision(user, "carton_procurement:" + permission, factory, dept)[0]
               for dept in core.CARTON_DEPARTMENTS)


def can_submit(user, factory):
    return allowed(user, factory, "special_request_submit") or allowed(user, factory, "order_write")


def can_receive(user, factory):
    return allowed(user, factory, "receipt_write") and allowed(user, factory, "inventory_write")


def customer_access(db, user, row):
    if row.customer_code:
        ensure_customer_operation(db, user, row.factory_id, row.customer_code)


def ensure_customer_operation(db, user, factory, customer_code):
    """Current customer responsibility, with canonical denies in this new domain."""
    if allowed(user, factory, "order_adjust"):
        return
    from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment
    assignees = set(db.scalars(select(Assignment.user_id).join(CartonCustomer,
        CartonCustomer.id == Assignment.customer_id).where(Assignment.factory_id == factory,
            CartonCustomer.factory_id == factory, CartonCustomer.customer_code == customer_code.strip().upper())))
    if assignees and user.id not in assignees:
        raise HTTPException(403, "该客户由其他人员负责，请联系客户负责人发送或确认需求")


def supplier(db, user, factory, permission="carton_supplier:read"):
    core.require_carton_factory(factory)
    if not portal.supplier_permission(user, permission, factory):
        raise HTTPException(403, "没有本厂供应商协同权限")
    return portal.fixed_supplier(db, factory)


def access(db, user, factory, identifier=None, *, external=False):
    core.require_carton_factory(factory)
    if external:
        vendor = supplier(db, user, factory)
    elif not (can_submit(user, factory) or can_receive(user, factory) or allowed(user, factory, "read")):
        raise HTTPException(403, "没有本厂纸品需求权限")
    row = db.get(SpecialRequest, identifier) if identifier else None
    if identifier:
        if row is None or row.factory_id != factory or (external and (row.supplier_id != vendor.id or row.status == "SUBMITTED" or not is_published(db, row))):
            raise HTTPException(404, "未找到此厂区纸品需求")
        if not external:
            if not (allowed(user, factory, "order_write") or can_receive(user, factory)) and row.created_by != user.id:
                raise HTTPException(403, "只可查看自己提交的纸品需求")
            customer_access(db, user, row)
    return row


def locked_actor(db, user, factory):
    # Same IAM-before-factory order used by scoped mutable domains.
    from app.services.identity_policy import lock_mutation
    lock_mutation(db)
    core._lock_receipt_factory(db, factory)
    actor = db.get(AuthUser, user.id)
    if actor is None or actor.status != "active":
        raise HTTPException(403, "账号已停用")
    return build_auth_context(db, actor)


def lines(db, row):
    return list(db.scalars(select(SpecialLine).where(SpecialLine.request_id == row.id).order_by(SpecialLine.line_no)))


def attachments(db, row):
    return list(db.scalars(select(SpecialAttachment).where(SpecialAttachment.request_id == row.id).order_by(SpecialAttachment.version)))


def next_attachment_version(db, row):
    # Attachment ordering is independent of the immutable procurement revision.
    saved = [file.version for file in attachments(db, row)]
    pending = [file.version for file in db.new if isinstance(file, SpecialAttachment) and file.request_id == row.id]
    return max([row.revision, *saved, *pending]) + 1


def line_out(line):
    return {key: (str(getattr(line, key)) if key in {"quantity", "unit_price"} else getattr(line, key)) for key in
        ("id", "line_no", "item_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "quantity", "unit", "unit_price",
         "mark_mode", "mark_attachment_id", "mark_asset_id", "mark_asset_revision")} | {
        "mark_ready": line.mark_mode == "NONE" or bool(line.mark_mode in {"EXISTING", "UPLOAD"} and line.mark_attachment_id)}


def snapshot(db, row):
    confirmed = {}
    selected = {paper.mark_attachment_id for paper in lines(db, row) if paper.mark_attachment_id}
    for file in attachments(db, row):
        if file.role == "CONFIRMED" and (not file.line_id or file.id in selected):
            confirmed[file.id] = {"id": file.id, "line_id": file.line_id, "filename": file.filename, "sha256": file.sha256}
    return {key: getattr(row, key) for key in ("kind", "title", "requester_name", "workshop_id", "customer_code",
        "customer_name", "purpose", "required_date", "pricing_kind", "promised_date", "status")} | {
        "lines": [line_out(line) for line in lines(db, row)], "material_manifest": list(confirmed.values())}


def version(db, user, row, action, *, execution=False, reason=""):
    row.revision += 1
    row.updated_at = core.now_text()
    db.flush()
    event = SpecialVersion(id=uid("CSV-"), factory_id=row.factory_id, request_id=row.id, revision=row.revision,
        action=action, actor_id=user.id, actor_name=user.display_name, created_at=row.updated_at, snapshot_json=pack(snapshot(db, row) | ({"reason": reason} if reason else {})))
    db.add(event)
    if execution:
        row.current_version_id = event.id
    db.flush()
    return event


def replay_id(user, payload):
    return "CAE-CS-" + hashlib.sha256(f"{payload.factory_id}:{user.id}:{payload.request_id}".encode()).hexdigest()


def replay(db, user, payload, action, identifier="", extra=None):
    data = payload.model_dump(mode="json")
    # New default continuation controls are equivalent to pre-upgrade payloads.
    for body in [data, *data.get("special", [])]:
        if body.get("remaining_action") == "WAIT": body.pop("remaining_action", None)
        if body.get("close_reason") == "": body.pop("close_reason", None)
        for line in body.get("lines", []):
            if line.get("close_remaining") is False: line.pop("close_remaining", None)
    for line in (data.get("formal") or {}).get("lines", []):
        if line.get("close_remaining") is False: line.pop("close_remaining", None)
    # The optional formal receipt bridge must preserve older unified retries.
    for line in (data.get("formal") or {}).get("lines", []):
        if line.get("replenishment_issue_id") is None:
            line.pop("replenishment_issue_id", None)
    digest = hashlib.sha256(pack({"action": action, "id": identifier, "payload": data, "extra": extra}).encode()).hexdigest()
    event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == replay_id(user, payload)))
    if event:
        saved = json.loads(event.detail_json)
        if saved["fingerprint"] != digest:
            # New optional fields must not invalidate a proven pre-upgrade retry.
            # Only fields omitted by this client may be removed; explicit new
            # choices still participate in the content-bound identity.
            legacy = data
            for key in ("received_kind", "workshop_id", "requester_name"):
                if isinstance(payload, schema.Receive) and key not in payload.model_fields_set:
                    legacy.pop(key, None)
            for model, data in zip(getattr(payload, "lines", []), legacy.get("lines", [])):
                for key in ("mark_mode", "free_confirmed", "price_action", "price_reason", "zero_price_kind"):
                    if key not in model.model_fields_set: data.pop(key, None)
                if isinstance(model, schema.ReceiveLine) and "unit_price" not in model.model_fields_set:
                    data.pop("unit_price", None)
            old_digest = hashlib.sha256(pack({"action": action, "id": identifier, "payload": legacy, "extra": extra}).encode()).hexdigest()
            if saved["fingerprint"] != old_digest:
                raise HTTPException(409, "此提交标识已用于不同操作或内容")
        return digest, saved["response"]
    return digest, None


def finish(db, user, payload, row, action, digest, *, external=False, commit=True, response_extra=None):
    response = detail(db, user, row.factory_id, row.id, external=external)
    response.update(response_extra or {})
    event = core._audit(db, user, row.factory_id, "SPECIAL_" + action, "carton_special_request", row.id,
        {"fingerprint": digest, "request_id": payload.request_id, "response": response})
    event.id = replay_id(user, payload)
    if commit: db.commit()
    else: db.flush()
    return response


def state_counts(db, row):
    shipped = list(db.scalars(select(SpecialShipmentLine).join(SpecialShipment,
        SpecialShipment.id == SpecialShipmentLine.shipment_id).where(SpecialShipment.request_id == row.id)))
    received, consumed, receipt_rows = {}, {}, {}
    for link, paper, receipt in db.execute(select(SpecialReceiptLink, CartonReceiptLine, CartonReceipt)
        .join(CartonReceiptLine, CartonReceiptLine.id == SpecialReceiptLink.receipt_line_id)
        .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(SpecialReceiptLink.shipment_line_id.in_([line.id for line in shipped]))).all() if shipped else []:
        receipt_rows[receipt.id] = receipt
        if receipt.status == "POSTED":
            received[link.shipment_line_id] = received.get(link.shipment_line_id, Decimal(0)) + paper.effective_quantity
            consumed[link.shipment_line_id] = consumed.get(link.shipment_line_id, Decimal(0)) + paper.received_quantity
    from app.services.carton_special_receiving import closed_quantities
    for key, value in closed_quantities(db, row.factory_id, [paper.shipment_id for paper in shipped]).items():
        consumed[key] = consumed.get(key, Decimal(0)) + value
    by_request = {}
    for paper in shipped:
        by_request[paper.request_line_id] = by_request.get(paper.request_line_id, Decimal(0)) + received.get(paper.id, Decimal(0))
    return shipped, received, consumed, by_request, receipt_rows


def deleted_predicate():
    return select(SpecialVersion.id).where(SpecialVersion.request_id == SpecialRequest.id,
        SpecialVersion.factory_id == SpecialRequest.factory_id, SpecialVersion.action == "DELETED").exists()


def is_published(db, row):
    return row.origin == "SUPPLIER_EXTRA" or row.kind == "SUPPLIER_GIFT" or bool(db.scalar(select(SpecialVersion.id).where(
        SpecialVersion.factory_id == row.factory_id, SpecialVersion.request_id == row.id,
        SpecialVersion.action == "SEND").limit(1)))


def deletion_allowed(db, user, row):
    if not allowed(user, row.factory_id, "order_write") or not (
        allowed(user, row.factory_id, "inventory_write") or allowed(user, row.factory_id, "order_adjust")):
        return False
    if is_published(db, row):
        from app.services.carton_supplier_changes import special_confirmation
        return row.status == "CANCELLED" and special_confirmation(db, row)["status"] == "CANCEL_ACKNOWLEDGED"
    if row.status == "CANCELLED": return True
    return row.origin == "INTERNAL" and not db.scalar(select(SpecialShipment.id).where(SpecialShipment.request_id == row.id).limit(1)) \
        and not db.scalar(select(SpecialVersion.id).where(SpecialVersion.request_id == row.id, SpecialVersion.action == "QUOTE").limit(1)) \
        and not db.scalar(select(SpecialAttachment.id).where(SpecialAttachment.request_id == row.id).limit(1))


def flags(db, user, row, external):
    from app.services.carton_supplier_changes import special_confirmation
    confirmation = special_confirmation(db, row)
    manager = not external and allowed(user, row.factory_id, "order_write")
    from app.services.carton_mark_library import CARTON_MARK_WRITE_DEPARTMENTS
    from app.services.auth import authorization_decision
    mark_writer = not external and any(authorization_decision(user, 'carton_mark:template_upload', row.factory_id, dept)[0]
        for dept in CARTON_MARK_WRITE_DEPARTMENTS)
    active = row.status not in {"CANCELLED", "COMPLETED"}
    result = dict(can_edit=not external and active and row.status == "SUBMITTED" and (manager or row.created_by == user.id),
        can_confirm=manager and row.status == "SUBMITTED",
        can_adjust=manager and active and row.status != "SUBMITTED" and row.origin not in {"SUPPLIER_EXTRA", "REPLENISHMENT"}
        and row.kind in {"SAMPLE", "WORKSHOP_MISC"},
        can_append=manager and row.status not in {"SUBMITTED", "CANCELLED"} and row.origin not in {"SUPPLIER_EXTRA", "REPLENISHMENT"}
        and row.kind in {"SAMPLE", "WORKSHOP_MISC"},
        can_manual_receive=not external and can_receive(user, row.factory_id) and row.kind in {"SAMPLE", "WORKSHOP_MISC"} and row.status in {"SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED"} and row.origin != "SUPPLIER_EXTRA",
        can_send=manager and row.status == "SUBMITTED", can_approve=manager and row.status == "QUOTED",
        can_cancel=manager and active, can_quote=external and active and row.status in {"SENT", "QUOTED"}
        and portal.supplier_permission(user, "carton_supplier:approve", row.factory_id),
        can_ship=external and row.status in {"SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED"}
        and confirmation["status"] in {"ACCEPTED", "SUPPLIER_ORIGIN"}
        and portal.supplier_permission(user, "carton_supplier:edit", row.factory_id),
        can_receive=not external and can_receive(user, row.factory_id),
        can_attach=row.status != 'CANCELLED' and (manager or mark_writer or (not external and row.created_by == user.id) or
            (external and portal.supplier_permission(user, "carton_supplier:edit", row.factory_id))),
        can_message=not external or portal.supplier_permission(user, "carton_supplier:edit", row.factory_id),
        can_confirm_material=manager and active,
        can_delete=not external and deletion_allowed(db, user, row))
    from app.services import carton_special_stock
    stock_writer = manager and allowed(user, row.factory_id, "inventory_write")
    result.update(can_return_stock=stock_writer and carton_special_stock.eligible(db, row),
        can_replenish=stock_writer and carton_special_stock.eligible(db, row),
        can_undo_replenish=stock_writer and row.origin == carton_special_stock.ORIGIN and not carton_special_stock.undo_blockers(db, row, carton_special_stock.replacement(db, row)))
    if row.origin == carton_special_stock.ORIGIN:
        for key in ("can_edit", "can_confirm", "can_adjust", "can_append", "can_send", "can_cancel", "can_delete", "can_confirm_material"):
            result[key] = False
    if db.scalar(select(SpecialVersion.id).where(SpecialVersion.request_id == row.id, SpecialVersion.action == "DELETED").limit(1)):
        return dict.fromkeys(result, False)
    return result


def delete_request(db, user, identifier, payload, *, commit=True):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier)
    if not allowed(user, row.factory_id, "order_write") or not (
        allowed(user, row.factory_id, "inventory_write") or allowed(user, row.factory_id, "order_adjust")):
        raise HTTPException(403, "只有本厂主管或仓管可删除订单")
    digest, saved = replay(db, user, payload, "DELETE", identifier)
    if saved: return saved
    require_revision(row, payload)
    if not flags(db, user, row, False)["can_delete"]:
        raise HTTPException(409, "已发布订单须先取消并取得供应商收到当前停止通知的回执，才能归档删除")
    # Keep every source row and immutable batch; only remove it from order lists.
    row.status = "CANCELLED"
    version(db, user, row, "DELETED", execution=True, reason=payload.reason)
    return finish(db, user, payload, row, "DELETED", digest, response_extra={"deleted": True}, commit=commit)


def detail(db, user, factory, identifier, *, external=False, mark_assets_by_order=None):
    row = access(db, user, factory, identifier, external=external)
    from app.services.carton_replenishment_receipts import receipt_links
    receipt_price_links = receipt_links(db, factory) if external else {}
    shipped, received, consumed, received_by_request, receipt_rows = state_counts(db, row)
    response = {key: getattr(row, key) for key in ("id", "factory_id", "request_no", "kind", "title", "requester_name",
        "customer_code", "customer_name", "workshop_id", "purpose", "required_date", "status", "revision", "current_version_id",
        "quote_version_id", "pricing_kind", "promised_date", "created_by", "created_at", "updated_at", "origin")}
    response["deleted"] = bool(db.scalar(select(SpecialVersion.id).where(SpecialVersion.request_id == row.id, SpecialVersion.action == "DELETED").limit(1)))
    from app.services.carton_supplier_changes import special_confirmation
    response["supplier_confirmation"] = special_confirmation(db, row)
    from app.services.carton_special_stock import replacement_out
    response["replacement"] = replacement_out(db, row, user=user, external=external)
    response["lines"] = [line_out(line) | {"received_quantity": str(received_by_request.get(line.id, Decimal(0))),
        "remaining_quantity": str(max(Decimal(0), line.quantity - received_by_request.get(line.id, Decimal(0)))),
        "remaining_to_ship": str(max(Decimal(0), line.quantity - received_by_request.get(line.id, Decimal(0)) -
            sum((paper.quantity - consumed.get(paper.id, Decimal(0)) for paper in shipped if paper.request_line_id == line.id), Decimal(0))))} for line in lines(db, row)]
    response["attachments"] = [{key: getattr(file, key) for key in ("id", "role", "filename", "media_type", "sha256", "size", "version", "created_by", "created_at", "line_id")} for file in attachments(db, row)]
    from app.services.carton_special_marks import associated_files
    if mark_assets_by_order is None: mark_assets_by_order = associated_files(db, user, factory, external=external, request_ids={row.id})
    response['mark_assets'] = mark_assets_by_order.get(row.id, [])
    response["messages"] = [{key: getattr(message, key) for key in ("id", "body", "actor_id", "actor_name", "audience", "created_at")}
        for message in db.scalars(select(SpecialMessage).where(SpecialMessage.request_id == row.id).order_by(SpecialMessage.created_at, SpecialMessage.id))]
    response["history"] = [{key: getattr(event, key) for key in ("id", "revision", "action", "actor_id", "actor_name", "created_at")} |
        {"snapshot": json.loads(event.snapshot_json)} for event in db.scalars(select(SpecialVersion).where(SpecialVersion.request_id == row.id).order_by(SpecialVersion.revision))]
    from app.services.carton_special_receiving import closed_quantities, closures
    closed = closed_quantities(db, factory, [paper.shipment_id for paper in shipped])
    response["shipments"] = []
    for shipment in db.scalars(select(SpecialShipment).where(SpecialShipment.request_id == row.id).order_by(SpecialShipment.created_at)):
        papers = [paper for paper in shipped if paper.shipment_id == shipment.id]
        linked_ids = set(db.scalars(select(CartonReceiptLine.receipt_id).join(SpecialReceiptLink,
            SpecialReceiptLink.receipt_line_id == CartonReceiptLine.id).where(SpecialReceiptLink.shipment_line_id.in_([paper.id for paper in papers]))))
        response["shipments"].append({key: getattr(shipment, key) for key in ("id", "version_id", "delivery_note_no", "delivery_date", "created_at")} |
            {"source_origin": "WAREHOUSE_MANUAL" if any(json.loads(paper.snapshot_json).get("source_origin") == "WAREHOUSE_MANUAL" for paper in papers) else "SUPPLIER",
             "lines": [{"id": paper.id, "request_line_id": paper.request_line_id, "quantity": str(paper.quantity),
                "snapshot": json.loads(paper.snapshot_json), "gross_received_quantity": str(consumed.get(paper.id, Decimal(0)) - closed.get(paper.id, Decimal(0))),
                "closed_quantity": str(closed.get(paper.id, Decimal(0))),
                "effective_received_quantity": str(received.get(paper.id, Decimal(0))),
                "received_quantity": str(received.get(paper.id, Decimal(0))),
                "remaining_quantity": str(max(Decimal(0), paper.quantity - consumed.get(paper.id, Decimal(0))))} for paper in papers],
             "closures": [dict(detail, created_at=event.created_at) for event, detail in closures(db, factory, [shipment.id])],
             "receipts": [{key: getattr(receipt_rows[rid], key) for key in ("id", "receipt_no", "status", "revision", "acceptance_date")} |
                {"lines": [receipt_line_out(paper, external=external, replacement_link=receipt_price_links.get(paper.id)) for paper in core._receipt_lines(db, rid)]} for rid in sorted(linked_ids)]})
    response["permissions"] = flags(db, user, row, external)
    return response


def receipt_line_out(paper, *, external=False, replacement_link=None):
    result = {key: str(getattr(paper, key)) for key in ("id", "delivered_quantity", "received_quantity", "damaged_quantity",
        "rejected_quantity", "unusable_quantity", "effective_quantity", "unit_price", "unit", "packaging_type", "paper_quality", "specification")}
    if not external:
        result["location_allocations"] = json.loads(paper.location_allocations_json or "[]")
    elif replacement_link and replacement_link.get("responsibility") == "SUPPLIER":
        value = replacement_link.get("settlement_unit_price")
        result["unit_price"] = str(value) if value is not None else None
    return result


def workspace(db, user, factory, *, external=False, responsibility_scope="OWN"):
    access(db, user, factory, external=external)
    if responsibility_scope not in {"OWN", "ALL"}: raise HTTPException(422, "客户范围无效")
    items = []
    from app.services.carton_special_marks import associated_files
    mark_assets_by_order = associated_files(db, user, factory, external=external)
    query = select(SpecialRequest).where(SpecialRequest.factory_id == factory, ~deleted_predicate())
    if not external and responsibility_scope == "OWN":
        from app.services.carton_customer_assignment import customer_predicate
        query = query.where(customer_predicate(user, factory, SpecialRequest.customer_code))
    for row in db.scalars(query.order_by(SpecialRequest.updated_at.desc())):
        try:
            items.append(detail(db, user, factory, row.id, external=external, mark_assets_by_order=mark_assets_by_order))
        except HTTPException as error:
            if error.status_code not in {403, 404}: raise
    options = {"customers": [], "workshops": [], "locations": []}
    if not external:
        # Applicants get only the selection vocabulary, never ordinary ledgers.
        for customer in db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id == factory, CartonCustomer.status == "ACTIVE")):
            try: ensure_customer_operation(db, user, factory, customer.customer_code)
            except HTTPException: continue
            options["customers"].append({"customer_code": customer.customer_code, "customer_name": customer.customer_name})
        options["workshops"] = [{"id": row.id, "name": row.code} for row in db.scalars(select(CartonMasterRecord).where(
            CartonMasterRecord.factory_id == factory, CartonMasterRecord.kind == "WORKSHOP", CartonMasterRecord.status == "ACTIVE"))]
        if can_receive(user, factory): options["locations"] = [{"id": item["id"], "label": item["label"]} for item in positions.locations(db, factory) if item["status"] == "ACTIVE"]
    return {"items": items, "total": len(items), "can_create": portal.supplier_permission(user, "carton_supplier:edit", factory) if external else can_submit(user, factory), "options": options}


def require_revision(row, payload):
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "需求版本已变更，请刷新后重试")


def notify(db, row, action, *, audience):
    # Address individual currently authorized users. A generic permission queue
    # would leak a customer-owned request to other customer owners.
    for actor in db.scalars(select(AuthUser).where(AuthUser.status == "active")):
        user = build_auth_context(db, actor)
        try:
            access(db, user, row.factory_id, row.id, external=audience == "SUPPLIER")
        except HTTPException: continue
        permission = "carton_supplier:read" if audience == "SUPPLIER" else (
            "carton_procurement:receipt_write" if action == "SHIPPED" else "carton_procurement:order_write")
        capable = portal.supplier_permission(user, permission, row.factory_id) if audience == "SUPPLIER" else (
            can_receive(user, row.factory_id) if action == "SHIPPED" else allowed(user, row.factory_id, "order_write"))
        if not capable and not (action == "MESSAGE" and row.created_by == user.id): continue
        identifier = "cs-notice:" + hashlib.sha256(f"{row.id}:{row.revision}:{action}:{audience}:{user.id}".encode()).hexdigest()
        if db.get(SystemNotification, identifier): continue
        db.add(SystemNotification(id=identifier, target_user_id=user.id, target_permission="", target_factory_id=row.factory_id,
            target_department="", type="carton_special_request", title="纸品需求协作有新进展", message={"SENT": "新订单待接单，请核对纸品并承诺交期", "ADJUSTED": "订单有调整，请核对最新版本并明确同意或提出异议", "CANCEL": "订单已停止执行，请确认收到停止通知；费用及赔偿仍须另行协商", "QUOTED": "供应商报价待确认", "APPROVED": "收费报价已确认，可制作送货", "SHIPPED": "有送货待验收", "MATERIAL_CHANGED": "确认资料已变更，请核对最新版本后重新接单", "MESSAGE": "有新的协作留言"}.get(action, "请查看需求当前版本"),
            payload_json=pack({"request_id": row.id, "factory_id": row.factory_id, "audience": audience, "required_permission": permission}), status="unread",
            created_at=core.now_text(), read_at="", handled_at=""))


def assign_input(db, user, row, payload):
    from app.services.carton_master import workshop_snapshot
    workshop_snapshot(db, row.factory_id, payload.workshop_id)
    customer = core.get_active_customer(db, row.factory_id, payload.customer_code) if payload.customer_code else None
    if customer: ensure_customer_operation(db, user, row.factory_id, customer.customer_code)
    for key in ("kind", "title", "purpose", "workshop_id"):
        setattr(row, key, getattr(payload, key))
    row.requester_name = payload.requester_name or user.display_name
    row.required_date = payload.required_date.isoformat()
    row.customer_code = customer.customer_code if customer else ""
    row.customer_name = customer.customer_name if customer else ""
    previous = {line.id: line for line in lines(db, row)}
    provided_ids = [line.id for line in payload.lines if line.id]
    if len(provided_ids) != len(set(provided_ids)) or set(provided_ids) - set(previous):
        raise HTTPException(422, "需求明细身份无效或重复")
    for old in previous.values():
        if old.id not in provided_ids: db.delete(old)
    for index, item in enumerate(payload.lines):
        core._unordered_specification(item.specification, item.dimension_unit)
        paper = previous.get(item.id)
        if paper is None:
            paper = SpecialLine(id=uid("CSL-"), factory_id=row.factory_id, request_id=row.id)
            db.add(paper)
        elif paper.mark_mode != item.mark_mode:
            paper.mark_attachment_id = ""; paper.mark_asset_id = ""; paper.mark_asset_revision = 0
        elif any(getattr(paper, key) != getattr(item, key) for key in ("packaging_type", "paper_quality", "specification", "dimension_unit", "item_no")):
            paper.mark_attachment_id = ""; paper.mark_asset_id = ""; paper.mark_asset_revision = 0
        for key, value in item.model_dump(exclude={"id"}).items(): setattr(paper, key, value)
        paper.line_no = index + 1
        paper.unit_price = Decimal(0)


def create(db, user, payload: schema.Create, *, external=False, commit=True):
    user = locked_actor(db, user, payload.factory_id)
    vendor = supplier(db, user, payload.factory_id, "carton_supplier:edit") if external else portal.fixed_supplier(db, payload.factory_id)
    if not external and not can_submit(user, payload.factory_id): raise HTTPException(403, "没有纸品需求提交权限")
    if external != (payload.kind == "SUPPLIER_GIFT"):
        raise HTTPException(422, "赠送只能由供应商发起；内部需求请选择样板或车间杂用")
    digest, saved = replay(db, user, payload, "CREATE")
    if saved:
        access(db, user, payload.factory_id, saved["id"], external=external)
        return saved
    row = SpecialRequest(id=uid("CSR-"), factory_id=payload.factory_id, supplier_id=vendor.id,
        request_no="SP-" + uuid4().hex[:16].upper(), status="SUBMITTED", revision=1, current_version_id="", quote_version_id="",
        pricing_kind="PENDING_QUOTE", promised_date="", created_by=user.id, created_at=core.now_text(), updated_at=core.now_text(),
        kind=payload.kind, title=payload.title, requester_name=payload.requester_name or user.display_name,
        purpose=payload.purpose, required_date=payload.required_date.isoformat())
    db.add(row); db.flush()
    if external:
        if payload.customer_code or payload.workshop_id: raise HTTPException(422, "供应商赠送不指定内部客户或车间")
        assign_input(db, user, row, payload)
        row.pricing_kind = "FREE"; row.status = "READY"; row.promised_date = row.required_date
    else: assign_input(db, user, row, payload)
    event = version(db, user, row, "GIFT_CREATED" if external else "SUBMITTED", execution=True)
    if external: row.quote_version_id = event.id; notify(db, row, "GIFT_CREATED", audience="INTERNAL")
    else: notify(db, row, "SUBMITTED", audience="INTERNAL")
    return finish(db, user, payload, row, "CREATE", digest, external=external, commit=commit)


def update(db, user, identifier, payload: schema.Create, *, adjusting=False, commit=True):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier)
    if not (allowed(user, row.factory_id, "order_write") or (not adjusting and row.created_by == user.id and can_submit(user, row.factory_id))):
        raise HTTPException(403, "没有此订单修改权限")
    action_name = "ADJUST" if adjusting else "UPDATE"
    digest, saved = replay(db, user, payload, action_name, identifier)
    if saved: return saved
    require_revision(row, payload)
    capabilities = flags(db, user, row, False)
    permitted = (capabilities["can_adjust"] or capabilities["can_append"]) if adjusting else capabilities["can_edit"]
    if not permitted:
        raise HTTPException(409, "已锁定订单请使用有原因的调整；未锁定订单请直接修改")
    if payload.kind == "SUPPLIER_GIFT": raise HTTPException(422, "内部不能创建赠送")
    was_sent = row.status != "SUBMITTED"
    if was_sent:
        shipped, _, consumed, totals, _ = state_counts(db, row)
        if any(paper.quantity > consumed.get(paper.id, Decimal(0)) for paper in shipped):
            raise HTTPException(409, "存在在途或冲销待更正送货，请先核实原送货单后修改需求")
        if (payload.kind, payload.customer_code.upper(), payload.workshop_id) != (row.kind, row.customer_code.upper(), row.workshop_id):
            raise HTTPException(422, "已发送需求不可改写客户、类型或车间归属，请另建需求")
        incoming = {item.id: item for item in payload.lines}
        for paper in shipped:
            if paper.request_line_id not in incoming:
                raise HTTPException(422, "已发货纸品须保留原明细身份，不可删除")
            if incoming[paper.request_line_id].unit != json.loads(paper.snapshot_json)["unit"]:
                raise HTTPException(422, "已发货纸品不可更改计数单位；其他单位须另增需求明细")
        for line_id, total in totals.items():
            if incoming[line_id].quantity < total:
                raise HTTPException(409, "需求数量不可低于有效验收数量")
        if row.status == "COMPLETED":
            original = {paper.id: paper for paper in lines(db, row)}
            identity = ("item_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "unit")
            if any(identifier not in incoming or any(getattr(incoming[identifier], key) != getattr(paper, key) for key in identity)
                   for identifier, paper in original.items()):
                raise HTTPException(409, "已完成订单加单须保留原纸品资料；其他纸品请另增明细")
            if any(incoming[identifier].quantity < paper.quantity for identifier, paper in original.items()):
                raise HTTPException(409, "已完成需求不能通过调整减量；退货须按实际库存另行登记")
            if not any(item.id not in original or item.quantity > original[item.id].quantity for item in payload.lines):
                raise HTTPException(409, "已完成订单加单须增加实际纸品需求")
    assign_input(db, user, row, payload)
    db.flush()
    if was_sent:
        row.status = "SENT"; row.quote_version_id = ""; row.pricing_kind = "PENDING_QUOTE"; row.promised_date = ""
        if any(totals.values()):
            row.status = "COMPLETED" if all(totals.get(paper.id, Decimal(0)) >= paper.quantity for paper in lines(db, row)) else "PARTIALLY_RECEIVED"
    version(db, user, row, "ADJUSTED" if adjusting else "UPDATED", execution=True,
        reason=payload.reason if adjusting else "")
    if adjusting:
        db.add(SpecialMessage(id=uid("CSM-"), factory_id=row.factory_id, request_id=row.id,
            body="订单调整：" + payload.reason, actor_id=user.id, actor_name=user.display_name,
            audience="INTERNAL", created_at=core.now_text()))
        db.flush()
    if was_sent: notify(db, row, "ADJUSTED" if adjusting else "SENT", audience="SUPPLIER")
    return finish(db, user, payload, row, action_name, digest, commit=commit)


def action(db, user, identifier, payload, name, *, external=False, commit=True):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier, external=external)
    flag = {"SEND": "can_send", "APPROVE": "can_approve", "CANCEL": "can_cancel", "QUOTE": "can_quote"}[name]
    # Authorization before replay, state/revision after replay.
    permitted = portal.supplier_permission(user, "carton_supplier:approve", row.factory_id) if external else allowed(user, row.factory_id, "order_write")
    if not permitted: raise HTTPException(403, "没有此需求操作权限")
    digest, saved = replay(db, user, payload, name, identifier)
    if saved: return saved
    require_revision(row, payload)
    if not flags(db, user, row, external)[flag]: raise HTTPException(409, "需求当前阶段不允许此操作")
    was_published = is_published(db, row)
    if name == "SEND": row.status = "SENT"
    elif name == "CANCEL":
        if state_counts(db, row)[0]: raise HTTPException(409, "已发货需求须先核实送货及冲销，不可直接取消")
        row.status = "CANCELLED"
    elif name == "APPROVE":
        if payload.quote_version_id != row.quote_version_id: raise HTTPException(409, "报价版本已变更")
        row.status = "READY"
    else:
        if payload.version_id != row.current_version_id: raise HTTPException(409, "需求或确认资料版本已变更，请重新确认")
        if row.kind == "SUPPLIER_GIFT" and payload.pricing_kind != "FREE":
            raise HTTPException(422, "供应商赠送必须免费，不能转为收费需求")
        from app.services.carton_special_stock import replacement
        stock_source = replacement(db, row)
        if stock_source and stock_source["responsibility"] == "SUPPLIER" and payload.pricing_kind != "FREE":
            raise HTTPException(422, "供应商责任补单须免费，不能改为收费采购")
        papers = lines(db, row)
        prices = {item.line_id: item.unit_price for item in payload.lines}
        if set(prices) != {paper.id for paper in papers}: raise HTTPException(422, "须对本次需求全部纸品逐行报价")
        row.pricing_kind = payload.pricing_kind; row.promised_date = payload.promised_date.isoformat()
        for paper in papers: paper.unit_price = prices[paper.id]
        row.status = "READY" if payload.pricing_kind == "FREE" else "QUOTED"
    event = version(db, user, row, name, execution=True)
    if name == "QUOTE": row.quote_version_id = event.id
    if name in {"SEND", "APPROVE"} or (name == "CANCEL" and was_published):
        notify(db, row, "SENT" if name == "SEND" else "APPROVED" if name == "APPROVE" else "CANCEL", audience="SUPPLIER")
    if name == "QUOTE": notify(db, row, "QUOTED", audience="INTERNAL")
    return finish(db, user, payload, row, name, digest, external=external, commit=commit)


def ship(db, user, identifier, payload: schema.Ship, *, commit=True, allow_shared_note=False):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier, external=True)
    supplier(db, user, row.factory_id, "carton_supplier:edit")
    digest, saved = replay(db, user, payload, "SHIP", identifier)
    if saved: return saved
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    ensure_evidence_open(db, row.factory_id, row.supplier_id, payload.delivery_date)
    require_revision(row, payload)
    if not flags(db, user, row, True)["can_ship"] or row.current_version_id != payload.version_id:
        raise HTTPException(409, "需求尚未发送、已结束或资料版本已变更，请刷新后核对当前需求")
    if len({item.line_id for item in payload.lines}) != len(payload.lines): raise HTTPException(422, "发货纸品不能重复")
    papers = {line.id: line for line in lines(db, row)}
    shipped, received, consumed, received_by_request, _ = state_counts(db, row)
    reserved = {}
    for paper in shipped:
        reserved[paper.request_line_id] = reserved.get(paper.request_line_id, Decimal(0)) + paper.quantity - consumed.get(paper.id, Decimal(0))
    # The original note number cannot be reused across formal and special paths.
    from app.models.carton_supplier_portal import SupplierShipment
    if not allow_shared_note and (db.scalar(select(SpecialShipment.id).where(SpecialShipment.factory_id == row.factory_id, SpecialShipment.supplier_id == row.supplier_id,
        SpecialShipment.delivery_note_no == payload.delivery_note_no)) or db.scalar(select(SupplierShipment.id).where(SupplierShipment.factory_id == row.factory_id,
        SupplierShipment.supplier_id == row.supplier_id, SupplierShipment.delivery_note_no == payload.delivery_note_no)) or db.scalar(select(CartonReceipt.id).where(
        CartonReceipt.factory_id == row.factory_id, CartonReceipt.supplier_id == row.supplier_id, CartonReceipt.delivery_note_no == payload.delivery_note_no))):
        raise HTTPException(409, "供应商送货单号已登记，请核对原单")
    shipment = SpecialShipment(id=uid("CSSP-"), factory_id=row.factory_id, supplier_id=row.supplier_id, request_id=row.id,
        version_id=row.current_version_id, delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(), created_by=user.id, created_at=core.now_text())
    db.add(shipment); db.flush()
    from app.services.carton_mark_associations import freeze_files
    file_manifest = freeze_files(db, user, row, order_kind='SAMPLE' if row.kind == 'SAMPLE' else 'MISC')
    for item in payload.lines:
        paper = papers.get(item.line_id)
        if paper is None: raise HTTPException(422, "发货纸品不属于此需求")
        if item.quantity > paper.quantity - received_by_request.get(paper.id, Decimal(0)) - reserved.get(paper.id, Decimal(0)):
            raise HTTPException(409, "发货数量超过需求剩余数量（含在途保留）")
        # Price belongs to this physical delivery, not a quotation/approval gate.
        # Older clients may omit it only for an already explicitly priced request.
        price = item.unit_price
        if price is None:
            if not row.quote_version_id or row.pricing_kind == "PENDING_QUOTE":
                raise HTTPException(422, "请填写本次送货单价；免费纸品明确填写零")
            price = paper.unit_price
        if row.kind == "SUPPLIER_GIFT" and price != 0:
            raise HTTPException(422, "供应商赠送必须免费")
        from app.services.carton_special_stock import replacement
        stock_source = replacement(db, row)
        if stock_source and stock_source["responsibility"] == "SUPPLIER" and price != 0:
            raise HTTPException(422, "供应商责任补单须免费，不能登记收费送货")
        legacy_free = item.unit_price is None and row.quote_version_id and row.pricing_kind == "FREE"
        if price == 0 and not item.free_confirmed and not legacy_free:
            raise HTTPException(422, "零单价必须明确确认本行免费")
        paper.unit_price = price
        db.add(SpecialShipmentLine(id=uid("CSSPL-"), factory_id=row.factory_id, shipment_id=shipment.id,
            request_line_id=paper.id, quantity=item.quantity, snapshot_json=pack(line_out(paper) | {
                "pricing_kind": "FREE" if price == 0 else "CHARGEABLE", "customer_code": row.customer_code, "customer_name": row.customer_name,
                "kind": row.kind, "request_no": row.request_no,
                "file_manifest": [file for file in file_manifest if not file['line_id'] or file['line_id'] == paper.id],
                "material_manifest": [file for file in snapshot(db, row)["material_manifest"] if file["line_id"] == paper.id]})))
    row.pricing_kind = "CHARGEABLE" if any(paper.unit_price > 0 for paper in papers.values()) else "FREE"
    if row.status in {"SENT", "QUOTED"}: row.status = "READY"
    version(db, user, row, "SHIPPED")
    notify(db, row, "SHIPPED", audience="INTERNAL")
    return finish(db, user, payload, row, "SHIP", digest, external=True, commit=commit)


def receive(db, user, identifier, shipment_id, payload: schema.Receive, *, commit=True):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier)
    if not can_receive(user, row.factory_id): raise HTTPException(403, "验收须同时具备本厂收料及库存权限")
    digest, saved = replay(db, user, payload, "RECEIVE", identifier, shipment_id)
    if saved: return saved
    require_revision(row, payload)
    if row.origin == "SUPPLIER_EXTRA" and any(item.received_quantity - item.damaged_quantity - item.rejected_quantity - item.unusable_quantity > 0 for item in payload.lines):
        if not payload.received_kind:
            raise HTTPException(422, "额外送货须选择样板或杂单入库类型")
        if any(receipt.status == "POSTED" for receipt in state_counts(db, row)[4].values()) and (
                payload.received_kind != row.kind or payload.workshop_id != row.workshop_id):
            raise HTTPException(409, "额外送货已按原用途入库，后续批次须保持相同类型及使用车间；更正请先冲销原收料")
        from app.services.carton_master import workshop_snapshot
        workshop_snapshot(db, row.factory_id, payload.workshop_id)
        row.kind = payload.received_kind; row.workshop_id = payload.workshop_id; row.requester_name = payload.requester_name
    if row.status not in {"SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(409, "当前需求不可验收，请核对需求及原送货单")
    shipment = db.get(SpecialShipment, shipment_id)
    if shipment is None or shipment.factory_id != row.factory_id or shipment.request_id != row.id:
        raise HTTPException(404, "未找到此需求送货单")
    if len({item.shipment_line_id for item in payload.lines}) != len(payload.lines): raise HTTPException(422, "验收纸品不能重复")
    shipped, _, consumed, _, _ = state_counts(db, row)
    sources = {paper.id: paper for paper in shipped if paper.shipment_id == shipment.id}
    if (payload.remaining_action == "CLOSE" or any(item.close_remaining for item in payload.lines)) and len(payload.close_reason.strip()) < 4:
        raise HTTPException(422, "短送结束须填写至少四字原因；采购欠数仍保留")
    from app.services.carton_supplier_settlement import date_check, ensure_open
    date_check(payload.acceptance_date.isoformat())
    ensure_open(db, row.factory_id, row.supplier_id, payload.acceptance_date.isoformat()[:7])
    receipt_inputs, accepted_items, closed = [], [], {}
    for item in payload.lines:
        source = sources.get(item.shipment_line_id)
        if source is None: raise HTTPException(422, "验收纸品不属于此送货单")
        if item.received_quantity > source.quantity - consumed.get(source.id, Decimal(0)):
            raise HTTPException(409, "验收数量超过此送货单剩余数量")
        if payload.remaining_action == "CLOSE" or item.close_remaining:
            remaining = source.quantity - consumed.get(source.id, Decimal(0)) - item.received_quantity
            if remaining > 0: closed[source.id] = str(remaining)
        if item.received_quantity == 0:
            continue
        accepted_items.append(item)
        saved_line = json.loads(source.snapshot_json)
        receipt_inputs.append(CartonReceiptLineCreate(source_type="AD_HOC", special_source_line_id=source.id,
            customer_code=saved_line["customer_code"], item_no=saved_line["item_no"], contract_no="",
            packaging_type=saved_line["packaging_type"], paper_quality=saved_line["paper_quality"],
            specification=saved_line["specification"], dimension_unit=saved_line["dimension_unit"], unit=saved_line["unit"], currency="CNY",
            unit_price=Decimal(saved_line["unit_price"]), zero_price_kind="FREE" if saved_line["pricing_kind"] == "FREE" else "PENDING" if saved_line.get("source_origin") == "WAREHOUSE_MANUAL" and Decimal(saved_line["unit_price"]) == 0 else None,
            delivered_quantity=item.received_quantity, received_quantity=item.received_quantity, damaged_quantity=item.damaged_quantity,
            rejected_quantity=item.rejected_quantity, unusable_quantity=item.unusable_quantity, location_allocations=item.location_allocations,
            feedback_note=f"纸品需求 {row.request_no}；原送货单 {shipment.delivery_note_no}；版本 {shipment.version_id}"))
    # Unique receipt number for each physical acceptance batch; original supplier
    # note identity lives on the structured shipment, not an inferred text match.
    # Core receipt locking expires ORM state. Persist the warehouse classification
    # inside this transaction before that refresh (Session autoflush is disabled).
    db.flush()
    receipt = core._create_receipt(db, CartonReceiptCreate(factory_id=row.factory_id, supplier_id=row.supplier_id,
        delivery_note_no=f"{shipment.delivery_note_no[:75]}#SP-{payload.request_id[:24]}", delivery_date=shipment.delivery_date,
        acceptance_date=payload.acceptance_date.isoformat(), lines=receipt_inputs), user, commit=False, special_request_id=row.id) if receipt_inputs else None
    if receipt:
        core.confirm_receipt(db, receipt.id, CartonReceiptConfirmRequest(factory_id=row.factory_id, expected_revision=receipt.revision), user, commit=False)
        db.flush()
    for paper, item in zip(core._receipt_lines(db, receipt.id) if receipt else [], accepted_items):
        db.add(SpecialReceiptLink(id=uid("CSRL-"), factory_id=row.factory_id, shipment_line_id=item.shipment_line_id, receipt_line_id=paper.id))
        from app.services.carton_special_stock import replacement
        stock_source = replacement(db, row)
        if not stock_source or stock_source["responsibility"] != "SUPPLIER":
            from app.services.carton_price_review import record_line
            record_line(db, user, paper, sources[item.shipment_line_id], shipment, item, source_kind="SPECIAL")
    if closed:
        from app.services.carton_special_receiving import EVENT
        core._audit(db, user, row.factory_id, EVENT, "carton_special_shipment", shipment.id,
            {"quantities": closed, "reason": payload.close_reason.strip(), "acceptance_date": payload.acceptance_date.isoformat(),
             "receipt_id": receipt.id if receipt else None})
    db.flush()
    _, _, _, totals, _ = state_counts(db, row)
    if any(totals.values()) and row.status in {"SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED", "COMPLETED"}:
        row.status = "COMPLETED" if all(totals.get(paper.id, Decimal(0)) >= paper.quantity for paper in lines(db, row)) else "PARTIALLY_RECEIVED"
    receive_action = "RECEIVED" if receipt else "DELIVERY_CLOSED" if closed else "DELIVERY_DEFERRED"
    version(db, user, row, receive_action)
    notify(db, row, receive_action, audience="SUPPLIER")
    return finish(db, user, payload, row, "RECEIVE", digest, commit=commit)


def attachment(db, user, identifier, payload, role, filename, content, *, external=False, line_id=""):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier, external=external)
    if not flags(db, user, row, external)["can_attach"]: raise HTTPException(403, "当前需求不可上传附件")
    if role not in {"REFERENCE", "DRAFT", "CONFIRMED"}: raise HTTPException(422, "附件类型无效")
    # The old parameter remains readable/replayable, but a new file is evidence,
    # never an implicit production approval or a replacement of historical art.
    requested_role = role
    if role == 'CONFIRMED': role = 'DRAFT'
    from pathlib import PurePosixPath
    from app.services.carton_mark_assets import IMAGE_CONTENT_TYPES, validate_asset_image
    suffix = PurePosixPath(filename).suffix.lower()
    if role != 'REFERENCE' and suffix not in {'.pdf', '.xls', '.xlsx', '.xlsm', '.jpg', '.jpeg', '.png', '.webp'}:
        raise HTTPException(422, '此文件仅作为参考附件；制作稿请上传 PDF、图片或 Excel')
    if suffix in IMAGE_CONTENT_TYPES:
        if not filename or len(filename) > 255 or any(char in filename for char in ('/', '\\', '\r', '\n', '\x00')):
            raise HTTPException(422, "附件文件名无效")
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(422, "附件不能为空且单文件最多 10 MiB")
        try: validate_asset_image(filename, content)
        except ValueError as error: raise HTTPException(422, str(error)) from error
        media = IMAGE_CONTENT_TYPES[suffix]
    else: media = portal.validate_file(filename, content)
    if not line_id and role == "CONFIRMED" and len(lines(db, row)) == 1:
        line_id = lines(db, row)[0].id
    paper = db.get(SpecialLine, line_id) if line_id else None
    if line_id and (paper is None or paper.request_id != row.id or paper.factory_id != row.factory_id):
        raise HTTPException(404, "纸品明细不存在")
    if role == "CONFIRMED" and paper is None:
        raise HTTPException(422, "确认制作稿须指定对应纸品明细")
    extra = {"filename": filename, "role": requested_role, "line_id": line_id, "sha256": hashlib.sha256(content).hexdigest()}
    digest, saved = replay(db, user, payload, "ATTACHMENT", identifier, extra)
    if saved: return saved
    require_revision(row, payload)
    attachment_id = uid("CSA-SP-")
    attachment_row = SpecialAttachment(id=attachment_id, factory_id=row.factory_id, request_id=row.id, role=role, line_id=line_id,
        filename=filename, media_type=media, sha256=extra["sha256"], size=len(content), content=content, created_by=user.id, created_at=core.now_text(), version=next_attachment_version(db, row))
    db.add(attachment_row)
    if role in {'DRAFT', 'CONFIRMED'}:
        from app.services.carton_special_marks import publish_attachment
        publish_attachment(db, user, row, paper, attachment_row, external=external)
    # No procurement revision is advanced by storing a file.
    # Include the new library association in both the response and its replay.
    db.flush()
    return finish(db, user, payload, row, "ATTACHMENT", digest, external=external)


def download(db, user, factory, identifier, attachment_id, *, external=False):
    row = access(db, user, factory, identifier, external=external)
    file = db.get(SpecialAttachment, attachment_id)
    if file is None or file.factory_id != factory or file.request_id != row.id: raise HTTPException(404, "附件不存在")
    return file


def message(db, user, identifier, payload: schema.Message, *, external=False):
    user = locked_actor(db, user, payload.factory_id)
    row = access(db, user, payload.factory_id, identifier, external=external)
    if not flags(db, user, row, external)["can_message"]: raise HTTPException(403, "没有留言权限")
    digest, saved = replay(db, user, payload, "MESSAGE", identifier)
    if saved: return saved
    require_revision(row, payload)
    db.add(SpecialMessage(id=uid("CSM-"), factory_id=row.factory_id, request_id=row.id, body=payload.body,
        actor_id=user.id, actor_name=user.display_name, audience="SUPPLIER" if external else "INTERNAL", created_at=core.now_text()))
    version(db, user, row, "MESSAGE")
    if row.status != "SUBMITTED": notify(db, row, "MESSAGE", audience="INTERNAL" if external else "SUPPLIER")
    return finish(db, user, payload, row, "MESSAGE", digest, external=external)


def validate_receipt_source(db, request_id, payload):
    """Trusted bridge only. Public receipt APIs cannot authorize this source."""
    row = db.get(SpecialRequest, request_id)
    if row is None or row.factory_id != payload.factory_id or row.supplier_id != payload.supplier_id:
        raise HTTPException(422, "纸品需求收料来源无效")
    shipped, _, consumed, totals, _ = state_counts(db, row)
    sources = {paper.id: paper for paper in shipped}
    result = {}
    current_lines = {paper.id: paper for paper in lines(db, row)}
    additions = {}
    for item in payload.lines:
        source = sources.get(item.special_source_line_id)
        if source is None or item.received_quantity > source.quantity - consumed.get(source.id, Decimal(0)):
            raise HTTPException(409, "纸品需求收料来源或剩余额度已变更")
        saved = json.loads(source.snapshot_json)
        effective = item.received_quantity - item.damaged_quantity - item.rejected_quantity - item.unusable_quantity
        additions[source.request_line_id] = additions.get(source.request_line_id, Decimal(0)) + effective
        if totals.get(source.request_line_id, Decimal(0)) + additions[source.request_line_id] > current_lines[source.request_line_id].quantity:
            raise HTTPException(409, "有效验收数量超过当前需求剩余额度，请先核实冲销及其他送货批次")
        price = Decimal(saved["unit_price"])
        if item.unit_price != price or (saved["pricing_kind"] == "FREE" and item.zero_price_kind != "FREE"):
            raise HTTPException(422, "验收价格必须使用原送货单记录的单价")
        accepted_kind = row.kind if row.origin == "SUPPLIER_EXTRA" else saved["kind"]
        marker = "__SUPPLIER_GIFT__" if accepted_kind == "SUPPLIER_GIFT" else "__WORKSHOP_MISC__" if accepted_kind == "WORKSHOP_MISC" else "__SAMPLE__"
        result[source.id] = {"customer_code": saved["customer_code"] or marker,
            "customer_name": saved["customer_name"] or {"SAMPLE": "样板需求", "WORKSHOP_MISC": "车间杂用", "SUPPLIER_GIFT": "供应商赠送"}[accepted_kind],
            "contract_no": "", "item_no": saved["item_no"], "packaging_type": saved["packaging_type"], "paper_quality": saved["paper_quality"],
            "specification": core._unordered_specification(saved["specification"], saved["dimension_unit"]), "unit": saved["unit"], "unit_price": price,
            "currency": "CNY", "order_line_id": None}
        from app.services.carton_special_stock import receipt_link
        link = receipt_link(db, row, source.request_line_id, effective)
        if link:
            if link["responsibility"] == "SUPPLIER" and price != 0:
                raise HTTPException(422, "供应商责任补单须以免费原送货证据入库")
            result[source.id]["special_replenishment_link"] = link
    return result


def receipt_reversed(db, receipt, user):
    request_ids = set(db.scalars(select(SpecialShipment.request_id).join(SpecialShipmentLine,
        SpecialShipmentLine.shipment_id == SpecialShipment.id).join(SpecialReceiptLink,
        SpecialReceiptLink.shipment_line_id == SpecialShipmentLine.id).join(CartonReceiptLine,
        CartonReceiptLine.id == SpecialReceiptLink.receipt_line_id).where(CartonReceiptLine.receipt_id == receipt.id)))
    for identifier in request_ids:
        row = db.get(SpecialRequest, identifier)
        if row.status == "COMPLETED": row.status = "PARTIALLY_RECEIVED"
        version(db, user, row, "RECEIPT_REVERSED")
        notify(db, row, "SHIPPED", audience="INTERNAL")


def validate_legacy_correction(db, user, payload):
    """Compatibility for a proven, reversed manual source, never a new ad hoc purchase."""
    receipt = db.get(CartonReceipt, payload.legacy_correction_receipt_id)
    if receipt is None or receipt.factory_id != payload.factory_id or receipt.status != "REVERSED":
        raise HTTPException(409, "历史更正必须关联本厂已冲销的原收料单")
    if payload.supplier_id != receipt.supplier_id:
        raise HTTPException(422, "历史更正供应商必须与原收料一致")
    original = core._receipt_lines(db, receipt.id)
    if not original or not any(paper.source_type == "AD_HOC" for paper in original) or any(paper.special_source_line_id for paper in payload.lines):
        raise HTTPException(422, "此兼容入口只用于含原手工非正式收料的冲销更正")
    from app.models.carton_supplier_portal import SupplierShipment
    from app.services.carton_shipment_receiving import owner
    if db.scalar(select(SpecialReceiptLink.id).where(SpecialReceiptLink.receipt_line_id.in_([paper.id for paper in original]))) or db.scalar(
        select(SupplierShipment.id).where(SupplierShipment.factory_id == receipt.factory_id,
            (SupplierShipment.receipt_id == receipt.id) | (SupplierShipment.delivery_note_no == receipt.delivery_note_no))) or owner(db, receipt.factory_id, receipt.id):
        raise HTTPException(409, "此收料有原需求或供应商送货来源，请沿原单更正验收")
    core.ensure_receipt_operation(db, user, receipt.factory_id, original)
    previous = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == receipt.factory_id,
        CartonAuditEvent.event_type == "LEGACY_RECEIPT_REENTERED", CartonAuditEvent.entity_id == receipt.id)))
    for event in previous:
        successor = db.get(CartonReceipt, json.loads(event.detail_json)["replacement_receipt_id"])
        if successor:
            raise HTTPException(409, "此历史收料已有后继更正，请沿最新一张已冲销更正继续，不可分叉重录")
    if len(original) != len(payload.lines): raise HTTPException(422, "历史更正须保留原纸品行数")
    for old, new in zip(original, payload.lines):
        if old.source_type != new.source_type or old.order_line_id != new.order_line_id:
            raise HTTPException(422, "历史更正须保留原纸品来源及订单关联")
        if new.delivered_quantity > old.delivered_quantity or new.received_quantity > old.delivered_quantity:
            raise HTTPException(422, "历史更正数量不得超出原送货数量；新增到货须关联有效需求")
        if old.source_type == "FORMAL_ORDER":
            continue  # Ordinary capacity, revision and order-state guards remain authoritative.
        expected_code = "__UNORDERED__" if new.unordered_receipt else new.customer_code
        if (old.customer_code, old.contract_no, old.item_no, old.unit) != (expected_code, new.contract_no, new.item_no, new.unit):
            raise HTTPException(422, "历史更正不可改写客户、合同、货号或计数单位")
    return receipt


def settlement_evidence(db, factory, supplier_id, period):
    """Allocate vendor evidence to exact existing receipt source keys, never money twice."""
    from app.services.carton_supplier_settlement import money
    from app.services.carton_replenishment_receipts import receipt_links
    receipt_price_links = receipt_links(db, factory)
    by_line, evidence = {}, []
    shipments = list(db.scalars(select(SpecialShipment).where(SpecialShipment.factory_id == factory,
        SpecialShipment.supplier_id == supplier_id).order_by(SpecialShipment.id)))
    for shipment in shipments:
        request = db.get(SpecialRequest, shipment.request_id)
        from app.services.carton_special_stock import replacement
        stock_source = replacement(db, request)
        papers = list(db.scalars(select(SpecialShipmentLine).where(SpecialShipmentLine.shipment_id == shipment.id).order_by(SpecialShipmentLine.id)))
        for source in papers:
            frozen = json.loads(source.snapshot_json)
            if stock_source:
                frozen = {**frozen, "special_replenishment_request_id": request.id,
                    "parent_request_id": stock_source["parent_request_id"], "parent_request_no": stock_source["parent_request_no"],
                    "responsibility": stock_source["responsibility"]}
            free_replacement = bool(stock_source and stock_source["responsibility"] == "SUPPLIER")
            original_price = None if frozen.get("source_origin") == "WAREHOUSE_MANUAL" else Decimal(frozen["unit_price"])
            original_price_text = str(original_price) if original_price is not None else None
            price = Decimal(0) if free_replacement else original_price
            price_text = str(price) if price is not None else None
            price_warning = "仓库代录，供应商原价待核实" if original_price is None else ""
            consumed_to_period = Decimal(0)
            for link, paper, receipt in db.execute(select(SpecialReceiptLink, CartonReceiptLine, CartonReceipt)
                .join(CartonReceiptLine, CartonReceiptLine.id == SpecialReceiptLink.receipt_line_id)
                .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
                .where(SpecialReceiptLink.shipment_line_id == source.id).order_by(CartonReceiptLine.id)):
                day = receipt.acceptance_date or receipt.confirmed_at[:10]
                if receipt.status == "POSTED" and day[:7] <= period:
                    consumed_to_period += paper.received_quantity
                if day[:7] != period: continue
                allocated = paper.received_quantity
                vendor = {"shipment_id": shipment.id, "line_id": source.id, "document_no": shipment.delivery_note_no,
                    "delivery_date": shipment.delivery_date, "quantity": str(allocated), "original_quantity": str(source.quantity),
                    "unit_price": price_text, "amount": str(money(allocated * price)) if price is not None else None, "original_unit_price": original_price_text,
                    "currency": "CNY", "price_warning": price_warning, "received_quantity": str(paper.received_quantity),
                    "damaged_quantity": str(paper.damaged_quantity), "rejected_quantity": str(paper.rejected_quantity),
                    "unusable_quantity": str(paper.unusable_quantity), "difference_reason": paper.feedback_note,
                    "quantity_difference": str(allocated - paper.effective_quantity), "price_difference": "0" if price is not None else None,
                    "request_id": request.id, "request_no": request.request_no, "request_kind": request.kind,
                    "version_id": shipment.version_id,
                    **({"special_replenishment_request_id": request.id, "responsibility": stock_source["responsibility"],
                        "parent_request_no": stock_source["parent_request_no"]} if stock_source else {})}
                by_line[paper.id] = vendor
                evidence.append({"shipment_id": shipment.id, "revision": receipt.id + ":" + source.id, "receipt_id": receipt.id,
                    "document_no": shipment.delivery_note_no, "delivery_date": shipment.delivery_date, "acceptance_date": day,
                    "status": "RECEIVED", "lines": [{"id": source.id, "order_line_id": None, "quantity": str(allocated),
                        "original_quantity": str(source.quantity), "unit_price": price_text, "amount": str(money(allocated*price)) if price is not None else None,
                        "original_unit_price": original_price_text, "price_warning": price_warning, "currency": "CNY", "snapshot": frozen}],
                    "acceptance": {"lines": [{"shipment_line_id": source.id, **receipt_line_out(paper, external=True, replacement_link=receipt_price_links.get(paper.id))}]}})
            from app.services.carton_special_receiving import closed_quantities, closures
            closed = closed_quantities(db, factory, [shipment.id], period=period).get(source.id, Decimal(0))
            for event, closure in closures(db, factory, [shipment.id], period=period):
                quantity = Decimal(closure["quantities"].get(source.id, "0"))
                if quantity <= 0 or closure["acceptance_date"][:7] != period: continue
                evidence.append({"shipment_id": shipment.id, "revision": event.id, "receipt_id": None,
                    "document_no": shipment.delivery_note_no, "delivery_date": shipment.delivery_date,
                    "acceptance_date": closure["acceptance_date"], "status": "NOT_RECEIVED",
                    "lines": [{"id": source.id, "order_line_id": None, "quantity": str(quantity),
                        "unit_price": price_text, "amount": str(money(quantity*price)) if price is not None else None,
                        "original_unit_price": original_price_text, "price_warning": price_warning, "currency": "CNY", "snapshot": frozen}],
                    "acceptance": {"lines": [{"shipment_line_id": source.id, "received_quantity": "0", "difference_reason": closure["reason"]}]}})
            pending = source.quantity - consumed_to_period - closed
            if pending > 0 and shipment.delivery_date[:7] == period:
                evidence.append({"shipment_id": shipment.id, "revision": "PENDING:" + source.id, "receipt_id": None,
                    "document_no": shipment.delivery_note_no, "delivery_date": shipment.delivery_date, "acceptance_date": None,
                    "status": "SENT", "as_of_period": True, "lines": [{"id": source.id, "order_line_id": None,
                        "quantity": str(pending), "unit_price": price_text, "amount": str(money(pending*price)) if price is not None else None,
                        "original_unit_price": original_price_text, "price_warning": price_warning, "currency": "CNY", "snapshot": frozen}], "acceptance": {}})
    return by_line, evidence
