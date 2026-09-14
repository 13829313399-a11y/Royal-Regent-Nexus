"""Persisted order facts; material and production execution remain downstream."""
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OrderLedgerLine(Base):
    __tablename__ = "order_ledger_lines"
    __table_args__ = (
        UniqueConstraint("factory_id", "customer_code", "identity_key", name="uq_order_ledger_identity"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_order_ledger_quantity"),
        CheckConstraint("shipped_quantity >= 0 AND (quantity IS NULL OR shipped_quantity <= quantity)", name="ck_order_ledger_shipped"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    identity_key: Mapped[str] = mapped_column(String(64))
    reference_no: Mapped[str] = mapped_column(String(255))
    product_no: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    shipped_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    status: Mapped[str] = mapped_column(String(24), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class OrderLedgerVersion(Base):
    __tablename__ = "order_ledger_versions"
    __table_args__ = (UniqueConstraint("line_id", "version", name="uq_order_ledger_version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_lines.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(32))


class OrderLedgerIdentity(Base):
    """Keep previous order references usable after explicit PO reconciliation."""
    __tablename__ = "order_ledger_identities"
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_lines.id"), index=True)


class OrderLedgerSource(Base):
    __tablename__ = "order_ledger_sources"
    __table_args__ = (UniqueConstraint("factory_id", "customer_code", "sha256", "kind", name="uq_order_ledger_source"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(24))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class OrderLedgerLineSource(Base):
    __tablename__ = "order_ledger_line_sources"
    line_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_lines.id"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_sources.id"), primary_key=True)


class OrderLedgerDispatch(Base):
    __tablename__ = "order_ledger_dispatches"
    __table_args__ = (UniqueConstraint("line_id", "version", "recipient", name="uq_order_ledger_dispatch"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_lines.id"), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    recipient: Mapped[str] = mapped_column(String(24), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[str] = mapped_column(String(32), default="")
    received_by: Mapped[str] = mapped_column(String(255), default="")


class OrderLedgerShipment(Base):
    __tablename__ = "order_ledger_shipments"
    __table_args__ = (
        UniqueConstraint("factory_id", "idempotency_key", name="uq_order_ledger_shipment_key"),
        CheckConstraint("quantity > 0", name="ck_order_ledger_shipment_quantity"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_lines.id"), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    ship_date: Mapped[str] = mapped_column(String(10))
    document_no: Mapped[str] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(32))


class OrderLedgerShipmentReversal(Base):
    __tablename__ = "order_ledger_shipment_reversals"
    shipment_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_shipments.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(32))
