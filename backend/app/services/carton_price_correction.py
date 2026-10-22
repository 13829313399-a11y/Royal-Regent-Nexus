"""Three-party receipt-price corrections; original quantity and cash facts stay immutable."""
import hashlib
import json
from decimal import Decimal, localcontext
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt, CartonReceiptLine, CartonInventoryMovement, CartonSupplier, CartonClosing
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_supplier_settlement import CartonSupplierSettlement
from app.services import carton_procurement as core, carton_price_review as reviews, carton_supplier_settlement as settlement
from app.services.carton_inventory_valuation import value_movements, cost_key
from app.services.carton_ledger_time import ledger_rows, ledger_time

ENTITY = "carton_price_correction"
EVENT = "RECEIPT_PRICE_CORRECTION_ACTION"
COST_EVENT = "INVENTORY_PRICE_CORRECTED"
ZERO = Decimal(0)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def number(value):
    return format(Decimal(value), "f") if value is not None else None


def events(db, factory):
    return list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory).order_by(CartonAuditEvent.sequence)))


def state(records, identifier):
    result = dict(revision=0, proposal=None, history=[], versions=[])
    for event in records:
        if event.entity_type != ENTITY or event.entity_id != identifier or event.event_type != EVENT: continue
        detail = json.loads(event.detail_json); data = detail["data"]; name = detail["action"]
        result["revision"] = detail["revision"]
        result["history"].append(dict(id=event.id, action=name, created_at=event.created_at, actor_name=event.actor_name,
            reason=data["reason"], proposal_id=data.get("proposal_id"), data=data))
        if name == "PROPOSE":
            if result["proposal"] and result["proposal"]["status"] in {"PENDING_SUPPLIER", "SUPPLIER_CONFIRMED", "DISPUTED"}: result["proposal"]["status"] = "SUPERSEDED"
            proposal = dict(data, id=data["proposal_id"], version=len(result["versions"])+1, status="PENDING_SUPPLIER", created_at=event.created_at, created_by=event.actor_name)
            result["proposal"] = proposal; result["versions"].append(proposal)
        elif name in {"SUPPLIER_CONFIRM", "SUPPLIER_DISPUTE"}:
            result["proposal"].update(status="SUPPLIER_CONFIRMED" if name == "SUPPLIER_CONFIRM" else "DISPUTED",
                supplier_review=dict(decision=name, by=event.actor_name, at=event.created_at, reason=data["reason"]))
        elif name == "FINAL_CONFIRM": result["proposal"].update(status="APPLIED", applied_at=event.created_at, applied_by=event.actor_name)
        elif name == "WITHDRAW": result["proposal"]["status"] = "WITHDRAWN"
    return result


def effective_price(movement, records):
    price, version = Decimal(movement.unit_price), "RAW"
    for event in records:
        if event.entity_id == movement.id and event.event_type in {"INVENTORY_PRICE_CONFIRMED", COST_EVENT}:
            price, version = Decimal(str(json.loads(event.detail_json)["unit_price"])), event.id
    return price, version, bool(price != 0 or version != "RAW")


def authorize(db, user, factory, *, external=False, role="read"):
    from app.services import carton_special_requests as special, carton_supplier_portal as portal
    core.require_carton_factory(factory)
    if external:
        supplier = portal.supplier_access(db, user, factory)
        if role != "read" and not portal.supplier_permission(user, "carton_supplier:approve", factory): raise HTTPException(403, "没有本厂供应商价格确认权限")
        return supplier.id
    permissions = ("read",) if role == "read" else ("read", "receipt_write", "inventory_write") if role == "propose" else ("read", "inventory_write", "closing_manage", "order_adjust")
    if not all(special.allowed(user, factory, permission) for permission in permissions): raise HTTPException(403, "没有本厂对应的入库单价更正权限")
    return None


def can_role(db, user, factory, role):
    try: authorize(db, user, factory, role=role); return True
    except HTTPException as exc:
        if exc.status_code != 403: raise
        return False


