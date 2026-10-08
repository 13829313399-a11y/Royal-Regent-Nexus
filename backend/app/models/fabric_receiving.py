"""Physical receipts and immutable inbound movements, separate from procurement evidence."""
from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class FabricReceipt(Base):
    __tablename__ = "fabric_receipts"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_fabric_receipt_factory"),
        UniqueConstraint("factory_id", "request_id", name="uq_fabric_receipt_request"),
        UniqueConstraint("factory_id", "source_line_id", "delivery_reference", name="uq_fabric_receipt_delivery"),
        ForeignKeyConstraint(["source_line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
        CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_receipt_factory"),
        CheckConstraint("CAST(quantity AS NUMERIC) > 0", name="ck_fabric_receipt_quantity"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_line_id: Mapped[str] = mapped_column(String(64), index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    delivery_reference: Mapped[str] = mapped_column(String(128))
    receipt_date: Mapped[str] = mapped_column(String(10), index=True)
    accounting_month: Mapped[str] = mapped_column(String(7))
    quantity: Mapped[str] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(32))
    prior_received_quantity: Mapped[str] = mapped_column(String(32))
    # Legacy storage stays intact; an unknown baseline is explicitly flagged.
    baseline_known: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    source_json: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[str] = mapped_column(String(40))


class FabricStockBatch(Base):
    __tablename__ = "fabric_stock_batches"
    __table_args__ = (
        UniqueConstraint("id", "receipt_id", "factory_id", name="uq_fabric_batch_receipt_factory"),
        ForeignKeyConstraint(["receipt_id", "factory_id"], ["fabric_receipts.id", "fabric_receipts.factory_id"]),
        CheckConstraint("quality_status = 'PENDING_INSPECTION'", name="ck_fabric_batch_quality"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), index=True)
    location: Mapped[str] = mapped_column(String(128))
    dye_lot: Mapped[str] = mapped_column(String(128))
    roll_no: Mapped[str] = mapped_column(String(128))
    material_category: Mapped[str] = mapped_column(String(16))
    quality_status: Mapped[str] = mapped_column(String(32), default="PENDING_INSPECTION")


class FabricInventoryMovement(Base):
    __tablename__ = "fabric_inventory_movements"
    __table_args__ = (
        ForeignKeyConstraint(["batch_id", "receipt_id", "factory_id"], ["fabric_stock_batches.id", "fabric_stock_batches.receipt_id", "fabric_stock_batches.factory_id"]),
        UniqueConstraint("batch_id", "kind", name="uq_fabric_batch_inbound"),
        CheckConstraint("kind = 'RECEIPT'", name="ck_fabric_movement_kind"),
        CheckConstraint("CAST(quantity AS NUMERIC) > 0", name="ck_fabric_movement_quantity"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="RECEIPT")
    quantity: Mapped[str] = mapped_column(String(32))
