"""add internal quote target customer price

Revision ID: 20260718_0025
Revises: 20260717_0024
Create Date: 2026-07-18 10:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260718_0025"
down_revision: Union[str, None] = "20260717_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "internal_quotes",
        sa.Column(
            "target_customer_price",
            sa.String(length=128),
            nullable=False,
            server_default="无",
        ),
    )


def downgrade() -> None:
    op.drop_column("internal_quotes", "target_customer_price")
