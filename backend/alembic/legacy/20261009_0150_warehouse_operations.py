"""Add immutable fabric and semi-finished operational documents."""
from alembic import op
import sqlalchemy as sa

revision = '20261009_0150'
down_revision = '20261009_0149'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('warehouse_operations_documents',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('warehouse', sa.String(16), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('business_date', sa.String(10), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('actor_name', sa.String(128), nullable=False),
        sa.Column('occurred_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('factory_id', 'warehouse', 'request_id', name='uq_warehouse_operation_request'),
        sa.UniqueConstraint('factory_id', 'warehouse', 'sequence', name='uq_warehouse_operation_sequence'),
        sa.CheckConstraint("factory_id = 'huakang-c'", name='ck_warehouse_operation_factory'),
        sa.CheckConstraint("warehouse IN ('fabric','semi')", name='ck_warehouse_operation_warehouse'))
    for column in ('factory_id', 'warehouse', 'business_date'):
        op.create_index(f'ix_warehouse_operations_documents_{column}', 'warehouse_operations_documents', [column])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM warehouse_operations_documents LIMIT 1')).first():
        raise RuntimeError('已有仓库收发和交接记录，禁止删除降级')
    op.drop_table('warehouse_operations_documents')
