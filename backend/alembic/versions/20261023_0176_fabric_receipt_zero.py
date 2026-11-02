"""Allow evidence-only purchase receipts; positive stock movements stay unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '20261023_0176'
down_revision = '20261022_0175'
branch_labels = None
depends_on = None


def replace_check(expression):
    # SQLite rebuilds this table, preserving its columns, indexes and other constraints.
    # PostgreSQL uses native ALTER TABLE DROP/ADD CONSTRAINT.
    with op.batch_alter_table('fabric_receipts') as batch:
        batch.drop_constraint('ck_fabric_receipt_quantity', type_='check')
        batch.create_check_constraint('ck_fabric_receipt_quantity', expression)


def upgrade():
    replace_check('CAST(quantity AS NUMERIC) >= 0')


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError('Downgrade requires an online zero-receipt check; evidence must be preserved')
    if op.get_bind().execute(sa.text('SELECT 1 FROM fabric_receipts WHERE CAST(quantity AS NUMERIC) = 0 LIMIT 1')).first():
        raise RuntimeError('存在零入库差异单，不能恢复 quantity > 0；请保留原始差异证据')
    replace_check('CAST(quantity AS NUMERIC) > 0')
