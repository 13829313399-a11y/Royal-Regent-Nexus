"""Versioned calculation configuration and immutable reference-run snapshots."""

import sqlalchemy as sa
from alembic.util import CommandError

from alembic import op

revision = "20260902_0092"
down_revision = "20260902_0091"
branch_labels = None
depends_on = None

TABLE = "injection_schedule_calculation_runs"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("planning_base_at", sa.String(40), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "factory_id", "request_id", name="uq_is_calculation_request"
        ),
        sa.CheckConstraint(
            "factory_id IN ('huaxing','huadeng','huakang-a','huakang-b')",
            name="ck_is_calculation_factory",
        ),
        sa.CheckConstraint(
            "config_version >= 0", name="ck_is_calculation_config_version"
        ),
    )
    op.create_index(
        "ix_is_calculation_factory_created", TABLE, ["factory_id", "created_at", "id"]
    )
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_is_calculation_no_{action.lower()} BEFORE {action} ON {TABLE} BEGIN SELECT RAISE(ABORT, 'calculation snapshots are immutable'); END"
            )
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION reject_is_calculation_mutation_0092() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'calculation snapshots are immutable'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            f"CREATE TRIGGER trg_is_calculation_immutable BEFORE UPDATE OR DELETE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION reject_is_calculation_mutation_0092()"
        )


def downgrade():
    raise CommandError("Phase 4 计算快照不可删除；请恢复已验证的迁移前备份。")
