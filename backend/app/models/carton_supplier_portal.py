"""Supplier collaboration evidence, separate from internal permissions and stock."""
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class SupplierMember(Base):
    __tablename__ = "carton_supplier_members"
    __table_args__ = (UniqueConstraint("user_id", "factory_id", name="uq_carton_supplier_member_user_factory"),
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),
        CheckConstraint("status IN ('ACTIVE','INACTIVE') AND revision >= 1", name="ck_carton_supplier_member_state"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))

class SupplierCommitment(Base):
    __tablename__ = "carton_supplier_commitments"
    __table_args__ = (ForeignKeyConstraint(["order_line_id", "factory_id"], ["carton_order_lines.id", "carton_order_lines.factory_id"]),
        CheckConstraint("revision >= 1", name="ck_carton_supplier_commitment_revision"))
    order_line_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("carton_purchase_order_issues.id"))
    promised_date: Mapped[str] = mapped_column(String(10))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    accepted_by: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[str] = mapped_column(String(40))

class SupplierShipment(Base):
    __tablename__ = "carton_supplier_shipments"
    __table_args__ = (UniqueConstraint("factory_id", "supplier_id", "delivery_note_no", name="uq_carton_supplier_shipment_note"),
        UniqueConstraint("factory_id", "created_by", "request_id", name="uq_carton_supplier_shipment_request"),
        UniqueConstraint("id", "factory_id", name="uq_carton_supplier_shipment_factory"),
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),
        CheckConstraint("status IN ('SENT','RECEIVED','NOT_RECEIVED') AND revision >= 1", name="ck_carton_supplier_shipment_status"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96), index=True)
    delivery_note_no: Mapped[str] = mapped_column(String(128))
    delivery_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default="SENT", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey("carton_receipts.id"), nullable=True)
    confirmation_request_id: Mapped[str] = mapped_column(String(128), default="")
    confirmation_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    confirmed_by: Mapped[str] = mapped_column(String(64), default="")
    confirmed_at: Mapped[str] = mapped_column(String(40), default="")
    acceptance_json: Mapped[str] = mapped_column(Text, default="{}")

class SupplierShipmentLine(Base):
    __tablename__ = "carton_supplier_shipment_lines"
    __table_args__ = (UniqueConstraint("shipment_id", "order_line_id", name="uq_carton_supplier_shipment_line"),
        ForeignKeyConstraint(["shipment_id", "factory_id"], ["carton_supplier_shipments.id", "carton_supplier_shipments.factory_id"]),
        ForeignKeyConstraint(["order_line_id", "factory_id"], ["carton_order_lines.id", "carton_order_lines.factory_id"]),
        CheckConstraint("quantity > 0", name="ck_carton_supplier_shipment_quantity"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_line_id: Mapped[str] = mapped_column(String(96), index=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("carton_purchase_order_issues.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18,4))
    snapshot_json: Mapped[str] = mapped_column(Text)

class SupplierAttachment(Base):
    __tablename__ = "carton_supplier_attachments"
    __table_args__ = (UniqueConstraint("order_id", "filename", "version", name="uq_carton_supplier_attachment_version"),
        ForeignKeyConstraint(["order_id", "factory_id"], ["carton_orders.id", "carton_orders.factory_id"]),
        CheckConstraint("version >= 1 AND size > 0 AND size <= 10485760", name="ck_carton_supplier_attachment_size"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
