"""create the new injection scheduling backend contract

Revision ID: 20260728_0039
Revises: 20260727_0038
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0039"
down_revision: str | Sequence[str] | None = "20260727_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "injection_scheduling:read",
        "查看注塑排程",
        "查看授权厂区的排程草案与已发布快照",
        "read",
    ),
    (
        "injection_scheduling:import",
        "导入注塑计划表",
        "预览并确认授权厂区的注塑计划表导入",
        "operate",
    ),
    (
        "injection_scheduling:edit",
        "调整注塑排程草案",
        "在授权厂区校验、锁定和调整排程草案",
        "operate",
    ),
    (
        "injection_scheduling:publish",
        "发布注塑排程",
        "发布授权厂区的不可变排程快照",
        "operate",
    ),
    (
        "injection_scheduling:rollback",
        "回滚注塑排程",
        "从授权厂区的历史发布快照创建新草案",
        "operate",
    ),
)

CLERK_ROLE_IDS = (
    "position_production_clerk",
    "position_molding_clerk",
    "molding_clerk",
)
SUPERVISOR_ROLE_IDS = (
    "position_general_manager",
    "position_production_manager",
    "position_production_supervisor",
    "position_molding_manager",
    "position_molding_supervisor",
    "molding_supervisor",
    "manager",
    "admin",
)


def _create_tables() -> None:
    op.create_table(
        "injection_scheduling_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("preview_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="preview"),
        sa.Column("normalized_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("confirm_reason", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_import_batch_id_factory",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "business_date",
            "preview_revision",
            name="uq_injection_scheduling_import_preview_revision",
        ),
    )
    op.create_index(
        "ix_injection_scheduling_import_batches_factory_id",
        "injection_scheduling_import_batches",
        ["factory_id"],
    )
    op.create_index(
        "ix_injection_scheduling_import_batches_business_date",
        "injection_scheduling_import_batches",
        ["business_date"],
    )
    op.create_index(
        "ix_injection_scheduling_import_batches_status",
        "injection_scheduling_import_batches",
        ["status"],
    )
    op.create_index(
        "ix_injection_scheduling_import_source",
        "injection_scheduling_import_batches",
        ["factory_id", "source_sha256", "business_date"],
    )

    op.create_table(
        "injection_scheduling_import_issues",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("field", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_issue_batch_factory",
            ondelete="CASCADE",
        ),
    )
    for column in ("batch_id", "factory_id", "severity", "code"):
        op.create_index(
            f"ix_injection_scheduling_import_issues_{column}",
            "injection_scheduling_import_issues",
            [column],
        )

    op.create_table(
        "injection_scheduling_machines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("machine_name", sa.String(128), nullable=False),
        sa.Column("workshop", sa.String(128), nullable=False, server_default=""),
        sa.Column("state", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("machine_class", sa.String(32), nullable=False, server_default=""),
        sa.Column("tonnage", sa.Integer(), nullable=True),
        sa.Column("injection_capacity_g", sa.String(32), nullable=False, server_default=""),
        sa.Column("safety_utilization", sa.String(16), nullable=False, server_default="0.82"),
        sa.Column("mold_width_mm", sa.String(32), nullable=False, server_default=""),
        sa.Column("mold_height_mm", sa.String(32), nullable=False, server_default=""),
        sa.Column("robot_level", sa.String(32), nullable=False, server_default="none"),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("restrictions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "completeness",
            sa.String(32),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column(
            "source_batch_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column("source_lineage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_scheduling_machine_factory_code",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_machine_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_machine_batch_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "factory_id",
        "machine_code",
        "state",
        "machine_class",
        "completeness",
        "source_batch_id",
    ):
        op.create_index(
            f"ix_injection_scheduling_machines_{column}",
            "injection_scheduling_machines",
            [column],
        )

    op.create_table(
        "injection_scheduling_molds",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_no", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
        sa.Column(
            "machine_class_requirement",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("length_mm", sa.String(32), nullable=False, server_default=""),
        sa.Column("width_mm", sa.String(32), nullable=False, server_default=""),
        sa.Column("thickness_mm", sa.String(32), nullable=False, server_default=""),
        sa.Column("shot_weight_g", sa.String(32), nullable=False, server_default=""),
        sa.Column("material", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "robot_requirement",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "core_pull_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "unscrew_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("attributes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "completeness",
            sa.String(32),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column(
            "source_batch_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column("source_lineage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "mold_no",
            name="uq_injection_scheduling_mold_factory_no",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_mold_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_mold_batch_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "factory_id",
        "mold_no",
        "status",
        "completeness",
        "source_batch_id",
    ):
        op.create_index(
            f"ix_injection_scheduling_molds_{column}",
            "injection_scheduling_molds",
            [column],
        )

    op.create_table(
        "injection_scheduling_orders",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("natural_key", sa.String(255), nullable=False),
        sa.Column("order_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("mold_id", sa.String(96), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("order_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_target", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material", sa.String(128), nullable=False, server_default=""),
        sa.Column("color", sa.String(128), nullable=False, server_default=""),
        sa.Column("delivery_due_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("priority_code", sa.String(8), nullable=False, server_default="P2"),
        sa.Column("priority_flag", sa.String(128), nullable=False, server_default=""),
        sa.Column("requirement_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "completeness",
            sa.String(32),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column(
            "source_batch_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column("source_lineage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "natural_key",
            name="uq_injection_scheduling_order_factory_key",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_order_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            [
                "injection_scheduling_molds.id",
                "injection_scheduling_molds.factory_id",
            ],
            name="fk_injection_scheduling_order_mold_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_order_batch_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "factory_id",
        "natural_key",
        "order_no",
        "item_no",
        "mold_id",
        "delivery_due_at",
        "priority_code",
        "completeness",
        "source_batch_id",
    ):
        op.create_index(
            f"ix_injection_scheduling_orders_{column}",
            "injection_scheduling_orders",
            [column],
        )

    op.create_table(
        "injection_scheduling_rule_sets",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("superseded_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "factory_id",
            "revision",
            name="uq_injection_scheduling_rule_factory_revision",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_rule_id_factory",
        ),
    )
    for column in ("factory_id", "status", "created_by"):
        op.create_index(
            f"ix_injection_scheduling_rule_sets_{column}",
            "injection_scheduling_rule_sets",
            [column],
        )

    op.create_table(
        "injection_scheduling_plans",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("published_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anchor_at", sa.String(32), nullable=False),
        sa.Column(
            "rule_set_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column(
            "source_batch_id",
            sa.String(96),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_plan_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id", "factory_id"],
            [
                "injection_scheduling_rule_sets.id",
                "injection_scheduling_rule_sets.factory_id",
            ],
            name="fk_injection_scheduling_plan_rule_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_plan_batch_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "factory_id",
        "status",
        "is_current",
        "rule_set_id",
        "source_batch_id",
        "created_by",
        "updated_by",
        "updated_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_plans_{column}",
            "injection_scheduling_plans",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_current_plan",
        "injection_scheduling_plans",
        ["factory_id", "is_current"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "injection_scheduling_plan_revisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "plan_id",
            "revision",
            name="uq_injection_scheduling_plan_revision",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_revision_plan_factory",
            ondelete="CASCADE",
        ),
    )
    for column in (
        "plan_id",
        "factory_id",
        "status",
        "snapshot_sha256",
        "created_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_plan_revisions_{column}",
            "injection_scheduling_plan_revisions",
            [column],
        )

    op.create_table(
        "injection_scheduling_tasks",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("planned_start", sa.String(32), nullable=False, server_default=""),
        sa.Column("planned_end", sa.String(32), nullable=False, server_default=""),
        sa.Column("risk", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("task_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "plan_id",
            "machine_id",
            "sequence",
            name="uq_injection_scheduling_task_lane_sequence",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_task_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_task_plan_factory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_task_machine_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_task_order_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "plan_id",
        "factory_id",
        "machine_id",
        "order_id",
        "is_current",
        "locked",
        "risk",
    ):
        op.create_index(
            f"ix_injection_scheduling_tasks_{column}",
            "injection_scheduling_tasks",
            [column],
        )

    op.create_table(
        "injection_scheduling_published_snapshots",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "rollback_of_snapshot_id",
            sa.String(128),
            nullable=True,
        ),
        sa.Column("published_by", sa.String(64), nullable=False),
        sa.Column("published_by_name", sa.String(128), nullable=False),
        sa.Column("published_at", sa.String(32), nullable=False),
        sa.Column("superseded_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "factory_id",
            "version",
            name="uq_injection_scheduling_publish_factory_version",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_publish_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_publish_plan_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_of_snapshot_id", "factory_id"],
            [
                "injection_scheduling_published_snapshots.id",
                "injection_scheduling_published_snapshots.factory_id",
            ],
            name="fk_injection_scheduling_publish_rollback_factory",
            ondelete="RESTRICT",
        ),
    )
    for column in (
        "plan_id",
        "factory_id",
        "snapshot_sha256",
        "is_current",
        "rollback_of_snapshot_id",
        "published_by",
        "published_at",
    ):
        op.create_index(
            (
                "ix_inj_sched_publish_rollback"
                if column == "rollback_of_snapshot_id"
                else f"ix_injection_scheduling_published_snapshots_{column}"
            ),
            "injection_scheduling_published_snapshots",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_publish_current",
        "injection_scheduling_published_snapshots",
        ["factory_id", "is_current"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "injection_scheduling_audit_events",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("old_revision", sa.Integer(), nullable=True),
        sa.Column("new_revision", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
    )
    for column in (
        "factory_id",
        "plan_id",
        "action",
        "actor_id",
        "request_id",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_audit_events_{column}",
            "injection_scheduling_audit_events",
            [column],
        )


def _seed_permissions() -> None:
    connection = op.get_bind()
    timestamp = "2026-07-28 00:00:00"
    for sort_offset, (code, name, description, access_kind) in enumerate(PERMISSIONS):
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permissions (id, code, name, description)
                SELECT :id, :code, :name, :description
                WHERE NOT EXISTS (
                    SELECT 1 FROM auth_permissions WHERE code = :code
                )
                """
            ),
            {
                "id": permission_id,
                "code": code,
                "name": name,
                "description": description,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permission_metadata (
                    permission_id, module_code, action, risk_level,
                    access_kind, scope_type, status, sort_order,
                    created_at, updated_at
                )
                SELECT
                    permission.id,
                    'injection_scheduling',
                    :action,
                    :risk_level,
                    :access_kind,
                    'factory_department',
                    'active',
                    :sort_order,
                    :timestamp,
                    :timestamp
                FROM auth_permissions permission
                WHERE permission.code = :code
                  AND NOT EXISTS (
                      SELECT 1
                      FROM auth_permission_metadata metadata
                      WHERE metadata.permission_id = permission.id
                  )
                """
            ),
            {
                "code": code,
                "action": code.partition(":")[2],
                "risk_level": (
                    "high"
                    if code.endswith((":publish", ":rollback", ":import"))
                    else "normal"
                ),
                "access_kind": access_kind,
                "sort_order": 800 + sort_offset,
                "timestamp": timestamp,
            },
        )

        role_ids = (
            (*CLERK_ROLE_IDS, *SUPERVISOR_ROLE_IDS)
            if code.endswith((":read", ":import", ":edit"))
            else SUPERVISOR_ROLE_IDS
        )
        for role_id in role_ids:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO auth_role_permissions (id, role_id, permission_id)
                    SELECT
                        :binding_id,
                        role.id,
                        permission.id
                    FROM auth_roles role
                    JOIN auth_permissions permission ON permission.code = :code
                    WHERE role.id = :role_id
                      AND NOT EXISTS (
                          SELECT 1
                          FROM auth_role_permissions binding
                          WHERE binding.role_id = role.id
                            AND binding.permission_id = permission.id
                      )
                    """
                ),
                {
                    "binding_id": f"{role_id}:{permission_id}",
                    "role_id": role_id,
                    "code": code,
                },
            )

    affected_roles = tuple(dict.fromkeys((*CLERK_ROLE_IDS, *SUPERVISOR_ROLE_IDS)))
    for role_id in affected_roles:
        connection.execute(
            sa.text(
                """
                UPDATE auth_role_metadata
                SET version = version + 1, updated_at = :timestamp
                WHERE role_id = :role_id
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )
        connection.execute(
            sa.text(
                """
                UPDATE auth_user_authorization_revisions
                SET revision = revision + 1, updated_at = :timestamp
                WHERE user_id IN (
                    SELECT user_id
                    FROM auth_user_roles
                    WHERE role_id = :role_id
                )
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )


def _install_audit_immutability() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_injection_scheduling_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'injection scheduling audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_scheduling_audit_no_update
            BEFORE UPDATE ON injection_scheduling_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_injection_scheduling_audit_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_scheduling_audit_no_delete
            BEFORE DELETE ON injection_scheduling_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_injection_scheduling_audit_mutation()
            """
        )
    elif connection.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_injection_scheduling_audit_no_update
            BEFORE UPDATE ON injection_scheduling_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'injection scheduling audit events are immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_scheduling_audit_no_delete
            BEFORE DELETE ON injection_scheduling_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'injection scheduling audit events are immutable');
            END
            """
        )


