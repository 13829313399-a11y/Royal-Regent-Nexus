"""Purchase follow-up and reversible import batches; never warehouse receipts."""
import json
from datetime import date
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import business_now
from app.models.fabric_procurement import FabricProcurementLine, FabricProcurementImport, FabricProcurementEvidence
from app.services.fabric_procurement_parser import number, decimal_text, dump, digest
from app.services import fabric_procurement as source


def batches(db):
    records = list(db.scalars(select(FabricProcurementImport).where(FabricProcurementImport.factory_id == source.FACTORY)))
    return sorted(records, key=lambda batch: (json.loads(batch.result_json).get("sequence", 0), batch.occurred_at, batch.id), reverse=True)


def tracking_context(db):
    metadata = {batch.id: json.loads(batch.result_json) for batch in batches(db)}
    changes, tracked = defaultdict(list), set()
    # Do not load raw spreadsheet cells for list queries.
    evidence = db.execute(select(FabricProcurementEvidence.id, FabricProcurementEvidence.line_id,
                                 FabricProcurementEvidence.import_id, FabricProcurementEvidence.before_json,
                                 FabricProcurementEvidence.after_json).where(FabricProcurementEvidence.factory_id == source.FACTORY))
    for event_id, line_id, batch_id, before_json, after_json in evidence:
        batch = metadata[batch_id]
        if batch.get("withdrawal"):
            continue
        before, after = json.loads(before_json), json.loads(after_json)
        if before.get("status") == "PENDING" or after.get("status") == "PENDING":
            tracked.add(line_id)
        if before and before != after and event_id not in batch.get("reviews", {}):
            changes[line_id].append(event_id)
    from app.services.fabric_receiving import receipt_context
    return changes, tracked, receipt_context(db)


def line_tracking(line, context):
    changes, tracked, receipts = context
    facts = json.loads(line.payload_json)
    ordered, received = number(facts.get("ordered_quantity")), number(facts.get("reported_received_quantity"))
    complete = facts["status"] == "RETURNED" or (ordered is not None and received is not None and received >= ordered)
    from app.services.fabric_receiving import receipt_progress
    progress = receipt_progress(facts, receipts.get(line.id))
    warehouse_remaining = number(progress["warehouse_outstanding_quantity"])
    # A zero procurement chase balance alone is not warehouse confirmation.
    warehouse_complete = (progress["receipt_count"] > 0 or progress["chase_resolution"] is not None) and warehouse_remaining == 0
    outstanding = line.status != "WITHDRAWN" and not warehouse_complete and facts["status"] == "PENDING" and not complete
    remainder = max(ordered - received, 0) if ordered is not None and received is not None else None
    arrival_review = line.status != "WITHDRAWN" and not warehouse_complete and line.id in tracked and complete
    # A later non-date reply (e.g. 等通知) supersedes the previous date.
    reply_key = "second_reply" if facts.get("second_reply") or facts.get("second_reply_date") else "supplier_reply"
    promise = facts.get(reply_key + "_date")
    try:
        promise_date = date.fromisoformat(promise) if promise else None
    except ValueError:
        promise_date = None
    days = (business_now().date() - promise_date).days if promise_date else None
    follow_up = outstanding and not warehouse_complete and not arrival_review
    overdue = follow_up and warehouse_remaining is not None and warehouse_remaining > 0 and days is not None and days > 0
    due_today = follow_up and warehouse_remaining is not None and warehouse_remaining > 0 and days == 0
    awaiting_date = follow_up and promise_date is None
    return {"tracking": {"outstanding": outstanding, "not_arrived": outstanding and progress["receipt_count"] == 0 and (received is None or received == 0),
                         "partial": outstanding and ((received is not None and received > 0) or progress["receipt_count"] > 0),
                         "arrival_review": arrival_review, "overdue": overdue, "due_today": due_today, "awaiting_date": awaiting_date,
                         "quantity_review": (outstanding or arrival_review) and progress["receipt_quantity_review_required"],
                         "changed": bool(changes[line.id]) and line.status != "WITHDRAWN"},
            "promise_date": promise_date.isoformat() if promise_date else None, "promise_text": facts.get(reply_key, ""),
            "overdue_days": days if overdue else 0,
            "promise_elapsed_days": max(days, 0) if follow_up and days is not None else None,
            "reported_outstanding_quantity": decimal_text(remainder), "unreviewed_changes": len(changes[line.id]), **progress}


