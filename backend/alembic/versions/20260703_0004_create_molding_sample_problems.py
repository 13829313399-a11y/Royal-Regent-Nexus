"""create molding sample problems

Revision ID: 20260703_0004
Revises: 20260703_0003
Create Date: 2026-07-03 23:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260703_0004"
down_revision: Union[str, None] = "20260703_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "molding_sample_problems",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("order_number", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_problems_factory_id", "molding_sample_problems", ["factory_id"])
    op.create_index("ix_molding_sample_problems_order_id", "molding_sample_problems", ["order_id"])
    op.create_index("ix_molding_sample_problems_order_type", "molding_sample_problems", ["order_type"])
    op.create_index("ix_molding_sample_problems_status", "molding_sample_problems", ["status"])


def downgrade() -> None:
    op.drop_index("ix_molding_sample_problems_status", table_name="molding_sample_problems")
    op.drop_index("ix_molding_sample_problems_order_type", table_name="molding_sample_problems")
    op.drop_index("ix_molding_sample_problems_order_id", table_name="molding_sample_problems")
    op.drop_index("ix_molding_sample_problems_factory_id", table_name="molding_sample_problems")
    op.drop_table("molding_sample_problems")
