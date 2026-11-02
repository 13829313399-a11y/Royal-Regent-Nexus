"""Only a rebuildable carton material reference projection; no legacy backfill."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_0185'
down_revision = '20261026_0184'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_carton_material_ref_version': ['factory_id', 'version_id', 'active', 'target_context_id'],
    'ix_carton_material_ref_source': ['factory_id', 'source_context_id', 'active', 'reference_id'],
}


def upgrade():
    offline = op.get_context().as_sql
    exists = not offline and sa.inspect(op.get_bind()).has_table('carton_material_references')
    if not exists:
        op.create_table('carton_material_references',
            sa.Column('factory_id', sa.String(64), primary_key=True),
            sa.Column('reference_id', sa.String(96), primary_key=True),
            *[sa.Column(name, sa.String(96), nullable=False) for name in
              ('customer_id', 'version_id', 'source_context_id', 'source_order_key',
               'target_context_id', 'target_order_key', 'contract_id')],
            sa.Column('active', sa.Boolean(), nullable=False),
            sa.Column('revision', sa.Integer(), nullable=False),
            sa.Column('origin_event_sequence', sa.BigInteger(), nullable=False),
            sa.Column('last_event_sequence', sa.BigInteger(), nullable=False),
            sa.UniqueConstraint('factory_id', 'target_context_id', 'version_id', name='uq_carton_material_ref_target_version'),
            sa.CheckConstraint('revision >= 1 AND origin_event_sequence > 0 AND last_event_sequence >= origin_event_sequence',
                               name='ck_carton_material_ref_revision'))
    else:
        inspector=sa.inspect(op.get_bind())
        expected={'factory_id','reference_id','customer_id','version_id','source_context_id','source_order_key',
                  'target_context_id','target_order_key','contract_id','active','revision','origin_event_sequence','last_event_sequence'}
        if {c['name'] for c in inspector.get_columns('carton_material_references')} != expected:
            raise RuntimeError('Reference projection schema differs; refusing to hide a partial migration')
        if inspector.get_pk_constraint('carton_material_references')['constrained_columns'] != ['factory_id','reference_id'] or not any(
            c['column_names']==['factory_id','target_context_id','version_id'] for c in inspector.get_unique_constraints('carton_material_references')):
            raise RuntimeError('Reference projection identity constraints differ')
    present={} if not exists else {i['name']:i['column_names'] for i in sa.inspect(op.get_bind()).get_indexes('carton_material_references')}
    for name,columns in INDEXES.items():
        if name in present and present[name]!=columns:
            raise RuntimeError('Reference projection index differs: '+name)
        if name not in present: op.create_index(name,'carton_material_references',columns)


def downgrade():
    raise RuntimeError('Keep reference readers and evidence: disable writes and rebuild the projection; do not downgrade to an unaware writer')
