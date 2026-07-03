"""create molding sample notifications

Revision ID: 20260703_0002
Revises: 20260701_0001
Create Date: 2026-07-03 18:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260703_0002"
down_revision: Union[str, None] = "20260701_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "molding_sample_notifications",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("target_module", sa.String(length=96), nullable=False),
        sa.Column("target_role", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("read_at", sa.String(length=32), nullable=False),
        sa.Column("handled_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_notifications_event_type", "molding_sample_notifications", ["event_type"])
    op.create_index("ix_molding_sample_notifications_factory_id", "molding_sample_notifications", ["factory_id"])
    op.create_index("ix_molding_sample_notifications_order_id", "molding_sample_notifications", ["order_id"])
    op.create_index("ix_molding_sample_notifications_status", "molding_sample_notifications", ["status"])
    op.create_index("ix_molding_sample_notifications_target_module", "molding_sample_notifications", ["target_module"])
    op.create_index("ix_molding_sample_notifications_target_role", "molding_sample_notifications", ["target_role"])


def downgrade() -> None:
    op.drop_index("ix_molding_sample_notifications_target_role", table_name="molding_sample_notifications")
    op.drop_index("ix_molding_sample_notifications_target_module", table_name="molding_sample_notifications")
    op.drop_index("ix_molding_sample_notifications_status", table_name="molding_sample_notifications")
    op.drop_index("ix_molding_sample_notifications_order_id", table_name="molding_sample_notifications")
    op.drop_index("ix_molding_sample_notifications_factory_id", table_name="molding_sample_notifications")
    op.drop_index("ix_molding_sample_notifications_event_type", table_name="molding_sample_notifications")
    op.drop_table("molding_sample_notifications")
