import importlib.util
from unittest.mock import patch
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from test_alembic_migrations import BACKEND_DIR


def test_additive_master_migration_preserves_business_snapshots_and_permissions():
    spec = importlib.util.spec_from_file_location('master_migration', BACKEND_DIR / 'alembic/versions/20260908_0104_add_carton_master.py')
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE carton_orders (id TEXT PRIMARY KEY, product_name TEXT, safety_lead_days INTEGER)'))
        c.execute(text("INSERT INTO carton_orders VALUES ('O1','historical',3)"))
        c.execute(text('CREATE TABLE carton_locations (id TEXT PRIMARY KEY, bin_code TEXT)'))
        c.execute(text("INSERT INTO carton_locations VALUES ('L1','OLD')"))
        c.execute(text('CREATE TABLE carton_inventory_movements (id TEXT PRIMARY KEY, quantity NUMERIC, unit_price NUMERIC, location TEXT)'))
        c.execute(text("INSERT INTO carton_inventory_movements VALUES ('M1',10,2,'OLD')"))
        c.execute(text('CREATE TABLE auth_permissions (id TEXT PRIMARY KEY, code TEXT, name TEXT, description TEXT)'))
        c.execute(text('CREATE TABLE auth_roles (id TEXT PRIMARY KEY)'))
        c.execute(text("INSERT INTO auth_roles VALUES ('admin'),('warehouse_keeper'),('position_carton_supervisor')"))
        c.execute(text('CREATE TABLE auth_role_permissions (id TEXT PRIMARY KEY, role_id TEXT, permission_id TEXT)'))
        with Operations.context(MigrationContext.configure(c)):
            migration.upgrade()
            assert tuple(c.execute(text('SELECT * FROM carton_orders')).one()) == ('O1', 'historical', 3, '', 0)
            assert tuple(c.execute(text('SELECT * FROM carton_locations')).one()) == ('L1', 'OLD', 'ACTIVE', 1)
            assert tuple(c.execute(text('SELECT * FROM carton_inventory_movements')).one()) == ('M1', 10, 2, 'OLD', '', '')
            assert set(c.execute(text('SELECT role_id FROM auth_role_permissions')).scalars()) == {'admin', 'position_carton_supervisor'}
            assert {'carton_master_records', 'carton_master_sources'} <= set(inspect(c).get_table_names())
            with pytest.raises(RuntimeError): migration.downgrade()
    engine.dispose()


def test_master_startup_guard_requires_migration_without_mutating_database(monkeypatch):
    from app import db
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as c: c.execute(text('CREATE TABLE alembic_version (version_num TEXT)'))
    monkeypatch.setattr(db, 'engine', engine)
    with pytest.raises(RuntimeError, match='0104'): db.ensure_carton_master_schema_ready()
    assert set(inspect(engine).get_table_names()) == {'alembic_version'}
    engine.dispose()
