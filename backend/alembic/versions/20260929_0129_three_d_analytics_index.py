"""Cover 3D telemetry statistics without reading raw device payload pages."""

from alembic import op

revision = "20260929_0129"
down_revision = "20260929_0128"
branch_labels = None
depends_on = None

INDEX = "ix_3d_event_analytics"
TABLE = "three_d_printing_printer_state_events"


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        # Keep telemetry ingestion online while indexing existing history.
        with op.get_context().autocommit_block():
            op.create_index(
                INDEX, TABLE, ["factory_id", "machine_no", "observed_at"],
                postgresql_include=["state", "error_code", "temperatures_json"],
                postgresql_concurrently=True,
            )
    else:
        op.create_index(INDEX, TABLE, ["factory_id", "machine_no", "observed_at"])


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
    else:
        op.drop_index(INDEX, table_name=TABLE)
