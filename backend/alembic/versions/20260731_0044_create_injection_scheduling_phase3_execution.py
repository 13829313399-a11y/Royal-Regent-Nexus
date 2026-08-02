"""create injection scheduling phase 3 execution workflow

Revision ID: 20260731_0044
Revises: 20260731_0043
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0044"
down_revision: str | Sequence[str] | None = "20260731_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PHASE3_TABLES_CHILD_FIRST = (
    "injection_scheduling_audit_events",
    "injection_scheduling_published_snapshots",
    "injection_scheduling_plan_revisions",
    "injection_scheduling_shift_reports",
    "injection_scheduling_tasks",
    "injection_scheduling_plans",
    "injection_scheduling_orders",
)

APPEND_ONLY_TABLES = (
    "injection_scheduling_shift_reports",
    "injection_scheduling_plan_revisions",
    "injection_scheduling_published_snapshots",
    "injection_scheduling_audit_events",
)


def _create_orders() -> None:
    op.create_table(
        "injection_scheduling_orders",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("order_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("mold_id", sa.String(96), nullable=True),
        sa.Column("order_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column(
            "source_completed_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "estimated_completion_at",
            sa.String(32),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "estimated_remaining_shifts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("delivery_slack_days", sa.Integer(), nullable=True),
        sa.Column(
            "delivery_start_date", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "delivery_due_date", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "priority_code", sa.String(32), nullable=False, server_default="NORMAL"
        ),
        sa.Column(
            "material_readiness_status",
            sa.String(32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("warehouse_text", sa.String(255), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "source_type", sa.String(32), nullable=False, server_default="manual"
        ),
        sa.Column("source_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_version", sa.String(128), nullable=False, server_default=""),
        sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="BACKLOG"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_order_id_factory"
        ),
        sa.CheckConstraint(
            "order_quantity > 0",
            name="ck_injection_scheduling_order_quantity",
        ),
        sa.CheckConstraint(
            "source_completed_quantity >= 0 AND completed_quantity >= 0",
            name="ck_injection_scheduling_order_completed_quantity",
        ),
        sa.CheckConstraint(
            "priority_code IN ('NORMAL', 'URGENT', 'CRITICAL')",
            name="ck_injection_scheduling_order_priority",
        ),
        sa.CheckConstraint(
            "material_readiness_status IN "
            "('unknown', 'ready', 'partial', 'blocked')",
            name="ck_injection_scheduling_order_material_readiness",
        ),
        sa.CheckConstraint(
            "status IN ('BACKLOG', 'SCHEDULED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_scheduling_order_status",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND estimated_remaining_shifts >= 0",
            name="ck_injection_scheduling_order_revision",
        ),
    )
    for column in (
        "factory_id",
        "order_no",
        "item_no",
        "mold_id",
        "delivery_due_date",
        "priority_code",
        "material_readiness_status",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_orders_{column}",
            "injection_scheduling_orders",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_order_factory_status_due",
        "injection_scheduling_orders",
        ["factory_id", "status", "delivery_due_date"],
    )
    op.create_index(
        "ix_injection_scheduling_order_factory_number_item",
        "injection_scheduling_orders",
        ["factory_id", "order_no", "item_no"],
    )


def _create_plans() -> None:
    op.create_table(
        "injection_scheduling_plans",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rule_set_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("rule_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "based_on_plan_id", sa.String(96), nullable=False, server_default=""
        ),
        sa.Column("rollback_request_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("published_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "published_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("published_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("archived_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_plan_id_factory"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_injection_scheduling_plan_status",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_plan_revision",
        ),
    )
    for column in (
        "factory_id",
        "business_date",
        "status",
        "based_on_plan_id",
        "rollback_request_id",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "published_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_plans_{column}",
            "injection_scheduling_plans",
            [column],
        )
    op.create_index(
        "uq_injection_scheduling_one_draft_per_factory",
        "injection_scheduling_plans",
        ["factory_id"],
        unique=True,
        sqlite_where=sa.text("status = 'DRAFT'"),
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index(
        "uq_injection_scheduling_one_published_per_factory",
        "injection_scheduling_plans",
        ["factory_id"],
        unique=True,
        sqlite_where=sa.text("status = 'PUBLISHED'"),
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    op.create_index(
        "uq_injection_scheduling_rollback_request",
        "injection_scheduling_plans",
        ["factory_id", "rollback_request_id"],
        unique=True,
        sqlite_where=sa.text("rollback_request_id IS NOT NULL"),
        postgresql_where=sa.text("rollback_request_id IS NOT NULL"),
    )
    op.create_index(
        "ix_injection_scheduling_plan_factory_status_updated",
        "injection_scheduling_plans",
        ["factory_id", "status", "updated_at"],
    )


def _create_tasks() -> None:
    op.create_table(
        "injection_scheduling_tasks",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("mold_id", sa.String(96), nullable=True),
        sa.Column("mold_copy_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "execution_status",
            sa.String(32),
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column("planned_start", sa.String(32), nullable=False, server_default=""),
        sa.Column("planned_finish", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "shift_target_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reported_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "estimated_start", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "estimated_finish", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "estimated_remaining_shifts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("delivery_slack_days", sa.Integer(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "manual_override_reason", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column(
            "active_execution", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_task_id_factory"
        ),
        sa.UniqueConstraint(
            "plan_id",
            "machine_id",
            "sequence_no",
            name="uq_injection_scheduling_task_plan_machine_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_task_plan_factory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_task_order_factory",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_task_machine_factory",
        ),
        sa.ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_task_mold_factory",
        ),
        sa.CheckConstraint(
            "execution_status IN "
            "('QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_scheduling_task_execution_status",
        ),
        sa.CheckConstraint(
            "sequence_no >= 0 AND mold_copy_no >= 1",
            name="ck_injection_scheduling_task_sequence_copy",
        ),
        sa.CheckConstraint(
            "shift_target_quantity >= 0 AND reported_quantity >= 0",
            name="ck_injection_scheduling_task_quantities",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND estimated_remaining_shifts >= 0",
            name="ck_injection_scheduling_task_revision",
        ),
    )
    for column in (
        "factory_id",
        "plan_id",
        "machine_id",
        "order_id",
        "mold_id",
        "execution_status",
        "active_execution",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_tasks_{column}",
            "injection_scheduling_tasks",
            [column],
        )
    op.create_index(
        "uq_injection_scheduling_one_running_per_machine",
        "injection_scheduling_tasks",
        ["factory_id", "machine_id"],
        unique=True,
        sqlite_where=sa.text(
            "active_execution = 1 AND execution_status = 'RUNNING'"
        ),
        postgresql_where=sa.text(
            "active_execution = true AND execution_status = 'RUNNING'"
        ),
    )
    op.create_index(
        "ix_injection_scheduling_task_plan_machine_sequence",
        "injection_scheduling_tasks",
        ["plan_id", "machine_id", "sequence_no"],
    )
    op.create_index(
        "ix_injection_scheduling_task_factory_execution",
        "injection_scheduling_tasks",
        ["factory_id", "active_execution", "execution_status"],
    )


def _create_reports_and_snapshots() -> None:
    op.create_table(
        "injection_scheduling_shift_reports",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("shift_code", sa.String(16), nullable=False),
        sa.Column("quantity_mode", sa.String(16), nullable=False),
        sa.Column("reported_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column(
            "normalized_increment_quantity", sa.Numeric(14, 3), nullable=False
        ),
        sa.Column(
            "shift_target_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("downtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exception_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("exception_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "reported_status", sa.String(32), nullable=False, server_default="RUNNING"
        ),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("reported_by", sa.String(64), nullable=False),
        sa.Column(
            "reported_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_scheduling_shift_report_request",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "factory_id"],
            ["injection_scheduling_tasks.id", "injection_scheduling_tasks.factory_id"],
            name="fk_injection_scheduling_shift_report_task_factory",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_shift_report_order_factory",
        ),
        sa.CheckConstraint(
            "shift_code IN ('DAY', 'NIGHT')",
            name="ck_injection_scheduling_shift_report_shift",
        ),
        sa.CheckConstraint(
            "quantity_mode IN ('INCREMENTAL', 'CUMULATIVE')",
            name="ck_injection_scheduling_shift_report_mode",
        ),
        sa.CheckConstraint(
            "reported_quantity >= 0 AND normalized_increment_quantity >= 0",
            name="ck_injection_scheduling_shift_report_quantity",
        ),
        sa.CheckConstraint(
            "shift_target_quantity >= 0 AND downtime_minutes >= 0",
            name="ck_injection_scheduling_shift_report_operating_values",
        ),
    )
    for column in (
        "factory_id",
        "task_id",
        "order_id",
        "business_date",
        "shift_code",
        "request_id",
        "reported_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_shift_reports_{column}",
            "injection_scheduling_shift_reports",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_shift_report_factory_task_created",
        "injection_scheduling_shift_reports",
        ["factory_id", "task_id", "created_at"],
    )

    op.create_table(
        "injection_scheduling_plan_revisions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "plan_id",
            "plan_revision",
            name="uq_injection_scheduling_plan_revision",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_plan_revision_plan_factory",
        ),
    )
    for column in (
        "factory_id",
        "plan_id",
        "snapshot_sha256",
        "created_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_plan_revisions_{column}",
            "injection_scheduling_plan_revisions",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_plan_revision_factory_created",
        "injection_scheduling_plan_revisions",
        ["factory_id", "created_at"],
    )

    op.create_table(
        "injection_scheduling_published_snapshots",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("published_by", sa.String(64), nullable=False),
        sa.Column(
            "published_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_scheduling_published_snapshot_request",
        ),
        sa.UniqueConstraint(
            "plan_id",
            name="uq_injection_scheduling_published_snapshot_plan",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_published_snapshot_plan_factory",
        ),
    )
    for column in (
        "factory_id",
        "plan_id",
        "request_id",
        "snapshot_sha256",
        "published_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_published_snapshots_{column}",
            "injection_scheduling_published_snapshots",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_published_snapshot_factory_created",
        "injection_scheduling_published_snapshots",
        ["factory_id", "created_at"],
    )


def _create_audit_events() -> None:
    op.create_table(
        "injection_scheduling_audit_events",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("entity_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("id", name="uq_injection_scheduling_audit_event_id"),
    )
    for column in (
        "factory_id",
        "event_type",
        "entity_type",
        "entity_id",
        "request_id",
        "actor_user_id",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_audit_events_{column}",
            "injection_scheduling_audit_events",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_audit_factory_sequence",
        "injection_scheduling_audit_events",
        ["factory_id", "sequence"],
    )
    op.create_index(
        "ix_injection_scheduling_audit_entity",
        "injection_scheduling_audit_events",
        ["factory_id", "entity_type", "entity_id"],
    )


def _create_sqlite_guards() -> None:
    for table_name in APPEND_ONLY_TABLES:
        short_name = table_name.removeprefix("injection_scheduling_")
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_injection_scheduling_{short_name}_no_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_injection_scheduling_{short_name}_no_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
        )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_injection_scheduling_published_plan_no_delete
            BEFORE DELETE ON injection_scheduling_plans
            WHEN OLD.status IN ('PUBLISHED', 'ARCHIVED')
            BEGIN
                SELECT RAISE(ABORT, 'published scheduling plan is immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_injection_scheduling_published_plan_no_update
            BEFORE UPDATE ON injection_scheduling_plans
            WHEN OLD.status = 'ARCHIVED'
              OR (
                OLD.status = 'PUBLISHED'
                AND (
                    NEW.status NOT IN ('PUBLISHED', 'ARCHIVED')
                    OR NEW.factory_id IS NOT OLD.factory_id
                    OR NEW.business_date IS NOT OLD.business_date
                    OR NEW.revision IS NOT OLD.revision
                    OR NEW.rule_set_id IS NOT OLD.rule_set_id
                    OR NEW.rule_revision IS NOT OLD.rule_revision
                    OR NEW.based_on_plan_id IS NOT OLD.based_on_plan_id
                    OR NEW.rollback_request_id IS NOT OLD.rollback_request_id
                    OR NEW.created_by IS NOT OLD.created_by
                    OR NEW.created_by_name IS NOT OLD.created_by_name
                    OR NEW.created_at IS NOT OLD.created_at
                    OR NEW.published_by IS NOT OLD.published_by
                    OR NEW.published_by_name IS NOT OLD.published_by_name
                    OR NEW.published_at IS NOT OLD.published_at
                )
              )
            BEGIN
                SELECT RAISE(ABORT, 'published scheduling plan is immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_injection_scheduling_published_task_no_insert
            BEFORE INSERT ON injection_scheduling_tasks
            WHEN EXISTS (
                SELECT 1 FROM injection_scheduling_plans
                WHERE id = NEW.plan_id
                  AND factory_id = NEW.factory_id
                  AND status IN ('PUBLISHED', 'ARCHIVED')
            )
            BEGIN
                SELECT RAISE(ABORT, 'published scheduling task planning data is immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_injection_scheduling_published_task_no_delete
            BEFORE DELETE ON injection_scheduling_tasks
            WHEN EXISTS (
                SELECT 1 FROM injection_scheduling_plans
                WHERE id = OLD.plan_id
                  AND factory_id = OLD.factory_id
                  AND status IN ('PUBLISHED', 'ARCHIVED')
            )
            BEGIN
                SELECT RAISE(ABORT, 'published scheduling task planning data is immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_injection_scheduling_published_task_planning_no_update
            BEFORE UPDATE ON injection_scheduling_tasks
            WHEN EXISTS (
                SELECT 1 FROM injection_scheduling_plans
                WHERE id = OLD.plan_id
                  AND factory_id = OLD.factory_id
                  AND status IN ('PUBLISHED', 'ARCHIVED')
            )
            AND (
                NEW.factory_id IS NOT OLD.factory_id
                OR NEW.plan_id IS NOT OLD.plan_id
                OR NEW.machine_id IS NOT OLD.machine_id
                OR NEW.order_id IS NOT OLD.order_id
                OR NEW.mold_id IS NOT OLD.mold_id
                OR NEW.mold_copy_no IS NOT OLD.mold_copy_no
                OR NEW.sequence_no IS NOT OLD.sequence_no
                OR NEW.planned_start IS NOT OLD.planned_start
                OR NEW.planned_finish IS NOT OLD.planned_finish
                OR NEW.shift_target_quantity IS NOT OLD.shift_target_quantity
                OR NEW.locked IS NOT OLD.locked
                OR NEW.manual_override_reason IS NOT OLD.manual_override_reason
            )
            BEGIN
                SELECT RAISE(ABORT, 'published scheduling task planning data is immutable');
            END
            """
        )
    )


