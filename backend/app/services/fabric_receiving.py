"""Atomic warehouse confirmation. Procurement references never post inventory."""
from decimal import Decimal
from uuid import uuid4, uuid5
import json

from fastapi import HTTPException
from sqlalchemy import inspect, select, literal, or_

from app.core.time import business_now
from app.models.fabric_procurement import FabricProcurementLine, FabricProcurementEvidence, FabricProcurementImport
from app.models.fabric_receiving import FabricReceipt, FabricStockBatch, FabricInventoryMovement
from app.models.fabric_master import FabricChaseResolution
from app.services import fabric_procurement as source
from app.services.fabric_procurement_parser import number, decimal_text, digest, dump

MODELS = (FabricReceipt, FabricStockBatch, FabricInventoryMovement)


def schema_ready(db):
    inspector = inspect(db.get_bind())
    return {model.__tablename__ for model in MODELS} <= set(inspector.get_table_names()) and "baseline_known" in {c["name"] for c in inspector.get_columns("fabric_receipts")}


def ensure_schema(db):
    source.ensure_schema(db)
    if not schema_ready(db):
        raise HTTPException(503, "布料仓实际收料数据库尚未升级，请先备份并执行迁移 20261008_0143")


def valid_reference(value):
    amount = number(value)
    return amount if amount is not None and 0 <= amount < Decimal("1e12") and amount.as_tuple().exponent >= -6 else None


def receipt_context(db):
    totals = {}
    # Derive the starting chase reference from active import evidence, never stock.
    # Later spreadsheet receipts may include our own postings: don't subtract twice.
    events = db.execute(select(FabricProcurementEvidence, FabricProcurementImport).join(FabricProcurementImport,
        FabricProcurementImport.id == FabricProcurementEvidence.import_id).where(FabricProcurementEvidence.factory_id == source.FACTORY))
    imports = []
    for event, batch in events:
        metadata = json.loads(batch.result_json)
        if not metadata.get("withdrawal"):
            sequence = metadata.get("sequence", 0)
            order = (1, sequence) if sequence else (0, batch.occurred_at)
            imports.append((order, batch.id, event.id, event.line_id, json.loads(event.after_json)))
    for order, batch_id, event_id, line_id, facts in sorted(imports, key=lambda item: item[:3]):
        reported = valid_reference(facts.get("reported_received_quantity"))
        if reported is None:
            continue
        item = totals.setdefault(line_id, {"receipt_count": 0, "warehouse_received_quantity": Decimal(0),
            "prior_received_quantity": reported, "source_facts": facts, "reference_order": order,
            "chase_reference": {"quantity": decimal_text(reported), "import_id": batch_id, "evidence_id": event_id}})
        if item["reference_order"] == order and (reported != item["prior_received_quantity"] or
            any(facts.get(key) != item["source_facts"].get(key) for key in ("material_code", "material_name", "unit", "supplier"))):
            item["reference_review_required"] = True
    inspector = inspect(db.get_bind())
    if "fabric_receipts" not in inspector.get_table_names():
        return totals
    known_column = FabricReceipt.baseline_known if "baseline_known" in {c["name"] for c in inspector.get_columns("fabric_receipts")} else literal(True).label("baseline_known")
    # Existing 0135 receipts remain readable until the explicit additive upgrade.
    receipt_rows = db.execute(select(FabricReceipt.id, FabricReceipt.source_line_id, FabricReceipt.prior_received_quantity,
        FabricReceipt.source_json, FabricReceipt.payload_json, FabricReceipt.quantity, known_column).where(FabricReceipt.factory_id == source.FACTORY).order_by(FabricReceipt.occurred_at, FabricReceipt.id))
    for receipt in receipt_rows:
        item = totals.setdefault(receipt.source_line_id, {"receipt_count": 0, "warehouse_received_quantity": Decimal(0)})
        if not item["receipt_count"]:
            item.update(prior_received_quantity=Decimal(receipt.prior_received_quantity) if receipt.baseline_known else None, source_facts=json.loads(receipt.source_json),
                chase_reference=json.loads(receipt.payload_json).get("chase_reference"), reference_review_required=False)
            item["first_receipt_id"] = receipt.id
        item["receipt_count"] += 1
        item["warehouse_received_quantity"] += Decimal(receipt.quantity)
    from app.services.fabric_master import ready
    if ready(db):
        for resolution in db.scalars(select(FabricChaseResolution).where(FabricChaseResolution.factory_id == source.FACTORY).order_by(FabricChaseResolution.revision)):
            item = totals.setdefault(resolution.source_line_id, {"receipt_count": 0, "warehouse_received_quantity": Decimal(0)})
            item["resolution"] = {"id": resolution.id, "revision": resolution.revision, "starting_quantity": resolution.starting_quantity,
                "facts": json.loads(resolution.source_json), "cutoff": json.loads(resolution.cutoff_json), "evidence": resolution.evidence,
                "actor_name": resolution.actor_name, "occurred_at": resolution.occurred_at}
            item.setdefault("source_facts", json.loads(resolution.source_json))
    return totals


