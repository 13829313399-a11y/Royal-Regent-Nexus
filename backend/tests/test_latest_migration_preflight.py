"""New canonical heads retain historical preflight guards and repeat safely."""
import sqlite3
import pytest
from test_cutting_jp_migration import base_database, clone, migrate, snapshot, version_snapshot

@pytest.fixture(scope='module')
def latest_database(base_database, tmp_path_factory):
    path = clone(base_database, tmp_path_factory.mktemp('latest-head-preflight'))
    migrate(path, '20261102_0189')
    for revision in ('20261104_0190', '20261104_0191', '20261104_0192', '20261107_0193', '20261110_0194'):
        migrate(path, revision)
        before = snapshot(path)
        migrate(path, revision)
        assert snapshot(path) == before
        assert version_snapshot(path) == [(revision,)]
    return path

def test_latest_heads_repeat_without_rewriting_existing_rows(latest_database):
    before = snapshot(latest_database)
    migrate(latest_database, 'head')
    assert snapshot(latest_database) == before
    with sqlite3.connect(latest_database) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []

@pytest.mark.parametrize('damage, message', [
    ('header_index', 'cutting header index is missing'),
    ('history_trigger', '0163 schema drift'),
    ('unknown_revision', 'Unknown 0163 collision history'),
])
def test_latest_head_still_rejects_damage_before_writes(latest_database, tmp_path, damage, message):
    path = clone(latest_database, tmp_path)
    with sqlite3.connect(path) as db:
        if damage == 'header_index':
            db.execute('DROP INDEX ix_cutting_period_headers')
        elif damage == 'history_trigger':
            db.execute('DROP TRIGGER cutting_period_no_update')
        else:
            db.execute("UPDATE alembic_version SET version_num='unknown-history'")
    before, versions = snapshot(path), version_snapshot(path)
    assert message in migrate(path, 'head', success=False).stderr
    assert snapshot(path) == before
    assert version_snapshot(path) == versions
