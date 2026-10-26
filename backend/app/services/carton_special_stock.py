"""Exact-receipt stock returns and independent, immutable SPECIAL replacements.

Shared material balances never prove request ownership. Only explicit original
receipt allocations minus every later debit are a conservative reusable source.
No transfer-in, reversal or unrelated inbound recreates that proof.
"""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonReceipt, CartonReceiptLine, CartonClosing
from app.models.carton_special_requests import SpecialRequest, SpecialLine, SpecialShipment, SpecialShipmentLine, SpecialReceiptLink, SpecialVersion
from app.services import carton_special_requests as special, carton_positions as positions
from app.services.carton_inventory_identity import inventory_key
from app.services.carton_inventory_valuation import load_valuation, cost_key

EVENT = "SPECIAL_STOCK_ACTION"
LINK_EVENT = "SPECIAL_RECEIPT_REPLENISHMENT_LINKED"
ORIGIN = "REPLENISHMENT"
D = Decimal
IDENTITY = ("item_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "unit")


def number(value):
    text = format(D(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def summary(row):
    return {key: getattr(row, key) for key in ("id", "request_no", "revision", "status")}


def actions(db, factory):
    return [json.loads(event.detail_json) for event in db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory, CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence))]


def replacement(db, row):
    if row.origin != ORIGIN:
        return None
    return next((data for data in actions(db, row.factory_id) if data.get("child_request_id") == row.id), None)


def require_mutable(db, row):
    if row.origin == ORIGIN:
        raise HTTPException(409, "补单纸品、数量及责任已冻结；未发货时请使用撤销补单，不能单独改写、取消或删除")


def authorize(db, user, factory, identifier):
    row = special.access(db, user, factory, identifier)
    if not all(special.allowed(user, factory, permission) for permission in ("order_write", "inventory_write")):
        raise HTTPException(403, "退货或补单须同时具备本厂订单及库存操作权限")
    if special.portal.fixed_supplier(db, factory).id != row.supplier_id:
        raise HTTPException(409, "原需求供应商与当前厂区供应商不一致，请核实")
    return row


def eligible(db, row):
    return row.kind in {"SAMPLE", "WORKSHOP_MISC"} and row.origin in {"INTERNAL", ORIGIN} \
        and row.status in {"PARTIALLY_RECEIVED", "COMPLETED"} and not db.scalar(select(SpecialVersion.id).where(
            SpecialVersion.request_id == row.id, SpecialVersion.action == "DELETED").limit(1))


def undo_blockers(db, row, data):
    if not data:
        return ["原补单的不可变库存来源记录缺失，请核实"]
    result = []
    if row.status == "CANCELLED": result.append("补单已撤销")
    if db.scalar(select(SpecialShipment.id).where(SpecialShipment.request_id == row.id).limit(1)):
        result.append("补单已有送货历史，须沿原送货及收料流程核实，不可撤销原出库")
    if any(db.scalar(select(CartonInventoryMovement.id).where(
            CartonInventoryMovement.reversal_of_movement_id == part["debit_movement_id"])) for part in data["allocations"]):
        result.append("原补单出库已存在冲销记录")
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    try:
        ensure_evidence_open(db, row.factory_id, row.supplier_id, row.created_at[:10], special.core.now_text()[:10])
    except HTTPException as error:
        result.append(str(error.detail))
    from app.services.carton_ledger_time import ledger_time
    for part in data["allocations"]:
        movement = db.get(CartonInventoryMovement, part["debit_movement_id"])
        if not movement:
            result.append("补单原出库记录缺失")
            continue
        period = min(ledger_time(at).strftime("%Y-%m") for at in (movement.occurred_at, special.core.now_text()))
        if db.scalar(select(CartonClosing.id).where(CartonClosing.factory_id == row.factory_id,
                CartonClosing.customer_code == movement.customer_code, CartonClosing.period >= period,
                CartonClosing.status == "LOCKED").limit(1)):
            result.append("原补单出库或当前库存月份已锁账，请先由主管解锁重核")
    return result


def replacement_out(db, row, *, user=None, external=False):
    data = replacement(db, row)
    if not data:
        return None
    blockers = undo_blockers(db, row, data)
    return {"parent_request_id": data["parent_request_id"], "parent_request_no": data["parent_request_no"],
        "responsibility": data["responsibility"], "can_undo": not external and user is not None and not blockers
        and all(special.allowed(user, row.factory_id, key) for key in ("order_write", "inventory_write")), "blockers": blockers}


def preview(db, user, factory, identifier):
    row = authorize(db, user, factory, identifier)
    result = _preview(db, row)
    result["replacement"] = replacement_out(db, row, user=user)
    return result


def _preview(db, row):
    blockers = []
    if not eligible(db, row): blockers.append("只有已有实际收料的样板或杂单可按明确来源退货、补单")
    current = {paper.id: paper for paper in special.lines(db, row)}
    snapshot = positions._position_snapshot(db, row.factory_id)
    totals, by_movement = defaultdict(D), defaultdict(list)
    for entry, movement, location, canonical in snapshot:
        totals[(canonical, entry.location_id)] += entry.quantity
        if movement: by_movement[movement.id].append((entry, location, canonical))
    valuation = load_valuation(db, row.factory_id)
    all_movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == row.factory_id)))
    unallocated_debits = {inventory_key(item) for item in all_movements if item.quantity < 0 and (
        sum((entry.quantity for entry, _, _ in by_movement.get(item.id, [])), D(0)) != item.quantity
        or any(location.id == positions.unknown_id(row.factory_id) for _, location, _ in by_movement.get(item.id, [])))}
    unallocated_debits.update(canonical for entry, _, location, canonical in snapshot
        if entry.quantity < 0 and location.id == positions.unknown_id(row.factory_id))
    used, reversals = defaultdict(D), set(db.scalars(select(CartonInventoryMovement.reversal_of_movement_id).where(
        CartonInventoryMovement.factory_id == row.factory_id, CartonInventoryMovement.reversal_of_movement_id.is_not(None))))
    for data in actions(db, row.factory_id):
        for part in data["allocations"]:
            if part["debit_movement_id"] not in reversals:
                used[part["receipt_line_id"]] += D(part["quantity"])
    sources = db.execute(select(CartonReceiptLine, CartonReceipt, SpecialShipmentLine)
        .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .join(SpecialReceiptLink, SpecialReceiptLink.receipt_line_id == CartonReceiptLine.id)
        .join(SpecialShipmentLine, SpecialShipmentLine.id == SpecialReceiptLink.shipment_line_id)
        .join(SpecialShipment, SpecialShipment.id == SpecialShipmentLine.shipment_id)
        .where(CartonReceipt.factory_id == row.factory_id, SpecialShipment.request_id == row.id,
            CartonReceipt.status == "POSTED", CartonReceiptLine.effective_quantity > 0)
        .order_by(CartonReceiptLine.id)).all()
    options, evidence = [], []
    for paper, receipt, source in sources:
        immutable = json.loads(source.snapshot_json)
        movements = list(db.scalars(select(CartonInventoryMovement).where(
            CartonInventoryMovement.factory_id == row.factory_id, CartonInventoryMovement.source_type == "RECEIPT",
            CartonInventoryMovement.source_id == receipt.id, CartonInventoryMovement.source_line_id == paper.id,
            CartonInventoryMovement.quantity > 0)))
        allocations = json.loads(paper.location_allocations_json or "[]")
        if len(movements) != 1 or not allocations:
            blockers.append(f"{receipt.delivery_note_no} 缺少唯一原入库或原始明确分仓证据，不能推定库存归属")
            continue
        movement = movements[0]
        parts = by_movement.get(movement.id, [])
        declared = {part["location_id"]: D(part["quantity"]) for part in allocations}
        if (movement.id in reversals or movement.quantity != paper.effective_quantity
                or any(getattr(movement, key) != getattr(paper, key) for key in ("customer_code", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "currency"))
                or len(declared) != len(allocations) or sum(declared.values(), D(0)) != paper.effective_quantity
                or {entry.location_id: entry.quantity for entry, _, _ in parts} != declared
                or any(entry.transfer_id or entry.quantity <= 0 or location.id == positions.unknown_id(row.factory_id) for entry, location, _ in parts)):
            blockers.append(f"{receipt.delivery_note_no} 原收料、分仓与有效入库证据不一致，请核实原单")
            continue
        original = current.get(source.request_line_id)
        mismatch = original is None or any(str(getattr(original, key)) != str(immutable.get(key, "")) for key in IDENTITY)
        for entry, location, canonical in parts:
            line_blockers = []
            negatives = sum((-later.quantity for later, _, _, key in snapshot if later.id > entry.id
                and key == canonical and later.location_id == entry.location_id and later.quantity < 0), D(0))
            safe = max(D(0), min(entry.quantity - negatives, totals[(canonical, entry.location_id)],
                paper.effective_quantity - used[paper.id]))
            if mismatch: line_blockers.append("当前需求纸品与原收料快照已不同，不能按原物料退补当前需求")
            if canonical in unallocated_debits: line_blockers.append("同物料历史出库缺少明确分仓证据，不能证明本次原仓位余量")
            if cost_key(movement) in {cost_key(item) for item, _ in valuation.errors} or movement.id in valuation.unpriced_movements:
                line_blockers.append("原库存成本尚未核实，请先核价后操作")
            balance = valuation.balances.get(cost_key(movement))
            if not balance or balance.quantity <= 0 or cost_key(movement) in valuation.unpriced_pools:
                line_blockers.append("当前物料成本待核实或计价库存不足")
            if safe <= 0: line_blockers.append("原仓位后续已发生扣减，暂无可证明仍属本次收料的库存")
            if line_blockers: safe = D(0)
            price = balance.amount / balance.quantity if balance and balance.quantity > 0 and not line_blockers else None
            public = {"receipt_line_id": paper.id, "movement_id": movement.id, "location_id": location.id,
                "location_label": positions.label(location), "receipt_no": receipt.delivery_note_no,
                "request_line_id": source.request_line_id,
                **{key: immutable.get(key, "") for key in IDENTITY}, "currency": movement.currency,
                "received_quantity": number(paper.effective_quantity), "safe_quantity": number(safe),
                "inventory_unit_price": str(price.quantize(D("0.000001"), rounding=ROUND_HALF_UP)) if price is not None else None,
                "inventory_amount": number(safe * price) if price is not None else None, "blockers": line_blockers}
            options.append(public)
            evidence.append({**public, "position_id": entry.id, "receipt_revision": receipt.revision,
                "position_revision": max((later.id for later, _, _, key in snapshot if key == canonical and later.location_id == location.id), default=0),
                "immutable": immutable})
    if not options: blockers.append("暂无带原始明确收料、仓位证据的可操作库存；共享库存余额不等于本单库存")
    usable = eligible(db, row) and any(D(option["safe_quantity"]) > 0 for option in options)
    fingerprint = hashlib.sha256(special.pack({"source": summary(row), "current_version_id": row.current_version_id,
        "evidence": evidence}).encode()).hexdigest()
    return {"source_request": {**summary(row), "kind": row.kind,
            "supplier_name": special.portal.fixed_supplier(db, row.factory_id).supplier_name},
        "source_fingerprint": fingerprint, "can_return": usable, "can_replenish": usable,
        "blockers": list(dict.fromkeys(blockers)), "lines": options, "replacement": replacement_out(db, row)}


