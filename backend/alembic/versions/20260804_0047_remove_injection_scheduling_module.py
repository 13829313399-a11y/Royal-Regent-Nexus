"""remove the injection scheduling module before redesign

Revision ID: 20260804_0047
Revises: 20260802_0046
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0047"
down_revision: str | Sequence[str] | None = "20260802_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INJECTION_SCHEDULING_TABLES_CHILD_FIRST = (
    "injection_scheduling_import_issues",
    "injection_scheduling_shift_reports",
    "injection_scheduling_published_snapshots",
    "injection_scheduling_plan_revisions",
    "injection_scheduling_audit_events",
    "injection_scheduling_tasks",
    "injection_scheduling_plans",
    "injection_scheduling_orders",
    "injection_scheduling_rule_sets",
    "injection_scheduling_molds",
    "injection_scheduling_machines",
    "injection_scheduling_import_batches",
)


def _remove_permissions() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            UPDATE auth_access_requests
            SET status = 'rejected',
                decision_comment = '注塑排产模块已移除，相关权限申请自动关闭',
                decided_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'pending'
              AND id IN (
                  SELECT DISTINCT request_id
                  FROM auth_access_request_items
                  WHERE permission_id IN (
                      SELECT id
                      FROM auth_permissions
                      WHERE code LIKE 'injection_scheduling:%'
                  )
              )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE auth_role_metadata
            SET version = version + 1, updated_at = CURRENT_TIMESTAMP
            WHERE role_id IN (
                SELECT DISTINCT role_id
                FROM auth_role_permissions
                WHERE permission_id IN (
                    SELECT id
                    FROM auth_permissions
                    WHERE code LIKE 'injection_scheduling:%'
                )
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE auth_user_authorization_revisions
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id IN (
                SELECT DISTINCT user_id
                FROM auth_user_roles
                WHERE role_id IN (
                    SELECT DISTINCT role_id
                    FROM auth_role_permissions
                    WHERE permission_id IN (
                        SELECT id
                        FROM auth_permissions
                        WHERE code LIKE 'injection_scheduling:%'
                    )
                )
                UNION
                SELECT DISTINCT user_id
                FROM auth_user_permission_overrides
                WHERE permission_id IN (
                    SELECT id
                    FROM auth_permissions
                    WHERE code LIKE 'injection_scheduling:%'
                )
            )
            """
        )
    )

    for table_name in (
        "auth_user_permission_overrides",
        "auth_role_permissions",
        "auth_permission_metadata",
    ):
        connection.execute(
            sa.text(
                f"DELETE FROM {table_name} "
                "WHERE permission_id IN ("
                "SELECT id FROM auth_permissions "
                "WHERE code LIKE 'injection_scheduling:%'"
                ")"
            )
        )

    connection.execute(
        sa.text(
            "DELETE FROM auth_permissions "
            "WHERE code LIKE 'injection_scheduling:%'"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM auth_iam_state "
            "WHERE key LIKE 'injection_scheduling%' "
            "OR key LIKE 'injection_schedule%'"
        )
    )


def _drop_postgresql_guard_functions() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for function_name in (
        "guard_injection_scheduling_phase4_import",
        "guard_injection_scheduling_published_task_lineage",
        "guard_injection_scheduling_published_plan",
        "guard_injection_scheduling_published_task",
        "reject_injection_scheduling_phase3_mutation",
    ):
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function_name}()"))


def upgrade() -> None:
    _remove_permissions()
    for table_name in INJECTION_SCHEDULING_TABLES_CHILD_FIRST:
        op.drop_table(table_name)
    _drop_postgresql_guard_functions()


def downgrade() -> None:
    raise RuntimeError(
        "20260804_0047 is irreversible because it intentionally removes the "
        "injection scheduling module and its data. Restore a verified "
        "pre-removal database backup instead of downgrading this revision."
    )
