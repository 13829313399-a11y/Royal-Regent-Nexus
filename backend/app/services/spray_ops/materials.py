"""Batch-cost materials: issue is a transfer, only consumption recognizes cost."""
from decimal import Decimal

from app.models import spray_ops as m
from .common import add, get, serialize, require, version, touch, check_period
from .production import rows


def active_rule(db, f, rule_id, kind, day, *, approved=True):
    rule = get(db, m.SprayOpsRule, f, rule_id)
    require(rule.kind == kind, "rule_kind", "规则类型不匹配", 422)
    require(not approved or rule.status == "confirmed", "rule_unconfirmed", "规则尚未确认，不能用于正式业务")
    require(rule.effective_from <= str(day) and (rule.effective_until is None or rule.effective_until >= str(day)), "rule_expired", "规则不在业务日期的有效期内")
    return rule


def purchase_detail(db, f, purchase):
    return {**serialize(purchase), "lines": [serialize(line) for line in rows(db, m.SprayOpsPurchaseLine, f, purchase_id=purchase.id)]}


def create_purchase(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新采购单版本应为 0")
    purchase = add(db, m.SprayOpsPurchase, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "lines", "business_date"}), business_date=str(b.business_date))
    for item in b.lines:
        get(db, m.SprayOpsMaterial, f, item.material_id)
        add(db, m.SprayOpsPurchaseLine, f, purchase_id=purchase.id, **item.model_dump(exclude={"due_date"}), due_date=str(item.due_date))
    return purchase_detail(db, f, purchase)


def cancel_purchase(db, f, purchase_id, b):
    purchase = get(db, m.SprayOpsPurchase, f, purchase_id)
    version(purchase, b.expected_version)
    line = get(db, m.SprayOpsPurchaseLine, f, b.line_id)
    require(line.purchase_id == purchase.id, "purchase_mismatch", "采购行不属于此单", 422)
    require(b.quantity <= line.quantity - line.received - line.cancelled, "cancel_overflow", "只能取消未收货的剩余数量")
    line.cancelled += b.quantity
    touch(line)
    touch(purchase)
    return purchase_detail(db, f, purchase)


