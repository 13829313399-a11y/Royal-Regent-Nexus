"""Add 3D site, migration lineage and device consistency schema without runtime cutover.

Frozen definitions: do not import current application models from this migration.
Downgrade only supports an empty 3D domain; restore a coordinated backup otherwise.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260904_0098"
down_revision = "20260904_0097"
branch_labels = None
depends_on = None

SITE_ID = "3dsite-huakang-a-heyuan"
NEW_TABLES = ['three_d_printing_sites', 'three_d_printing_network_gateways', 'three_d_printing_connector_instances', 'three_d_printing_printer_connections', 'three_d_printing_printer_state_events', 'three_d_printing_material_aliases', 'three_d_printing_migration_batches', 'three_d_printing_migration_row_results']
EXTENSION_COLUMNS = {'three_d_printing_production_records': ['site_id', 'device_job_key', 'legacy_status', 'run_status', 'reconciliation_status', 'data_quality_flags_json', 'product_snapshot_json', 'cost_profile_version', 'calculated_cost_snapshot_json', 'migration_batch_id', 'source_system'], 'three_d_printing_inventory_movements': ['idempotency_key', 'movement_status', 'reversal_of_movement_id', 'reservation_id', 'source_event_id', 'migration_batch_id', 'raw_material_name', 'affects_balance'], 'three_d_printing_printer_commands': ['connector_instance_id', 'lease_id', 'leased_until', 'attempt_count', 'next_attempt_at', 'result_evidence_json']}

def _production_records_columns() -> list[sa.Column]:
    return [
        sa.Column('site_id', sa.String(length=96), nullable=True),
        sa.Column('device_job_key', sa.String(length=128), nullable=True),
        sa.Column('legacy_status', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('run_status', sa.String(length=24), nullable=False, server_default='unknown'),
        sa.Column('reconciliation_status', sa.String(length=24), nullable=False, server_default='none'),
        sa.Column('data_quality_flags_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('product_snapshot_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('cost_profile_version', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('calculated_cost_snapshot_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('migration_batch_id', sa.String(length=96), nullable=True),
        sa.Column('source_system', sa.String(length=64), nullable=False, server_default='nexus'),
    ]

def _inventory_movements_columns() -> list[sa.Column]:
    return [
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('movement_status', sa.String(length=24), nullable=False, server_default='posted'),
        sa.Column('reversal_of_movement_id', sa.String(length=96), nullable=True),
        sa.Column('reservation_id', sa.String(length=96), nullable=True),
        sa.Column('source_event_id', sa.String(length=96), nullable=True),
        sa.Column('migration_batch_id', sa.String(length=96), nullable=True),
        sa.Column('raw_material_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('affects_balance', sa.Boolean(), nullable=False, server_default=sa.true()),
    ]

def _printer_commands_columns() -> list[sa.Column]:
    return [
        sa.Column('connector_instance_id', sa.String(length=96), nullable=True),
        sa.Column('lease_id', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('leased_until', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('result_evidence_json', sa.Text(), nullable=False, server_default='{}'),
    ]

def upgrade() -> None:
    op.create_index("uq_3d_material_id_factory", "three_d_printing_materials", ["id", "factory_id"], unique=True)
    op.create_index("uq_3d_movement_id_factory", "three_d_printing_inventory_movements", ["id", "factory_id"], unique=True)
    op.add_column("three_d_printing_printers", sa.Column("site_id", sa.String(96), nullable=True))
    op.add_column("three_d_printing_product_images", sa.Column("legacy_sha256", sa.String(64), nullable=False, server_default=""))
    op.create_table('three_d_printing_sites',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('site_code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='Asia/Shanghai'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('updated_at', sa.String(length=32), nullable=False, server_default=''),
        sa.CheckConstraint("factory_id = 'huakang-a'", name='ck_3d_site_factory'),
        sa.UniqueConstraint('factory_id', 'site_code', name='uq_3d_site_code'),
        sa.UniqueConstraint('id', 'factory_id', name='uq_3d_site_id_factory'),
    )
    op.create_table('three_d_printing_network_gateways',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=96), nullable=False),
        sa.Column('gateway_key', sa.String(length=96), nullable=False),
        sa.Column('vpn_type', sa.String(length=24), nullable=False),
        sa.Column('advertised_cidr', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('tunnel_address', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='unknown'),
        sa.Column('last_handshake_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('latency_ms', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0'),
        sa.Column('packet_loss_percent', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('config_revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_error', sa.String(length=255), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['site_id', 'factory_id'], ['three_d_printing_sites.id', 'three_d_printing_sites.factory_id'], name='fk_3d_gateway_site', ondelete='RESTRICT'),
        sa.UniqueConstraint('factory_id', 'gateway_key', name='uq_3d_gateway_key'),
    )
    op.create_table('three_d_printing_connector_instances',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=96), nullable=False),
        sa.Column('connector_key', sa.String(length=96), nullable=False),
        sa.Column('instance_id', sa.String(length=96), nullable=False),
        sa.Column('version', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='offline'),
        sa.Column('capabilities_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('last_seen_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('leader_printer_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=255), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['site_id', 'factory_id'], ['three_d_printing_sites.id', 'three_d_printing_sites.factory_id'], name='fk_3d_connector_site', ondelete='RESTRICT'),
        sa.UniqueConstraint('id', 'factory_id', name='uq_3d_connector_id_factory'),
        sa.UniqueConstraint('site_id', 'instance_id', name='uq_3d_connector_instance'),
    )
    op.create_table('three_d_printing_printer_connections',
        sa.Column('printer_id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=96), nullable=False),
        sa.Column('lan_host', sa.String(length=255), nullable=False),
        sa.Column('mqtt_port', sa.Integer(), nullable=False, server_default='8883'),
        sa.Column('credential_ref', sa.String(length=255), nullable=False),
        sa.Column('certificate_fingerprint', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('connection_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('connection_revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('connection_owner', sa.String(length=24), nullable=False, server_default='edge-legacy'),
        sa.Column('leader_instance_id', sa.String(length=96), nullable=True),
        sa.Column('leader_lease_id', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('leader_leased_until', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('last_connect_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('last_disconnect_at', sa.String(length=32), nullable=False, server_default=''),
        sa.CheckConstraint('mqtt_port BETWEEN 1 AND 65535', name='ck_3d_connection_port'),
        sa.ForeignKeyConstraint(['printer_id', 'factory_id'], ['three_d_printing_printers.id', 'three_d_printing_printers.factory_id'], name='fk_3d_connection_printer', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['site_id', 'factory_id'], ['three_d_printing_sites.id', 'three_d_printing_sites.factory_id'], name='fk_3d_connection_site', ondelete='RESTRICT'),
    )
    op.create_table('three_d_printing_printer_state_events',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('connector_instance_id', sa.String(length=96), nullable=False),
        sa.Column('printer_id', sa.String(length=96), nullable=False),
        sa.Column('machine_no', sa.Integer(), nullable=False),
        sa.Column('connection_session_id', sa.String(length=96), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('observed_at', sa.String(length=32), nullable=False),
        sa.Column('received_at', sa.String(length=32), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('remaining_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_file', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('temperatures_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('error_code', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('error_text', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('payload_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('raw_payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.CheckConstraint('length(raw_payload_json) <= 65536', name='ck_3d_event_payload_limit'),
        sa.CheckConstraint('sequence >= 0', name='ck_3d_event_sequence'),
        sa.ForeignKeyConstraint(['connector_instance_id', 'factory_id'], ['three_d_printing_connector_instances.id', 'three_d_printing_connector_instances.factory_id'], name='fk_3d_event_connector', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['printer_id', 'factory_id'], ['three_d_printing_printers.id', 'three_d_printing_printers.factory_id'], name='fk_3d_event_printer', ondelete='RESTRICT'),
        sa.UniqueConstraint('id', 'factory_id', name='uq_3d_event_id_factory'),
        sa.UniqueConstraint('printer_id', 'connection_session_id', 'sequence', name='uq_3d_event_session_sequence'),
    )
    op.create_index('ix_3d_event_printer_observed', 'three_d_printing_printer_state_events', ['factory_id', 'printer_id', 'observed_at'], unique=False)
    op.create_table('three_d_printing_material_aliases',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('raw_name', sa.String(length=255), nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=False),
        sa.Column('canonical_material_id', sa.String(length=96), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='legacy'),
        sa.Column('approved_by', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('approved_at', sa.String(length=32), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['canonical_material_id', 'factory_id'], ['three_d_printing_materials.id', 'three_d_printing_materials.factory_id'], name='fk_3d_alias_material', ondelete='RESTRICT'),
        sa.CheckConstraint("factory_id = 'huakang-a'", name='ck_3d_alias_factory'),
        sa.UniqueConstraint('factory_id', 'raw_name', name='uq_3d_alias_raw_name'),
    )
    op.create_index('ix_3d_alias_normalized', 'three_d_printing_material_aliases', ['factory_id', 'normalized_name'], unique=False)
    op.create_table('three_d_printing_migration_batches',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=96), nullable=False),
        sa.Column('source_system', sa.String(length=64), nullable=False),
        sa.Column('source_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_updated_at_ms', sa.BigInteger(), nullable=False),
        sa.Column('source_size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('image_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('image_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('migration_version', sa.String(length=64), nullable=False),
        sa.Column('code_revision', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='analyzed'),
        sa.Column('expected_counts_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('summary_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('reconciliation_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('checkpoint_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('started_at', sa.String(length=32), nullable=False),
        sa.Column('completed_at', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('lease_id', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('leased_until', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('error_code', sa.String(length=64), nullable=False, server_default=''),
        sa.CheckConstraint("status IN ('analyzed','dry_run','importing','imported','reconciled','failed','rolled_back')", name='ck_3d_batch_status'),
        sa.ForeignKeyConstraint(['site_id', 'factory_id'], ['three_d_printing_sites.id', 'three_d_printing_sites.factory_id'], name='fk_3d_batch_site', ondelete='RESTRICT'),
        sa.UniqueConstraint('id', 'factory_id', name='uq_3d_batch_id_factory'),
        sa.UniqueConstraint('factory_id', 'site_id', 'source_system', 'source_sha256', name='uq_3d_batch_source'),
    )
    op.create_index('ix_3d_batch_source_updated', 'three_d_printing_migration_batches', ['factory_id', 'site_id', 'source_system', 'source_updated_at_ms'], unique=False)
    op.create_table('three_d_printing_migration_row_results',
        sa.Column('id', sa.String(length=96), primary_key=True, nullable=False),
        sa.Column('factory_id', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.String(length=96), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('legacy_id', sa.String(length=255), nullable=False),
        sa.Column('target_id', sa.String(length=96), nullable=False, server_default=''),
        sa.Column('source_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('target_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='pending'),
        sa.Column('error_code', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['batch_id', 'factory_id'], ['three_d_printing_migration_batches.id', 'three_d_printing_migration_batches.factory_id'], name='fk_3d_row_batch', ondelete='RESTRICT'),
        sa.UniqueConstraint('batch_id', 'entity_type', 'legacy_id', name='uq_3d_row_source'),
    )
    op.create_index('ix_3d_row_batch_status', 'three_d_printing_migration_row_results', ['batch_id', 'status'], unique=False)
    op.create_index('ix_3d_row_target', 'three_d_printing_migration_row_results', ['factory_id', 'entity_type', 'target_id'], unique=False)
    with op.batch_alter_table('three_d_printing_production_records') as batch:
        for column in _production_records_columns():
            batch.add_column(column)
        batch.create_foreign_key("fk_3d_record_site", "three_d_printing_sites", ["site_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_3d_record_batch", "three_d_printing_migration_batches", ["migration_batch_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_3d_record_device_job", ["factory_id", "device_job_key"])
        batch.create_check_constraint("ck_3d_record_run_status", "run_status IN ('pending','running','paused','succeeded','failed','cancelled','unknown')")
        batch.create_check_constraint("ck_3d_record_reconciliation", "reconciliation_status IN ('none','pending','resolved')")
    with op.batch_alter_table('three_d_printing_inventory_movements') as batch:
        for column in _inventory_movements_columns():
            batch.add_column(column)
        batch.create_foreign_key("fk_3d_movement_batch", "three_d_printing_migration_batches", ["migration_batch_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_3d_movement_event", "three_d_printing_printer_state_events", ["source_event_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_3d_movement_reversal", "three_d_printing_inventory_movements", ["reversal_of_movement_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_3d_movement_idempotency", ["factory_id", "idempotency_key"])
    with op.batch_alter_table('three_d_printing_printer_commands') as batch:
        for column in _printer_commands_columns():
            batch.add_column(column)
        batch.create_foreign_key("fk_3d_command_connector", "three_d_printing_connector_instances", ["connector_instance_id", "factory_id"], ["id", "factory_id"], ondelete="RESTRICT")
    op.execute(sa.text("UPDATE three_d_printing_production_records SET legacy_status = status"))
    op.execute(sa.text("INSERT INTO three_d_printing_sites (id, factory_id, site_code, name, timezone, enabled, created_at, updated_at) VALUES (:id, 'huakang-a', 'heyuan', '华康A河源3D打印现场', 'Asia/Shanghai', true, '2026-09-04T00:00:00+00:00', '2026-09-04T00:00:00+00:00')").bindparams(id=SITE_ID))

def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM three_d_printing_product_images WHERE legacy_sha256 <> '' LIMIT 1")).first():
        raise RuntimeError("three_d_v2_downgrade_would_discard_image_lineage")
    for table in NEW_TABLES[1:] + list(EXTENSION_COLUMNS):
        if connection.execute(sa.text(f'SELECT 1 FROM "{table}" LIMIT 1')).first():
            raise RuntimeError("three_d_v2_downgrade_requires_empty_domain_restore_backup_instead")
    if connection.execute(sa.text("SELECT 1 FROM three_d_printing_printers WHERE site_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("three_d_v2_downgrade_would_discard_printer_site")
    sites = connection.execute(sa.text("SELECT id, factory_id, site_code, name, timezone, enabled FROM three_d_printing_sites")).all()
    if sites != [(SITE_ID, "huakang-a", "heyuan", "华康A河源3D打印现场", "Asia/Shanghai", True)]:
        raise RuntimeError("three_d_v2_downgrade_would_discard_site_changes")
    with op.batch_alter_table('three_d_printing_printer_commands') as batch:
        batch.drop_constraint('fk_3d_command_connector', type_='foreignkey')
        for name in EXTENSION_COLUMNS['three_d_printing_printer_commands']:
            batch.drop_column(name)
    with op.batch_alter_table('three_d_printing_inventory_movements') as batch:
        batch.drop_constraint("uq_3d_movement_idempotency", type_="unique")
        for name in ("fk_3d_movement_batch", "fk_3d_movement_event", "fk_3d_movement_reversal"):
            batch.drop_constraint(name, type_="foreignkey")
        for name in EXTENSION_COLUMNS['three_d_printing_inventory_movements']:
            batch.drop_column(name)
    with op.batch_alter_table('three_d_printing_production_records') as batch:
        batch.drop_constraint("uq_3d_record_device_job", type_="unique")
        batch.drop_constraint("fk_3d_record_site", type_="foreignkey")
        batch.drop_constraint("fk_3d_record_batch", type_="foreignkey")
        batch.drop_constraint("ck_3d_record_run_status", type_="check")
        batch.drop_constraint("ck_3d_record_reconciliation", type_="check")
        for name in EXTENSION_COLUMNS['three_d_printing_production_records']:
            batch.drop_column(name)
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.drop_index("uq_3d_movement_id_factory", table_name="three_d_printing_inventory_movements")
    op.drop_index("uq_3d_material_id_factory", table_name="three_d_printing_materials")
    op.drop_column("three_d_printing_printers", "site_id")
    op.drop_column("three_d_printing_product_images", "legacy_sha256")
