"""Carton rush migration preserves orders and the frozen local 0173 script."""
from hashlib import sha256
from pathlib import Path
import runpy

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn
from test_cutting_jp_migration import migrate, snapshot, version_snapshot

BACKEND = Path(__file__).resolve().parents[1]
PATH = BACKEND / 'alembic/versions/20261022_0175_carton_order_rush_manual.py'


def test_rush_upgrade_preserves_original_order_and_defaults():
    module = runpy.run_path(str(PATH))
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE carton_orders (id TEXT PRIMARY KEY, quantity INTEGER)')
        connection.exec_driver_sql("INSERT INTO carton_orders VALUES ('0001', 123)")
        with Operations.context(MigrationContext.configure(connection)):
            module['upgrade']()
            module['validate_rush_schema'](connection)
            assert tuple(connection.exec_driver_sql('SELECT * FROM carton_orders').one()) == (
                '0001', 123, 0, 0, '', None, None, None, None)
            connection.exec_driver_sql("UPDATE carton_orders SET rush = 1, rush_reason = 'retained evidence'")
            module['upgrade']()
            assert connection.exec_driver_sql('SELECT rush, rush_reason FROM carton_orders').one() == (1, 'retained evidence')
            with pytest.raises(RuntimeError, match='preserved'):
                module['downgrade']()
    engine.dispose()


def test_partial_legacy_rush_schema_is_rejected_without_adding_columns():
    module = runpy.run_path(str(PATH))
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE carton_orders (id TEXT, rush BOOLEAN NOT NULL DEFAULT 0)')
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match='mismatch'):
                module['upgrade']()
        assert [column['name'] for column in sa.inspect(connection).get_columns('carton_orders')] == ['id', 'rush']
    engine.dispose()


def test_postgresql_boolean_defaults_use_false():
    module = runpy.run_path(str(PATH))
    for column in module['columns']()[:2]:
        assert 'DEFAULT false NOT NULL' in str(CreateColumn(column).compile(dialect=postgresql.dialect()))


def test_local_0173_archive_keeps_its_original_bytes():
    archive = BACKEND / 'alembic/legacy/20261022_0173_carton_order_rush_manual.py'
    assert runpy.run_path(str(archive))['revision'] == '20261022_0173'
    assert sha256(archive.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == '814d5429f145bdb0b28ae9aab676ed1da806b2c36297391818f4c16e6904b704'


def test_canonical_chain_preserves_prior_tables_and_repeats_at_head(tmp_path):
    import sqlite3

    path = tmp_path / 'canonical.db'
    migrate(path, '20261022_0174')
    before = snapshot(path)
    with sqlite3.connect(path) as connection:
        original_columns = connection.execute('PRAGMA table_info(carton_orders)').fetchall()
    migrate(path, 'head')
    after = snapshot(path)
    assert after.keys() == before.keys()
    for name, value in before.items():
        if name != 'carton_orders':
            assert after[name] == value, name
    with sqlite3.connect(path) as connection:
        columns = connection.execute('PRAGMA table_info(carton_orders)').fetchall()
        assert columns[:len(original_columns)] == original_columns
        assert len(columns) == len(original_columns) + 7
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    assert version_snapshot(path) == [('20261022_0175',)]
    migrate(path, 'head')
    assert snapshot(path) == after
