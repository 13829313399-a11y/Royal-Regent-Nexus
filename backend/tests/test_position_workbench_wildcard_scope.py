"""Concrete management denials must constrain every wildcard-source entrypoint."""
import importlib
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_iam_api import login
from test_position_reviews import client, employee, submit, plan, commit


@pytest.fixture(autouse=True)
def seed_disposable_accounts(monkeypatch):
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "true")


@pytest.mark.parametrize("permission_code,source_factory,source_department,denied_factory,denied_department", [
    ("system:user_manage", "*", "engineering", "huakang-b", "engineering"),
    ("system:access_manage", "*", "engineering", "huakang-b", "engineering"),
    ("system:access_manage", "huakang-b", "*", "huakang-b", "engineering"),
    ("system:access_manage", "*", "management", "group-management", "management"),
])
def test_wildcard_sources_respect_concrete_deny_at_queue_detail_and_writes(
        client, permission_code, source_factory, source_department, denied_factory, denied_department):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    key, body, preview = plan(client, review, keep=True)
    dbm, models, positions = (importlib.import_module(name) for name in
        ("app.db", "app.models.auth", "app.models.position_review"))
    with dbm.SessionLocal() as db:
        source_permission = db.scalar(select(models.AuthPermission).where(
            models.AuthPermission.code == "molding_sample:read"))
        manage_permission = db.scalar(select(models.AuthPermission).where(
            models.AuthPermission.code == permission_code))
        db.add(models.AuthUserPermissionOverride(id="wildcard-source", user_id=uid,
            permission_id=source_permission.id, factory_id=source_factory,
            department=source_department, effect="allow", status="active",
            lifecycle_policy="independent", employment_epoch=1))
        db.add(models.AuthUserPermissionOverride(id="concrete-manage-deny", user_id="user-admin",
            permission_id=manage_permission.id, factory_id=denied_factory,
            department=denied_department, effect="deny", status="active"))
        db.commit()
    login(client, "admin")
    queue = client.get("/api/iam/position-workbench/queue", params={"q": "position-clerk"})
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == queue.json()["actionable_total"] == 0
    workspace = client.get("/api/iam/workspace/tasks", params={"target_user_id": uid})
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["visible_total"] == 0
    attempts = [
        client.get(f"/api/iam/position-workbench/items/{key}"),
        client.get("/api/iam/position-workbench/packages", params={"item_key": key}),
        client.post(f"/api/iam/position-workbench/items/{key}/preview", json=body),
        commit(client, key, preview)[0],
        client.post(f"/api/iam/position-workbench/items/{key}/decision", json={
            "expected_source_revision": preview["source_revision"], "command_id": str(uuid4()),
            "action": "return_position", "reason": "不得越过具体厂区禁止项"}),
    ]
    for response in attempts:
        assert response.status_code == 403, response.text
    with dbm.SessionLocal() as db:
        row = db.get(positions.PositionReview, review["id"])
        assert row.status == "pending" and row.revision == 1
        assert db.get(models.EmployeeProfile, uid).identity_version == 1
        db.delete(db.get(models.AuthUserPermissionOverride, "concrete-manage-deny"))
        db.commit()
    login(client, "admin")
    assert client.get(f"/api/iam/position-workbench/items/{key}").status_code == 200
    assert client.get("/api/iam/position-workbench/queue").json()["total"] == 1


def test_provisional_registration_wildcard_source_hides_queue_and_detail(client):
    response = client.post("/api/auth/register", json={"username": "wildcard-applicant",
        "display_name": "隔离注册范围测试", "password": "Testing123!", "confirm_password": "Testing123!",
        "phone": "13800000001", "email": "", "factory_id": "huakang-a",
        "department": "engineering", "position": "工程师"})
    assert response.status_code == 200, response.text
    login(client, "admin")
    row = client.get("/api/iam/position-workbench/queue").json()["items"][0]
    uid, key = row["user"]["id"], row["item_key"]
    dbm, models = (importlib.import_module(name) for name in ("app.db", "app.models.auth"))
    with dbm.SessionLocal() as db:
        permissions = dict(db.execute(select(models.AuthPermission.code, models.AuthPermission.id)).all())
        db.add(models.AuthUserPermissionOverride(id="registration-wildcard-source", user_id=uid,
            permission_id=permissions["molding_sample:read"], factory_id="*", department="engineering",
            effect="allow", status="active"))
        db.add(models.AuthUserPermissionOverride(id="registration-concrete-deny", user_id="user-admin",
            permission_id=permissions["system:access_manage"], factory_id="huakang-b",
            department="engineering", effect="deny", status="active"))
        db.commit()
    login(client, "admin")
    data = client.get("/api/iam/workspace/tasks", params={"target_user_id": uid}).json()
    assert data["visible_total"] == data["actionable_total"] == 0
    assert client.get("/api/iam/position-workbench/queue").json()["total"] == 0
    assert client.get(f"/api/iam/position-workbench/items/{key}").status_code == 403
