"""Engineering BOM foundation. Explicit migration, no business data/grants."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0190'
down_revision = '20261102_0189'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('engineering_bom_documents',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('effective_version', sa.Integer(), nullable=True),
        sa.Column('item_no', sa.String(128), nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_table('engineering_bom_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('operation_id', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('occurred_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.UniqueConstraint('factory_id', 'operation_id'),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_index('ix_engineering_bom_events_entity_id', 'engineering_bom_events', ['entity_id'])
    if op.get_bind().dialect.name == 'sqlite':
        for action in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER engineering_events_no_{action.lower()} BEFORE {action} ON engineering_bom_events BEGIN SELECT RAISE(ABORT, 'immutable engineering evidence'); END")
    else:
        op.execute("CREATE FUNCTION engineering_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable engineering evidence'; END $$")
        op.execute('CREATE TRIGGER engineering_events_immutable BEFORE UPDATE OR DELETE ON engineering_bom_events FOR EACH ROW EXECUTE FUNCTION engineering_events_immutable()')


def downgrade():
    if op.get_context().as_sql or op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM engineering_bom_events')):
        raise RuntimeError('Preserve engineering history; only an empty domain can be removed')
    op.drop_table('engineering_bom_events')
    op.drop_table('engineering_bom_documents')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION engineering_events_immutable()')