def source(db, factory, identifier, records=None):
    records = events(db, factory) if records is None else records
    line = db.get(CartonReceiptLine, identifier)
    receipt = db.get(CartonReceipt, line.receipt_id) if line and line.factory_id == factory else None
    if not receipt or receipt.factory_id != factory: raise HTTPException(404, "本厂收料纸品不存在")
    movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory,
        CartonInventoryMovement.source_type == "RECEIPT", CartonInventoryMovement.source_id == receipt.id, CartonInventoryMovement.source_line_id == line.id)))
    movement = movements[0] if len(movements) == 1 else None
    supplier = db.get(CartonSupplier, receipt.supplier_id)
    review = db.scalar(select(CartonPriceReview).where(CartonPriceReview.factory_id == factory, CartonPriceReview.receipt_line_id == identifier))
    price, price_version, known = effective_price(movement, records) if movement else (None, "", False)
    payable = review.proposed_unit_price if review and review.status == "CONFIRMED" else None if review else price
    from app.services.carton_replenishment_receipts import receipt_links
    replacement = receipt_links(db, factory).get(identifier, {})
    if replacement.get("responsibility") == "SUPPLIER":
        payable = ZERO  # Contractual free replacement never exposes carrying cost as payable.
    frozen = ""
    original_supplier_price = number(review.original_unit_price) if review else None
    gift = False
    if review:
        from app.models.carton_supplier_portal import SupplierShipmentLine
        from app.models.carton_special_requests import SpecialShipmentLine, SpecialShipment, SpecialRequest
        original = db.get(SupplierShipmentLine if review.source_kind == "REGULAR" else SpecialShipmentLine, review.shipment_line_id)
        frozen = original.snapshot_json if original and original.factory_id == factory else ""
        if review.source_kind == "SPECIAL" and original:
            shipment = db.get(SpecialShipment, original.shipment_id)
            request = db.get(SpecialRequest, shipment.request_id) if shipment else None
            gift = bool(request and request.kind == "SUPPLIER_GIFT")
    elif movement and receipt.status == "POSTED":
        period = (receipt.acceptance_date or settlement._posting_date(receipt.confirmed_at))[:7]
        rows,base_fp,_,_ = settlement.sources(db,factory,receipt.supplier_id,period,core.normalize_currency(line.currency))
        from app.services.carton_settlement_collaboration import build
        vendor = next((row.get("supplier_delivery") for row in build(db,factory,receipt.supplier_id,period,core.normalize_currency(line.currency),rows,base_fp)["sources"]
            if row["source_key"] == "RECEIPT:"+identifier), None)
        if vendor:
            frozen = encoded({key:vendor.get(key) for key in ("shipment_id","line_id","document_no","delivery_date","original_unit_price","original_quantity")})
            original_supplier_price = vendor.get("original_unit_price")
    invalid = []
    from app.models.carton_special_requests import SpecialReceiptLink,SpecialShipmentLine,SpecialShipment,SpecialRequest
    special_link=db.scalar(select(SpecialReceiptLink).where(SpecialReceiptLink.factory_id==factory,SpecialReceiptLink.receipt_line_id==identifier))
    if special_link:
        special_line=db.get(SpecialShipmentLine,special_link.shipment_line_id)
        special_shipment=db.get(SpecialShipment,special_line.shipment_id) if special_line and special_line.factory_id==factory else None
        special_request=db.get(SpecialRequest,special_shipment.request_id) if special_shipment and special_shipment.factory_id==factory else None
        if not special_request or special_request.factory_id!=factory or special_request.supplier_id!=receipt.supplier_id:
            invalid.append("旧特殊收料原需求或供应商来源无法明确，请先核实原单")
        else:
            gift=gift or special_request.kind=="SUPPLIER_GIFT"
            if replacement.get("responsibility") == "SUPPLIER":
                original = json.loads(special_line.snapshot_json)
                original_supplier_price = None if original.get("source_origin") == "WAREHOUSE_MANUAL" else number(original.get("unit_price"))
    elif review and review.source_kind=="SPECIAL": invalid.append("特殊收料缺少精确原收料关联，请先核实原单")
    if receipt.status != "POSTED" or line.effective_quantity <= 0 or not movement: invalid.append("须关联唯一有效已入库收料及其原入库流水")
    elif (movement.quantity != line.effective_quantity or movement.unit != line.unit or core.normalize_currency(movement.currency) != core.normalize_currency(line.currency)
            or movement.unit_price != line.unit_price): invalid.append("原收料数量、单位、币种或入库价证据不一致，请先核实来源")
    if movement and any(row.reversal_of_movement_id == movement.id for row in db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory, CartonInventoryMovement.reversal_of_movement_id == movement.id))): invalid.append("原入库已冲销，不可更正价格")
    if not supplier or supplier.status != "ACTIVE" or supplier.factory_id != factory or supplier.supplier_code != "HEYUAN-DONGKANG": invalid.append("原收料未明确可协同的本厂东康供应商")
    if not receipt.acceptance_date: invalid.append("原收料实际验收日期待核实，请先沿实际验收日期补证入口核实，再更正价格；不能按记账月份猜测供应商归月")
    if line.order_line_id:
        from app.models.carton_procurement import CartonOrderLine, CartonOrder
        order_line = db.get(CartonOrderLine, line.order_line_id)
        order = db.get(CartonOrder, order_line.order_id) if order_line and order_line.factory_id == factory else None
        if not order or order.factory_id != factory or order.supplier_id != receipt.supplier_id: invalid.append("原收料与关联订单供应商不一致，请先核实来源归属")
    if not known: invalid.append("原入库价格仍未知，请先完成待核价流程")
    if movement and known and price == 0 and not any(event.event_type == COST_EVENT and event.entity_id == movement.id for event in records):
        invalid.append("原批次已确认为免费，不属于已知非零单价更正范围")
    if gift or replacement.get("responsibility") == "SUPPLIER": invalid.append("免费赠送或供应商责任换补不能通过价格更正变成收费采购")
    fp = digest([receipt.id, receipt.revision, receipt.status, receipt.supplier_id, receipt.acceptance_date,
        [getattr(line, key) for key in ("id", "order_line_id", "effective_quantity", "unit", "unit_price", "currency")],
        [movement.id, movement.quantity, movement.unit_price, movement.currency] if movement else None, number(price), price_version,
        [review.id, review.revision, review.status, number(review.proposed_unit_price)] if review else None, frozen, replacement])
    return dict(line=line, receipt=receipt, movement=movement, supplier=supplier, review=review, cost=price, payable=payable,
        known=known, source_fingerprint=fp, records=records, state=state(records, identifier), invalid=invalid,
        original_supplier_price=original_supplier_price)


