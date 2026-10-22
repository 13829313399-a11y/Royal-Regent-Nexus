"""Join main and Indonesia customer history without DDL or data writes."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0172'
down_revision = ('20261020_0171', '20261021_0169')
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError('Customer merge requires live schema validation; offline merge refused')
    validate_customer_schema(op.get_bind())


def validate_customer_schema(bind):
    """Read-only check for databases already carrying a customer successor label."""
    inspector = sa.inspect(bind)
    table = 'indonesia_material_customers'
    if not inspector.has_table(table):
        raise RuntimeError('Indonesia customer schema is missing; merge refused')
    columns = {column['name']: column for column in inspector.get_columns(table)}
    required = {'id', 'factory_id', 'business_key', 'version', 'data', 'updated_at'}
    unique = {frozenset(item['column_names']) for item in inspector.get_unique_constraints(table)}
    if (not required <= columns.keys() or any(columns[key]['nullable'] for key in required)
            or inspector.get_pk_constraint(table)['constrained_columns'] != ['id']
            or frozenset({'factory_id', 'business_key'}) not in unique):
        raise RuntimeError('Indonesia customer schema is incomplete; merge refused')


def downgrade():
    raise RuntimeError('Merged Indonesia customer evidence must be preserved; use a forward migration')
