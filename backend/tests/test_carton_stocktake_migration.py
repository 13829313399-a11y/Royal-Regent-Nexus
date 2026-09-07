import importlib.util

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from test_alembic_migrations import BACKEND_DIR


def test_startup_guard_does_not_create_missing_stocktake_tables(monkeypatch):
    from app import db
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('20260907_0101')"))
    monkeypatch.setattr(db, "engine", engine)
    with pytest.raises(RuntimeError, match="20260907_0102"):
        db.ensure_carton_stocktake_schema_ready()
    assert "carton_stocktakes" not in inspect(engine).get_table_names()
    engine.dispose()


def test_stocktake_frozen_migration_matches_models_and_protects_evidence():
    path = BACKEND_DIR / "alembic/versions/20260907_0102_add_carton_stocktakes.py"
    spec = importlib.util.spec_from_file_location("stocktake_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
            for model in (CartonStocktake, CartonStocktakeLine):
                columns = inspect(connection).get_columns(model.__tablename__)
                assert {column["name"]: column["nullable"] for column in columns} == {column.name: column.nullable for column in model.__table__.columns}
                assert "CREATE TABLE" in str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
            module.downgrade()
            assert "carton_stocktakes" not in inspect(connection).get_table_names()
            module.upgrade()
            connection.execute(text("""INSERT INTO carton_stocktakes
                (id,factory_id,status,revision,created_by,created_by_name,created_at,
                 submitted_by,submitted_by_name,submitted_at,reviewed_by,reviewed_by_name,reviewed_at,note,basis_token)
                VALUES ('PD-1','huaxing','DRAFT',1,'u','User','2026-09-07','','','','','','','','')"""))
            with pytest.raises(RuntimeError, match="盘点证据"):
                module.downgrade()
            assert connection.execute(text("SELECT COUNT(*) FROM carton_stocktakes")).scalar() == 1
    engine.dispose()
