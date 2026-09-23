from decimal import Decimal
from uuid import uuid4
from app.models import uv_operations as m
from . import common as c


def balance(db, user, body, location):
    values = dict(id=uuid4().hex, factory_id=m.FACTORY, sku_id=body.sku_id, lot=body.lot, location=location, quantity_ml=0, cost_value=0, currency=body.currency, version=1, created_at=m.now(), updated_at=m.now(), created_by=user.id)
    c.insert_once(db, m.UvOpsInkBalance, values, ["factory_id", "sku_id", "lot", "location"])
    row = db.scalar(c.query(m.UvOpsInkBalance).where(m.UvOpsInkBalance.sku_id == body.sku_id, m.UvOpsInkBalance.lot == body.lot, m.UvOpsInkBalance.location == location).with_for_update().execution_options(populate_existing=True))
    c.require(row.currency == body.currency, "currency_mismatch", "同一库存批次必须使用同一币种", 422)
    return row


def movement(db, user, body):
    c.lock_period(db, body.business_date)
    # Lock the SKU before creating balances, including initially empty keys.
    c.get(db, m.UvOpsInkSku, body.sku_id, lock=True)
    if body.task_id:
        c.get(db, m.UvOpsTask, body.task_id)
    locations = sorted({body.location, body.target_location} - {None})
    balances = {location: balance(db, user, body, location) for location in locations}
    source = balances[body.location]
    c.require(source.version == body.expected_version or (body.expected_version == 0 and source.quantity_ml == 0), "version_conflict", "库存已变化，请刷新余额后重试", version=source.version)
    quantity, cost = body.quantity_ml, body.cost_value
    original = None
    if body.kind in {"reverse", "return"}:
        c.require(body.reversal_of is not None, "original_required", "退回或冲销必须关联原流水", 422)
        original = c.get(db, m.UvOpsInkMovement, body.reversal_of, lock=True)
        c.require(original.balance_id == source.id and original.kind in {"receipt", "consume", "stocktake_in", "stocktake_out"}, "reversal_target", "该流水不能在此库存上冲销")
        c.require(quantity == original.quantity_ml, "full_reversal", "冲销需按原流水数量完整反向，再录入正确数量", 422)
        if body.kind == "return":
            c.require(original.kind == "consume", "return_target", "耗用退回必须对应原耗用流水", 422)
        cost = original.cost_value
    incoming = body.kind in {"receipt", "stocktake_in"} or (original is not None and original.kind in {"consume", "stocktake_out"})
    if incoming:
        c.require(cost is not None, "cost_required", "入库缺少有依据的金额，不能按零处理", 422)
        source.quantity_ml += quantity
        source.cost_value += cost
    else:
        c.require(source.quantity_ml >= quantity, "stock_insufficient", "库存不足，不能产生负库存")
        if original is None:
            cost = source.cost_value if source.quantity_ml == quantity else (source.cost_value * quantity / source.quantity_ml).quantize(Decimal("0.000001"))
        c.require(source.cost_value >= cost, "stock_cost_conflict", "原成本已被后续使用，不能直接冲销")
        source.quantity_ml -= quantity
        source.cost_value -= cost
    target = None
    if body.kind == "transfer":
        c.require(body.target_location and body.target_location != body.location, "transfer_target", "请选择不同的目标库位", 422)
        target = balances[body.target_location]
        target.quantity_ml += quantity
        target.cost_value += cost
        c.touch(target)
    c.touch(source)
    entry = c.add(db, m.UvOpsInkMovement, user, balance_id=source.id, other_balance_id=target.id if target else None, task_id=body.task_id, kind=body.kind, quantity_ml=quantity, cost_value=cost, currency=body.currency, business_date=body.business_date, reversal_of=body.reversal_of, evidence=body.evidence)
    return dict(entry=c.record(entry), balance=c.record(source), target=c.record(target) if target else None)
