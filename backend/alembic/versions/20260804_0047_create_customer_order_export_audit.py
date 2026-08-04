"""create immutable customer-order export audit evidence

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


def upgrade() -> None:
    op.create_table(
        "customer_order_export_audits",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("actor_user_id", sa.String(64), nullable=True),
        sa.Column("actor_username", sa.String(64), nullable=False, server_default=""),
        sa.Column("actor_display_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("received_date", sa.String(32), nullable=False, server_default=""),
        sa.Column("preview_schema_version", sa.String(96), nullable=False, server_default=""),
        sa.Column("preview_fingerprint", sa.String(64), nullable=False),
        sa.Column("po_file_names_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_po_sha256s_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("schedule_file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_schedule_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("output_file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("output_template", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_issue_keys_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("confirmed_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmation_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "confirmed_issue_count >= 0",
            name="ck_customer_order_export_audit_confirmed_issue_count",
        ),
    )
    for column in (
        "actor_user_id",
        "actor_username",
        "factory_id",
        "customer_code",
        "received_date",
        "preview_fingerprint",
        "source_schedule_sha256",
        "output_sha256",
        "created_at",
    ):
        op.create_index(
            f"ix_customer_order_export_audits_{column}",
            "customer_order_export_audits",
            [column],
        )
    op.create_index(
        "ix_customer_order_export_audits_factory_created",
        "customer_order_export_audits",
        ["factory_id", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    audit_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM customer_order_export_audits")
    ).scalar_one()
    if audit_count:
        raise RuntimeError(
            "20260804_0047 cannot be downgraded after customer-order export audits exist; "
            "back up the audit evidence first"
        )
    op.drop_table("customer_order_export_audits")
