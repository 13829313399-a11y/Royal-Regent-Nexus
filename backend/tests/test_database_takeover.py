"""Takeover rehearsal safety: synthetic copies only, never the local database."""
from contextlib import closing
import sqlite3

import pytest

from tools import rehearse_database_takeover as takeover
from tools import audit_unversioned_database as audit


def database(path, sql):
    with closing(sqlite3.connect(path)) as db:
        db.executescript(sql)
        db.commit()
    return path


@pytest.fixture
def copies(tmp_path):
    source = database(tmp_path / 'source.db', """
        CREATE TABLE auth_users(id INTEGER PRIMARY KEY AUTOINCREMENT, payload BLOB);
        INSERT INTO auth_users VALUES(1, X'00FF');
        INSERT INTO auth_users VALUES(10, NULL);
        DELETE FROM auth_users WHERE id=10;
        CREATE TABLE internal_quote_customers(id TEXT PRIMARY KEY);
    """)
    canonical = database(tmp_path / 'canonical.db', """
        CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY);
        INSERT INTO alembic_version VALUES('synthetic');
        CREATE TABLE auth_users(id INTEGER PRIMARY KEY AUTOINCREMENT, payload BLOB);
        INSERT INTO auth_users VALUES(2, X'FF');
        CREATE TRIGGER auth_immutable BEFORE DELETE ON auth_users
            BEGIN SELECT RAISE(ABORT, 'immutable'); END;
        CREATE TABLE internal_quote_customers(id TEXT PRIMARY KEY);
        INSERT INTO internal_quote_customers VALUES('seed-customer');
        CREATE TABLE spray_factories(id TEXT PRIMARY KEY);
        INSERT INTO spray_factories VALUES('new-factory');
    """)
    return source, canonical, tmp_path / 'candidate.db'


def test_preserves_binary_empty_tables_versions_new_seeds_sequences_and_guards(copies):
    source, canonical, candidate = copies
    before, reference = audit.state(source), audit.state(canonical)
    result = takeover.import_original(*copies)
    assert result['preserved']['auth_users']['rows'] == 1
    assert result['preserved']['internal_quote_customers']['rows'] == 0
    assert result['new_tables']['spray_factories']['rows'] == 1
    assert not result['full_takeover_approved']
    assert audit.state(source) == before
    assert audit.state(canonical) == reference
    with closing(sqlite3.connect(candidate)) as db:
        assert db.execute('SELECT * FROM auth_users').fetchall() == [(1, b'\x00\xff')]
        assert db.execute('SELECT seq FROM sqlite_sequence WHERE name="auth_users"').fetchone() == (10,)
        assert db.execute('SELECT * FROM internal_quote_customers').fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            db.execute('DELETE FROM auth_users')
        db.execute('INSERT INTO auth_users(payload) VALUES (NULL)')
        assert db.execute('SELECT max(id) FROM auth_users').fetchone() == (11,)


@pytest.mark.parametrize('target', ['source', 'canonical', 'existing'])
def test_never_overwrites_existing_destination(copies, target):
    source, canonical, candidate = copies
    destination = {'source': source, 'canonical': canonical, 'existing': candidate}[target]
    if target == 'existing':
        database(destination, 'CREATE TABLE sentinel(x);')
    before = audit.state(destination)
    with pytest.raises(FileExistsError):
        takeover.import_original(source, canonical, destination)
    assert audit.state(destination) == before


@pytest.mark.parametrize('sql, message', [
    ('CREATE TABLE alembic_version(version_num TEXT);', 'unversioned'),
    ('CREATE TABLE unknown_table(id INTEGER);', 'Unknown original tables'),
    ('ALTER TABLE auth_users ADD COLUMN lost TEXT;', 'Original columns missing'),
])
def test_rejects_unknown_history_or_dropped_data(copies, sql, message):
    source, canonical, candidate = copies
    database(source, sql)
    before = audit.state(source)
    with pytest.raises(RuntimeError, match=message):
        takeover.import_original(*copies)
    assert audit.state(source) == before
    assert audit.state(candidate) == audit.state(canonical)


@pytest.mark.parametrize('sql, message', [
    ('ALTER TABLE auth_users ADD COLUMN unexpected TEXT;', 'Unreviewed'),
    ('CREATE TABLE strange_module(id TEXT);', 'Unclassified table'),
    ('''CREATE TABLE spray_links(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES auth_users(id));
        INSERT INTO spray_links VALUES(1,2);''', 'foreign-key'),
])
def test_rejects_unreviewed_seed_dependencies_and_columns(copies, sql, message):
    source, canonical, candidate = copies
    database(canonical, sql)
    with pytest.raises(RuntimeError, match=message):
        takeover.import_original(*copies)
    assert audit.state(candidate) == audit.state(canonical)


