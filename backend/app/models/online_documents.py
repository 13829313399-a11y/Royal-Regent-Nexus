"""Whole-document editing; uploads and saved revisions are immutable assets."""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OnlineDocument(Base):
    __tablename__ = "online_documents"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_online_document_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_epoch: Mapped[int] = mapped_column(Integer)
    owner_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(8))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    storage_key: Mapped[str] = mapped_column(String(400))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    grants: Mapped[list] = mapped_column(JSON, default=list)
    editor_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    editor_source: Mapped[str] = mapped_column(String(400), default="")
    editor_started: Mapped[int] = mapped_column(Integer, default=0)
    participants: Mapped[dict] = mapped_column(JSON, default=dict)
    pending_save: Mapped[str] = mapped_column(String(64), default="")
    pending_since: Mapped[int] = mapped_column(Integer, default=0)
    saved_request: Mapped[str] = mapped_column(String(64), default="")
    save_error: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    deleted_at: Mapped[str] = mapped_column(String(32), default="")
    access_generation: Mapped[int] = mapped_column(Integer, default=1)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    protection: Mapped[dict] = mapped_column(JSON, default=dict)


class OnlineDocumentRevision(Base):
    __tablename__ = "online_document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision", name="uq_online_document_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("online_documents.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(400))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))
    protection: Mapped[dict] = mapped_column(JSON, default=dict)


class OnlineDocumentEvent(Base):
    __tablename__ = "online_document_events"
    __table_args__ = (UniqueConstraint("document_id", "command_id", name="uq_online_document_command"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("online_documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    actor_epoch: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    command_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32))


class OnlineDocumentFolder(Base):
    __tablename__ = "online_document_folders"
    __table_args__ = (UniqueConstraint("factory_id", "owner_id", "owner_epoch", "name_key", name="uq_online_document_folder_name"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(String(64))
    owner_epoch: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(32))
    deleted_at: Mapped[str] = mapped_column(String(32), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class OnlineDocumentPlacement(Base):
    __tablename__ = "online_document_placements"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_online_document_placement_version"),)
    document_id: Mapped[str] = mapped_column(ForeignKey("online_documents.id"), primary_key=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("online_document_folders.id"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
