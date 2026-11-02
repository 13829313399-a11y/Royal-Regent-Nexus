"""Atomic, content-bound append commands over the existing order sources."""
import hashlib
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from app.models.carton_procurement import CartonOrderLine
from app.schemas import carton_procurement as regular_schema, carton_special_requests as special_schema
from app.services import carton_procurement as core, carton_special_requests as special


def append(db, user, payload, *, refresh_actor=None):
    user = special.locked_actor(db, user, payload.factory_id)
    if refresh_actor is not None:
        user = refresh_actor()
    if not special.allowed(user, payload.factory_id, "order_write"):
        raise HTTPException(403, "没有本厂订单操作权限")
    digest, saved = special.replay(db, user, payload, "UNIFIED_APPEND")
    if saved:
        for item in saved["processed"]:
            if item["kind"] == "PURCHASE":
                row = core.get_order_by_no(db, payload.factory_id, item["id"])
                core.ensure_customer_operation(db, user, payload.factory_id, row.customer_code)
            else:
                special.access(db, user, payload.factory_id, item["id"])
        return saved
    processed = []
    try:
        for item in payload.items:
            try:
                if item.kind == "PURCHASE":
                    row = core.get_order_by_no(db, payload.factory_id, item.id)
                    core.ensure_customer_operation(db, user, payload.factory_id, row.customer_code)
                    if row.deleted_at:
                        raise HTTPException(409, "订单已删除")
                    if row.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"} and not (
                        special.allowed(user, payload.factory_id, "order_adjust") or special.allowed(user, payload.factory_id, "inventory_write")
                    ):
                        raise HTTPException(403, "没有已锁定订单调整权限")
                    if row.revision != item.expected_revision:
                        raise HTTPException(409, "订单已更新，请刷新")
                    core._guard_no_supplier_transit(db, row)
                    papers = core._order_lines(db, row.id)
                    amounts = {line.id: line.additional_quantity for line in item.lines}
                    if set(amounts) - {line.id for line in papers}:
                        raise HTTPException(422, "纸品身份不存在")
                    if len(papers) + len(item.new_lines) > 50:
                        raise HTTPException(422, "订单最多包含 50 项纸品")
                    for new in item.new_lines:
                        if new.item_no and new.item_no != row.item_no:
                            raise HTTPException(422, "新增纸品货号须与原正单一致")
                        core._unordered_specification(new.specification, new.dimension_unit)
                        line = CartonOrderLine(id="CTL-" + uuid4().hex, factory_id=row.factory_id,
                            order_id=row.id, line_no=len(papers) + 1, customer_code=row.customer_code,
                            contract_no=row.contract_no, item_no=row.item_no, packaging_type=new.packaging_type,
                            paper_quality=new.paper_quality, specification=new.specification, dimension_unit=new.dimension_unit,
                            usage_quantity=Decimal(1), required_quantity=Decimal(0), unit=new.unit,
                            unit_price=Decimal(0), currency="CNY", price_source="manual", note="")
                        core._set_manual_quantity(line, Decimal(0))
                        db.add(line)
                        papers.append(line)
                        amounts[line.id] = new.quantity
                    db.flush()
                    targets = [{"order_line_id": line.id, "required_quantity": line.required_quantity + amounts.get(line.id, Decimal(0))} for line in papers]
                    dates = {}
                    if item.due_date:
                        dates["customer_due_date" if row.quantity_basis == "CALCULATED" and row.customer_due_date else "due_date"] = item.due_date.isoformat()
                    core.append_order(db, row.order_no, regular_schema.CartonOrderAppendRequest(factory_id=payload.factory_id,
                        expected_revision=item.expected_revision, line_quantities=targets, reason=item.reason,
                        issue_to_supplier=True, **dates), user, commit=False)
                    number = row.order_no
                else:
                    row = special.access(db, user, payload.factory_id, item.id)
                    if row.kind != item.kind or not special.flags(db, user, row, False)["can_append"]:
                        raise HTTPException(409, "订单当前不可追加")
                    papers = special.lines(db, row)
                    amounts = {line.id: line.additional_quantity for line in item.lines}
                    if set(amounts) - {line.id for line in papers}:
                        raise HTTPException(422, "纸品身份不存在")
                    inputs = [dict(id=line.id, item_no=line.item_no, packaging_type=line.packaging_type,
                        paper_quality=line.paper_quality, specification=line.specification, dimension_unit=line.dimension_unit,
                        quantity=line.quantity + amounts.get(line.id, Decimal(0)), unit=line.unit, mark_mode=line.mark_mode) for line in papers]
                    inputs.extend(line.model_dump() for line in item.new_lines)
                    key = "UA-" + hashlib.sha256(f"{payload.request_id}:{item.kind}:{item.id}".encode()).hexdigest()
                    body = special_schema.Adjust(factory_id=payload.factory_id, request_id=key, expected_revision=item.expected_revision,
                        kind=row.kind, title=row.title, requester_name=row.requester_name, customer_code=row.customer_code,
                        workshop_id=row.workshop_id, purpose=row.purpose, required_date=item.due_date or row.required_date,
                        reason=item.reason, lines=inputs)
                    special.update(db, user, row.id, body, adjusting=True, commit=False)
                    number = row.request_no
                # Link the original order timeline back to this batch without altering its source identity.
                core._audit(db, user, payload.factory_id, "ORDER_BATCH_APPEND_LINK",
                    "carton_order" if item.kind == "PURCHASE" else "carton_special_request", row.id,
                    {"batch_id": payload.request_id, "reason": item.reason, "number": number})
                processed.append({"kind": item.kind, "id": item.id, "number": number, "customer_code": row.customer_code,
                    "reason": item.reason, "lines": [line.model_dump(mode="json") for line in item.lines],
                    "new_lines": [line.model_dump(mode="json") for line in item.new_lines], "due_date": item.due_date.isoformat() if item.due_date else None})
                db.flush()
            except HTTPException as error:
                raise HTTPException(error.status_code, f"订单 {item.id}：{error.detail}") from error
        response = {"batch_id": payload.request_id, "processed": processed, "count": len(processed)}
        event = core._audit(db, user, payload.factory_id, "UNIFIED_ORDER_APPEND", "carton_unified_order_batch", payload.request_id,
            {"fingerprint": digest, "request_id": payload.request_id, "response": response})
        event.id = special.replay_id(user, payload)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise
