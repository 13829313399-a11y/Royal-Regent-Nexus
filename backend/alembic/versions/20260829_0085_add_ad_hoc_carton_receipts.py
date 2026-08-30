"""allow human-confirmed ad hoc carton receipt lines

Revision ID: 20260829_0085
Revises: 20260826_0084
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0085"
down_revision: str | Sequence[str] | None = "20260826_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("carton_receipt_lines", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(length=24),
                nullable=False,
                server_default="FORMAL_ORDER",
            )
        )
        batch_op.alter_column(
            "order_line_id",
            existing_type=sa.String(length=96),
            nullable=True,
        )
        batch_op.create_check_constraint(
            "ck_carton_receipt_line_source_type",
            "source_type IN ('FORMAL_ORDER', 'AD_HOC')",
        )
        batch_op.create_index(
            "ix_carton_receipt_lines_source_type",
            ["source_type"],
            unique=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    ad_hoc_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM carton_receipt_lines "
            "WHERE source_type = 'AD_HOC' OR order_line_id IS NULL"
        )
    )
    if ad_hoc_count:
        raise RuntimeError(
            "cannot downgrade while ad hoc carton receipt lines exist; "
            "archive or migrate those business records first"
        )
    with op.batch_alter_table("carton_receipt_lines", recreate="always") as batch_op:
        batch_op.drop_index("ix_carton_receipt_lines_source_type")
        batch_op.drop_constraint("ck_carton_receipt_line_source_type", type_="check")
        batch_op.alter_column(
            "order_line_id",
            existing_type=sa.String(length=96),
            nullable=False,
        )
        batch_op.drop_column("source_type")
