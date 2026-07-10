"""add molding sample mold metadata

Revision ID: 20260710_0008
Revises: 20260708_0007
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260710_0008"
down_revision: Union[str, None] = "20260708_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "molding_sample_items",
        sa.Column("mold_dimensions", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_items",
        sa.Column("mold_presence_status", sa.String(length=20), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("molding_sample_items", "mold_presence_status")
    op.drop_column("molding_sample_items", "mold_dimensions")