def _create_postgresql_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reject_injection_scheduling_phase3_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'injection scheduling execution record is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    for table_name in APPEND_ONLY_TABLES:
        short_name = table_name.removeprefix("injection_scheduling_")
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_injection_scheduling_{short_name}_immutable
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION
                reject_injection_scheduling_phase3_mutation();
                """
            )
        )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION guard_injection_scheduling_published_plan()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF OLD.status IN ('PUBLISHED', 'ARCHIVED') THEN
                        RAISE EXCEPTION 'published scheduling plan is immutable';
                    END IF;
                    RETURN OLD;
                END IF;
                IF OLD.status = 'ARCHIVED'
                   OR (
                       OLD.status = 'PUBLISHED'
                       AND (
                           NEW.status NOT IN ('PUBLISHED', 'ARCHIVED')
                           OR NEW.factory_id IS DISTINCT FROM OLD.factory_id
                           OR NEW.business_date IS DISTINCT FROM OLD.business_date
                           OR NEW.revision IS DISTINCT FROM OLD.revision
                           OR NEW.rule_set_id IS DISTINCT FROM OLD.rule_set_id
                           OR NEW.rule_revision IS DISTINCT FROM OLD.rule_revision
                           OR NEW.based_on_plan_id IS DISTINCT FROM OLD.based_on_plan_id
                           OR NEW.rollback_request_id IS DISTINCT FROM OLD.rollback_request_id
                           OR NEW.created_by IS DISTINCT FROM OLD.created_by
                           OR NEW.created_by_name IS DISTINCT FROM OLD.created_by_name
                           OR NEW.created_at IS DISTINCT FROM OLD.created_at
                           OR NEW.published_by IS DISTINCT FROM OLD.published_by
                           OR NEW.published_by_name IS DISTINCT FROM OLD.published_by_name
                           OR NEW.published_at IS DISTINCT FROM OLD.published_at
                       )
                   )
                THEN
                    RAISE EXCEPTION 'published scheduling plan is immutable';
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
            CREATE TRIGGER trg_injection_scheduling_published_plan_guard
            BEFORE UPDATE OR DELETE ON injection_scheduling_plans
            FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_published_plan();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION guard_injection_scheduling_published_task()
            RETURNS trigger AS $$
            DECLARE
                plan_status varchar(32);
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    SELECT status INTO plan_status
                    FROM injection_scheduling_plans
                    WHERE id = NEW.plan_id AND factory_id = NEW.factory_id;
                    IF plan_status IN ('PUBLISHED', 'ARCHIVED') THEN
                        RAISE EXCEPTION 'published scheduling task planning data is immutable';
                    END IF;
                    RETURN NEW;
                END IF;
                SELECT status INTO plan_status
                FROM injection_scheduling_plans
                WHERE id = OLD.plan_id AND factory_id = OLD.factory_id;
                IF plan_status IN ('PUBLISHED', 'ARCHIVED') THEN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION 'published scheduling task planning data is immutable';
                    END IF;
                    IF NEW.factory_id IS DISTINCT FROM OLD.factory_id
                       OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
                       OR NEW.machine_id IS DISTINCT FROM OLD.machine_id
                       OR NEW.order_id IS DISTINCT FROM OLD.order_id
                       OR NEW.mold_id IS DISTINCT FROM OLD.mold_id
                       OR NEW.mold_copy_no IS DISTINCT FROM OLD.mold_copy_no
                       OR NEW.sequence_no IS DISTINCT FROM OLD.sequence_no
                       OR NEW.planned_start IS DISTINCT FROM OLD.planned_start
                       OR NEW.planned_finish IS DISTINCT FROM OLD.planned_finish
                       OR NEW.shift_target_quantity IS DISTINCT FROM OLD.shift_target_quantity
                       OR NEW.locked IS DISTINCT FROM OLD.locked
                       OR NEW.manual_override_reason IS DISTINCT FROM OLD.manual_override_reason
                    THEN
                        RAISE EXCEPTION 'published scheduling task planning data is immutable';
                    END IF;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
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
            CREATE TRIGGER trg_injection_scheduling_published_task_guard
            BEFORE INSERT OR UPDATE OR DELETE ON injection_scheduling_tasks
            FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_published_task();
            """
        )
    )


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        _create_sqlite_guards()
    elif dialect == "postgresql":
        _create_postgresql_guards()


