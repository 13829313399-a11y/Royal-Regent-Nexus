from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingImportProfile(Base):
    __tablename__ = "injection_scheduling_import_profiles"
    __table_args__ = (
        UniqueConstraint(
            "profile_family",
            "revision",
            name="uq_injection_scheduling_import_profile_family_revision",
        ),
        UniqueConstraint(
            "profile_code",
            name="uq_injection_scheduling_import_profile_code",
        ),
        CheckConstraint(
            "status IN ('PROFILE_DRAFT', 'ACTIVE', 'RETIRED')",
            name="ck_injection_scheduling_import_profile_status",
        ),
        CheckConstraint(
            "revision >= 1 AND lifecycle_revision >= 1",
            name="ck_injection_scheduling_import_profile_revisions",
        ),
        Index(
            "ix_injection_scheduling_import_profile_family_status_revision",
            "profile_family",
            "status",
            "revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    profile_code: Mapped[str] = mapped_column(String(96), index=True)
    profile_family: Mapped[str] = mapped_column(String(96), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    lifecycle_revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="PROFILE_DRAFT", index=True)
    config_json: Mapped[str] = mapped_column(Text)
    definition_sha256: Mapped[str] = mapped_column(String(64), index=True)
    template_signature: Mapped[str] = mapped_column(String(64), default="", index=True)
    header_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    renderer_code: Mapped[str] = mapped_column(String(96), default="")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    reviewed_by_name: Mapped[str] = mapped_column(String(128), default="")
    reviewed_at: Mapped[str] = mapped_column(String(32), default="")
    retired_by: Mapped[str] = mapped_column(String(64), default="")
    retired_by_name: Mapped[str] = mapped_column(String(128), default="")
    retired_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingImportProfileFactory(Base):
    __tablename__ = "injection_scheduling_import_profile_factories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id"],
            ["injection_scheduling_import_profiles.id"],
            name="fk_injection_scheduling_import_profile_factory_profile",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "factory_id",
            name="uq_injection_scheduling_import_profile_factory",
        ),
        Index(
            "ix_injection_scheduling_import_profile_factory_scope",
            "factory_id",
            "profile_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


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
    profile_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    profile_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_definition_sha256: Mapped[str] = mapped_column(String(64), default="")
    template_signature: Mapped[str] = mapped_column(String(64), default="", index=True)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    batch_state: Mapped[str] = mapped_column(String(32), default="LEGACY_PREVIEW", index=True)
    preview_generation: Mapped[int] = mapped_column(Integer, default=1)
    target_draft_plan_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    target_draft_plan_revision: Mapped[int] = mapped_column(Integer, default=0)
    reference_published_plan_id: Mapped[str] = mapped_column(
        String(96), default="", index=True
    )
    reference_published_plan_revision: Mapped[int] = mapped_column(Integer, default=0)
    reference_published_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    order_task_revision_digest: Mapped[str] = mapped_column(String(64), default="")
    action_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    rule_revision: Mapped[int] = mapped_column(Integer, default=0)
    master_revision_digest: Mapped[str] = mapped_column(String(64), default="")
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


class InjectionSchedulingUploadArtifact(Base):
    __tablename__ = "injection_scheduling_upload_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_upload_artifact_batch_factory",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            name="uq_injection_scheduling_upload_artifact_batch",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_injection_scheduling_upload_artifact_storage_key",
        ),
        CheckConstraint(
            "cleanup_status IN ('RETAINED', 'CLEANED')",
            name="ck_injection_scheduling_upload_artifact_cleanup_status",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="ck_injection_scheduling_upload_artifact_size",
        ),
        Index(
            "ix_injection_scheduling_upload_artifact_expiry_cleanup",
            "expires_at",
            "cleanup_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(128))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    detected_format: Mapped[str] = mapped_column(String(32), default="XLSX")
    payload_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
    cleanup_status: Mapped[str] = mapped_column(
        String(16), default="RETAINED", index=True
    )
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    cleaned_at: Mapped[str] = mapped_column(String(32), default="")


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
    preview_generation: Mapped[int] = mapped_column(Integer, default=1, index=True)
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


class InjectionSchedulingImportAction(Base):
    __tablename__ = "injection_scheduling_import_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_import_action_batch_factory",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            "preview_generation",
            "action_sha256",
            name="uq_inj_sched_import_action_generation_fingerprint",
        ),
        Index(
            "ix_injection_scheduling_import_action_batch_type_row",
            "batch_id",
            "action_type",
            "source_row",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    preview_generation: Mapped[int] = mapped_column(Integer, default=1, index=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    stable_order_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    stable_row_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_sheet_name: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_order_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    target_task_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    requires_publish: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(64), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    action_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingImportMasterDecision(Base):
    __tablename__ = "injection_scheduling_import_master_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_import_master_decision_batch_factory",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            "entity_type",
            "business_key",
            name="uq_injection_scheduling_import_master_decision_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    business_key: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(16), default="APPROVED")
    reason: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    decided_by: Mapped[str] = mapped_column(String(64), index=True)
    decided_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