def receipt_progress(facts, context=None):
    item = context or {}
    received = item.get("warehouse_received_quantity", Decimal(0))
    prior = item.get("prior_received_quantity")
    mismatch = bool(item.get("source_facts") and any(facts.get(key) != item["source_facts"].get(key) for key in ("material_code", "material_name", "unit", "supplier")))
    ordered = valid_reference(facts.get("ordered_quantity"))
    reported = valid_reference(facts.get("reported_received_quantity"))
    needs_review = prior is None or ordered is None or reported is None or prior > ordered or reported < prior or bool(item.get("reference_review_required"))
    quantity_conflict = bool(item.get("reference_review_required")) or (prior is not None and ordered is not None and prior > ordered) or (prior is not None and reported is not None and reported < prior)
    resolution = item.get("resolution")
    starting = ordered - prior if not needs_review and not mismatch else None
    if item.get("receipt_count") and item.get("source_facts"):
        original_ordered = valid_reference(item["source_facts"].get("ordered_quantity"))
        if ordered != original_ordered:
            needs_review = True
            quantity_conflict = True
            starting = None
    if resolution:
        needs_review = ordered is None or resolution["facts"].get("ordered_quantity") != facts.get("ordered_quantity")
        quantity_conflict = needs_review
        starting = Decimal(resolution["starting_quantity"]) if not needs_review and not mismatch else None
    outstanding = max(starting - received, Decimal(0)) if starting is not None else None
    return {"receipt_count": item.get("receipt_count", 0), "warehouse_received_quantity": decimal_text(received),
            "prior_received_quantity": decimal_text(prior), "warehouse_outstanding_quantity": decimal_text(outstanding),
            "starting_chase_quantity": decimal_text(starting), "chase_resolution": resolution,
            "receipt_reconciliation_required": mismatch, "receipt_quantity_review_required": needs_review,
            "receipt_quantity_conflict": quantity_conflict,
            "receipt_identity_review_required": mismatch or not all(str(facts.get(key) or "").strip() for key in ("material_code", "material_name", "unit", "supplier"))}


def quantity(value, label, allow_zero=False):
    result = number(value)
    if result is None or result < 0 or (not allow_zero and result == 0) or result >= Decimal("1e12") or result.as_tuple().exponent < -6:
        raise HTTPException(422, f"{label}须为{'非负数' if allow_zero else '正数'}，最多六位小数且小于一万亿")
    return result


