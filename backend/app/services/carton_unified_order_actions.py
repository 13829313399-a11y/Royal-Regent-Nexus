"""One typed selection and atomic command boundary for all carton order kinds."""
import hashlib
from fastapi import HTTPException
from app.schemas import carton_procurement as regular_schema, carton_special_requests as special_schema
from app.services import carton_procurement as core, carton_special_requests as special


def selected(db, user, payload):
    special.access(db, user, payload.factory_id)
    result = []
    for item in payload.items:
        if item.kind == "PURCHASE":
            if not special.allowed(user, payload.factory_id, "read"): raise HTTPException(403, "没有本厂订单读取权限")
            try:
                row = core.get_order_by_no(db, payload.factory_id, item.id)
            except HTTPException as error:
                if error.status_code == 404: continue
                raise
            core.ensure_customer_operation(db, user, payload.factory_id, row.customer_code)
            result.append({"kind": "PURCHASE", "order": core.order_out(db, row)})
        else:
            try:
                row = special.detail(db, user, payload.factory_id, item.id)
            except HTTPException as error:
                if error.status_code == 404: continue
                raise
            if row["kind"] != item.kind or row["deleted"]: continue
            result.append({"kind": item.kind, "special": row})
    return result


def perform(db, user, payload, *, refresh_actor=None):
    user = special.locked_actor(db, user, payload.factory_id)
    if refresh_actor is not None:
        user = refresh_actor()
    if not special.allowed(user, payload.factory_id, "order_write"): raise HTTPException(403, "没有本厂订单操作权限")
    if payload.action == "DELETE" and not (special.allowed(user, payload.factory_id, "inventory_write") or special.allowed(user, payload.factory_id, "order_adjust")):
        raise HTTPException(403, "只有本厂主管或仓管可删除订单")
    digest, saved = special.replay(db, user, payload, "UNIFIED_" + payload.action)
    if saved:
        for item in saved["processed"]:
            special.ensure_customer_operation(db, user, payload.factory_id, item["customer_code"])
        return saved
    regular, requests, processed = [], [], []
    # Authorize and validate every source before issuing any state transition.
    for item in payload.items:
        if item.kind == "PURCHASE":
            row = core.get_order_by_no(db, payload.factory_id, item.id)
            core.ensure_customer_operation(db, user, payload.factory_id, row.customer_code)
            if row.revision != item.expected_revision: raise HTTPException(409, f"订单 {item.id} 已更新，请刷新")
            if payload.action == "CONFIRM":
                if row.status not in {"DRAFT", "CONFIRMED"}: raise HTTPException(409, "所选正单已锁定或结束")
                core._require_order_complete(db, row)
            elif payload.action == "CANCEL":
                if row.status not in {"DRAFT", "CONFIRMED", "PENDING_SUPPLIER"}: raise HTTPException(409, "所选正单已有收料或已结束，请按退单流程处理")
                core._guard_no_supplier_transit(db, row)
                if core._order_has_business_activity(db, row): raise HTTPException(409, "所选订单已有收发记录")
            elif core.order_deletion_block_reason(db, row): raise HTTPException(409, core.order_deletion_block_reason(db, row))
            regular.append({"order_no": row.order_no, "expected_revision": row.revision})
        else:
            row = special.access(db, user, payload.factory_id, item.id)
            if row.kind != item.kind: raise HTTPException(404, "所选订单类型不符")
            special.require_revision(row, item)
            flag = {"CONFIRM": "can_confirm", "CANCEL": "can_cancel", "DELETE": "can_delete"}[payload.action]
            if not special.flags(db, user, row, False)[flag]: raise HTTPException(409, f"订单 {row.request_no} 当前不可执行此操作")
            if payload.action == "CANCEL" and special.state_counts(db, row)[0]: raise HTTPException(409, "已有送货记录，请先核实原单")
            requests.append(item)
        processed.append({"kind": item.kind, "id": item.id, "customer_code": row.customer_code})
    try:
        if regular:
            args = dict(factory_id=payload.factory_id, items=regular)
            if payload.action == "CONFIRM": core.bulk_submit_orders_to_supplier(db, regular_schema.CartonOrderBulkSubmitRequest(**args), user, commit=False)
            elif payload.action == "CANCEL": core.bulk_cancel_orders(db, regular_schema.CartonOrderBulkCancelRequest(**args, reason=payload.reason), user, commit=False)
            else: core.bulk_delete_orders(db, regular_schema.CartonOrderBulkDeleteRequest(**args, reason=payload.reason), user, commit=False)
        for item in requests:
            key = "UO-" + hashlib.sha256(f"{payload.request_id}:{item.kind}:{item.id}".encode()).hexdigest()
            args = dict(factory_id=payload.factory_id, request_id=key, expected_revision=item.expected_revision)
            if payload.action == "DELETE": special.delete_request(db, user, item.id, special_schema.Delete(**args, reason=payload.reason), commit=False)
            else: special.action(db, user, item.id, special_schema.Command(**args), "SEND" if payload.action == "CONFIRM" else "CANCEL", commit=False)
        response = {"processed": processed, "count": len(processed)}
        audit = core._audit(db, user, payload.factory_id, "UNIFIED_ORDER_" + payload.action, "carton_unified_order_batch", payload.request_id,
            {"fingerprint": digest, "request_id": payload.request_id, "reason": payload.reason, "response": response})
        audit.id = special.replay_id(user, payload)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise
