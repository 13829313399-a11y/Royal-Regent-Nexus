"""Append-only warehouse documents. Original fabric receipts remain immutable."""
from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class WarehouseOperation(Base):
    __tablename__ = "warehouse_operations_documents"
    __table_args__ = (
        UniqueConstraint("factory_id", "warehouse", "request_id", name="uq_warehouse_operation_request"),
        UniqueConstraint("factory_id", "warehouse", "sequence", name="uq_warehouse_operation_sequence"),
        CheckConstraint("factory_id = 'huakang-c'", name="ck_warehouse_operation_factory"),
        CheckConstraint("warehouse IN ('fabric','semi')", name="ck_warehouse_operation_warehouse"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    warehouse: Mapped[str] = mapped_column(String(16), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[str] = mapped_column(String(40))
