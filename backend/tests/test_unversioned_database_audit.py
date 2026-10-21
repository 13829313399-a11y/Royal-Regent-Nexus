"""Audit/rehearsal safety checks against disposable SQLite databases only."""
import sqlite3

import pytest

from tools import audit_unversioned_database as audit


@pytest.fixture
def original(tmp_path):
    path = tmp_path / 'original.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE order_ledger_sources (id TEXT PRIMARY KEY, payload BLOB)')
        db.execute('INSERT INTO order_ledger_sources VALUES (?,?)', ('00001', b'\x00\xff-original'))
        db.execute('CREATE TABLE original_account (id TEXT PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO original_account VALUES ('admin-fixture','original-permission')")
    return path


def test_backup_is_exclusive_and_preserves_binary_rows(original, tmp_path):
    before = audit.state(original)
    copy = tmp_path / 'copy.db'
    audit.backup(original, copy)
    assert audit.state(copy) == before
    with pytest.raises(FileExistsError):
        audit.backup(original, original)
    assert audit.state(original) == before


def test_readers_and_backup_close_all_connections(original, tmp_path, monkeypatch):
    connect = sqlite3.connect
    connections = []
    def track(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection
    monkeypatch.setattr(audit.sqlite3, 'connect', track)
    copy = tmp_path / 'copy.db'
    audit.backup(original, copy)
    audit.state(copy)
    audit.compare(original, copy)
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            connection.execute('SELECT 1')
    copy.unlink()


def test_unrelated_failure_cannot_be_classified_as_expected_rejection():
    report = dict(rehearsal_exit=1, rehearsal_unknown_history_rejected=True,
                  rehearsal_unchanged=True, baseline_backup_unchanged=True, source_unchanged=True)
    assert audit.expected_rejection(report)
    for key in ('rehearsal_unknown_history_rejected', 'rehearsal_unchanged', 'baseline_backup_unchanged', 'source_unchanged'):
        assert not audit.expected_rejection(dict(report, **{key:False}))


def test_catalog_reports_defaults_missing_columns_and_check_changes(original, tmp_path):
    canonical = tmp_path / 'canonical.db'
    with sqlite3.connect(canonical) as db:
        db.execute("CREATE TABLE original_account (id TEXT PRIMARY KEY, value TEXT DEFAULT 'x' CHECK(length(value)>0), added TEXT)")
        db.execute('CREATE INDEX expected_index ON original_account(value)')
        db.execute('CREATE TABLE new_module (id TEXT PRIMARY KEY)')
    diff = audit.compare(original, canonical)
    assert diff['missing_columns'] == ['original_account.added']
    assert diff['default_differences'] == ['original_account.value']
    assert diff['missing_tables'] == ['new_module']
    assert diff['extra_tables'] == ['order_ledger_sources']
    assert diff['missing_existing_table_objects']['index'] == ['expected_index']
    assert 'ddl' in diff['differences']['original_account']


def test_additive_rehearsal_preserves_source_and_never_stamps(original, tmp_path):
    before = audit.state(original)
    receipt = audit.rehearse_jp(original, tmp_path)
    assert receipt['original_rows_preserved'] == 2
    assert len(receipt['new_empty_tables']) == 5
    assert receipt['repeated_execution_unchanged'] and not receipt['version_created']
    assert audit.state(original) == before


@pytest.mark.parametrize('damage', ['partial', 'object_conflict', 'versioned', 'missing_dependency'])
def test_unsafe_copy_refused_without_mutation(original, damage):
    with sqlite3.connect(original) as db:
        if damage == 'partial': db.execute('CREATE TABLE jp_intake_counters (x TEXT)')
        if damage == 'object_conflict': db.execute('CREATE INDEX ix_jp_intake_exports_created_at ON original_account(value)')
        if damage == 'versioned': db.execute('CREATE TABLE alembic_version (version_num TEXT)')
        if damage == 'missing_dependency': db.execute('DROP TABLE order_ledger_sources')
    before = audit.state(original)
    with pytest.raises(RuntimeError):
        audit.complete_jp_copy(original)
    assert audit.state(original) == before


def test_mid_creation_failure_rolls_back_and_retries(original, monkeypatch):
    before = audit.state(original)
    actual_run_path = audit.runpy.run_path
    def patched(path):
        module = actual_run_path(path)
        if '_run' in module:
            original_run = module['_run']
            def fail_after_creation(*args):
                original_run(*args)
                raise RuntimeError('injected after DDL')
            module['_run'] = fail_after_creation
        return module
    with monkeypatch.context() as patch:
        patch.setattr(audit.runpy, 'run_path', patched)
        with pytest.raises(RuntimeError, match='injected'):
            audit.complete_jp_copy(original)
    assert audit.state(original) == before
    audit.complete_jp_copy(original)
    after = audit.state(original)
    audit.complete_jp_copy(original)
    assert audit.state(original) == after