def _block(code, message, kind="SOURCE", identifier=None, period=None):
    return dict(code=code, message=message, kind=kind, id=identifier, period=period)


def _price(value, free, current):
    if value is None: raise HTTPException(422, "请填写明确的新单价")
    if value == 0 and not free: raise HTTPException(422, "新价为零须明确免费凭证")
    if free and value != 0: raise HTTPException(422, "免费确认仅适用于零单价")
    if current["cost"] == value and current["payable"] == value: raise HTTPException(409, "新价与当前成本价及应付价相同，无须生成更正")
    from app.schemas.carton_supplier_settlement import StatementLine
    from pydantic import ValidationError
    from decimal import DecimalException
    try:
        with localcontext() as context:
            context.prec=48
            StatementLine(id="correction-preview",quantity=current["line"].effective_quantity,unit_price=value,amount=settlement.money(current["line"].effective_quantity*value))
    except (ValidationError,DecimalException) as exc: raise HTTPException(422,"更正金额超过月结允许位数或精度") from exc
    return Decimal(value)


def impact(db, current, price):
    records, movement, line, receipt = current["records"], current["movement"], current["line"], current["receipt"]
    rows = ledger_rows(db, receipt.factory_id)
    before = value_movements(rows, records)
    synthetic = SimpleNamespace(id="PREVIEW-CORRECTION", entity_id=movement.id, event_type=COST_EVENT,
        sequence=max((event.sequence for event in records), default=0)+1, detail_json=encoded(dict(unit_price=number(price))))
    after = value_movements(rows, records+[synthetic])
    changed = [row for row in rows if before.amounts[row.id] != after.amounts[row.id]]
    keys = {cost_key(row) for row in changed} | {cost_key(movement)}
    blockers = [_block("INVALID_SOURCE", message) for message in current["invalid"]]
    proposal = current["state"]["proposal"]
    if proposal and proposal["source_fingerprint"] != current["source_fingerprint"] and proposal["status"] not in {"APPLIED", "WITHDRAWN"}: blockers.append(_block("STALE_SOURCE", "原收料或价格依据已变化，请重新提议并由供应商确认"))
    for row, message in before.errors+after.errors:
        if cost_key(row) in keys: blockers.append(_block("AMBIGUOUS_REPLENISHMENT" if "补货" in message else "VALUATION_ERROR", message, "VALUATION", row.id))
    if (any(key in before.unpriced_pools or key in after.unpriced_pools for key in keys)
            or any(row.id in before.unpriced_movements or row.id in after.unpriced_movements for row in changed)):
        blockers.append(_block("UNRESOLVED_PRICE", "受影响库存或已耗用成本仍有未知价格，请先核实完整来源", "VALUATION"))
    movements = [dict(movement_id=row.id, **{key: getattr(row, key) for key in ("document_no", "movement_type", "issue_kind", "source_type", "occurred_at", "unit", "currency", "customer_name", "contract_no", "item_no")},
        quantity=number(row.quantity), old_cost_amount=number(before.amounts[row.id]), new_cost_amount=number(after.amounts[row.id]), cost_difference=number(after.amounts[row.id]-before.amounts[row.id])) for row in changed]
    pools = []
    for key in sorted(keys):
        a, b = before.balances.get(key), after.balances.get(key)
        if a is None or b is None: continue
        pools.append(dict(id=digest(key), customer_code=key[1], currency=key[-1], unit=key[-2], quantity=number(a.quantity), old_amount=number(a.amount), new_amount=number(b.amount), difference=number(b.amount-a.amount)))
    closings, closing_versions = [], []
    for closing in db.scalars(select(CartonClosing).where(CartonClosing.factory_id == receipt.factory_id)):
        earliest = min((ledger_time(row.occurred_at).strftime("%Y-%m") for row in changed if row.customer_code == closing.customer_code and core.normalize_currency(row.currency) == closing.currency), default=None)
        if not earliest or closing.period < earliest: continue
        _, end = core._period_bounds(closing.period)
        period_rows = [row for row in rows if ledger_time(row.occurred_at) < ledger_time(end)]
        a, b = value_movements(period_rows, records), value_movements(period_rows, records+[synthetic])
        old = sum((a.amounts[row.id] for row in period_rows if row.customer_code == closing.customer_code and core.normalize_currency(row.currency) == closing.currency), ZERO)
        new = sum((b.amounts[row.id] for row in period_rows if row.customer_code == closing.customer_code and core.normalize_currency(row.currency) == closing.currency), ZERO)
        closings.append(dict(id=closing.id, period=closing.period, customer_code=closing.customer_code, currency=closing.currency, status=closing.status,
            revision=closing.revision, old_ending_amount=number(old), new_ending_amount=number(new), amount_difference=number(new-old)))
        closing_versions.append([closing.id, closing.revision, closing.status])
        if closing.status == "LOCKED": blockers.append(_block("LOCKED_CLOSING", f"{closing.period} 库存已锁账，请主管由最新月份倒序解锁重核", "INVENTORY_CLOSING", closing.id, closing.period))
    period = (receipt.acceptance_date or settlement._posting_date(receipt.confirmed_at))[:7]
    bills = list(db.scalars(select(CartonSupplierSettlement).where(CartonSupplierSettlement.factory_id == receipt.factory_id,
        CartonSupplierSettlement.supplier_id == receipt.supplier_id, CartonSupplierSettlement.period == period,
        CartonSupplierSettlement.currency == core.normalize_currency(line.currency))))
    from app.services import carton_supplier_payables as payables
    account = payables.fold(payables.events(db, receipt.factory_id, receipt.supplier_id, core.normalize_currency(line.currency)))
    allocations = []
    for bill in bills:
        if bill.status == "CONFIRMED": blockers.append(_block("CONFIRMED_SUPPLIER_MONTH", f"{period} 供应商月结已确认，请先解除原分配并说明原因重开", "SUPPLIER_SETTLEMENT", bill.id, period))
        allocations.extend(row for row in payables.active_allocations(account) if row["source_id"] == "SETTLEMENT:"+bill.id or row["target_id"] == "SETTLEMENT:"+bill.id)
    for allocation in allocations: blockers.append(_block("ACTIVE_ALLOCATION", f"{allocation.get('source_document_no') or '付款/贷项'} → {allocation.get('target_document_no') or period} 第{allocation.get('target_version', '')}版已有核销，请明确解除；付款本身保留", "ALLOCATION", allocation["id"], period))
    with localcontext() as ctx:
        ctx.prec = 48
        incoming = sum((after.amounts[row.id]-before.amounts[row.id] for row in changed if row.movement_type == "INBOUND"), ZERO)
        outgoing = -sum((after.amounts[row.id]-before.amounts[row.id] for row in changed if row.movement_type == "OUTBOUND"), ZERO)
        other = sum((after.amounts[row.id]-before.amounts[row.id] for row in changed if row.movement_type not in {"INBOUND", "OUTBOUND"}), ZERO)
        ending = sum((after.balances[key].amount-before.balances[key].amount for key in keys), ZERO)
        summary = dict(currency=core.normalize_currency(line.currency), source_cost_difference=number(after.amounts[movement.id]-before.amounts[movement.id]),
            inbound_cost_difference=number(incoming), outbound_cost_difference=number(outgoing), other_cost_difference=number(other), ending_cost_difference=number(ending), bridge_difference=number(incoming-outgoing+other-ending),
            payable_difference=number(settlement.money(line.effective_quantity*price)-settlement.money(line.effective_quantity*current["payable"])) if current["payable"] is not None else None)
    fingerprint = digest([current["source_fingerprint"], number(price), [[row.id, row.quantity, row.unit_price, row.occurred_at, number(before.amounts[row.id])] for row in rows],
        [[event.id, event.sequence, event.detail_json] for event in records if event.event_type in {COST_EVENT, "INVENTORY_PRICE_CONFIRMED", "RECEIPT_REPLENISHMENT_LINKED", "SPECIAL_RECEIPT_REPLENISHMENT_LINKED", "ORDER_SPLIT_STOCK_MOVED"}],
        closing_versions, [[bill.id,bill.revision,bill.status] for bill in bills], allocations])
    return dict(impact_fingerprint=fingerprint, can_apply=not blockers, blockers=blockers, summary=summary, movements=movements, pools=pools, closings=closings)


