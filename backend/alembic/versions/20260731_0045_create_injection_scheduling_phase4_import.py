"""create injection scheduling phase 4 Excel import workflow

Revision ID: 20260731_0045
Revises: 20260731_0044
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0045"
down_revision: str | Sequence[str] | None = "20260731_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_import_batches() -> None:
    op.create_table(
        "injection_scheduling_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_file_hash", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("plan_sheet_name", sa.String(128), nullable=False, server_default="计划表"),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("preview_schema_version", sa.String(64), nullable=False),
        sa.Column("normalized_json", sa.Text(), nullable=False),
        sa.Column("normalized_sha256", sa.String(64), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PREVIEW"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preview_request_id", sa.String(128), nullable=False),
        sa.Column("preview_payload_hash", sa.String(64), nullable=False),
        sa.Column("confirm_request_id", sa.String(128), nullable=True),
        sa.Column("confirm_payload_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirm_mode", sa.String(32), nullable=False, server_default=""),
        sa.Column("confirmed_plan_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("confirmed_plan_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_import_batch_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "preview_request_id",
            name="uq_injection_scheduling_import_preview_request",
        ),
        sa.CheckConstraint(
            "status IN ('PREVIEW', 'CONFIRMED')",
            name="ck_injection_scheduling_import_batch_status",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND source_size_bytes > 0 AND issue_count >= 0 "
            "AND blocking_issue_count >= 0",
            name="ck_injection_scheduling_import_batch_counts",
        ),
    )
    for column in (
        "factory_id",
        "source_file_hash",
        "normalized_sha256",
        "status",
        "preview_request_id",
        "confirm_request_id",
        "confirmed_plan_id",
        "created_by",
        "created_at",
        "confirmed_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_batches_{column}",
            "injection_scheduling_import_batches",
            [column],
        )
    op.create_index(
        "uq_injection_scheduling_import_confirm_request",
        "injection_scheduling_import_batches",
        ["factory_id", "confirm_request_id"],
        unique=True,
        sqlite_where=sa.text("confirm_request_id IS NOT NULL"),
        postgresql_where=sa.text("confirm_request_id IS NOT NULL"),
    )
    op.create_index(
        "ix_injection_scheduling_import_batch_factory_created",
        "injection_scheduling_import_batches",
        ["factory_id", "created_at"],
    )


def _create_import_issues() -> None:
    op.create_table(
        "injection_scheduling_import_issues",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("cell_ref", sa.String(32), nullable=False, server_default=""),
        sa.Column("raw_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("formula_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_import_issue_batch_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_injection_scheduling_import_issue_severity",
        ),
    )
    for column in (
        "batch_id",
        "factory_id",
        "severity",
        "code",
        "source_row",
        "blocking",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_issues_{column}",
            "injection_scheduling_import_issues",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_import_issue_batch_blocking_row",
        "injection_scheduling_import_issues",
        ["batch_id", "blocking", "source_row"],
    )


def _extend_tasks() -> None:
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("import_batch_id", sa.String(96), nullable=True),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("source_sheet_name", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("source_row", sa.Integer(), nullable=True),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("source_file_hash", sa.String(64), nullable=False, server_default=""),
    )
    for column in ("import_batch_id", "source_row", "source_file_hash"):
        op.create_index(
            f"ix_injection_scheduling_tasks_{column}",
            "injection_scheduling_tasks",
            [column],
        )
    op.create_index(
        "uq_injection_scheduling_task_plan_source_row",
        "injection_scheduling_tasks",
        [
            "factory_id",
            "plan_id",
            "source_file_hash",
            "source_sheet_name",
            "source_row",
        ],
        unique=True,
        sqlite_where=sa.text("source_file_hash <> '' AND source_row IS NOT NULL"),
        postgresql_where=sa.text("source_file_hash <> '' AND source_row IS NOT NULL"),
    )


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_import_issues_no_update
                BEFORE UPDATE ON injection_scheduling_import_issues
                BEGIN
                    SELECT RAISE(ABORT, 'injection scheduling import issue is append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_import_issues_no_delete
                BEFORE DELETE ON injection_scheduling_import_issues
                BEGIN
                    SELECT RAISE(ABORT, 'injection scheduling import issue is append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_import_batches_no_delete
                BEFORE DELETE ON injection_scheduling_import_batches
                BEGIN
                    SELECT RAISE(ABORT, 'injection scheduling import batch cannot be deleted');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_confirmed_import_no_update
                BEFORE UPDATE ON injection_scheduling_import_batches
                WHEN OLD.status = 'CONFIRMED'
                BEGIN
                    SELECT RAISE(ABORT, 'confirmed injection scheduling import is immutable');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_published_task_lineage_no_update
                BEFORE UPDATE ON injection_scheduling_tasks
                WHEN EXISTS (
                    SELECT 1 FROM injection_scheduling_plans
                    WHERE id = OLD.plan_id
                      AND factory_id = OLD.factory_id
                      AND status IN ('PUBLISHED', 'ARCHIVED')
                )
                AND (
                    NEW.import_batch_id IS NOT OLD.import_batch_id
                    OR NEW.source_sheet_name IS NOT OLD.source_sheet_name
                    OR NEW.source_row IS NOT OLD.source_row
                    OR NEW.source_file_hash IS NOT OLD.source_file_hash
                )
                BEGIN
                    SELECT RAISE(ABORT, 'published scheduling task lineage is immutable');
                END
                """
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION guard_injection_scheduling_phase4_import()
                RETURNS trigger AS $$
                BEGIN
                    IF TG_TABLE_NAME = 'injection_scheduling_import_issues' THEN
                        RAISE EXCEPTION 'injection scheduling import issue is append-only';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION 'injection scheduling import batch cannot be deleted';
                    END IF;
                    IF OLD.status = 'CONFIRMED' THEN
                        RAISE EXCEPTION 'confirmed injection scheduling import is immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_import_issues_immutable
                BEFORE UPDATE OR DELETE ON injection_scheduling_import_issues
                FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_phase4_import();
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_import_batches_guard
                BEFORE UPDATE OR DELETE ON injection_scheduling_import_batches
                FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_phase4_import();
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION guard_injection_scheduling_published_task_lineage()
                RETURNS trigger AS $$
                DECLARE
                    plan_status varchar(32);
                BEGIN
                    SELECT status INTO plan_status
                    FROM injection_scheduling_plans
                    WHERE id = OLD.plan_id AND factory_id = OLD.factory_id;
                    IF plan_status IN ('PUBLISHED', 'ARCHIVED')
                       AND (
                           NEW.import_batch_id IS DISTINCT FROM OLD.import_batch_id
                           OR NEW.source_sheet_name IS DISTINCT FROM OLD.source_sheet_name
                           OR NEW.source_row IS DISTINCT FROM OLD.source_row
                           OR NEW.source_file_hash IS DISTINCT FROM OLD.source_file_hash
                       )
                    THEN
                        RAISE EXCEPTION 'published scheduling task lineage is immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_published_task_lineage_guard
                BEFORE UPDATE ON injection_scheduling_tasks
                FOR EACH ROW EXECUTE FUNCTION
                guard_injection_scheduling_published_task_lineage();
                """
            )
        )


def upgrade() -> None:
    _create_import_batches()
    _create_import_issues()
    _extend_tasks()
    _create_guards()


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for trigger_name in (
            "trg_injection_scheduling_import_issues_no_update",
            "trg_injection_scheduling_import_issues_no_delete",
            "trg_injection_scheduling_import_batches_no_delete",
            "trg_injection_scheduling_confirmed_import_no_update",
            "trg_injection_scheduling_published_task_lineage_no_update",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_injection_scheduling_import_issues_immutable "
                "ON injection_scheduling_import_issues"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_injection_scheduling_import_batches_guard "
                "ON injection_scheduling_import_batches"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_task_lineage_guard "
                "ON injection_scheduling_tasks"
            )
        )
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS guard_injection_scheduling_phase4_import()")
        )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS "
                "guard_injection_scheduling_published_task_lineage()"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    batch_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM injection_scheduling_import_batches")
    ).scalar_one()
    imported_task_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM injection_scheduling_tasks "
            "WHERE source_file_hash <> '' OR import_batch_id IS NOT NULL"
        )
    ).scalar_one()
    if batch_count or imported_task_count:
        raise RuntimeError(
            "20260731_0045 cannot be downgraded after an injection scheduling "
            "import preview or imported task exists; back up the domain first."
        )
    _drop_guards()
    op.drop_index(
        "uq_injection_scheduling_task_plan_source_row",
        table_name="injection_scheduling_tasks",
    )
    for column in ("source_file_hash", "source_row", "import_batch_id"):
        op.drop_index(
            f"ix_injection_scheduling_tasks_{column}",
            table_name="injection_scheduling_tasks",
        )
    for column in ("source_file_hash", "source_row", "source_sheet_name", "import_batch_id"):
        op.drop_column("injection_scheduling_tasks", column)
    op.drop_table("injection_scheduling_import_issues")
    op.drop_table("injection_scheduling_import_batches")
