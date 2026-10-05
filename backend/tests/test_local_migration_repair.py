"""Verify adoption cannot hide schema drift or remove legacy data."""
import importlib.util
from pathlib import Path
import sqlite3

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_migration_repair", BACKEND / "tools/repair_local_migration_state.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@pytest.fixture
def legacy_database(tmp_path):
    path = tmp_path / "legacy.db"
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(path)))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE internal_quotes (id VARCHAR(64) PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(connection)):
            for filename in repair.SCRIPTS:
                module_spec = importlib.util.spec_from_file_location("fixture_" + filename[:-3], BACKEND / "alembic/versions" / filename)
                migration = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(migration)
                migration.upgrade()
        connection.exec_driver_sql("DROP TRIGGER customer_price_snapshot_no_update")
        connection.exec_driver_sql("DROP TRIGGER customer_price_snapshot_no_delete")
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (repair.SUPPLIER_REVISION,))
        connection.exec_driver_sql("INSERT INTO customer_price_settings VALUES ('huaxing','buzz',7,'{}','old','owner','Legacy')")
        connection.exec_driver_sql("INSERT INTO customer_price_settings_snapshots VALUES ('S1','huaxing','buzz',7,'{}','old','owner')")
        connection.exec_driver_sql("INSERT INTO internal_quotes VALUES ('Q1')")
        connection.exec_driver_sql("INSERT INTO internal_quote_families VALUES ('F1','huaxing',4,'Q1')")
        connection.exec_driver_sql("INSERT INTO internal_quote_alternatives VALUES ('Q1','F1','A','Original',1,'','','','',0)")
    engine.dispose()
    return path


def versions(db):
    return {row[0] for row in db.execute("SELECT version_num FROM alembic_version")}


def test_adopts_verified_branches_preserves_data_and_restores_immutable_guard(legacy_database):
    with sqlite3.connect(legacy_database) as db:
        before = {table: db.execute(f'SELECT * FROM "{table}"').fetchall()
                  for table in (*repair.TABLES, "internal_quotes")}
        db.execute("DROP INDEX ix_customer_price_settings_snapshots_factory_id")
    repair.reconcile(legacy_database)
    with sqlite3.connect(legacy_database) as db:
        assert versions(db) == {repair.SUPPLIER_REVISION, repair.QUOTE_REVISION}
        for table, rows in before.items():
            assert db.execute(f'SELECT * FROM "{table}"').fetchall() == rows
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='ix_customer_price_settings_snapshots_factory_id'").fetchone()[0] == 1
        for statement in ("UPDATE customer_price_settings_snapshots SET revision=8 WHERE id='S1'",
                          "DELETE FROM customer_price_settings_snapshots WHERE id='S1'"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                db.execute(statement)
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_schema_drift_is_rejected_before_any_write(legacy_database):
    with sqlite3.connect(legacy_database) as db:
        db.execute("ALTER TABLE internal_quote_families ADD COLUMN unknown_column TEXT")
    before = legacy_database.read_bytes()
    with pytest.raises(repair.RepairError, match="Schema mismatch"):
        repair.reconcile(legacy_database)
    assert legacy_database.read_bytes() == before
    with sqlite3.connect(legacy_database) as db:
        assert versions(db) == {repair.SUPPLIER_REVISION}
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0] == 0


def test_incompatible_guard_is_not_replaced_or_stamped(legacy_database):
    with sqlite3.connect(legacy_database) as db:
        db.execute("CREATE TRIGGER customer_price_snapshot_no_update BEFORE UPDATE ON customer_price_settings_snapshots BEGIN SELECT 1; END")
    before = legacy_database.read_bytes()
    with pytest.raises(repair.RepairError, match="Trigger mismatch"):
        repair.reconcile(legacy_database)
    assert legacy_database.read_bytes() == before


def test_foreign_key_damage_blocks_adoption(legacy_database):
    with sqlite3.connect(legacy_database) as db:
        db.execute("UPDATE internal_quote_alternatives SET family_id='missing-family'")
    before = legacy_database.read_bytes()
    with pytest.raises(repair.RepairError, match="foreign-key errors"):
        repair.reconcile(legacy_database)
    assert legacy_database.read_bytes() == before


def test_unsupported_revision_and_existing_backup_are_refused(legacy_database, tmp_path):
    with sqlite3.connect(legacy_database) as db:
        db.execute("UPDATE alembic_version SET version_num='20260917_0117'")
    before = legacy_database.read_bytes()
    with pytest.raises(repair.RepairError, match="Unsupported migration records"):
        repair.reconcile(legacy_database)
    assert legacy_database.read_bytes() == before
    with sqlite3.connect(legacy_database) as db:
        db.execute("UPDATE alembic_version SET version_num=?", (repair.SUPPLIER_REVISION,))
    before = legacy_database.read_bytes()
    backup_dir = tmp_path / "existing-backup"
    backup_dir.mkdir()
    with pytest.raises(FileExistsError):
        repair.apply_with_backup(legacy_database, backup_dir)
    assert legacy_database.read_bytes() == before


def test_revision_alone_cannot_claim_missing_schema_is_current(legacy_database):
    head = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
    with sqlite3.connect(legacy_database) as db:
        db.execute("UPDATE alembic_version SET version_num=?", (head,))
    before = legacy_database.read_bytes()
    with pytest.raises(repair.RepairError, match="missing identity tables"):
        repair.reconcile(legacy_database)
    assert legacy_database.read_bytes() == before