def receipt_data(db, receipt):
    rows = db.execute(select(FabricStockBatch, FabricInventoryMovement).join(FabricInventoryMovement,
        FabricInventoryMovement.batch_id == FabricStockBatch.id).where(FabricStockBatch.factory_id == source.FACTORY,
        FabricStockBatch.receipt_id == receipt.id).order_by(FabricStockBatch.id))
    return {"id": receipt.id, "source_line_id": receipt.source_line_id, "source_revision": receipt.source_revision,
        "facts": json.loads(receipt.source_json), **json.loads(receipt.payload_json), "quantity": receipt.quantity,
        "unit": receipt.unit, "actor_name": receipt.actor_name, "occurred_at": receipt.occurred_at, "stock_posted": True,
        "batches": [{"id": batch.id, "location": batch.location, "dye_lot": batch.dye_lot, "roll_no": batch.roll_no,
                     "quality_status": batch.quality_status, "quantity": movement.quantity} for batch, movement in rows]}


def receive(db, actor, line_id, payload, *, _state=None, _batch_metadata=None, _commit=True):
    ensure_schema(db)
    body = payload.model_dump(mode="json")
    if not payload.confirmed:
        raise HTTPException(422, "请核实本次实物数量并确认入库")
    request_hash = digest([actor.id, line_id, body])
    state = _state if _state is not None else source.lock_factory(db)
    # Batch roots are durable request identities even though each receipt stores a child UUID.
    if _commit:
        root_candidates = db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == source.FACTORY,
            FabricReceipt.payload_json.contains(str(payload.request_id)))).all()
        if any(json.loads(row.payload_json).get("batch_request_id") == str(payload.request_id) for row in root_candidates):
            raise HTTPException(409, "该请求编号已用于批量入库，请查询入库记录核对")
    previous = db.scalar(select(FabricReceipt).where(FabricReceipt.factory_id == source.FACTORY, FabricReceipt.request_id == str(payload.request_id)))
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, "这个收料请求已用于其他内容或账号，请查询入库记录核对")
        result = receipt_data(db, previous)
        if _commit:
            db.rollback()
        return result
    line = db.scalar(select(FabricProcurementLine).where(FabricProcurementLine.id == line_id, FabricProcurementLine.factory_id == source.FACTORY).execution_options(populate_existing=True))
    if not line or line.status == "WITHDRAWN":
        raise HTTPException(404, "找不到有效的采购来源，请重新查询")
    if line.revision != payload.expected_source_revision:
        raise HTTPException(409, "采购来源已变化，请重新查看后登记入库")
    facts = json.loads(line.payload_json)
    context = receipt_context(db).get(line_id)
    progress = receipt_progress(facts, context)
    if payload.expected_receipt_count != progress["receipt_count"] or progress["receipt_identity_review_required"]:
        raise HTTPException(409, "收料次数或来源物料、单位、供应商已变化，请重新核对入库记录")
    if progress["receipt_quantity_conflict"]:
        raise HTTPException(422, "来源数量回退、订单数量变化或历史先后冲突，请负责人核对起始待收量")
    prior = valid_reference(progress["prior_received_quantity"])
    if payload.prior_received_quantity is not None and (prior is None or quantity(payload.prior_received_quantity, "导入已回参考", True) != prior):
        raise HTTPException(409, "追货参考由导入数据确定，请刷新来源后登记")
    if payload.receipt_date > business_now().date():
        raise HTTPException(422, "实际收货日期不能晚于今天")
    month = payload.receipt_date.strftime("%Y-%m")
    if payload.accounting_month is not None and payload.accounting_month != month:
        raise HTTPException(422, "记账月份须与收货日期一致")
    if not payload.delivery_reference.strip():
        raise HTTPException(422, "请填写送货单号或手工收料依据编号")
    reference = payload.delivery_reference.strip()
    duplicate = db.scalar(select(FabricReceipt.id).where(FabricReceipt.factory_id == source.FACTORY,
        FabricReceipt.source_line_id == line_id, FabricReceipt.delivery_reference == reference))
    if duplicate:
        raise HTTPException(409, "该来源的这张送货依据已入库，请查看入库记录；同单分仓位在一次收料中填写")
    from app.services.fabric_master import receipt_references
    master_references = receipt_references(db, facts, payload)
    location_codes = {row["code"].casefold(): row["code"] for row in master_references["locations"]}
    batches, roll_keys = [], set()
    for batch in payload.batches:
        amount = quantity(batch.quantity, "批次数量")
        if not batch.location.strip():
            raise HTTPException(422, "请填写每项实物的仓位")
        if payload.material_category == "FABRIC" and not batch.dye_lot.strip():
            raise HTTPException(422, "布料每项实物须填写缸号")
        if payload.material_category != "FABRIC" and (batch.dye_lot.strip() or batch.roll_no.strip()):
            raise HTTPException(422, "辅料和线无需填写布料缸号、卷号，请核对分类")
        # A roll can split across bins, but the same roll/bin cannot be entered twice.
        entered_location = batch.location.strip()
        key = (batch.dye_lot.strip(), batch.roll_no.strip(), location_codes.get(entered_location.casefold(), entered_location))
        if batch.roll_no.strip() and key in roll_keys:
            raise HTTPException(422, "同缸号、卷号和仓位重复，请合并核对")
        roll_keys.add(key)
        batches.append({"quantity": decimal_text(amount), "location": key[2], "dye_lot": key[0], "roll_no": key[1]})
    total = sum((Decimal(batch["quantity"]) for batch in batches), Decimal(0))
    quantity(decimal_text(total), "本次实收总数")
    remaining = valid_reference(progress["warehouse_outstanding_quantity"])
    if remaining is not None and total > remaining and not payload.difference_reason.strip():
        raise HTTPException(422, "本次实收超过待收数量，请填写超收说明")
    now = business_now().isoformat()
    frozen_body = {k: v for k, v in body.items() if k not in {"request_id", "factory_id", "confirmed", "batches", "expected_source_revision", "expected_receipt_count"}}
    if _batch_metadata:
        frozen_body.update(_batch_metadata)
    frozen_body.update(delivery_reference=reference, prior_received_quantity=decimal_text(prior), accounting_month=month,
        starting_chase_quantity=progress["starting_chase_quantity"], chase_resolution=progress["chase_resolution"], master_references=master_references)
    if context and context.get("chase_reference"):
        frozen_body["chase_reference"] = context["chase_reference"]
    receipt = FabricReceipt(id=uuid4().hex, factory_id=source.FACTORY, source_line_id=line_id, source_revision=line.revision,
        request_id=str(payload.request_id), request_hash=request_hash, delivery_reference=reference,
        receipt_date=payload.receipt_date.isoformat(), accounting_month=month, quantity=decimal_text(total),
        unit=facts["unit"], prior_received_quantity=decimal_text(prior) if prior is not None else "0", baseline_known=prior is not None,
        source_json=dump(facts), payload_json=dump(frozen_body),
        actor_id=actor.id, actor_name=actor.display_name, occurred_at=now)
    db.add(receipt)
    db.flush()
    movements = []
    for item in batches:
        batch = FabricStockBatch(id=uuid4().hex, factory_id=source.FACTORY, receipt_id=receipt.id,
            material_category=payload.material_category, quality_status="PENDING_INSPECTION", **{k: v for k, v in item.items() if k != "quantity"})
        db.add(batch)
        movements.append(FabricInventoryMovement(id=uuid4().hex, factory_id=source.FACTORY, receipt_id=receipt.id,
            batch_id=batch.id, kind="RECEIPT", quantity=item["quantity"]))
    db.flush()
    db.add_all(movements)
    state.revision += 1
    db.flush()
    result = receipt_data(db, receipt)
    if _commit:
        db.commit()
    return result


