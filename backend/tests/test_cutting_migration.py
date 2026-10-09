"""Actual Alembic upgrade in an isolated file; never use the configured database."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from sqlalchemy import create_engine, inspect


def test_upgrade_preserves_existing_tables_and_matches_models(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / 'cutting-migration.db'
    env = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix(), SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1', CUTTING_OPS_ENABLED='false')
    def upgrade(revision):
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=backend, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
    upgrade('20261009_0148')
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE cutting_preservation_probe (id TEXT PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO cutting_preservation_probe VALUES ('00001', '真实格式保留')")
        old_tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'").fetchall()
        old_rows = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name, _ in old_tables}
    upgrade('head'); upgrade('head')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [('20261009_0149',)]
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for name, ddl in old_tables:
            assert db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0] == ddl
            assert db.execute('SELECT * FROM "' + name + '"').fetchall() == old_rows[name]
    from app.services.cutting_ops import TABLES, schema_ready
    engine = create_engine('sqlite:///' + database.as_posix())
    assert schema_ready(engine)
    for table in TABLES:
        actual = {column['name']: column for column in inspect(engine).get_columns(table.name)}
        assert set(actual) == {column.name for column in table.columns}
        for column in table.columns:
            assert actual[column.name]['nullable'] == column.nullable
    engine.dispose()
