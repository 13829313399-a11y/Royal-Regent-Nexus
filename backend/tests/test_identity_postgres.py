"""Real independent PostgreSQL connections; requires an explicit loopback test URL."""
import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from test_identity_changes import client, engineer, identity, draft, preview, confirm
from test_iam_api import create_user


@pytest.fixture
def postgres(client):
    url = os.getenv("IAM_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("IAM_TEST_POSTGRES_URL not provided")
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"} and parsed.database == "iam_v2_test", "Dedicated local IAM test DB only"
    schema = "iam_qa_" + uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    dbm = importlib.import_module("app.db")
    original_engine, original_sessions = dbm.engine, dbm.SessionLocal
    try:
        dbm.Base.metadata.create_all(engine)
        # Copy synthetic identity seeds only. No production connection or backup.
        names = {t.name for t in dbm.Base.metadata.tables.values() if t.name.startswith("auth_")}
        names |= {"employee_profiles", "iam_org_units", "iam_org_departments", "system_notifications"}
        with original_engine.connect() as source, engine.begin() as target:
            for table in dbm.Base.metadata.sorted_tables:
                if table.name in names:
                    rows = [dict(r) for r in source.execute(table.select()).mappings()]
                    if rows:
                        target.execute(table.insert(), rows)
            # Explicitly copied audit IDs do not advance PostgreSQL's sequence.
            target.execute(text("SELECT setval(pg_get_serial_sequence('auth_audit_logs', 'id'), "
                "greatest(coalesce((SELECT max(id) FROM auth_audit_logs), 0), 1), EXISTS(SELECT 1 FROM auth_audit_logs))"))
        dbm.engine = engine
        dbm.SessionLocal = sessionmaker(engine, autoflush=False, expire_on_commit=False)
        yield client, dbm
    finally:
        dbm.engine, dbm.SessionLocal = original_engine, original_sessions
        engine.dispose()
        assert schema.startswith("iam_qa_") and len(schema) == 39
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def parallel_commit(dbm, jobs):
    changes = importlib.import_module("app.services.identity_changes")
    schemas = importlib.import_module("app.schemas.identity")
    barrier = Barrier(len(jobs))
    def run(job):
        actor, row, plan = job
        with dbm.SessionLocal() as db:
            barrier.wait(timeout=15)
            try:
                result = changes.commit_change(db, actor, row["id"], schemas.IdentityCommit(
                    preview_token=plan["preview_token"], expected_request_revision=row["revision"], confirm_high_risk=True), uuid4().hex)
                return 200, result
            except HTTPException as error:
                db.rollback()
                return error.status_code, error.detail
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(run, jobs))


def test_two_managers_transfer_one_user_serialized(postgres):
    client, dbm = postgres
    user_id = engineer(client)
    source = identity(client, user_id)["primary_assignment"]["id"]
    rows = [draft(client, user_id, "primary_assignment_transfer", source_assignment_id=source,
                  new_assignment={"org_unit_id": f, "department_code": "engineering", "official_position_title": "工程师"})
            for f in ("huakang-b", "huaxing")]
    other = create_user("transfer-admin", "admin", "*", "*")
    changes = importlib.import_module("app.services.identity_changes")
    jobs = []
    for actor, row in zip(("user-admin", other), rows):
        with dbm.SessionLocal() as db:
            jobs.append((actor, row, changes.preview_change(db, actor, row["id"])))
    results = parallel_commit(dbm, jobs)
    assert sorted(status for status, _ in results) == [200, 409], results
    current = identity(client, user_id)
    assert len([a for a in current["active_assignments_summary"] if a["is_primary"]]) == 1


def test_last_two_administrators_cannot_both_freeze(postgres):
    client, dbm = postgres
    second = create_user("second-admin", "admin", "*", "*")
    rows = [draft(client, user, "freeze") for user in ("user-admin", second)]
    changes = importlib.import_module("app.services.identity_changes")
    jobs = []
    for actor, row in zip(("user-admin", second), rows):
        with dbm.SessionLocal() as db:
            jobs.append((actor, row, changes.preview_change(db, actor, row["id"])))
    results = parallel_commit(dbm, jobs)
    assert sum(status == 200 for status, _ in results) == 1, results
    models = importlib.import_module("app.models.auth")
    auth = importlib.import_module("app.services.auth")
    with dbm.SessionLocal() as db:
        assert any(auth.can(auth.build_auth_context(db, db.get(models.AuthUser, u)), "system:user_manage", "*", "*") for u in ("user-admin", second))


