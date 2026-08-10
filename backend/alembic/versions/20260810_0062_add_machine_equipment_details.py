"""add editable machine equipment details and remarks

Revision ID: 20260810_0062
Revises: 20260810_0061
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0062"
down_revision: str | Sequence[str] | None = "20260810_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(connection).get_columns("injection_scheduling_machines")
    }
    with op.batch_alter_table("injection_scheduling_machines") as batch_op:
        if "equipment_details_json" not in columns:
            batch_op.add_column(
                sa.Column(
                    "equipment_details_json",
                    sa.Text(),
                    nullable=False,
                    server_default="{}",
                )
            )
        if "remarks" not in columns:
            batch_op.add_column(
                sa.Column("remarks", sa.Text(), nullable=False, server_default="")
            )


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM injection_scheduling_machines "
            "WHERE equipment_details_json NOT IN ('', '{}') OR remarks <> ''"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "0062 已保存机台设备明细或备注，拒绝执行会丢失数据的降级；"
            "请恢复升级前备份。"
        )
    with op.batch_alter_table("injection_scheduling_machines") as batch_op:
        batch_op.drop_column("remarks")
        batch_op.drop_column("equipment_details_json")
