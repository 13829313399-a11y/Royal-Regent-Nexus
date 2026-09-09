from sqlalchemy import String, Text, Integer, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonSupplierSettlement(Base):
    __tablename__ = "carton_supplier_settlements"
    __table_args__ = (
        UniqueConstraint("factory_id", "supplier_id", "period", "currency", "version", name="uq_carton_supplier_settlement_version"),
        CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'SUPERSEDED')", name="ck_carton_supplier_settlement_status"),
        CheckConstraint("revision >= 1 AND version >= 1", name="ck_carton_supplier_settlement_revision"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    currency: Mapped[str] = mapped_column(String(8))
    version: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    statement_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[str] = mapped_column(String(40), default="")
    confirmed_by: Mapped[str] = mapped_column(String(64), default="")
    reopen_reason: Mapped[str] = mapped_column(Text, default="")
