"""add rollout policy and scheduler assignment physical asset

Revision ID: 20260809_0060
Revises: 20260809_0059
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260809_0060"
down_revision: str | Sequence[str] | None = "20260809_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FACTORIES = (
    "huakang-a",
    "huakang-b",
    "huakang-c",
    "huakang-d",
    "huadeng",
    "huaxing",
)


def upgrade() -> None:
    op.create_table(
        "injection_scheduling_rollout_policies",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column(
            "demand_mode",
            sa.String(24),
            nullable=False,
            server_default="MANUAL_CONFIRM",
        ),
        sa.Column(
            "master_data_mode",
            sa.String(24),
            nullable=False,
            server_default="PROPOSAL_ONLY",
        ),
        sa.Column(
            "business_contract_status",
            sa.String(16),
            nullable=False,
            server_default="UNSIGNED",
        ),
        sa.Column(
            "price_activation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "tentative_hold_ttl_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "demand_mode IN ('SHADOW', 'PREVIEW_ONLY', 'MANUAL_CONFIRM', 'AUTO_ENRICH')",
            name="ck_inj_sched_rollout_demand_mode",
        ),
        sa.CheckConstraint(
            "master_data_mode IN ('PROPOSAL_ONLY', 'APPROVAL_ACTIVE')",
            name="ck_inj_sched_rollout_master_mode",
        ),
        sa.CheckConstraint(
            "business_contract_status IN ('UNSIGNED', 'SIGNED')",
            name="ck_inj_sched_rollout_contract_status",
        ),
        sa.CheckConstraint(
            "tentative_hold_ttl_minutes BETWEEN 5 AND 120",
            name="ck_inj_sched_rollout_hold_ttl",
        ),
    )
    op.create_index(
        "ix_inj_sched_rollout_demand_mode",
        "injection_scheduling_rollout_policies",
        ["demand_mode"],
    )
    op.create_index(
        "ix_inj_sched_rollout_master_mode",
        "injection_scheduling_rollout_policies",
        ["master_data_mode"],
    )
    op.create_index(
        "ix_inj_sched_rollout_contract_status",
        "injection_scheduling_rollout_policies",
        ["business_contract_status"],
    )

    policy = sa.table(
        "injection_scheduling_rollout_policies",
        sa.column("factory_id", sa.String),
        sa.column("demand_mode", sa.String),
        sa.column("master_data_mode", sa.String),
        sa.column("business_contract_status", sa.String),
        sa.column("price_activation_enabled", sa.Boolean),
        sa.column("tentative_hold_ttl_minutes", sa.Integer),
        sa.column("revision", sa.Integer),
        sa.column("updated_by", sa.String),
        sa.column("updated_by_name", sa.String),
        sa.column("updated_at", sa.String),
    )
    op.bulk_insert(
        policy,
        [
            {
                "factory_id": factory_id,
                "demand_mode": "MANUAL_CONFIRM",
                "master_data_mode": "PROPOSAL_ONLY",
                "business_contract_status": "UNSIGNED",
                "price_activation_enabled": False,
                "tentative_hold_ttl_minutes": 30,
                "revision": 1,
                "updated_by": "system:migration",
                "updated_by_name": "",
                "updated_at": "2026-08-09T00:00:00+08:00",
            }
            for factory_id in FACTORIES
        ],
    )

    with op.batch_alter_table("injection_scheduling_run_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("physical_mold_asset_id", sa.String(96), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_inj_sched_assignment_physical_asset",
            "injection_scheduling_physical_mold_assets",
            ["physical_mold_asset_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_inj_sched_assignment_physical_asset",
            ["physical_mold_asset_id"],
        )


def downgrade() -> None:
    if not context.is_offline_mode():
        connection = op.get_bind()
        assigned = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM injection_scheduling_run_assignments "
                "WHERE physical_mold_asset_id IS NOT NULL"
            )
        ).scalar_one()
        changed_policies = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM injection_scheduling_rollout_policies "
                "WHERE revision <> 1 OR demand_mode <> 'MANUAL_CONFIRM' "
                "OR master_data_mode <> 'PROPOSAL_ONLY' "
                "OR business_contract_status <> 'UNSIGNED' "
                "OR price_activation_enabled <> false "
                "OR tentative_hold_ttl_minutes <> 30"
            )
        ).scalar_one()
        if assigned or changed_policies:
            raise RuntimeError(
                "0060 已产生排程资产预占或 rollout policy 变更，拒绝丢失数据的降级"
            )

    with op.batch_alter_table("injection_scheduling_run_assignments") as batch_op:
        batch_op.drop_index("ix_inj_sched_assignment_physical_asset")
        batch_op.drop_constraint(
            "fk_inj_sched_assignment_physical_asset", type_="foreignkey"
        )
        batch_op.drop_column("physical_mold_asset_id")
    op.drop_index(
        "ix_inj_sched_rollout_contract_status",
        table_name="injection_scheduling_rollout_policies",
    )
    op.drop_index(
        "ix_inj_sched_rollout_master_mode",
        table_name="injection_scheduling_rollout_policies",
    )
    op.drop_index(
        "ix_inj_sched_rollout_demand_mode",
        table_name="injection_scheduling_rollout_policies",
    )
    op.drop_table("injection_scheduling_rollout_policies")
