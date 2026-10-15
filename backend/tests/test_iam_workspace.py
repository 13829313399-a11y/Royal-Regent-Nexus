"""Consolidated projection: disposable database, real HTTP, scope and read-only assertions."""
import importlib
import json
import pytest
from datetime import datetime, timedelta
from sqlalchemy import event, select
from test_position_reviews import client, employee, submit
from test_iam_api import login, create_user


@pytest.fixture(autouse=True)
def seed_disposable_workspace(monkeypatch):
    # The shared fixture supplies a fresh database URL; do not inherit daily .env seeding policy.
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "true")


def modules():
    return tuple(importlib.import_module(name) for name in ("app.db", "app.models.auth", "app.models.position_review", "app.services.iam_workspace"))


def seed_sources(uid, n=12):
    dbm, m, p, _ = modules()
    declaration = json.dumps({"org_unit_id": "huakang-a", "department_code": "engineering", "position": "汇总测试", "note": ""})
    now = "2026-10-13 08:00:00"
    with dbm.SessionLocal() as db:
        for i in range(n):
            key = f"mixed-{i:03}"
            db.add(p.PositionReview(id=key, user_id=uid, employment_epoch=1, origin="employee", initiator_user_id=uid,
                status="returned" if i == 0 else "applied", declared_snapshot_json=declaration, created_at=now, updated_at=now, last_submitted_at=now))
            db.add(m.AuthRegistrationRequest(id=key, user_id=uid, username="workspace", display_name="汇总测试", org_unit_id="huakang-a",
                factory_id="huakang-a", department="engineering", position="工程师", status="approved", created_at=now))
            db.add(m.AuthPasswordResetRequest(id=key, user_id=uid, username="workspace", factory_id="huakang-a", department="engineering",
                status="approved", claim_token_hash="synthetic-" + key, expires_at=(datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                submitted_at=now, created_at=now, updated_at=now))
            db.add(m.AuthAccessRequest(id=key, target_user_id=uid, requester_user_id="user-admin", request_type="identity:profile_correction",
                lifecycle_state="draft", payload_json=json.dumps({"target_user_id": uid, "official_position_title": "工程师"}), created_at=now))
        db.commit()


def test_four_sources_stable_sql_pages_and_exact_filtered_counts(client):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid)
    seen = []
    for page in range(1, 8):
        response = client.get("/api/iam/workspace/tasks", params={"state": "", "page_size": 7, "page": page, "target_user_id": uid, "to_at": "2026-10-13T23:59:59+08:00"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["partial"] is False, data
        assert data["visible_total"] == 48
        assert data["actionable_total"] == 24  # 12 resets, 12 drafts
        seen.extend(r["key"] for r in data["items"])
    expected = [f"{kind}:mixed-{i:03}" for i in range(12) for kind in sorted(("position", "registration", "password-reset", "identity-change"))]
    assert seen == expected
    for kind, count in (("registration", 0), ("password-reset", 12), ("position", 0)):
        data = client.get("/api/iam/workspace/tasks", params={"kind": kind, "state": "", "q": "position-clerk"}).json()
        assert data["visible_total"] == 12 and data["actionable_total"] == count
    none = client.get("/api/iam/workspace/tasks", params={"q": "never-matches"}).json()
    assert none["visible_total"] == none["actionable_total"] == 0


def test_reading_all_sources_and_expired_password_does_not_write(client):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    dbm, m, _, _ = modules()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            statements.append(statement)
    event.listen(dbm.engine, "before_cursor_execute", capture)
    try:
        data = client.get("/api/iam/workspace/tasks", params={"state": ""}).json()
        assert not data["partial"], data
        detail = client.get("/api/iam/workspace/password-resets/mixed-000")
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == "expired" and detail.json()["can_reopen"]
        assert not statements, statements
    finally:
        event.remove(dbm.engine, "before_cursor_execute", capture)
    with dbm.SessionLocal() as db:
        assert db.get(m.AuthPasswordResetRequest, "mixed-000").status == "approved"


def test_source_failure_is_partial_unknown_count_and_other_sources_survive(client, monkeypatch):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    _, _, _, service = modules()
    monkeypatch.setattr(service.Projection, "password", lambda self: (_ for _ in ()).throw(RuntimeError("synthetic")))
    data = client.get("/api/iam/workspace/tasks", params={"state": ""}).json()
    assert data["partial"] and data["visible_total"] is None and data["actionable_total"] is None
    assert len([r for r in data["items"] if r["source_id"] == "mixed-000"]) == 3
    assert next(s for s in data["coverage"] if s["kind"] == "password-reset")["state"] == "unavailable"
    # A failure in an unrequested source does not make a known source unknown.
    assert not client.get("/api/iam/workspace/tasks", params={"kind": "position"}).json()["partial"]


def test_specific_admin_deny_hides_complete_target_from_password_queue_and_detail(client):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    dbm, m, _, _ = modules()
    with dbm.SessionLocal() as db:
        code = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "molding_sample:create"))
        db.add(m.AuthUserPermissionOverride(id="future-allow", user_id=uid, permission_id=code.id, factory_id="huakang-b", department="engineering",
            effect="allow", status="active", lifecycle_policy="independent", employment_epoch=1, valid_from="2090-01-01T00:00:00Z"))
        management = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "system:user_manage"))
        db.add(m.AuthUserPermissionOverride(id="specific-deny", user_id="user-admin", permission_id=management.id, factory_id="huakang-b", department="engineering",
            effect="deny", status="active", lifecycle_policy="independent", employment_epoch=1))
        db.commit()
    data = client.get("/api/iam/workspace/tasks", params={"state": "", "target_user_id": uid}).json()
    assert not data["partial"] and data["visible_total"] == 0, data
    assert client.get("/api/iam/workspace/password-resets/mixed-000").status_code == 403