def receive_many(db, actor, payload):
    """One factory lock and transaction for all sources; retries bind the whole request."""
    from app.schemas.fabric_receiving import ReceiveSourceRequest
    ensure_schema(db)
    ids = [item.source_line_id for item in payload.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "所选采购明细重复，请合并为一项收料")
    if sum(len(item.batches) for item in payload.items) > 500:
        raise HTTPException(422, "一次最多登记 500 项实物明细，请分批收料")
    batch_id = str(payload.request_id)
    batch_hash = digest([actor.id, payload.model_dump(mode="json")])
    child_ids = [str(uuid5(payload.request_id, line_id)) for line_id in ids]
    try:
        state = source.lock_factory(db)
        candidates = db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == source.FACTORY,
            or_(*(FabricReceipt.payload_json.contains(identity) for identity in [batch_id, *child_ids])))).all()
        previous = [row for row in candidates if json.loads(row.payload_json).get("batch_request_id") == batch_id]
        if previous:
            if len(previous) != len(ids) or {row.source_line_id for row in previous} != set(ids) or any(
                json.loads(row.payload_json).get("batch_request_hash") != batch_hash for row in previous
            ):
                raise HTTPException(409, "这个批量收料请求已用于其他内容或账号，请查询入库记录核对")
            by_source = {row.source_line_id: row for row in previous}
            result = {"request_id": batch_id, "receipts": [receipt_data(db, by_source[line_id]) for line_id in ids]}
            db.rollback()
            return result
        if any(json.loads(row.payload_json).get("batch_request_id") in child_ids for row in candidates):
            raise HTTPException(409, "批量明细编号已用于其他入库请求，请先查询记录核对")
        if db.scalar(select(FabricReceipt.id).where(FabricReceipt.factory_id == source.FACTORY,
            FabricReceipt.request_id.in_([batch_id, *child_ids]))):
            raise HTTPException(409, "该请求编号已登记入库，请先查询记录核对")
        receipts = []
        common = payload.model_dump(exclude={"items", "request_id"})
        for item, child_id in zip(payload.items, child_ids):
            entry = ReceiveSourceRequest(**common, request_id=child_id,
                **item.model_dump(exclude={"source_line_id"}))
            receipts.append(receive(db, actor, item.source_line_id, entry, _state=state, _commit=False,
                _batch_metadata={"batch_request_id": batch_id, "batch_request_hash": batch_hash, "batch_source_ids": ids}))
        db.commit()
        return {"request_id": batch_id, "receipts": receipts}
    except Exception:
        db.rollback()
        raise


