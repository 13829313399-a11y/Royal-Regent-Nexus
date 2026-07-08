"""create injection schedule schema

Revision ID: 20260708_0006
Revises: 20260706_0005
Create Date: 2026-07-08 17:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260708_0006"
down_revision: Union[str, None] = "20260706_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "injection_schedule_import_batches",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("business_date", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_injection_schedule_import_batches_factory_id",
        "injection_schedule_import_batches",
        ["factory_id"],
    )
    op.create_index(
        "ix_injection_schedule_import_batches_status",
        "injection_schedule_import_batches",
        ["status"],
    )

    op.create_table(
        "injection_schedule_machines",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("machine_code", sa.String(length=64), nullable=False),
        sa.Column("workshop", sa.String(length=64), nullable=False),
        sa.Column("machine_spec_label", sa.String(length=128), nullable=False),
        sa.Column("machine_process_type", sa.String(length=64), nullable=False),
        sa.Column("robot_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("constraints_json", sa.Text(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["injection_schedule_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_injection_schedule_machines_batch_id", "injection_schedule_machines", ["batch_id"])
    op.create_index("ix_injection_schedule_machines_factory_id", "injection_schedule_machines", ["factory_id"])
    op.create_index(
        "ix_injection_schedule_machines_machine_code",
        "injection_schedule_machines",
        ["machine_code"],
    )

    op.create_table(
        "injection_schedule_tasks",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("assigned_machine_code", sa.String(length=64), nullable=False),
        sa.Column("task_bucket", sa.String(length=32), nullable=False),
        sa.Column("mold_code", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("order_no", sa.String(length=128), nullable=False),
        sa.Column("product_code", sa.String(length=128), nullable=False),
        sa.Column("machine_model", sa.String(length=128), nullable=False),
        sa.Column("color", sa.String(length=128), nullable=False),
        sa.Column("pigment", sa.String(length=128), nullable=False),
        sa.Column("material", sa.String(length=128), nullable=False),
        sa.Column("order_qty", sa.Float(), nullable=True),
        sa.Column("produced_qty", sa.Float(), nullable=True),
        sa.Column("shortage_qty", sa.Float(), nullable=True),
        sa.Column("daily_target_qty", sa.Float(), nullable=True),
        sa.Column("delivery_due_date", sa.String(length=32), nullable=False),
        sa.Column("plan_start_at", sa.String(length=32), nullable=False),
        sa.Column("plan_finish_at", sa.String(length=32), nullable=False),
        sa.Column("warehouse_due_at", sa.String(length=32), nullable=False),
        sa.Column("delivery_gap_days", sa.Float(), nullable=True),
        sa.Column("priority_flag", sa.String(length=32), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("source_values_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["injection_schedule_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_injection_schedule_tasks_batch_id", "injection_schedule_tasks", ["batch_id"])
    op.create_index("ix_injection_schedule_tasks_factory_id", "injection_schedule_tasks", ["factory_id"])
    op.create_index(
        "ix_injection_schedule_tasks_assigned_machine_code",
        "injection_schedule_tasks",
        ["assigned_machine_code"],
    )
    op.create_index("ix_injection_schedule_tasks_source_row", "injection_schedule_tasks", ["source_row"])
    op.create_index("ix_injection_schedule_tasks_task_bucket", "injection_schedule_tasks", ["task_bucket"])

    op.create_table(
        "injection_schedule_import_issues",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["injection_schedule_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_injection_schedule_import_issues_batch_id",
        "injection_schedule_import_issues",
        ["batch_id"],
    )
    op.create_index(
        "ix_injection_schedule_import_issues_issue_type",
        "injection_schedule_import_issues",
        ["issue_type"],
    )
    op.create_index(
        "ix_injection_schedule_import_issues_source_row",
        "injection_schedule_import_issues",
        ["source_row"],
    )


def downgrade() -> None:
    op.drop_index("ix_injection_schedule_import_issues_source_row", table_name="injection_schedule_import_issues")
    op.drop_index("ix_injection_schedule_import_issues_issue_type", table_name="injection_schedule_import_issues")
    op.drop_index("ix_injection_schedule_import_issues_batch_id", table_name="injection_schedule_import_issues")
    op.drop_table("injection_schedule_import_issues")

    op.drop_index("ix_injection_schedule_tasks_task_bucket", table_name="injection_schedule_tasks")
    op.drop_index("ix_injection_schedule_tasks_source_row", table_name="injection_schedule_tasks")
    op.drop_index("ix_injection_schedule_tasks_assigned_machine_code", table_name="injection_schedule_tasks")
    op.drop_index("ix_injection_schedule_tasks_factory_id", table_name="injection_schedule_tasks")
    op.drop_index("ix_injection_schedule_tasks_batch_id", table_name="injection_schedule_tasks")
    op.drop_table("injection_schedule_tasks")

    op.drop_index("ix_injection_schedule_machines_machine_code", table_name="injection_schedule_machines")
    op.drop_index("ix_injection_schedule_machines_factory_id", table_name="injection_schedule_machines")
    op.drop_index("ix_injection_schedule_machines_batch_id", table_name="injection_schedule_machines")
    op.drop_table("injection_schedule_machines")

    op.drop_index("ix_injection_schedule_import_batches_status", table_name="injection_schedule_import_batches")
    op.drop_index("ix_injection_schedule_import_batches_factory_id", table_name="injection_schedule_import_batches")
    op.drop_table("injection_schedule_import_batches")
