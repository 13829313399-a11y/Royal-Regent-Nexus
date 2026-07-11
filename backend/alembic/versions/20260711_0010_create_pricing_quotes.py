"""create internal pricing quotes

Revision ID: 20260711_0010
Revises: 20260710_0009
Create Date: 2026-07-11 23:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260711_0010"
down_revision: Union[str, None] = "20260710_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_quotes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=128), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_quotes_factory_id", "pricing_quotes", ["factory_id"])
    op.create_index("ix_pricing_quotes_customer_id", "pricing_quotes", ["customer_id"])
    op.create_index("ix_pricing_quotes_status", "pricing_quotes", ["status"])
    op.create_index("ix_pricing_quotes_created_by", "pricing_quotes", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_pricing_quotes_created_by", table_name="pricing_quotes")
    op.drop_index("ix_pricing_quotes_status", table_name="pricing_quotes")
    op.drop_index("ix_pricing_quotes_customer_id", table_name="pricing_quotes")
    op.drop_index("ix_pricing_quotes_factory_id", table_name="pricing_quotes")
    op.drop_table("pricing_quotes")