def list_receipts(db, search="", offset=0, limit=50):
    ensure_schema(db)
    needle = search.strip().casefold()
    records = db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == source.FACTORY).order_by(FabricReceipt.receipt_date.desc(), FabricReceipt.occurred_at.desc(), FabricReceipt.id))
    items = [record for record in records if not needle or needle in (record.source_json + record.delivery_reference + record.id).casefold()]
    return {"total": len(items), "offset": offset, "limit": limit, "items": [receipt_data(db, record) for record in items[offset:offset+limit]]}


def list_stock(db, search="", offset=0, limit=50):
    ensure_schema(db)
    rows = db.execute(select(FabricStockBatch, FabricReceipt, FabricInventoryMovement).join(FabricReceipt,
        FabricReceipt.id == FabricStockBatch.receipt_id).join(FabricInventoryMovement, FabricInventoryMovement.batch_id == FabricStockBatch.id)
        .where(FabricStockBatch.factory_id == source.FACTORY).order_by(FabricReceipt.receipt_date.desc(), FabricStockBatch.id))
    items, needle = [], search.strip().casefold()
    for batch, receipt, movement in rows:
        facts = json.loads(receipt.source_json)
        item = {"id": batch.id, "receipt_id": receipt.id, "movement_id": movement.id, "kind": movement.kind,
            "source_line_id": receipt.source_line_id, "facts": facts, "quantity": movement.quantity, "unit": receipt.unit,
            "location": batch.location, "dye_lot": batch.dye_lot, "roll_no": batch.roll_no, "material_category": batch.material_category,
            "quality_status": batch.quality_status, "receipt_date": receipt.receipt_date, "accounting_month": receipt.accounting_month,
            "delivery_reference": receipt.delivery_reference, "actor_name": receipt.actor_name, "occurred_at": receipt.occurred_at}
        if not needle or needle in dump(item).casefold():
            items.append(item)
    # Deliberately no total across different materials/units and no inferred opening balance.
    return {"total": len(items), "offset": offset, "limit": limit, "items": items[offset:offset+limit]}


