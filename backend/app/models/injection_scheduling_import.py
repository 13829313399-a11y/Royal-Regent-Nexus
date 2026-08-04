from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingImportBatch(Base):
    __tablename__ = "injection_scheduling_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_import_batch_id_factory",
        ),
        UniqueConstraint(
            "factory_id",
            "preview_request_id",
            name="uq_injection_scheduling_import_preview_request",
        ),
        Index(
            "uq_injection_scheduling_import_confirm_request",
            "factory_id",
            "confirm_request_id",
            unique=True,
            sqlite_where=text("confirm_request_id IS NOT NULL"),
            postgresql_where=text("confirm_request_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('PREVIEW', 'CONFIRMED')",
            name="ck_injection_scheduling_import_batch_status",
        ),
        CheckConstraint(
            "revision >= 1 AND source_size_bytes > 0 AND issue_count >= 0 "
            "AND blocking_issue_count >= 0",
            name="ck_injection_scheduling_import_batch_counts",
        ),
        Index(
            "ix_injection_scheduling_import_batch_factory_created",
            "factory_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_file_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    plan_sheet_name: Mapped[str] = mapped_column(String(128), default="计划表")
    parser_version: Mapped[str] = mapped_column(String(64))
    preview_schema_version: Mapped[str] = mapped_column(String(64))
    normalized_json: Mapped[str] = mapped_column(Text)
    normalized_sha256: Mapped[str] = mapped_column(String(64), index=True)
    summary_json: Mapped[str] = mapped_column(Text)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PREVIEW", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    preview_request_id: Mapped[str] = mapped_column(String(128), index=True)
    preview_payload_hash: Mapped[str] = mapped_column(String(64))
    confirm_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    confirm_payload_hash: Mapped[str] = mapped_column(String(64), default="")
    confirm_mode: Mapped[str] = mapped_column(String(32), default="")
    confirmed_plan_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    confirmed_plan_revision: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(64), default="")
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_at: Mapped[str] = mapped_column(String(32), default="", index=True)


class InjectionSchedulingImportIssue(Base):
    __tablename__ = "injection_scheduling_import_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_import_issue_batch_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_injection_scheduling_import_issue_severity",
        ),
        Index(
            "ix_injection_scheduling_import_issue_batch_blocking_row",
            "batch_id",
            "blocking",
            "source_row",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    sheet_name: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    field_name: Mapped[str] = mapped_column(String(128), default="")
    cell_ref: Mapped[str] = mapped_column(String(32), default="")
    raw_value: Mapped[str] = mapped_column(Text, default="")
    formula_text: Mapped[str] = mapped_column(Text, default="")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
