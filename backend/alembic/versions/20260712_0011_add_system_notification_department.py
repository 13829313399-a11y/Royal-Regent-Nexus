"""add system notification department scope

Revision ID: 20260712_0011
Revises: 20260711_0010
Create Date: 2026-07-12 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0011"
down_revision: Union[str, None] = "20260711_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_notifications",
        sa.Column(
            "target_department",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_system_notifications_target_department",
        "system_notifications",
        ["target_department"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_system_notifications_target_department",
        table_name="system_notifications",
    )
    op.drop_column("system_notifications", "target_department")