def detail(db, user, factory, identifier, *, external=False, loaded=None, include_impact_blockers=True):
    supplier = authorize(db, user, factory, external=external)
    core._lock_receipt_factory(db, factory)
    current = loaded or source(db, factory, identifier)
    line, receipt, movement = current["line"], current["receipt"], current["movement"]
    if supplier and receipt.supplier_id != supplier: raise HTTPException(404, "本供应商收料更正不存在")
    record, proposal = current["state"], current["state"]["proposal"]
    if external and not proposal: raise HTTPException(404, "尚未发布此批次价格更正")
    status = proposal["status"] if proposal else "NONE"
    stale = bool(proposal and proposal["status"] not in {"APPLIED", "WITHDRAWN"} and (current["invalid"] or proposal["source_fingerprint"] != current["source_fingerprint"]))
    if stale: status = "STALE"
    allowed = []
    can_manage_proposal = not external and can_role(db, user, factory, "propose")
    customer_allowed = True
    if not external:
        try:
            from app.services.carton_special_requests import ensure_customer_operation
            ensure_customer_operation(db, user, factory, line.customer_code)
        except HTTPException as exc:
            if exc.status_code != 403: raise
            customer_allowed = False
    can_manage_proposal = can_manage_proposal and customer_allowed
    can_propose = can_manage_proposal and not current["invalid"]
    if can_propose: allowed.append("PROPOSE")
    if proposal and status not in {"APPLIED", "WITHDRAWN"}:
        if external and not stale:
            from app.services.carton_supplier_portal import supplier_permission
            if supplier_permission(user, "carton_supplier:approve", factory): allowed.extend(["SUPPLIER_CONFIRM", "SUPPLIER_DISPUTE"])
        elif can_manage_proposal: allowed.append("WITHDRAW")
        if not external and customer_allowed and not stale and status == "SUPPLIER_CONFIRMED" and can_role(db, user, factory, "final"): allowed.append("FINAL_CONFIRM")
    result = dict(receipt_line_id=line.id, receipt_id=receipt.id, movement_id=movement.id if movement else None, factory_id=factory, supplier_id=receipt.supplier_id,
        currency=core.normalize_currency(line.currency), quantity=number(line.effective_quantity), unit=line.unit, document_no=receipt.delivery_note_no,
        acceptance_date=receipt.acceptance_date, **{key:getattr(line,key) for key in ("customer_name","contract_no","item_no","packaging_type","paper_quality","specification")},
        revision=record["revision"], source_fingerprint=current["source_fingerprint"], status=status, can_propose=can_propose, allowed_actions=allowed,
        current_unit_price=number(current["payable"]), original_supplier_unit_price=current["original_supplier_price"], proposed_unit_price=proposal["proposed_unit_price"] if proposal else None,
        proposal=proposal, history=record["history"], versions=record["versions"], blockers=[_block("INVALID_SOURCE",message) for message in current["invalid"]])
    if not external:
        result.update(raw_unit_price=number(line.unit_price), current_cost_unit_price=number(current["cost"]))
        if include_impact_blockers and proposal and movement and proposal["status"] not in {"APPLIED", "WITHDRAWN"}: result["blockers"] = impact(db, current, Decimal(proposal["proposed_unit_price"]))["blockers"]
    else:
        safe_proposal = lambda value: {key:item for key,item in value.items() if key in {"id","version","status","proposed_unit_price","free_confirmed","document_no","document_date","reason","source_fingerprint","created_at","created_by","supplier_review","applied_at"}}
        result["proposal"] = safe_proposal(proposal) if proposal else None
        result["versions"] = [safe_proposal(version) for version in record["versions"]]
        result["history"] = []
        for event in record["history"]:
            visible = {key:value for key,value in event.items() if key != "data"}
            visible["data"] = {key:value for key,value in event["data"].items() if key in {"reason","proposed_unit_price","free_confirmed","document_no","document_date","proposal_id"}}
            if event["action"] == "FINAL_CONFIRM": visible.update(actor_name="", reason="价格更正已生效", data={"proposal_id":event["proposal_id"]})
            result["history"].append(visible)
    return result


