import importlib
import runpy
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_additive_migration_preserves_originals_and_protects_evidence(tmp_path, monkeypatch):
    migration = runpy.run_path(str(Path(__file__).parents[1] / "alembic/versions/20261010_0153_carton_mark_qc_evidence.py"))
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE carton_mark_templates (id VARCHAR(96) PRIMARY KEY, factory_id VARCHAR(64), UNIQUE(id, factory_id))")
        connection.exec_driver_sql("INSERT INTO carton_mark_templates VALUES ('T1', 'huaxing')")
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration["upgrade"].__globals__["op"], "get_bind", lambda: connection)
        monkeypatch.setattr(migration["upgrade"].__globals__["op"], "execute", operations.execute)
        migration["upgrade"]()
        assert connection.exec_driver_sql("SELECT * FROM carton_mark_templates").all() == [("T1", "huaxing")]
        assert len(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all()) == 6
        records = migration["_tables"]()[0]
        values = dict(id="QC1", factory_id="huaxing", template_id="T1", template_version=1, template_snapshot_json="{}",
            customer_name="customer", po="", item="I1", contract_number="C1", pdf_sha256="sha", request_id="req", request_hash="hash",
            slot=0, corrects_record_id=None, note="", created_by="actor", created_by_name="QC", created_at="today")
        connection.execute(records.insert().values(**values))
        for statement in ("UPDATE carton_mark_qc_records SET note='changed'", "DELETE FROM carton_mark_qc_records"):
            with pytest.raises(sa.exc.DBAPIError, match="append-only"):
                connection.exec_driver_sql(statement)
        with pytest.raises(RuntimeError, match="retained QC evidence"):
            migration["downgrade"]()


def test_empty_schema_can_downgrade_without_dropping_template(tmp_path, monkeypatch):
    migration = runpy.run_path(str(Path(__file__).parents[1] / "alembic/versions/20261010_0153_carton_mark_qc_evidence.py"))
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE carton_mark_templates (id VARCHAR(96) PRIMARY KEY, factory_id VARCHAR(64), UNIQUE(id, factory_id))")
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration["upgrade"].__globals__["op"], "get_bind", lambda: connection)
        monkeypatch.setattr(migration["upgrade"].__globals__["op"], "execute", operations.execute)
        migration["upgrade"]()
        migration["downgrade"]()
        assert sa.inspect(connection).get_table_names() == ["carton_mark_templates"]


def test_startup_requires_qc_tables_immutable_guards_and_customer_layout(tmp_path, monkeypatch):
    db_module = importlib.import_module("app.db")
    importlib.import_module("app.models.carton_mark")
    migrations = Path(__file__).parents[1] / "alembic/versions"
    qc_migration = runpy.run_path(str(migrations / "20261010_0153_carton_mark_qc_evidence.py"))
    layout_migration = runpy.run_path(str(migrations / "20261010_0154_carton_mark_customer_layouts.py"))
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version(version_num TEXT)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('20261010_0154')")
        connection.exec_driver_sql("CREATE TABLE carton_mark_templates (id VARCHAR(96) PRIMARY KEY, factory_id VARCHAR(64), UNIQUE(id, factory_id))")
        for name in ("carton_mark_customers", "carton_mark_documents"):
            connection.exec_driver_sql(f"CREATE TABLE {name}(id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE carton_mark_assets(id TEXT PRIMARY KEY, kind TEXT, photo_group_id TEXT, CONSTRAINT ck_carton_mark_asset_kind CHECK(kind IN ('excel','pdf','image')))")

    with pytest.raises(RuntimeError, match="20261010_0153.*carton_mark_qc_records"):
        db_module.ensure_carton_mark_library_schema_ready()
    with engine.begin() as connection:
        for table in qc_migration["_tables"]():
            table.create(connection)
    with pytest.raises(RuntimeError, match="carton_mark_qc_records_no_update"):
        db_module.ensure_carton_mark_library_schema_ready()
    with engine.begin() as connection:
        for table in qc_migration["_tables"]():
            for action in ("update", "delete"):
                connection.exec_driver_sql(f"CREATE TRIGGER {table.name}_no_{action} BEFORE {action.upper()} ON {table.name} BEGIN SELECT RAISE(ABORT, 'QC evidence is append-only'); END")
    with pytest.raises(RuntimeError, match="20261010_0154"):
        db_module.ensure_carton_mark_library_schema_ready()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE carton_suppliers(id VARCHAR(96), factory_id VARCHAR(64), UNIQUE(id, factory_id))")
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(layout_migration["upgrade"].__globals__["op"], "create_table", operations.create_table)
        layout_migration["upgrade"]()
    db_module.ensure_carton_mark_library_schema_ready()
    engine.dispose()
