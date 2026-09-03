"""Add immutable Phase 5 draft evidence to the retained proposal table."""

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "20260902_0093"
down_revision = "20260902_0092"
branch_labels = None
depends_on = None
TABLE = "injection_schedule_auto_proposals"


def upgrade():
    # Additive only: no table rebuild, no reinterpretation of legacy proposals.
    for column in (
        sa.Column("phase5_revision", sa.Integer(), nullable=True),
        sa.Column("phase5_parent_id", sa.String(96), nullable=True),
        sa.Column("phase5_input_json", sa.Text(), nullable=True),
        sa.Column("phase5_result_digest", sa.String(64), nullable=True),
        sa.Column("phase5_reason", sa.String(500), nullable=True),
    ):
        op.add_column(TABLE, column)
    op.create_index(
        "uq_is_phase5_factory_revision",
        TABLE,
        ["factory_id", "phase5_revision"],
        unique=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_is_phase5_no_{action.lower()} BEFORE {action} ON {TABLE} WHEN OLD.phase5_revision IS NOT NULL BEGIN SELECT RAISE(ABORT, 'Phase 5 drafts are immutable'); END"
            )
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION reject_is_phase5_mutation_0093() RETURNS trigger AS $$ BEGIN IF OLD.phase5_revision IS NOT NULL THEN RAISE EXCEPTION 'Phase 5 drafts are immutable'; END IF; IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            f"CREATE TRIGGER trg_is_phase5_immutable BEFORE UPDATE OR DELETE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION reject_is_phase5_mutation_0093()"
        )


def downgrade():
    raise CommandError("Phase 5 草稿证据不可删除；请恢复已验证的迁移前备份。")
