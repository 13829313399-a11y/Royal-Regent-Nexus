"""add recoverable public injection planning artifacts

Revision ID: 20260807_0058
Revises: 20260805_0057
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0058"
down_revision: str | Sequence[str] | None = "20260805_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    plan_columns = (
        sa.Column("export_profile_id", sa.String(96), nullable=True),
        sa.Column("export_profile_revision", sa.Integer(), nullable=True),
        sa.Column(
            "export_profile_family", sa.String(96), nullable=False, server_default=""
        ),
        sa.Column(
            "export_renderer_code", sa.String(96), nullable=False, server_default=""
        ),
        sa.Column(
            "export_binding_source",
            sa.String(32),
            nullable=False,
            server_default="LEGACY_UNKNOWN",
        ),
        sa.Column(
            "calculation_version", sa.String(64), nullable=False, server_default=""
        ),
    )
    for column in plan_columns:
        op.add_column("injection_scheduling_plans", column)
    if op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_inj_sched_plan_export_binding_source",
            "injection_scheduling_plans",
            "export_binding_source IN "
            "('LEGACY_UNKNOWN', 'SYSTEM_STANDARD', 'IMPORT_PROFILE')",
        )
    op.create_index(
        "ix_inj_sched_plan_export_profile_id",
        "injection_scheduling_plans",
        ["export_profile_id"],
    )
    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "preview_generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    with op.batch_alter_table("injection_scheduling_import_issues") as batch_op:
        batch_op.add_column(
            sa.Column(
                "preview_generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_index(
            "ix_inj_sched_import_issue_preview_generation",
            ["preview_generation"],
        )
    with op.batch_alter_table("injection_scheduling_import_actions") as batch_op:
        batch_op.drop_constraint(
            "uq_injection_scheduling_import_action_fingerprint",
            type_="unique",
        )
        batch_op.add_column(
            sa.Column(
                "preview_generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_index(
            "ix_inj_sched_import_action_preview_generation",
            ["preview_generation"],
        )
        batch_op.create_unique_constraint(
            "uq_inj_sched_import_action_generation_fingerprint",
            ["batch_id", "preview_generation", "action_sha256"],
        )

    op.create_table(
        "injection_scheduling_upload_artifacts",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(128), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "detected_format",
            sa.String(32),
            nullable=False,
            server_default="XLSX",
        ),
        sa.Column("payload_blob", sa.LargeBinary(), nullable=True),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column(
            "cleanup_status",
            sa.String(16),
            nullable=False,
            server_default="RETAINED",
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("cleaned_at", sa.String(32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_inj_sched_upload_artifact_batch_factory",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "batch_id",
            name="uq_inj_sched_upload_artifact_batch",
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_inj_sched_upload_artifact_storage_key",
        ),
        sa.CheckConstraint(
            "cleanup_status IN ('RETAINED', 'CLEANED')",
            name="ck_inj_sched_upload_artifact_cleanup_status",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_inj_sched_upload_artifact_size",
        ),
    )
    op.create_index(
        "ix_inj_sched_upload_artifact_batch_id",
        "injection_scheduling_upload_artifacts",
        ["batch_id"],
    )
    op.create_index(
        "ix_inj_sched_upload_artifact_factory_id",
        "injection_scheduling_upload_artifacts",
        ["factory_id"],
    )
    op.create_index(
        "ix_inj_sched_upload_artifact_source_sha256",
        "injection_scheduling_upload_artifacts",
        ["source_sha256"],
    )
    op.create_index(
        "ix_inj_sched_upload_artifact_expiry_cleanup",
        "injection_scheduling_upload_artifacts",
        ["expires_at", "cleanup_status"],
    )
    op.create_table(
        "injection_scheduling_export_audits",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("export_mode", sa.String(32), nullable=False),
        sa.Column("profile_id", sa.String(96), nullable=True),
        sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profile_family", sa.String(96), nullable=False, server_default=""),
        sa.Column("renderer_code", sa.String(96), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("rule_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "mapping_fingerprint", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column(
            "reference_report_event_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "signed_row_manifest_digest",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "export_options_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_signature", sa.String(64), nullable=False),
        sa.Column("signing_key_id", sa.String(64), nullable=False),
        sa.Column("payload_blob", sa.LargeBinary(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("request_payload_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_inj_sched_export_audit_plan_factory",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_inj_sched_export_audit_factory_request",
        ),
        sa.CheckConstraint(
            "export_mode IN ('SOURCE_COMPATIBLE', 'SYSTEM_STANDARD')",
            name="ck_inj_sched_export_audit_mode",
        ),
        sa.CheckConstraint(
            "plan_revision >= 1 AND profile_revision >= 0 AND size_bytes > 0",
            name="ck_inj_sched_export_audit_counts",
        ),
    )
    for column in ("factory_id", "plan_id", "export_mode", "profile_id", "file_sha256", "manifest_sha256", "request_id", "created_by"):
        op.create_index(
            f"ix_inj_sched_export_audit_{column}",
            "injection_scheduling_export_audits",
            [column],
        )
    op.create_index(
        "ix_inj_sched_export_audit_plan_revision",
        "injection_scheduling_export_audits",
        ["plan_id", "plan_revision"],
    )
    op.create_index(
        "ix_inj_sched_export_audit_created_at",
        "injection_scheduling_export_audits",
        ["created_at"],
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_inj_sched_export_audit_no_update
                BEFORE UPDATE ON injection_scheduling_export_audits
                BEGIN
                    SELECT RAISE(ABORT, 'injection scheduling export audit is immutable');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_inj_sched_export_audit_no_delete
                BEFORE DELETE ON injection_scheduling_export_audits
                BEGIN
                    SELECT RAISE(ABORT, 'injection scheduling export audit is immutable');
                END
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION reject_inj_sched_export_audit_mutation()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'injection scheduling export audit is immutable';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_inj_sched_export_audit_no_{operation.lower()}
                    BEFORE {operation} ON injection_scheduling_export_audits
                    FOR EACH ROW EXECUTE FUNCTION reject_inj_sched_export_audit_mutation()
                    """
                )
            )


