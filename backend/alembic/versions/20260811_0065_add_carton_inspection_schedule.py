"""add carton inspection schedule reminder imports

Revision ID: 20260811_0065
Revises: 20260810_0064
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0065"
down_revision: str | Sequence[str] | None = "20260810_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("carton_import_batches") as batch_op:
        batch_op.add_column(
            sa.Column("import_profile", sa.String(255), nullable=False, server_default="")
        )
        batch_op.drop_constraint("uq_carton_import_factory_type_hash", type_="unique")
        batch_op.drop_constraint("ck_carton_import_type", type_="check")
        batch_op.create_unique_constraint(
            "uq_carton_import_factory_type_hash",
            ["factory_id", "import_type", "source_sha256", "import_profile"],
        )
        batch_op.create_check_constraint(
            "ck_carton_import_type",
            "import_type IN ('DELIVERY_NOTE', 'WEEKLY_SCHEDULE', 'INSPECTION_SCHEDULE')",
        )


def downgrade() -> None:
    with op.batch_alter_table("carton_import_batches") as batch_op:
        batch_op.drop_constraint("uq_carton_import_factory_type_hash", type_="unique")
        batch_op.drop_constraint("ck_carton_import_type", type_="check")
        batch_op.create_unique_constraint(
            "uq_carton_import_factory_type_hash",
            ["factory_id", "import_type", "source_sha256"],
        )
        batch_op.create_check_constraint(
            "ck_carton_import_type",
            "import_type IN ('DELIVERY_NOTE', 'WEEKLY_SCHEDULE')",
        )
        batch_op.drop_column("import_profile")
