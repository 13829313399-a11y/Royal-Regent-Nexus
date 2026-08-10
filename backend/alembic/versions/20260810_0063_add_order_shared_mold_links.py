"""link scheduling orders directly to shared mold master data

Revision ID: 20260810_0063
Revises: 20260810_0062
Create Date: 2026-08-10
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0063"
down_revision: str | Sequence[str] | None = "20260810_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(connection: sa.Connection) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(connection).get_columns("injection_scheduling_orders")
    }


def _backfill_shared_links(connection: sa.Connection) -> None:
    version_links = {
        row.id: (row.mold_definition_id, row.mold_output_spec_id)
        for row in connection.execute(
            sa.text(
                "SELECT id, mold_definition_id, mold_output_spec_id "
                "FROM injection_scheduling_demand_order_versions"
            )
        )
    }
    orders = connection.execute(
        sa.text("SELECT id, source_ref, lineage_json FROM injection_scheduling_orders")
    )
    for order in orders:
        try:
            lineage = json.loads(order.lineage_json or "{}")
        except (TypeError, json.JSONDecodeError):
            lineage = {}
        version_definition_id, version_output_id = version_links.get(
            order.source_ref, (None, None)
        )
        definition_id = lineage.get("mold_definition_id") or version_definition_id
        output_id = lineage.get("mold_output_spec_id") or version_output_id
        if not definition_id and not output_id:
            continue
        connection.execute(
            sa.text(
                "UPDATE injection_scheduling_orders "
                "SET mold_definition_id = :definition_id, "
                "mold_output_spec_id = :output_id WHERE id = :order_id"
            ),
            {
                "definition_id": definition_id,
                "output_id": output_id,
                "order_id": order.id,
            },
        )


def upgrade() -> None:
    connection = op.get_bind()
    columns = _existing_columns(connection)
    with op.batch_alter_table("injection_scheduling_orders") as batch_op:
        if "mold_definition_id" not in columns:
            batch_op.add_column(
                sa.Column("mold_definition_id", sa.String(96), nullable=True)
            )
            batch_op.create_index(
                "ix_inj_sched_order_mold_definition",
                ["mold_definition_id"],
                unique=False,
            )
            batch_op.create_foreign_key(
                "fk_inj_sched_order_mold_definition",
                "injection_scheduling_mold_definitions",
                ["mold_definition_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "mold_output_spec_id" not in columns:
            batch_op.add_column(
                sa.Column("mold_output_spec_id", sa.String(96), nullable=True)
            )
            batch_op.create_index(
                "ix_inj_sched_order_mold_output",
                ["mold_output_spec_id"],
                unique=False,
            )
            batch_op.create_foreign_key(
                "fk_inj_sched_order_mold_output",
                "injection_scheduling_mold_output_specs",
                ["mold_output_spec_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    _backfill_shared_links(connection)


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM injection_scheduling_orders "
            "WHERE mold_definition_id IS NOT NULL OR mold_output_spec_id IS NOT NULL"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "0063 已保存订单共享模具关联，拒绝执行会丢失数据的降级；请恢复升级前备份。"
        )
    with op.batch_alter_table("injection_scheduling_orders") as batch_op:
        batch_op.drop_constraint("fk_inj_sched_order_mold_output", type_="foreignkey")
        batch_op.drop_index("ix_inj_sched_order_mold_output")
        batch_op.drop_column("mold_output_spec_id")
        batch_op.drop_constraint(
            "fk_inj_sched_order_mold_definition", type_="foreignkey"
        )
        batch_op.drop_index("ix_inj_sched_order_mold_definition")
        batch_op.drop_column("mold_definition_id")