def downgrade() -> None:
    connection = op.get_bind()
    state = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT COUNT(*) FROM injection_scheduling_upload_artifacts) AS artifacts,
                (SELECT COUNT(*) FROM injection_scheduling_export_audits) AS exports,
                (SELECT COUNT(*) FROM injection_scheduling_import_batches
                 WHERE preview_generation != 1) AS retried_batches,
                (SELECT COUNT(*) FROM injection_scheduling_plans
                 WHERE export_binding_source != 'LEGACY_UNKNOWN'
                    OR export_profile_id IS NOT NULL
                    OR calculation_version != '') AS bound_plans
            """
        )
    ).mappings().one()
    if any(state.values()):
        raise RuntimeError(
            "20260807_0058 cannot be downgraded after upload artifacts, exports, "
            "plan bindings, or re-identified import generations exist; restore a "
            "verified pre-0058 backup."
        )
    op.drop_table("injection_scheduling_export_audits")
    if connection.dialect.name != "sqlite":
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS reject_inj_sched_export_audit_mutation()"
            )
        )
    op.drop_table("injection_scheduling_upload_artifacts")
    with op.batch_alter_table("injection_scheduling_import_actions") as batch_op:
        batch_op.drop_constraint(
            "uq_inj_sched_import_action_generation_fingerprint",
            type_="unique",
        )
        batch_op.drop_index("ix_inj_sched_import_action_preview_generation")
        batch_op.drop_column("preview_generation")
        batch_op.create_unique_constraint(
            "uq_injection_scheduling_import_action_fingerprint",
            ["batch_id", "action_sha256"],
        )
    with op.batch_alter_table("injection_scheduling_import_issues") as batch_op:
        batch_op.drop_index("ix_inj_sched_import_issue_preview_generation")
        batch_op.drop_column("preview_generation")
    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        batch_op.drop_column("preview_generation")
    op.drop_index(
        "ix_inj_sched_plan_export_profile_id",
        table_name="injection_scheduling_plans",
    )
    if connection.dialect.name != "sqlite":
        op.drop_constraint(
            "ck_inj_sched_plan_export_binding_source",
            "injection_scheduling_plans",
            type_="check",
        )
    for column in (
        "calculation_version",
        "export_binding_source",
        "export_renderer_code",
        "export_profile_family",
        "export_profile_revision",
        "export_profile_id",
    ):
        op.drop_column("injection_scheduling_plans", column)
