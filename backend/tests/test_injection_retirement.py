"""Safety boundary for permanently retiring the old scheduling database."""

import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.util import CommandError

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/20261116_inj_retire_scheduling.py"


@pytest.fixture
def migration(monkeypatch):
    spec = importlib.util.spec_from_file_location("retired_injection_v3_purge", MIGRATION_PATH)
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
                "CREATE TABLE injection_v3_demand (id TEXT PRIMARY KEY, old_order_id TEXT REFERENCES injection_scheduling_orders(id))",
                "CREATE TABLE injection_ops_runs (id TEXT PRIMARY KEY, source TEXT REFERENCES injection_v3_demand(id))",
                "CREATE VIEW injection_ops_summary AS SELECT * FROM injection_v3_demand",
                "CREATE TABLE molding_sample_orders (id TEXT PRIMARY KEY, payload TEXT)",
                "CREATE TABLE injectionXschedule_keep (id TEXT PRIMARY KEY)",
            ):
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql("INSERT INTO injection_scheduling_orders VALUES ('old-order')")
            connection.exec_driver_sql("INSERT INTO injection_v3_demand VALUES ('line','old-order')")
            connection.exec_driver_sql("CREATE TRIGGER immutable_lines BEFORE DELETE ON injection_v3_demand BEGIN SELECT RAISE(ABORT, 'immutable history'); END")
            connection.exec_driver_sql("INSERT INTO molding_sample_orders VALUES ('keep','unaltered')")
            for key, code in (
                ("old", "injection_scheduling:read"),
                ("center", "injection_schedule_center:read"),
                ("new", "production:injection_scheduling:view"),
                ("ops", "injection_ops:read"),
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
            preview_by_id = {
                "draft-ops": {"operations": [{"permission_id": "ops"}]},
                "draft-v3": {"permission_codes": ["injection_scheduling:read"]},
                "reason-only": {"reason": "injection-scheduling", "operations": [{"permission_code": "molding_sample:read"}]},
            }
            for ident, payload in preview_by_id.items():
                connection.execute(sa.text("INSERT INTO auth_authorization_previews VALUES (:id,:payload)"),
                                   {"id": ident, "payload": json.dumps(payload)})
            connection.exec_driver_sql("INSERT INTO auth_authorization_events VALUES ('system-audit','injection_scheduling:read and molding_sample:read')")
            connection.exec_driver_sql("INSERT INTO auth_iam_state VALUES ('injection_scheduling_seed','{}'),('keep','{}')")
            connection.exec_driver_sql("INSERT INTO auth_access_requests VALUES ('only','pending','','',''),('mixed','pending','','','')")
            connection.exec_driver_sql("INSERT INTO auth_access_request_items VALUES ('only-item','only','old'),('mixed-old','mixed','new'),('mixed-keep','mixed','keep')")
        yield connection
    engine.dispose()


def apply_migration(migration, db):
    with db.begin(), Operations.context(MigrationContext.configure(db)):
        migration.upgrade()


def test_purge_drops_v3_and_legacy_generations_and_preserves_other_business_and_audit(migration, db):
    apply_migration(migration, db)
    tables = set(sa.inspect(db).get_table_names())
    assert not any(name.startswith(migration.TABLE_PREFIXES) for name in tables)
    assert {"molding_sample_orders", "injectionXschedule_keep"} <= tables
    assert db.exec_driver_sql("SELECT * FROM molding_sample_orders").all() == [("keep", "unaltered")]
    assert db.exec_driver_sql("SELECT id FROM auth_permissions ORDER BY id").scalars().all() == ["keep", "similar"]
    assert db.exec_driver_sql("SELECT id FROM auth_role_permissions").scalars().all() == ["keep-grant"]
    assert db.exec_driver_sql("SELECT count(*) FROM auth_user_permission_overrides").scalar_one() == 0
    assert db.exec_driver_sql("SELECT id FROM auth_authorization_previews ORDER BY id").scalars().all() == ["keep", "reason-only"]
    assert db.exec_driver_sql("SELECT key FROM auth_iam_state").scalars().all() == ["keep"]
    assert db.exec_driver_sql("SELECT version FROM auth_role_metadata").scalar_one() == 5
    assert db.exec_driver_sql("SELECT revision FROM auth_user_authorization_revisions").scalar_one() == 8
    assert db.exec_driver_sql("SELECT id,status FROM auth_access_requests ORDER BY id").all() == [("mixed", "pending"), ("only", "rejected")]
    assert db.exec_driver_sql("SELECT id FROM auth_access_request_items").scalars().all() == ["mixed-keep"]
    assert db.exec_driver_sql("SELECT before_json FROM auth_authorization_events").scalar_one() == "injection_scheduling:read and molding_sample:read"
    assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("dependency", ["foreign_key", "view", "trigger", "chained_view", "uppercase_view", "uppercase_fk"])
def test_purge_refuses_unrelated_dependencies_before_mutating_any_data(migration, db, dependency):
    ddl = {
        "chained_view": "CREATE VIEW other_business AS SELECT * FROM injection_ops_summary",
        "uppercase_view": "CREATE VIEW other_business AS SELECT * FROM INJECTION_V3_DEMAND",
        "uppercase_fk": "CREATE TABLE other_business (source TEXT REFERENCES INJECTION_V3_DEMAND(id))",
        "foreign_key": "CREATE TABLE other_business (id TEXT PRIMARY KEY, source_id TEXT REFERENCES injection_v3_demand(id))",
        "view": "CREATE VIEW other_business AS SELECT * FROM injection_v3_demand",
        "trigger": "CREATE TRIGGER other_business AFTER UPDATE ON molding_sample_orders BEGIN SELECT id FROM injection_v3_demand; END",
    }[dependency]
    db.exec_driver_sql(ddl)
    db.commit()
    with pytest.raises(CommandError, match="unrelated"):
        apply_migration(migration, db)
    assert db.exec_driver_sql("SELECT count(*) FROM injection_v3_demand").scalar_one() == 1
    assert db.exec_driver_sql("SELECT count(*) FROM auth_permissions").scalar_one() == 6


def test_purge_is_repeatable_but_downgrade_cannot_invent_lost_data(migration, db):
    apply_migration(migration, db)
    apply_migration(migration, db)
    assert db.exec_driver_sql("SELECT version FROM auth_role_metadata").scalar_one() == 5
    with pytest.raises(CommandError, match="backup"):
        migration.downgrade()


def test_retired_api_permissions_and_assistant_cannot_read_or_recreate_tables(env):
    from sqlalchemy import event, inspect
    from app.services.assistant import business, registry, visibility
    from app.services.assistant.errors import AssistantError
    from app.services.permission_codes import APPLICATION_PERMISSION_CODES
    from test_work_center_api import actor
    client, database, calls, patch = env
    assert client.get('/api/injection-scheduling/state', params={'factory_id':'huaxing'}).status_code == 404
    assert client.get('/api/injection-ops/factories/huaxing/capabilities').status_code == 404
    assert not any(n.startswith(('injection_v3_', 'injection_schedule_', 'injection_scheduling_', 'injection_ops_')) for n in inspect(database.engine).get_table_names())
    assert not any(p.startswith('injection_scheduling:') for p in APPLICATION_PERMISSION_CODES)
    assert 'get_injection_overview' not in business.NAMES
    with pytest.raises(AssistantError):
        registry.resolve('injection-scheduling', 'demand')
    statements = []
    def capture(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(database.engine, 'before_cursor_execute', capture)
    try:
        with pytest.raises(AssistantError):
            business.query(actor(), 'get_injection_overview', {'factory_id':'huaxing'}, 'retired')
        assert not visibility.allowed(actor(), [{'kind':'business', 'tool_name':'get_injection_overview', 'scope':{'factory_id':'huaxing'}}])
    finally:
        event.remove(database.engine, 'before_cursor_execute', capture)
    assert not any('injection_v3_' in s for s in statements)
    assert not calls

from test_assistant_api import env
