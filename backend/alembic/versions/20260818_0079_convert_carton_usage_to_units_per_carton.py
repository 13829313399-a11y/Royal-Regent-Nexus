"""convert carton line usage to units per carton

Revision ID: 20260818_0079
Revises: 20260817_0078
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0079"
down_revision: str | Sequence[str] | None = "20260817_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _convert(*, units_per_carton: bool) -> None:
    connection = op.get_bind()
    expression = (
        "1.0 * carton_orders.product_order_quantity / carton_order_lines.required_quantity"
        if units_per_carton
        else "1.0 * carton_order_lines.required_quantity / carton_orders.product_order_quantity"
    )
    connection.execute(
        sa.text(
            f"""
            UPDATE carton_order_lines
            SET usage_quantity = ROUND((
                SELECT {expression}
                FROM carton_orders
                WHERE carton_orders.id = carton_order_lines.order_id
                  AND carton_orders.factory_id = carton_order_lines.factory_id
            ), 8)
            WHERE carton_order_lines.required_quantity > 0
              AND EXISTS (
                  SELECT 1
                  FROM carton_orders
                  WHERE carton_orders.id = carton_order_lines.order_id
                    AND carton_orders.factory_id = carton_order_lines.factory_id
                    AND carton_orders.product_order_quantity > 0
              )
            """
        )
    )


def upgrade() -> None:
    # The compatibility column now stores units per carton. Keep the persisted
    # required quantity unchanged and derive the exact reciprocal from it.
    _convert(units_per_carton=True)


def downgrade() -> None:
    # Restore the legacy per-product usage semantics from the unchanged totals.
    _convert(units_per_carton=False)
