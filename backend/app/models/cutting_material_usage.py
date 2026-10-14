"""Append-only custody use, counted remainder and batch cost evidence."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CuttingMaterialEvent(Base):
    __tablename__ = 'cutting_ops_material_events'
    __table_args__ = (
        ForeignKeyConstraint(['line_id'], ['cutting_ops_orders.line_id']),
        UniqueConstraint('factory_id', 'version'),
        CheckConstraint("factory_id = 'huakang-c'"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
