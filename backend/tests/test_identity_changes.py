"""All HTTP tests create disposable SQLite databases before importing app."""
import importlib
from uuid import uuid4
import pytest
from test_iam_api import make_client, login, create_user


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("IAM_IDENTITY_WRITES_ENABLED", "true")
    monkeypatch.setenv("IAM_IDENTITY_SCHEDULING_ENABLED", "false")
    with make_client(monkeypatch) as result:
        login(result, "admin")
        yield result


def identity(client, user_id):
    response = client.get(f"/api/system/users/{user_id}/identity")
    assert response.status_code == 200, response.text
    return response.json()


def draft(client, user_id, kind, **kwargs):
    current = identity(client, user_id)
    payload = {"request_type": kind, "target_user_id": user_id, "reason": "隔离测试任职变更",
               "base_identity_version": current["identity_version"], "base_authorization_version": current["authorization_version"], **kwargs}
    response = client.post("/api/iam/identity-changes", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, row):
    response = client.post(f"/api/iam/identity-changes/{row['id']}/preview")
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, row, plan=None, key=None):
    plan = plan or preview(client, row)
    return client.post(f"/api/iam/identity-changes/{row['id']}/commit", headers={"Idempotency-Key": key or uuid4().hex},
                       json={"preview_token": plan["preview_token"], "expected_request_revision": row["revision"], "confirm_high_risk": True})


def confirm(client, user_id):
    current = identity(client, user_id)
    row = draft(client, user_id, "confirm_identity", new_assignment={"org_unit_id": current["primary_factory_id"],
        "department_code": current["primary_department"], "official_position_title": current["position"]},
        binding_dispositions=[{"binding_id": b["id"], "source": "assignment"} for b in current["role_bindings"] if b["state"] == "active"],
        exception_decisions=[{"override_id": o["id"], "decision": "keep_original_scope"} for o in current["overrides"]])
    response = commit(client, row)
    assert response.status_code == 200, response.text
    return identity(client, user_id)


def engineer(client):
    user_id = create_user("identity-engineer", "engineer", "huakang-a", "engineering")
    confirm(client, user_id)
    return user_id


def test_confirm_preview_is_read_only_transfer_and_idempotency(client):
    user_id = engineer(client)
    current = identity(client, user_id)
    row = draft(client, user_id, "primary_assignment_transfer", source_assignment_id=current["primary_assignment"]["id"],
        new_assignment={"org_unit_id": "huaxing", "department_code": "pmc-warehouse", "official_position_title": "仓管员",
                        "role_bindings": [{"role_id": "warehouse_keeper", "department": "pmc-warehouse"}]})
    plan = preview(client, row)
    assert identity(client, user_id)["primary_factory_id"] == "huakang-a"
    key = uuid4().hex
    first = commit(client, row, plan, key)
    assert first.status_code == 200, first.text
    assert first.json() == commit(client, row, plan, key).json()
    current = identity(client, user_id)
    assert current["primary_factory_id"] == "huaxing"
    assert current["primary_department"] == "pmc-warehouse"
    assert len(current["assignments"]) == 2
    assert current["assignments"][0]["state"] == "ended"
    stale = commit(client, row, plan)
    assert stale.status_code == 409
    mismatch = client.post(f"/api/iam/identity-changes/{row['id']}/commit", headers={"Idempotency-Key": key},
        json={"preview_token": plan["preview_token"], "expected_request_revision": row["revision"], "confirm_high_risk": False})
    assert mismatch.status_code == 409


def test_multiple_assignments_scope_ceiling_and_old_writer(client):
    user_id = engineer(client)
    row = draft(client, user_id, "add_assignment", new_assignment={"org_unit_id": "huakang-b", "department_code": "pmc-warehouse",
        "official_position_title": "兼任仓库经理", "is_primary": False, "assignment_type": "part_time",
        "role_bindings": [{"role_id": "position_warehouse_manager", "department": "pmc-warehouse",
                           "factory_scope": {"kind": "selected", "factory_ids": ["huakang-b"]}}]})
    response = commit(client, row)
    assert response.status_code == 200, response.text
    current = identity(client, user_id)
    end = draft(client, user_id, "end_assignment", source_assignment_id=current["primary_assignment"]["id"])
    assert commit(client, end).status_code == 200
    remaining = identity(client, user_id)
    assert remaining["primary_assignment"] is None
    assert len(remaining["active_assignments_summary"]) == 1
    dbm = importlib.import_module("app.db")
    auth = importlib.import_module("app.services.auth")
    models = importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        ctx = auth.build_auth_context(db, db.get(models.AuthUser, user_id))
        assert auth.can(ctx, "carton_procurement:read", "huakang-b", "pmc-warehouse")
        assert not auth.can(ctx, "carton_procurement:read", "huakang-a", "pmc-warehouse")
    old = client.post(f"/api/iam/users/{user_id}/system-position/preview", json={"base_revision": remaining["authorization_version"], "system_position_role_id": "position_warehouse_manager", "reason": "旧入口"})
    assert old.status_code == 409, old.text


def test_freeze_revoke_sessions_leave_and_rehire_epoch(client):
    user_id = engineer(client)
    login(client, "identity-engineer")
    saved_cookie = client.cookies.get("rr_session")
    login(client, "admin")
    freeze = draft(client, user_id, "freeze")
    assert commit(client, freeze).status_code == 200
    restore = draft(client, user_id, "unfreeze")
    assert commit(client, restore).status_code == 200
    admin_cookie = client.cookies.get("rr_session")
    client.cookies.clear()
    client.cookies.set("rr_session", saved_cookie)
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    client.cookies.set("rr_session", admin_cookie)
    leave = draft(client, user_id, "leave")
    assert commit(client, leave).status_code == 200
    left = identity(client, user_id)
    assert left["employment_status"] == "left"
    old_status = client.patch(f"/api/system/users/{user_id}/status", json={"status": "active"})
    assert old_status.status_code == 409, old_status.text
    rehire = draft(client, user_id, "rehire", new_assignment={"org_unit_id": "huakang-b", "department_code": "engineering", "official_position_title": "工程师"})
    response = commit(client, rehire)
    assert response.status_code == 200, response.text
    assert identity(client, user_id)["employment_epoch"] > left["employment_epoch"]


def test_profile_correction_and_atomic_failure(client, monkeypatch):
    user_id = engineer(client)
    before = identity(client, user_id)
    row = draft(client, user_id, "profile_correction", official_position_title="正式工程师")
    plan = preview(client, row)
    assert not plan["permission_diffs"]["added"] and not plan["permission_diffs"]["removed"]
    service = importlib.import_module("app.services.identity_changes")
    def fail_after_write(db):
        from fastapi import HTTPException
        raise HTTPException(409, "injected rollback")
    monkeypatch.setattr(service, "ensure_admin_survives", fail_after_write)
    assert commit(client, row, plan).status_code == 409
    after = identity(client, user_id)
    assert after["identity_version"] == before["identity_version"]
    assert after["position"] == before["position"]


def test_future_lifecycle_and_naive_time_rejected(client):
    user_id = engineer(client)
    row = draft(client, user_id, "freeze", effective_at="2099-01-01T00:00:00+08:00")
    response = client.post(f"/api/iam/identity-changes/{row['id']}/preview")
    assert response.status_code == 422
    data = row["payload"]
    data["effective_at"] = "2099-01-01T00:00:00"
    assert client.post("/api/iam/identity-changes", json=data).status_code == 422
