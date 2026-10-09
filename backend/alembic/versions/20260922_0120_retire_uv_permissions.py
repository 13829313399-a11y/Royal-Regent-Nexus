"""Retire removed workspace permissions without deleting business or audit history."""

from alembic import op
import sqlalchemy as sa

revision = "20260922_0120"
down_revision = "20260922_0119"
branch_labels = None
depends_on = None


def retire_permissions(connection):
    # Frozen exact codes: underscores must never act as SQL LIKE wildcards.
    codes = ", ".join("'uv_printing:" + action + "'" for action in (
        "read", "report", "quality", "master_write", "shift_write", "ink_write",
        "cost_read", "cost_write", "payroll_read", "payroll_write", "import", "export", "close",
    ))
    permission_ids = f"SELECT id FROM auth_permissions WHERE code IN ({codes})"
    role_ids = f"SELECT role_id FROM auth_role_permissions WHERE permission_id IN ({permission_ids})"
    user_ids = (
        f"SELECT user_id FROM auth_user_roles WHERE role_id IN ({role_ids}) UNION "
        f"SELECT user_id FROM auth_user_permission_overrides WHERE permission_id IN ({permission_ids})"
    )
    connection.execute(sa.text(
        "UPDATE auth_user_authorization_revisions SET revision = revision + 1, "
        f"updated_at = CURRENT_TIMESTAMP WHERE user_id IN ({user_ids})"
    ))
    connection.execute(sa.text(
        "UPDATE auth_role_metadata SET version = version + 1, "
        f"updated_at = CURRENT_TIMESTAMP WHERE role_id IN ({role_ids})"
    ))
    for table in ("auth_user_permission_overrides", "auth_role_permissions", "auth_permission_metadata"):
        connection.execute(sa.text(f"DELETE FROM {table} WHERE permission_id IN ({permission_ids})"))
    connection.execute(sa.text(f"DELETE FROM auth_permissions WHERE code IN ({codes})"))


def upgrade():
    retire_permissions(op.get_bind())


def downgrade():
    raise RuntimeError("Restore a verified backup to recover retired permission assignments.")
