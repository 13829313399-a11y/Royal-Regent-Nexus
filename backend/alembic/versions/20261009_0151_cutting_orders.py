"""Versioned cutting order receipt, engineering requisitions and promised dates."""
from alembic import op
import sqlalchemy as sa

revision = '20261009_0151'
down_revision = '20261009_0150'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cutting_ops_orders',
        sa.Column('line_id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('dispatch_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['line_id'], ['order_ledger_lines.id']),
        sa.ForeignKeyConstraint(['dispatch_id'], ['order_ledger_dispatches.id']),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_table('cutting_ops_order_revisions',
        sa.Column('line_id', sa.String(64), primary_key=True),
        sa.Column('version', sa.Integer(), primary_key=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(['line_id'], ['cutting_ops_orders.line_id']))


def downgrade():
    raise RuntimeError('裁床订单与需求历史不可自动删除；请按备份恢复流程回退')
