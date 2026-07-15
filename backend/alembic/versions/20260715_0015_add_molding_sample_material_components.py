"""add molding sample material components

Revision ID: 20260715_0015
Revises: 20260714_0014
Create Date: 2026-07-15 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0015"
down_revision: Union[str, None] = "20260714_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "molding_sample_items",
        sa.Column("material_components", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "molding_sample_items",
        sa.Column("material_usage_type", sa.String(length=20), server_default="production", nullable=False),
    )
    op.add_column(
        "molding_sample_items",
        sa.Column("actual_material_cost_components", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("molding_sample_items", "actual_material_cost_components")
    op.drop_column("molding_sample_items", "material_usage_type")
    op.drop_column("molding_sample_items", "material_components")