def review_changes(db, actor, line_id, expected_revision):
    source.ensure_schema(db)
    state = source.lock_factory(db)
    line = db.scalar(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == source.FACTORY, FabricProcurementLine.id == line_id))
    if not line or line.status == "WITHDRAWN":
        raise HTTPException(404, "找不到有效采购来源")
    if line.revision != expected_revision:
        raise HTTPException(409, "订单又有变化，请重新查看后标记已读")
    events = set(tracking_context(db)[0][line.id])
    if events:
        for batch in batches(db):
            result = json.loads(batch.result_json)
            event_ids = set(db.scalars(select(FabricProcurementEvidence.id).where(FabricProcurementEvidence.import_id == batch.id))) & events
            for event_id in event_ids:
                result.setdefault("reviews", {})[event_id] = {"actor_id": actor.id, "actor_name": actor.display_name, "occurred_at": business_now().isoformat()}
            if event_ids:
                batch.result_json = dump(result)
        state.revision += 1
    db.commit()
    return {"reviewed": len(events), "stock_posted": False}


def withdrawal_preview(db, batch_id):
    source.ensure_schema(db)
    records = batches(db)
    batch = next((item for item in records if item.id == batch_id), None)
    if not batch:
        raise HTTPException(404, "找不到该厂区的导入记录")
    result = json.loads(batch.result_json)
    if result.get("withdrawal"):
        raise HTTPException(409, "这次导入已经撤销")
    active = [item for item in records if not json.loads(item.result_json).get("withdrawal")]
    if active[0].id != batch_id:
        raise HTTPException(409, "请先撤销后续导入，避免覆盖后续订单变化")
    # Legacy batches lacked a sequence. Equal timestamps cannot prove their order.
    if not result.get("sequence") and len(active) > 1 and active[1].occurred_at == batch.occurred_at:
        raise HTTPException(409, "历史导入时间相同，无法安全确定先后，请核对来源记录")
    evidence = list(db.scalars(select(FabricProcurementEvidence).where(FabricProcurementEvidence.factory_id == source.FACTORY, FabricProcurementEvidence.import_id == batch_id)))
    from app.services.fabric_receiving import guard_source_withdrawal
    guard_source_withdrawal(db, [item.line_id for item in evidence])
    removed = sum(not json.loads(item.before_json) for item in evidence)
    current_revision = source.revision(db)
    return {"id": batch.id, "source_name": batch.source_name, "remove_count": removed, "restore_count": len(evidence) - removed,
            "preview_token": digest(["withdraw", batch.id, current_revision, result]), "revision": current_revision}


def withdraw(db, actor, batch_id, token, reason, confirmed):
    source.ensure_schema(db)
    if not confirmed or not reason.strip():
        raise HTTPException(422, "请填写撤销原因并确认影响范围")
    state = source.lock_factory(db)
    batch = db.scalar(select(FabricProcurementImport).where(FabricProcurementImport.factory_id == source.FACTORY, FabricProcurementImport.id == batch_id))
    if not batch:
        raise HTTPException(404, "找不到该厂区的导入记录")
    result = json.loads(batch.result_json)
    if result.get("withdrawal"):
        db.rollback()
        return result  # Retry after an unknown network result never re-applies rollback.
    review = withdrawal_preview(db, batch_id)
    if review["preview_token"] != token:
        raise HTTPException(409, "采购来源已变化，请重新核对撤销范围")
    evidence = db.scalars(select(FabricProcurementEvidence).where(FabricProcurementEvidence.factory_id == source.FACTORY, FabricProcurementEvidence.import_id == batch_id))
    now = business_now().isoformat()
    for item in evidence:
        line = db.get(FabricProcurementLine, item.line_id)
        before = json.loads(item.before_json)
        if before:
            line.payload_json = item.before_json
            line.status, line.order_no, line.supplier, line.material_code, line.production_no = (before[key] for key in ("status", "order_no", "supplier", "material_code", "production_no"))
        else:
            # Retain the identity and FK evidence; re-import can reuse this slot.
            line.status = "WITHDRAWN"
        line.revision += 1
        line.updated_at = now
    result["withdrawal"] = {"actor_id": actor.id, "actor_name": actor.display_name, "occurred_at": now, "reason": reason.strip(),
                            "remove_count": review["remove_count"], "restore_count": review["restore_count"]}
    batch.result_json = dump(result)
    state.revision += 1
    db.commit()
    return result
