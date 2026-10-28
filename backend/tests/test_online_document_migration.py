"""New document branch/merge must remain repeatable and retain legacy guards."""
import sqlite3

from test_cutting_jp_migration import base_database, clone, migrate, snapshot, version_snapshot


def test_online_document_branch_merge_and_repeat_preserve_original_tables(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261023_0176')
    before = snapshot(path)
    migrate(path, '20261026_0177')
    assert set(version_snapshot(path)) == {('20261023_0176',), ('20261026_0177',)}
    migrate(path, '20261026_0178')
    after = snapshot(path)
    assert set(after) - set(before) == {'online_documents', 'online_document_revisions'}
    assert all(after[name] == data for name, data in before.items())
    migrate(path, '20261026_0178')
    assert snapshot(path) == after
    # The new head cannot bypass complete historical-schema validation.
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE cutting_ops_period_events')
    damaged = snapshot(path)
    result = migrate(path, '20261026_0178', success=False)
    assert 'incomplete' in result.stderr
    assert snapshot(path) == damaged


def test_online_document_standalone_branch_rejects_unknown_version(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261026_0177')
    migrate(path, '20261026_0177')
    with sqlite3.connect(path) as db:
        db.execute("UPDATE alembic_version SET version_num='unknown-office-history'")
    before = snapshot(path)
    assert 'Unknown 0163' in migrate(path, '20261026_0178', success=False).stderr
    assert snapshot(path) == before


def test_management_branch_preserves_original_data_and_repeat(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261026_0177')
    before = snapshot(path)
    migrate(path, '20261026_0179')
    assert version_snapshot(path) == [('20261026_0179',)]
    after = snapshot(path)
    assert set(after) - set(before) == {'online_document_events'}
    assert all(after[name] == data for name, data in before.items() if name not in {'online_documents', 'online_document_revisions'})
    migrate(path, '20261026_0179')
    assert snapshot(path) == after
    migrate(path, '20261026_0180')
    assert version_snapshot(path) == [('20261026_0180',)]
    merged = snapshot(path)
    migrate(path, '20261026_0180')
    assert snapshot(path) == merged


def test_folder_version_upgrade_preserves_folder_data_and_repeats(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261026_0182')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO online_document_folders (id,factory_id,owner_id,owner_epoch,name,name_key,created_at,deleted_at) VALUES ('folder-proof','group','owner',1,'月份','月份','time','')")
        before = db.execute('SELECT * FROM online_document_folders').fetchall()
    migrate(path, '20261026_0184')
    assert version_snapshot(path) == [('20261026_0184',)]
    with sqlite3.connect(path) as db:
        after = db.execute('SELECT * FROM online_document_folders').fetchall()
        assert [r[:-1] for r in after] == before and after[0][-1] == 1
    state = snapshot(path)
    migrate(path, '20261026_0184')
    assert snapshot(path) == state


def test_folder_branch_and_merge_preserve_existing_tables(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261026_0179')
    before = snapshot(path)
    migrate(path, '20261026_0181')
    assert version_snapshot(path) == [('20261026_0181',)]
    after = snapshot(path)
    assert set(after) - set(before) == {'online_document_folders', 'online_document_placements'}
    assert all(after[name] == data for name, data in before.items())
    migrate(path, '20261026_0181')
    assert snapshot(path) == after
    migrate(path, '20261026_0182')
    assert version_snapshot(path) == [('20261026_0182',)]
    merged = snapshot(path)
    migrate(path, '20261026_0182')
    assert snapshot(path) == merged
