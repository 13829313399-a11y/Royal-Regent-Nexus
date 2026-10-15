"""Atomic normal-order creation with durable, actor-scoped replay evidence."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrder
from app.services import carton_procurement as core
from app.services.identity_policy import lock_mutation
from app.services.carton_customer_assignment import ensure_customer_operation


def create(db, payload, user, *, refresh_user, authorize):
    try:
        # Same lock order as IAM/customer responsibility writes, then factory stock.
        lock_mutation(db)
        core._lock_receipt_factory(db, payload.factory_id)
        current = refresh_user()
        if current.id != user.id:
            raise HTTPException(401, "账号身份已变化，请重新核对")
        user = current
        authorize(user)
        for row in payload.rows:
            ensure_customer_operation(db, user, payload.factory_id, row.order.customer_code)
        fingerprint = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True,
            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        scope = json.dumps([payload.factory_id, user.id, payload.request_id], separators=(",", ":"))
        event_id = "CAE-OCG-" + hashlib.sha256(scope.encode()).hexdigest()
        previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
        if previous:
            detail = json.loads(previous.detail_json)
            if detail["fingerprint"] != fingerprint:
                raise HTTPException(409, "该合单草稿已转为订单，内容不能修改后重复提交；请核对原订单")
            for result in detail["orders"]:
                order = db.get(CartonOrder, result["id"])
                if order is None or order.deleted_at is not None:
                    raise HTTPException(409, "合单组原订单已删除，请核对历史记录，勿重复转单")
                ensure_customer_operation(db, user, payload.factory_id, order.customer_code)
            db.commit()
            return detail["orders"]
        results = []
        for index, row in enumerate(payload.rows, 1):
            if not row.order.customer_due_date:
                raise HTTPException(422, f"第 {index} 款缺少客户交期，请补齐草稿")
            if any(not line.paper_quality or not line.specification or not line.dimension_unit for line in row.order.lines):
                raise HTTPException(422, f"第 {index} 款纸品资料不齐：请填写纸质、规格及尺寸单位")
            row.order.customer_code = row.order.customer_code.strip().upper()
            rules = core.master_data.due_rules(db, payload.factory_id, row.order.customer_code)
            row.order.due_date = core.derive_carton_plan_due_date(row.order.order_date, row.order.customer_due_date, rules["lead_days"])
            order = core.create_order(db, row.order, user, commit=False)
            core._require_order_complete(db, order)
            results.append(core.order_out(db, order).model_dump(mode="json"))
            # Written within the same transaction, retaining each PO/style/source.
            core._audit(db, user, payload.factory_id, "ORDER_GROUP_SOURCE_LINKED", "carton_order", order.id,
                {"group_request_id": payload.request_id, "group_name": payload.name,
                 "row_id": row.row_id, "source": row.source, "customer_po": order.customer_po})
            db.flush()
        event = core._audit(db, user, payload.factory_id, "ORDER_GROUP_CREATED", "carton_order_group",
            payload.request_id, {"fingerprint": fingerprint, "name": payload.name, "orders": results,
                "sources": [{"row_id": row.row_id, "source": row.source} for row in payload.rows]})
        event.id = event_id
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise
