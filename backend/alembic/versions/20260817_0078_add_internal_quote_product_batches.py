"""add internal quote product batches

Revision ID: 20260817_0078
Revises: 20260814_0077
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0078"
down_revision: str | Sequence[str] | None = "20260814_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("internal_quotes") as batch_op:
        batch_op.add_column(
            sa.Column("quote_type", sa.String(length=32), nullable=False, server_default="single")
        )
        batch_op.add_column(
            sa.Column("batch_id", sa.String(length=96), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("batch_quote_no", sa.String(length=128), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("batch_position", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("baseline_quote_id", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("region_code", sa.String(length=32), nullable=False, server_default="")
        )
        batch_op.create_index("ix_internal_quotes_quote_type", ["quote_type"], unique=False)
        batch_op.create_index("ix_internal_quotes_batch_id", ["batch_id"], unique=False)
        batch_op.create_index("ix_internal_quotes_batch_quote_no", ["batch_quote_no"], unique=False)
        batch_op.create_index("ix_internal_quotes_batch_position", ["batch_position"], unique=False)
        batch_op.create_index("ix_internal_quotes_baseline_quote_id", ["baseline_quote_id"], unique=False)
        batch_op.create_index("ix_internal_quotes_region_code", ["region_code"], unique=False)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE internal_quotes
            SET batch_id = id,
                batch_quote_no = quote_no,
                baseline_quote_id = id
            WHERE batch_id = '' OR batch_quote_no = '' OR baseline_quote_id = ''
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("internal_quotes") as batch_op:
        batch_op.drop_index("ix_internal_quotes_region_code")
        batch_op.drop_index("ix_internal_quotes_baseline_quote_id")
        batch_op.drop_index("ix_internal_quotes_batch_position")
        batch_op.drop_index("ix_internal_quotes_batch_quote_no")
        batch_op.drop_index("ix_internal_quotes_batch_id")
        batch_op.drop_index("ix_internal_quotes_quote_type")
        batch_op.drop_column("region_code")
        batch_op.drop_column("baseline_quote_id")
        batch_op.drop_column("batch_size")
        batch_op.drop_column("batch_position")
        batch_op.drop_column("batch_quote_no")
        batch_op.drop_column("batch_id")
        batch_op.drop_column("quote_type")
