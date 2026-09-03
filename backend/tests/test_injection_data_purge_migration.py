"""Safety boundary for permanently retiring the old scheduling database."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.util import CommandError

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/20260903_0095_purge_retired_injection_scheduling.py"


@pytest.fixture
def migration(monkeypatch):
    spec = importlib.util.spec_from_file_location("retired_injection_purge", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.context, "is_offline_mode", lambda: False)
    return module


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        with connection.begin():
            for statement in (
                "CREATE TABLE auth_permissions (id TEXT PRIMARY KEY, code TEXT)",
                "CREATE TABLE auth_permission_metadata (permission_id TEXT PRIMARY KEY REFERENCES auth_permissions(id))",
                "CREATE TABLE auth_role_permissions (id TEXT PRIMARY KEY, role_id TEXT, permission_id TEXT REFERENCES auth_permissions(id))",
                "CREATE TABLE auth_user_permission_overrides (id TEXT PRIMARY KEY, user_id TEXT, permission_id TEXT REFERENCES auth_permissions(id))",
                "CREATE TABLE auth_user_roles (id TEXT PRIMARY KEY, user_id TEXT, role_id TEXT)",
                "CREATE TABLE auth_role_metadata (role_id TEXT PRIMARY KEY, version INTEGER, updated_at TEXT)",
                "CREATE TABLE auth_user_authorization_revisions (user_id TEXT PRIMARY KEY, revision INTEGER, updated_at TEXT)",
                "CREATE TABLE auth_authorization_previews (id TEXT PRIMARY KEY, payload_json TEXT)",
                "CREATE TABLE auth_authorization_events (id TEXT PRIMARY KEY, before_json TEXT)",
                "CREATE TABLE auth_iam_state (key TEXT PRIMARY KEY, value_json TEXT)",
                "CREATE TABLE auth_access_requests (id TEXT PRIMARY KEY, status TEXT, decision_comment TEXT, decided_at TEXT, updated_at TEXT)",
                "CREATE TABLE auth_access_request_items (id TEXT PRIMARY KEY, request_id TEXT REFERENCES auth_access_requests(id), permission_id TEXT)",
                "CREATE TABLE injection_scheduling_orders (id TEXT PRIMARY KEY)",
                "CREATE TABLE injection_schedule_lines (id TEXT PRIMARY KEY, old_order_id TEXT REFERENCES injection_scheduling_orders(id))",
                "CREATE TABLE molding_sample_orders (id TEXT PRIMARY KEY, payload TEXT)",
                "CREATE TABLE injectionXschedule_keep (id TEXT PRIMARY KEY)",
            ):
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql("INSERT INTO injection_scheduling_orders VALUES ('old-order')")
            connection.exec_driver_sql("INSERT INTO injection_schedule_lines VALUES ('line','old-order')")
            connection.exec_driver_sql("CREATE TRIGGER immutable_lines BEFORE DELETE ON injection_schedule_lines BEGIN SELECT RAISE(ABORT, 'immutable history'); END")
            connection.exec_driver_sql("INSERT INTO molding_sample_orders VALUES ('keep','unaltered')")
            for key, code in (
                ("old", "injection_scheduling:read"),
                ("center", "injection_schedule_center:read"),
                ("new", "production:injection_scheduling:view"),
                ("keep", "molding_sample:read"),
                ("similar", "injectionXschedule_center:read"),
            ):
                connection.execute(sa.text("INSERT INTO auth_permissions VALUES (:id,:code)"), {"id": key, "code": code})
                connection.execute(sa.text("INSERT INTO auth_permission_metadata VALUES (:id)"), {"id": key})
            connection.exec_driver_sql("INSERT INTO auth_role_permissions VALUES ('old-grant','role','old'),('keep-grant','role','keep')")
            connection.exec_driver_sql("INSERT INTO auth_user_roles VALUES ('binding','user','role')")
            connection.exec_driver_sql("INSERT INTO auth_role_metadata VALUES ('role',4,'before')")
            connection.exec_driver_sql("INSERT INTO auth_user_authorization_revisions VALUES ('user',7,'before')")
            connection.exec_driver_sql("INSERT INTO auth_user_permission_overrides VALUES ('override','user','new')")
            connection.exec_driver_sql("INSERT INTO auth_authorization_previews VALUES ('stale','production:injection_scheduling:view'),('keep','molding_sample:read')")
            connection.exec_driver_sql("INSERT INTO auth_authorization_events VALUES ('system-audit','injection_scheduling:read and molding_sample:read')")
            connection.exec_driver_sql("INSERT INTO auth_iam_state VALUES ('injection_scheduling_seed','{}'),('keep','{}')")
            connection.exec_driver_sql("INSERT INTO auth_access_requests VALUES ('only','pending','','',''),('mixed','pending','','','')")
            connection.exec_driver_sql("INSERT INTO auth_access_request_items VALUES ('only-item','only','old'),('mixed-old','mixed','new'),('mixed-keep','mixed','keep')")
        yield connection
    engine.dispose()


def apply_migration(migration, db):
    with db.begin(), Operations.context(MigrationContext.configure(db)):
        migration.upgrade()


def test_purge_drops_both_generations_and_preserves_other_business_and_audit(migration, db):
    apply_migration(migration, db)
    tables = set(sa.inspect(db).get_table_names())
    assert not any(name.startswith(migration.TABLE_PREFIXES) for name in tables)
    assert {"molding_sample_orders", "injectionXschedule_keep"} <= tables
    assert db.exec_driver_sql("SELECT * FROM molding_sample_orders").all() == [("keep", "unaltered")]
    assert db.exec_driver_sql("SELECT id FROM auth_permissions ORDER BY id").scalars().all() == ["keep", "similar"]
    assert db.exec_driver_sql("SELECT id FROM auth_role_permissions").scalars().all() == ["keep-grant"]
    assert db.exec_driver_sql("SELECT count(*) FROM auth_user_permission_overrides").scalar_one() == 0
    assert db.exec_driver_sql("SELECT id FROM auth_authorization_previews").scalars().all() == ["keep"]
    assert db.exec_driver_sql("SELECT key FROM auth_iam_state").scalars().all() == ["keep"]
    assert db.exec_driver_sql("SELECT version FROM auth_role_metadata").scalar_one() == 5
    assert db.exec_driver_sql("SELECT revision FROM auth_user_authorization_revisions").scalar_one() == 8
    assert db.exec_driver_sql("SELECT id,status FROM auth_access_requests ORDER BY id").all() == [("mixed", "pending"), ("only", "rejected")]
    assert db.exec_driver_sql("SELECT id FROM auth_access_request_items").scalars().all() == ["mixed-keep"]
    assert db.exec_driver_sql("SELECT before_json FROM auth_authorization_events").scalar_one() == "injection_scheduling:read and molding_sample:read"
    assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("dependency", ["foreign_key", "view", "trigger"])
def test_purge_refuses_unrelated_dependencies_before_mutating_any_data(migration, db, dependency):
    ddl = {
        "foreign_key": "CREATE TABLE other_business (id TEXT PRIMARY KEY, source_id TEXT REFERENCES injection_schedule_lines(id))",
        "view": "CREATE VIEW other_business AS SELECT * FROM injection_schedule_lines",
        "trigger": "CREATE TRIGGER other_business AFTER UPDATE ON molding_sample_orders BEGIN SELECT id FROM injection_schedule_lines; END",
    }[dependency]
    db.exec_driver_sql(ddl)
    db.commit()
    with pytest.raises(CommandError, match="unrelated"):
        apply_migration(migration, db)
    assert db.exec_driver_sql("SELECT count(*) FROM injection_schedule_lines").scalar_one() == 1
    assert db.exec_driver_sql("SELECT count(*) FROM auth_permissions").scalar_one() == 5


def test_purge_is_repeatable_but_downgrade_cannot_invent_lost_data(migration, db):
    apply_migration(migration, db)
    apply_migration(migration, db)
    assert db.exec_driver_sql("SELECT version FROM auth_role_metadata").scalar_one() == 5
    with pytest.raises(CommandError, match="backup"):
        migration.downgrade()
