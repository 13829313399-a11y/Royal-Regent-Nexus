"""Versioned sample, workshop and supplier gift collaboration; no historical backfill."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_0168"
down_revision = "20261019_0167"
branch_labels = None
depends_on = None

NAMES = ('carton_special_requests', 'carton_special_lines', 'carton_special_versions', 'carton_special_attachments', 'carton_special_messages', 'carton_special_shipments', 'carton_special_shipment_lines', 'carton_special_receipt_links')


def upgrade():
    op.create_table('carton_special_requests',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('supplier_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('request_no', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('title', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('requester_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('workshop_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('customer_code', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('purpose', sa.Text(), nullable=False, primary_key=False),
        sa.Column('required_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('current_version_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('quote_version_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('pricing_kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('promised_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['supplier_id', 'factory_id'], ['carton_suppliers.id', 'carton_suppliers.factory_id']),
        sa.CheckConstraint("kind IN ('SAMPLE','WORKSHOP_MISC','SUPPLIER_GIFT')"),
        sa.UniqueConstraint('factory_id', 'request_no'),
        sa.CheckConstraint("status IN ('SUBMITTED','SENT','QUOTED','READY','PARTIALLY_RECEIVED','COMPLETED','CANCELLED')"),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.CheckConstraint('revision >= 1'))
    op.create_index('ix_carton_special_requests_factory_id', 'carton_special_requests', ['factory_id'], unique=False)
    op.create_table('carton_special_lines',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('line_no', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('item_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('packaging_type', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('paper_quality', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('specification', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('dimension_unit', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False, primary_key=False),
        sa.Column('unit', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('unit_price', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['request_id', 'factory_id'], ['carton_special_requests.id', 'carton_special_requests.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.CheckConstraint('quantity > 0 AND unit_price >= 0'))
    op.create_index('ix_carton_special_lines_request_id', 'carton_special_lines', ['request_id'], unique=False)
    op.create_table('carton_special_versions',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('action', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('actor_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['request_id', 'factory_id'], ['carton_special_requests.id', 'carton_special_requests.factory_id']),
        sa.UniqueConstraint('request_id', 'revision'))
    op.create_index('ix_carton_special_versions_request_id', 'carton_special_versions', ['request_id'], unique=False)
    op.create_table('carton_special_attachments',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('role', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('filename', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('media_type', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('size', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('content', sa.LargeBinary(), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['request_id', 'factory_id'], ['carton_special_requests.id', 'carton_special_requests.factory_id']),
        sa.CheckConstraint('size > 0 AND size <= 10485760'),
        sa.CheckConstraint("role IN ('REFERENCE','DRAFT','CONFIRMED')"))
    op.create_index('ix_carton_special_attachments_request_id', 'carton_special_attachments', ['request_id'], unique=False)
    op.create_table('carton_special_messages',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('body', sa.Text(), nullable=False, primary_key=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('actor_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('audience', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['request_id', 'factory_id'], ['carton_special_requests.id', 'carton_special_requests.factory_id']))
    op.create_index('ix_carton_special_messages_request_id', 'carton_special_messages', ['request_id'], unique=False)
    op.create_table('carton_special_shipments',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('supplier_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('version_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('delivery_note_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('delivery_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['request_id', 'factory_id'], ['carton_special_requests.id', 'carton_special_requests.factory_id']),
        sa.ForeignKeyConstraint(['version_id', 'factory_id'], ['carton_special_versions.id', 'carton_special_versions.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('factory_id', 'supplier_id', 'delivery_note_no'))
    op.create_index('ix_carton_special_shipments_request_id', 'carton_special_shipments', ['request_id'], unique=False)
    op.create_table('carton_special_shipment_lines',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('shipment_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('request_line_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False, primary_key=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False, primary_key=False),
        sa.UniqueConstraint('shipment_id', 'request_line_id'),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['shipment_id', 'factory_id'], ['carton_special_shipments.id', 'carton_special_shipments.factory_id']),
        sa.CheckConstraint('quantity > 0'),
        sa.ForeignKeyConstraint(['request_line_id', 'factory_id'], ['carton_special_lines.id', 'carton_special_lines.factory_id']))
    op.create_index('ix_carton_special_shipment_lines_shipment_id', 'carton_special_shipment_lines', ['shipment_id'], unique=False)
    op.create_table('carton_special_receipt_links',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('shipment_line_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.Column('receipt_line_id', sa.String(length=96), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['receipt_line_id', 'factory_id'], ['carton_receipt_lines.id', 'carton_receipt_lines.factory_id']),
        sa.UniqueConstraint('receipt_line_id'),
        sa.ForeignKeyConstraint(['shipment_line_id', 'factory_id'], ['carton_special_shipment_lines.id', 'carton_special_shipment_lines.factory_id']))
    op.create_index('ix_carton_special_receipt_links_shipment_line_id', 'carton_special_receipt_links', ['shipment_line_id'], unique=False)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION carton_special_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Carton special evidence is immutable'; END; $$ LANGUAGE plpgsql")
    for name in ('carton_special_versions', 'carton_special_attachments', 'carton_special_messages', 'carton_special_shipments', 'carton_special_shipment_lines', 'carton_special_receipt_links'):
        if bind.dialect.name == "sqlite":
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT, 'Carton special evidence is immutable'); END")
        elif bind.dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION carton_special_immutable()")


def downgrade():
    bind = op.get_bind()
    if any(bind.scalar(sa.text(f"SELECT count(*) FROM {name}")) for name in NAMES):
        raise RuntimeError("Carton request, quotation and receipt evidence must be preserved; downgrade refused")
    for name in reversed(NAMES): op.drop_table(name)
    if bind.dialect.name == "postgresql": op.execute("DROP FUNCTION carton_special_immutable()")
