"""Publish warehouse operations after main's quote and cutting migrations.

The local-only warehouse 0150 is preserved byte-for-byte in ../legacy.
Only its exact SQLite schema may be adopted; no history is stamped or rebuilt.
"""
from pathlib import Path
import runpy

from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

revision = '20261009_0152'
down_revision = '20261009_0151'
branch_labels = None
depends_on = None

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT.parent / 'legacy' / '20261009_0150_warehouse_operations.py'
WAREHOUSE = 'warehouse_operations_documents'
MASTERS = ('cutting_ops_masters', 'cutting_ops_revisions', 'cutting_ops_commands')
ORDERS = ('cutting_ops_orders', 'cutting_ops_order_revisions')


def _signature(inspector, name):
    return {
        'columns': [(c['name'], str(c['type']).upper(), c['nullable'], c['default']) for c in inspector.get_columns(name)],
        'pk': inspector.get_pk_constraint(name)['constrained_columns'],
        'unique': sorted((c.get('name') or '', tuple(c['column_names'])) for c in inspector.get_unique_constraints(name)),
        # SQL literals are case/whitespace sensitive. Accept only the original
        # reflected expressions, never normalize their contents.
        'checks': sorted((c.get('name') or '', c['sqltext']) for c in inspector.get_check_constraints(name)),
        'indexes': sorted((c['name'], tuple(c['column_names']), bool(c['unique']),
                           str(c.get('dialect_options', {}).get('sqlite_where', '')))
                          for c in inspector.get_indexes(name)),
        'foreign_keys': sorted((tuple(c['constrained_columns']), c['referred_table'], tuple(c['referred_columns']),
                                tuple(sorted(c.get('options', {}).items()))) for c in inspector.get_foreign_keys(name)),
    }


def _expected():
    # Derive the contract from the immutable original scripts, on an empty
    # in-memory connection. Do not replace Alembic's active global op context.
    engine = sa.create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            operation = Operations(MigrationContext.configure(connection))
            for path in (LEGACY, ROOT / '20261007_0131_cutting_master.py', ROOT / '20261009_0151_cutting_orders.py'):
                upgrade = runpy.run_path(str(path))['upgrade']
                upgrade.__globals__['op'] = operation
                upgrade()
            inspector = sa.inspect(connection)
            return {name: _signature(inspector, name) for name in (WAREHOUSE, *MASTERS, *ORDERS)}
    finally:
        engine.dispose()


def _quote_column(bind):
    inspector = sa.inspect(bind)
    if not inspector.has_table('molding_sample_items'):
        raise RuntimeError('molding schema is missing; inspect migration history before upgrading')
    column = next((c for c in inspector.get_columns('molding_sample_items') if c['name'] == 'quote_target_daily_qty'), None)
    if column and (str(column['type']).upper() != 'INTEGER' or not column['nullable'] or column['default'] is not None):
        raise RuntimeError('quote target column has schema drift; inspect migration history before upgrading')
    return column


def preflight_legacy(bind, *, before_cutting=False):
    """Read-only guard, also called by env.py before SQLite can execute 0151."""
    if bind.dialect.name != 'sqlite':
        raise RuntimeError('pre-existing warehouse schema can only be adopted for the known local SQLite migration')
    inspector = sa.inspect(bind)
    expected = _expected()
    tables = (WAREHOUSE, *MASTERS, *(() if before_cutting else ORDERS))
    for name in tables:
        if not inspector.has_table(name) or _signature(inspector, name) != expected[name]:
            raise RuntimeError(f'local warehouse migration schema drift: {name}; inspect history before upgrading')
        if bind.execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=:name"), {'name': name}).first():
            raise RuntimeError(f'local warehouse migration has unexpected triggers: {name}')
    if before_cutting and any(inspector.has_table(name) for name in ORDERS):
        raise RuntimeError('local warehouse 0150 has unexpected cutting order tables; inspect migration history')
    _quote_column(bind)


def upgrade():
    bind = op.get_bind()
    existing = sa.inspect(bind).has_table(WAREHOUSE)
    if existing:
        preflight_legacy(bind)
    quote = _quote_column(bind)
    if quote is None:
        if not existing:
            raise RuntimeError('published quote migration is missing; refusing to infer an unknown history')
        # The old local warehouse 0150 shadowed main's quote 0150. The complete
        # cutting contract was checked above, so its older repair branch cannot run.
        runpy.run_path(str(ROOT / '20261009_0150_molding_quote_target.py'))['upgrade']()
    if not existing:
        runpy.run_path(str(LEGACY))['upgrade']()


def downgrade():
    # Canonical quote/cutting history belongs to preceding published revisions.
    runpy.run_path(str(LEGACY))['downgrade']()