def guard_source_withdrawal(db, line_ids):
    if "fabric_receipts" in inspect(db.get_bind()).get_table_names() and line_ids and db.scalar(select(FabricReceipt.id).where(FabricReceipt.factory_id == source.FACTORY,
        FabricReceipt.source_line_id.in_(line_ids)).limit(1)):
        raise HTTPException(409, "本次导入涉及已登记入库的来源，不能撤销；请保留来源和入库证据后另行更正")
    from app.services.fabric_master import ready
    if ready(db) and line_ids and db.scalar(select(FabricChaseResolution.id).where(FabricChaseResolution.factory_id == source.FACTORY,
        FabricChaseResolution.source_line_id.in_(line_ids)).limit(1)):
        raise HTTPException(409, "本次导入涉及已确认起始待收量的来源，不能撤销；请保留核对证据后另行更正")


def resolve_chase(db, actor, line_id, payload):
    ensure_schema(db)
    from app.services.fabric_master import ensure_schema as ensure_master
    ensure_master(db)
    request_hash = digest([actor.id, line_id, payload.model_dump(mode="json")])
    state = source.lock_factory(db)
    previous = db.scalar(select(FabricChaseResolution).where(FabricChaseResolution.factory_id == source.FACTORY, FabricChaseResolution.request_id == str(payload.request_id)))
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, "该核对请求已用于其他内容或账号")
        db.rollback()
        return {"id": previous.id, "revision": previous.revision, "starting_quantity": previous.starting_quantity, "stock_posted": False}
    line = db.scalar(select(FabricProcurementLine).where(FabricProcurementLine.id == line_id, FabricProcurementLine.factory_id == source.FACTORY))
    if not line or line.status == "WITHDRAWN":
        raise HTTPException(404, "找不到有效采购来源")
    facts = json.loads(line.payload_json)
    context = receipt_context(db).get(line_id, {})
    progress = receipt_progress(facts, context)
    resolution_revision = (context.get("resolution") or {}).get("revision", 0)
    if line.revision != payload.expected_source_revision or progress["receipt_count"] != payload.expected_receipt_count or resolution_revision != payload.expected_resolution_revision:
        raise HTTPException(409, "来源、收料次数或追货核对已变化，请刷新后核对")
    if progress["receipt_identity_review_required"]:
        raise HTTPException(409, "来源身份或单位已变化，不能用数量核对消除身份差异")
    if not payload.confirmed_start or not payload.evidence.strip():
        raise HTTPException(422, "请说明依据并确认填的是本系统首次入库之前的起始待收量")
    amount = quantity(payload.starting_quantity, "起始待收数量", True)
    ordered = quantity(facts.get("ordered_quantity"), "来源订单数量", True)
    if amount > ordered:
        raise HTTPException(422, "起始待收量不能超过当前订单数量，请先核对采购来源")
    cutoff = {"first_receipt_id": context.get("first_receipt_id"), "receipt_count_at_confirmation": progress["receipt_count"],
              "warehouse_received_at_confirmation": progress["warehouse_received_quantity"], "before_all_system_receipts": True}
    resolution = FabricChaseResolution(id=uuid4().hex, factory_id=source.FACTORY, source_line_id=line_id, revision=resolution_revision + 1,
        request_id=str(payload.request_id), request_hash=request_hash, starting_quantity=decimal_text(amount), source_json=dump(facts),
        evidence=payload.evidence.strip(), cutoff_json=dump(cutoff), actor_id=actor.id, actor_name=actor.display_name, occurred_at=business_now().isoformat())
    db.add(resolution)
    line.revision += 1
    state.revision += 1
    db.commit()
    return {"id": resolution.id, "revision": resolution.revision, "starting_quantity": resolution.starting_quantity, "stock_posted": False}
