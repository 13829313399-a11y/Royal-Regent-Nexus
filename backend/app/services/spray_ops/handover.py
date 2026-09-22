"""Physical delivery/return facts are independent from settlement/credit facts."""
from decimal import Decimal

from app.models import spray_ops as m
from .common import add, get, serialize, require, version, touch, check_period
from .production import rows, make_stock, movement, completed, piece_quantity


def delivery_detail(db, f, delivery):
    result = []
    for line in rows(db, m.SprayOpsDeliveryLine, f, delivery_id=delivery.id):
        stock = get(db, m.SprayOpsStock, f, line.stock_id)
        events = rows(db, m.SprayOpsMovement, f, kind="delivery_accept", reference_id=line.id)
        result.append({**serialize(line), "unit": stock.unit, "acceptances": [{"business_date": e.business_date, "quantity": str(e.quantity)} for e in events]})
    return {**serialize(delivery), "lines": result}


def create_delivery(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新送货单版本应为 0")
    require(len({line.stock_id for line in b.lines}) == len(b.lines), "duplicate_stock", "送货单不可重复选择库存", 422)
    delivery = add(db, m.SprayOpsDelivery, f, document_no=b.document_no, counterparty=b.counterparty, business_date=str(b.business_date), warehouse_ref=b.warehouse_ref)
    for item in b.lines:
        stock = get(db, m.SprayOpsStock, f, item.stock_id)
        require(stock.state == "finished" and stock.line_id, "not_finished", "仅合格成品库存可送货")
        line = get(db, m.SprayOpsDemandLine, f, stock.line_id)
        demand = get(db, m.SprayOpsDemand, f, line.demand_id)
        require(demand.counterparty == b.counterparty, "counterparty_mismatch", "送货委托方与订单不一致", 422)
        piece_quantity(item.quantity, stock.unit)
        add(db, m.SprayOpsDeliveryLine, f, delivery_id=delivery.id, stock_id=stock.id, quantity=item.quantity, price=line.commercial_price, currency=line.currency, price_evidence=line.price_evidence)
    if b.dispatch:
        dispatch(db, f, delivery.id, 1)
    return delivery_detail(db, f, delivery)


def dispatch(db, f, delivery_id, expected):
    delivery = get(db, m.SprayOpsDelivery, f, delivery_id)
    version(delivery, expected)
    check_period(db, f, delivery.business_date)
    require(delivery.status == "draft", "delivery_state", "仅草稿送货单可发出")
    for line in rows(db, m.SprayOpsDeliveryLine, f, delivery_id=delivery.id):
        stock = get(db, m.SprayOpsStock, f, line.stock_id)
        require(stock.state == "finished" and stock.quantity - stock.reserved >= line.quantity, "finished_shortage", "合格成品库存不足")
        stock.quantity -= line.quantity
        touch(stock)
        movement(db, f, stock, None, line.quantity, 0, "delivery_dispatch", line.id, delivery.business_date)
    delivery.status = "dispatched"
    touch(delivery)
    return delivery_detail(db, f, delivery)


def accept(db, f, delivery_id, b):
    delivery = get(db, m.SprayOpsDelivery, f, delivery_id)
    version(delivery, b.expected_version)
    require(delivery.status in {"dispatched", "partial_accepted"}, "delivery_state", "送货单不在待验收状态")
    require(len({line.delivery_line_id for line in b.lines}) == len(b.lines), "duplicate_line", "验收行不能重复", 422)
    for item in b.lines:
        line = get(db, m.SprayOpsDeliveryLine, f, item.delivery_line_id)
        require(line.delivery_id == delivery.id, "delivery_mismatch", "验收行不属于送货单", 422)
        require(item.accepted + item.rejected > 0 and line.accepted + line.rejected + item.accepted + item.rejected <= line.quantity, "acceptance_overflow", "验收数量超过在途数量")
        require(not item.rejected or item.reason, "rejection_reason", "拒收须记录原因", 422)
        stock = get(db, m.SprayOpsStock, f, line.stock_id)
        piece_quantity(item.accepted, stock.unit)
        piece_quantity(item.rejected, stock.unit)
        # Each acceptance is an immutable dated movement. The last date is only
        # a display convenience; eligibility uses the dated events below.
        line.accepted += item.accepted
        line.rejected += item.rejected
        line.accepted_date = str(b.business_date)
        touch(line)
        if item.accepted:
            movement(db, f, None, None, item.accepted, 0, "delivery_accept", line.id, b.business_date)
        if item.rejected:
            target = make_stock(db, f, stock.batch_id, stock.line_id, item.rejected, stock.unit, "hold", m.now(), completed(db, f, stock.id), rework_origin=stock.id)
            movement(db, f, None, target, item.rejected, item.rejected, "delivery_reject", line.id, b.business_date, item.reason)
    all_lines = rows(db, m.SprayOpsDeliveryLine, f, delivery_id=delivery.id)
    delivery.status = "accepted" if all(line.accepted + line.rejected == line.quantity for line in all_lines) else "partial_accepted"
    touch(delivery)
    return delivery_detail(db, f, delivery)


def return_goods(db, f, b):
    line = get(db, m.SprayOpsDeliveryLine, f, b.delivery_line_id)
    version(line, b.expected_version)
    require(b.quantity <= line.accepted - line.returned, "return_overflow", "退货不得超过净验收数量")
    stock = get(db, m.SprayOpsStock, f, line.stock_id)
    piece_quantity(b.quantity, stock.unit)
    return_record = add(db, m.SprayOpsReturn, f, delivery_line_id=line.id, quantity=b.quantity, business_date=str(b.business_date), reason=b.reason)
    target = make_stock(db, f, stock.batch_id, stock.line_id, b.quantity, stock.unit, "hold", m.now(), completed(db, f, stock.id), rework_origin=stock.id)
    movement(db, f, None, target, b.quantity, b.quantity, "customer_return", return_record.id, b.business_date, b.reason)
    line.returned += b.quantity
    touch(line)
    return {**serialize(return_record), "stock": serialize(target), "credit_required": line.settled > line.accepted - line.returned}


def container(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新周转记录版本应为 0")
    if b.delivery_id:
        delivery = get(db, m.SprayOpsDelivery, f, b.delivery_id)
        require(delivery.counterparty == b.counterparty, "counterparty_mismatch", "周转物往来方不匹配", 422)
    piece_quantity(b.quantity, "个")
    return serialize(add(db, m.SprayOpsContainer, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "business_date"}), business_date=str(b.business_date)))