def workspace(db, user, factory, *, external=False, status="PENDING", keyword="", limit=50, offset=0):
    supplier = authorize(db, user, factory, external=external)
    core._lock_receipt_factory(db, factory)
    if status not in {"ALL", "PENDING"}: raise HTTPException(422, "更正筛选状态无效")
    records = events(db, factory); result = []
    identifiers = list(db.scalars(select(CartonReceiptLine.id).where(CartonReceiptLine.factory_id == factory).order_by(CartonReceiptLine.id)))
    for identifier in identifiers:
        current = source(db, factory, identifier, records)
        if supplier and current["receipt"].supplier_id != supplier: continue
        if not current["state"]["proposal"] and (external or current["invalid"]): continue
        row = detail(db, user, factory, identifier, external=external, loaded=current, include_impact_blockers=False)
        result.append(row)
    pending = lambda row: row["status"] not in {"NONE", "APPLIED", "WITHDRAWN"}
    pending_count = sum(pending(row) for row in result)
    if status == "PENDING": result = [row for row in result if pending(row)]
    if keyword.strip(): result = [row for row in result if keyword.casefold() in " ".join(str(row.get(key) or "") for key in ("document_no","customer_name","contract_no","item_no","packaging_type","specification")).casefold()]
    return dict(items=result[offset:offset+limit], total=len(result), limit=limit, offset=offset, pending_count=pending_count)


