"""Rebuildable reference current state; immutable evidence stays in audit."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CartonMaterialReference(Base):
    __tablename__ = 'carton_material_references'
    __table_args__ = (
        UniqueConstraint('factory_id', 'target_context_id', 'version_id', name='uq_carton_material_ref_target_version'),
        Index('ix_carton_material_ref_version', 'factory_id', 'version_id', 'active', 'target_context_id'),
        Index('ix_carton_material_ref_source', 'factory_id', 'source_context_id', 'active', 'reference_id'),
        CheckConstraint('revision >= 1 AND origin_event_sequence > 0 AND last_event_sequence >= origin_event_sequence',
                        name='ck_carton_material_ref_revision'),
    )
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(96))
    version_id: Mapped[str] = mapped_column(String(96))
    source_context_id: Mapped[str] = mapped_column(String(96))
    source_order_key: Mapped[str] = mapped_column(String(96))
    target_context_id: Mapped[str] = mapped_column(String(96))
    target_order_key: Mapped[str] = mapped_column(String(96))
    contract_id: Mapped[str] = mapped_column(String(96))
    active: Mapped[bool] = mapped_column(Boolean)
    revision: Mapped[int] = mapped_column(Integer)
    origin_event_sequence: Mapped[int] = mapped_column(BigInteger)
    last_event_sequence: Mapped[int] = mapped_column(BigInteger)
