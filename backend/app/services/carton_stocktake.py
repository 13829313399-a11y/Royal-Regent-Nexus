"""Optimistic cutoff counts; review posts fixed differences, never overwrites stock."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonSupplier
from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from app.schemas.carton_stocktake import StocktakeAction, StocktakeCreate
from app.services import carton_procurement as ledger
from app.services import carton_positions as positions
from app.services.carton_inventory_valuation import cost_key, load_valuation
from app.services.carton_inventory_identity import aliases_for, resolve_key


def _fail(message: str, status: int = 409):
    raise HTTPException(status_code=status, detail=message)


def _lock(db: Session, factory: str):
    ledger.require_carton_factory(factory)
    ledger.lock_transaction(db, "carton-inventory", factory)
    result = db.execute(update(CartonSupplier).where(CartonSupplier.factory_id == factory)
                        .values(updated_at=CartonSupplier.updated_at))
    if not result.rowcount:
        _fail("当前厂区尚未初始化库存服务")
    db.expire_all()


def _get(db: Session, factory: str, identifier: str):
    doc = db.get(CartonStocktake, identifier)
    if not doc or doc.factory_id != factory:
        _fail("盘点单不存在", 404)
    lines = list(db.scalars(select(CartonStocktakeLine).where(
        CartonStocktakeLine.stocktake_id == doc.id,
        CartonStocktakeLine.factory_id == factory).order_by(CartonStocktakeLine.id)))
    return doc, lines


def _legacy_state(db: Session, doc, lines):
    keys = {line.inventory_key for line in lines}
    all_rows = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == doc.factory_id)))
    aliases = aliases_for(all_rows)
    canonical = {key: resolve_key(key, aliases) for key in keys}
    rows = [row for row in all_rows if ledger._movement_key(row) in set(canonical.values())]
    locations = {}
    for row in sorted(rows, key=lambda row: (row.occurred_at, row.id)):
        locations[ledger._movement_key(row)] = (row.location, 0)
    locations.update(ledger._inventory_locations(db, doc.factory_id))
    quantities = {key: sum((row.quantity for row in rows if ledger._movement_key(row) == canonical[key]), Decimal(0)) for key in keys}
    locations = {key: locations.get(canonical[key], ("", 0)) for key in keys}
    # Include every immutable movement, not net quantities: an issue then receipt must invalidate the cutoff.
    data = [doc.factory_id, doc.id, doc.revision,
            sorted((line.id, line.inventory_key) for line in lines),
            sorted(row.id for row in rows), sorted((key, locations.get(key, ("", 0))) for key in keys)]
    token = hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()
    basis = hashlib.sha256(json.dumps(data[:2] + data[3:], ensure_ascii=False).encode()).hexdigest()
    return quantities, locations, token, rows, basis


def _base_key(key):
    return json.loads(key)[0] if key.startswith("[") else key


def _canonical_count_key(line, aliases):
    raw = line.inventory_key
    if raw.startswith("["):
        base, location = json.loads(raw)
        return positions.position_key(resolve_key(base, aliases), location)
    return resolve_key(raw, aliases)


def _state(db, doc, lines):
    if any(not line.inventory_key.startswith("[") for line in lines):
        return _legacy_state(db, doc, lines)
    all_rows = list(db.scalars(select(CartonInventoryMovement).where(
        CartonInventoryMovement.factory_id == doc.factory_id)))
    aliases = aliases_for(all_rows)
    canonical = {line.inventory_key: _canonical_count_key(line, aliases) for line in lines}
    keys = set(canonical)
    bases = {_base_key(key) for key in canonical.values()}
    rows = [row for row in all_rows if ledger._movement_key(row) in bases]
    totals, revisions, transfers = positions.state(db, doc.factory_id)
    location_map = {row.position_key: (row.latest_location, row.location_revision)
                    for row in positions.position_balances(db, doc.factory_id)}
    quantities = {key: totals.get(canonical[key], Decimal(0)) for key in keys}
    # Preserve old persisted keys in cutoff tokens and line responses.
    location_map = {key: location_map.get(canonical[key], ("", 0)) for key in keys}
    data = [doc.factory_id, doc.id, doc.revision,
            sorted((line.id, line.inventory_key) for line in lines), sorted(row.id for row in rows),
            sorted((key, revisions.get(canonical[key], 0), location_map.get(key, ("", 0))) for key in keys)]
    token = hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()
    basis = hashlib.sha256(json.dumps(data[:2] + data[3:], ensure_ascii=False).encode()).hexdigest()
    return quantities, location_map, token, rows, basis


def _header(doc):
    return {name: getattr(doc, name) for name in (
        "id", "factory_id", "status", "revision", "created_by", "created_by_name", "created_at",
        "submitted_by", "submitted_by_name", "submitted_at", "reviewed_by", "reviewed_by_name", "reviewed_at", "note")}


def list_stocktakes(db: Session, factory: str, limit=100, offset=0, status=""):
    query = select(CartonStocktake).where(CartonStocktake.factory_id == factory)
    if status:
        query = query.where(CartonStocktake.status == status)
    return [_header(doc) for doc in db.scalars(query.order_by(CartonStocktake.created_at.desc(), CartonStocktake.id)
        .limit(limit).offset(offset))]


def stocktake_detail(db: Session, factory: str, identifier: str):
    doc, lines = _get(db, factory, identifier)
    reconciliation_error = ""
    try:
        quantities, locations, token, _, basis = _state(db, doc, lines)
    except HTTPException as error:
        if not str(error.detail).startswith("旧库存身份"):
            raise
        reconciliation_error = str(error.detail)
        quantities, locations, token, basis = {line.inventory_key: None for line in lines}, {}, "", "unresolved"
    return {**_header(doc), "ledger_token": token, "basis_changed": basis != doc.basis_token,
            "reconciliation_error": reconciliation_error,
            "cutoff_at": ledger.now_text(), "lines": [
        {"id": line.id, **json.loads(line.snapshot_json),
         "initial_quantity": line.initial_quantity, "count_book_quantity": line.count_book_quantity,
         "current_quantity": quantities[line.inventory_key], "actual_quantity": line.actual_quantity,
         "difference": line.difference, "reason": line.reason, "movement_id": line.movement_id,
         "location_changed": locations.get(line.inventory_key, ("", 0)) !=
             (json.loads(line.snapshot_json)["latest_location"], line.location_revision)}
        for line in lines], "events": [
            {"action": event.event_type, "actor": event.actor_name, "at": event.created_at,
             "detail": json.loads(event.detail_json)}
            for event in db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.factory_id == factory, CartonAuditEvent.entity_id == doc.id)
                .order_by(CartonAuditEvent.sequence))]}


def create_stocktake(db: Session, payload: StocktakeCreate, user):
    _lock(db, payload.factory_id)
    positions.seed_unallocated(db, payload.factory_id)
    all_balances = positions.position_balances(db, payload.factory_id)
    balances = {row.position_key: row for row in all_balances}
    refs = payload.position_keys
    if not refs:
        refs = []
        for ref in payload.reference_movement_ids:
            matches = [row.position_key for row in all_balances if row.latest_movement_id == ref]
            if len(matches) != 1:
                _fail("请按具体仓位重新选择盘点库存", 422)
            refs.append(matches[0])
    if not refs or len(set(refs)) != len(refs):
        _fail("请选择库存仓位，不能重复", 422)
    if any(ref not in balances for ref in refs):
        _fail("仓位库存已更新或不属于当前厂区，请刷新后重新选择")
    movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == payload.factory_id)))
    keys = set(refs)
    active = db.scalars(select(CartonStocktakeLine).join(CartonStocktake,
        CartonStocktake.id == CartonStocktakeLine.stocktake_id).where(
            CartonStocktake.factory_id == payload.factory_id, CartonStocktake.status.in_(["DRAFT", "SUBMITTED"])))
    aliases = aliases_for(movements)
    for line in active:
        active_key = _canonical_count_key(line, aliases)
        if active_key in keys or (not active_key.startswith("[") and active_key in {_base_key(key) for key in keys}):
            _fail("所选库存已有进行中的盘点单，请先完成或取消原单")
    for key in keys:
        if len({cost_key(row) for row in movements if ledger._movement_key(row) == _base_key(key)}) != 1:
            _fail("所选库存包含不同单位或币种，需先核对计价归属再盘点")
    doc = CartonStocktake(id=f"PD-{uuid4().hex}", factory_id=payload.factory_id, status="DRAFT", revision=1,
                         created_by=user.id, created_by_name=user.display_name, created_at=ledger.now_text())
    db.add(doc)
    db.flush()
    for ref in refs:
        balance = balances[ref]
        if balance.balance < 0:
            _fail("库存账面异常，请先核对")
        snapshot = balance.model_dump(mode="json")
        db.add(CartonStocktakeLine(id=f"PDL-{uuid4().hex}", stocktake_id=doc.id, factory_id=doc.factory_id,
            inventory_key=ref, reference_movement_id=balance.latest_movement_id,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False), initial_quantity=balance.balance,
            count_book_quantity=balance.balance, location_revision=balance.location_revision))
    ledger._audit(db, user, doc.factory_id, "STOCKTAKE_CREATED", "carton_stocktake", doc.id, {"line_count": len(refs)})
    db.flush()
    _, lines = _get(db, doc.factory_id, doc.id)
    doc.basis_token = _state(db, doc, lines)[4]
    db.commit()
    return stocktake_detail(db, doc.factory_id, doc.id)


def act_stocktake(db: Session, identifier: str, payload: StocktakeAction, user):
    _lock(db, payload.factory_id)
    doc, lines = _get(db, payload.factory_id, identifier)
    if doc.revision != payload.expected_revision:
        _fail("盘点单已更新，请刷新后操作")
    if doc.status in ("POSTED", "CANCELLED"):
        _fail("盘点单已结束，不能重复操作")
    action = payload.action
    if action == "CONFIRM" and not payload.posting_confirmed:
        _fail("请核对盘点结果并确认提交入账", 422)
    if action != "CANCEL":
        quantities, locations, token, rows, basis = _state(db, doc, lines)
    if action != "CANCEL" and any(not line.inventory_key.startswith("[") for line in lines):
        _fail("该盘点单按旧整笔库存建立，请保留原证据并取消后按仓位重新盘点")
    if action == "CONFIRM" and token != payload.ledger_token:
        _fail("库存已变化，请刷新并重新核对盘点差额后确认入账")
    if action in ("SAVE", "SUBMIT") or (action == "CONFIRM" and doc.status == "DRAFT"):
        if doc.status != "DRAFT" or doc.created_by != user.id:
            _fail("只有创建人可以填写草稿盘点单", 403)
        if token != payload.ledger_token:
            _fail("盘点期间发生收发货或调仓，请刷新账面并重新核对实盘数量后提交")
        counts = {count.id: count for count in payload.lines}
        if len(counts) != len(payload.lines) or set(counts) != {line.id for line in lines}:
            _fail("请完整填写本单明细，不能重复或包含其他盘点单明细", 422)
        if action in ("SUBMIT", "CONFIRM") and not payload.cutoff_acknowledged:
            _fail("请确认实盘数量已按页面账面截止时间核对", 422)
        accept_basis = basis == doc.basis_token or payload.cutoff_acknowledged
        for line in lines:
            count = counts[line.id]
            book = quantities[line.inventory_key] if accept_basis else line.count_book_quantity
            diff = None if count.actual_quantity is None else ledger.quantity(count.actual_quantity - book)
            if action in ("SUBMIT", "CONFIRM") and (diff is None or (diff != 0 and not count.reason)):
                _fail("实盘数量不可留空，有差异的明细必须填写原因", 422)
            line.actual_quantity, line.difference, line.reason = count.actual_quantity, diff, count.reason
            line.count_book_quantity = book
            if accept_basis:
                line.location_revision = locations.get(line.inventory_key, ("", 0))[1]
            snapshot = json.loads(line.snapshot_json)
            if accept_basis and line.inventory_key in locations:
                snapshot["latest_location"] = locations[line.inventory_key][0]
                line.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        if action in ("SUBMIT", "CONFIRM"):
            doc.status = "SUBMITTED"
            doc.submitted_by, doc.submitted_by_name, doc.submitted_at = user.id, user.display_name, ledger.now_text()
        if accept_basis:
            doc.basis_token = basis
    if action in ("APPROVE", "CONFIRM"):
        if doc.status != "SUBMITTED":
            _fail("只能复核已提交的盘点单")
        if action == "APPROVE" and user.id in (doc.created_by, doc.submitted_by):
            _fail("盘点创建人或提交人不能复核自己的盘点单，请由另一位主管复核", 403)
        valuation = load_valuation(db, doc.factory_id)
        posting_at = ledger.now_text()
        references = {row.id: row for row in rows}
        for line in lines:
            if locations.get(line.inventory_key, ("", 0)) != (json.loads(line.snapshot_json)["latest_location"], line.location_revision):
                _fail("提交后仓位发生变化，请退回并重新盘点")
            if line.difference is None or quantities[line.inventory_key] + line.difference < 0:
                _fail("盘点差额会导致负库存，请退回核对")
            reference = references[line.reference_movement_id]
            key = cost_key(reference)
            if len({cost_key(row) for row in rows if ledger._movement_key(row) == ledger._movement_key(reference)}) != 1:
                _fail("盘点库存计价归属发生变化，请退回核对")
            if any(cost_key(row) == key for row, _ in valuation.errors):
                _fail("盘点库存存在历史计价异常，请先核对")
            # Validate every line's period, including zero differences, before accepting the document.
            ledger._ensure_period_open(db, doc.factory_id, reference.customer_code, posting_at)
            if line.difference == 0:
                continue
            carrying = valuation.balances.get(key)
            price = ((carrying.amount / carrying.quantity).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                     if carrying and carrying.quantity > 0 else Decimal(0))
            fields = {name: getattr(reference, name) for name in (
                "order_line_id", "customer_code", "customer_name", "contract_no", "item_no",
                "packaging_type", "paper_quality", "specification", "unit", "currency")}
            movement = CartonInventoryMovement(id=f"CIM-{uuid4().hex}", factory_id=doc.factory_id, **fields,
                movement_type="ADJUSTMENT", quantity=line.difference, unit_price=price,
                location=json.loads(line.snapshot_json)["latest_location"], document_no=doc.id,
                source_type="STOCKTAKE", source_id=doc.id, source_line_id=line.id, reason=line.reason,
                actor_user_id=user.id, actor_name=user.display_name, occurred_at=posting_at)
            positions.post(db, movement, location_id=json.loads(line.snapshot_json)["location_id"])
            line.movement_id = movement.id
            ledger._audit(db, user, doc.factory_id, "INVENTORY_MOVEMENT_CREATED", "carton_inventory_movement", movement.id,
                          {"stocktake_id": doc.id, "quantity": line.difference, "movement_type": "ADJUSTMENT"})
        doc.status = "POSTED"
        doc.reviewed_by, doc.reviewed_by_name, doc.reviewed_at = user.id, user.display_name, posting_at
    elif action in ("RETURN", "CANCEL"):
        if action == "RETURN" and doc.status != "SUBMITTED":
            _fail("只能退回待复核的盘点单")
        if not payload.reason:
            _fail("请填写退回或取消原因", 422)
        doc.status = "DRAFT" if action == "RETURN" else "CANCELLED"
        doc.note = payload.reason
        if action == "RETURN":
            doc.submitted_by = doc.submitted_by_name = doc.submitted_at = ""
    doc.revision += 1
    evidence = {"reason": payload.reason, "revision": doc.revision, "status": doc.status}
    if action in ("SUBMIT", "CONFIRM"):
        evidence.update({"posting_confirmed": payload.posting_confirmed, "cutoff_at": doc.submitted_at, "lines": [
            {"id": line.id, "book_quantity": str(line.count_book_quantity),
             "actual_quantity": str(line.actual_quantity), "difference": str(line.difference),
             "reason": line.reason, "location": json.loads(line.snapshot_json)["latest_location"],
             "location_revision": line.location_revision} for line in lines]})
    ledger._audit(db, user, doc.factory_id, f"STOCKTAKE_{action}", "carton_stocktake", doc.id,
                  evidence)
    db.commit()
    return stocktake_detail(db, doc.factory_id, doc.id)
