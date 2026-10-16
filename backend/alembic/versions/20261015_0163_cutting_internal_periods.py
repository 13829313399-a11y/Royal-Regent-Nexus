"""Explicit immutable cutting internal month snapshots and lock history."""
from alembic import op
import sqlalchemy as sa

revision = '20261015_0163'
down_revision = '20261015_0162'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cutting_ops_period_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('month', sa.String(7), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('actor_name', sa.String(128), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.UniqueConstraint('factory_id', 'version'),
        sa.CheckConstraint("factory_id = 'huakang-c'"),
        sa.CheckConstraint("action IN ('save','submit','return','lock','reopen')"))
    op.create_index('ix_cutting_period_month', 'cutting_ops_period_events', ['factory_id', 'month'])
    if op.get_bind().dialect.name == 'sqlite':
        for action in ('update', 'delete'):
            op.execute(f"CREATE TRIGGER cutting_period_no_{action} BEFORE {action.upper()} ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT, 'cutting period evidence is append-only'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION cutting_period_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'cutting period evidence is append-only'; END; $$")
        op.execute("CREATE TRIGGER cutting_period_immutable BEFORE UPDATE OR DELETE ON cutting_ops_period_events FOR EACH ROW EXECUTE FUNCTION cutting_period_immutable()")


def downgrade():
    raise RuntimeError('月结、锁月和反结历史不可自动删除；请按备份恢复流程回退')
