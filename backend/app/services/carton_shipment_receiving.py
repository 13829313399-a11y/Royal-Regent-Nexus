"""Delivery receipt batches projected from immutable supplier acceptance evidence.

The shipment's receipt_id remains a compatibility/current-correction pointer.
All receipt ownership, quantities and accounting use the complete batch history.
"""
import json
from decimal import Decimal
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt
from app.models.carton_supplier_portal import SupplierShipment

EVENTS = {"SUPPLIER_SHIPMENT_RECEIVED", "SUPPLIER_SHIPMENT_NOT_RECEIVED",
          "SUPPLIER_SHIPMENT_RECEIPT_LINKED"}
QUANTITIES = ("received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity")


def batches(db, shipment, *, period=None):
    from app.services.carton_delivery_reopening import totals
    reopened = totals(db, shipment.factory_id, "supplier_shipment", [shipment.id])
    events = db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == shipment.factory_id,
        CartonAuditEvent.entity_type == "supplier_shipment",
        CartonAuditEvent.entity_id == shipment.id,
        CartonAuditEvent.event_type.in_(EVENTS | {"SUPPLIER_SHIPMENT_NON_ARRIVAL_REOPENED"}))
        .order_by(CartonAuditEvent.sequence)).all()
    result = []
    for event in events:
        detail = json.loads(event.detail_json)
        if event.event_type == "SUPPLIER_SHIPMENT_NON_ARRIVAL_REOPENED":
            result = [batch for batch in result if batch.get("receipt_id")]
            continue
        acceptance = detail.get("acceptance") or {}
        if period and (acceptance.get("acceptance_date") or "")[:7] > period:
            continue
        supersedes = detail.get("supersedes_receipt_id")
        if supersedes:
            result = [batch for batch in result if batch.get("receipt_id") != supersedes]
        result.append({**detail, "acceptance": acceptance, "event_id": event.id,
                       "confirmed_at": event.created_at, "closure_reopens": reopened})
    if not events and shipment.receipt_id:
        result = [{"receipt_id": shipment.receipt_id,
                   "acceptance": json.loads(shipment.acceptance_json or "{}"),
                   "event_id": shipment.id, "confirmed_at": shipment.confirmed_at,
                   "closure_reopens": reopened, "legacy_unsequenced": True}]
    for batch in result:
        receipt = db.get(CartonReceipt, batch.get("receipt_id")) if batch.get("receipt_id") else None
        batch["receipt"] = receipt if receipt and receipt.factory_id == shipment.factory_id else None
    return result


def entry(batch, paper):
    original = json.loads(paper.snapshot_json).get("original_unmatched_line_id")
    return next((item for item in batch["acceptance"].get("lines", [])
                 if item["shipment_line_id"] in {paper.id, original}), {})


def amount(item, key):
    return Decimal(str(item.get(key) or 0))


def effective(item):
    return amount(item, QUANTITIES[0]) - sum(amount(item, key) for key in QUANTITIES[1:])


def raw_allocated(batch, paper):
    # Legacy acceptance closed the complete delivery, including its shortfall.
    values = batch.get("delivery_quantities")
    if values is None:
        return paper.quantity
    original = json.loads(paper.snapshot_json).get("original_unmatched_line_id")
    return Decimal(str(values.get(paper.id, values.get(original, 0))))


def closure_sources(batch, paper):
    """Keep original closure identities through a later physical correction."""
    original = json.loads(paper.snapshot_json).get("original_unmatched_line_id")
    carried = [dict(item) for item in batch.get("carried_closures", {}).get(paper.id,
        batch.get("carried_closures", {}).get(original, []))]
    own = max(Decimal(0), raw_allocated(batch, paper) - amount(entry(batch, paper), "received_quantity")
        - sum((Decimal(item["quantity"]) for item in carried), Decimal(0)))
    if own:
        from app.services.carton_ledger_time import ledger_time
        day = batch["acceptance"].get("acceptance_date") or (
            ledger_time(batch["confirmed_at"]).date().isoformat() if batch.get("confirmed_at") else "")
        carried.append({"closure_event_id": batch["event_id"], "quantity": str(own),
            "acceptance_date": day, "reason": entry(batch, paper).get("difference_reason", "")})
    return carried


def allocated(batch, paper):
    return raw_allocated(batch, paper) - sum((min(Decimal(item["quantity"]),
        reopened_quantity(batch, paper, item["closure_event_id"]))
        for item in closure_sources(batch, paper)), Decimal(0))


def reopened_quantity(batch, paper, source_id):
    reopened = batch.get("closure_reopens", {})
    original = json.loads(paper.snapshot_json).get("original_unmatched_line_id")
    return reopened.get((source_id, paper.id), Decimal(0)) + (
        reopened.get((source_id, original), Decimal(0)) if original and original != paper.id else Decimal(0))


def closure_pool(db, shipment, papers):
    result = {}
    for batch in batches(db, shipment):
        for paper in papers:
            for item in closure_sources(batch, paper):
                remaining = Decimal(item["quantity"]) - reopened_quantity(batch, paper, item["closure_event_id"])
                if remaining > 0:
                    result.setdefault(paper.id, []).append(dict(item, remaining_quantity=remaining))
    return result


def progress(db, shipment, papers, *, history=None):
    history = batches(db, shipment) if history is None else history
    corrections = [batch for batch in history if batch["receipt"] and batch["receipt"].status == "REVERSED"]
    correction = corrections[0] if corrections else None
    result = {}
    for paper in papers:
        remaining = max(Decimal(0), paper.quantity - sum(allocated(batch, paper) for batch in history))
        totals = {key: Decimal(0) for key in QUANTITIES}
        for batch in history:
            if batch["receipt"] and batch["receipt"].status != "POSTED":
                continue
            item = entry(batch, paper)
            for key in QUANTITIES:
                totals[key] += amount(item, key)
        reserved = remaining + sum(max(Decimal(0), effective(entry(batch, paper))) for batch in corrections)
        result[paper.id] = {**totals, "effective_quantity": effective(totals),
            "remaining_quantity": remaining, "reserved_quantity": reserved,
            "receivable_quantity": amount(entry(correction, paper), "received_quantity") if correction else remaining,
            "closed_quantity": sum(max(Decimal(0), allocated(batch, paper) - amount(entry(batch, paper), "received_quantity")) for batch in history)}
    return history, correction, result


def linked_receipt_ids(db, factory):
    return {batch["receipt_id"] for shipment in db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory)) for batch in batches(db, shipment) if batch.get("receipt_id")}


def owner(db, factory, receipt_id):
    for shipment in db.scalars(select(SupplierShipment).where(SupplierShipment.factory_id == factory)):
        if any(batch.get("receipt_id") == receipt_id for batch in batches(db, shipment)):
            return shipment
    return None
