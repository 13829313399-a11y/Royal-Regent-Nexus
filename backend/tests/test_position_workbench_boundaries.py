"""Scope, stale previews, independent connections and registration atomicity."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from test_position_reviews import client, employee, submit, plan, commit
from test_iam_api import login, create_user
from test_identity_changes import identity
from test_identity_postgres import postgres


def modules():
    return tuple(importlib.import_module(name) for name in ("app.db", "app.models.auth", "app.models.identity", "app.services.position_workbench"))


def test_changed_role_revision_or_declaration_invalidates_preview(client):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    key, _, preview = plan(client, review)
    dbm, models, _, _ = modules()
    with dbm.SessionLocal() as db:
        revision = db.get(models.AuthUserAuthorizationRevision, uid)
        revision.revision += 1
        db.commit()
    assert commit(client, key, preview)[0].json()["code"] == "AUTHORIZATION_CHANGED"
    key, _, preview = plan(client, review)
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == "molding_sample:create"))
        db.add(models.AuthRolePermission(id=uuid4().hex, role_id="position_engineering_supervisor", permission_id=permission.id))
        db.commit()
    assert commit(client, key, preview)[0].json()["code"] == "AUTHORIZATION_CHANGED"
    key, _, preview = plan(client, review)
    login(client, "position-clerk")
    assert client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 1,
        "declaration": {**review["declaration"], "note": "已更正"}}).status_code == 200
    login(client, "admin")
    assert commit(client, key, preview)[0].json()["code"] == "REVIEW_REVISION_CONFLICT"


def test_independent_future_allow_and_deny_preserved_and_scheduled_binding_blocks(client):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    dbm, models, _, _ = modules()
    with dbm.SessionLocal() as db:
        pid = db.scalar(select(models.AuthPermission.id).where(models.AuthPermission.code == "molding_sample:create"))
        db.add(models.AuthUserPermissionOverride(id="future-allow", user_id=uid, permission_id=pid, factory_id="huakang-b",
            department="engineering", effect="allow", status="active", employment_epoch=1, valid_from="2099-01-01T00:00:00Z"))
        db.add(models.AuthUserPermissionOverride(id="permanent-deny", user_id=uid, permission_id=pid, factory_id="huakang-a",
            department="engineering", effect="deny", status="active", employment_epoch=1))
        db.commit()
    key, body, preview = plan(client, review)
    assert body["independent_allow_decisions"] == [{"override_id": "future-allow", "decision": "keep_original_scope"}]
    missing = client.post(f"/api/iam/position-workbench/items/{key}/preview", json={**body, "independent_allow_decisions": []})
    assert missing.status_code == 422
    assert commit(client, key, preview)[0].status_code == 200
    with dbm.SessionLocal() as db:
        future = db.get(models.AuthUserPermissionOverride, "future-allow")
        assert future.valid_from == "2099-01-01T00:00:00Z" and future.status == "active"
        assert db.get(models.AuthUserPermissionOverride, "permanent-deny").status == "active"
        binding = db.scalar(select(models.AuthRoleBindingMetadata).join(models.AuthUserRole,
            models.AuthUserRole.id == models.AuthRoleBindingMetadata.user_role_id).where(models.AuthUserRole.user_id == uid,
                models.AuthRoleBindingMetadata.state == "active"))
        binding.valid_from = "2099-01-01T00:00:00Z"
        db.commit()
    login(client, "position-clerk")
    review = submit(client, "工程经理")
    login(client, "admin")
    key = "position:" + review["id"]
    body["expected_source_revision"] = "position:1"
    blocked = client.post(f"/api/iam/position-workbench/items/{key}/preview", json=body)
    assert blocked.json()["code"] == "SCHEDULED_SOURCE_REVIEW_REQUIRED"


def registration(client, name="position-applicant"):
    response = client.post("/api/auth/register", json={"username": name, "display_name": "隔离注册测试", "password": "Testing123!",
        "confirm_password": "Testing123!", "phone": "13800000001", "email": "", "factory_id": "huakang-a",
        "department": "engineering", "position": "工程师"})
    assert response.status_code == 200, response.text
    login(client, "admin")
    queue = client.get("/api/iam/position-workbench/queue").json()
    row = next(i for i in queue["items"] if i["user"]["username"] == name)
    selected = next(p for p in client.get("/api/iam/position-workbench/packages", params={"item_key": row["item_key"]}).json()["items"]
                    if p["role_id"] == "position_engineering_engineer")
    body = {"expected_source_revision": row["source_revision"], "decision": "apply_package",
        "independent_allow_decisions": [],
        "confirmed_profile": {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "确认工程师"},
        "registration_details_correction": {"display_name": "确认姓名", "phone": "13800000002", "email": ""},
        "package_selection": {"role_id": selected["role_id"], "definition_hash": selected["definition_hash"],
            "factory_scope": {"kind": "home", "factory_ids": []}, "permission_department": "engineering"}}
    preview = client.post(f"/api/iam/position-workbench/items/{row['item_key']}/preview", json=body)
    assert preview.status_code == 200, preview.text
    return row, preview.json()


def test_registration_single_transaction_and_original_declaration(client, monkeypatch):
    row, preview = registration(client)
    dbm, models, iam, service = modules()
    original = service.save_receipt_tx
    def broken(*args):
        raise HTTPException(409, {"code": "INJECTED", "message": "回执写入故障"})
    monkeypatch.setattr(service, "save_receipt_tx", broken)
    assert commit(client, row["item_key"], preview)[0].status_code == 409
    with dbm.SessionLocal() as db:
        assert db.get(models.AuthUser, row["user"]["id"]).status == "pending"
        assert db.scalar(select(func.count()).select_from(iam.EmployeeAssignment).where(iam.EmployeeAssignment.user_id == row["user"]["id"])) == 0
        assert db.get(models.AuthRegistrationRequest, row["item_key"].split(":", 1)[1]).status == "pending"
    monkeypatch.setattr(service, "save_receipt_tx", original)
    response, _ = commit(client, row["item_key"], preview)
    assert response.status_code == 200, response.text
    with dbm.SessionLocal() as db:
        applicant = db.get(models.AuthUser, row["user"]["id"])
        assert applicant.status == "active" and applicant.display_name == "确认姓名"
        source = db.get(models.AuthRegistrationRequest, row["item_key"].split(":", 1)[1])
        assert source.position == "确认工程师"
        assert json.loads(source.declared_profile_json)["position"] == "工程师"
    assert identity(client, row["user"]["id"])["identity_mode"] == "v2"


def test_scope_filters_before_total_and_no_recipient_diagnostic(client, monkeypatch):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    outsider = create_user("position-other-admin", "admin", "huakang-b", "engineering")
    login(client, "position-other-admin")
    queue = client.get("/api/iam/position-workbench/queue")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 0 and queue.json()["actionable_total"] == 0
    assert client.get(f"/api/iam/position-workbench/items/position:{review['id']}").status_code == 403
    login(client, "admin")
    delivery = importlib.import_module("app.services.position_review_notifications")
    monkeypatch.setattr(delivery, "recipients", lambda *args: [])
    dbm, _, _, _ = modules()
    with dbm.SessionLocal() as db:
        result = importlib.import_module("app.services.identity_outbox").drain(db)
        assert result["retry"] == 1
    queue = client.get("/api/iam/position-workbench/queue").json()
    assert queue["total"] == 1 and queue["routing_attention"]


def test_postgres_two_commits_and_replay_use_independent_connections(postgres):
    client, dbm = postgres
    employee(client)
    review = submit(client)
    login(client, "admin")
    key, _, preview = plan(client, review)
    service = importlib.import_module("app.services.position_workbench")
    schema = importlib.import_module("app.schemas.position_review")
    barrier = Barrier(2)
    def run(command):
        with dbm.SessionLocal() as db:
            barrier.wait(15)
            try:
                return 200, service.commit(db, "user-admin", key, schema.CommitInput(expected_source_revision=preview["source_revision"],
                    preview_token=preview["preview_token"], command_id=command, risk_acknowledged=True))
            except HTTPException as e:
                db.rollback()
                return e.status_code, e.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [str(uuid4()), str(uuid4())]))
    assert sorted(status for status, _ in results) == [200, 409], results
    result = next(value for status, value in results if status == 200)
    response, _ = commit(client, key, preview, command=result["command_id"])
    assert response.json() == result


def test_postgres_simultaneous_self_submission_has_one_open_review(postgres):
    client, dbm = postgres
    uid = employee(client)
    service = importlib.import_module("app.services.position_reviews")
    schema = importlib.import_module("app.schemas.position_review")
    barrier = Barrier(2)
    payload = schema.SubmitReview(declaration={"org_unit_id": "huakang-a", "department_code": "engineering", "position": "新岗位"})
    def run(_):
        with dbm.SessionLocal() as db:
            barrier.wait(15)
            return service.submit(db, uid, payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(run, range(2)))
    assert {r["review"]["id"] for r in rows}.__len__() == 1
    assert sorted(r["changed"] for r in rows) == [False, True]


def test_registration_history_uses_current_and_scheduled_person_scope(client):
    row, preview = registration(client)
    assert commit(client, row["item_key"], preview)[0].status_code == 200
    uid = row["user"]["id"]
    login(client, "position-applicant", "Testing123!")
    declaration = {"org_unit_id":"huakang-b","department_code":"engineering","position":"B厂工程师","note":""}
    submitted = client.post("/api/auth/me/position-reviews", json={"declaration":declaration})
    assert submitted.status_code == 200, submitted.text
    login(client, "admin")
    key, _, preview = plan(client, submitted.json()["review"], keep=True)
    assert commit(client, key, preview)[0].status_code == 200
    create_user("a-scope-reviewer", "admin", "huakang-a", "engineering")
    login(client, "a-scope-reviewer")
    assert client.get(f"/api/system/users/{uid}/identity").status_code == 403
    history = client.get("/api/iam/position-workbench/queue", params={"status":"history"})
    assert history.status_code == 200 and history.json()["total"] == 0, history.text
    assert client.get("/api/iam/position-workbench/items/" + row["item_key"]).status_code == 403


def test_rejected_applicant_resubmission_uses_new_declaration_not_unconfirmed_profile(client):
    row, _ = registration(client, name="resubmitted-applicant")
    result = client.post(f"/api/iam/position-workbench/items/{row['item_key']}/decision", json={
        "expected_source_revision": row["source_revision"], "command_id": str(uuid4()),
        "action": "reject_registration", "reason": "请重新核对所属厂区"})
    assert result.status_code == 200, result.text
    response = client.post("/api/auth/register", json={"username":"resubmitted-applicant", "display_name":"重新申请", "password":"Testing123!",
        "confirm_password":"Testing123!", "phone":"13800000001", "email":"", "factory_id":"huakang-b", "department":"engineering", "position":"工程师"})
    assert response.status_code == 200, response.text
    create_user("b-scope-reviewer", "admin", "huakang-b", "engineering")
    login(client, "b-scope-reviewer")
    queue = client.get("/api/iam/position-workbench/queue").json()
    assert queue["total"] == 1, queue
    detail = client.get("/api/iam/position-workbench/items/" + queue["items"][0]["item_key"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_official"] is None
    assert detail.json()["declaration"]["org_unit_id"] == "huakang-b"
