import importlib.util
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from test_alembic_migrations import BACKEND_DIR


def test_migration_preserves_confirmation_without_guessing_acceptance_date():
    spec = importlib.util.spec_from_file_location("supplier_migration", BACKEND_DIR / "alembic/versions/20260909_0105_carton_supplier_settlement.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE carton_receipts (id TEXT PRIMARY KEY, delivery_date TEXT, confirmed_at TEXT)"))
        c.execute(text("INSERT INTO carton_receipts VALUES ('R1','2026-09-30','2026-10-02T12:00:00')"))
        with Operations.context(MigrationContext.configure(c)):
            migration.upgrade()
            assert tuple(c.execute(text("SELECT * FROM carton_receipts")).one()) == ("R1", "2026-09-30", "2026-10-02T12:00:00", None)
            assert "carton_supplier_settlements" in inspect(c).get_table_names()
            with pytest.raises(RuntimeError):
                migration.downgrade()
    engine.dispose()


def test_startup_guard_is_read_only(monkeypatch):
    from app import db
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
    monkeypatch.setattr(db, "engine", engine)
    with pytest.raises(RuntimeError, match="0105"):
        db.ensure_carton_supplier_settlement_schema_ready()
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
