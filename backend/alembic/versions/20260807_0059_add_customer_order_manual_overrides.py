"""add customer-order manual override audit evidence

Revision ID: 20260807_0059
Revises: 20260807_0058
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0059"
down_revision: str | Sequence[str] | None = "20260807_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customer_order_export_audits") as batch_op:
        batch_op.add_column(
            sa.Column("manual_overrides_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("manual_override_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_customer_order_export_audit_manual_override_count",
            "manual_override_count >= 0",
        )


def downgrade() -> None:
    connection = op.get_bind()
    override_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM customer_order_export_audits "
            "WHERE manual_override_count > 0"
        )
    ).scalar_one()
    if override_count:
        raise RuntimeError(
            "20260807_0059 cannot be downgraded after manual customer-order overrides exist; "
            "back up the audit evidence first"
        )
    with op.batch_alter_table("customer_order_export_audits") as batch_op:
        batch_op.drop_constraint(
            "ck_customer_order_export_audit_manual_override_count",
            type_="check",
        )
        batch_op.drop_column("manual_override_count")
        batch_op.drop_column("manual_overrides_json")