def receipt(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新入库单版本应为 0")
    receipt = add(db, m.SprayOpsMaterialReceipt, f, document_no=b.document_no, supplier=b.supplier, business_date=str(b.business_date), source_ref=b.source_ref)
    lots = []
    for item in b.lines:
        line = get(db, m.SprayOpsPurchaseLine, f, item.purchase_line_id)
        purchase = get(db, m.SprayOpsPurchase, f, line.purchase_id)
        require(purchase.supplier == b.supplier, "supplier_mismatch", "入库供应商与采购单不符", 422)
        material = get(db, m.SprayOpsMaterial, f, line.material_id)
        factor = Decimal(1)
        if line.unit != material.unit:
            require(item.conversion_rule_id, "unit_unconfirmed", "采购单位与库存单位不同，须选择确认的 SKU 换算版本")
            rule = active_rule(db, f, item.conversion_rule_id, "unit", b.business_date)
            require(rule.material_id == material.id and rule.parameters["from_unit"] == line.unit and rule.parameters["to_unit"] == material.unit, "unit_mismatch", "单位换算版本不适用于此物料", 422)
            factor = Decimal(rule.parameters["factor"])
        require(item.unit in {line.unit, material.unit}, "unit_mismatch", "收货单位与采购及库存单位均不匹配", 422)
        ordered_qty = item.quantity if item.unit == line.unit else item.quantity / factor
        base_qty = ordered_qty * factor
        require(ordered_qty <= line.quantity - line.received - line.cancelled, "over_receipt", "入库数量超过采购剩余量")
        cost = line.price / factor if line.price is not None else None
        lot = add(db, m.SprayOpsMaterialLot, f, receipt_id=receipt.id, purchase_line_id=line.id, material_id=material.id, quantity=base_qty, unit=material.unit, unit_cost=cost, currency=purchase.currency, warehouse=base_qty, conversion_rule_id=item.conversion_rule_id)
        line.received += ordered_qty
        touch(line)
        touch(purchase)
        lots.append(serialize(lot))
    return {**serialize(receipt), "lots": lots}


def move(db, f, lot_id, b):
    lot = get(db, m.SprayOpsMaterialLot, f, lot_id)
    version(lot, b.expected_version)
    if b.line_id:
        get(db, m.SprayOpsDemandLine, f, b.line_id)
    if b.kind == "issue":
        require(b.issue_id is None, "issue_reference", "领料不可指向其他领料记录", 422)
        require(lot.warehouse >= b.quantity, "material_shortage", "仓库批次库存不足")
        lot.warehouse -= b.quantity
        lot.floor += b.quantity
    else:
        require(b.issue_id, "issue_required", "耗用和退料必须选择原领料记录", 422)
        issue = get(db, m.SprayOpsMaterialMovement, f, b.issue_id)
        require(issue.kind == "issue" and issue.lot_id == lot.id, "issue_mismatch", "领料批次不匹配", 422)
        used = sum(item.quantity for item in rows(db, m.SprayOpsMaterialMovement, f, issue_id=issue.id))
        require(b.quantity <= issue.quantity - used and lot.floor >= b.quantity, "floor_shortage", "超过原领料剩余未耗用数量")
        lot.floor -= b.quantity
        if b.kind == "return":
            lot.warehouse += b.quantity
        else:
            lot.consumed += b.quantity
    event = add(db, m.SprayOpsMaterialMovement, f, lot_id=lot.id, kind=b.kind, quantity=b.quantity,
                cost=lot.unit_cost * b.quantity if b.kind == "consume" and lot.unit_cost is not None else None,
                business_date=str(b.business_date), line_id=b.line_id, issue_id=b.issue_id, reason=b.reason)
    touch(lot)
    return {**serialize(event), "lot": serialize(lot)}


def saving(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新分析记录版本应为 0")
    if b.purchase_line_id:
        get(db, m.SprayOpsPurchaseLine, f, b.purchase_line_id)
    amount = (b.old_price - b.new_price) * b.quantity
    return serialize(add(db, m.SprayOpsSaving, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "business_date"}), business_date=str(b.business_date), saving=amount, signed_difference=-amount))


def confirm_original_cost(db, f, lot_id, b):
    lot = get(db, m.SprayOpsMaterialLot, f, lot_id)
    version(lot, b.expected_version)
    require(lot.unit_cost is None, "cost_frozen", "已有批次成本不能用新价格改写")
    receipt = get(db, m.SprayOpsMaterialReceipt, f, lot.receipt_id)
    check_period(db, f, receipt.business_date)
    consumes = rows(db, m.SprayOpsMaterialMovement, f, lot_id=lot.id, kind="consume")
    for movement in consumes:
        check_period(db, f, movement.business_date)
        require(movement.cost is None, "cost_frozen", "原耗用已记录成本，不能再次补价")
    # A separate evidence event resolves the original unknown cost. Historical
    # consumption rows and previously downloaded artifacts remain untouched.
    evidence = add(db, m.SprayOpsMaterialMovement, f, lot_id=lot.id, kind="cost_confirmation", quantity=lot.quantity,
                   cost=lot.quantity * b.unit_cost, business_date=str(b.business_date), reason=b.evidence)
    adjustments = []
    for movement in consumes:
        adjustment = add(db, m.SprayOpsMaterialMovement, f, lot_id=lot.id, kind="cost_adjustment", quantity=movement.quantity,
                         cost=movement.quantity * b.unit_cost, business_date=movement.business_date, issue_id=movement.id,
                         line_id=movement.line_id, reason=f"原批次成本补确认 {evidence.id}：{b.evidence}")
        adjustments.append(serialize(adjustment))
    lot.unit_cost = b.unit_cost
    touch(lot)
    return dict(id=lot.id, lot=serialize(lot), evidence=serialize(evidence), adjustments=adjustments)
