"""Add ownership and plain text to the existing source library; preserve evidence."""
import json
from alembic import op
import sqlalchemy as sa

revision = '20261030_0187'
down_revision = '20261030_0186'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('carton_mark_assets') as batch:
        batch.add_column(sa.Column('owner_department', sa.String(64), nullable=True))
        batch.add_column(sa.Column('owner_supplier_id', sa.String(96), nullable=True))
        batch.add_column(sa.Column('asset_purpose', sa.String(16), nullable=False, server_default='MATERIAL'))
        batch.drop_constraint('ck_carton_mark_asset_kind', type_='check')
        batch.create_check_constraint('ck_carton_mark_asset_kind', "kind IN ('excel', 'pdf', 'image', 'text')")
        batch.create_check_constraint('ck_carton_mark_asset_purpose', "asset_purpose IN ('MATERIAL', 'EVIDENCE')")
        batch.create_index('ix_carton_mark_asset_owner', ['factory_id','owner_department','is_archived','created_at'])
    # Only creation-time, actor-matched supplier evidence establishes ownership.
    # Never infer an internal department from an employee's current assignment.
    if op.get_context().as_sql:
        return  # Offline DDL is not a backfill rehearsal.
    db = op.get_bind()
    rows = db.execute(sa.text("SELECT a.id,a.factory_id,a.created_by,e.actor_user_id,e.detail_json "
        "FROM carton_mark_assets a JOIN carton_audit_events e ON e.entity_id=a.id AND e.factory_id=a.factory_id "
        "WHERE e.entity_type='carton_mark_asset' AND e.event_type='CARTON_MARK_ASSET_CREATED' "
        "AND a.recognition_source!='materials_folder'"))
    candidates = {}
    for identifier,factory,creator,actor,raw in rows:
        try:
            supplier = json.loads(raw).get('supplier_context', {}).get('supplier_id')
        except (ValueError,TypeError,AttributeError):
            continue
        if supplier and creator == actor:
            candidates.setdefault((identifier,factory), set()).add(supplier)
    for (identifier,factory),values in candidates.items():
        if len(values) != 1: continue
        supplier = next(iter(values))
        if db.execute(sa.text('SELECT id FROM carton_suppliers WHERE id=:s AND factory_id=:f'),dict(s=supplier,f=factory)).first():
            db.execute(sa.text("UPDATE carton_mark_assets SET owner_department='supplier',owner_supplier_id=:s "
                'WHERE id=:id AND factory_id=:f AND owner_department IS NULL'),dict(s=supplier,id=identifier,f=factory))


def downgrade():
    raise RuntimeError('Keep ownership, text and evidence. Disable CARTON_ASSET_V1_WRITES_ENABLED; use a compatible reader, not a destructive downgrade.')
