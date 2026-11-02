"""Explicit, atomic handoff from a sales notification to one ordinary carton PO.

Preview executes the existing guarded operations in a rolled-back savepoint. The
confirmation repeats that preview under the same IAM/factory/ledger locks, checks
its fingerprint and commits procurement, supplier publication and receipt together.
"""
import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update

from app.models.carton_procurement import CartonAuditEvent, CartonCustomer, CartonOrder
from app.models.customer_order_ledger import OrderLedgerDispatch as Dispatch, OrderLedgerLine as Line, OrderLedgerVersion as Version
from app.schemas.carton_procurement import (CartonOrderAppendRequest, CartonOrderCancelRequest,
    CartonOrderDatesRequest, CartonOrderReduceRequest, CartonOrderUpdate)
from app.services import carton_business_customers as customers, carton_procurement as core
from app.services import customer_order_ledger as ledger
from app.services.business_authz import has_permission_for_departments
from app.services.carton_customer_assignment import ensure_customer_operation
from app.services.carton_quantity import rule
from app.services.carton_special_requests import allowed

EVENT = "BUSINESS_LEDGER_CARTON_APPLIED"


def capable(user, factory, recipient):
    return recipient in {"pmc", "warehouse"} and all(
        has_permission_for_departments(user, "customer_order:" + action, factory, ledger.RECIPIENTS[recipient])
        for action in ("inbox_read", "inbox_receive")) and all(
        allowed(user, factory, action) for action in ("read", "order_write"))


def context(db, user, factory, recipient, dispatch_id):
    if not capable(user, factory, recipient):
        raise HTTPException(403, "需要本厂收件箱签收及纸箱订单维护权限")
    item = db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id,
        Dispatch.factory_id == factory, Dispatch.recipient == recipient))
    if item is None:
        raise HTTPException(404, "当前收件箱中没有此订单")
    # Serialize against business amendments without changing their revision.
    db.execute(update(Line).where(Line.id == item.line_id, Line.factory_id == factory)
        .values(revision=Line.revision), execution_options={"synchronize_session": False})
    line = ledger.get_line(db, factory, item.line_id)
    db.refresh(line)
    if item.version != line.version:
        raise HTTPException(409, "业务已有更新版本，请处理最新通知")
    if item.version <= 1:
        raise HTTPException(409, "此入口只处理变更通知；新单请按下单流程处理")
    return item, line


def processing(db, factory, line_ids):
    result = {}
    if not line_ids:
        return result
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type == EVENT, CartonAuditEvent.entity_id.in_(line_ids))
        .order_by(CartonAuditEvent.sequence))
    for event in events:
        data = json.loads(event.detail_json)
        result[(event.entity_id, data["version"])] = data | {
            "processed_by": event.actor_name, "processed_at": event.created_at}
    return result


def matching_order(db, user, factory, source):
    binding = next((r for r in customers.records(db, factory)
        if r.status == "ACTIVE" and r.code == source["customer_code"]), None)
    customer = db.get(CartonCustomer, json.loads(binding.data_json)["customer_id"]) if binding else None
    if customer is None or customer.factory_id != factory:
        raise HTTPException(409, "业务客户尚未关联纸箱客户，请先在纸箱客户资料中同步并核对客户")
    ensure_customer_operation(db, user, factory, customer.customer_code)
    contract = str(source.get("contract_no") or source.get("reference_no") or "").strip()
    item_no = str(source.get("product_no") or "").strip()
    if not contract or not item_no:
        raise HTTPException(409, "业务通知缺少合同或货号，不能确定采购单")
    orders = list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
        CartonOrder.customer_code == customer.customer_code, CartonOrder.contract_no == contract,
        CartonOrder.item_no == item_no)))
    if not orders:
        raise HTTPException(409, "尚未找到对应纸箱采购单，请核对客户、合同、货号或先下单")
    if len(orders) != 1:
        raise HTTPException(409, "对应多张采购单，需逐单核对分配数量；不能把整张业务数量套到其中一张")
    order = orders[0]
    if order.customer_po and source.get("po_no") and order.customer_po != source["po_no"]:
        raise HTTPException(409, "业务 PO 与采购单的客户 PO 不一致，请先核对关联")
    return order