def upgrade() -> None:
    _create_tables()
    _seed_permissions()
    _install_audit_immutability()


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM injection_scheduling_import_batches
            LIMIT 1
            """
        )
    ).first()
    if populated is not None:
        raise RuntimeError(
            "20260728_0039 cannot be downgraded after injection scheduling "
            "imports exist; export or back up the new domain first."
        )

    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_update "
            "ON injection_scheduling_audit_events"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_delete "
            "ON injection_scheduling_audit_events"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS reject_injection_scheduling_audit_mutation()"
        )
    elif connection.dialect.name == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_update"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_delete"
        )

    for table_name in (
        "injection_scheduling_audit_events",
        "injection_scheduling_published_snapshots",
        "injection_scheduling_tasks",
        "injection_scheduling_plan_revisions",
        "injection_scheduling_plans",
        "injection_scheduling_rule_sets",
        "injection_scheduling_orders",
        "injection_scheduling_molds",
        "injection_scheduling_machines",
        "injection_scheduling_import_issues",
        "injection_scheduling_import_batches",
    ):
        op.drop_table(table_name)

    permission_ids = sa.text(
        "SELECT id FROM auth_permissions "
        "WHERE code LIKE 'injection_scheduling:%'"
    )
    for table_name in (
        "auth_user_permission_overrides",
        "auth_role_permissions",
        "auth_permission_metadata",
    ):
        connection.execute(
            sa.text(
                f"DELETE FROM {table_name} "
                f"WHERE permission_id IN ({permission_ids.text})"
            )
        )
    connection.execute(
        sa.text(
            "DELETE FROM auth_permissions "
            "WHERE code LIKE 'injection_scheduling:%'"
        )
    )
