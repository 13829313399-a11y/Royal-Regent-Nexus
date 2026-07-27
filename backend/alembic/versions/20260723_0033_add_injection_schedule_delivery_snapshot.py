"""add injection schedule delivery snapshot

Revision ID: 20260723_0033
Revises: 20260723_0032
Create Date: 2026-07-23 20:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0033"
down_revision: str | Sequence[str] | None = "20260723_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "delivery_due_date_snapshot",
            sa.String(20),
            nullable=False,
            server_default="",
        ),
    )
    op.execute(
        """
        UPDATE injection_schedule_tasks
        SET delivery_due_date_snapshot = COALESCE(
            (
                SELECT injection_order_masters.delivery_due_date
                FROM injection_order_masters
                WHERE injection_order_masters.id = injection_schedule_tasks.order_id
                  AND injection_order_masters.factory_id = injection_schedule_tasks.factory_id
            ),
            ''
        )
        """
    )


def downgrade() -> None:
    op.drop_column(
        "injection_schedule_tasks",
        "delivery_due_date_snapshot",
    )
