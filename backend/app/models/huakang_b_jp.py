"""Isolated enquiry references, numbering and immutable export evidence."""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class JPReference(Base):
    __tablename__ = "jp_intake_references"
    __table_args__ = (CheckConstraint("factory_id = 'huakang-b'"), CheckConstraint("revision >= 1"))
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_sources.id"))
    revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[str] = mapped_column(String(40))
    options: Mapped[dict] = mapped_column(JSON, default=dict)


class JPReferenceEvent(Base):
    __tablename__ = "jp_intake_reference_events"
    __table_args__ = (UniqueConstraint("factory_id", "kind", "revision"),
                      CheckConstraint("factory_id = 'huakang-b'"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(ForeignKey("order_ledger_sources.id"))
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(40))
    options: Mapped[dict] = mapped_column(JSON, default=dict)


class JPCounter(Base):
    __tablename__ = "jp_intake_counters"
    __table_args__ = (CheckConstraint("factory_id = 'huakang-b'"),
                      CheckConstraint("last_number >= 0 AND last_number <= 99999"))
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class JPExport(Base):
    __tablename__ = "jp_intake_exports"
    __table_args__ = (UniqueConstraint("factory_id", "request_hash"),
                      CheckConstraint("factory_id = 'huakang-b'"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    first_number: Mapped[int] = mapped_column(Integer)
    last_number: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class JPExportIdentity(Base):
    __tablename__ = "jp_intake_export_identities"
    __table_args__ = (CheckConstraint("factory_id = 'huakang-b'"),)
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    export_id: Mapped[str] = mapped_column(ForeignKey("jp_intake_exports.id"))
