"""Append-only internal monthly closing evidence, separate from live previews."""
from sqlalchemy import CheckConstraint, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CuttingPeriodEvent(Base):
    __tablename__ = 'cutting_ops_period_events'
    __table_args__ = (
        UniqueConstraint('factory_id', 'version'),
        CheckConstraint("factory_id = 'huakang-c'"),
        CheckConstraint("action IN ('save','submit','return','lock','reopen')"),
        Index('ix_cutting_period_month', 'factory_id', 'month'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    month: Mapped[str] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
