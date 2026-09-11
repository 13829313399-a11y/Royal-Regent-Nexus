"""Spray graph, shared capacity, historical facts and employee payroll."""
from alembic import op
import sqlalchemy as sa

revision = "20260911_0109"
down_revision = "20260911_0108"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('spray_settlements',sa.Column('adjustment_ids',sa.JSON(),nullable=False,server_default='[]'))
    if op.get_bind().dialect.name == "postgresql":
        for table,column in [("spray_movements","from_state"),("spray_movements","to_state"),("spray_tasks","input_state")]:
            op.alter_column(table,column,type_=sa.Text())
    op.add_column('spray_order_lines', sa.Column('graph_route', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('spray_steps', sa.Column('predecessors', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('spray_resources', sa.Column('shared_requirements', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('spray_tasks', sa.Column('shared_allocations', sa.JSON(), nullable=False, server_default='[]'))
    op.create_table('spray_history_facts',
        sa.Column('business_key', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('customer', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('product_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('part_name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('values', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('factory_id', 'business_key'),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_history_facts_business_date','spray_history_facts',['business_date'],unique=False)
    op.create_index('ix_spray_history_facts_document_no','spray_history_facts',['document_no'],unique=False)
    op.create_index('ix_spray_history_facts_factory_id','spray_history_facts',['factory_id'],unique=False)
    op.create_index('ix_spray_history_facts_kind','spray_history_facts',['kind'],unique=False)
    op.create_table('spray_preferences',
        sa.Column('owner', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('factory_id', 'owner', 'kind', 'name'),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_preferences_factory_id','spray_preferences',['factory_id'],unique=False)
    op.create_table('spray_shared_resources',
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('capacity', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('calendar', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('factory_id', 'kind', 'name'),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_shared_resources_factory_id','spray_shared_resources',['factory_id'],unique=False)
    op.create_table('spray_adjustments',
        sa.Column('settlement_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('document_no', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['settlement_id', 'factory_id'], ['spray_settlements.id', 'spray_settlements.factory_id']),
        sa.ForeignKeyConstraint(['settlement_id'], ['spray_settlements.id']),
        sa.UniqueConstraint('factory_id', 'document_no'),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_adjustments_factory_id','spray_adjustments',['factory_id'],unique=False)
    op.create_table('spray_payrolls',
        sa.Column('business_date', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('shift', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('policy_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['policy_id', 'factory_id'], ['spray_rates.id', 'spray_rates.factory_id']),
        sa.ForeignKeyConstraint(['policy_id'], ['spray_rates.id']),
        sa.UniqueConstraint('factory_id', 'business_date', 'shift', 'currency'),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_payrolls_business_date','spray_payrolls',['business_date'],unique=False)
    op.create_index('ix_spray_payrolls_factory_id','spray_payrolls',['factory_id'],unique=False)
    op.create_table('spray_history_links',
        sa.Column('fact_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('import_row_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('role', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['fact_id'], ['spray_history_facts.id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['import_row_id', 'factory_id'], ['spray_import_rows.id', 'spray_import_rows.factory_id']),
        sa.ForeignKeyConstraint(['import_row_id'], ['spray_import_rows.id']),
        sa.ForeignKeyConstraint(['fact_id', 'factory_id'], ['spray_history_facts.id', 'spray_history_facts.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
    )
    op.create_index('ix_spray_history_links_fact_id','spray_history_links',['fact_id'],unique=False)
    op.create_index('ix_spray_history_links_factory_id','spray_history_links',['factory_id'],unique=False)
    op.create_index('ix_spray_history_links_import_row_id','spray_history_links',['import_row_id'],unique=False)

def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM spray_history_facts LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_preferences LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_shared_resources LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_adjustments LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_payrolls LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_history_links LIMIT 1")).first():
        raise RuntimeError("喷油增强已有业务记录，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_order_lines WHERE graph_route = true LIMIT 1")).first():
        raise RuntimeError("已有工艺图，禁止有损回退")
    op.drop_table('spray_history_links')
    op.drop_table('spray_payrolls')
    op.drop_table('spray_adjustments')
    op.drop_table('spray_shared_resources')
    op.drop_table('spray_preferences')
    op.drop_table('spray_history_facts')
    op.drop_column('spray_tasks','shared_allocations')
    op.drop_column('spray_resources','shared_requirements')
    op.drop_column('spray_steps','predecessors')
    op.drop_column('spray_order_lines','graph_route')
    op.drop_column('spray_settlements','adjustment_ids')
