"""Durable private source files and leased conversion jobs."""
from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DocumentToolSource(Base):
    __tablename__ = "document_tool_sources"
    __table_args__ = (UniqueConstraint("id", "owner_user_id", name="uq_doc_source_owner"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(256))
    detected_type: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512))
    inspection_status: Mapped[str] = mapped_column(String(32), default="queued")
    inspection_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_key: Mapped[str] = mapped_column(String(512), default="")
    factory_context: Mapped[str] = mapped_column(String(64), default="")
    credential_ciphertext: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class DocumentToolJob(Base):
    __tablename__ = "document_tool_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["source_id", "owner_user_id"], ["document_tool_sources.id", "document_tool_sources.owner_user_id"]),
        UniqueConstraint("id", "owner_user_id", name="uq_doc_job_owner"),
        UniqueConstraint("owner_user_id", "client_request_id", name="uq_doc_job_request"),
        CheckConstraint("execution_status IN ('queued','running','awaiting_input','succeeded','failed','cancelled')", name="ck_doc_job_execution"),
        Index("ix_doc_jobs_owner_created", "owner_user_id", "created_at", "id"),
        Index("ix_doc_jobs_claim", "execution_status", "created_at", "id"),
        Index("ix_doc_jobs_lease", "execution_status", "lease_until"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_job_id: Mapped[str | None] = mapped_column(ForeignKey("document_tool_jobs.id"), nullable=True)
    batch_id: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="convert")
    operation: Mapped[str] = mapped_column(String(32))
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)
    request_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    client_request_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    execution_status: Mapped[str] = mapped_column(String(32), default="queued")
    quality_status: Mapped[str] = mapped_column(String(32), default="not_checked")
    stage: Mapped[str] = mapped_column(String(24), default="inspect")
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_revision: Mapped[int] = mapped_column(Integer, default=1)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DocumentToolArtifact(Base):
    __tablename__ = "document_tool_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(["job_id", "owner_user_id"], ["document_tool_jobs.id", "document_tool_jobs.owner_user_id"]),
        UniqueConstraint("job_id", "revision", "storage_key", name="uq_doc_artifact_publish"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(24))
    format: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(256))
    storage_key: Mapped[str] = mapped_column(String(512))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class DocumentToolCorrection(Base):
    __tablename__ = "document_tool_corrections"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_job_id: Mapped[str] = mapped_column(ForeignKey("document_tool_jobs.id"), index=True)
    new_job_id: Mapped[str] = mapped_column(ForeignKey("document_tool_jobs.id"), index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    target_anchor: Mapped[dict] = mapped_column(JSON)
    old_value: Mapped[str] = mapped_column(Text)
    new_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
