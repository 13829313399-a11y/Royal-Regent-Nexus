"""Sales trial drafts only. Explicit, empty-domain-reversible migration."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0191'
down_revision = '20261104_0190'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('material_plan_drafts',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('owner_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_table('material_plan_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('operation_id', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('occurred_at', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.UniqueConstraint('factory_id', 'operation_id'),
        sa.CheckConstraint("factory_id = 'huakang-c'"))
    op.create_index('ix_material_plan_events_entity_id', 'material_plan_events', ['entity_id'])
    if op.get_bind().dialect.name == 'sqlite':
        for action in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER material_plan_no_{action.lower()} BEFORE {action} ON material_plan_events BEGIN SELECT RAISE(ABORT, 'immutable trial history'); END")
    else:
        op.execute("CREATE FUNCTION material_plan_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable trial history'; END $$")
        op.execute('CREATE TRIGGER material_plan_immutable BEFORE UPDATE OR DELETE ON material_plan_events FOR EACH ROW EXECUTE FUNCTION material_plan_immutable()')


def downgrade():
    if op.get_context().as_sql or any(op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {table}'))
            for table in ('material_plan_events', 'material_plan_drafts')):
        raise RuntimeError('Preserve trial history; only an empty domain can be removed')
    op.drop_table('material_plan_events')
    op.drop_table('material_plan_drafts')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION material_plan_immutable()')
