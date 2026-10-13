"""Persist immutable factory-scoped QC photos, template snapshots and review history."""
from alembic import op
import sqlalchemy as sa

revision = "20261010_0153"
down_revision = "20261009_0152"
branch_labels = None
depends_on = None


def _tables():
    meta = sa.MetaData()
    sa.Table("carton_mark_templates", meta, sa.Column("id", sa.String(96)), sa.Column("factory_id", sa.String(64)))
    sa.Table('carton_mark_qc_records', meta,
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('template_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('template_version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('template_snapshot_json', sa.Text(), nullable=False, primary_key=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('po', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('item', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('contract_number', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('pdf_sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('slot', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('corrects_record_id', sa.String(length=96), nullable=True, primary_key=False),
        sa.Column('note', sa.String(length=1000), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('created_by_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.CheckConstraint('slot >= 0 AND template_version >= 1', name='ck_mark_qc_version_slot'),
        sa.ForeignKeyConstraint(['corrects_record_id', 'factory_id'], ['carton_mark_qc_records.id', 'carton_mark_qc_records.factory_id'], name='fk_mark_qc_correction_factory'),
        sa.ForeignKeyConstraint(['template_id', 'factory_id'], ['carton_mark_templates.id', 'carton_mark_templates.factory_id'], name='fk_mark_qc_template_factory'),
        sa.UniqueConstraint('id', 'factory_id', name='uq_mark_qc_record_factory'),
        sa.UniqueConstraint('factory_id', 'created_by', 'request_id', 'slot', name='uq_mark_qc_submission'),
    )
    sa.Index('ix_mark_qc_factory_created', meta.tables['carton_mark_qc_records'].c['factory_id'], meta.tables['carton_mark_qc_records'].c['created_at'], meta.tables['carton_mark_qc_records'].c['id'], unique=False)
    sa.Table('carton_mark_qc_photos', meta,
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('record_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('side', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('file_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('content_type', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('content', sa.LargeBinary(), nullable=False, primary_key=False),
        sa.CheckConstraint("side IN ('front', 'side') AND size_bytes > 0", name='ck_mark_qc_photo'),
        sa.ForeignKeyConstraint(['record_id', 'factory_id'], ['carton_mark_qc_records.id', 'carton_mark_qc_records.factory_id'], name='fk_mark_qc_photo_factory'),
        sa.UniqueConstraint('record_id', 'side', name='uq_mark_qc_photo_side'),
    )
    sa.Index('ix_carton_mark_qc_photos_record_id', meta.tables['carton_mark_qc_photos'].c['record_id'], unique=False)
    sa.Table('carton_mark_qc_events', meta,
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('record_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('result_json', sa.Text(), nullable=False, primary_key=False),
        sa.Column('error', sa.String(length=1000), nullable=False, primary_key=False),
        sa.Column('note', sa.String(length=1000), nullable=False, primary_key=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('actor_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.CheckConstraint("kind IN ('AUTO_CHECK', 'REVIEW', 'VOID')", name='ck_mark_qc_event_kind'),
        sa.CheckConstraint('revision >= 1', name='ck_mark_qc_event_revision'),
        sa.CheckConstraint("status IN ('待复核', '核对通过', '发现异常', '已作废')", name='ck_mark_qc_event_status'),
        sa.ForeignKeyConstraint(['record_id', 'factory_id'], ['carton_mark_qc_records.id', 'carton_mark_qc_records.factory_id'], name='fk_mark_qc_event_factory'),
        sa.UniqueConstraint('record_id', 'actor_id', 'request_id', name='uq_mark_qc_event_request'),
        sa.UniqueConstraint('record_id', 'revision', name='uq_mark_qc_event_revision'),
    )
    sa.Index('ix_carton_mark_qc_events_record_id', meta.tables['carton_mark_qc_events'].c['record_id'], unique=False)
    return [meta.tables[name] for name in ('carton_mark_qc_records', 'carton_mark_qc_photos', 'carton_mark_qc_events')]


def upgrade():
    bind = op.get_bind()
    for table in _tables():
        table.create(bind)
        if bind.dialect.name == "sqlite":
            for action in ("update", "delete"):
                op.execute(f"CREATE TRIGGER {table.name}_no_{action} BEFORE {action.upper()} ON {table.name} "
                           "BEGIN SELECT RAISE(ABORT, 'QC evidence is append-only'); END")
        elif bind.dialect.name == "postgresql":
            op.execute("CREATE OR REPLACE FUNCTION carton_mark_qc_immutable() RETURNS trigger AS $$ "
                       "BEGIN RAISE EXCEPTION 'QC evidence is append-only'; END; $$ LANGUAGE plpgsql")
            op.execute(f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
                       "FOR EACH ROW EXECUTE FUNCTION carton_mark_qc_immutable()")


def downgrade():
    bind = op.get_bind()
    tables = _tables()
    for table in tables:
        if bind.execute(sa.select(table.c.id).limit(1)).first():
            raise RuntimeError("Cannot discard retained QC evidence")
    for table in reversed(tables):
        table.drop(bind)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION carton_mark_qc_immutable()")
