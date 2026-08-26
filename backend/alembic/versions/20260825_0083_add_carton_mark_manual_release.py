"""add audited manual release fields to carton-mark templates

Revision ID: 20260825_0083
Revises: 20260824_0082
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError

revision: str = "20260825_0083"
down_revision: str | Sequence[str] | None = "20260824_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "carton_mark_templates",
        sa.Column("manual_release_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "carton_mark_templates",
        sa.Column("manual_release_source_status", sa.String(16), nullable=False, server_default=""),
    )
    op.add_column(
        "carton_mark_templates",
        sa.Column("manual_released_by", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "carton_mark_templates",
        sa.Column("manual_released_by_name", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "carton_mark_templates",
        sa.Column("manual_released_at", sa.String(40), nullable=False, server_default=""),
    )


def downgrade() -> None:
    if context.is_offline_mode():
        raise CommandError("箱唛人工放行迁移不支持离线降级")

    bind = op.get_bind()
    released_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM carton_mark_templates "
            "WHERE manual_released_at <> '' OR manual_release_reason <> ''"
        )
    ).scalar_one()
    if released_count:
        raise CommandError("存在箱唛人工放行审计数据，拒绝降级以避免丢失审批证据")

    op.drop_column("carton_mark_templates", "manual_released_at")
    op.drop_column("carton_mark_templates", "manual_released_by_name")
    op.drop_column("carton_mark_templates", "manual_released_by")
    op.drop_column("carton_mark_templates", "manual_release_source_status")
    op.drop_column("carton_mark_templates", "manual_release_reason")
