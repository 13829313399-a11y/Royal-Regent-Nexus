"""0176 changes only the receipt CHECK; stock and historical evidence stay intact."""
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS = Path(__file__).parents[1] / 'alembic' / 'versions'


def migration(filename):
    spec = spec_from_file_location(filename, VERSIONS / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


current = migration('20261023_0176_fabric_receipt_zero.py')


def insert_receipt(connection, identifier, quantity):
    connection.execute(sa.text("""INSERT INTO fabric_receipts
        (id,factory_id,source_line_id,source_revision,request_id,request_hash,delivery_reference,
         receipt_date,accounting_month,quantity,unit,prior_received_quantity,source_json,payload_json,actor_id,actor_name,occurred_at)
        VALUES (:id,'huakang-c','L',1,:id,'HASH',:id,'2026-09-16','2026-09',:quantity,'码','0','{}','{}','A','Warehouse','NOW')"""),
        dict(id=identifier, quantity=quantity))


def schema(connection, table):
    inspector = sa.inspect(connection)
    return dict(columns=[(col['name'], str(col['type']), col['nullable'], col['default']) for col in inspector.get_columns(table)],
        indexes=inspector.get_indexes(table), foreign_keys=inspector.get_foreign_keys(table),
        unique=sorted(inspector.get_unique_constraints(table), key=lambda constraint: constraint['name']),
        checks=[check for check in inspector.get_check_constraints(table) if check['name'] != 'ck_fabric_receipt_quantity'])


def test_sqlite_upgrade_preserves_schema_data_and_blocks_unsafe_downgrade(tmp_path):
    engine = sa.create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration('20261005_0134_fabric_procurement.py').upgrade()
            migration('20261008_0142_fabric_receiving.py').upgrade()
            connection.execute(sa.text("INSERT INTO fabric_procurement_lines VALUES ('L','huakang-c','KEY',1,'PENDING','PO','Supplier','MAT','PROD','{}',1,'NOW')"))
            insert_receipt(connection, 'OLD', '960')
            connection.execute(sa.text("INSERT INTO fabric_stock_batches VALUES ('B','huakang-c','OLD','A01','LOT','ROLL','FABRIC','PENDING_INSPECTION')"))
            connection.execute(sa.text("INSERT INTO fabric_inventory_movements VALUES ('M','huakang-c','OLD','B','RECEIPT','960')"))
            names = sa.inspect(connection).get_table_names()
            before_schema = {name: schema(connection, name) for name in names}
            before_data = {name: list(connection.execute(sa.text(f'SELECT * FROM {name}'))) for name in names}
            with pytest.raises(sa.exc.IntegrityError):
                insert_receipt(connection, 'ZERO', '0')
            current.upgrade()
            assert sa.inspect(connection).get_table_names() == names
            assert {name: schema(connection, name) for name in names} == before_schema
            assert {name: list(connection.execute(sa.text(f'SELECT * FROM {name}'))) for name in names} == before_data
            insert_receipt(connection, 'ZERO', '0')
            insert_receipt(connection, 'POSITIVE', '960')
            with pytest.raises(sa.exc.IntegrityError):
                insert_receipt(connection, 'NEGATIVE', '-1')
            # Batch quantities are owned by movements, not a second column on batches.
            assert 'quantity' not in {column['name'] for column in sa.inspect(connection).get_columns('fabric_stock_batches')}
            with pytest.raises(sa.exc.IntegrityError, match='ck_fabric_movement_quantity'):
                connection.execute(sa.text("INSERT INTO fabric_inventory_movements VALUES ('ZERO-M','huakang-c','ZERO','ZERO-B','RECEIPT','0')"))
            with pytest.raises(RuntimeError, match='零入库差异单'):
                current.downgrade()
            assert connection.scalar(sa.text("SELECT quantity FROM fabric_receipts WHERE id='ZERO'")) == '0'
            # Remove only our isolated test fixture to verify a safe downgrade.
            connection.execute(sa.text("DELETE FROM fabric_receipts WHERE id='ZERO'"))
            current.downgrade()
            assert connection.scalar(sa.text("SELECT quantity FROM fabric_receipts WHERE id='OLD'")) == '960'
            with pytest.raises(sa.exc.IntegrityError):
                insert_receipt(connection, 'ZERO-AGAIN', '0')
            assert connection.execute(sa.text('PRAGMA foreign_key_check')).all() == []
    engine.dispose()


def test_postgresql_upgrade_emits_only_drop_add_check_and_head_is_linear():
    output = StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})):
        current.upgrade()
        with pytest.raises(RuntimeError, match='online zero-receipt check'):
            current.downgrade()
    statements = [part.strip() for part in output.getvalue().split(';') if part.strip()]
    assert statements == [
        'ALTER TABLE fabric_receipts DROP CONSTRAINT ck_fabric_receipt_quantity',
        'ALTER TABLE fabric_receipts ADD CONSTRAINT ck_fabric_receipt_quantity CHECK (CAST(quantity AS NUMERIC) >= 0)',
    ]
    config = Config()
    config.set_main_option('script_location', str(VERSIONS.parent))
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == current.revision
    assert current.down_revision == '20261022_0175'