def state(db, order):
    return {"order_no": order.order_no, "revision": order.revision, "status": order.status,
        "product_order_quantity": str(order.product_order_quantity) if order.product_order_quantity is not None else None,
        "customer_due_date": order.customer_due_date, "due_date": order.due_date,
        "plan_date_manual": bool(order.plan_date_manual),
        "lines": [{"id": line.id, "packaging_type": line.packaging_type, "specification": line.specification,
            "required_quantity": str(line.required_quantity), "unit": line.unit} for line in core._order_lines(db, order.id)]}


def apply(db, user, order, source, previous):
    reason = ("业务通知改单：" + str(source.get("change_reason") or "业务数量或交期变更"))[:500]
    def args():
        return dict(factory_id=order.factory_id, expected_revision=order.revision, reason=reason)
    if order.status not in {"DRAFT", "CONFIRMED"} and not (
            allowed(user, order.factory_id, "order_adjust") or allowed(user, order.factory_id, "inventory_write")):
        raise HTTPException(403, "已下单的采购单还需要订单调整权限或库存操作权限")
    if source.get("status") == "cancelled":
        if order.status == "CANCELLED":
            return order
        return core.cancel_order(db, order.order_no, CartonOrderCancelRequest(**args()), user, commit=False)
    if order.status == "CANCELLED":
        raise HTTPException(409, "采购单已取消，不能用业务变更重新启用，请人工核对")
    target = Decimal(str(source["quantity"])) if source.get("quantity") not in (None, "") else None
    old = Decimal(str(previous["quantity"])) if previous.get("quantity") not in (None, "") else None
    quantity_changed = target != old
    date_changed = source.get("requested_ship_date") != previous.get("requested_ship_date")
    if not quantity_changed and not date_changed:
        raise HTTPException(409, "本通知没有数量或交期变更，请人工核对其他要求后签收")
    if quantity_changed:
        if target is None or target <= 0:
            raise HTTPException(409, "业务数量为空或为零，请先核对；不能把零数量当作整单退货")
        if order.quantity_basis != "CALCULATED" or order.product_order_quantity is None or any(
                rule(line) and rule(line).manual_quantity is not None for line in core._order_lines(db, order.id)):
            raise HTTPException(409, "采购单有手工纸品需求，需逐纸品核对数量，不能直接按业务数量换算")
        if order.product_order_quantity not in {old, target}:
            raise HTTPException(409, "采购数量与业务变更前数量不一致，可能已分批或另行调整，请人工核对")
    if date_changed and not source.get("requested_ship_date"):
        raise HTTPException(409, "业务交期被清空，请先补齐交期再改单")
    needs_quantity = quantity_changed and order.product_order_quantity != target
    needs_date = date_changed and order.customer_due_date != source.get("requested_ship_date")
    if order.status in {"DRAFT", "CONFIRMED"}:
        if needs_quantity or needs_date:
            values = core.order_out(db, order).model_dump()
            # Keep the exact stored units and approved configuration; no unrelated remapping.
            values.update(master_config_id=order.master_config_id, master_config_revision=order.master_config_revision)
            for value, stored in zip(values["lines"], core._order_lines(db, order.id)):
                value["dimension_unit"] = stored.dimension_unit
            if needs_quantity:
                values["product_order_quantity"] = target
            if needs_date:
                values["customer_due_date"] = source["requested_ship_date"]
            values.update(args())
            order = core.update_order(db, order.order_no, CartonOrderUpdate.model_validate(values), user, commit=False)
        return order
    # Completed orders can reopen through an increase; dates on other open orders
    # are changed before a reduction can complete them.
    def change_quantity():
        if not needs_quantity:
            return order
        difference = target - order.product_order_quantity
        if difference > 0:
            return core.append_order(db, order.order_no, CartonOrderAppendRequest(**args(), additional_quantity=difference), user, commit=False)
        return core.reduce_order(db, order.order_no, CartonOrderReduceRequest(**args(), reduction_quantity=-difference), user, commit=False)
    if order.status == "COMPLETED":
        order = change_quantity()
    if needs_date:
        order = core.update_order_dates(db, order.order_no, CartonOrderDatesRequest(**args(),
            customer_due_date=source["requested_ship_date"]), user, commit=False)
    if needs_quantity and order.product_order_quantity != target:
        order = change_quantity()
    return order


