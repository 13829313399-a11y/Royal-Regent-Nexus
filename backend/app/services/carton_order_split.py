"""Audited allocations, not duplicate supplier demand or supplier payable.

The immutable audit stream is the aggregate store, as for schedule order links.
Only balanced inventory adjustments change ownership; receipts remain original.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonOrder, CartonOrderLine
from app.schemas.carton_order_split import SplitCreate, SplitAction
from app.services import carton_positions as positions
from app.services.carton_inventory_valuation import cost_key, load_valuation

PREFIX = "CSL-"


def norm(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def plans(db, factory, order_id=None):
    events = db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == "carton_order_split",
    ).order_by(CartonAuditEvent.sequence)).all()
    result = {}
    for event in events:
        detail = json.loads(event.detail_json)
        if event.event_type == "ORDER_SPLIT_CREATED":
            result[event.entity_id] = {**detail["plan"], "revision": 1, "created_at": event.created_at,
                "created_by_name": event.actor_name, "pairs": []}
        elif event.entity_id in result:
            plan = result[event.entity_id]
            if event.event_type == "ORDER_SPLIT_STOCK_MOVED":
                plan["pairs"].extend(detail["pairs"])
            elif event.event_type in {"ORDER_SPLIT_CONFIRMED", "ORDER_SPLIT_CANCELLED"}:
                plan.update(status="ACTIVE" if event.event_type == "ORDER_SPLIT_CONFIRMED" else "CANCELLED",
                            revision=plan["revision"] + 1)
    for plan in result.values():
        received = defaultdict(Decimal)
        for pair in plan["pairs"]:
            if pair.get("receipt_id"):
                received[pair["target_line_id"]] += Decimal(pair["quantity"])
        for target in plan["targets"]:
            for line in target["lines"]:
                line["received_quantity"] = str(received[line["target_line_id"]])
                line["pending_remaining"] = str(max(Decimal(0), Decimal(line["pending_quantity"]) - received[line["target_line_id"]]))
    return [plan for plan in result.values() if not order_id or plan["order_id"] == order_id]


def live_plans(db, factory, order_id=None):
    return [plan for plan in plans(db, factory, order_id) if plan["status"] != "CANCELLED"]


def guard_order_change(db, order):
    if live_plans(db, order.factory_id, order.id):
        raise HTTPException(409, "订单已有拆分归属，请先撤销可撤销的拆单并核对已领用记录，再减单、取消或修改订单信息")


def _get_order(db, factory, number):
    order = db.scalar(select(CartonOrder).where(CartonOrder.factory_id == factory, CartonOrder.order_no == number,
        CartonOrder.deleted_at.is_(None)))
    if not order:
        raise HTTPException(404, "原纸箱订单不存在")
    return order


def context(db, factory, number):
    from app.services import carton_procurement as core
    core._lock_receipt_factory(db, factory)
    order = _get_order(db, factory, number)
    lines = core._order_lines(db, order.id)
    records = plans(db, factory, order.id)
    reserved = defaultdict(Decimal)
    for plan in records:
        if plan["status"] == "CANCELLED":
            continue
        for target in plan["targets"]:
            for line in target["lines"]:
                reserved[line["order_line_id"]] += Decimal(line["pending_remaining"])
    received = core.protected_by_line(db, [line.id for line in lines])
    pending = core._pending_received_by_line(db, [line.id for line in lines])
    positions.seed_unallocated(db, factory)
    stock = positions.position_balances(db, factory)
    return {"factory_id": factory, "order_no": number, "revision": order.revision, "plans": records,
            "lines": [{"order_line_id": line.id, "packaging_type": line.packaging_type,
                "paper_quality": line.paper_quality, "specification": line.specification, "unit": line.unit,
                "usage_quantity": str(line.usage_quantity) if line.usage_quantity is not None else None, "required_quantity": str(line.required_quantity),
                "pending_available": str(max(Decimal(0), line.required_quantity - received.get(line.id, Decimal(0))
                    - pending.get(line.id, Decimal(0)) - reserved[line.id])),
                "positions": [row.model_dump(mode="json") for row in stock if row.inventory_key == line.id and row.balance > 0],
            } for line in lines]}


def _stock_requests(plan):
    for target in plan["targets"]:
        for line in target["lines"]:
            for part in line["stock"]:
                yield target, line, part


def create(db, number, payload: SplitCreate, user):
    from app.services import carton_procurement as core
    from app.services.carton_customer_assignment import ensure_customer_operation
    factory = core.require_carton_factory(payload.factory_id)
    core._lock_receipt_factory(db, factory)
    source = _get_order(db, factory, number)
    ensure_customer_operation(db, user, factory, source.customer_code)
    request_key = "CAE-SPLIT-" + hashlib.sha256(json.dumps([factory, user.id, payload.request_id]).encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps([number, payload.model_dump(mode="json", exclude={"request_id"})], sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == request_key))
    if previous:
        detail = json.loads(previous.detail_json)
        if detail["fingerprint"] != fingerprint:
            raise HTTPException(409, "提交标识已用于其他拆单，请核对原结果")
        return next(plan for plan in plans(db, factory) if plan["id"] == previous.entity_id)
    order = _get_order(db, factory, number)
    if order.revision != payload.expected_revision:
        raise HTTPException(409, "订单已变化，请刷新拆单数量后重试")
    if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(409, "仅已下单、部分到货或已完成订单可以拆单")
    core.get_active_customer(db, factory, order.customer_code)
    data = context(db, factory, number)
    available = {line["order_line_id"]: line for line in data["lines"]}
    actual = {line.id: line for line in core._order_lines(db, order.id)}
    current = live_plans(db, factory, order.id)
    pending_totals, stock_totals, quantities = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    existing_targets = {(norm(target["contract_no"]), norm(target["customer_po"]))
                        for plan in live_plans(db, factory) for target in plan["targets"]
                        if plan["customer_code"] == order.customer_code and norm(plan["item_no"]) == norm(order.item_no)}
    split_id = "CS-" + uuid4().hex
    targets = []
    for index, target in enumerate(payload.targets):
        key = (norm(target.contract_no), norm(target.customer_po))
        if key == (norm(order.contract_no), norm(order.customer_po)) or key in existing_targets:
            raise HTTPException(409, "拆分去向与原单或已有拆分合同／PO重复，请核对")
        existing_targets.add(key)
        occupied = db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
            CartonOrder.customer_code == order.customer_code, CartonOrder.status != "CANCELLED")).all()
        if any(norm(row.contract_no) == key[0] and norm(row.item_no) == norm(order.item_no)
               and norm(row.customer_po) == key[1] for row in occupied):
            raise HTTPException(409, "拆分去向已有正式采购订单，请先核对，不能重复记录需求")
        if order.quantity_basis == "CALCULATED" and target.product_quantity is None:
            raise HTTPException(422, "按装箱计算的订单须填写拆分产品数量")
        target_data = target.model_dump(mode="json")
        for line_index, line in enumerate(target.lines):
            if line.order_line_id not in available:
                raise HTTPException(404, "拆分纸品不属于原订单或当前厂区")
            paper = actual[line.order_line_id]
            if not paper.paper_quality or not paper.specification:
                raise HTTPException(422, "拆单前请补齐原纸品质和规格")
            stock_quantity = sum((part.quantity for part in line.stock), Decimal(0))
            total = line.pending_quantity + stock_quantity
            pending_totals[line.order_line_id] += line.pending_quantity
            quantities[line.order_line_id] += total
            if order.quantity_basis == "CALCULATED" and total != core.required_carton_quantity(target.product_quantity, paper.usage_quantity):
                raise HTTPException(422, f"{paper.packaging_type} 拆分纸品数量须等于按每箱个数取整后的需求")
            amounts = [line.pending_quantity, *(part.quantity for part in line.stock)]
            if paper.unit in {"张", "个", "件", "只", "箱"} and any(amount != amount.to_integral_value() for amount in amounts):
                raise HTTPException(422, "纸品拆分数量必须为整数")
            for part in line.stock:
                pk = positions.position_key(line.order_line_id, part.location_id)
                stock_totals[pk] += part.quantity
                position = next((row for row in available[line.order_line_id]["positions"] if row["location_id"] == part.location_id), None)
                if not position or position["position_revision"] != part.expected_position_revision:
                    raise HTTPException(409, "原库存仓位已变化，请刷新并重新核对")
            target_data["lines"][line_index].update(target_line_id=f"{PREFIX}{split_id[3:]}-{index}-{line_index}",
                packaging_type=paper.packaging_type, paper_quality=paper.paper_quality,
                specification=paper.specification, dimension_unit=paper.dimension_unit, unit=paper.unit)
        if order.quantity_basis == "CALCULATED" and {line.order_line_id for line in target.lines} != set(actual):
            raise HTTPException(422, "按装箱计算的订单必须逐纸品分配完整拆分需求")
        targets.append(target_data)
    for identifier, amount in pending_totals.items():
        if amount > Decimal(available[identifier]["pending_available"]):
            raise HTTPException(409, "待到数量已被收货草稿或其他拆单占用，不能超量分配")
    reserved_stock = defaultdict(Decimal)
    for plan in current:
        if plan["status"] == "PENDING_WAREHOUSE":
            for _, line, part in _stock_requests(plan):
                reserved_stock[positions.position_key(line["order_line_id"], part["location_id"])] += Decimal(part["quantity"])
    all_positions = {positions.position_key(line_id, part["location_id"]): Decimal(part["balance"])
                     for line_id, row in available.items() for part in row["positions"]}
    if any(amount + reserved_stock[pk] > all_positions.get(pk, Decimal(0)) for pk, amount in stock_totals.items()):
        raise HTTPException(409, "只能拆分尚未领用且未被其他待确认拆单占用的库存")
    allocated_products = sum((Decimal(target["product_quantity"] or 0) for plan in current for target in plan["targets"]), Decimal(0))
    products = sum((target.product_quantity or Decimal(0) for target in payload.targets), Decimal(0))
    if order.product_order_quantity is not None and allocated_products + products > order.product_order_quantity:
        raise HTTPException(409, "拆分产品数量超过原订单剩余可分配数量")
    if order.quantity_basis == "CALCULATED":
        rest = order.product_order_quantity - allocated_products - products
        for identifier, paper in actual.items():
            existing_papers = sum((Decimal(line["pending_quantity"]) + sum((Decimal(part["quantity"]) for part in line["stock"]), Decimal(0))
                                  for plan in current for target in plan["targets"] for line in target["lines"] if line["order_line_id"] == identifier), Decimal(0))
            needed = existing_papers + quantities[identifier] + (core.required_carton_quantity(rest, paper.usage_quantity) if rest else 0)
            if needed > paper.required_quantity:
                raise HTTPException(409, f"拆分装箱取整后 {paper.packaging_type} 额外需要 {needed - paper.required_quantity} {paper.unit}，请另行补充采购；本次拆单未保存")
    plan = {"id": split_id, "order_id": order.id, "order_no": order.order_no, "factory_id": factory,
        "customer_code": order.customer_code, "customer_name": order.customer_name, "item_no": order.item_no,
        "original_contract_no": order.contract_no, "supplier_id": order.supplier_id,
        "status": "PENDING_WAREHOUSE" if stock_totals else "ACTIVE", "reason": payload.reason, "targets": targets}
    event = core._audit(db, user, factory, "ORDER_SPLIT_CREATED", "carton_order_split", split_id,
                        {"plan": plan, "fingerprint": fingerprint})
    event.id = request_key
    order.revision += 1
    order.updated_by, order.updated_by_name, order.updated_at = user.id, user.display_name, core.now_text()
    db.commit()
    return next(row for row in plans(db, factory) if row["id"] == split_id)


def _move(db, plan, target, line, allocations, user, receipt_id=""):
    from app.services import carton_procurement as core
    parent = db.get(CartonOrderLine, line["order_line_id"])
    timestamp = core.now_text()
    core._ensure_period_open(db, plan["factory_id"], plan["customer_code"], timestamp)
    amount = sum((Decimal(part["quantity"]) for part in allocations), Decimal(0))
    common = {"factory_id": plan["factory_id"], "customer_code": plan["customer_code"], "customer_name": plan["customer_name"],
        "item_no": plan["item_no"], "packaging_type": parent.packaging_type, "paper_quality": parent.paper_quality,
        "specification": parent.specification, "unit": parent.unit, "currency": parent.currency,
        "movement_type": "ADJUSTMENT", "source_type": "ORDER_SPLIT", "source_id": plan["id"],
        "document_no": plan["id"], "reason": "拆单库存归属调整：" + plan["reason"],
        "actor_user_id": user.id, "actor_name": user.display_name, "occurred_at": timestamp, "issue_kind": "OTHER"}
    negative = CartonInventoryMovement(**common, id="CIM-" + uuid4().hex, source_line_id="CSM-" + uuid4().hex,
        order_line_id=parent.id, contract_no=parent.contract_no, quantity=-amount, unit_price=parent.unit_price)
    valuation = load_valuation(db, plan["factory_id"])
    key = cost_key(negative)
    balance = valuation.balances.get(key)
    if not balance or balance.quantity < amount or key in valuation.unpriced_pools or any(cost_key(row) == key for row, _ in valuation.errors):
        raise HTTPException(409, "原库存不足、未核价或历史计价异常，请先核对再拆单")
    negative.unit_price = (balance.amount / balance.quantity).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)
    positive = CartonInventoryMovement(**common, id="CIM-" + uuid4().hex, source_line_id="CSM-" + uuid4().hex,
        order_line_id=line["target_line_id"], contract_no=target["contract_no"], quantity=amount, unit_price=negative.unit_price)
    positions.post(db, negative, allocations=[{**part, "quantity": str(-Decimal(part["quantity"]))} for part in allocations])
    positions.post(db, positive, allocations=allocations)
    pair = {"from_id": negative.id, "to_id": positive.id, "quantity": str(amount),
        "target_line_id": line["target_line_id"], "order_line_id": parent.id, "receipt_id": receipt_id}
    core._audit(db, user, plan["factory_id"], "ORDER_SPLIT_STOCK_MOVED", "carton_order_split", plan["id"], {"pairs": [pair]})
    db.flush()


def act(db, split_id, payload: SplitAction, user, *, cancel=False):
    from app.services import carton_procurement as core
    factory = core.require_carton_factory(payload.factory_id)
    core._lock_receipt_factory(db, factory)
    plan = next((plan for plan in plans(db, factory) if plan["id"] == split_id), None)
    if not plan:
        raise HTTPException(404, "拆单记录不存在")
    if plan["revision"] != payload.expected_revision:
        raise HTTPException(409, "拆单已被处理，请刷新后核对")
    if plan["status"] == "CANCELLED" or not cancel and plan["status"] != "PENDING_WAREHOUSE":
        raise HTTPException(409, "当前拆单状态不能执行该操作")
    if cancel:
        from app.services.carton_customer_assignment import ensure_customer_operation
        source = db.get(CartonOrder, plan["order_id"])
        ensure_customer_operation(db, user, factory, source.customer_code)
        if plan["pairs"]:
            _reverse_pairs(db, plan, payload.reason, user)
    else:
        totals, revisions, _ = positions.state(db, factory)
        requirements = defaultdict(Decimal)
        for _, line, part in _stock_requests(plan):
            pk = positions.position_key(line["order_line_id"], part["location_id"])
            requirements[pk] += Decimal(part["quantity"])
            if revisions.get(pk) != part["expected_position_revision"]:
                raise HTTPException(409, "原库存已收发或调仓，请撤销本方案后重新拆单")
        if any(totals[pk] < quantity for pk, quantity in requirements.items()):
            raise HTTPException(409, "当前可用库存不足，本次拆单未过账")
        for target in plan["targets"]:
            for line in target["lines"]:
                if line["stock"]:
                    _move(db, plan, target, line, line["stock"], user)
    core._audit(db, user, factory, "ORDER_SPLIT_CANCELLED" if cancel else "ORDER_SPLIT_CONFIRMED",
                "carton_order_split", split_id, {"reason": payload.reason})
    order = db.get(CartonOrder, plan["order_id"])
    order.revision += 1
    order.updated_by, order.updated_by_name, order.updated_at = user.id, user.display_name, core.now_text()
    db.commit()
    return next(row for row in plans(db, factory) if row["id"] == split_id)


def _reverse_pairs(db, plan, reason, user):
    from app.services import carton_procurement as core
    keys = {line["target_line_id"] for target in plan["targets"] for line in target["lines"]}
    rows = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == plan["factory_id"],
        CartonInventoryMovement.order_line_id.in_(keys))))
    # Once consumed or corrected, ownership history must not be erased by an undo.
    if any(row.source_type != "ORDER_SPLIT" for row in rows):
        raise HTTPException(409, "拆分库存已有出库、调整或冲销记录，不能撤销，请由主管核对库存归属")
    for pair in reversed(plan["pairs"]):
        for identifier in (pair["to_id"], pair["from_id"]):
            original = db.get(CartonInventoryMovement, identifier)
            core._ensure_period_open(db, plan["factory_id"], original.customer_code, original.occurred_at)
            timestamp = core.now_text()
            core._ensure_period_open(db, plan["factory_id"], original.customer_code, timestamp)
            reversal_id = "CIM-" + uuid4().hex
            snapshot = {name: getattr(original, name) for name in ("factory_id", "order_line_id", "customer_code", "customer_name",
                "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "currency", "unit_price")}
            reversal = CartonInventoryMovement(**snapshot, id=reversal_id, movement_type="REVERSAL", quantity=-original.quantity,
                document_no="REV-" + plan["id"], source_type="SPLIT_REVERSAL", source_id=plan["id"], source_line_id=reversal_id,
                reversal_of_movement_id=original.id, reason=reason, actor_user_id=user.id, actor_name=user.display_name, occurred_at=timestamp)
            positions.post(db, reversal, reverse=original)
            core._audit(db, user, plan["factory_id"], "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id,
                        {"reversal_id": reversal_id, "split_id": plan["id"], "reason": reason})
    valuation = load_valuation(db, plan["factory_id"])
    if any(row.order_line_id in keys for row, _ in valuation.errors):
        raise HTTPException(409, "拆单撤销后库存金额未对平，本次未保存，请核对后续库存记录")


def receipt_preview(db, factory, lines):
    supplied = {line["order_line_id"]: Decimal(str(line["effective_quantity"])) for line in lines if line.get("order_line_id")}
    remaining = dict(supplied)
    distribution, blocked = [], []
    for plan in live_plans(db, factory):
        for target in plan["targets"]:
            for line in target["lines"]:
                identifier = line["order_line_id"]
                if supplied.get(identifier, Decimal(0)) <= 0:
                    continue
                if plan["status"] == "PENDING_WAREHOUSE":
                    blocked.append(plan["id"])
                    continue
                amount = min(remaining[identifier], Decimal(line["pending_remaining"]))
                if amount <= 0:
                    continue
                remaining[identifier] -= amount
                distribution.append({"plan_id": plan["id"], "target_line_id": line["target_line_id"], "order_line_id": identifier,
                    "contract_no": target["contract_no"], "customer_po": target["customer_po"], "item_no": plan["item_no"],
                    "packaging_type": line["packaging_type"], "quantity": format(amount.quantize(Decimal(".0001")), "f"), "unit": line["unit"]})
    token = hashlib.sha256(json.dumps(distribution, sort_keys=True).encode()).hexdigest() if distribution else ""
    return {"allocations": distribution, "confirmation": token, "blocked_plans": sorted(set(blocked))}


def validate_receipt_confirmation(db, factory, lines, confirmation):
    preview = receipt_preview(db, factory, lines)
    if preview["blocked_plans"]:
        raise HTTPException(409, "原订单有拆单待仓库确认，请先确认或撤销拆单方案，再确认收货")
    if preview["confirmation"] and confirmation != preview["confirmation"]:
        raise HTTPException(409, "本次收货涉及拆单，请刷新拆分去向并由仓库确认分配后再入库")
    return preview


def allocate_receipt(db, receipt, lines, preview, user):
    from app.models.carton_positions import CartonPositionEntry
    from app.services.carton_replenishment_receipts import receipt_links
    replacements = receipt_links(db, receipt.factory_id)
    current_plans = {plan["id"]: plan for plan in live_plans(db, receipt.factory_id)}
    by_line = {line.order_line_id: line for line in lines}
    remaining_positions = {}
    for allocation in preview["allocations"]:
        source = by_line[allocation["order_line_id"]]
        if source.id in replacements:
            raise HTTPException(409, "补单收货需先核对拆分需求，不能自动分配到拆单合同")
        if source.id not in remaining_positions:
            movement = db.scalar(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == receipt.factory_id,
                CartonInventoryMovement.source_type == "RECEIPT", CartonInventoryMovement.source_line_id == source.id))
            parts = db.scalars(select(CartonPositionEntry).where(CartonPositionEntry.factory_id == receipt.factory_id,
                CartonPositionEntry.movement_id == movement.id).order_by(CartonPositionEntry.id)).all()
            remaining_positions[source.id] = [[part.location_id, part.quantity] for part in parts]
        amount = Decimal(allocation["quantity"])
        parts = []
        for position in remaining_positions[source.id]:
            taken = min(amount, position[1])
            if taken > 0:
                parts.append({"location_id": position[0], "quantity": str(taken)})
                amount -= taken
                position[1] -= taken
        if amount:
            raise HTTPException(409, "本次收货仓位分配不足，拆单未过账")
        plan = current_plans[allocation["plan_id"]]
        target, line = next((target, line) for target in plan["targets"] for line in target["lines"]
                            if line["target_line_id"] == allocation["target_line_id"])
        _move(db, plan, target, line, parts, user, receipt.id)


def target_origin(db, factory, identifier):
    if not identifier or not identifier.startswith(PREFIX):
        return None
    return next(((plan, target, line) for plan in plans(db, factory) for target in plan["targets"]
                 for line in target["lines"] if line["target_line_id"] == identifier), None)


def schedule_matches(db, factory, row, records=None):
    po = row.get("source_reference") if row.get("template") == "unified-item" and row.get("source_reference") else row.get("customer_po")
    return [(plan, target) for plan in (live_plans(db, factory) if records is None else records) for target in plan["targets"]
            if row.get("schedule_customer_code") == plan["customer_code"] and norm(row.get("contract_no")) == norm(target["contract_no"])
            and norm(row.get("item_no")) == norm(plan["item_no"])
            and (not po or norm(po) == norm(target["customer_po"]))]


def annotate_schedule(db, factory, row, records=None):
    matches = schedule_matches(db, factory, row, records)
    if not matches:
        return False
    if len(matches) != 1:
        row.update(match_status="AMBIGUOUS", procurement_state="REVIEW", suggestion="同合同货号存在多个拆分 PO，请补充 PO 后核对拆单")
        return True
    plan, target = matches[0]
    parent = db.get(CartonOrder, plan["order_id"])
    exact_orders = list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
        CartonOrder.customer_code == plan["customer_code"], CartonOrder.status != "CANCELLED")))
    po = row.get("source_reference") if row.get("template") == "unified-item" and row.get("source_reference") else row.get("customer_po")
    if any(norm(order.contract_no) == norm(target["contract_no"]) and norm(order.item_no) == norm(plan["item_no"])
           and (not po or norm(order.customer_po) == norm(po)) for order in exact_orders):
        row.update(match_status="AMBIGUOUS", procurement_state="REVIEW", suggestion="该合同货号同时匹配原采购和拆单，请按客户 PO 核对")
        return True
    expected = Decimal(target["product_quantity"]) if target["product_quantity"] is not None else None
    mismatch = expected is None or Decimal(str(row.get("quantity") or 0)) != expected
    complete = plan["status"] == "ACTIVE" and all(Decimal(line["pending_remaining"]) == 0 for line in target["lines"])
    row.update(order_id=parent.id, order_no=parent.order_no, order_status=parent.status,
        customer_code=plan["customer_code"], customer_name=plan["customer_name"], split_id=plan["id"],
        match_basis="原采购单的拆分记录", match_status="QUANTITY_MISMATCH" if mismatch else "MATCHED",
        procurement_state="REVIEW" if mismatch else "COMPLETED" if complete else "ORDERED",
        suggestion="已关联原采购单拆分记录，不重复下单" + ("；拆分产品数量未知或与排期不符，请核对" if mismatch else "")
            + ("；库存拆分待仓库确认" if plan["status"] == "PENDING_WAREHOUSE" else ""))
    if row.get("date_review_required"):
        row["suggestion"] += "；日期原文需人工确认"
        if not mismatch:
            row["match_status"] = "REVIEW_REQUIRED"
    source_due = str(row.get("customer_due_date") or "")
    if source_due and parent.customer_due_date and source_due != parent.customer_due_date:
        row["date_difference"] = {"business_date": source_due, "order_date": parent.customer_due_date}
        row["suggestion"] += "；业务交期与原采购交期不一致，请核对拆分合同交期"
        if row["match_status"] == "MATCHED":
            row["match_status"] = "DATE_MISMATCH"
    return True


def remaining_products(db, order, records=None):
    if order.product_order_quantity is None:
        return None
    targets = [target for plan in (live_plans(db, order.factory_id, order.id) if records is None else records)
               if plan["order_id"] == order.id for target in plan["targets"]]
    if any(target["product_quantity"] is None for target in targets):
        return None
    return order.product_order_quantity - sum((Decimal(target["product_quantity"]) for target in targets), Decimal(0))
