"""Cutting daily reports, matching and handover evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20261010_0155'
down_revision = '20261010_0154'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cutting_ops_production_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('line_id', sa.String(64), nullable=False),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.String(64), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(['line_id'], ['cutting_ops_orders.line_id']),
        sa.UniqueConstraint('line_id', 'version'),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_index('ix_cutting_ops_production_events_line_id', 'cutting_ops_production_events', ['line_id'])
    if op.get_bind().dialect.name == 'sqlite':
        for action in ('update', 'delete'):
            op.execute(f"CREATE TRIGGER cutting_production_no_{action} BEFORE {action.upper()} ON cutting_ops_production_events BEGIN SELECT RAISE(ABORT, 'cutting production evidence is append-only'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION cutting_production_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'cutting production evidence is append-only'; END; $$")
        op.execute("CREATE TRIGGER cutting_production_immutable BEFORE UPDATE OR DELETE ON cutting_ops_production_events FOR EACH ROW EXECUTE FUNCTION cutting_production_immutable()")


def downgrade():
    raise RuntimeError('裁床实绩历史不可自动删除；请按备份恢复流程回退')
