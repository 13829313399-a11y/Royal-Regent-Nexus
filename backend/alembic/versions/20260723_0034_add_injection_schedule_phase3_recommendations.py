"""add injection schedule phase3 recommendation fields

Revision ID: 20260723_0034
Revises: 20260723_0033
Create Date: 2026-07-23 23:35:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0034"
down_revision: str | Sequence[str] | None = "20260723_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "injection_schedule_versions",
        sa.Column(
            "rule_config_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # Historical rule snapshots do not record the source config revision.
    # Keep migrated versions at 0 ("legacy/unknown") rather than falsely
    # attributing them to whatever config happens to be current at migration
    # time. Newly created versions persist the exact revision.
    op.add_column(
        "injection_machine_masters",
        sa.Column("screw_type", sa.String(64), nullable=False, server_default=""),
    )

    op.add_column(
        "injection_mold_masters",
        sa.Column("mold_thickness_mm", sa.Float(), nullable=True),
    )
    op.add_column(
        "injection_mold_masters",
        sa.Column("required_opening_stroke_mm", sa.Float(), nullable=True),
    )
    op.add_column(
        "injection_mold_masters",
        sa.Column(
            "required_screw_type",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "injection_order_masters",
        sa.Column("color_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "injection_order_masters",
        sa.Column("downstream_urgency", sa.Float(), nullable=True),
    )
    op.add_column(
        "injection_order_masters",
        sa.Column(
            "warehouse_buffer_hours",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "injection_order_masters",
        sa.Column(
            "downstream_buffer_hours",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "injection_order_masters",
        sa.Column(
            "special_handling_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "color_snapshot",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column("color_rank_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "material_snapshot",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column("recommendation_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "score_breakdown_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "constraint_snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "recommendation_context_hash",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )
    op.execute(
        """
        UPDATE injection_schedule_tasks
        SET color_snapshot = COALESCE(
                (
                    SELECT COALESCE(
                        NULLIF(TRIM(injection_order_masters.pigment), ''),
                        injection_order_masters.color
                    )
                    FROM injection_order_masters
                    WHERE injection_order_masters.id = injection_schedule_tasks.order_id
                      AND injection_order_masters.factory_id = injection_schedule_tasks.factory_id
                ),
                ''
            ),
            color_rank_snapshot = (
                SELECT injection_order_masters.color_rank
                FROM injection_order_masters
                WHERE injection_order_masters.id = injection_schedule_tasks.order_id
                  AND injection_order_masters.factory_id = injection_schedule_tasks.factory_id
            ),
            material_snapshot = COALESCE(
                (
                    SELECT injection_order_masters.material
                    FROM injection_order_masters
                    WHERE injection_order_masters.id = injection_schedule_tasks.order_id
                      AND injection_order_masters.factory_id = injection_schedule_tasks.factory_id
                ),
                ''
            )
        """
    )
    op.create_index(
        "ix_injection_schedule_tasks_source",
        "injection_schedule_tasks",
        ["source"],
    )
    op.create_index(
        "ix_injection_schedule_tasks_recommendation_context_hash",
        "injection_schedule_tasks",
        ["recommendation_context_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_injection_schedule_tasks_recommendation_context_hash",
        table_name="injection_schedule_tasks",
    )
    op.drop_index(
        "ix_injection_schedule_tasks_source",
        table_name="injection_schedule_tasks",
    )
    for column_name in (
        "recommendation_context_hash",
        "constraint_snapshot_json",
        "score_breakdown_json",
        "recommendation_score",
        "source",
        "material_snapshot",
        "color_rank_snapshot",
        "color_snapshot",
    ):
        op.drop_column("injection_schedule_tasks", column_name)

    for column_name in (
        "special_handling_reason",
        "downstream_buffer_hours",
        "warehouse_buffer_hours",
        "downstream_urgency",
        "color_rank",
    ):
        op.drop_column("injection_order_masters", column_name)

    for column_name in (
        "required_screw_type",
        "required_opening_stroke_mm",
        "mold_thickness_mm",
    ):
        op.drop_column("injection_mold_masters", column_name)
    op.drop_column("injection_machine_masters", "screw_type")
    op.drop_column("injection_schedule_versions", "rule_config_revision")
