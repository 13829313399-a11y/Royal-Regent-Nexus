"""Factory-specific eligible Indonesia customers; preserve existing snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0169'
down_revision = '20261019_0167'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        _create_schema()
    else:
        # Failed SQLite DDL must leave neither a partial customer table nor a revision.
        with op.get_bind().begin_nested():
            _create_schema()


def _create_schema():
    op.create_table('indonesia_material_customers',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('business_key', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('factory_id', 'business_key'),
        sa.CheckConstraint('version > 0'))
    op.create_index('ix_indonesia_material_customers_factory_id', 'indonesia_material_customers', ['factory_id'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM indonesia_material_customers')):
        raise RuntimeError('固定客人资料已有记录，请保留原资料及操作证据，拒绝删除式降级')
    op.drop_table('indonesia_material_customers')
