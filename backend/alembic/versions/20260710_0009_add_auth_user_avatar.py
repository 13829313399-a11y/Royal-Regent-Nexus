"""add current user avatar

Revision ID: 20260710_0009
Revises: 20260710_0008
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260710_0009"
down_revision: Union[str, None] = "20260710_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("auth_users", sa.Column("avatar_png", sa.LargeBinary(), nullable=True))
    op.add_column(
        "auth_users",
        sa.Column("avatar_version", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("auth_users", "avatar_version")
    op.drop_column("auth_users", "avatar_png")
