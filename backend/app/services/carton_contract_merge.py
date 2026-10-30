"""Move unissued orders into one new contract without copying procurement demand."""
import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrder
from app.models.carton_master import CartonMasterRecord, CartonMasterSource
from app.services import carton_procurement as core, carton_master as master
from app.services.carton_customer_assignment import ensure_customer_operation
from app.services.identity_policy import lock_mutation
from app.services.carton_order_split import plans
from app.services.carton_order_projection import order_page_out


def merge(db, payload, user, *, refresh_user, authorize):
    try:
        factory = core.require_carton_factory(payload.factory_id)
        lock_mutation(db)
        core._lock_receipt_factory(db, factory)
        current = refresh_user()
        if current.id != user.id:
            raise HTTPException(401, "账号身份已变化，请重新核对")
        user = current
        authorize(user)
        fingerprint = master.digest(payload.model_dump(mode="json"))
        event_id = "CAE-MERGE-" + hashlib.sha256(master.encoded([factory, user.id, payload.request_id]).encode()).hexdigest()
        previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
        if previous:
            detail = json.loads(previous.detail_json)
            if detail["fingerprint"] != fingerprint:
                raise HTTPException(409, "原合单请求已完成，不能修改后重复提交，请核对原结果")
            for result in detail["orders"]:
                order = db.get(CartonOrder, result["id"])
                if order is None or order.deleted_at is not None:
                    raise HTTPException(409, "原合单请求已完成，其中的订单已删除，请核对历史记录，勿重复合单")
                ensure_customer_operation(db, user, factory, order.customer_code)
            db.commit()
            return detail["orders"]
        orders = [core.get_order_by_no(db, factory, number) for number in sorted(payload.expected_revisions)]
        for order in orders:
            ensure_customer_operation(db, user, factory, order.customer_code)
        if len({(order.customer_code, order.supplier_id) for order in orders}) != 1:
            raise HTTPException(422, "只能合并同厂区、同客户、同供应商的订单")
        customer = orders[0].customer_code
        core.get_active_customer(db, factory, customer)
        seen = set()
        for order in orders:
            if order.revision != payload.expected_revisions[order.order_no]:
                raise HTTPException(409, f"订单 {order.order_no} 已变化，请刷新后重新选择")
            if (order.status != "CONFIRMED" or core._purchase_order_issues(db, order.id)
                    or core._order_has_business_activity(db, order) or core._order_has_supplier_evidence(db, order)
                    or plans(db, factory, order.id)):
                raise HTTPException(409, f"订单 {order.order_no} 已下单或已有执行记录，不能合单")
            master.validate_order(db, factory, customer, payload.contract_no, order.item_no, customer_po=order.customer_po)
            identity = (order.customer_po.strip().casefold(), order.item_no.strip().casefold())
            if identity[0] and identity in seen:
                raise HTTPException(422, "所选订单有重复的客户 PO 与货号，请先核对重复需求")
            seen.add(identity)
        contract_key = payload.contract_no.casefold()
        old_codes = db.scalars(select(CartonOrder.contract_no).where(CartonOrder.factory_id == factory, CartonOrder.customer_code == customer))
        master_codes = db.scalars(select(CartonMasterRecord.code).where(CartonMasterRecord.factory_id == factory,
            CartonMasterRecord.customer_code == customer, CartonMasterRecord.kind == "CONTRACT"))
        if any(code.strip().casefold() == contract_key for code in [*old_codes, *master_codes]):
            raise HTTPException(409, "该客户已有此合同号，请填写新的合同号")
        timestamp = core.now_text()
        contract_data = {"item_nos": sorted({order.item_no for order in orders})}
        contract = CartonMasterRecord(id="CMD-" + uuid4().hex, factory_id=factory, kind="CONTRACT",
            identity=master.digest([customer, payload.contract_no]), customer_code=customer, code=payload.contract_no,
            data_json=master.encoded(contract_data), status="ACTIVE", revision=1, maintained=0, updated_at=timestamp)
        db.add(contract)
        db.flush()
        originals = [result.model_dump(mode="json") for result in order_page_out(db, orders)]
        for order, before in zip(orders, originals):
            order.contract_no = payload.contract_no
            order.revision += 1
            order.updated_at = timestamp
            order.updated_by = user.id
            order.updated_by_name = user.display_name
            for line in core._order_lines(db, order.id):
                line.contract_no = payload.contract_no
            evidence = {"order_no": order.order_no, "order_date": order.order_date, "customer_code": customer,
                "customer_po": order.customer_po, "contract_no": payload.contract_no, "item_no": order.item_no,
                "original_contract_no": before["contract_no"], "configuration": contract_data}
            db.add(CartonMasterSource(id="CMS-" + uuid4().hex, factory_id=factory, record_id=contract.id,
                order_id=order.id, signature=master.digest([contract_data, order.customer_po]) if order.customer_po else master.digest(contract_data),
                snapshot_json=master.encoded(evidence), occurred_at=timestamp))
            core._audit(db, user, factory, "ORDER_CONTRACT_MERGED", "carton_order", order.id,
                {"reason": payload.reason, "request_id": payload.request_id, "contract_id": contract.id,
                 "before": before, "new_contract_no": payload.contract_no})
        db.flush()
        results = [result.model_dump(mode="json") for result in order_page_out(db, orders)]
        event = core._audit(db, user, factory, "CONTRACT_MERGE_CREATED", "carton_master", contract.id,
            {"fingerprint": fingerprint, "contract_no": payload.contract_no, "reason": payload.reason,
             "originals": originals, "orders": results})
        event.id = event_id
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise
