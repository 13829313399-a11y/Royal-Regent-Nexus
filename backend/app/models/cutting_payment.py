"""Immutable actual-payment registrations and payable allocations."""
from sqlalchemy import CheckConstraint, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CuttingPaymentEvent(Base):
    __tablename__ = 'cutting_ops_payment_events'
    __table_args__ = (
        UniqueConstraint('factory_id', 'version'),
        CheckConstraint("factory_id = 'huakang-c'"),
        CheckConstraint("action IN ('save','submit','return','confirm','reverse')"),
        Index('ix_cutting_payment_document', 'factory_id', 'document_id'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
