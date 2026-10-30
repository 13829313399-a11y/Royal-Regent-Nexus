"""Canonical integration preserves local history and refuses blind adoption."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

BACKEND = Path(__file__).resolve().parents[1]


def ownership_migration():
    path = BACKEND / 'alembic/versions/20261030_0187_carton_asset_ownership.py'
    spec = importlib.util.spec_from_file_location('canonical_carton_ownership', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ownership_upgrade_preserves_original_rows_and_uses_creation_evidence(tmp_path):
    engine = sa.create_engine('sqlite:///' + str(tmp_path / 'ownership.db'))
    original = [
        ('internal', 'huaxing', 'employee', 'manual_orders', 'pdf'),
        ('supplier', 'huaxing', 'supplier-user', 'manual_orders', 'image'),
        ('unproven', 'huaxing', 'employee', 'manual_orders', 'pdf'),
    ]
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE carton_mark_assets (id TEXT PRIMARY KEY, factory_id TEXT, created_by TEXT, recognition_source TEXT, kind TEXT, is_archived BOOLEAN DEFAULT 0, created_at TEXT, CONSTRAINT ck_carton_mark_asset_kind CHECK (kind IN ('excel','pdf','image')))")
        connection.exec_driver_sql('CREATE TABLE carton_audit_events (entity_id TEXT, factory_id TEXT, actor_user_id TEXT, detail_json TEXT, entity_type TEXT, event_type TEXT)')
        connection.exec_driver_sql('CREATE TABLE carton_suppliers (id TEXT, factory_id TEXT)')
        connection.exec_driver_sql('INSERT INTO carton_mark_assets (id,factory_id,created_by,recognition_source,kind) VALUES (?,?,?,?,?)', original)
        connection.exec_driver_sql("INSERT INTO carton_suppliers VALUES ('dongkang','huaxing')")
        connection.exec_driver_sql("INSERT INTO carton_audit_events VALUES (?,?,?,?,?,?)", [
            ('supplier', 'huaxing', 'supplier-user', '{"supplier_context":{"supplier_id":"dongkang"}}', 'carton_mark_asset', 'CARTON_MARK_ASSET_CREATED'),
            ('unproven', 'huaxing', 'different-actor', '{"supplier_context":{"supplier_id":"dongkang"}}', 'carton_mark_asset', 'CARTON_MARK_ASSET_CREATED'),
        ])
        migration = ownership_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.exec_driver_sql('SELECT id,factory_id,created_by,recognition_source,kind FROM carton_mark_assets').fetchall()
        assert sorted(map(tuple, rows)) == sorted(original)
        assert connection.exec_driver_sql('SELECT id,owner_department,owner_supplier_id,asset_purpose FROM carton_mark_assets ORDER BY id').fetchall() == [
            ('internal', None, None, 'MATERIAL'),
            ('supplier', 'supplier', 'dongkang', 'MATERIAL'),
            ('unproven', None, None, 'MATERIAL'),
        ]
        assert connection.exec_driver_sql('SELECT count(*) FROM carton_audit_events').scalar_one() == 2
        with pytest.raises(RuntimeError, match='Keep ownership'):
            migration.downgrade()
    engine.dispose()


@pytest.mark.parametrize('legacy', ['20261028_0185', '20261028_0186'])
def test_legacy_carton_identity_upgrade_refuses_without_changing_database(tmp_path, legacy):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        connection.execute('INSERT INTO alembic_version VALUES (?)', (legacy,))
        connection.execute('CREATE TABLE carton_material_references (reference_id TEXT PRIMARY KEY)')
        connection.execute("INSERT INTO carton_material_references VALUES ('original-evidence')")
        before = list(connection.iterdump())
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(path), PYTHONUTF8='1', ONLINE_DOCUMENTS_ENABLED='false')
    result = subprocess.run([sys.executable, '-m', 'alembic', '-c', str(BACKEND / 'alembic.ini'), 'upgrade', 'head'],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode != 0
    assert ('Legacy local carton' if legacy.endswith('0186') else 'cutting header index is missing') in result.stderr
    with sqlite3.connect(path) as connection:
        assert list(connection.iterdump()) == before
