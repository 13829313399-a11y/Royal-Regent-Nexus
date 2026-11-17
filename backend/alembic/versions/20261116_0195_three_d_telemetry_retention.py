"""Keep exact timing separately from expired high-frequency printer reports."""
from alembic import op
import sqlalchemy as sa

revision = "20261116_0195"
down_revision = "20261110_0194"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "three_d_printing_telemetry_ticks",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_no", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.String(32), nullable=False),
        sa.Column("received_at", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("payload_digest", sa.LargeBinary(32), nullable=False),
    )
    op.create_index("ix_3d_tick_clock", "three_d_printing_telemetry_ticks",
                    ["factory_id", "machine_no", "observed_at"])
    op.create_table(
        "three_d_printing_retention_cursors",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("printer_id", sa.String(96), primary_key=True),
        sa.Column("received_at", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(96), nullable=False),
    )


def downgrade():
    raise RuntimeError("Archived printer observations are primary statistical evidence. Preserve them before downgrading.")
