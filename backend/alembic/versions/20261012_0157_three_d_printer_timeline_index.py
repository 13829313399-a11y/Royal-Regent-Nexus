"""Index the bounded printer timeline by its existing receive-time ordering."""

from alembic import op

revision = "20261012_0157"
down_revision = "20261010_0156"
branch_labels = None
depends_on = None

INDEX = "ix_3d_event_printer_received"
TABLE = "three_d_printing_printer_state_events"
COLUMNS = ["factory_id", "printer_id", "received_at"]


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        # Existing collectors keep writing while PostgreSQL builds the index.
        # Do not change event ordering, retained history or business records.
        with op.get_context().autocommit_block():
            op.create_index(INDEX, TABLE, COLUMNS, postgresql_concurrently=True)
    else:
        op.create_index(INDEX, TABLE, COLUMNS)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
    else:
        op.drop_index(INDEX, table_name=TABLE)
