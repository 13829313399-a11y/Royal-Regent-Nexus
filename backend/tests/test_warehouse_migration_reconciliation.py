"""Migration collision rehearsal on disposable databases only."""
import hashlib
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
LEGACY = BACKEND / 'alembic/legacy/20261009_0150_warehouse_operations.py'
CURRENT = BACKEND / 'alembic/versions/20261009_0152_warehouse_operations.py'


def migrate(database, revision='head', *, success=True):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix(), SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1')
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=BACKEND, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    return result.stdout + result.stderr


def snapshot(database):
    with sqlite3.connect(database) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='alembic_version'")]
        return {name: ([r[1] for r in db.execute(f'PRAGMA table_info("{name}")')], db.execute(f'SELECT * FROM "{name}"').fetchall()) for name in names}


def unchanged(database, before):
    with sqlite3.connect(database) as db:
        for name, (columns, rows) in before.items():
            projection = ','.join('"' + column + '"' for column in columns)
            assert db.execute(f'SELECT {projection} FROM "{name}"').fetchall() == rows
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def local_legacy(database):
    migrate(database, '20261009_0149')
    engine = sa.create_engine('sqlite:///' + database.as_posix())
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(LEGACY))['upgrade']()
        connection.exec_driver_sql("INSERT INTO warehouse_operations_documents VALUES ('old','huakang-c','fabric',1,'old-request','hash','RECEIPT','2026-10-09','{\"quantity\":\"12\",\"location\":\"旧仓位\"}','actor','仓管','2026-10-09')")
        # Reproduce the marker written by the actually applied local-only script.
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='20261009_0150'")
    engine.dispose()


def test_archive_is_unchanged_and_canonical_graph_has_one_head():
    assert hashlib.sha256(LEGACY.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == '3d91bed295960672a7d36124ca74b02daf4c76d51dd822d9b85250ba8c4a3502'
    assert ScriptDirectory.from_config(Config(str(BACKEND / 'alembic.ini'))).get_heads() == ['20261009_0152']


@pytest.mark.parametrize('legacy', [False, True])
def test_published_and_legacy_databases_upgrade_without_changing_existing_values(tmp_path, legacy):
    database = tmp_path / 'warehouse-upgrade.db'
    if legacy:
        local_legacy(database)
    else:
        migrate(database, '20261009_0151')
    before = snapshot(database)
    migrate(database); migrate(database)
    unchanged(database, before)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [('20261009_0152',)]
        assert 'quote_target_daily_qty' in {r[1] for r in db.execute('PRAGMA table_info(molding_sample_items)')}
        assert db.execute('SELECT COUNT(*) FROM warehouse_operations_documents').fetchone()[0] == int(legacy)
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('cutting_ops_orders','cutting_ops_order_revisions')").fetchone()[0] == 2


@pytest.mark.parametrize('drift', ['column', 'index', 'trigger', 'cutting', 'quote'])
def test_legacy_drift_is_rejected_before_any_new_migration(tmp_path, drift):
    database = tmp_path / 'warehouse-drift.db'
    local_legacy(database)
    with sqlite3.connect(database) as db:
        if drift == 'column': db.execute('ALTER TABLE warehouse_operations_documents ADD COLUMN unknown TEXT')
        elif drift == 'index': db.execute('DROP INDEX ix_warehouse_operations_documents_warehouse')
        elif drift == 'trigger': db.execute('CREATE TRIGGER unexpected AFTER INSERT ON warehouse_operations_documents BEGIN SELECT 1; END')
        elif drift == 'cutting': db.execute('ALTER TABLE cutting_ops_masters ADD COLUMN unknown TEXT')
        else: db.execute('ALTER TABLE molding_sample_items ADD COLUMN quote_target_daily_qty TEXT')
    before = snapshot(database)
    output = migrate(database, success=False)
    assert 'schema drift' in output or 'unexpected triggers' in output
    unchanged(database, before)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [('20261009_0150',)]
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='cutting_ops_orders'").fetchone()


def test_non_sqlite_cannot_adopt_the_local_collision():
    with pytest.raises(RuntimeError, match='known local SQLite'):
        runpy.run_path(str(CURRENT))['preflight_legacy'](SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))


@pytest.mark.parametrize('drift', ['check_literal', 'partial_index'])
def test_semantic_schema_drift_is_not_normalized_away(drift):
    migration = runpy.run_path(str(CURRENT))
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        operation = Operations(MigrationContext.configure(connection))
        for path in (LEGACY, BACKEND / 'alembic/versions/20261007_0131_cutting_master.py'):
            upgrade = runpy.run_path(str(path))['upgrade']
            upgrade.__globals__['op'] = operation
            upgrade()
        connection.exec_driver_sql('CREATE TABLE molding_sample_items (id TEXT PRIMARY KEY)')
        migration['preflight_legacy'](connection, before_cutting=True)
        if drift == 'check_literal':
            ddl = connection.scalar(sa.text("SELECT sql FROM sqlite_master WHERE name='warehouse_operations_documents'"))
            indexes = connection.scalars(sa.text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='warehouse_operations_documents' AND sql IS NOT NULL")).all()
            connection.exec_driver_sql('DROP TABLE warehouse_operations_documents')
            connection.exec_driver_sql(ddl.replace("'huakang-c'", "'HUAKANG-C'"))
            for sql in indexes:
                connection.exec_driver_sql(sql)
        else:
            connection.exec_driver_sql('DROP INDEX ix_warehouse_operations_documents_warehouse')
            connection.exec_driver_sql("CREATE INDEX ix_warehouse_operations_documents_warehouse ON warehouse_operations_documents (warehouse) WHERE warehouse='fabric'")
        with pytest.raises(RuntimeError, match='schema drift'):
            migration['preflight_legacy'](connection, before_cutting=True)
    engine.dispose()
