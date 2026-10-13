"""Private conversations; exclusively created by an explicit Alembic migration."""
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AssistantSession(Base):
    __tablename__ = "nexus_assistant_sessions"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "employment_epoch", "create_request_id", name="uq_nas_create"),
        Index("ix_nas_owner_page", "owner_user_id", "employment_epoch", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    employment_epoch: Mapped[int] = mapped_column(Integer)
    create_request_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160), default="新对话")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    deletion_state: Mapped[str] = mapped_column(String(16), default="active")
    deleted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)
    # Non-content accounting survives deletion so deletion cannot reset a budget.
    budget_day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    budget_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    budget_unknown: Mapped[bool] = mapped_column(Boolean, default=False)


class AssistantRun(Base):
    __tablename__ = "nexus_assistant_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "client_request_id", name="uq_nar_request"),
        Index("ix_nar_admission", "state", "lease_expires_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="connecting")
    model: Mapped[str] = mapped_column(String(160))
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str] = mapped_column(String(64))
    lease_expires_at: Mapped[float] = mapped_column(Float)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_input: Mapped[dict] = mapped_column(JSON)
    context_window: Mapped[dict] = mapped_column(JSON, default=dict)


class AssistantMessage(Base):
    __tablename__ = "nexus_assistant_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_nam_seq"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content_parts: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24))
    help_citations: Mapped[list] = mapped_column(JSON, default=list)
    context_descriptor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class AssistantAttachment(Base):
    __tablename__ = "nexus_assistant_attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    employment_epoch: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(96))
    media_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AssistantFile(Base):
    __tablename__ = "nexus_assistant_files"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_sessions.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    employment_epoch: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(240))
    storage_key: Mapped[str] = mapped_column(String(96))
    media_type: Mapped[str] = mapped_column(String(80))
    byte_size: Mapped[int] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(String(16))
    parse_owner: Mapped[str] = mapped_column(String(64))
    parse_index: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class AssistantArtifact(Base):
    __tablename__ = "nexus_assistant_artifacts"
    __table_args__ = (Index("ix_naa_owner_page", "owner_user_id", "employment_epoch", "updated_at", "id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    employment_epoch: Mapped[int] = mapped_column(Integer)
    session_id: Mapped[str] = mapped_column(String(64))
    source_run_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    current_revision: Mapped[int] = mapped_column(Integer)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class AssistantArtifactVersion(Base):
    __tablename__ = "nexus_assistant_artifact_versions"
    artifact_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_artifacts.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float)


class AssistantFavorite(Base):
    __tablename__ = "nexus_assistant_favorites"
    session_id: Mapped[str] = mapped_column(ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    employment_epoch: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)
