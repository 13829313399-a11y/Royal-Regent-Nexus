"""Entry-assistance master data; never a replacement for business snapshots."""
from sqlalchemy import Integer, String, Text, UniqueConstraint, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonMasterRecord(Base):
    __tablename__ = "carton_master_records"
    __table_args__ = (UniqueConstraint("factory_id", "kind", "identity", name="uq_carton_master_identity"),
                      UniqueConstraint("id", "factory_id", name="uq_carton_master_factory"))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    identity: Mapped[str] = mapped_column(String(64))
    customer_code: Mapped[str] = mapped_column(String(64), default="")
    code: Mapped[str] = mapped_column(String(128), default="")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    preferred: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    maintained: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class CartonMasterSource(Base):
    __tablename__ = "carton_master_sources"
    __table_args__ = (UniqueConstraint("factory_id", "record_id", "order_id", "signature", name="uq_carton_master_source"),
                      ForeignKeyConstraint(["record_id", "factory_id"], ["carton_master_records.id", "carton_master_records.factory_id"]))
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96))
    signature: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(String(40))
