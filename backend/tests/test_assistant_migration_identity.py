"""Canonical assistant migrations preserve rows and reject ambiguous local history."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from test_cutting_jp_migration import base_database, clone, migrate, snapshot, version_snapshot

BACKEND = Path(__file__).resolve().parents[1]


def test_historical_assistant_migrations_remain_byte_exact():
    expected = {
        '20261026_0176_assistant_durable_runs.py': 'e27700169dbc22b3f9e8bd440ac15f511c0708f11e6ff72b66b0becd46114249',
        '20261026_0177_assistant_operations.py': '635999dac5b9e7ecbaf86d5969dc26e988c479d7699c03e30b93e29f98040560',
    }
    for name, digest in expected.items():
        canonical_bytes = (BACKEND / 'alembic/legacy' / name).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(canonical_bytes).hexdigest() == digest
        assert not (BACKEND / 'alembic/versions' / name).exists()


@pytest.mark.parametrize('revision, table', [
    ('20261026_0176', 'nexus_assistant_executions'),
    ('20261026_0177', 'nexus_assistant_executions'),
    ('20261026_0177', 'nexus_assistant_feedback'),
])
def test_legacy_assistant_upgrade_refuses_before_any_write(tmp_path, revision, table):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        db.execute('INSERT INTO alembic_version VALUES (?)', (revision,))
        db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, evidence TEXT)')
        db.execute(f'INSERT INTO {table} VALUES (?, ?)', ('original', 'private retained evidence'))
        before = list(db.iterdump())
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(path), PYTHONUTF8='1', ONLINE_DOCUMENTS_ENABLED='false')
    result = subprocess.run([sys.executable, '-m', 'alembic', '-c', str(BACKEND / 'alembic.ini'), 'upgrade', 'head'],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode != 0 and 'Legacy local assistant' in result.stderr
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before


def test_canonical_assistant_upgrade_retains_all_existing_tables_and_repeats(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261030_0187')
    before = snapshot(path)
    migrate(path, 'head')
    after = snapshot(path)
    assert version_snapshot(path) == [('20261102_0189',)]
    assert set(after) - set(before) == {
        'nexus_assistant_executions', 'nexus_assistant_run_events', 'nexus_assistant_provider_steps',
        'nexus_assistant_run_metrics', 'nexus_assistant_subscriptions', 'nexus_assistant_feedback',
    }
    assert all(after[name] == value for name, value in before.items())
    migrate(path, 'head')
    assert snapshot(path) == after
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        db.execute('DROP INDEX ix_cutting_period_headers')
    damaged = snapshot(path)
    assert 'cutting header index is missing' in migrate(path, 'head', success=False).stderr
    assert snapshot(path) == damaged
