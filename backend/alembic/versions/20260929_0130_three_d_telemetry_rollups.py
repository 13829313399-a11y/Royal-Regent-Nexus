"""Add rebuildable hourly telemetry summaries, leaving original events intact."""

from alembic import op
import sqlalchemy as sa

revision = "20260929_0130"
down_revision = "20260929_0129"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "three_d_printing_telemetry_rollups",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("bucket_start", sa.String(32), primary_key=True),
        sa.Column("dirty", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("counters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("calculated_at", sa.String(32), nullable=False, server_default=""),
    )
    op.create_table(
        "three_d_printing_telemetry_rollup_state",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("initialized_at", sa.String(32), nullable=False, server_default=""),
    )


def downgrade():
    # Only derived, reproducible summaries are removed. Raw event evidence stays.
    op.drop_table("three_d_printing_telemetry_rollup_state")
    op.drop_table("three_d_printing_telemetry_rollups")
