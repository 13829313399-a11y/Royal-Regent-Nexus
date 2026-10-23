"""Atomic, preview-bound cancellation of one immutable opening import batch."""
import json
from collections import defaultdict
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonClosing, CartonInventoryMovement
from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from app.services import carton_positions as positions, carton_procurement as ledger
from app.services.carton_inventory_identity import aliases_for, inventory_key
from app.services.carton_inventory_valuation import cost_key, load_valuation
from app.services.carton_opening_preview import digest, encoded

REVERSED_EVENT = "HISTORY_INVENTORY_BATCH_REVERSED"


class OpeningBatchReversal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: UUID
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


def retired_openings(events):
    return {identifier for event in events if event.event_type == REVERSED_EVENT
            for identifier in json.loads(event.detail_json).get("original_ids", [])}


def _state(db, factory):
    rows = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)))
    events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory)
                            .order_by(CartonAuditEvent.sequence)))
    return rows, events


def _originals(rows, batch_id):
    originals = [row for row in rows if row.source_type == "HISTORY_INVENTORY" and row.source_id == batch_id]
    if not originals:
        raise HTTPException(404, "本厂区未找到该期初导入批次")
    return originals


def _header(batch_id, originals, events, reversed_ids):
    imported = [event for event in events if event.event_type == "HISTORY_INVENTORY_IMPORTED" and event.entity_id == batch_id]
    evidence = json.loads(imported[-1].detail_json) if imported else {}
    reversed_count = sum(row.id in reversed_ids for row in originals)
    cancelled = any(event.event_type == REVERSED_EVENT and event.entity_id == batch_id for event in events)
    return {
        "batch_id": batch_id, "filename": evidence.get("filename") or "历史期初导入（原文件名未记录）",
        "imported_at": imported[-1].created_at if imported else "",
        "actor_name": imported[-1].actor_name if imported else originals[0].actor_name,
        "row_count": len(originals), "reversed_count": reversed_count,
        "status": "REVERSED" if cancelled else "PARTIAL" if reversed_count else "ACTIVE",
        "date_from": min(row.occurred_at[:10] for row in originals),
        "date_to": max(row.occurred_at[:10] for row in originals),
    }


def list_batches(db, factory_id, limit=20, offset=0):
    factory = ledger.require_carton_factory(factory_id)
    rows, events = _state(db, factory)
    groups = defaultdict(list)
    for row in rows:
        if row.source_type == "HISTORY_INVENTORY" and row.source_id:
            groups[row.source_id].append(row)
    reversed_ids = {row.reversal_of_movement_id for row in rows if row.reversal_of_movement_id}
    headers = [_header(batch_id, group, events, reversed_ids) for batch_id, group in groups.items()]
    headers.sort(key=lambda row: (row["imported_at"], row["batch_id"]), reverse=True)
    return {"factory_id": factory, "total": len(headers), "items": headers[offset:offset + limit]}


