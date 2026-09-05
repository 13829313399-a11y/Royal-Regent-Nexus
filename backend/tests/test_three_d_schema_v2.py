"""Real 0040 domain DDL -> 0098 upgrade, isolated from business databases."""
from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def load_migration(name):
    path = next((BACKEND / "alembic/versions").glob(name))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration():
    return load_migration("20260904_0098_*.py")


@pytest.fixture
def db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'upgrade.sqlite'}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        with connection.begin(), Operations.context(MigrationContext.configure(connection)):
            # 0041 only reassigns scope; its schema is identical to 0040.
            old = load_migration("20260729_0040_*.py")
            old._create_tables()
            old._install_audit_immutability()
            connection.exec_driver_sql("CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('20260904_0097')")
        yield connection
    engine.dispose()


def apply(db, migration, action="upgrade"):
    if db.in_transaction():
        db.commit()
    with db.begin(), Operations.context(MigrationContext.configure(db)):
        getattr(migration, action)()
        db.execute(sa.text("UPDATE alembic_version SET version_num=:revision"),
                   {"revision": migration.revision if action == "upgrade" else migration.down_revision})


def insert(db, table, **values):
    target = sa.Table(table, sa.MetaData(), autoload_with=db)
    for column in target.columns:
        if column.name in values or column.nullable or column.server_default is not None:
            continue
        values[column.name] = 0 if isinstance(column.type, (sa.Integer, sa.Numeric, sa.Boolean)) else ""
    db.execute(target.insert().values(**values))


def batch(db, ident="batch-1", **values):
    defaults = {"id": ident, "factory_id": "huakang-a", "site_id": "3dsite-huakang-a-heyuan",
                "source_system": "legacy-sqlite", "source_sha256": ident.ljust(64, "a"),
                "source_updated_at_ms": 1788497206084, "migration_version": "v1",
                "started_at": "2026-09-04T00:00:00+00:00"}
    defaults.update(values)
    insert(db, "three_d_printing_migration_batches", **defaults)


def test_real_upgrade_preserves_existing_business_and_legacy_edge(db, migration):
    insert(db, "three_d_printing_printers", id="printer", factory_id="huakang-a", machine_no=1, name="existing")
    insert(db, "three_d_printing_edge_agents", id="edge", factory_id="huakang-a", agent_key="old")
    insert(db, "three_d_printing_production_records", id="old-record", factory_id="huakang-a", status="running", product_name="Historical", weight_g=12.34)
    insert(db, "three_d_printing_inventory", id="inv", factory_id="huakang-a", material_name="PLA", stock_g=10500)
    insert(db, "three_d_printing_inventory_movements", id="mov", factory_id="huakang-a", inventory_id="inv", material_name="PLA", delta_g=100, balance_after_g=10500)
    insert(db, "three_d_printing_printer_commands", id="cmd", factory_id="huakang-a", printer_id="printer", idempotency_key="old-command")
    insert(db, "three_d_printing_audit_events", id="audit", factory_id="huakang-a", detail_json='{"unchanged":true}')
    apply(db, migration)
    assert set(migration.NEW_TABLES) <= set(sa.inspect(db).get_table_names())
    assert db.exec_driver_sql("SELECT product_name,weight_g,legacy_status,run_status,reconciliation_status,source_system FROM three_d_printing_production_records").one() == ("Historical", 12.34, "running", "unknown", "none", "nexus")
    assert db.exec_driver_sql("SELECT delta_g,affects_balance,idempotency_key FROM three_d_printing_inventory_movements").one() == (100, 1, None)
    assert db.exec_driver_sql("SELECT stock_g FROM three_d_printing_inventory").scalar_one() == 10500
    assert db.exec_driver_sql("SELECT lease_id,attempt_count,next_attempt_at FROM three_d_printing_printer_commands").one() == ("", 0, "")
    assert db.exec_driver_sql("SELECT agent_key FROM three_d_printing_edge_agents").scalar_one() == "old"
    assert db.exec_driver_sql("SELECT detail_json FROM three_d_printing_audit_events").scalar_one() == '{"unchanged":true}'
    assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with pytest.raises(RuntimeError, match="restore_backup"):
        apply(db, migration, "downgrade")
    assert "three_d_printing_sites" in sa.inspect(db).get_table_names()