def preview(db, user, item, line):
    source = item.snapshot
    previous = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == item.version - 1))
    result = {"dispatch_id": item.id, "version": item.version, "customer_name": source.get("customer_name", ""),
        "contract_no": source.get("contract_no") or source.get("reference_no", ""), "item_no": source.get("product_no", ""),
        "source_before": {k: (previous.data.get(k) if previous else None) for k in ("quantity", "requested_ship_date", "status")},
        "source_after": {k: source.get(k) for k in ("quantity", "requested_ship_date", "status")},
        "reason": source.get("change_reason", ""), "before": None, "after": None,
        "can_confirm": False, "blocked_reason": "", "fingerprint": "", "processed": None}
    try:
        order = matching_order(db, user, line.factory_id, source)
        saved = processing(db, line.factory_id, [line.id]).get((line.id, item.version))
        if saved:
            result.update(processed=saved, before=saved["before"], after=saved["after"], fingerprint=saved["fingerprint"])
            return result
        result["before"] = state(db, order)
        if previous is None:
            raise HTTPException(409, "缺少业务上一版本，无法核对变更")
        details = core.order_out(db, order)
        if details.order_split or details.print_split or details.split_records or details.schedule_split_source:
            raise HTTPException(409, "采购单涉及拆单，需逐单核对分配，不能自动套用业务总数量")
        # A savepoint gives the preview precisely the existing demand, transit and
        # received-quantity guards, with no durable revision/audit/stock changes.
        savepoint = db.begin_nested()
        try:
            changed = apply(db, user, order, source, previous.data)
            result["after"] = state(db, changed)
        finally:
            savepoint.rollback()
        result["can_confirm"] = True
        evidence = result | {"ledger_revision": line.revision}
        result["fingerprint"] = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    except HTTPException as exc:
        if exc.status_code in {401, 403}:
            raise
        result["blocked_reason"] = str(exc.detail)
    except ValidationError:
        result["blocked_reason"] = "当前采购资料不满足改单要求，请到纸箱采购单补齐后重试"
    return result


def confirm(db, user, item, line, body):
    if not body.confirmed:
        raise HTTPException(422, "请核对变更内容后再次确认")
    shown = preview(db, user, item, line)
    if shown["fingerprint"] != body.fingerprint:
        raise HTTPException(409, "业务或采购单已变化，请重新打开核对后确认")
    if shown["processed"]:
        return shown
    if not shown["can_confirm"]:
        raise HTTPException(409, shown["blocked_reason"])
    order = matching_order(db, user, line.factory_id, item.snapshot)
    previous = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == item.version - 1))
    order = apply(db, user, order, item.snapshot, previous.data)
    ordinary = [issue for issue in core._purchase_order_issues(db, order.id)
        if not core._purchase_order_snapshot(issue).get("replenishment")]
    if order.status != "CANCELLED" and ordinary and core._purchase_order_pending_change(
            order, core._order_lines(db, order.id), ordinary[0])[0] != "NONE":
        core.create_purchase_order_issue(db, order, order.revision, user, commit=False, already_locked=True)
    after = state(db, order)
    detail = {"version": item.version, "dispatch_id": item.id, "fingerprint": body.fingerprint,
        "order_id": order.id, "order_no": order.order_no, "before": shown["before"], "after": after}
    event = core._audit(db, user, line.factory_id, EVENT, "business_order_line", line.id, detail)
    if not item.received_at:
        item.received_at, item.received_by = ledger.now_text(), ledger.actor_name(user)
    db.flush()
    return shown | {"can_confirm": False, "after": after, "processed": detail | {
        "processed_by": event.actor_name, "processed_at": event.created_at}}