def test_lock_refreshes_cached_actor_and_rejects_revoked_authority(postgres):
    client, dbm = postgres
    target = engineer(client)
    row = draft(client, target, "freeze")
    plan = preview(client, row)
    models = importlib.import_module("app.models.auth")
    schemas = importlib.import_module("app.schemas.identity")
    changes = importlib.import_module("app.services.identity_changes")
    policy = importlib.import_module("app.services.identity_policy")
    with dbm.SessionLocal() as stale, dbm.SessionLocal() as writer:
        old_actor = stale.get(models.AuthUser, "user-admin")
        assert old_actor.status == "active"
        policy.lock_mutation(writer)
        writer.get(models.AuthUser, "user-admin").status = "suspended"
        writer.commit()
        with pytest.raises(HTTPException) as failure:
            changes.commit_change(stale, "user-admin", row["id"], schemas.IdentityCommit(
                preview_token=plan["preview_token"], expected_request_revision=row["revision"], confirm_high_risk=True), uuid4().hex)
        assert failure.value.status_code == 401
        stale.rollback()
        assert stale.get(models.AuthUser, target).status == "active"


def test_legacy_confirmation_racing_access_edit_and_registration_preserves_latest_facts(postgres, monkeypatch):
    from concurrent.futures import TimeoutError
    from threading import Event
    from test_identity_changes import commit
    client, dbm = postgres
    user_id = create_user("migration-race", "engineer", "huakang-a", "engineering")
    current = identity(client, user_id)
    row = draft(client, user_id, "confirm_identity", new_assignment={"org_unit_id": "huakang-a",
        "department_code": "engineering", "official_position_title": current["position"]},
        binding_dispositions=[{"binding_id": b["id"], "source": "assignment"} for b in current["role_bindings"]])
    plan = preview(client, row)
    edit = client.post(f"/api/iam/users/{user_id}/access/preview", json={
        "base_revision": current["authorization_version"], "reason": "迁移预检后新增禁止开单",
        "overrides": [{"permission_code": "molding_sample:create", "effect": "deny",
                       "factory_id": "huakang-a", "department": "engineering"}]})
    assert edit.status_code == 200, edit.text
    iam = importlib.import_module("app.services.iam")
    changes = importlib.import_module("app.services.identity_changes")
    written, release, migration_started = Event(), Event(), Event()
    original_increment, original_lock = iam._increment_revision, changes.lock_mutation

    def hold_edit(db, target):
        result = original_increment(db, target)
        written.set()
        assert release.wait(15)
        return result

    def enter_migration(db):
        migration_started.set()
        original_lock(db)

    monkeypatch.setattr(iam, "_increment_revision", hold_edit)
    monkeypatch.setattr(changes, "lock_mutation", enter_migration)
    with ThreadPoolExecutor(max_workers=3) as pool:
        editor = pool.submit(client.post, f"/api/iam/users/{user_id}/access/commit",
                             json={"preview_token": edit.json()["preview_token"], "confirm_high_risk": True})
        assert written.wait(15)
        migration = pool.submit(commit, client, row, plan)
        registration = pool.submit(client.post, "/api/auth/register", json={"username": "registered-during-migration",
            "display_name": "并发注册", "password": "Testing123!", "confirm_password": "Testing123!",
            "phone": "13800000001", "email": "", "factory_id": "huakang-b", "department": "engineering", "position": "工程师"})
        try:
            assert migration_started.wait(15)
            with pytest.raises(TimeoutError):
                migration.result(timeout=0.2)
        finally:
            release.set()
        assert editor.result(timeout=20).status_code == 200
        rejected = migration.result(timeout=20)
        assert rejected.status_code == 409, rejected.text
        registered = registration.result(timeout=20)
        assert registered.status_code == 200, registered.text
    assert identity(client, user_id)["identity_mode"] == "legacy"
    monkeypatch.setattr(iam, "_increment_revision", original_increment)
    monkeypatch.setattr(changes, "lock_mutation", original_lock)
    confirm(client, user_id)  # Fresh migration explicitly preserves the new deny.
    models = importlib.import_module("app.models.auth")
    auth = importlib.import_module("app.services.auth")
    from sqlalchemy import select
    with dbm.SessionLocal() as db:
        assert not auth.can(auth.build_auth_context(db, db.get(models.AuthUser, user_id)),
                            "molding_sample:create", "huakang-a", "engineering")
        applicant = db.scalar(select(models.AuthUser).where(models.AuthUser.username == "registered-during-migration"))
        assert applicant is not None and applicant.status == "pending"
        assert db.get(models.EmployeeProfile, applicant.id).primary_factory_id == "huakang-b"
