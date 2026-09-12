"""Native four-factory spray workshop schema; no historical stock or wage seeds."""
from alembic import op
import sqlalchemy as sa

revision = "20260911_0106"
down_revision = "20260908_0105"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('spray_factories',
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.CheckConstraint("factory_id IN ('huaxing','huakang-a','huakang-b','huadeng')"),
    )
    op.create_table('spray_imports',
        sa.Column('filename', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('content', sa.LargeBinary(), nullable=False, primary_key=False),
        sa.Column('format', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('mapping', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('factory_id', 'sha256'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_imports_factory_id', 'spray_imports', ['factory_id'], unique=False)
    op.create_table('spray_operations',
        sa.Column('operation_id', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'operation_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_operations_factory_id', 'spray_operations', ['factory_id'], unique=False)
    op.create_table('spray_orders',
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('customer', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('customer_factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('source_ref', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('due_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('expected_material_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('priority', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('close_reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('factory_id', 'document_no'),
    )
    op.create_index('ix_spray_orders_factory_id', 'spray_orders', ['factory_id'], unique=False)
    op.create_index('ix_spray_orders_due_date', 'spray_orders', ['due_date'], unique=False)
    op.create_index('ix_spray_orders_customer', 'spray_orders', ['customer'], unique=False)
    op.create_table('spray_purchases',
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('supplier', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('material', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('unit', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('base_unit', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('conversion', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('conversion_evidence', sa.Text(), nullable=False, primary_key=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('factory_id', 'document_no', 'material'),
    )
    op.create_index('ix_spray_purchases_factory_id', 'spray_purchases', ['factory_id'], unique=False)
    op.create_table('spray_rates',
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('rule_code', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('quantity_basis', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('effective_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('parameters', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('evidence', sa.Text(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_rates_factory_id', 'spray_rates', ['factory_id'], unique=False)
    op.create_table('spray_reports',
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('team', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('corrected_report_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['corrected_report_id', 'factory_id'], ['spray_reports.id', 'spray_reports.factory_id']),
        sa.ForeignKeyConstraint(['corrected_report_id'], ['spray_reports.id']),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_reports_business_date', 'spray_reports', ['business_date'], unique=False)
    op.create_index('ix_spray_reports_factory_id', 'spray_reports', ['factory_id'], unique=False)
    op.create_table('spray_resources',
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('capability', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('workers', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('machine_rate', sa.Numeric(precision=18, scale=6), nullable=True, primary_key=False),
        sa.Column('person_minutes', sa.Numeric(precision=18, scale=6), nullable=True, primary_key=False),
        sa.Column('setup_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('calendar', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('factory_id', 'name'),
    )
    op.create_index('ix_spray_resources_factory_id', 'spray_resources', ['factory_id'], unique=False)
    op.create_table('spray_returnables',
        sa.Column('customer', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('unit', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_returnables_factory_id', 'spray_returnables', ['factory_id'], unique=False)
    op.create_table('spray_scenarios',
        sa.Column('base_revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('changes', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_scenarios_factory_id', 'spray_scenarios', ['factory_id'], unique=False)
    op.create_table('spray_settlements',
        sa.Column('customer', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('period', sa.String(length=7), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('factory_id', 'customer', 'period', 'currency'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_settlements_factory_id', 'spray_settlements', ['factory_id'], unique=False)
    op.create_table('spray_shipments',
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('customer', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'document_no'),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_shipments_customer', 'spray_shipments', ['customer'], unique=False)
    op.create_index('ix_spray_shipments_factory_id', 'spray_shipments', ['factory_id'], unique=False)
    op.create_index('ix_spray_shipments_business_date', 'spray_shipments', ['business_date'], unique=False)
    op.create_table('spray_import_rows',
        sa.Column('import_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('sheet', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('row_number', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('cells', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('role', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['import_id'], ['spray_imports.id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['import_id', 'factory_id'], ['spray_imports.id', 'spray_imports.factory_id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
    )
    op.create_index('ix_spray_import_rows_import_id', 'spray_import_rows', ['import_id'], unique=False)
    op.create_index('ix_spray_import_rows_factory_id', 'spray_import_rows', ['factory_id'], unique=False)
    op.create_table('spray_material_events',
        sa.Column('purchase_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('order_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('cost', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['order_id'], ['spray_orders.id']),
        sa.ForeignKeyConstraint(['order_id', 'factory_id'], ['spray_orders.id', 'spray_orders.factory_id']),
        sa.UniqueConstraint('factory_id', 'document_no', 'purchase_id', 'kind'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['purchase_id'], ['spray_purchases.id']),
        sa.ForeignKeyConstraint(['purchase_id', 'factory_id'], ['spray_purchases.id', 'spray_purchases.factory_id']),
    )
    op.create_index('ix_spray_material_events_purchase_id', 'spray_material_events', ['purchase_id'], unique=False)
    op.create_index('ix_spray_material_events_factory_id', 'spray_material_events', ['factory_id'], unique=False)
    op.create_table('spray_order_lines',
        sa.Column('order_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('product_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('part_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('unit', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('per_set', sa.Numeric(precision=18, scale=6), nullable=True, primary_key=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=True, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('price_reference', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('route_version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('prep_ready_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('prep_reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['order_id'], ['spray_orders.id']),
        sa.ForeignKeyConstraint(['order_id', 'factory_id'], ['spray_orders.id', 'spray_orders.factory_id']),
    )
    op.create_index('ix_spray_order_lines_product_no', 'spray_order_lines', ['product_no'], unique=False)
    op.create_index('ix_spray_order_lines_factory_id', 'spray_order_lines', ['factory_id'], unique=False)
    op.create_index('ix_spray_order_lines_order_id', 'spray_order_lines', ['order_id'], unique=False)
    op.create_table('spray_batches',
        sa.Column('line_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('source_line', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('received', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'document_no', 'source_line'),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['line_id', 'factory_id'], ['spray_order_lines.id', 'spray_order_lines.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['line_id'], ['spray_order_lines.id']),
    )
    op.create_index('ix_spray_batches_line_id', 'spray_batches', ['line_id'], unique=False)
    op.create_index('ix_spray_batches_factory_id', 'spray_batches', ['factory_id'], unique=False)
    op.create_table('spray_steps',
        sa.Column('line_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('sequence', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('capability', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('color', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('wait_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('line_id', 'sequence'),
        sa.ForeignKeyConstraint(['line_id'], ['spray_order_lines.id']),
        sa.ForeignKeyConstraint(['line_id', 'factory_id'], ['spray_order_lines.id', 'spray_order_lines.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_steps_line_id', 'spray_steps', ['line_id'], unique=False)
    op.create_index('ix_spray_steps_factory_id', 'spray_steps', ['factory_id'], unique=False)
    op.create_table('spray_movements',
        sa.Column('batch_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('event_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('from_state', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('to_state', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('available_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.CheckConstraint('quantity > 0'),
        sa.ForeignKeyConstraint(['batch_id', 'factory_id'], ['spray_batches.id', 'spray_batches.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['batch_id'], ['spray_batches.id']),
    )
    op.create_index('ix_spray_movements_batch_id', 'spray_movements', ['batch_id'], unique=False)
    op.create_index('ix_spray_movements_factory_id', 'spray_movements', ['factory_id'], unique=False)
    op.create_index('ix_spray_movements_event_id', 'spray_movements', ['event_id'], unique=False)
    op.create_table('spray_shipment_lines',
        sa.Column('shipment_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('original_line_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('price_reference', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['original_line_id', 'factory_id'], ['spray_shipment_lines.id', 'spray_shipment_lines.factory_id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['batch_id'], ['spray_batches.id']),
        sa.ForeignKeyConstraint(['shipment_id', 'factory_id'], ['spray_shipments.id', 'spray_shipments.factory_id']),
        sa.ForeignKeyConstraint(['original_line_id'], ['spray_shipment_lines.id']),
        sa.ForeignKeyConstraint(['batch_id', 'factory_id'], ['spray_batches.id', 'spray_batches.factory_id']),
        sa.ForeignKeyConstraint(['shipment_id'], ['spray_shipments.id']),
    )
    op.create_index('ix_spray_shipment_lines_shipment_id', 'spray_shipment_lines', ['shipment_id'], unique=False)
    op.create_index('ix_spray_shipment_lines_factory_id', 'spray_shipment_lines', ['factory_id'], unique=False)
    op.create_table('spray_tasks',
        sa.Column('batch_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('step_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('resource_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('reported', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('start_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('end_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('workers', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('input_state', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('duration_source', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['step_id'], ['spray_steps.id']),
        sa.ForeignKeyConstraint(['resource_id', 'factory_id'], ['spray_resources.id', 'spray_resources.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['batch_id', 'factory_id'], ['spray_batches.id', 'spray_batches.factory_id']),
        sa.ForeignKeyConstraint(['resource_id'], ['spray_resources.id']),
        sa.ForeignKeyConstraint(['batch_id'], ['spray_batches.id']),
        sa.ForeignKeyConstraint(['step_id', 'factory_id'], ['spray_steps.id', 'spray_steps.factory_id']),
    )
    op.create_index('ix_spray_tasks_factory_id', 'spray_tasks', ['factory_id'], unique=False)
    op.create_index('ix_spray_tasks_batch_id', 'spray_tasks', ['batch_id'], unique=False)
    op.create_index('ix_spray_tasks_resource_id', 'spray_tasks', ['resource_id'], unique=False)
    op.create_index('ix_spray_tasks_start_at', 'spray_tasks', ['start_at'], unique=False)
    op.create_table('spray_report_lines',
        sa.Column('report_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('task_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('activity', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('regular_qty', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('overtime_qty', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('regular_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('overtime_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('good', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('held', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('rework', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('scrap', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('people', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('wage_status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('calculation', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.ForeignKeyConstraint(['task_id', 'factory_id'], ['spray_tasks.id', 'spray_tasks.factory_id']),
        sa.ForeignKeyConstraint(['task_id'], ['spray_tasks.id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['report_id'], ['spray_reports.id']),
        sa.ForeignKeyConstraint(['report_id', 'factory_id'], ['spray_reports.id', 'spray_reports.factory_id']),
    )
    op.create_index('ix_spray_report_lines_factory_id', 'spray_report_lines', ['factory_id'], unique=False)
    op.create_index('ix_spray_report_lines_report_id', 'spray_report_lines', ['report_id'], unique=False)
    op.create_table('spray_settlement_lines',
        sa.Column('settlement_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('shipment_line_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['shipment_line_id', 'factory_id'], ['spray_shipment_lines.id', 'spray_shipment_lines.factory_id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['settlement_id'], ['spray_settlements.id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('shipment_line_id'),
        sa.ForeignKeyConstraint(['settlement_id', 'factory_id'], ['spray_settlements.id', 'spray_settlements.factory_id']),
        sa.ForeignKeyConstraint(['shipment_line_id'], ['spray_shipment_lines.id']),
    )
    op.create_index('ix_spray_settlement_lines_factory_id', 'spray_settlement_lines', ['factory_id'], unique=False)
    op.create_index('ix_spray_settlement_lines_settlement_id', 'spray_settlement_lines', ['settlement_id'], unique=False)
    op.bulk_insert(sa.table("spray_factories", sa.column("factory_id"), sa.column("revision")), [{"factory_id": f, "revision": 0} for f in ("huaxing", "huakang-a", "huakang-b", "huadeng")])

def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM spray_imports LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_operations LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_orders LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_purchases LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_rates LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_reports LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_resources LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_returnables LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_scenarios LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_settlements LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_shipments LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_import_rows LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_material_events LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_order_lines LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_batches LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_steps LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_movements LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_shipment_lines LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_tasks LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_report_lines LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    if bind.execute(sa.text("SELECT 1 FROM spray_settlement_lines LIMIT 1")).first():
        raise RuntimeError("喷油模块已有业务或证据记录，禁止有损回退；请恢复已验证备份")
    op.drop_table('spray_settlement_lines')
    op.drop_table('spray_report_lines')
    op.drop_table('spray_tasks')
    op.drop_table('spray_shipment_lines')
    op.drop_table('spray_movements')
    op.drop_table('spray_steps')
    op.drop_table('spray_batches')
    op.drop_table('spray_order_lines')
    op.drop_table('spray_material_events')
    op.drop_table('spray_import_rows')
    op.drop_table('spray_shipments')
    op.drop_table('spray_settlements')
    op.drop_table('spray_scenarios')
    op.drop_table('spray_returnables')
    op.drop_table('spray_resources')
    op.drop_table('spray_reports')
    op.drop_table('spray_rates')
    op.drop_table('spray_purchases')
    op.drop_table('spray_orders')
    op.drop_table('spray_operations')
    op.drop_table('spray_imports')
    op.drop_table('spray_factories')
