"""remove injection scheduling module

Revision ID: 20260723_0031
Revises: 20260722_0030
Create Date: 2026-07-23 09:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0031"
down_revision: str | Sequence[str] | None = "20260722_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INJECTION_TABLES_CHILD_FIRST = (
    "injection_schedule_constraint_results",
    "injection_shift_outputs",
    "injection_machine_downtimes",
    "injection_schedule_audit_logs",
    "injection_schedule_assignments",
    "injection_schedule_versions",
    "injection_schedule_rules",
    "injection_order_tasks",
    "injection_mold_masters",
    "injection_machine_masters",
    "injection_schedule_import_diffs",
    "injection_schedule_import_issues",
    "injection_schedule_tasks",
    "injection_schedule_machines",
    "injection_schedule_import_batches",
)


def upgrade() -> None:
    connection = op.get_bind()
    permission_ids = sa.text(
        "SELECT id FROM auth_permissions WHERE code LIKE 'injection_schedule:%'"
    )
    for table_name in (
        "auth_user_permission_overrides",
        "auth_role_permissions",
        "auth_permission_metadata",
    ):
        connection.execute(
            sa.text(
                f"DELETE FROM {table_name} WHERE permission_id IN ({permission_ids.text})"
            )
        )
    connection.execute(
        sa.text("DELETE FROM auth_permissions WHERE code LIKE 'injection_schedule:%'")
    )
    connection.execute(
        sa.text(
            "DELETE FROM auth_iam_state "
            "WHERE key = 'legacy_read_compat_v1_completed'"
        )
    )

    for table_name in INJECTION_TABLES_CHILD_FIRST:
        op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20260723_0031 is irreversible because it intentionally removes the injection "
        "scheduling module and its data. "
        "Restore the pre-removal database backup instead of downgrading this revision."
    )
