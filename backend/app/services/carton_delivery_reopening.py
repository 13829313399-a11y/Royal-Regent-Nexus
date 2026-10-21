"""Append-only correction of genuinely unreceived delivery shortfalls."""
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrderLine

EVENT = "DELIVERY_SHORTFALL_REOPENED"


def events(db, factory, entity_type, identifiers):
    return list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == entity_type, CartonAuditEvent.entity_id.in_(identifiers),
        CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence))) if identifiers else []


def totals(db, factory, entity_type, identifiers):
    result = {}
    for event in events(db, factory, entity_type, identifiers):
        for item in json.loads(event.detail_json)["allocations"]:
            key = (item["closure_event_id"], item["shipment_line_id"])
            result[key] = result.get(key, Decimal(0)) + Decimal(item["quantity"])
    return result


def allocate(pool, supplied):
    """Allocate only the net, physically unreceived part of original closures."""
    result = []
    for item in supplied:
        remaining = item.quantity
        for source in pool.get(item.shipment_line_id, []):
            quantity = min(remaining, source["remaining_quantity"])
            if quantity > 0:
                result.append({"closure_event_id": source["closure_event_id"],
                    "shipment_line_id": item.shipment_line_id, "quantity": str(quantity),
                    "acceptance_date": source["acceptance_date"]})
                remaining -= quantity
        if remaining > 0:
            raise HTTPException(409, "重开数量超过当前真正未到货的关闭余量，可能已重开或已被后续收货使用，请刷新核对")
    return result


def record(db, user, shipment, entity_type, allocations, reason, revision):
    from app.services import carton_procurement as core
    quantities = {}
    for item in allocations:
        key = item["shipment_line_id"]
        quantities[key] = str(Decimal(quantities.get(key, "0")) + Decimal(item["quantity"]))
    return core._audit(db, user, shipment.factory_id, EVENT, entity_type, shipment.id,
        {"reason": reason, "operation_date": core.business_now().date().isoformat(),
         "delivery_date": shipment.delivery_date, "revision": revision,
         "quantities": quantities, "allocations": allocations})


def formal(db, user, shipment, command, reason):
    from app.services import carton_supplier_portal as portal, carton_shipment_receiving as receiving
    from app.services import carton_replenishment_supplier as replacement
    from app.services.carton_material_correction import guard_lines
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    if shipment.revision != command.expected_revision:
        raise HTTPException(409, "原送货单版本已变化，请刷新后重开")
    if portal.receipt_link.link_only(shipment):
        raise HTTPException(409, "后补凭证不产生新的可收余量，请沿原收料更正")
    papers, unmatched = portal._shipment_sources(db, shipment)
    selected = {paper.id: paper for paper in papers}
    if any(item.shipment_line_id not in selected for item in command.lines):
        raise HTTPException(422, "重开纸品须属于此原送货单及明确采购来源，未关联纸品请先核实来源")
    if any(batch.get("legacy_unsequenced") for batch in receiving.batches(db, shipment)):
        raise HTTPException(409, "历史原单缺少完整验收审计，不能直接重开短送；请先核实原收料和关闭证据")
    pool = receiving.closure_pool(db, shipment, papers + unmatched)
    allocations = allocate(pool, command.lines)
    ensure_evidence_open(db, shipment.factory_id, shipment.supplier_id, shipment.delivery_date,
        *(item["acceptance_date"] for item in allocations))
    guard_lines(db, shipment.factory_id, [selected[item.shipment_line_id].order_line_id for item in command.lines])
    for item in command.lines:
        paper = selected[item.shipment_line_id]
        line = db.get(CartonOrderLine, paper.order_line_id)
        order = portal.supplier_order(db, line.order_id, shipment.factory_id, shipment.supplier_id)
        frozen = json.loads(paper.snapshot_json)
        if frozen.get("replenishment_issue_id"):
            replacement.validate_issue(db, order, frozen["replenishment_issue_id"])
            source = next(source for source in replacement.sources(db, order) if source["issue_id"] == paper.issue_id)
            if not all(entry["accepted"] for entry in source["lines"]):
                raise HTTPException(409, "原补单尚未确认或存在异议，请先从变更待办核实")
            capacity = Decimal(next(entry for entry in source["lines"] if entry["id"] == line.id)["remaining_to_ship"])
        else:
            portal.executable(db, order, paper.issue_id)
            current = portal.order_out(db, order)
            if not all(entry["accepted"] for entry in current["lines"] if Decimal(entry["required_quantity"]) > 0):
                raise HTTPException(409, "原采购版本尚未整单确认，请先核实供应商接单")
            capacity = replacement.ordinary_capacity(db, order, line.id)
        if item.quantity > capacity:
            raise HTTPException(409, "原采购或补单的可收额度已被其他收料/送货占用，不能重开此余量")
    shipment.revision += 1
    record(db, user, shipment, "supplier_shipment", allocations, reason, shipment.revision)
    shipment.status = "SENT"
    db.flush()
    notification = portal.shipment_notifications.create_notification(db, shipment)
    notification.status = "unread"; notification.read_at = notification.handled_at = ""
    notification.created_at = portal.now_text()
    notification.title = f"供应商送货单 {shipment.delivery_note_no[:100]} 短送更正，重新待收"
    notification.message = "原关闭记录及重开原因已保留；仅恢复选中纸品的未到货余量，请沿原单核实实际到货。"