def preview(db, user, identifier, payload):
    authorize(db, user, payload.factory_id, role="final")
    core._lock_receipt_factory(db, payload.factory_id)
    current = source(db, payload.factory_id, identifier)
    from app.services.carton_special_requests import ensure_customer_operation
    ensure_customer_operation(db,user,payload.factory_id,current["line"].customer_code)
    if payload.expected_revision != current["state"]["revision"] or payload.source_fingerprint != current["source_fingerprint"]: raise HTTPException(409, "收料或价格更正版本已变化，请刷新")
    if current["invalid"]: raise HTTPException(409, "；".join(current["invalid"]))
    proposal = current["state"]["proposal"]
    price = Decimal(proposal["proposed_unit_price"]) if proposal and proposal["status"] not in {"APPLIED","WITHDRAWN"} else _price(payload.proposed_unit_price, payload.free_confirmed, current)
    return dict(detail(db,user,payload.factory_id,identifier,loaded=current), impact=impact(db,current,price))


def rebuild_closings(db, user, current, affected, price_event):
    snapshots, previous = {}, []
    for projected in affected:
        closing = db.get(CartonClosing, projected["id"])
        previous.append(dict(id=closing.id, **core._closing_audit_snapshot(closing)))
        _, end = core._period_bounds(closing.period)
        rows = ledger_rows(db, closing.factory_id, before=end, customer=closing.customer_code)
        rows = [row for row in rows if core.normalize_currency(row.currency) == closing.currency]
        valuation = value_movements(ledger_rows(db, closing.factory_id, before=end), events(db, closing.factory_id))
        quantities = core._closing_current_snapshot(db, closing, valuation)
        for key,value in quantities.items(): setattr(closing,key,value)
        closing.status="DRAFT"; closing.revision+=1
        closing.confirmed_by=closing.confirmed_at=closing.locked_by=closing.locked_at=""
        closing.generated_by=user.id; closing.generated_by_name=user.display_name; closing.generated_at=core.now_text()
        snapshots[closing.id]=core._closing_unit_quantities(rows,closing.period)
    value=json.loads(price_event.detail_json); value.update(previous_closing_snapshots=previous,closing_unit_snapshots=snapshots)
    price_event.detail_json=encoded(value)


