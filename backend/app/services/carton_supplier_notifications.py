"""Factory-scoped notification projection for supplier delivery notes."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import SystemNotification
from app.models.carton_procurement import CartonReceipt, CartonAuditEvent
from app.models.carton_supplier_portal import SupplierShipment


NOTIFICATION_TYPE = "carton_supplier_shipment"
NOTIFICATION_PREFIX = "carton-shipment:"


def notification_id(shipment_id: str) -> str:
    return f"{NOTIFICATION_PREFIX}{shipment_id}"


def notification_for(shipment: SupplierShipment) -> SystemNotification:
    handled = shipment.status != "SENT"
    return SystemNotification(
        id=notification_id(shipment.id),
        target_user_id="",
        target_permission="carton_procurement:receipt_write",
        target_factory_id=shipment.factory_id,
        target_department="pmc-warehouse",
        type=NOTIFICATION_TYPE,
        title=f"供应商送货单 {shipment.delivery_note_no[:110]} 待核实",
        message=f"{shipment.delivery_date} 送往本厂区；请核对实到、破损与拒收数量后确认收料。",
        payload_json=json.dumps({"shipment_id": shipment.id, "delivery_note_no": shipment.delivery_note_no}, ensure_ascii=False),
        status="handled" if handled else "unread",
        created_at=shipment.created_at,
        read_at=shipment.confirmed_at if handled else "",
        handled_at=shipment.confirmed_at if handled else "",
    )


def create_notification(db: Session, shipment: SupplierShipment) -> SystemNotification:
    notification = db.get(SystemNotification, notification_id(shipment.id))
    if notification is None:
        notification = notification_for(shipment)
        db.add(notification)
    return notification


def legacy_reversed_notifications(db: Session, changed_after: str | None = None) -> list[SystemNotification]:
    """Project notes reversed before the atomic reopening hook was introduced."""
    result = []
    shipments = db.scalars(select(SupplierShipment).join(CartonReceipt, CartonReceipt.id == SupplierShipment.receipt_id)
        .where(SupplierShipment.status == "RECEIVED", CartonReceipt.status == "REVERSED")).all()
    for shipment in shipments:
        stored = db.get(SystemNotification, notification_id(shipment.id))
        candidate = notification_for(shipment)
        event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == shipment.factory_id,
            CartonAuditEvent.entity_id == shipment.receipt_id, CartonAuditEvent.event_type == "RECEIPT_REVERSED")
            .order_by(CartonAuditEvent.sequence.desc()).limit(1))
        candidate.created_at = event.created_at if event else shipment.created_at
        candidate.title = f"供应商送货单 {shipment.delivery_note_no[:100]} 收料已冲销，待更正"
        candidate.message = "请沿原送货单更正验收；旧记录保留，不重复入库。"
        candidate.status = "read" if stored and stored.status == "read" else "unread"
        candidate.read_at = stored.read_at if stored and stored.status == "read" else ""
        candidate.handled_at = ""
        if not changed_after or max(candidate.created_at, candidate.read_at) >= changed_after:
            result.append(candidate)
    return result


def handle_notification(db: Session, shipment: SupplierShipment) -> None:
    notification = create_notification(db, shipment)
    notification.status = "handled"
    notification.read_at = notification.read_at or shipment.confirmed_at
    notification.handled_at = shipment.confirmed_at


def legacy_pending_notifications(db: Session, known_ids: set[str], changed_after: str | None = None) -> list[SystemNotification]:
    """Show pre-existing unconfirmed shipments without mutating a GET request."""
    statement = select(SupplierShipment).where(SupplierShipment.status == "SENT")
    if changed_after:
        statement = statement.where(SupplierShipment.created_at >= changed_after)
    return [notification_for(shipment) for shipment in db.scalars(statement).all()
            if notification_id(shipment.id) not in known_ids]
