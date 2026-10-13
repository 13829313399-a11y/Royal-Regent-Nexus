"""Add isolated, versioned Huakang C cutting master data; no automatic grants."""
from alembic import op
import sqlalchemy as sa

revision = '20261007_0131'
down_revision = '20260929_0130'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cutting_ops_masters',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('code', sa.String(80), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.UniqueConstraint('factory_id', 'kind', 'code'),
        sa.CheckConstraint("factory_id = 'huakang-c'"),
        sa.CheckConstraint("kind IN ('material', 'resource', 'bom')"))
    op.create_table('cutting_ops_revisions',
        sa.Column('master_id', sa.String(36), primary_key=True),
        sa.Column('version', sa.Integer(), primary_key=True),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(['master_id'], ['cutting_ops_masters.id']))
    op.create_table('cutting_ops_commands',
        sa.Column('operation_id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('action', sa.String(120), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))


def downgrade():
    raise RuntimeError('裁床资料版本及审计不可自动删除；请按备份恢复流程回退')
