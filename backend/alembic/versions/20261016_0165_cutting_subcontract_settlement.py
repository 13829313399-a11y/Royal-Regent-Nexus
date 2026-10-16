"""Explicit migration for immutable subcontract settlement evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_0165'
down_revision = '20261016_0164'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cutting_ops_settlement_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('document_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('actor_name', sa.String(128), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.UniqueConstraint('factory_id', 'version'),
        sa.CheckConstraint("factory_id = 'huakang-c'"),
        sa.CheckConstraint("action IN ('price','save','submit','return','confirm','reopen')"))
    op.create_index('ix_cutting_settlement_document', 'cutting_ops_settlement_events', ['factory_id', 'document_id'])
    if op.get_bind().dialect.name == 'sqlite':
        for action in ('update', 'delete'):
            op.execute(f"CREATE TRIGGER cutting_settlement_no_{action} BEFORE {action.upper()} ON cutting_ops_settlement_events BEGIN SELECT RAISE(ABORT, 'cutting settlement evidence is append-only'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION cutting_settlement_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'cutting settlement evidence is append-only'; END; $$")
        op.execute("CREATE TRIGGER cutting_settlement_immutable BEFORE UPDATE OR DELETE ON cutting_ops_settlement_events FOR EACH ROW EXECUTE FUNCTION cutting_settlement_immutable()")


def downgrade():
    raise RuntimeError('外发结算及价格证据不可自动删除，请使用备份恢复流程')
