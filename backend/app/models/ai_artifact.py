from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIArtifact(Base):
    __tablename__ = "ai_artifacts"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('INTERNAL', 'CONFIDENTIAL_BUSINESS', 'RESTRICTED')",
            name="ck_ai_artifact_classification",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DELETION_PENDING', 'DELETED', 'EXPIRED')",
            name="ck_ai_artifact_status",
        ),
        CheckConstraint(
            "scanner_status IN ('CLEAN', 'REJECTED')",
            name="ck_ai_artifact_scanner_status",
        ),
        CheckConstraint(
            "parser_status IN ('NOT_REQUESTED', 'PENDING', 'READY', 'FAILED')",
            name="ck_ai_artifact_parser_status",
        ),
        CheckConstraint(
            "derivation_type IN ('ORIGINAL', 'WORKBOOK_MAPPING', 'TRANSLATION', "
            "'OCR', 'REPORT', 'OTHER_DERIVED')",
            name="ck_ai_artifact_derivation_type",
        ),
        CheckConstraint(
            "content_class IN ('WORKBOOK', 'DOCUMENT', 'IMAGE')",
            name="ck_ai_artifact_content_class",
        ),
        CheckConstraint("size_bytes > 0", name="ck_ai_artifact_size_positive"),
        CheckConstraint("length(sha256) = 64", name="ck_ai_artifact_sha256_length"),
        CheckConstraint(
            "(parent_artifact_id IS NULL AND derivation_type = 'ORIGINAL') OR "
            "(parent_artifact_id IS NOT NULL AND derivation_type <> 'ORIGINAL')",
            name="ck_ai_artifact_lineage",
        ),
        Index("ix_ai_artifact_owner_status", "owner_user_id", "status", "created_at"),
        Index("ix_ai_artifact_factory_status", "factory_id", "status", "created_at"),
        Index("ix_ai_artifact_retention", "status", "retention_until"),
        Index("ix_ai_artifact_parent", "parent_artifact_id", "created_at"),
        Index("ix_ai_artifact_sha256", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    normalized_extension: Mapped[str] = mapped_column(String(16))
    declared_mime_type: Mapped[str] = mapped_column(String(128))
    detected_mime_type: Mapped[str] = mapped_column(String(128))
    content_class: Mapped[str] = mapped_column(String(16), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(32), index=True)
    storage_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(24), index=True, default="ACTIVE")
    scanner_status: Mapped[str] = mapped_column(String(16))
    scanner_result_code: Mapped[str] = mapped_column(String(64), default="CLEAN")
    parser_status: Mapped[str] = mapped_column(String(24), default="NOT_REQUESTED")
    parser_version: Mapped[str] = mapped_column(String(64), default="")
    model_version: Mapped[str] = mapped_column(String(128), default="")
    parent_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_artifacts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    derivation_type: Mapped[str] = mapped_column(String(32), default="ORIGINAL")
    retention_until: Mapped[str] = mapped_column(String(40), index=True)
    deleted_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    storage_deleted_at: Mapped[str] = mapped_column(String(40), default="")
    tombstone_expires_at: Mapped[str] = mapped_column(String(40), default="")
    backup_delete_by: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