def _preview(db, factory, batch_id):
    rows, events = _state(db, factory)
    originals = _originals(rows, batch_id)
    original_ids = {row.id for row in originals}
    reversed_ids = {row.reversal_of_movement_id for row in rows if row.reversal_of_movement_id}
    header = _header(batch_id, originals, events, reversed_ids)
    errors = []
    evidenced = {item.get("movement_id") for event in events
                 if event.event_type == "HISTORY_INVENTORY_IMPORTED" and event.entity_id == batch_id
                 for item in json.loads(event.detail_json).get("rows", [])}
    if not original_ids.issubset(evidenced):
        errors.append("本批缺少完整的原文件逐行入账依据，暂不能整批撤销，请先核对旧版导入记录")
    if header["status"] == "REVERSED":
        errors.append("本批已整批撤销，请查看原撤销记录；修正文件后可重新预览导入")
    elif header["reversed_count"]:
        errors.append("本批已有逐笔冲销记录，请先核对原流水；不能混合整批撤销或再次入账")
    if any(row.movement_type != "ADJUSTMENT" or row.quantity <= 0 for row in originals):
        errors.append("本批包含非正数期初调整记录，请先核对历史来源")

    keys = {inventory_key(row) for row in originals}
    retired = retired_openings(events)
    related = [row for row in rows if inventory_key(row) in keys and row.id not in original_ids
               and row.id not in retired and row.reversal_of_movement_id not in retired]
    if related:
        errors.append(f"相关纸品已有 {len(related)} 笔其他收发、盘点或冲销记录，请先核对后续业务；本批不能直接整批撤销")

    closings = list(db.scalars(select(CartonClosing).where(CartonClosing.factory_id == factory)))
    locked = sorted({closing.period for row in originals for closing in closings
                     if closing.customer_code == row.customer_code and closing.status == "LOCKED"
                     and closing.period >= row.occurred_at[:7]})
    if locked:
        errors.append(f"原期初月份或后续月份已锁账（{'、'.join(locked)}），请先由主管按倒序解锁核实")
    counts = list(db.execute(select(CartonStocktake, CartonStocktakeLine)
        .join(CartonStocktakeLine, (CartonStocktake.id == CartonStocktakeLine.stocktake_id)
              & (CartonStocktake.factory_id == CartonStocktakeLine.factory_id))
        .where(CartonStocktake.factory_id == factory, CartonStocktake.status.in_(["DRAFT", "SUBMITTED"]))))
    aliases = aliases_for(rows)
    for document, line in counts:
        raw = line.inventory_key
        if raw.startswith("["):
            raw = json.loads(raw)[0]
        if line.reference_movement_id in original_ids or aliases.get(raw, set()) & keys:
            errors.append(f"相关纸品正在盘点（{document.id}），请先完成或取消盘点")
            break

    snapshot = positions._position_snapshot(db, factory)
    original_parts = defaultdict(list)
    for part, movement, location, key in snapshot:
        if movement and movement.id in original_ids:
            original_parts[movement.id].append(part)
    if any(not original_parts[row.id] or sum((part.quantity for part in original_parts[row.id]), Decimal(0)) != row.quantity
           for row in originals):
        errors.append("期初流水与仓位分账缺少完整对应，请先核实原始库存")
    if any(part.transfer_id and key in keys for part, _, _, key in snapshot):
        errors.append("相关纸品已有调仓记录，请先核对并处理关联调仓")
    totals_by_position = defaultdict(Decimal)
    needed = defaultdict(Decimal)
    for part, _, _, key in snapshot:
        totals_by_position[(key, part.location_id)] += part.quantity
    for row in originals:
        for part in original_parts[row.id]:
            needed[(inventory_key(row), part.location_id)] += part.quantity
    if any(totals_by_position[key] < quantity for key, quantity in needed.items()):
        errors.append("原仓位库存不足以整批撤销，请先核对后续出库及调仓")
    valuation = load_valuation(db, factory)
    affected_costs = {cost_key(row) for row in originals}
    if any(cost_key(row) in affected_costs for row, _ in valuation.errors):
        errors.append("相关库存金额存在待核算问题，请先核实成本流水")

    totals = defaultdict(Decimal)
    for row in originals:
        totals[row.unit] += row.quantity
    token = digest({
        "version": 1, "factory": factory, "batch": batch_id,
        "movements": sorted((row.id, str(row.quantity), str(row.unit_price), row.currency,
                             row.occurred_at, row.reversal_of_movement_id) for row in rows),
        "events": [(event.id, event.sequence) for event in events],
        "positions": [(part.id, part.location_id, part.movement_id, part.transfer_id, str(part.quantity))
                      for part, _, _, _ in snapshot],
        "closings": sorted((row.id, row.revision, row.status) for row in closings),
        "counts": sorted((document.id, document.revision, document.status, line.id) for document, line in counts),
    })
    result = {**header, "factory_id": factory, "source_fingerprint": token, "errors": list(dict.fromkeys(errors)),
        "totals": [{"unit": unit, "quantity": quantity} for unit, quantity in sorted(totals.items())],
        "rows": [{"movement_id": row.id, "customer_name": row.customer_name, "contract_no": row.contract_no,
                  "item_no": row.item_no, "packaging_type": row.packaging_type, "paper_quality": row.paper_quality,
                  "specification": row.specification, "quantity": row.quantity, "unit": row.unit,
                  "unit_price": row.unit_price, "location": row.location, "occurred_at": row.occurred_at}
                 for row in sorted(originals, key=lambda row: (row.occurred_at, row.id))]}
    return json.loads(encoded(result)), originals


