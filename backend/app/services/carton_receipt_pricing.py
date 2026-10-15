"""Explicit zero-price decisions, kept as receipt-line audit evidence."""
import json
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonReceiptLine

EVENT = 'RECEIPT_ZERO_PRICE_DECLARED'


def declarations(db, factory_id, receipt_id):
    line_ids = select(CartonReceiptLine.id).where(
        CartonReceiptLine.factory_id == factory_id,
        CartonReceiptLine.receipt_id == receipt_id)
    return {event.entity_id: json.loads(event.detail_json)['zero_price_kind']
            for event in db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.factory_id == factory_id,
                CartonAuditEvent.event_type == EVENT,
                CartonAuditEvent.entity_id.in_(line_ids)))}
