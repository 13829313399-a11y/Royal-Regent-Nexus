"""Connector credentials and immutable ingest receipts; no production accounting."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UvConnector(Base):
    __tablename__ = "uv_connectors"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: datetime.now(UTC).isoformat())
    __table_args__ = (CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_connector_factory"),)


class UvConnectorMachine(Base):
    __tablename__ = "uv_connector_machines"
    connector_id: Mapped[str] = mapped_column(ForeignKey("uv_connectors.id"), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"), primary_key=True)


class UvPrintEvent(Base):
    __tablename__ = "uv_print_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id: Mapped[str] = mapped_column(String(32))
    connector_id: Mapped[str] = mapped_column(ForeignKey("uv_connectors.id"))
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"), index=True)
    generation: Mapped[str] = mapped_column(String(128))
    source_event_id: Mapped[str] = mapped_column(String(255))
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("uv_jobs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[str] = mapped_column(String(40), index=True)
    received_at: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("connector_id", "generation", "source_event_id", name="uq_uv_ingest_event"),
        CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_event_factory"),
        CheckConstraint("seq >= 0", name="ck_uv_event_seq"),
    )