def test_new_batch_row_and_existing_record_factory_constraints(db, migration):
    apply(db, migration)
    batch(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_sites", id="wrong", factory_id="huaxing", site_code="heyuan", name="wrong")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_migration_row_results", id="wrong", factory_id="huaxing", batch_id="batch-1", entity_type="product", legacy_id="1", updated_at="")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_production_records", id="wrong", factory_id="huaxing", migration_batch_id="batch-1", status="running")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_production_records", id="bad-state", factory_id="huakang-a", run_status="running_pending_reconciliation", status="running")
    insert(db, "three_d_printing_production_records", id="legacy-a", factory_id="huakang-a", status="running")
    insert(db, "three_d_printing_production_records", id="legacy-b", factory_id="huakang-a", status="running")
    insert(db, "three_d_printing_production_records", id="job-a", factory_id="huakang-a", device_job_key="job", status="running")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_production_records", id="job-b", factory_id="huakang-a", device_job_key="job", status="running")
    with pytest.raises(IntegrityError), db.begin_nested():
        batch(db, ident="duplicate", source_sha256="batch-1".ljust(64, "a"))


def test_alias_and_movement_relationships_reject_cross_factory(db, migration):
    apply(db, migration)
    insert(db, "three_d_printing_materials", id="other-material", factory_id="huaxing", name="PLA")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_material_aliases", id="alias", factory_id="huakang-a", raw_name="PLA", normalized_name="pla", canonical_material_id="other-material")
    insert(db, "three_d_printing_inventory", id="inv", factory_id="huakang-a", material_name="PLA")
    insert(db, "three_d_printing_inventory", id="other", factory_id="huaxing", material_name="PLA")
    insert(db, "three_d_printing_inventory_movements", id="other-mov", factory_id="huaxing", inventory_id="other", material_name="PLA")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_inventory_movements", id="bad-reversal", factory_id="huakang-a", inventory_id="inv", material_name="PLA", reversal_of_movement_id="other-mov")
    insert(db, "three_d_printing_inventory_movements", id="one", factory_id="huakang-a", inventory_id="inv", material_name="PLA", idempotency_key="consume")
    with pytest.raises(IntegrityError), db.begin_nested():
        insert(db, "three_d_printing_inventory_movements", id="duplicate", factory_id="huakang-a", inventory_id="inv", material_name="PLA", idempotency_key="consume")


def test_empty_downgrade_roundtrip_and_big_integer_source_timestamp(db, migration):
    apply(db, migration)
    batch(db)
    assert db.exec_driver_sql("SELECT source_updated_at_ms FROM three_d_printing_migration_batches").scalar_one() == 1788497206084
    db.exec_driver_sql("DELETE FROM three_d_printing_migration_batches")
    apply(db, migration, "downgrade")
    assert not (set(migration.NEW_TABLES) & set(sa.inspect(db).get_table_names()))
    apply(db, migration)
    assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_postgresql_offline_ddl_compiles_and_revision_has_single_head(migration):
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output, "literal_binds": True})
    with Operations.context(context):
        migration.upgrade()
    sql = output.getvalue()
    assert "BIGINT" in sql and "fk_3d_record_batch" in sql and "fk_3d_alias_material" in sql
    assert "CREATE TABLE three_d_printing_sites" in sql
    assert "DROP TABLE" not in sql
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["20260904_0099"]


def test_readiness_guard_rejects_old_and_partial_new_schema(db, migration, monkeypatch):
    from app import db as app_db
    monkeypatch.setattr(app_db, "engine", db.engine)
    with pytest.raises(RuntimeError, match="0099"):
        app_db.ensure_three_d_printing_schema_ready()
    apply(db, migration)
    with pytest.raises(RuntimeError, match="0099"):
        app_db.ensure_three_d_printing_schema_ready()
    apply(db, load_migration("20260904_0099_*.py"))
    app_db.ensure_three_d_printing_schema_ready()
    db.exec_driver_sql("ALTER TABLE three_d_printing_migration_batches DROP COLUMN checkpoint_json")
    db.commit()
    with pytest.raises(RuntimeError, match="0099"):
        app_db.ensure_three_d_printing_schema_ready()
