"""Purchase-source evidence only. These tables never post warehouse stock."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class FabricProcurementState(Base):
    __tablename__ = "fabric_procurement_state"
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class FabricProcurementLine(Base):
    __tablename__ = "fabric_procurement_lines"
    __table_args__ = (
        UniqueConstraint("factory_id", "identity_key", "ordinal", name="uq_fabric_purchase_source"),
        UniqueConstraint("id", "factory_id", name="uq_fabric_purchase_factory"),
        CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_purchase_factory"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    order_no: Mapped[str] = mapped_column(String(128), index=True)
    supplier: Mapped[str] = mapped_column(String(255))
    material_code: Mapped[str] = mapped_column(String(128), index=True)
    production_no: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(40))


class FabricProcurementImport(Base):
    __tablename__ = "fabric_procurement_imports"
    __table_args__ = (
        UniqueConstraint("factory_id", "request_id", name="uq_fabric_import_request"),
        UniqueConstraint("id", "factory_id", name="uq_fabric_import_factory"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    source_name: Mapped[str] = mapped_column(String(255))
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[str] = mapped_column(String(40))
    result_json: Mapped[str] = mapped_column(Text)


class FabricProcurementEvidence(Base):
    __tablename__ = "fabric_procurement_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
        ForeignKeyConstraint(["import_id", "factory_id"], ["fabric_procurement_imports.id", "fabric_procurement_imports.factory_id"]),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    import_id: Mapped[str] = mapped_column(String(64), index=True)
    sheet: Mapped[str] = mapped_column(String(128))
    row_number: Mapped[int] = mapped_column(Integer)
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text)
