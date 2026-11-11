"""Engineering documents; shared materials stay in fabric_master_records."""
from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class EngineeringBom(Base):
    __tablename__ = 'engineering_bom_documents'
    __table_args__ = (CheckConstraint("factory_id = 'huakang-c'"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    effective_version: Mapped[int | None] = mapped_column(Integer)
    item_no: Mapped[str] = mapped_column(String(128))


class EngineeringEvent(Base):
    __tablename__ = 'engineering_bom_events'
    __table_args__ = (UniqueConstraint('factory_id', 'operation_id'),
                      CheckConstraint("factory_id = 'huakang-c'"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    operation_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
