"""Factory/customer-private product defaults, never order or inventory records."""
from sqlalchemy import CheckConstraint, Integer, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OrderProductCatalog(Base):
    __tablename__ = "customer_order_product_catalogs"
    __table_args__ = (CheckConstraint("factory_id = 'huaxing' AND customer_code = 'dickie'"),)
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    products: Mapped[dict] = mapped_column(JSON)


class OrderProductChange(Base):
    __tablename__ = "customer_order_product_changes"
    __table_args__ = (UniqueConstraint("factory_id", "customer_code", "revision"),
        CheckConstraint("factory_id = 'huaxing' AND customer_code = 'dickie'"),
        Index('ix_order_product_history', 'factory_id', 'customer_code', 'product_key', 'revision'))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    customer_code: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    product_key: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)


class OrderProductExportEvidence(Base):
    __tablename__ = "customer_order_product_export_evidence"
    __table_args__ = (CheckConstraint("factory_id = 'huaxing' AND customer_code = 'dickie'"),)
    # Bound to an existing immutable export audit without changing its schema.
    audit_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    customer_code: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
