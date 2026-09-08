import importlib.util
from unittest.mock import patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.carton_positions import CartonLocation, CartonPositionEntry
from app.services.carton_positions import unknown_id
from test_alembic_migrations import BACKEND_DIR


def test_frozen_position_migration_preserves_old_balances_and_marks_unknown():
    path = BACKEND_DIR / "alembic/versions/20260908_0103_add_carton_positions.py"
    spec = importlib.util.spec_from_file_location("positions_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE carton_receipt_lines (id VARCHAR(96) PRIMARY KEY)"))
        c.execute(text("""CREATE TABLE carton_inventory_movements (
            id VARCHAR(96) PRIMARY KEY, factory_id VARCHAR(64), order_line_id VARCHAR(96),
            customer_code TEXT, contract_no TEXT, item_no TEXT, packaging_type TEXT,
            paper_quality TEXT, specification TEXT, unit TEXT, quantity NUMERIC(18,4),
            unit_price NUMERIC, location TEXT, occurred_at TEXT, UNIQUE(id,factory_id))"""))
        c.execute(text("""INSERT INTO carton_inventory_movements VALUES
            ('M1','huaxing','L1','','','','','','','个',100,2,'旧仓A','2026-09-01'),
            ('M2','huaxing','L1','','','','','','','个',-30,2,'旧仓B','2026-09-02'),
            ('M3','huadeng','L2','','','','','','','张',8,3,'另厂仓','2026-09-01')"""))
        before = c.execute(text("SELECT * FROM carton_inventory_movements ORDER BY id")).all()
        with Operations.context(MigrationContext.configure(c)), patch.object(module.context, "is_offline_mode", return_value=False):
            module.upgrade()
            for model in (CartonLocation, CartonPositionEntry):
                assert {col["name"]: col["nullable"] for col in inspect(c).get_columns(model.__tablename__)} == {
                    col.name: col.nullable for col in model.__table__.columns
                    if not (model is CartonLocation and col.name in {"status", "revision"})}
                assert "CREATE TABLE" in str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
            after = c.execute(text("SELECT * FROM carton_inventory_movements ORDER BY id")).all()
            assert [tuple(r[:-1]) for r in after] == [tuple(r) for r in before]
            assert all(r[-1] == "UNKNOWN" for r in after)
            rows = c.execute(text("SELECT factory_id,location_id,SUM(quantity) FROM carton_position_entries GROUP BY factory_id,location_id")).all()
            assert set(map(tuple, rows)) == {("huaxing", unknown_id("huaxing"), 70), ("huadeng", unknown_id("huadeng"), 8)}
            assert set(c.execute(text("SELECT warehouse FROM carton_locations")).scalars()) == {"待核仓位"}
            with pytest.raises(RuntimeError, match="分账证据"):
                module.downgrade()
    engine.dispose()


def test_position_startup_guard_is_read_only(monkeypatch):
    from app import db
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
        c.execute(text("INSERT INTO alembic_version VALUES ('20260907_0102')"))
    monkeypatch.setattr(db, "engine", engine)
    with pytest.raises(RuntimeError, match="20260908_0103"):
        db.ensure_carton_positions_schema_ready()
    assert "carton_position_entries" not in inspect(engine).get_table_names()
    engine.dispose()