def test_access_only_does_not_query_people_or_sources(client, monkeypatch):
    create_user("access-only-workspace", "position_engineering_engineer", "huakang-a", "engineering")
    dbm, m, _, service = modules()
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "system:access_manage"))
        db.add(m.AuthUserPermissionOverride(id="access-only", user_id="user-access-only-workspace", permission_id=permission.id,
            effect="allow", status="active", factory_id="huakang-a", department="engineering"))
        db.commit()
    login(client, "access-only-workspace")
    for name in ("position", "password", "changes"):
        monkeypatch.setattr(service.Projection, name, lambda *args: (_ for _ in ()).throw(AssertionError("unauthorized source queried")))
    data = client.get("/api/iam/workspace/tasks").json()
    assert data["visible_total"] == 0 and not data["partial"]
    assert all(not s["readable"] for s in data["coverage"])


def test_password_invalid_expiry_and_returned_position_semantics(client):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    dbm, m, _, _ = modules()
    with dbm.SessionLocal() as db:
        db.get(m.AuthPasswordResetRequest, "mixed-000").expires_at = ""
        db.commit()
    data = client.get("/api/iam/workspace/tasks", params={"state": ""}).json()
    by_kind = {r["kind"]: r for r in data["items"] if r["source_id"] == "mixed-000"}
    assert by_kind["position"]["state"] == "waiting_employee"
    assert by_kind["password-reset"]["raw_status"] == "approved"
    assert by_kind["password-reset"]["state"] == "closed"
    detail = client.get("/api/iam/workspace/password-resets/mixed-000").json()
    assert detail["status"] == "expired" and not detail["can_reopen"]


def test_writes_disabled_password_has_no_actions_and_rejects_all_commands(client, monkeypatch):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    dbm, m, _, service = modules()
    with dbm.SessionLocal() as db:
        db.get(m.AuthPasswordResetRequest, "mixed-000").status = "pending"
        db.commit()
    monkeypatch.setattr(service.settings, "authz_writes_enabled", False)
    detail = client.get("/api/iam/workspace/password-resets/mixed-000").json()
    assert detail["available_actions"] == [] and not detail["can_reopen"]
    for action in ("approve", "reject", "reissue"):
        result = client.post(f"/api/system/password-reset-requests/mixed-000/{action}", json={"identity_verified": True, "review_comment": "隔离核验"})
        assert result.status_code == 403, result.text
    with dbm.SessionLocal() as db:
        assert db.get(m.AuthPasswordResetRequest, "mixed-000").status == "pending"


