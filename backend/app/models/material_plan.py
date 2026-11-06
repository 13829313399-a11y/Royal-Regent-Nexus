"""Personal sales trial drafts, separate from orders and procurement."""
from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class MaterialPlan(Base):
    __tablename__ = 'material_plan_drafts'
    __table_args__ = (CheckConstraint("factory_id = 'huakang-c'"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)


class MaterialPlanEvent(Base):
    __tablename__ = 'material_plan_events'
    __table_args__ = (UniqueConstraint('factory_id', 'operation_id'), CheckConstraint("factory_id = 'huakang-c'"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    operation_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