def _save(db, user, payload, row, digest, response, **data):
    event = special.core._audit(db, user, row.factory_id, EVENT, "carton_special_request", row.id,
        {"fingerprint": digest, "request_id": payload.request_id, "response": response, **data})
    event.id = special.replay_id(user, payload)
    db.commit()
    return response


def submit(db, user, identifier, payload, *, refresh_actor):
    try:
        special.locked_actor(db, user, payload.factory_id)
        user = refresh_actor()
        row = authorize(db, user, payload.factory_id, identifier)
        digest, saved = special.replay(db, user, payload, "STOCK_ACTION", identifier)
        if saved: return saved
        special.require_revision(row, payload)
        view = _preview(db, row)
        if view["source_fingerprint"] != payload.source_fingerprint:
            raise HTTPException(409, "原收料、库存或成本已变化，请刷新来源后重新核实；本次未扣减库存")
        if not view["can_return" if payload.action == "RETURN" else "can_replenish"]:
            raise HTTPException(409, "；".join(view["blockers"]) or "暂无有来源证据的可操作库存")
        options = {(line["receipt_line_id"], line["movement_id"], line["location_id"]): line for line in view["lines"]}
        chosen = []
        receipt_totals = defaultdict(D)
        for item in payload.lines:
            option = options.get((item.receipt_line_id, item.movement_id, item.location_id))
            if not option or item.quantity > D(option["safe_quantity"]):
                raise HTTPException(409, "所选原收料或仓位的可证明库存不足，请刷新核实")
            receipt_totals[item.receipt_line_id] += item.quantity
            receipt_line = db.get(CartonReceiptLine, item.receipt_line_id)
            if receipt_totals[item.receipt_line_id] > receipt_line.effective_quantity:
                raise HTTPException(409, "本次退补数量超过原收料有效数量")
            chosen.append((item, option))
        child = None
        if payload.action == "REPLENISH":
            child = SpecialRequest(id=special.uid("CSR-"), factory_id=row.factory_id, supplier_id=row.supplier_id,
                request_no="SP-B-" + special.uid("")[:16].upper(), kind=row.kind, title=row.title,
                requester_name=row.requester_name, workshop_id=row.workshop_id, customer_code=row.customer_code,
                customer_name=row.customer_name, purpose=f"原单 {row.request_no} 补单：{payload.reason}",
                required_date=payload.required_date.isoformat(), status="SENT", revision=1, current_version_id="", quote_version_id="",
                pricing_kind="FREE" if payload.responsibility == "SUPPLIER" else "PENDING_QUOTE", promised_date="",
                created_by=user.id, created_at=special.core.now_text(), updated_at=special.core.now_text(), origin=ORIGIN)
            db.add(child); db.flush()
        from app.services import carton_supplier_settlement as settlement
        from app.services.carton_supplier_evidence_guard import ensure_evidence_open
        timestamp = special.core.now_text()
        ensure_evidence_open(db, row.factory_id, row.supplier_id, timestamp[:10])
        allocations, movement_ids = [], []
        for index, (item, option) in enumerate(chosen, 1):
            original = db.get(CartonInventoryMovement, item.movement_id)
            special.core._ensure_period_open(db, row.factory_id, original.customer_code, timestamp)
            source = db.scalar(select(SpecialShipmentLine).join(SpecialReceiptLink,
                SpecialReceiptLink.shipment_line_id == SpecialShipmentLine.id).where(SpecialReceiptLink.receipt_line_id == item.receipt_line_id))
            frozen = json.loads(source.snapshot_json)
            child_line = None
            if child:
                child_line = SpecialLine(id=special.uid("CSL-"), factory_id=row.factory_id, request_id=child.id, line_no=index,
                    **{key: frozen[key] for key in IDENTITY}, quantity=item.quantity, unit_price=D(0), mark_mode="PENDING")
                db.add(child_line); db.flush()
            movement = CartonInventoryMovement(**{key: getattr(original, key) for key in (
                "factory_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "currency")},
                id=special.uid("CIM-"), movement_type="OUTBOUND", quantity=-item.quantity, unit_price=D(0), location=option["location_label"],
                document_no=child.request_no if child else "RET-" + row.request_no,
                source_type="SPECIAL_REPLENISHMENT" if child else "SPECIAL_RETURN", source_id=child.id if child else row.id,
                source_line_id=child_line.id if child_line else item.receipt_line_id, reversal_of_movement_id=None,
                reason=payload.reason, issue_kind="OTHER" if child else "RETURN", workshop_id="", workshop_name="",
                actor_user_id=user.id, actor_name=user.display_name, occurred_at=timestamp)
            if not child:
                movement.source_line_id = movement.id  # Every partial/bin allocation is a distinct immutable debit.
            movement.unit_price = special.core._issue_cost_price(db, movement)
            part = {**item.model_dump(mode="json"), "debit_movement_id": movement.id,
                "supplier_id": row.supplier_id, "child_line_id": child_line.id if child_line else None}
            # Exact supplier evidence exists before the generic return collaboration resolver.
            special.core._audit(db, user, row.factory_id, "SPECIAL_STOCK_SOURCE_LINKED", "carton_inventory_movement", movement.id, part)
            db.flush()
            settlement.movement_guard(db, movement, return_date=payload.return_date.isoformat() if payload.return_date else None)
            positions.post(db, movement, location_id=item.location_id)
            special.core._audit(db, user, row.factory_id, "INVENTORY_MOVEMENT_CREATED", "carton_inventory_movement", movement.id,
                {"quantity": str(movement.quantity), "movement_type": "OUTBOUND"})
            if not child:
                from app.services import carton_return_dates
                day = carton_return_dates.require_date(payload.return_date.isoformat())
                carton_return_dates.record(db, user, movement, day, reason=payload.reason)
                from app.services.carton_return_collaboration import open_return
                open_return(db, user, movement)
            db.flush()
            allocations.append(part); movement_ids.append(movement.id)
        if child:
            special.version(db, user, child, "SEND", execution=True, reason=payload.reason)
            special.notify(db, child, "SENT", audience="SUPPLIER")
        special.version(db, user, row, "STOCK_REPLENISHED" if child else "STOCK_RETURNED", reason=payload.reason)
        response = {"action": payload.action, "movement_ids": movement_ids, "source_request": summary(row),
            "replenishment_request": summary(child) if child else None}
        return _save(db, user, payload, row, digest, response, parent_request_id=row.id, parent_request_no=row.request_no,
            child_request_id=child.id if child else None, responsibility=payload.responsibility,
            action=payload.action, allocations=allocations)
    except Exception:
        db.rollback()
        raise


def undo(db, user, identifier, payload, *, refresh_actor):
    try:
        special.locked_actor(db, user, payload.factory_id)
        user = refresh_actor()
        row = authorize(db, user, payload.factory_id, identifier)
        digest, saved = special.replay(db, user, payload, "STOCK_UNDO", identifier)
        if saved: return saved
        special.require_revision(row, payload)
        data = replacement(db, row)
        blockers = undo_blockers(db, row, data)
        if blockers: raise HTTPException(409, "；".join(blockers))
        from app.services.carton_supplier_evidence_guard import ensure_evidence_open
        ensure_evidence_open(db, row.factory_id, row.supplier_id, row.created_at[:10])
        ensure_evidence_open(db, row.factory_id, row.supplier_id, special.core.now_text()[:10])
        reversals = []
        for part in data["allocations"]:
            original = db.get(CartonInventoryMovement, part["debit_movement_id"])
            if not original or original.source_type != "SPECIAL_REPLENISHMENT" or original.source_id != row.id:
                raise HTTPException(409, "补单出库来源缺失，不能自动撤销")
            for at in (original.occurred_at, special.core.now_text()):
                special.core._ensure_period_open(db, row.factory_id, original.customer_code, at)
            reversal = CartonInventoryMovement(**{key: getattr(original, key) for key in (
                "factory_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "currency", "unit_price", "location")},
                id=special.uid("CIM-"), movement_type="REVERSAL", quantity=-original.quantity,
                document_no="REV-" + row.request_no, source_type="REVERSAL", source_id=original.id,
                source_line_id=original.id, reversal_of_movement_id=original.id, reason=payload.reason,
                issue_kind="OTHER", workshop_id="", workshop_name="", actor_user_id=user.id, actor_name=user.display_name,
                occurred_at=special.core.now_text())
            positions.post(db, reversal, reverse=original)
            special.core._audit(db, user, row.factory_id, "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id,
                {"reversal_id": reversal.id, "reason": payload.reason})
            reversals.append(reversal.id)
        row.status = "CANCELLED"
        special.version(db, user, row, "CANCEL", execution=True, reason=payload.reason)
        special.notify(db, row, "CANCEL", audience="SUPPLIER")
        response = {"action": "UNDO", "movement_ids": reversals, "source_request": summary(row), "replenishment_request": None}
        event = special.core._audit(db, user, row.factory_id, "SPECIAL_STOCK_UNDONE", "carton_special_request", row.id,
            {"fingerprint": digest, "request_id": payload.request_id, "response": response})
        event.id = special.replay_id(user, payload)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def receipt_dependency_guard(db, receipt):
    line_ids = set(db.scalars(select(CartonReceiptLine.id).where(CartonReceiptLine.receipt_id == receipt.id)))
    reversed_ids = set(db.scalars(select(CartonInventoryMovement.reversal_of_movement_id).where(
        CartonInventoryMovement.factory_id == receipt.factory_id, CartonInventoryMovement.reversal_of_movement_id.is_not(None))))
    if any(part["receipt_line_id"] in line_ids and part["debit_movement_id"] not in reversed_ids
            for data in actions(db, receipt.factory_id) for part in data["allocations"]):
        raise HTTPException(409, "原收料已用于有来源的退货或补单，须先核实并撤销关联操作，不能直接冲销原入库")


def receipt_link(db, row, source_line_id, qty):
    data = replacement(db, row)
    if not data:
        if row.origin == ORIGIN: raise HTTPException(409, "补单缺少不可变原出库依据，不能按普通收料处理")
        return None
    part = next((item for item in data["allocations"] if item["child_line_id"] == source_line_id), None)
    if not part: raise HTTPException(409, "补单纸品缺少不可变原出库依据")
    result = {"child_request_id": row.id, "parent_request_id": data["parent_request_id"],
        "responsibility": data["responsibility"], "source_movement_ids": [part["debit_movement_id"]],
        "source_quantity": part["quantity"], "quantity": str(qty), "document_no": row.request_no}
    if data["responsibility"] == "SUPPLIER":
        movement = db.get(CartonInventoryMovement, part["debit_movement_id"])
        valuation = load_valuation(db, row.factory_id)
        if not movement or movement.id in valuation.unpriced_movements or any(cost_key(item) == cost_key(movement) for item, _ in valuation.errors):
            raise HTTPException(409, "原补单出库成本待核实，不能登记免费补货")
        amount = -valuation.amounts[movement.id]
        result.update(inventory_amount=str(amount), inventory_unit_price=str((amount / D(part["quantity"])).quantize(D("0.000001"), rounding=ROUND_HALF_UP)),
            settlement_unit_price="0")
    return result
