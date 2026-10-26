"""Immutable release of a special delivery's unreceived remainder."""
import json
from decimal import Decimal
from sqlalchemy import select, func, cast, Numeric, true, case, or_, and_
from app.models.carton_procurement import CartonAuditEvent

EVENT = "SPECIAL_SHIPMENT_CLOSED"


def closed_quantity_query(db, factory):
    """Closure allocations in the same SQL snapshot as pending-note totals."""
    if db.bind.dialect.name == "sqlite":
        entries = func.json_each(CartonAuditEvent.detail_json, "$.quantities").table_valued("key", "value")
    else:
        from sqlalchemy.dialects.postgresql import JSONB
        entries = func.jsonb_each_text(cast(CartonAuditEvent.detail_json, JSONB)["quantities"]).table_valued("key", "value")
    from app.services.carton_delivery_reopening import EVENT as REOPENED
    signed = cast(entries.c.value, Numeric) * case((CartonAuditEvent.event_type == EVENT, 1), else_=-1)
    return select(entries.c.key.label("line_id"), func.sum(signed).label("quantity"))\
        .select_from(CartonAuditEvent).join(entries, true()).where(CartonAuditEvent.factory_id == factory,
            or_(CartonAuditEvent.event_type == EVENT, and_(CartonAuditEvent.event_type == REOPENED,
                CartonAuditEvent.entity_type == "carton_special_shipment"))).group_by(entries.c.key).subquery()


def closures(db, factory, shipment_ids=None, *, period=None):
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type == EVENT)
    if shipment_ids is not None:
        query = query.where(CartonAuditEvent.entity_id.in_(shipment_ids))
    records = list(db.scalars(query.order_by(CartonAuditEvent.sequence)))
    from app.services.carton_delivery_reopening import totals
    reopened = totals(db, factory, "carton_special_shipment", [event.entity_id for event in records])
    result = []
    for event in records:
        detail = json.loads(event.detail_json)
        if period and detail["acceptance_date"][:7] > period: continue
        original = detail["quantities"]
        result.append((event, dict(detail, original_quantities=original,
            quantities={key: str(Decimal(value) - reopened.get((event.id, key), Decimal(0))) for key, value in original.items()})))
    return result


def closed_quantities(db, factory, shipment_ids=None, *, period=None):
    result = {}
    for _, detail in closures(db, factory, shipment_ids, period=period):
        for key, value in detail["quantities"].items():
            result[key] = result.get(key, Decimal(0)) + Decimal(value)
    return result
