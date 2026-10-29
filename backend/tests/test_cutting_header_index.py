"""Optional SQLite metadata index: adoption, drift and real DDL rollback."""
from pathlib import Path
import importlib.util
import sqlite3
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.services.cutting_period_header_index import NAME, COLUMNS, select_hint

path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_0185_cutting_period_headers.py'
spec = importlib.util.spec_from_file_location('header_migration', path)
migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)


@pytest.fixture
def engine(tmp_path):
    db = sa.create_engine('sqlite:///' + str(tmp_path / 'cutting.db'))
    with db.begin() as con:
        con.exec_driver_sql('CREATE TABLE cutting_ops_period_events(id TEXT PRIMARY KEY,factory_id TEXT,month TEXT,version INTEGER,action TEXT,data TEXT,actor_id TEXT,actor_name TEXT,created_at TEXT,reason TEXT,UNIQUE(factory_id,version))')
        con.exec_driver_sql("CREATE TRIGGER cutting_period_no_update BEFORE UPDATE ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT,'immutable'); END")
        con.exec_driver_sql("CREATE TRIGGER cutting_period_no_delete BEFORE DELETE ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT,'immutable'); END")
        con.exec_driver_sql('INSERT INTO cutting_ops_period_events VALUES (?,?,?,?,?,?,?,?,?,?)', ('event','huakang-c','2026-10',1,'lock','{"frozen":"原金额"}','reviewer','合成复核','2026-11-01','原凭据'))
        con.exec_driver_sql('CREATE TABLE alembic_version(version_num TEXT)')
        con.exec_driver_sql("INSERT INTO alembic_version VALUES ('20261026_0184')")
    yield db
    db.dispose()


def invoke(con, function):
    with Operations.context(MigrationContext.configure(con)):
        function()


def test_upgrade_repeat_and_index_only_downgrade_preserve_immutable_data(engine):
    with engine.begin() as con:
        before = con.exec_driver_sql('SELECT * FROM cutting_ops_period_events').fetchall()
        invoke(con, migration.upgrade); invoke(con, migration.upgrade)
        assert migration.index_state(con)
        invoke(con, migration.downgrade)
        assert not migration.index_state(con)
        assert con.exec_driver_sql('SELECT * FROM cutting_ops_period_events').fetchall() == before
        with pytest.raises(sa.exc.IntegrityError, match='immutable'):
            con.exec_driver_sql('DELETE FROM cutting_ops_period_events')


def test_version_write_failure_rolls_back_actual_index_then_retry_succeeds(engine):
    with pytest.raises(RuntimeError, match='version failure'):
        with engine.begin() as con:
            invoke(con, migration.upgrade)
            assert con.connection.driver_connection.in_transaction
            raise RuntimeError('injected version failure')
    with engine.begin() as con:
        assert not migration.index_state(con)
        assert con.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '20261026_0184'
        invoke(con, migration.upgrade)
        con.exec_driver_sql("UPDATE alembic_version SET version_num='20261028_0185'")
    with engine.connect() as con:
        assert migration.index_state(con)
        assert con.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '20261028_0185'


@pytest.mark.parametrize('ddl', [
    'CREATE INDEX {name} ON cutting_ops_period_events (id)',
    'CREATE UNIQUE INDEX {name} ON cutting_ops_period_events ({cols})',
    "CREATE INDEX {name} ON cutting_ops_period_events ({cols}) WHERE month='2026-10'",
    'CREATE INDEX {name} ON cutting_ops_period_events (id DESC,factory_id,month,version,action,actor_id,actor_name,created_at,reason)',
    'CREATE INDEX {name} ON cutting_ops_period_events (id COLLATE NOCASE,factory_id,month,version,action,actor_id,actor_name,created_at,reason)',
])
def test_migration_and_runtime_refuse_incompatible_same_named_index(engine, ddl):
    with engine.begin() as con: con.exec_driver_sql(ddl.format(name=NAME, cols=','.join(COLUMNS)))
    with engine.begin() as con:
        with pytest.raises(RuntimeError, match='contract differs'): invoke(con, migration.upgrade)
    with sqlite3.connect(engine.url.database) as reader:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error: select_hint(reader)
        assert error.value.status_code == 503


def test_old_database_fallback_and_exact_adoption(engine):
    with sqlite3.connect(engine.url.database) as reader: assert select_hint(reader) == ''
    with engine.begin() as con: con.exec_driver_sql('CREATE INDEX '+NAME+' ON cutting_ops_period_events ('+','.join(COLUMNS)+')')
    with engine.begin() as con: invoke(con, migration.upgrade)
    with sqlite3.connect(engine.url.database) as reader:
        assert select_hint(reader) == ' INDEXED BY '+NAME
        assert any('COVERING INDEX '+NAME in row[-1] for row in reader.execute(
            'EXPLAIN QUERY PLAN SELECT actor_id,actor_name,created_at,reason FROM cutting_ops_period_events'+select_hint(reader)+
            ' WHERE id=? AND factory_id=? AND month=? AND version=? AND action=?', ('event','huakang-c','2026-10',1,'lock')))


def test_conflicting_object_is_not_adopted(engine):
    with engine.begin() as con: con.exec_driver_sql('CREATE TABLE '+NAME+'(id TEXT)')
    with engine.begin() as con:
        with pytest.raises(RuntimeError, match='occupied'): invoke(con, migration.upgrade)


def test_postgres_path_has_no_implicit_wide_text_index(monkeypatch):
    from types import SimpleNamespace
    class FakeOp:
        def get_context(self): return SimpleNamespace(as_sql=False)
        def get_bind(self): return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def create_index(self, *args, **kwargs): raise AssertionError('No PostgreSQL index is authorized by this migration')
    monkeypatch.setattr(migration, 'op', FakeOp())
    migration.upgrade(); migration.downgrade()
