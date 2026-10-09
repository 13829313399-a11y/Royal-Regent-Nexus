"""Rebuildable attention evidence and per-employment personal state."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WorkCenterEntry(Base):
    __tablename__ = "work_center_entries"
    __table_args__ = (
        Index("ix_wc_source", "module", "entity_id"),
        Index("ix_wc_scope", "factory_id", "kind", "lifecycle", "opened_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(512), unique=True)
    module: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(96))
    factory_id: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(12))
    lifecycle: Mapped[str | None] = mapped_column(String(24), nullable=True)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    attention_version: Mapped[int] = mapped_column(Integer, default=1)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[str] = mapped_column(String(255), default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkCenterEvent(Base):
    __tablename__ = "work_center_events"
    __table_args__ = (
        UniqueConstraint("entry_id", "source_event_key", name="uq_wc_event_source"),
        Index("ix_wc_event_page", "entry_id", "occurred_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("work_center_entries.id"))
    source_event_key: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_kind: Mapped[str] = mapped_column(String(32))
    safe_summary: Mapped[str] = mapped_column(String(255))


class WorkCenterUserState(Base):
    __tablename__ = "work_center_user_states"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    employment_epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Read-through source obligations exist before background materialisation.
    entry_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    read_version: Mapped[int] = mapped_column(Integer, default=0)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_attention_version: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    following: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class WorkCenterPreferences(Base):
    __tablename__ = "work_center_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
