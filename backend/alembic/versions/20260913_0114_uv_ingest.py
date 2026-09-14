"""UV scoped connector credentials and immutable event receipts."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0114"
down_revision = "20260913_0113"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("uv_connectors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(32), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_connector_factory"))
    op.create_table("uv_connector_machines",
        sa.Column("connector_id", sa.String(64), sa.ForeignKey("uv_connectors.id"), primary_key=True),
        sa.Column("machine_id", sa.String(64), sa.ForeignKey("uv_machines.id"), primary_key=True))
    op.create_table("uv_print_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(32), nullable=False),
        sa.Column("connector_id", sa.String(64), sa.ForeignKey("uv_connectors.id"), nullable=False),
        sa.Column("machine_id", sa.String(64), sa.ForeignKey("uv_machines.id"), nullable=False),
        sa.Column("generation", sa.String(128), nullable=False),
        sa.Column("source_event_id", sa.String(255), nullable=False),
        sa.Column("source_job_id", sa.String(255)),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("uv_jobs.id")),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.String(40), nullable=False),
        sa.Column("received_at", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("connector_id", "generation", "source_event_id", name="uq_uv_ingest_event"),
        sa.CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_event_factory"),
        sa.CheckConstraint("seq >= 0", name="ck_uv_event_seq"))
    for column in ("machine_id", "job_id", "observed_at"):
        op.create_index(f"ix_uv_print_events_{column}", "uv_print_events", [column])


def downgrade():
    op.drop_table("uv_print_events")
    op.drop_table("uv_connector_machines")
    op.drop_table("uv_connectors")
