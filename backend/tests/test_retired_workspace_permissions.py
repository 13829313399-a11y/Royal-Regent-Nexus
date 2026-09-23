import importlib.util
from pathlib import Path

import sqlalchemy as sa


def test_retirement_is_exact_scoped_and_idempotent():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20260922_0120_retire_uv_permissions.py"
    spec = importlib.util.spec_from_file_location("retirement", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE auth_permissions (id TEXT PRIMARY KEY, code TEXT)",
            "CREATE TABLE auth_role_permissions (role_id TEXT, permission_id TEXT)",
            "CREATE TABLE auth_permission_metadata (permission_id TEXT)",
            "CREATE TABLE auth_user_permission_overrides (user_id TEXT, permission_id TEXT)",
            "CREATE TABLE auth_user_roles (user_id TEXT, role_id TEXT)",
            "CREATE TABLE auth_role_metadata (role_id TEXT, version INTEGER, updated_at TEXT)",
            "CREATE TABLE auth_user_authorization_revisions (user_id TEXT, revision INTEGER, updated_at TEXT)",
            "CREATE TABLE uv_reports (id TEXT, quantity INTEGER)",
            "CREATE TABLE auth_authorization_events (id TEXT, permission_id TEXT)",
            "INSERT INTO auth_permissions VALUES ('retired', 'uv_printing:read'), ('other', 'uvXprinting:read'), ('custom', 'uv_printing:custom')",
            "INSERT INTO auth_role_permissions VALUES ('production', 'retired'), ('production', 'other'), ('other', 'other')",
            "INSERT INTO auth_permission_metadata VALUES ('retired'), ('other')",
            "INSERT INTO auth_user_roles VALUES ('operator', 'production'), ('unaffected', 'other')",
            "INSERT INTO auth_user_permission_overrides VALUES ('override', 'retired'), ('unaffected', 'other')",
            "INSERT INTO auth_role_metadata VALUES ('production', 4, ''), ('other', 2, '')",
            "INSERT INTO auth_user_authorization_revisions VALUES ('operator', 2, ''), ('override', 3, ''), ('unaffected', 1, '')",
            "INSERT INTO uv_reports VALUES ('historical', 100)",
            "INSERT INTO auth_authorization_events VALUES ('evidence', 'retired')",
        ):
            connection.execute(sa.text(statement))
        migration.retire_permissions(connection)
        migration.retire_permissions(connection)
        def rows(query):
            return connection.execute(sa.text(query)).all()
        assert rows("SELECT id FROM auth_permissions ORDER BY id") == [('custom',), ('other',)]
        assert rows("SELECT role_id, permission_id FROM auth_role_permissions ORDER BY role_id") == [('other', 'other'), ('production', 'other')]
        assert rows("SELECT permission_id FROM auth_permission_metadata") == [('other',)]
        assert rows("SELECT user_id FROM auth_user_permission_overrides") == [('unaffected',)]
        assert rows("SELECT user_id, revision FROM auth_user_authorization_revisions ORDER BY user_id") == [('operator', 3), ('override', 4), ('unaffected', 1)]
        assert rows("SELECT role_id, version FROM auth_role_metadata ORDER BY role_id") == [('other', 2), ('production', 5)]
        assert rows("SELECT * FROM uv_reports") == [('historical', 100)]
        assert rows("SELECT * FROM auth_authorization_events") == [('evidence', 'retired')]
