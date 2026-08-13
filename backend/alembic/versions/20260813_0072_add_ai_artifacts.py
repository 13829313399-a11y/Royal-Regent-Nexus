"""add immutable governed AI artifacts

Revision ID: 20260813_0072
Revises: 20260813_0071
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0072"
down_revision: str | Sequence[str] | None = "20260813_0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("normalized_extension", sa.String(16), nullable=False),
        sa.Column("declared_mime_type", sa.String(128), nullable=False),
        sa.Column("detected_mime_type", sa.String(128), nullable=False),
        sa.Column("content_class", sa.String(16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("scanner_status", sa.String(16), nullable=False),
        sa.Column(
            "scanner_result_code", sa.String(64), nullable=False, server_default="CLEAN"
        ),
        sa.Column(
            "parser_status",
            sa.String(24),
            nullable=False,
            server_default="NOT_REQUESTED",
        ),
        sa.Column("parser_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "parent_artifact_id",
            sa.String(64),
            sa.ForeignKey("ai_artifacts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "derivation_type",
            sa.String(32),
            nullable=False,
            server_default="ORIGINAL",
        ),
        sa.Column("retention_until", sa.String(40), nullable=False),
        sa.Column("deleted_at", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "storage_deleted_at", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column(
            "tombstone_expires_at", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column(
            "backup_delete_by", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "classification IN ('INTERNAL', 'CONFIDENTIAL_BUSINESS', 'RESTRICTED')",
            name="ck_ai_artifact_classification",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DELETION_PENDING', 'DELETED', 'EXPIRED')",
            name="ck_ai_artifact_status",
        ),
        sa.CheckConstraint(
            "scanner_status IN ('CLEAN', 'REJECTED')",
            name="ck_ai_artifact_scanner_status",
        ),
        sa.CheckConstraint(
            "parser_status IN ('NOT_REQUESTED', 'PENDING', 'READY', 'FAILED')",
            name="ck_ai_artifact_parser_status",
        ),
        sa.CheckConstraint(
            "derivation_type IN ('ORIGINAL', 'WORKBOOK_MAPPING', 'TRANSLATION', "
            "'OCR', 'REPORT', 'OTHER_DERIVED')",
            name="ck_ai_artifact_derivation_type",
        ),
        sa.CheckConstraint(
            "content_class IN ('WORKBOOK', 'DOCUMENT', 'IMAGE')",
            name="ck_ai_artifact_content_class",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_ai_artifact_size_positive"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_ai_artifact_sha256_length"),
        sa.CheckConstraint(
            "(parent_artifact_id IS NULL AND derivation_type = 'ORIGINAL') OR "
            "(parent_artifact_id IS NOT NULL AND derivation_type <> 'ORIGINAL')",
            name="ck_ai_artifact_lineage",
        ),
    )
    for name, columns in (
        ("ix_ai_artifacts_owner_user_id", ["owner_user_id"]),
        ("ix_ai_artifacts_factory_id", ["factory_id"]),
        ("ix_ai_artifacts_content_class", ["content_class"]),
        ("ix_ai_artifacts_classification", ["classification"]),
        ("ix_ai_artifacts_status", ["status"]),
        ("ix_ai_artifacts_parent_artifact_id", ["parent_artifact_id"]),
        ("ix_ai_artifacts_retention_until", ["retention_until"]),
        ("ix_ai_artifacts_deleted_at", ["deleted_at"]),
        ("ix_ai_artifacts_created_at", ["created_at"]),
        ("ix_ai_artifacts_updated_at", ["updated_at"]),
        ("ix_ai_artifact_owner_status", ["owner_user_id", "status", "created_at"]),
        ("ix_ai_artifact_factory_status", ["factory_id", "status", "created_at"]),
        ("ix_ai_artifact_retention", ["status", "retention_until"]),
        ("ix_ai_artifact_parent", ["parent_artifact_id", "created_at"]),
        ("ix_ai_artifact_sha256", ["sha256"]),
    ):
        op.create_index(name, "ai_artifacts", columns)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because Artifact metadata and stored bytes cannot be inspected."
        )
    connection = op.get_bind()
    count = int(
        connection.execute(sa.text("SELECT COUNT(*) FROM ai_artifacts")).scalar_one()
    )
    if count:
        raise RuntimeError(
            "Refusing to downgrade 20260813_0072 while protected Artifact data "
            f"exists (ai_artifacts={count}). Close upload and complete retention/export review."
        )
    op.drop_table("ai_artifacts")