def preview_batch_reversal(db, factory_id, batch_id):
    factory = ledger.require_carton_factory(factory_id)
    ledger._lock_receipt_factory(db, factory)
    return _preview(db, factory, batch_id)[0]


def reverse_batch(db, batch_id, payload, user):
    factory = ledger.require_carton_factory(payload.factory_id)
    try:
        ledger._lock_receipt_factory(db, factory)
        request_key = "CAE-REQ-" + digest(["opening-batch-reversal", factory, user.id, str(payload.request_id)])
        request_fingerprint = digest([batch_id, payload.model_dump(mode="json")])
        previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == request_key))
        if previous:
            recorded = json.loads(previous.detail_json).get("request", {})
            if recorded.get("fingerprint") != request_fingerprint:
                raise HTTPException(409, "本次提交标识已用于不同的期初撤销，请核对原操作结果")
            return {**recorded["result"], "duplicate": True}
        preview, originals = _preview(db, factory, batch_id)
        if preview["source_fingerprint"] != payload.expected_fingerprint:
            raise HTTPException(409, "期初批次、库存、盘点或锁账状态已变化，请重新预览撤销")
        if preview["errors"]:
            raise HTTPException(409, "；".join(preview["errors"]))
        reversal_ids = []
        for original in originals:
            ledger._ensure_period_open(db, factory, original.customer_code, original.occurred_at)
            identifier = "CIM-" + uuid4().hex
            reversal = CartonInventoryMovement(
                id=identifier, factory_id=factory, order_line_id=original.order_line_id,
                **{name: getattr(original, name) for name in (
                    "customer_code", "customer_name", "contract_no", "item_no", "packaging_type",
                    "paper_quality", "specification", "unit", "unit_price", "currency", "location")},
                movement_type="REVERSAL", quantity=-original.quantity,
                document_no="REV-" + original.document_no[:124], source_type="REVERSAL",
                source_id=original.id, source_line_id=identifier, reversal_of_movement_id=original.id,
                reason=payload.reason, actor_user_id=user.id, actor_name=user.display_name,
                occurred_at=original.occurred_at,
            )
            positions.post(db, reversal, reverse=original)
            ledger._audit(db, user, factory, "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id,
                          {"reversal_id": identifier, "reason": payload.reason, "opening_batch_id": batch_id})
            reversal_ids.append(identifier)
        db.flush()
        costs = {cost_key(row) for row in originals}
        if any(cost_key(row) in costs for row, _ in load_valuation(db, factory).errors):
            raise HTTPException(409, "整批撤销后库存金额无法对平，本批未作更改，请核对成本流水")
        result = {"factory_id": factory, "batch_id": batch_id, "reversed_count": len(originals),
                  "status": "REVERSED", "duplicate": False, "movement_ids": reversal_ids}
        event = ledger._audit(db, user, factory, REVERSED_EVENT, "carton_inventory_import", batch_id,
            {"filename": preview["filename"], "reason": payload.reason, "original_ids": [row.id for row in originals],
             "reversed_count": len(originals), "request": {"fingerprint": request_fingerprint, "result": result}})
        event.id = request_key
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