def test_failure_after_import_rolls_back_deleted_seeds_and_dropped_triggers(copies, monkeypatch):
    def interrupt(*args):
        raise RuntimeError('injected verification failure')
    monkeypatch.setattr(takeover, 'verify_original', interrupt)
    with pytest.raises(RuntimeError, match='injected'):
        takeover.import_original(*copies)
    assert audit.state(copies[2]) == audit.state(copies[1])


def test_check_constraint_failure_does_not_coerce_or_drop_original_rows(tmp_path):
    source = database(tmp_path / 'source.db', 'CREATE TABLE raw_materials(id INTEGER, qty INTEGER); INSERT INTO raw_materials VALUES(1,-1);')
    canonical = database(tmp_path / 'canonical.db', """
        CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic');
        CREATE TABLE raw_materials(id INTEGER, qty INTEGER CHECK(qty>=0));
        INSERT INTO raw_materials VALUES(2,5);
    """)
    candidate = tmp_path / 'candidate.db'
    before = audit.state(source)
    with pytest.raises(sqlite3.IntegrityError):
        takeover.import_original(source, canonical, candidate)
    assert audit.state(source) == before
    assert audit.state(candidate) == audit.state(canonical)


def test_only_explicit_nullable_carton_additions_are_allowed(tmp_path):
    source = database(tmp_path / 'source.db', 'CREATE TABLE carton_orders(id TEXT); INSERT INTO carton_orders VALUES("kept");')
    canonical = database(tmp_path / 'canonical.db', """
        CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic');
        CREATE TABLE carton_orders(id TEXT, gross_weight_kg NUMERIC, net_weight_kg NUMERIC);
    """)
    candidate = tmp_path / 'candidate.db'
    result = takeover.import_original(source, canonical, candidate)
    assert result['nullable_additions']['carton_orders'] == ['gross_weight_kg', 'net_weight_kg']
    with closing(sqlite3.connect(candidate)) as db:
        assert db.execute('SELECT * FROM carton_orders').fetchall() == [('kept', None, None)]


def test_other_autoincrement_table_cannot_hide_original_sequence_semantics(tmp_path):
    source = database(tmp_path / 'source.db', '''
        CREATE TABLE auth_users(id INTEGER PRIMARY KEY AUTOINCREMENT);
        INSERT INTO auth_users VALUES(10); DELETE FROM auth_users;
    ''')
    canonical = database(tmp_path / 'canonical.db', '''
        CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic');
        CREATE TABLE auth_users(id INTEGER PRIMARY KEY);
        CREATE TABLE spray_factories(id INTEGER PRIMARY KEY AUTOINCREMENT);
    ''')
    candidate = tmp_path / 'candidate.db'
    with pytest.raises(RuntimeError, match='Autoincrement/rowid'):
        takeover.import_original(source, canonical, candidate)
    assert audit.state(candidate) == audit.state(canonical)


def test_allocation_keywords_in_literals_and_comments_are_not_table_options(tmp_path):
    path = database(tmp_path / 'test.db', '''
        CREATE TABLE auth_users(id INTEGER PRIMARY KEY, "AUTOINCREMENT" TEXT DEFAULT 'WITHOUT ROWID'
          /* AUTOINCREMENT */);
    ''')
    with audit.readonly(path) as db:
        assert takeover.table_options(db, 'auth_users') == (False, False)


def test_comments_between_without_and_rowid_are_whitespace(tmp_path):
    path = database(tmp_path / 'test.db', '''
        CREATE TABLE auth_users(id TEXT PRIMARY KEY NOT NULL) WITHOUT/* note */ROWID;
    ''')
    with audit.readonly(path) as db:
        assert takeover.table_options(db, 'auth_users') == (False, True)


@pytest.mark.parametrize('change', [dict(exit_code=1), dict(changed_tables={'auth_users': {}}),
    dict(schema_changed=True), dict(identity_changed=['auth_roles']), dict(integrity=[('bad',)]),
    dict(foreign_key_violations=[('bad',)])])
def test_initialization_changes_or_errors_cannot_be_passed(change):
    good = dict(exit_code=0, changed_tables={}, schema_changed=False, identity_changed=[],
                integrity=[('ok',)], foreign_key_violations=[])
    assert takeover.initialization_passed([good, good])
    assert not takeover.initialization_passed([good])
    assert not takeover.initialization_passed([good, dict(good, **change)])
