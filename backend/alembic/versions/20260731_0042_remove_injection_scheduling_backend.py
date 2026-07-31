"""remove the injection scheduling backend before redesign

Revision ID: 20260731_0042
Revises: 20260729_0041
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260731_0042"
down_revision: str | Sequence[str] | None = "20260729_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INJECTION_SCHEDULING_TABLES_CHILD_FIRST = (
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
)


def _remove_permissions() -> None:
    connection = op.get_bind()
    permission_ids = sa.text(
        "SELECT id FROM auth_permissions "
        "WHERE code LIKE 'injection_scheduling:%'"
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
                f"WHERE permission_id IN ({permission_ids.text})"
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
            "WHERE key LIKE 'injection_scheduling%'"
        )
    )


def _remove_audit_immutability() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_update "
            "ON injection_scheduling_audit_events"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_delete "
            "ON injection_scheduling_audit_events"
        )
    elif connection.dialect.name == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_update"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_scheduling_audit_no_delete"
        )


def upgrade() -> None:
    connection = op.get_bind()
    _remove_permissions()
    _remove_audit_immutability()

    for table_name in INJECTION_SCHEDULING_TABLES_CHILD_FIRST:
        op.drop_table(table_name)

    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS reject_injection_scheduling_audit_mutation()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "20260731_0042 is irreversible because it intentionally removes the "
        "injection scheduling backend and its data. Restore a pre-removal "
        "database backup instead of downgrading this revision."
    )
