"""Explicit factory-local spreadsheet collaboration on its original applied branch.

The published main history is joined by 20261009_0148 without changing this
revision's parent or schema operations.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_0121"
down_revision = "20261005_0120"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("collaborative_sheets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=False),
        sa.Column("owner_name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("original_name", sa.String(240), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("grants", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("status IN ('draft','open','closed')", name="ck_collaborative_sheet_status"),
        sa.CheckConstraint("revision >= 1", name="ck_collaborative_sheet_revision"))
    for column in ("factory_id", "owner_user_id"):
        op.create_index("ix_collaborative_sheets_" + column, "collaborative_sheets", [column])
    op.create_table("collaborative_sheet_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("collaborative_sheets.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False))
    op.create_index("ix_collaborative_sheet_events_task_id", "collaborative_sheet_events", ["task_id"])
    op.create_table("collaborative_sheet_submissions",
        sa.Column("task_id", sa.String(64), sa.ForeignKey("collaborative_sheets.id"), primary_key=True),
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.String(32), nullable=False))
    if op.get_context().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER collaborative_sheet_events_no_{action.lower()} BEFORE {action} ON collaborative_sheet_events "
                       "BEGIN SELECT RAISE(ABORT, 'collaborative sheet history is append-only'); END")
    elif op.get_context().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION collaborative_sheet_history_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'collaborative sheet history is append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER collaborative_sheet_events_immutable BEFORE UPDATE OR DELETE ON collaborative_sheet_events "
                   "FOR EACH ROW EXECUTE FUNCTION collaborative_sheet_history_immutable()")


def downgrade():
    op.drop_table("collaborative_sheet_submissions")
    op.drop_table("collaborative_sheet_events")
    op.drop_table("collaborative_sheets")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS collaborative_sheet_history_immutable()")
