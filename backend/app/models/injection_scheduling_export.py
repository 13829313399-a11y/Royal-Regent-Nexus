from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingExportAudit(Base):
    __tablename__ = "injection_scheduling_export_audits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_inj_sched_export_audit_plan_factory",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_inj_sched_export_audit_factory_request",
        ),
        CheckConstraint(
            "export_mode IN ('SOURCE_COMPATIBLE', 'SYSTEM_STANDARD')",
            name="ck_inj_sched_export_audit_mode",
        ),
        CheckConstraint(
            "plan_revision >= 1 AND profile_revision >= 0 AND size_bytes > 0",
            name="ck_inj_sched_export_audit_counts",
        ),
        Index(
            "ix_inj_sched_export_audit_plan_revision",
            "plan_id",
            "plan_revision",
        ),
        Index(
            "ix_inj_sched_export_audit_created_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    export_mode: Mapped[str] = mapped_column(String(32), index=True)
    profile_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    profile_revision: Mapped[int] = mapped_column(Integer, default=0)
    profile_family: Mapped[str] = mapped_column(String(96), default="")
    renderer_code: Mapped[str] = mapped_column(String(96))
    calculation_version: Mapped[str] = mapped_column(String(64))
    rule_revision: Mapped[int] = mapped_column(Integer, default=0)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    reference_report_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    signed_row_manifest_digest: Mapped[str] = mapped_column(String(64), default="")
    export_options_json: Mapped[str] = mapped_column(Text, default="{}")
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    manifest_json: Mapped[str] = mapped_column(Text)
    manifest_sha256: Mapped[str] = mapped_column(String(64), index=True)
    metadata_signature: Mapped[str] = mapped_column(String(64))
    signing_key_id: Mapped[str] = mapped_column(String(64))
    payload_blob: Mapped[bytes] = mapped_column(LargeBinary)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    request_payload_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
