"""create molding sample trial reports

Revision ID: 20260714_0014
Revises: 20260714_0013
Create Date: 2026-07-14 15:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0014"
down_revision: Union[str, None] = "20260714_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "molding_sample_trial_reports",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["molding_sample_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "item_id", name="uq_molding_sample_trial_report_order_item"),
    )
    op.create_index("ix_molding_sample_trial_reports_factory_id", "molding_sample_trial_reports", ["factory_id"])
    op.create_index("ix_molding_sample_trial_reports_order_id", "molding_sample_trial_reports", ["order_id"])
    op.create_index("ix_molding_sample_trial_reports_item_id", "molding_sample_trial_reports", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_molding_sample_trial_reports_item_id", table_name="molding_sample_trial_reports")
    op.drop_index("ix_molding_sample_trial_reports_order_id", table_name="molding_sample_trial_reports")
    op.drop_index("ix_molding_sample_trial_reports_factory_id", table_name="molding_sample_trial_reports")
    op.drop_table("molding_sample_trial_reports")
