"""SQLite-only covering metadata index; immutable month evidence is unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_0185'
down_revision = '20261026_0184'
branch_labels = None
depends_on = None

NAME = 'ix_cutting_period_headers'
TABLE = 'cutting_ops_period_events'
COLUMNS = ('id', 'factory_id', 'month', 'version', 'action', 'actor_id', 'actor_name', 'created_at', 'reason')


def index_state(bind):
    rows = bind.exec_driver_sql('PRAGMA index_list(cutting_ops_period_events)').fetchall()
    match = next((row for row in rows if row[1] == NAME), None)
    if match is None:
        # A same-named object on another table must never be silently adopted.
        if bind.execute(sa.text('SELECT 1 FROM sqlite_master WHERE name=:name'), {'name': NAME}).first():
            raise RuntimeError('Cutting header index name is occupied by an incompatible object')
        return False
    keys = [row for row in bind.exec_driver_sql('PRAGMA index_xinfo(ix_cutting_period_headers)') if row[5]]
    if (match[2] or match[4] or tuple(row[2] for row in keys) != COLUMNS
            or any(row[1] < 0 or row[3] or row[4] != 'BINARY' for row in keys)):
        raise RuntimeError('Cutting header index contract differs; preserve database and reconcile explicitly')
    return True


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError('Cutting header index requires online contract inspection')
    bind = op.get_bind()
    # PostgreSQL keeps the existing query/transaction contract. A wide text
    # covering index there needs dedicated size/write validation, not this DDL.
    if bind.dialect.name != 'sqlite':
        return
    if not set(COLUMNS) <= {c['name'] for c in sa.inspect(bind).get_columns(TABLE)}:
        raise RuntimeError('Missing cutting month evidence columns')
    if not index_state(bind):
        if not bind.connection.driver_connection.in_transaction:
            bind.exec_driver_sql('BEGIN IMMEDIATE')
        op.create_index(NAME, TABLE, list(COLUMNS), unique=False)


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError('Cutting header index requires online contract inspection')
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite' and index_state(bind):
        if not bind.connection.driver_connection.in_transaction:
            bind.exec_driver_sql('BEGIN IMMEDIATE')
        op.drop_index(NAME, table_name=TABLE)
