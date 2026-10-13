"""Factory-scoped confirmed master data and immutable change evidence."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class FabricMasterRecord(Base):
    __tablename__ = "fabric_master_records"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_fabric_master_factory"),
        UniqueConstraint("factory_id", "kind", "code", name="uq_fabric_master_code"),
        CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_master_factory"),
        CheckConstraint("kind IN ('MATERIAL','SUPPLIER','LOCATION','UNIT')", name="ck_fabric_master_kind"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','INACTIVE')", name="ck_fabric_master_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(40))


class FabricMasterChange(Base):
    __tablename__ = "fabric_master_changes"
    __table_args__ = (
        UniqueConstraint("factory_id", "request_id", name="uq_fabric_master_request"),
        ForeignKeyConstraint(["record_id", "factory_id"], ["fabric_master_records.id", "fabric_master_records.factory_id"]),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[str] = mapped_column(String(40))


class FabricChaseResolution(Base):
    __tablename__ = "fabric_chase_resolutions"
    __table_args__ = (
        UniqueConstraint("factory_id", "request_id", name="uq_fabric_chase_request"),
        UniqueConstraint("source_line_id", "revision", name="uq_fabric_chase_revision"),
        ForeignKeyConstraint(["source_line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
        CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_chase_factory"),
        CheckConstraint("CAST(starting_quantity AS NUMERIC) >= 0", name="ck_fabric_chase_quantity"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_line_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    starting_quantity: Mapped[str] = mapped_column(String(32))
    source_json: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    cutoff_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[str] = mapped_column(String(40))