def special(db, user, shipment, command, reason):
    from app.services import carton_special_requests as service
    from app.services.carton_special_receiving import closures
    from app.services.carton_supplier_changes import special_confirmation
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    row = service.access(db, user, shipment.factory_id, shipment.request_id)
    service.require_revision(row, command)
    if (row.status not in {"SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED"}
        or shipment.version_id != row.current_version_id or service.detail(db, user, row.factory_id, row.id)["deleted"]
        or special_confirmation(db, row)["status"] not in {"ACCEPTED", "SUPPLIER_ORIGIN"}):
        raise HTTPException(409, "原样板或杂单已结束、取消、资料版本改变或存在接单异议，请先核实来源")
    shipped, _, consumed, received_by_request, _ = service.state_counts(db, row)
    sources = {paper.id: paper for paper in shipped if paper.shipment_id == shipment.id}
    if any(item.shipment_line_id not in sources for item in command.lines):
        raise HTTPException(422, "重开纸品不属于此样板或杂单送货单")
    pool = {}
    for event, closure in closures(db, row.factory_id, [shipment.id]):
        for key, value in closure["quantities"].items():
            pool.setdefault(key, []).append({"closure_event_id": event.id, "remaining_quantity": Decimal(value),
                "acceptance_date": closure["acceptance_date"]})
    allocations = allocate(pool, command.lines)
    ensure_evidence_open(db, row.factory_id, row.supplier_id, shipment.delivery_date,
        *(item["acceptance_date"] for item in allocations))
    current = {paper.id: paper for paper in service.lines(db, row)}
    requested = {}
    for item in command.lines:
        key = sources[item.shipment_line_id].request_line_id
        requested[key] = requested.get(key, Decimal(0)) + item.quantity
    for key, quantity in requested.items():
        reserved = sum((max(Decimal(0), paper.quantity - consumed.get(paper.id, Decimal(0)))
            for paper in shipped if paper.request_line_id == key), Decimal(0))
        if key not in current or quantity > current[key].quantity - received_by_request.get(key, Decimal(0)) - reserved:
            raise HTTPException(409, "原样板或杂单需求已被其他收料/送货占用，不能重开此余量")
    service.version(db, user, row, "DELIVERY_SHORTFALL_REOPENED", reason=reason)
    record(db, user, shipment, "carton_special_shipment", allocations, reason, row.revision)
    db.flush()
    service.notify(db, row, "SHIPPED", audience="INTERNAL")
    service.notify(db, row, "DELIVERY_SHORTFALL_REOPENED", audience="SUPPLIER")


def legacy_non_arrival(db, user, shipment, payload):
    """Retain the old zero-arrival endpoint with the same net closure ledger."""
    from types import SimpleNamespace
    from app.services import carton_special_requests as service, carton_supplier_portal as portal
    from app.services import carton_shipment_receiving as receiving
    from app.services.carton_unified_deliveries import authorize
    user = service.locked_actor(db, user, payload.factory_id)
    authorize(db, user, payload.factory_id)
    portal.ensure_shipment_customers(db, user, shipment)
    digest, saved = service.replay(db, user, payload, "LEGACY_REOPEN_SHORTFALL", shipment.id)
    if saved: return saved
    if shipment.status != "NOT_RECEIVED" or shipment.receipt_id:
        raise HTTPException(409, "此入口仅更正整张零到货记录；部分实收请在原统一送货单逐纸品重开")
    papers, unmatched = portal._shipment_sources(db, shipment)
    pool = receiving.closure_pool(db, shipment, papers + unmatched)
    command = SimpleNamespace(expected_revision=payload.expected_revision, lines=[SimpleNamespace(
        shipment_line_id=key, quantity=sum((item["remaining_quantity"] for item in values), Decimal(0)))
        for key, values in pool.items()])
    if not command.lines: raise HTTPException(409, "此原单已无可重开的未到货关闭余量")
    formal(db, user, shipment, command, payload.reason)
    response = portal.shipment_out(db, shipment, internal=True)
    event = service.core._audit(db, user, payload.factory_id, "SUPPLIER_SHORTFALL_REOPEN_COMMAND", "supplier_shipment", shipment.id,
        {"fingerprint": digest, "response": response})
    event.id = service.replay_id(user, payload)
    db.commit()
    return response
