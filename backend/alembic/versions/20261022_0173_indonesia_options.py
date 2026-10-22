"""Factory-maintained Indonesia form choices, without changing existing master snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0173'
down_revision = '20261021_0172'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        _create_schema()
    else:
        with op.get_bind().begin_nested():
            _create_schema()


def _create_schema():
    op.create_table('indonesia_material_options',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('business_key', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('factory_id', 'business_key'), sa.CheckConstraint('version > 0'))
    op.create_index('ix_indonesia_material_options_factory_id', 'indonesia_material_options', ['factory_id'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM indonesia_material_options')):
        raise RuntimeError('基础选项已有维护记录，请使用前向迁移保留资料')
    op.drop_table('indonesia_material_options')


def validate_options_schema(bind):
    inspector = sa.inspect(bind)
    name = 'indonesia_material_options'
    if not inspector.has_table(name):
        raise RuntimeError('Indonesia option schema is missing')
    columns = {column['name']: column for column in inspector.get_columns(name)}
    keys = {'id', 'factory_id', 'business_key', 'version', 'data', 'updated_at'}
    unique = {frozenset(item['column_names']) for item in inspector.get_unique_constraints(name)}
    if (not keys <= columns.keys() or any(columns[key]['nullable'] for key in keys)
            or inspector.get_pk_constraint(name)['constrained_columns'] != ['id']
            or frozenset({'factory_id', 'business_key'}) not in unique):
        raise RuntimeError('Indonesia option schema is incomplete')
