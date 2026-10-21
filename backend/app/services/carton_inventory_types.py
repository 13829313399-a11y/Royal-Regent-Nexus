"""Read-only inventory origin labels; never split or revalue a shared stock pool."""
import json
from collections import defaultdict
from sqlalchemy import select
from app.models.carton_special_requests import SpecialReceiptLink, SpecialShipmentLine, SpecialShipment, SpecialRequest
from app.services.carton_inventory_identity import inventory_key


def annotate_types(db, factory, balances, movements):
    from app.services.carton_source_links import line_sources
    refs = line_sources(db, factory, list({movement.source_line_id for movement in movements if movement.source_type == 'RECEIPT'}))
    sources = {}
    for receipt_line_id, snapshot, kind, origin in db.execute(select(SpecialReceiptLink.receipt_line_id,
        SpecialShipmentLine.snapshot_json, SpecialRequest.kind, SpecialRequest.origin)
        .join(SpecialShipmentLine, SpecialShipmentLine.id == SpecialReceiptLink.shipment_line_id)
        .join(SpecialShipment, SpecialShipment.id == SpecialShipmentLine.shipment_id)
        .join(SpecialRequest, SpecialRequest.id == SpecialShipment.request_id)
        .where(SpecialReceiptLink.factory_id == factory, SpecialRequest.factory_id == factory)):
        sources[receipt_line_id] = kind if origin == "SUPPLIER_EXTRA" else json.loads(snapshot).get("kind", kind)
    kinds = defaultdict(set)
    links = defaultdict(dict)
    reversed_ids = {movement.reversal_of_movement_id for movement in movements if movement.movement_type == "REVERSAL"}
    for movement in movements:
        if movement.quantity <= 0 or movement.movement_type == "REVERSAL" or movement.id in reversed_ids: continue
        kind = sources.get(movement.source_line_id) if movement.source_type == "RECEIPT" else None
        kinds[inventory_key(movement)].add(kind or ("PURCHASE" if movement.order_line_id else "LEGACY"))
        source = refs.get(movement.source_line_id)
        if source and source.get('id'):
            links[inventory_key(movement)][source['id']] = source
    for balance in balances:
        balance.business_kinds = sorted(kinds[balance.inventory_key] or {"LEGACY"})
        balance.source_requests = list(links[balance.inventory_key].values())
    return balances
