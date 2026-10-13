"""Isolated Heyuan-to-Indonesia materials; no existing-business migration."""
from alembic import op
import sqlalchemy as sa

revision = '20261013_0160'
down_revision = '20261012_0159'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('indonesia_material_records',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('business_key', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('factory_id', 'kind', 'business_key'),
        sa.CheckConstraint("kind IN ('material','product','order','supply','allocation','shipment','import')"),
        sa.CheckConstraint('version > 0'))
    op.create_index('ix_indonesia_material_records_factory_id', 'indonesia_material_records', ['factory_id'])
    op.create_table('indonesia_material_commands',
        sa.Column('operation_id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_indonesia_material_commands_factory_id', 'indonesia_material_commands', ['factory_id'])
    op.create_table('indonesia_material_assets',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(32), nullable=False),
        sa.Column('filename', sa.String(240), nullable=False),
        sa.Column('media_type', sa.String(100), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_indonesia_material_assets_factory_id', 'indonesia_material_assets', ['factory_id'])
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        for table in ('indonesia_material_commands', 'indonesia_material_assets'):
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable Indonesia material evidence'); END")
    elif bind.dialect.name == 'postgresql':
        op.execute("""CREATE FUNCTION protect_indonesia_material_evidence() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'immutable Indonesia material evidence'; END; $$ LANGUAGE plpgsql""")
        for table in ('indonesia_material_commands', 'indonesia_material_assets'):
            op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_indonesia_material_evidence()')


def downgrade():
    bind = op.get_bind()
    for table in ('indonesia_material_records', 'indonesia_material_commands', 'indonesia_material_assets'):
        if bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('送印尼物料已有资料或证据；拒绝删除业务数据的降级，请先保留备份')
    for table in ('indonesia_material_assets', 'indonesia_material_commands', 'indonesia_material_records'):
        op.drop_table(table)
    if bind.dialect.name == 'postgresql':
        op.execute('DROP FUNCTION protect_indonesia_material_evidence()')
