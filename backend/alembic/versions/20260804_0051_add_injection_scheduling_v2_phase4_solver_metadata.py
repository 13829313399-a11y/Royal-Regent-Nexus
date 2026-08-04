"""add injection scheduling V2 phase 4 solver metadata

Revision ID: 20260804_0051
Revises: 20260804_0050
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0051"
down_revision: str | Sequence[str] | None = "20260804_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "injection_scheduling_runs",
        sa.Column(
            "requested_solver",
            sa.String(32),
            nullable=False,
            server_default="HEURISTIC",
        ),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column(
            "solver_status", sa.String(32), nullable=False, server_default="NOT_RUN"
        ),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column(
            "fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column("fallback_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column(
            "scenario_group_id", sa.String(96), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column(
            "scenario_name", sa.String(128), nullable=False, server_default="方案 A"
        ),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column("alternative_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "injection_scheduling_runs",
        sa.Column("replay_of_run_id", sa.String(96), nullable=True),
    )
    op.create_index(
        "ix_injection_scheduling_run_scenario_group",
        "injection_scheduling_runs",
        ["factory_id", "scenario_group_id", "alternative_no"],
    )
    op.create_index(
        "ix_injection_scheduling_runs_replay_of_run_id",
        "injection_scheduling_runs",
        ["replay_of_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_injection_scheduling_runs_replay_of_run_id",
        table_name="injection_scheduling_runs",
    )
    op.drop_index(
        "ix_injection_scheduling_run_scenario_group",
        table_name="injection_scheduling_runs",
    )
    for column in (
        "replay_of_run_id",
        "alternative_no",
        "scenario_name",
        "scenario_group_id",
        "fallback_reason",
        "fallback_used",
        "solver_status",
        "requested_solver",
    ):
        op.drop_column("injection_scheduling_runs", column)
