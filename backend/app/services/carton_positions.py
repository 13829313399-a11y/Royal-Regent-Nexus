"""Authoritative physical allocations, never a second valuation ledger."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_positions import CartonLocation, CartonPositionEntry
from app.models.carton_procurement import CartonInventoryMovement, CartonAuditEvent
from app.services.carton_inventory_identity import inventory_key, aliases_for, resolve_key
from app.services.carton_ledger_time import ledger_time


def _position_snapshot(db, factory, prospective=()):
    db.flush()
    snapshot = db.execute(select(CartonPositionEntry, CartonInventoryMovement, CartonLocation)
        .join(CartonLocation, (CartonLocation.id == CartonPositionEntry.location_id)
              & (CartonLocation.factory_id == CartonPositionEntry.factory_id))
        .outerjoin(CartonInventoryMovement, (CartonInventoryMovement.id == CartonPositionEntry.movement_id)
                   & (CartonInventoryMovement.factory_id == CartonPositionEntry.factory_id))
        .where(CartonPositionEntry.factory_id == factory).order_by(CartonPositionEntry.id)).all()
    aliases = aliases_for([movement for _, movement, _ in snapshot if movement is not None] + list(prospective))
    # Linked entries have exact immutable provenance. Old transfers have only a
    # key: resolve only when unique, never guess a split of an old merged pool.
    return [(part, movement, location, inventory_key(movement) if movement is not None
             else resolve_key(part.inventory_key, aliases)) for part, movement, location in snapshot]


def unknown_id(factory):
    return "CL-UNKNOWN-" + hashlib.sha256(factory.encode()).hexdigest()[:32]


def position_key(key, location_id):
    return json.dumps([key, location_id], ensure_ascii=False, separators=(",", ":"))


def label(location):
    if location.warehouse in {"默认仓", "待核仓位"}:
        return location.bin_code or location.warehouse
    return f"{location.warehouse}／{location.bin_code}"


def location_out(row):
    return {"id": row.id, "factory_id": row.factory_id, "warehouse": row.warehouse,
            "bin_code": row.bin_code, "label": label(row), "status": row.status, "revision": row.revision}


def locations(db, factory):
    return [location_out(row) for row in db.scalars(select(CartonLocation).where(
        CartonLocation.factory_id == factory).order_by(CartonLocation.warehouse, CartonLocation.bin_code))]


def get_location(db, factory, identifier):
    row = db.get(CartonLocation, identifier)
    if not row or row.factory_id != factory:
        raise HTTPException(422, "仓位不存在或不属于当前工厂")
    return row


def create_location(db, factory, warehouse, bin_code):
    warehouse, bin_code = warehouse.strip().upper(), bin_code.strip().upper()
    if not warehouse or not bin_code or max(len(warehouse), len(bin_code)) > 64:
        raise HTTPException(422, "请填写仓库及仓位，长度均不能超过 64 字")
    row = db.scalar(select(CartonLocation).where(CartonLocation.factory_id == factory,
        CartonLocation.warehouse == warehouse, CartonLocation.bin_code == bin_code))
    if not row:
        row = CartonLocation(id=f"CL-{uuid4().hex}", factory_id=factory, warehouse=warehouse, bin_code=bin_code)
        db.add(row)
        db.flush()
    return row


def unknown_location(db, factory):
    row = db.get(CartonLocation, unknown_id(factory))
    if not row:
        row = CartonLocation(id=unknown_id(factory), factory_id=factory, warehouse="待核仓位", bin_code="")
        db.add(row)
        db.flush()
    return row


def entries(db, factory):
    db.flush()
    return list(db.scalars(select(CartonPositionEntry).where(CartonPositionEntry.factory_id == factory)
                          .order_by(CartonPositionEntry.id)))


def state(db, factory):
    totals, revisions, transfer_revisions = defaultdict(Decimal), {}, {}
    for row, _, _, canonical in _position_snapshot(db, factory):
        key = position_key(canonical, row.location_id)
        totals[key] += row.quantity
        revisions[key] = row.id
        if row.transfer_id:
            transfer_revisions[key] = row.id
    return totals, revisions, transfer_revisions


def seed_unallocated(db, factory):
    """Compatibility for fixture/legacy rows: never infer physical location from old text."""
    db.flush()
    allocated = set(db.scalars(select(CartonPositionEntry.movement_id).where(
        CartonPositionEntry.factory_id == factory, CartonPositionEntry.movement_id.is_not(None))))
    missing = [row for row in db.scalars(select(CartonInventoryMovement).where(
        CartonInventoryMovement.factory_id == factory)) if row.id not in allocated]
    if missing:
        location = unknown_location(db, factory)
        for row in missing:
            db.add(CartonPositionEntry(factory_id=factory, inventory_key=inventory_key(row),
                location_id=location.id, movement_id=row.id, quantity=row.quantity,
                transfer_id="", occurred_at=row.occurred_at))
        db.flush()


def validate_allocations(db, factory, allocations, effective):
    seen, result = set(), []
    for item in allocations:
        identifier = item["location_id"]
        amount = Decimal(str(item["quantity"]))
        location = get_location(db, factory, identifier)
        if location.status != "ACTIVE":
            raise HTTPException(422, "该仓位已停用，请选择有效入库仓位")
        if identifier in seen or amount <= 0 or amount != amount.quantize(Decimal("0.0001")):
            raise HTTPException(422, "分仓数量须大于 0、最多四位小数，且仓位不能重复")
        seen.add(identifier)
        result.append({"location_id": identifier, "quantity": str(amount), "label": label(location)})
    if result and sum((Decimal(item["quantity"]) for item in result), Decimal(0)) != effective:
        raise HTTPException(422, "各仓位分配数量之和必须等于有效入库数量")
    return result


def post(db, movement, *, allocations=None, location_id="", legacy_location="", reverse=None):
    """Call before adding a new main movement. Both ledgers commit together."""
    seed_unallocated(db, movement.factory_id)
    # A new identity must not make an existing legacy transfer ambiguous.
    # Validate its aliases before adding either ledger entry to this transaction.
    _position_snapshot(db, movement.factory_id, prospective=[movement])
    key = inventory_key(movement)
    if reverse is not None:
        parts = list(db.scalars(select(CartonPositionEntry).where(
            CartonPositionEntry.factory_id == movement.factory_id,
            CartonPositionEntry.movement_id == reverse.id)))
        allocations = [{"location_id": part.location_id, "quantity": str(-part.quantity)} for part in parts]
    elif allocations:
        allocations = [{"location_id": a["location_id"], "quantity": str(a["quantity"])} for a in allocations]
    else:
        if not location_id:
            totals, _, _ = state(db, movement.factory_id)
            candidates = [json.loads(k)[1] for k, q in totals.items() if json.loads(k)[0] == key and q > 0]
            if (movement.quantity < 0 or movement.movement_type == "ADJUSTMENT") and len(candidates) > 1:
                raise HTTPException(422, "该库存分布在多个仓位，请选择实际操作仓位")
            if candidates and (movement.quantity < 0 or (movement.movement_type == "ADJUSTMENT" and len(candidates) == 1)):
                location_id = candidates[0]
            elif legacy_location.strip():
                existing = db.scalar(select(CartonLocation).where(CartonLocation.factory_id == movement.factory_id, CartonLocation.warehouse == "默认仓", CartonLocation.bin_code == legacy_location.strip().upper()))
                if not existing:
                    raise HTTPException(422, "仓位尚未建档，请由有权限人员在基础资料中建立后再选择")
                location_id = existing.id
            else:
                location_id = unknown_location(db, movement.factory_id).id
        allocations = [{"location_id": location_id, "quantity": str(movement.quantity)}]
    if sum((Decimal(a["quantity"]) for a in allocations), Decimal(0)) != movement.quantity:
        raise HTTPException(409, "仓位分账数量与库存流水不一致")
    totals, _, _ = state(db, movement.factory_id)
    labels, seen = [], set()
    for part in allocations:
        loc = get_location(db, movement.factory_id, part["location_id"])
        amount = Decimal(part["quantity"])
        if amount > 0 and reverse is None and loc.status != "ACTIVE":
            raise HTTPException(422, "该仓位已停用，不能新增入库")
        pk = position_key(key, loc.id)
        if loc.id in seen or amount * movement.quantity <= 0 or amount != amount.quantize(Decimal("0.0001")):
            raise HTTPException(422, "仓位分配重复或数量为零")
        seen.add(loc.id)
        if totals[pk] + amount < 0:
            raise HTTPException(409, f"{label(loc)} 库存不足；已调走的货请先核对关联调仓，不能扣成负库存")
        labels.append(label(loc))
    # Flush the parent first for the composite movement/factory foreign key.
    movement.location = labels[0] if len(labels) == 1 and len(labels[0]) <= 128 else f"{len(labels)} 个仓位（详见分仓明细）"
    db.add(movement)
    db.flush()
    for part in allocations:
        db.add(CartonPositionEntry(factory_id=movement.factory_id, inventory_key=key,
            location_id=part["location_id"], movement_id=movement.id,
            transfer_id="", quantity=Decimal(part["quantity"]), occurred_at=movement.occurred_at))
    db.flush()


def position_balances(db, factory, customer_code=""):
    from app.schemas.carton_procurement import CartonInventoryBalanceOut
    # One SQL statement supplies quantities, revisions, identity and location metadata.
    # Separate SELECTs could mix two commits under PostgreSQL READ COMMITTED.
    snapshot = _position_snapshot(db, factory)
    totals, revisions, transfers = defaultdict(Decimal), {}, {}
    flows = defaultdict(lambda: defaultdict(Decimal))
    originals = {movement.id: movement for _, movement, _, _ in snapshot if movement is not None}
    latest, location_map, by_id = {}, {}, {}
    for part, movement, location, canonical in snapshot:
        pk = position_key(canonical, part.location_id)
        totals[pk] += part.quantity
        original = movement
        if movement is not None and movement.movement_type == "REVERSAL":
            original = originals.get(movement.reversal_of_movement_id)
            if original is None or original.movement_type == "REVERSAL" or inventory_key(original) != canonical:
                raise HTTPException(409, "库存冲销缺少一致的原始流水，无法生成可靠仓位收发汇总")
        if part.transfer_id:
            field = "transfer_quantity"
        elif original is not None and original.source_type == "HISTORY_INVENTORY":
            field = "opening_quantity"
        elif original is not None and original.movement_type == "INBOUND":
            field = "inbound_quantity"
        elif original is not None and original.movement_type == "OUTBOUND":
            field = "outbound_quantity"
        else:
            field = "adjustment_quantity"
        flows[pk][field] += -part.quantity if field == "outbound_quantity" else part.quantity
        revisions[pk] = part.id
        if part.transfer_id:
            transfers[pk] = part.id
        location_map[location.id] = location
        if movement is not None:
            latest[pk] = movement
            by_id[movement.id] = movement
    rows = sorted(by_id.values(), key=lambda row: (ledger_time(row.occurred_at), row.id))
    latest_identity = {inventory_key(row): row for row in rows}
    identity_inbound = {inventory_key(row): row.occurred_at for row in rows if row.movement_type == "INBOUND"}
    result = []
    for pk, balance in totals.items():
        key, loc_id = json.loads(pk)
        row = latest.get(pk, latest_identity.get(key))
        if not row or (customer_code and row.customer_code != customer_code):
            continue
        loc = location_map[loc_id]
        values = {name: getattr(row, name) for name in ("factory_id", "customer_code", "customer_name",
            "contract_no", "item_no", "order_line_id", "packaging_type", "paper_quality", "specification", "unit")}
        quantities = {field: flows[pk][field] for field in ("inbound_quantity", "outbound_quantity",
            "opening_quantity", "transfer_quantity", "adjustment_quantity")}
        result.append(CartonInventoryBalanceOut(**values, **quantities, balance=balance, latest_location=label(loc),
            latest_movement_id=row.id, latest_document_no=row.document_no, latest_movement_at=row.occurred_at,
            latest_inbound_at=identity_inbound.get(key), location_revision=transfers.get(pk, 0), position_revision=revisions[pk],
            position_key=pk, inventory_key=key, location_id=loc_id, warehouse=loc.warehouse, bin_code=loc.bin_code))
    return result


def transfer(db, payload, user):
    from app.services import carton_procurement as ledger
    ledger._lock_receipt_factory(db, payload.factory_id)
    seed_unallocated(db, payload.factory_id)
    scope = json.dumps([payload.factory_id, user.id, payload.request_id])
    event_id = "CAE-TRANSFER-" + hashlib.sha256(scope.encode()).hexdigest()
    request = payload.model_dump(mode="json")
    request["quantity"] = format(payload.quantity.normalize(), "f")
    fingerprint = json.dumps(request, sort_keys=True)
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous:
        detail = json.loads(previous.detail_json)
        if detail["request"]["fingerprint"] != fingerprint:
            raise HTTPException(409, "本次调仓标识已用于不同内容")
        return detail["request"]["result"]
    balances = position_balances(db, payload.factory_id)
    source = next((row for row in balances if row.position_key == payload.position_key), None)
    if not source or source.position_revision != payload.expected_position_revision:
        raise HTTPException(409, "来源仓位库存已变化，请刷新后核对")
    target = get_location(db, payload.factory_id, payload.location_id)
    if target.status != "ACTIVE":
        raise HTTPException(422, "目标仓位已停用")
    if target.id == source.location_id or payload.quantity <= 0 or payload.quantity > source.balance:
        raise HTTPException(422, "请选择不同目标仓位，调仓数量不能超过来源仓位库存")
    transfer_id = "CTF-" + uuid4().hex
    for loc_id, qty in ((source.location_id, -payload.quantity), (target.id, payload.quantity)):
        db.add(CartonPositionEntry(factory_id=payload.factory_id, inventory_key=source.inventory_key,
            location_id=loc_id, movement_id=None, transfer_id=transfer_id, quantity=qty, occurred_at=ledger.now_text()))
    result = {"id": transfer_id, "quantity": str(payload.quantity), "from_location": source.latest_location,
              "to_location": label(target)}
    event = ledger._audit(db, user, payload.factory_id, "INVENTORY_LOCATION_CHANGED", "carton_inventory_location",
        "INV-" + hashlib.sha256(source.inventory_key.encode()).hexdigest(), {**result, "reference_movement_id": source.latest_movement_id,
        "inventory_key": source.inventory_key, "contract_no": source.contract_no,
        "item_no": source.item_no, "unit": source.unit, "customer_name": source.customer_name,
        "reason": payload.note or "分仓调拨", "request": {"fingerprint": fingerprint, "result": result}})
    event.id = event_id
    db.commit()
    return result
