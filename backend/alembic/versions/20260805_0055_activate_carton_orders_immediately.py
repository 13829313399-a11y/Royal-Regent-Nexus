"""activate carton orders immediately

Revision ID: 20260805_0055
Revises: 20260805_0054
Create Date: 2026-08-05
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0055"
down_revision: str | Sequence[str] | None = "20260805_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    op.get_bind().execute(
        sa.text(
            "UPDATE carton_orders "
            "SET status = 'CONFIRMED', revision = revision + 1, "
            "updated_by = 'migration', updated_by_name = '数据库升级', updated_at = :updated_at "
            "WHERE status = 'PENDING_SUPPLIER'"
        ),
        {"updated_at": timestamp},
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260805_0055 cannot restore removed supplier confirmation state; "
        "restore a verified pre-upgrade database backup instead"
    )