def act(db,user,identifier,payload,*,external=False):
    from app.services.carton_special_requests import locked_actor, ensure_customer_operation
    user=locked_actor(db,user,core.require_carton_factory(payload.factory_id))
    name=payload.action
    if external and name not in {"SUPPLIER_CONFIRM","SUPPLIER_DISPUTE"} or not external and name not in {"PROPOSE","FINAL_CONFIRM","WITHDRAW"}: raise HTTPException(403,"当前身份不能执行此价格更正动作")
    supplier=authorize(db,user,payload.factory_id,external=external,role="final" if name=="FINAL_CONFIRM" else "propose")
    current=source(db,payload.factory_id,identifier)
    if supplier and current["receipt"].supplier_id!=supplier: raise HTTPException(404,"本供应商收料更正不存在")
    if not external: ensure_customer_operation(db,user,payload.factory_id,current["line"].customer_code)
    request_id="CAE-PC-"+digest([payload.factory_id,user.id,payload.request_id])
    request=payload.model_dump(mode="json")
    if payload.proposed_unit_price is not None: request["proposed_unit_price"]=number(payload.proposed_unit_price.normalize())
    fingerprint=digest([identifier,request])
    prior=db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id==request_id))
    if prior:
        if json.loads(prior.detail_json)["fingerprint"]!=fingerprint: raise HTTPException(409,"提交标识已用于其他更正内容，请按原请求重试")
        return dict(detail(db,user,payload.factory_id,identifier,external=external),replayed=True)
    record=current["state"]; proposal=record["proposal"]
    if payload.expected_revision!=record["revision"] or payload.source_fingerprint!=current["source_fingerprint"]: raise HTTPException(409,"原收料、价格依据或更正版本已变化，请刷新")
    reason=payload.reason.strip()
    if len(reason)<4: raise HTTPException(422,"请填写至少四字的更正依据")
    data=dict(reason=reason,proposal_id=proposal["id"] if proposal else None)
    final_impact=None
    if name=="PROPOSE":
        if current["invalid"]: raise HTTPException(409,"；".join(current["invalid"]))
        price=_price(payload.proposed_unit_price,payload.free_confirmed,current)
        from app.schemas.carton_supplier_settlement import StatementLine
        from pydantic import ValidationError
        from decimal import DecimalException
        try: StatementLine(id="correction-check",quantity=current["line"].effective_quantity,unit_price=price,amount=settlement.money(current["line"].effective_quantity*price))
        except (ValidationError,DecimalException) as exc: raise HTTPException(422,"更正金额超过月结允许位数或精度") from exc
        if not payload.document_no.strip() or not payload.document_date: raise HTTPException(422,"请填写价格更正凭证号及日期")
        settlement.date_check(payload.document_date.isoformat())
        data.update(proposal_id="CPC-"+uuid4().hex,proposed_unit_price=number(price),free_confirmed=payload.free_confirmed,document_no=payload.document_no.strip(),document_date=payload.document_date.isoformat(),source_fingerprint=current["source_fingerprint"])
    else:
        if not proposal or proposal["status"] in {"APPLIED","WITHDRAWN"}: raise HTTPException(409,"当前没有未完成更正提议")
        if name!="WITHDRAW" and (proposal["source_fingerprint"]!=current["source_fingerprint"] or current["invalid"]): raise HTTPException(409,"原价格或收料依据已变化，请重新提议并由供应商确认")
        if name=="FINAL_CONFIRM":
            if proposal["status"]!="SUPPLIER_CONFIRMED": raise HTTPException(409,"须先由供应商确认当前批次新价")
            final_impact=impact(db,current,Decimal(proposal["proposed_unit_price"]))
            if payload.impact_fingerprint!=final_impact["impact_fingerprint"]: raise HTTPException(409,"库存、月结或核销影响预览已变化，请主管重新预览")
            if final_impact["blockers"]: raise HTTPException(409,"；".join(row["message"] for row in final_impact["blockers"][:6]))
            data["impact"]=final_impact
    event=core._audit(db,user,payload.factory_id,EVENT,ENTITY,identifier,dict(action=name,data=data,revision=record["revision"]+1,fingerprint=fingerprint,request_id=payload.request_id))
    event.id=request_id
    if name=="FINAL_CONFIRM":
        price=Decimal(proposal["proposed_unit_price"])
        price_event=core._audit(db,user,payload.factory_id,COST_EVENT,"carton_inventory_movement",current["movement"].id,
            dict(unit_price=number(price),receipt_line_id=identifier,correction_id=proposal["id"],previous_price=number(current["cost"]),reason=reason,impact=final_impact))
        review=current["review"]
        if review:
            review.proposed_unit_price=price; review.status="CONFIRMED"; review.revision+=1
            review.reason=proposal["reason"]; review.updated_by=user.id; review.updated_at=core.now_text()
            core._audit(db,user,payload.factory_id,"PRICE_REVIEW_CORRECTION_APPLIED","carton_price_review",review.id,
                dict(correction_id=proposal["id"],revision=review.revision,status="CONFIRMED",proposed_unit_price=number(price),reason=reason))
        db.flush()
        rebuild_closings(db,user,current,final_impact["closings"],price_event)
    db.flush()
    result=detail(db,user,payload.factory_id,identifier,external=external)
    if final_impact: result["impact"]=final_impact
    db.commit()
    return result
