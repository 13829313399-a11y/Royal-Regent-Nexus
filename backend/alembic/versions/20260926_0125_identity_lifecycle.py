"""Add identity history without converting existing personnel or grants."""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0125"
down_revision = "20260924_0124"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("auth_registration_requests") as batch:
        batch.add_column(sa.Column("org_unit_id", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("declared_profile_json", sa.Text(), nullable=False, server_default="{}"))
    op.create_table('iam_org_units',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('parent_id', sa.String(length=64), sa.ForeignKey('iam_org_units.id'), nullable=True),
        sa.Column('legacy_factory_id', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_table('iam_org_departments',
        sa.Column('org_unit_id', sa.String(length=64), sa.ForeignKey('iam_org_units.id'), nullable=False, primary_key=True),
        sa.Column('department_code', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_table('iam_role_versions',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('role_id', sa.String(length=64), sa.ForeignKey('auth_roles.id'), nullable=False),
        sa.Column('definition_hash', sa.String(length=64), nullable=False),
        sa.Column('definition_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False, server_default=''),
        sa.UniqueConstraint('role_id','definition_hash', name='uq_iam_role_definition'),
    )
    op.create_index('ix_iam_role_versions_role_id', 'iam_role_versions', ['role_id'])
    op.create_table('employee_assignments',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('org_unit_id', sa.String(length=64), sa.ForeignKey('iam_org_units.id'), nullable=False),
        sa.Column('department_code', sa.String(length=64), nullable=False),
        sa.Column('official_position_title', sa.String(length=128), nullable=False),
        sa.Column('assignment_type', sa.String(length=16), nullable=False, server_default='regular'),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('valid_from', sa.String(length=32), nullable=False),
        sa.Column('valid_until', sa.String(length=32), nullable=True),
        sa.Column('lifecycle_state', sa.String(length=16), nullable=False, server_default='approved'),
        sa.Column('employment_epoch', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('source_request_id', sa.String(length=128), sa.ForeignKey('auth_access_requests.id'), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('confirmed_by', sa.String(length=64), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('ended_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('revoked_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.CheckConstraint('valid_until IS NULL OR valid_until > valid_from', name='ck_assignment_interval'),
        sa.CheckConstraint("assignment_type IN ('regular','part_time','temporary','acting')", name='ck_assignment_type'),
        sa.CheckConstraint("lifecycle_state IN ('approved','revoked')", name='ck_assignment_state'),
    )
    op.create_index('ix_assignment_user_interval', 'employee_assignments', ['user_id', 'valid_from', 'valid_until'])
    op.create_index('ix_employee_assignments_org_unit_id', 'employee_assignments', ['org_unit_id'])
    op.create_index('ix_employee_assignments_source_request_id', 'employee_assignments', ['source_request_id'])
    op.create_index('ix_employee_assignments_user_id', 'employee_assignments', ['user_id'])
    op.create_table('iam_delegations',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('org_unit_id', sa.String(length=64), sa.ForeignKey('iam_org_units.id'), nullable=False),
        sa.Column('department', sa.String(length=64), nullable=False),
        sa.Column('role_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('factory_ids_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_index('ix_iam_delegations_user_id', 'iam_delegations', ['user_id'])
    op.create_table('iam_handover_items',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('change_request_id', sa.String(length=128), sa.ForeignKey('auth_access_requests.id'), nullable=False),
        sa.Column('adapter_key', sa.String(length=64), nullable=False),
        sa.Column('resource_id', sa.String(length=96), nullable=False),
        sa.Column('responsibility_kind', sa.String(length=64), nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('previous_user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('successor_user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=True),
        sa.Column('expected_resource_revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('completed_at', sa.String(length=32), nullable=False, server_default=''),
        sa.UniqueConstraint('change_request_id','adapter_key','resource_id','responsibility_kind', name='uq_iam_handover_responsibility'),
    )
    op.create_index('ix_iam_handover_items_change_request_id', 'iam_handover_items', ['change_request_id'])
    op.create_table('iam_outbox',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('aggregate_id', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('claimed_until', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('last_error', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('created_at', sa.String(length=32), nullable=False),
    )
    op.create_index('ix_iam_outbox_aggregate_id', 'iam_outbox', ['aggregate_id'])
    op.create_index('ix_iam_outbox_status', 'iam_outbox', ['status'])
    op.create_table('iam_mutation_receipts',
        sa.Column('id', sa.String(length=96), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('operation', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.UniqueConstraint('actor_id','operation','idempotency_key', name='uq_iam_mutation_idempotency'),
    )
    with op.batch_alter_table('employee_profiles') as batch:
        batch.add_column(sa.Column('primary_assignment_id', sa.String(length=96), nullable=True))
        batch.create_foreign_key('fk_employee_profiles_primary_assignment_id', 'employee_assignments', ['primary_assignment_id'], ['id'])
        batch.add_column(sa.Column('primary_org_unit_id', sa.String(length=64), nullable=False, server_default=''))
        batch.add_column(sa.Column('employment_status', sa.String(length=16), nullable=False, server_default='active'))
        batch.add_column(sa.Column('employment_epoch', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('identity_version', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('identity_mode', sa.String(length=16), nullable=False, server_default='legacy'))
        batch.create_index('ix_employee_profiles_identity_mode', ['identity_mode'])
    with op.batch_alter_table('auth_role_binding_metadata') as batch:
        batch.add_column(sa.Column('assignment_id', sa.String(length=96), nullable=True))
        batch.create_foreign_key('fk_auth_role_binding_metadata_assignment_id', 'employee_assignments', ['assignment_id'], ['id'])
        batch.create_index('ix_auth_role_binding_metadata_assignment_id', ['assignment_id'])
        batch.add_column(sa.Column('role_version_id', sa.String(length=96), nullable=True))
        batch.create_foreign_key('fk_auth_role_binding_metadata_role_version_id', 'iam_role_versions', ['role_version_id'], ['id'])
        batch.add_column(sa.Column('scope_ceiling_json', sa.Text(), nullable=True))
        batch.add_column(sa.Column('employment_epoch', sa.Integer(), nullable=True))
    with op.batch_alter_table('auth_user_permission_overrides') as batch:
        batch.add_column(sa.Column('assignment_id', sa.String(length=96), nullable=True))
        batch.create_foreign_key('fk_auth_user_permission_overrides_assignment_id', 'employee_assignments', ['assignment_id'], ['id'])
        batch.create_index('ix_auth_user_permission_overrides_assignment_id', ['assignment_id'])
        batch.add_column(sa.Column('lifecycle_policy', sa.String(length=32), nullable=False, server_default='independent'))
        batch.add_column(sa.Column('employment_epoch', sa.Integer(), nullable=True))
    with op.batch_alter_table('auth_access_requests') as batch:
        batch.add_column(sa.Column('request_type', sa.String(length=48), nullable=False, server_default='access'))
        batch.create_index('ix_auth_access_requests_request_type', ['request_type'])
        batch.add_column(sa.Column('lifecycle_state', sa.String(length=32), nullable=False, server_default=''))
        batch.create_index('ix_auth_access_requests_lifecycle_state', ['lifecycle_state'])
        batch.add_column(sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('effective_at', sa.String(length=32), nullable=False, server_default=''))
        batch.add_column(sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'))
        batch.add_column(sa.Column('result_json', sa.Text(), nullable=False, server_default='{}'))
    op.execute("INSERT INTO auth_iam_state (key, value_json, updated_at) SELECT 'identity_mutation_lock', '{}', '' WHERE NOT EXISTS (SELECT 1 FROM auth_iam_state WHERE key = 'identity_mutation_lock')")


def downgrade():
    raise RuntimeError("V2 历史与撤权证据不能自动删除；使用理解 V2 的兼容版本回退")
