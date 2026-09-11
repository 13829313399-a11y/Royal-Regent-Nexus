"""Normalize shared resource reservations and employee payable lines."""
from alembic import op
import sqlalchemy as sa
from uuid import uuid4

revision = "20260911_0110"
down_revision = "20260911_0109"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('spray_payroll_lines',
        sa.Column('payroll_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('employee', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('regular_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('overtime_hours', sa.Numeric(precision=12, scale=6), nullable=False, primary_key=False),
        sa.Column('earned', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('guarantee', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('signed_difference', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('subsidy', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('payable', sa.Numeric(precision=18, scale=2), nullable=False, primary_key=False),
        sa.Column('source_lines', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['payroll_id', 'factory_id'], ['spray_payrolls.id', 'spray_payrolls.factory_id']),
        sa.ForeignKeyConstraint(['payroll_id'], ['spray_payrolls.id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('payroll_id', 'employee'),
    )
    op.create_index('ix_spray_payroll_lines_factory_id','spray_payroll_lines',['factory_id'],unique=False)
    op.create_index('ix_spray_payroll_lines_payroll_id','spray_payroll_lines',['payroll_id'],unique=False)
    op.create_table('spray_task_allocations',
        sa.Column('task_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('shared_resource_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('quantity', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('factory_id', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.CheckConstraint('quantity > 0'),
        sa.ForeignKeyConstraint(['shared_resource_id'], ['spray_shared_resources.id']),
        sa.ForeignKeyConstraint(['task_id', 'factory_id'], ['spray_tasks.id', 'spray_tasks.factory_id']),
        sa.ForeignKeyConstraint(['factory_id'], ['spray_factories.factory_id']),
        sa.ForeignKeyConstraint(['task_id'], ['spray_tasks.id']),
        sa.ForeignKeyConstraint(['shared_resource_id', 'factory_id'], ['spray_shared_resources.id', 'spray_shared_resources.factory_id']),
        sa.UniqueConstraint('id', 'factory_id'),
        sa.UniqueConstraint('task_id', 'shared_resource_id'),
    )
    op.create_index('ix_spray_task_allocations_factory_id','spray_task_allocations',['factory_id'],unique=False)
    op.create_index('ix_spray_task_allocations_shared_resource_id','spray_task_allocations',['shared_resource_id'],unique=False)
    op.create_index('ix_spray_task_allocations_task_id','spray_task_allocations',['task_id'],unique=False)
    bind=op.get_bind()
    tasks=sa.table('spray_tasks',sa.column('id'),sa.column('factory_id'),sa.column('created_at'),sa.column('created_by'),sa.column('shared_allocations',sa.JSON()))
    allocations=sa.Table('spray_task_allocations',sa.MetaData(),autoload_with=bind)
    for task in bind.execute(sa.select(tasks)).mappings():
        for item in task['shared_allocations'] or []:
            bind.execute(allocations.insert().values(id=uuid4().hex,factory_id=task['factory_id'],created_at=task['created_at'],created_by=task['created_by'],revision=1,task_id=task['id'],shared_resource_id=item['id'],quantity=item['quantity']))
    payrolls=sa.table('spray_payrolls',sa.column('id'),sa.column('factory_id'),sa.column('created_at'),sa.column('created_by'),sa.column('snapshot',sa.JSON()))
    payroll_lines=sa.Table('spray_payroll_lines',sa.MetaData(),autoload_with=bind)
    for payroll in bind.execute(sa.select(payrolls)).mappings():
        for employee in payroll['snapshot'].get('employees',[]):
            values={key:employee[key] for key in ('employee','name','regular_hours','overtime_hours','earned','guarantee','signed_difference','subsidy','payable')}
            bind.execute(payroll_lines.insert().values(id=uuid4().hex,factory_id=payroll['factory_id'],created_at=payroll['created_at'],created_by=payroll['created_by'],revision=1,payroll_id=payroll['id'],source_lines=employee['tasks'],**values))

def downgrade():
    bind=op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM spray_payroll_lines LIMIT 1")).first():
        raise RuntimeError("已有共享占用或员工应付明细，禁止有损回退")
    if bind.execute(sa.text("SELECT 1 FROM spray_task_allocations LIMIT 1")).first():
        raise RuntimeError("已有共享占用或员工应付明细，禁止有损回退")
    op.drop_table('spray_task_allocations')
    op.drop_table('spray_payroll_lines')