def upgrade() -> None:
    _create_orders()
    _create_plans()
    _create_tasks()
    _create_reports_and_snapshots()
    _create_audit_events()
    _create_guards()


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table_name in APPEND_ONLY_TABLES:
            short_name = table_name.removeprefix("injection_scheduling_")
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS "
                    f"trg_injection_scheduling_{short_name}_no_update"
                )
            )
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS "
                    f"trg_injection_scheduling_{short_name}_no_delete"
                )
            )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_task_no_insert"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_plan_no_delete"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_plan_no_update"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_task_no_delete"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_task_planning_no_update"
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_plan_guard "
                "ON injection_scheduling_plans"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS "
                "trg_injection_scheduling_published_task_guard "
                "ON injection_scheduling_tasks"
            )
        )
        for table_name in APPEND_ONLY_TABLES:
            short_name = table_name.removeprefix("injection_scheduling_")
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS "
                    f"trg_injection_scheduling_{short_name}_immutable "
                    f"ON {table_name}"
                )
            )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS guard_injection_scheduling_published_plan()"
            )
        )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS guard_injection_scheduling_published_task()"
            )
        )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS "
                "reject_injection_scheduling_phase3_mutation()"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    populated = {
        table_name: connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        for table_name in PHASE3_TABLES_CHILD_FIRST
    }
    if any(populated.values()):
        raise RuntimeError(
            "20260731_0044 cannot be downgraded after injection scheduling "
            "orders, plans, reports, snapshots, or audit events exist; "
            "back up the domain first."
        )
    _drop_guards()
    for table_name in PHASE3_TABLES_CHILD_FIRST:
        op.drop_table(table_name)