def test_scheduled_effect_is_derived_without_a_worker_or_writes(client, monkeypatch):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 2)
    dbm, m, _, service = modules()
    with dbm.SessionLocal() as db:
        for i, at in enumerate(("2099-01-01T00:00:00Z", "2000-01-01T00:00:00Z")):
            row = db.get(m.AuthAccessRequest, f"mixed-{i:03}")
            row.lifecycle_state = "scheduled"; row.effective_at = at
        db.commit()
    monkeypatch.setattr(service.settings, "iam_identity_scheduling_enabled", False)
    result = client.get("/api/iam/workspace/tasks", params={"kind": "identity-change", "state": ""}).json()
    rows = {r["source_id"]: r for r in result["items"]}
    assert rows["mixed-000"]["state"] == "scheduled"
    assert rows["mixed-001"]["state"] == "closed" and rows["mixed-001"]["raw_status"] == "scheduled"
    with dbm.SessionLocal() as db:
        assert db.get(m.AuthAccessRequest, "mixed-001").lifecycle_state == "scheduled"


def test_upgrade_and_expired_binding_destinations_are_read_scoped(client):
    uid = employee(client)
    login(client, "admin")
    dbm, m, _, service = modules()
    with dbm.SessionLocal() as db:
        binding = db.scalar(select(m.AuthUserRole).where(m.AuthUserRole.user_id == uid))
        meta = db.get(m.AuthRoleBindingMetadata, binding.id)
        source = meta.assignment_id
        meta.scope_ceiling_json = None
        db.get(m.AuthRoleMetadata, binding.role_id).scope_mode = "cross_factory_operate"
        db.add(m.AuthUserRole(id="expired-b", user_id=uid, role_id=binding.role_id, factory_id="huakang-b", department="engineering"))
        db.flush()
        db.add(m.AuthRoleBindingMetadata(user_role_id="expired-b", state="active", source_type="individual_exception", employment_epoch=1,
            valid_until="2000-01-01T00:00:00Z", scope_ceiling_json='["huakang-b"]', role_version_id=meta.role_version_id))
        for key, kind, payload in (("upgrade", "upgrade_packages", {"source_assignment_id": source}),
                                  ("confirmation", "confirm_identity", {"binding_dispositions": [{"binding_id": "expired-b", "source": "individual_exception"}]})):
            db.add(m.AuthAccessRequest(id=key, target_user_id=uid, requester_user_id="user-admin", request_type="identity:"+kind,
                lifecycle_state="pending_approval", payload_json=json.dumps({"target_user_id": uid, **payload}), created_at="2026-10-13 08:00:00"))
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "system:user_manage"))
        db.add(m.AuthUserPermissionOverride(id="deny-destination", user_id="user-admin", permission_id=permission.id, effect="deny", status="active",
            factory_id="huakang-b", department="engineering", lifecycle_policy="independent", employment_epoch=1))
        db.commit()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}: statements.append(statement)
    event.listen(dbm.engine, "before_cursor_execute", capture)
    try:
        data = client.get("/api/iam/workspace/tasks", params={"kind": "identity-change", "state": ""}).json()
        assert not data["partial"], data
        assert not {"upgrade", "confirmation"} & {r["source_id"] for r in data["items"]}
        for key in ("upgrade", "confirmation"):
            assert client.get("/api/iam/workspace/identity-changes/" + key).status_code == 403
        assert not statements, statements
    finally:
        event.remove(dbm.engine, "before_cursor_execute", capture)


def test_confirmation_checks_latest_definition_without_legacy_ceiling(client):
    uid = employee(client)
    login(client, "admin")
    dbm, m, _, _ = modules()
    with dbm.SessionLocal() as db:
        binding = db.scalar(select(m.AuthUserRole).where(m.AuthUserRole.user_id == uid))
        db.get(m.EmployeeProfile, uid).identity_mode = "legacy"
        db.get(m.AuthRoleBindingMetadata, binding.id).scope_ceiling_json = '["huakang-a"]'
        db.get(m.AuthRoleMetadata, binding.role_id).scope_mode = "cross_factory_operate"
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "system:user_manage"))
        db.add(m.AuthUserPermissionOverride(id="deny-future-cross", user_id="user-admin", permission_id=permission.id, effect="deny", status="active", factory_id="huakang-b", department="engineering"))
        db.add(m.AuthAccessRequest(id="confirmation-latest", target_user_id=uid, requester_user_id="user-admin", request_type="identity:confirm_identity", lifecycle_state="pending_approval", payload_json=json.dumps({"target_user_id": uid}), created_at="2026-10-13 08:00:00"))
        db.commit()
    result = client.get("/api/iam/workspace/tasks", params={"kind": "identity-change", "state": ""}).json()
    assert not result["partial"], result
    assert "confirmation-latest" not in {r["source_id"] for r in result["items"]}
    assert client.get("/api/iam/workspace/identity-changes/confirmation-latest").status_code == 403
