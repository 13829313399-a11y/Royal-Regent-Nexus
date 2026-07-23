"""add freight defaults to internal quote pricing baseline

Revision ID: 20260723_0030
Revises: 20260721_0029
Create Date: 2026-07-23 09:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0030"
down_revision: Union[str, None] = "20260721_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "internal_quote_pricing_baselines",
        sa.Column(
            "freight_routes_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("internal_quote_pricing_baselines", "freight_routes_json")
