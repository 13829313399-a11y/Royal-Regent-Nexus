"""Frozen UV inventory, cost and settlement schema; no historical business data is imported."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0113"
down_revision = "20260913_0112"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('uv_ink_skus',
        sa.Column('supplier', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('material', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('color', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('color_aliases', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('package_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('location', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('threshold_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('available_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('stock_value', sa.Numeric(precision=26, scale=8), nullable=True, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=True, primary_key=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.CheckConstraint('available_ml >= 0 AND package_ml > 0 AND threshold_ml >= 0'),
        sa.UniqueConstraint('factory_id', 'supplier', 'material', 'color', 'location'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_ink_skus_factory_id', 'uv_ink_skus', ['factory_id'], unique=False)
    op.create_table('uv_ink_movements',
        sa.Column('sku_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('occurred_on', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('posted_on', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('quantity_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('signed_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('bottle_input', sa.Numeric(precision=20, scale=6), nullable=True, primary_key=False),
        sa.Column('unit_cost', sa.Numeric(precision=26, scale=8), nullable=True, primary_key=False),
        sa.Column('cost_value', sa.Numeric(precision=26, scale=8), nullable=True, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=True, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('purpose', sa.Text(), nullable=False, primary_key=False),
        sa.Column('source_doc', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('evidence', sa.Text(), nullable=False, primary_key=False),
        sa.Column('source_movement_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('reverses_movement_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('reversed_by_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('balance_after_ml', sa.Numeric(precision=20, scale=6), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.CheckConstraint('quantity_ml > 0 AND balance_after_ml >= 0'),
        sa.ForeignKeyConstraint(['sku_id'], ['uv_ink_skus.id']),
        sa.ForeignKeyConstraint(['source_movement_id'], ['uv_ink_movements.id']),
        sa.ForeignKeyConstraint(['reverses_movement_id'], ['uv_ink_movements.id']),
        sa.UniqueConstraint('reverses_movement_id'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_ink_movements_factory_id', 'uv_ink_movements', ['factory_id'], unique=False)
    op.create_index('ix_uv_ink_movements_occurred_on', 'uv_ink_movements', ['occurred_on'], unique=False)
    op.create_index('ix_uv_ink_movements_posted_on', 'uv_ink_movements', ['posted_on'], unique=False)
    op.create_index('ix_uv_ink_movements_sku_id', 'uv_ink_movements', ['sku_id'], unique=False)
    op.create_table('uv_expenses',
        sa.Column('category', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('occurred_on', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('period', sa.String(length=7), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=22, scale=6), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=False, primary_key=False),
        sa.Column('machine_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('evidence', sa.Text(), nullable=False, primary_key=False),
        sa.Column('source', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('reverses_expense_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['reverses_expense_id'], ['uv_expenses.id']),
        sa.UniqueConstraint('reverses_expense_id'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_expenses_factory_id', 'uv_expenses', ['factory_id'], unique=False)
    op.create_index('ix_uv_expenses_occurred_on', 'uv_expenses', ['occurred_on'], unique=False)
    op.create_index('ix_uv_expenses_period', 'uv_expenses', ['period'], unique=False)
    op.create_table('uv_monthly_policies',
        sa.Column('month', sa.String(length=7), nullable=False, primary_key=False),
        sa.Column('working_days', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('allocation_method', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('rent', sa.JSON(), nullable=True, primary_key=False),
        sa.Column('utilities', sa.JSON(), nullable=True, primary_key=False),
        sa.Column('management_wage', sa.JSON(), nullable=True, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'month', 'version'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_monthly_policies_factory_id', 'uv_monthly_policies', ['factory_id'], unique=False)
    op.create_index('ix_uv_monthly_policies_month', 'uv_monthly_policies', ['month'], unique=False)
    op.create_table('uv_policy_allocations',
        sa.Column('policy_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('category', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=22, scale=6), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['policy_id'], ['uv_monthly_policies.id']),
        sa.UniqueConstraint('policy_id', 'business_date', 'category'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_policy_allocations_business_date', 'uv_policy_allocations', ['business_date'], unique=False)
    op.create_index('ix_uv_policy_allocations_factory_id', 'uv_policy_allocations', ['factory_id'], unique=False)
    op.create_index('ix_uv_policy_allocations_policy_id', 'uv_policy_allocations', ['policy_id'], unique=False)
    op.create_table('uv_pricing_quotes',
        sa.Column('label', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('product_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('input', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('adopted_rate_version_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('note', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_pricing_quotes_factory_id', 'uv_pricing_quotes', ['factory_id'], unique=False)
    op.create_table('uv_periods',
        sa.Column('period', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'period'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_periods_factory_id', 'uv_periods', ['factory_id'], unique=False)
    op.create_table('uv_payroll_batches',
        sa.Column('date_from', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('date_to', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=8), nullable=True, primary_key=False),
        sa.Column('status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('source_versions', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('adjustment_of', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['adjustment_of'], ['uv_payroll_batches.id']),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_payroll_batches_date_from', 'uv_payroll_batches', ['date_from'], unique=False)
    op.create_index('ix_uv_payroll_batches_date_to', 'uv_payroll_batches', ['date_to'], unique=False)
    op.create_index('ix_uv_payroll_batches_factory_id', 'uv_payroll_batches', ['factory_id'], unique=False)
    op.create_table('uv_payroll_batch_lines',
        sa.Column('batch_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('worker_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('worker_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=3), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=22, scale=6), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['batch_id'], ['uv_payroll_batches.id']),
        sa.UniqueConstraint('batch_id', 'worker_id'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_payroll_batch_lines_batch_id', 'uv_payroll_batch_lines', ['batch_id'], unique=False)
    op.create_index('ix_uv_payroll_batch_lines_factory_id', 'uv_payroll_batch_lines', ['factory_id'], unique=False)
    op.create_table('uv_import_batches',
        sa.Column('kind', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('file_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('mapping', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('rows', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('errors', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('applied_ids', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.UniqueConstraint('factory_id', 'kind', 'sha256'),
        sa.CheckConstraint("factory_id = 'huakang-a'"),
    )
    op.create_index('ix_uv_import_batches_factory_id', 'uv_import_batches', ['factory_id'], unique=False)

def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM uv_import_batches LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_payroll_batch_lines LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_payroll_batches LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_periods LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_pricing_quotes LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_policy_allocations LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_monthly_policies LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_expenses LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_ink_movements LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    if bind.execute(sa.text("SELECT 1 FROM uv_ink_skus LIMIT 1")).first():
        raise RuntimeError("Refusing to drop populated UV financial tables; use an audited recovery procedure")
    op.drop_table('uv_import_batches')
    op.drop_table('uv_payroll_batch_lines')
    op.drop_table('uv_payroll_batches')
    op.drop_table('uv_periods')
    op.drop_table('uv_pricing_quotes')
    op.drop_table('uv_policy_allocations')
    op.drop_table('uv_monthly_policies')
    op.drop_table('uv_expenses')
    op.drop_table('uv_ink_movements')
    op.drop_table('uv_ink_skus')
