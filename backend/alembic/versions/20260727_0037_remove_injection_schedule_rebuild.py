"""remove the rebuilt injection scheduling module

Revision ID: 20260727_0037
Revises: 20260727_0036
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260727_0037"
down_revision: str | Sequence[str] | None = "20260727_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INJECTION_TABLES_CHILD_FIRST = (
    "injection_schedule_actual_corrections",
    "injection_schedule_shift_actuals",
    "injection_schedule_replan_runs",
    "injection_schedule_validation_items",
    "injection_schedule_validation_runs",
    "injection_schedule_audit_events",
    "injection_schedule_tasks",
    "injection_schedule_factory_states",
    "injection_schedule_versions",
    "injection_schedule_import_issues",
    "injection_schedule_rule_configs",
    "injection_order_masters",
    "injection_mold_masters",
    "injection_machine_masters",
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
            "WHERE key LIKE 'injection_schedule%'"
        )
    )

    for table_name in INJECTION_TABLES_CHILD_FIRST:
        op.drop_table(table_name)

    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS reject_injection_schedule_audit_mutation()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "20260727_0037 is irreversible because it intentionally removes the rebuilt "
        "injection scheduling module and its data. Restore a pre-removal database "
        "backup instead of downgrading this revision."
    )
