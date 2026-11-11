"""Durable source events; never a replacement for order or inspection facts."""
from sqlalchemy import Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class QcDossierOutbox(Base):
    __tablename__ = 'qc_dossier_outbox'
    __table_args__ = (Index('ix_qc_dossier_pending', 'delivered_at', 'created_at', 'id'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
    delivered_at: Mapped[str] = mapped_column(String(40), default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default='')
