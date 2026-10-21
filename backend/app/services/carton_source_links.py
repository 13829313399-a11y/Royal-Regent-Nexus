"""Structured, factory-bound source references for existing receipt evidence."""
import json
from sqlalchemy import select
from app.models.carton_special_requests import SpecialRequest, SpecialShipment, SpecialShipmentLine, SpecialReceiptLink, UnifiedDelivery
from app.models.carton_procurement import CartonReceiptLine, CartonAuditEvent
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_supplier_portal import SupplierShipment


def delivery_ids(db, factory):
    result = {}
    for group in db.scalars(select(UnifiedDelivery).where(UnifiedDelivery.factory_id == factory)):
        children = json.loads(group.children_json)
        for identifier in [children.get('formal_id'), *children.get('special_ids', [])]:
            if identifier:
                result[identifier] = group.id
    return result


def line_sources(db, factory, line_ids):
    if not line_ids:
        return {}
    groups = delivery_ids(db, factory)
    result = {}
    query = select(SpecialReceiptLink.receipt_line_id, SpecialShipmentLine, SpecialShipment, SpecialRequest).join(
        SpecialShipmentLine, SpecialShipmentLine.id == SpecialReceiptLink.shipment_line_id).join(
        SpecialShipment, SpecialShipment.id == SpecialShipmentLine.shipment_id).join(
        SpecialRequest, SpecialRequest.id == SpecialShipment.request_id).where(
        SpecialReceiptLink.factory_id == factory, SpecialShipmentLine.factory_id == factory,
        SpecialShipment.factory_id == factory, SpecialRequest.factory_id == factory,
        SpecialReceiptLink.receipt_line_id.in_(line_ids))
    for line_id, paper, shipment, request in db.execute(query):
        frozen = json.loads(paper.snapshot_json)
        result[line_id] = dict(id=request.id, request_no=request.request_no,
            kind=request.kind if request.origin == 'SUPPLIER_EXTRA' else frozen.get('kind', request.kind),
            line_id=paper.request_line_id, shipment_id=shipment.id,
            delivery_id=groups.get(shipment.id, 'SPECIAL:' + shipment.id))
    reviews = list(db.scalars(select(CartonPriceReview).where(CartonPriceReview.factory_id == factory,
        CartonPriceReview.receipt_line_id.in_(line_ids), CartonPriceReview.source_kind == 'REGULAR')))
    classifications = {}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.event_type == 'SUPPLIER_SHIPMENT_RECEIVED',
            CartonAuditEvent.entity_id.in_({review.shipment_id for review in reviews}))):
        detail = json.loads(event.detail_json)
        for line in detail.get('acceptance', {}).get('lines', []):
            kind = {'SAMPLE': 'SAMPLE', 'MISC': 'WORKSHOP_MISC', 'GIFT': 'SUPPLIER_GIFT'}.get(line.get('no_order_decision'))
            if kind:
                classifications[(detail.get('receipt_id'), line.get('shipment_line_id'))] = kind
    papers = {paper.id: paper for paper in db.scalars(select(CartonReceiptLine).where(
        CartonReceiptLine.factory_id == factory, CartonReceiptLine.id.in_(line_ids)))}
    for review in reviews:
        source = dict(delivery_id=groups.get(review.shipment_id, 'FORMAL:' + review.shipment_id))
        paper = papers.get(review.receipt_line_id)
        kind = classifications.get((paper.receipt_id, review.shipment_line_id)) if paper else None
        if kind:
            source['kind'] = kind
        result.setdefault(review.receipt_line_id, source)
    return result


def receipt_sources(db, receipt, papers=None):
    papers = papers if papers is not None else list(db.scalars(select(CartonReceiptLine).where(
        CartonReceiptLine.factory_id == receipt.factory_id, CartonReceiptLine.receipt_id == receipt.id)))
    sources = line_sources(db, receipt.factory_id, [paper.id for paper in papers])
    requests = {source['id']: source for source in sources.values() if source.get('id')}
    identifiers = list(dict.fromkeys(source['delivery_id'] for source in sources.values()))
    if not identifiers:
        shipment = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == receipt.factory_id,
            SupplierShipment.receipt_id == receipt.id))
        if shipment:
            identifiers = [delivery_ids(db, receipt.factory_id).get(shipment.id, 'FORMAL:' + shipment.id)]
        else:
            # All-rejected batches have no price review. The shipment's current
            # pointer may have advanced; the immutable acceptance audit keeps
            # the original source for reversed and superseded receipts too.
            events = db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.factory_id == receipt.factory_id,
                CartonAuditEvent.entity_type == 'supplier_shipment',
                CartonAuditEvent.event_type == 'SUPPLIER_SHIPMENT_RECEIVED'))
            for event in events:
                if json.loads(event.detail_json).get('receipt_id') != receipt.id:
                    continue
                shipment = db.get(SupplierShipment, event.entity_id)
                if shipment and shipment.factory_id == receipt.factory_id and shipment.supplier_id == receipt.supplier_id:
                    identifiers = [delivery_ids(db, receipt.factory_id).get(shipment.id, 'FORMAL:' + shipment.id)]
                    break
    kinds = {source['kind'] for source in sources.values() if source.get('kind')}
    if any(paper.order_line_id for paper in papers):
        kinds.add('PURCHASE')
    if any(not paper.order_line_id and not sources.get(paper.id, {}).get('kind') for paper in papers):
        kinds.add('LEGACY')
    return dict(source_requests=list(requests.values()), delivery_id=identifiers[0] if len(identifiers) == 1 else None,
        business_kinds=sorted(kinds))
