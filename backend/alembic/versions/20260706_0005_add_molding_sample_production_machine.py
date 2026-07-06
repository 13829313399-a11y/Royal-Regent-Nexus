"""add molding sample production machine

Revision ID: 20260706_0005
Revises: 20260703_0004
Create Date: 2026-07-06 19:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260706_0005"
down_revision: Union[str, None] = "20260703_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "molding_sample_items",
        sa.Column("production_machine", sa.String(length=128), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("molding_sample_items", "production_machine")
