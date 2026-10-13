import importlib.util
from pathlib import Path

import sqlalchemy as sa
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_quote_target_migration_preserves_old_rows_and_accepts_preexisting_column():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261009_0150_molding_quote_target.py"
    spec = importlib.util.spec_from_file_location("quote_target_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE molding_sample_items (id TEXT PRIMARY KEY, shoot_qty INTEGER, notes TEXT)")
        connection.exec_driver_sql("INSERT INTO molding_sample_items VALUES ('old', 50, 'keep')")
        with Operations.context(MigrationContext.configure(connection)):
            import runpy
            runpy.run_path(str(path.with_name('20261007_0131_cutting_master.py')))['upgrade']()
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT * FROM molding_sample_items").one() == ('old', 50, 'keep', None)
            connection.exec_driver_sql("UPDATE molding_sample_items SET quote_target_daily_qty=3600")
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT quote_target_daily_qty FROM molding_sample_items").scalar_one() == 3600
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT * FROM molding_sample_items").one() == ('old', 50, 'keep')


@pytest.mark.parametrize('partial', [False, True])
def test_local_revision_collision_repairs_only_the_known_schema(partial):
    import runpy
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261009_0150_molding_quote_target.py'
    migration = runpy.run_path(str(path))
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE molding_sample_items (id TEXT PRIMARY KEY, quote_target_daily_qty INTEGER, notes TEXT)')
        connection.exec_driver_sql("INSERT INTO molding_sample_items VALUES ('existing', 3600, 'keep')")
        if partial:
            connection.exec_driver_sql('CREATE TABLE cutting_ops_masters (id TEXT PRIMARY KEY)')
        with Operations.context(MigrationContext.configure(connection)):
            if partial:
                with pytest.raises(RuntimeError, match='cutting schema is incomplete'):
                    migration['upgrade']()
            else:
                migration['upgrade'](); migration['upgrade']()
                assert {'cutting_ops_masters', 'cutting_ops_revisions', 'cutting_ops_commands'} <= set(sa.inspect(connection).get_table_names())
        assert connection.exec_driver_sql('SELECT * FROM molding_sample_items').one() == ('existing', 3600, 'keep')


def test_canonical_chain_has_one_head_and_upgrades_a_published_database(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    backend = Path(__file__).resolve().parents[1]
    assert ScriptDirectory.from_config(Config(str(backend / 'alembic.ini'))).get_heads() == ['20261009_0152']
    database = tmp_path / 'quote-target-chain.db'
    env = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix(), SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1')
    def upgrade(revision):
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=backend, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
    upgrade('20261009_0149')
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE preservation_probe (id TEXT PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO preservation_probe VALUES ('00001', '旧资料保留')")
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='alembic_version'")]
        columns = {name: [row[1] for row in db.execute(f'PRAGMA table_info("{name}")')] for name in tables}
        rows = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in tables}
    upgrade('head'); upgrade('head')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [('20261009_0152',)]
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for name in tables:
            projection = ','.join('"' + column + '"' for column in columns[name])
            assert db.execute(f'SELECT {projection} FROM "{name}"').fetchall() == rows[name]
