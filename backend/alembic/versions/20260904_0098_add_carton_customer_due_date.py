"""Add customer due dates and safety-lead snapshots to carton orders.

Revision ID: 20260904_0098
Revises: 20260904_0097
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260904_0098"
down_revision = "20260904_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "carton_orders",
        sa.Column("customer_due_date", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "carton_orders",
        sa.Column(
            "safety_lead_days",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.create_index(
        "ix_carton_orders_customer_due_date",
        "carton_orders",
        ["customer_due_date"],
    )
    op.create_index(
        "ix_carton_order_factory_customer_due_date",
        "carton_orders",
        ["factory_id", "customer_code", "customer_due_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_carton_order_factory_customer_due_date",
        table_name="carton_orders",
    )
    op.drop_index(
        "ix_carton_orders_customer_due_date",
        table_name="carton_orders",
    )
    op.drop_column("carton_orders", "safety_lead_days")
    op.drop_column("carton_orders", "customer_due_date")
