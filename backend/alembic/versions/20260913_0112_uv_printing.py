"""UV production core; frozen standalone migration schema."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0112"
down_revision = "20260912_0111"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('uv_factories',
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_table('uv_machines',
        sa.Column('code', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('brand', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('model', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('price_group', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('ink_material', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('admin_status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('runtime_status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('last_heartbeat_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.Column('current_task_name', sa.Text(), nullable=True, primary_key=False),
        sa.Column('progress_pct', sa.Numeric(precision=9, scale=4), nullable=True, primary_key=False),
        sa.Column('connector_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('connector_mode', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('capabilities', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'code'),
    )
    op.create_index('ix_uv_machines_factory_id', 'uv_machines', ['factory_id'], unique=False)
    op.create_table('uv_operations',
        sa.Column('actor_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('operation_id', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('command', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'actor_id', 'operation_id'),
    )
    op.create_index('ix_uv_operations_factory_id', 'uv_operations', ['factory_id'], unique=False)
    op.create_table('uv_products',
        sa.Column('product_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('external_ref', sa.String(length=255), nullable=True, primary_key=False),
        sa.Column('external_ref_kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('aliases', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'product_no'),
    )
    op.create_index('ix_uv_products_factory_id', 'uv_products', ['factory_id'], unique=False)
    op.create_table('uv_shift_templates',
        sa.Column('label', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('start_local', sa.String(length=5), nullable=False, primary_key=False),
        sa.Column('end_local', sa.String(length=5), nullable=False, primary_key=False),
        sa.Column('effective_from', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('effective_to', sa.String(length=10), nullable=True, primary_key=False),
        sa.Column('break_minutes', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
    )
    op.create_index('ix_uv_shift_templates_factory_id', 'uv_shift_templates', ['factory_id'], unique=False)
    op.create_table('uv_workers',
        sa.Column('employee_profile_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('employee_no', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('display_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('role', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('employ_state', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('left_on', sa.String(length=10), nullable=True, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'employee_no'),
    )
    op.create_index('ix_uv_workers_factory_id', 'uv_workers', ['factory_id'], unique=False)
    op.create_table('uv_assignment_batches',
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), sa.ForeignKey('uv_machines.id'), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'business_date', 'shift', 'machine_id'),
    )
    op.create_index('ix_uv_assignment_batches_factory_id', 'uv_assignment_batches', ['factory_id'], unique=False)
    op.create_table('uv_process_versions',
        sa.Column('product_id', sa.String(length=64), sa.ForeignKey('uv_products.id'), nullable=False, primary_key=False),
        sa.Column('version_label', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('effective_from', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('material', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('pieces_per_board', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('board_seconds', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('width_cm', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('length_cm', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('pricing_area_cm2', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('machine_area_m2', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('ink_reference_ml', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('product_id', 'version_label'),
        sa.CheckConstraint('pieces_per_board IS NULL OR pieces_per_board > 0'),
    )
    op.create_index('ix_uv_process_versions_product_id', 'uv_process_versions', ['product_id'], unique=False)
    op.create_index('ix_uv_process_versions_factory_id', 'uv_process_versions', ['factory_id'], unique=False)
    op.create_table('uv_assignments',
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), sa.ForeignKey('uv_machines.id'), nullable=False, primary_key=False),
        sa.Column('worker_id', sa.String(length=64), sa.ForeignKey('uv_workers.id'), nullable=False, primary_key=False),
        sa.Column('share', sa.Numeric(precision=18, scale=6), nullable=False, primary_key=False),
        sa.Column('work_batch', sa.String(length=64), sa.ForeignKey('uv_assignment_batches.id'), nullable=False, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
    )
    op.create_index('ix_uv_assignments_business_date', 'uv_assignments', ['business_date'], unique=False)
    op.create_index('ix_uv_assignments_factory_id', 'uv_assignments', ['factory_id'], unique=False)
    op.create_table('uv_jobs',
        sa.Column('machine_id', sa.String(length=64), sa.ForeignKey('uv_machines.id'), nullable=False, primary_key=False),
        sa.Column('source_job_id', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('source_event_id', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('connector_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('generation', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('raw_task_name', sa.Text(), nullable=False, primary_key=False),
        sa.Column('raw_product_name', sa.Text(), nullable=True, primary_key=False),
        sa.Column('product_id', sa.String(length=64), sa.ForeignKey('uv_products.id'), nullable=True, primary_key=False),
        sa.Column('process_version_id', sa.String(length=64), sa.ForeignKey('uv_process_versions.id'), nullable=True, primary_key=False),
        sa.Column('state', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('reconcile_note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('ignored', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('started_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.Column('completed_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.Column('time_evidence', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('raw_count', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('raw_unit', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('suggested_piece_qty', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('print_time_seconds', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('print_area_m2', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('ink_total_ml', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('ink_by_color', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('resolution', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('color_count', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('duplicate_suspect', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'connector_id', 'generation', 'source_job_id'),
    )
    op.create_index('ix_uv_jobs_factory_id', 'uv_jobs', ['factory_id'], unique=False)
    op.create_table('uv_rate_versions',
        sa.Column('rate_kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('product_id', sa.String(length=64), sa.ForeignKey('uv_products.id'), nullable=True, primary_key=False),
        sa.Column('process_version_id', sa.String(length=64), sa.ForeignKey('uv_process_versions.id'), nullable=True, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), sa.ForeignKey('uv_machines.id'), nullable=True, primary_key=False),
        sa.Column('price_group', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=False, primary_key=False),
        sa.Column('unit_price', sa.Numeric(precision=24, scale=6), nullable=False, primary_key=False),
        sa.Column('effective_from', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('effective_to', sa.String(length=10), nullable=True, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.CheckConstraint('unit_price >= 0'),
    )
    op.create_index('ix_uv_rate_versions_factory_id', 'uv_rate_versions', ['factory_id'], unique=False)
    op.create_table('uv_reports',
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('shift_template_version_id', sa.String(length=64), sa.ForeignKey('uv_shift_templates.id'), nullable=False, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), sa.ForeignKey('uv_machines.id'), nullable=False, primary_key=False),
        sa.Column('product_id', sa.String(length=64), sa.ForeignKey('uv_products.id'), nullable=False, primary_key=False),
        sa.Column('process_version_id', sa.String(length=64), sa.ForeignKey('uv_process_versions.id'), nullable=False, primary_key=False),
        sa.Column('product_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('product_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('source_kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('reported_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('good_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('defective_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('pending_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('semi_finished_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('notes', sa.Text(), nullable=False, primary_key=False),
        sa.Column('replaces_report_id', sa.String(length=64), sa.ForeignKey('uv_reports.id'), nullable=True, primary_key=False),
        sa.Column('correction_reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('confirmed_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.CheckConstraint('reported_qty = good_qty + defective_qty + pending_qty + semi_finished_qty'),
        sa.CheckConstraint('good_qty >= 0 AND defective_qty >= 0 AND pending_qty >= 0 AND semi_finished_qty >= 0'),
    )
    op.create_index('ix_uv_reports_factory_id', 'uv_reports', ['factory_id'], unique=False)
    op.create_index('ix_uv_reports_business_date', 'uv_reports', ['business_date'], unique=False)
    op.create_table('uv_allocations',
        sa.Column('job_id', sa.String(length=64), sa.ForeignKey('uv_jobs.id'), nullable=False, primary_key=False),
        sa.Column('report_id', sa.String(length=64), sa.ForeignKey('uv_reports.id'), nullable=False, primary_key=False),
        sa.Column('piece_qty', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('reversed', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.CheckConstraint('piece_qty > 0'),
    )
    op.create_index('ix_uv_allocations_factory_id', 'uv_allocations', ['factory_id'], unique=False)
    op.create_index('ix_uv_allocations_report_id', 'uv_allocations', ['report_id'], unique=False)
    op.create_index('ix_uv_allocations_job_id', 'uv_allocations', ['job_id'], unique=False)
    op.create_table('uv_rate_snapshots',
        sa.Column('report_id', sa.String(length=64), sa.ForeignKey('uv_reports.id'), nullable=False, primary_key=False),
        sa.Column('rate_kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('rate_version_id', sa.String(length=64), sa.ForeignKey('uv_rate_versions.id'), nullable=True, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=True, primary_key=False),
        sa.Column('unit_price', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('pricing_area_cm2', sa.Numeric(precision=24, scale=6), nullable=True, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('report_id', 'rate_kind'),
    )
    op.create_index('ix_uv_rate_snapshots_report_id', 'uv_rate_snapshots', ['report_id'], unique=False)
    op.create_index('ix_uv_rate_snapshots_factory_id', 'uv_rate_snapshots', ['factory_id'], unique=False)
    op.create_table('uv_report_evidence',
        sa.Column('report_id', sa.String(length=64), sa.ForeignKey('uv_reports.id'), nullable=False, primary_key=False),
        sa.Column('job_id', sa.String(length=64), sa.ForeignKey('uv_jobs.id'), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('report_id', 'job_id'),
    )
    op.create_index('ix_uv_report_evidence_factory_id', 'uv_report_evidence', ['factory_id'], unique=False)
    op.create_table('uv_report_workers',
        sa.Column('report_id', sa.String(length=64), sa.ForeignKey('uv_reports.id'), nullable=False, primary_key=False),
        sa.Column('worker_id', sa.String(length=64), sa.ForeignKey('uv_workers.id'), nullable=False, primary_key=False),
        sa.Column('employee_no', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('worker_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.UniqueConstraint('report_id', 'worker_id'),
    )
    op.create_index('ix_uv_report_workers_report_id', 'uv_report_workers', ['report_id'], unique=False)
    op.create_index('ix_uv_report_workers_factory_id', 'uv_report_workers', ['factory_id'], unique=False)


def downgrade():
    op.drop_table('uv_report_workers')
    op.drop_table('uv_report_evidence')
    op.drop_table('uv_rate_snapshots')
    op.drop_table('uv_allocations')
    op.drop_table('uv_reports')
    op.drop_table('uv_rate_versions')
    op.drop_table('uv_jobs')
    op.drop_table('uv_assignments')
    op.drop_table('uv_process_versions')
    op.drop_table('uv_assignment_batches')
    op.drop_table('uv_workers')
    op.drop_table('uv_shift_templates')
    op.drop_table('uv_products')
    op.drop_table('uv_operations')
    op.drop_table('uv_machines')
    op.drop_table('uv_factories')
