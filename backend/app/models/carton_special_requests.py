"""Lightweight carton requests. Formal purchase orders remain a separate domain."""
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, DDL, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class SpecialRequest(Base):
    __tablename__ = "carton_special_requests"
    __table_args__ = (UniqueConstraint("id", "factory_id"), UniqueConstraint("factory_id", "request_no"),
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),
        CheckConstraint("kind IN ('SAMPLE','WORKSHOP_MISC','SUPPLIER_GIFT')"),
        CheckConstraint("status IN ('SUBMITTED','SENT','QUOTED','READY','PARTIALLY_RECEIVED','COMPLETED','CANCELLED')"),
        CheckConstraint("revision >= 1"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96))
    request_no: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    requester_name: Mapped[str] = mapped_column(String(128))
    workshop_id: Mapped[str] = mapped_column(String(96), default="")
    customer_code: Mapped[str] = mapped_column(String(64), default="")
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    purpose: Mapped[str] = mapped_column(Text)
    required_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer)
    current_version_id: Mapped[str] = mapped_column(String(96), default="")
    quote_version_id: Mapped[str] = mapped_column(String(96), default="")
    pricing_kind: Mapped[str] = mapped_column(String(24), default="PENDING_QUOTE")
    promised_date: Mapped[str] = mapped_column(String(10), default="")
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    origin: Mapped[str] = mapped_column(String(24), default="INTERNAL", server_default="INTERNAL")


class SpecialLine(Base):
    __tablename__ = "carton_special_lines"
    __table_args__ = (UniqueConstraint("id", "factory_id"),
        ForeignKeyConstraint(["request_id", "factory_id"], ["carton_special_requests.id", "carton_special_requests.factory_id"]),
        CheckConstraint("quantity > 0 AND unit_price >= 0"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    item_no: Mapped[str] = mapped_column(String(128), default="")
    packaging_type: Mapped[str] = mapped_column(String(64))
    paper_quality: Mapped[str] = mapped_column(String(128))
    specification: Mapped[str] = mapped_column(String(255))
    dimension_unit: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal(0))
    mark_mode: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    mark_attachment_id: Mapped[str] = mapped_column(String(96), default="", server_default="")
    mark_asset_id: Mapped[str] = mapped_column(String(96), default="", server_default="")
    mark_asset_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SpecialVersion(Base):
    __tablename__ = "carton_special_versions"
    __table_args__ = (UniqueConstraint("id", "factory_id"), UniqueConstraint("request_id", "revision"),
        ForeignKeyConstraint(["request_id", "factory_id"], ["carton_special_requests.id", "carton_special_requests.factory_id"]))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    snapshot_json: Mapped[str] = mapped_column(Text)


class SpecialAttachment(Base):
    __tablename__ = "carton_special_attachments"
    __table_args__ = (ForeignKeyConstraint(["request_id", "factory_id"], ["carton_special_requests.id", "carton_special_requests.factory_id"]),
        CheckConstraint("role IN ('REFERENCE','DRAFT','CONFIRMED')"), CheckConstraint("size > 0 AND size <= 10485760"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    role: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    line_id: Mapped[str] = mapped_column(String(96), default="", server_default="")


class SpecialMessage(Base):
    __tablename__ = "carton_special_messages"
    __table_args__ = (ForeignKeyConstraint(["request_id", "factory_id"], ["carton_special_requests.id", "carton_special_requests.factory_id"]),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    body: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    audience: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(40))


class SpecialShipment(Base):
    __tablename__ = "carton_special_shipments"
    __table_args__ = (UniqueConstraint("id", "factory_id"), UniqueConstraint("factory_id", "supplier_id", "delivery_note_no", "request_id", name="uq_special_shipment_note_request"),
        ForeignKeyConstraint(["request_id", "factory_id"], ["carton_special_requests.id", "carton_special_requests.factory_id"]),
        ForeignKeyConstraint(["version_id", "factory_id"], ["carton_special_versions.id", "carton_special_versions.factory_id"]))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[str] = mapped_column(String(96))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    version_id: Mapped[str] = mapped_column(String(96))
    delivery_note_no: Mapped[str] = mapped_column(String(128))
    delivery_date: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class SpecialShipmentLine(Base):
    __tablename__ = "carton_special_shipment_lines"
    __table_args__ = (UniqueConstraint("id", "factory_id"), UniqueConstraint("shipment_id", "request_line_id"),
        ForeignKeyConstraint(["shipment_id", "factory_id"], ["carton_special_shipments.id", "carton_special_shipments.factory_id"]),
        ForeignKeyConstraint(["request_line_id", "factory_id"], ["carton_special_lines.id", "carton_special_lines.factory_id"]),
        CheckConstraint("quantity > 0"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    shipment_id: Mapped[str] = mapped_column(String(96), index=True)
    request_line_id: Mapped[str] = mapped_column(String(96))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    snapshot_json: Mapped[str] = mapped_column(Text)


class SpecialReceiptLink(Base):
    __tablename__ = "carton_special_receipt_links"
    __table_args__ = (UniqueConstraint("receipt_line_id"),
        ForeignKeyConstraint(["shipment_line_id", "factory_id"], ["carton_special_shipment_lines.id", "carton_special_shipment_lines.factory_id"]),
        ForeignKeyConstraint(["receipt_line_id", "factory_id"], ["carton_receipt_lines.id", "carton_receipt_lines.factory_id"]))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    shipment_line_id: Mapped[str] = mapped_column(String(96), index=True)
    receipt_line_id: Mapped[str] = mapped_column(String(96))


class UnifiedDelivery(Base):
    """One original supplier note, with existing formal/special source identities."""
    __tablename__ = "carton_unified_deliveries"
    __table_args__ = (
        UniqueConstraint("factory_id", "supplier_id", "delivery_note_no", name="uq_unified_delivery_note"),
        UniqueConstraint("factory_id", "created_by", "request_key", name="uq_unified_delivery_request"),
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96))
    delivery_note_no: Mapped[str] = mapped_column(String(128))
    delivery_date: Mapped[str] = mapped_column(String(10))
    children_json: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


TABLES = tuple(table for table in Base.metadata.tables.values() if table.name.startswith("carton_special_"))

# Fresh synthetic/bootstrap stores receive the same immutable evidence boundary
# as explicit migrations. Existing stores never create these tables at startup.
for _table in TABLES + (UnifiedDelivery.__table__,):
    if _table.name in {"carton_special_requests", "carton_special_lines"}:
        continue
    for _action in ("UPDATE", "DELETE"):
        event.listen(_table, "after_create", DDL(f"CREATE TRIGGER {_table.name}_no_{_action.lower()} BEFORE {_action} ON {_table.name} BEGIN SELECT RAISE(ABORT, 'Carton special evidence is immutable'); END").execute_if(dialect="sqlite"))
    event.listen(_table, "after_create", DDL("CREATE OR REPLACE FUNCTION carton_special_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Carton special evidence is immutable'; END; $$ LANGUAGE plpgsql").execute_if(dialect="postgresql"))
    event.listen(_table, "after_create", DDL(f"CREATE TRIGGER {_table.name}_immutable BEFORE UPDATE OR DELETE ON {_table.name} FOR EACH ROW EXECUTE FUNCTION carton_special_immutable()").execute_if(dialect="postgresql"))
