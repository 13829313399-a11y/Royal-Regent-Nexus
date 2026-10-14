"""Disposable databases only; end-to-end HTTP and real authorization assertions."""
import importlib
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from test_iam_api import make_client, login, create_user
from test_identity_changes import confirm, identity


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("IAM_IDENTITY_WRITES_ENABLED", "true")
    monkeypatch.setenv("IAM_IDENTITY_SCHEDULING_ENABLED", "false")
    monkeypatch.setenv("IAM_POSITION_WORKBENCH_ENABLED", "true")
    with make_client(monkeypatch) as result:
        login(result, "admin")
        yield result


def employee(client, username="position-clerk"):
    uid = create_user(username, "position_engineering_engineer", "huakang-a", "engineering")
    confirm(client, uid)
    login(client, username)
    return uid


def submit(client, title="工程主管"):
    response = client.post("/api/auth/me/position-reviews", json={"declaration": {
        "org_unit_id": "huakang-a", "department_code": "engineering", "position": title, "note": "岗位已调整"}})
    assert response.status_code == 200, response.text
    return response.json()["review"]


def plan(client, review, *, role="position_engineering_supervisor", keep=False):
    key = "position:" + review["id"]
    detail = client.get(f"/api/iam/position-workbench/items/{key}")
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    body = {"expected_source_revision": detail["source_revision"], "decision": "keep_permissions" if keep else "apply_package",
        "confirmed_profile": {k: v for k, v in review["declaration"].items() if k != "note"},
        "independent_allow_decisions": [{"override_id": o["override_id"], "decision": "keep_original_scope"} for o in detail["independent_allows"]]}
    if not keep:
        packages = client.get("/api/iam/position-workbench/packages", params={"item_key": key})
        assert packages.status_code == 200, packages.text
        selected = next(p for p in packages.json()["items"] if p["role_id"] == role)
        body["package_selection"] = {"role_id": role, "definition_hash": selected["definition_hash"],
            "factory_scope": {"kind": "home", "factory_ids": []}, "permission_department": selected["department"]}
    response = client.post(f"/api/iam/position-workbench/items/{key}/preview", json=body)
    assert response.status_code == 200, response.text
    return key, body, response.json()


def commit(client, key, preview, command=None, risk=True):
    body = {"expected_source_revision": preview["source_revision"], "preview_token": preview["preview_token"],
        "command_id": command or str(uuid4()), "risk_acknowledged": risk}
    return client.post(f"/api/iam/position-workbench/items/{key}/commit", json=body), body


def test_employee_to_admin_real_permission_flow_and_receipt(client):
    uid = employee(client)
    before = client.get("/api/auth/me").json()
    review = submit(client)
    duplicate = submit(client)
    assert duplicate["id"] == review["id"] and duplicate["revision"] == 1
    own = client.get("/api/auth/me/position-profile").json()
    assert own["official_position"]["position"] != "工程主管"
    unchanged = client.get("/api/auth/me").json()
    unchanged["identity"].pop("server_now")
    before["identity"].pop("server_now")
    assert unchanged == before
    login(client, "admin")
    queue = client.get("/api/iam/position-workbench/queue")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    old_identity = identity(client, uid)
    key, body, preview = plan(client, review)
    assert preview["high_risk"] and preview["permission_diffs"]["added"]
    assert identity(client, uid)["identity_version"] == old_identity["identity_version"]
    rejected, _ = commit(client, key, preview, risk=False)
    assert rejected.status_code == 422, rejected.text
    response, command = commit(client, key, preview)
    assert response.status_code == 200, response.text
    assert response.json()["source_status"] == "applied"
    again = client.post(f"/api/iam/position-workbench/items/{key}/commit", json=command)
    assert again.json() == response.json()
    receipt = client.get(f"/api/iam/position-workbench/receipts/{command['command_id']}")
    assert receipt.json()["result"] == response.json()
    assert identity(client, uid)["position"] == "工程主管"
    assert identity(client, uid)["primary_assignment"]["id"] == old_identity["primary_assignment"]["id"]
    dbm, auth, models = (importlib.import_module(m) for m in ("app.db", "app.services.auth", "app.models.auth"))
    with dbm.SessionLocal() as db:
        context = auth.build_auth_context(db, db.get(models.AuthUser, uid))
        assert auth.can(context, "molding_sample:supervisor_review", "huakang-a", "engineering")
    login(client, "position-clerk")
    assert client.get("/api/auth/me/position-profile").json()["official_position"]["position"] == "工程主管"
    assert client.get(f"/api/iam/position-workbench/receipts/{command['command_id']}").json()["status"] == "not_observed"


def test_strict_self_fields_idor_revisions_return_withdraw(client):
    uid = employee(client)
    declaration = {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "新岗位"}
    for field in ("user_id", "role_id", "approved", "authorization_version", "factory_scope", "identity_mode"):
        response = client.post("/api/auth/me/position-reviews", json={"declaration": {**declaration, field: "forged"}})
        assert response.status_code == 422, response.text
        assert "forged" not in response.text
    for bad in ("", " " * 5, "岗" * 129):
        assert client.post("/api/auth/me/position-reviews", json={"declaration": {**declaration, "position": bad}}).status_code == 422
    assert client.post("/api/auth/me/position-reviews", json={"declaration": {**declaration, "org_unit_id": "group"}}).status_code == 422
    review = submit(client)
    assert client.post("/api/auth/me/position-reviews", json={"declaration": declaration}).status_code == 409
    login(client, "admin")
    assert client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 1, "declaration": declaration}).status_code == 404
    key, _, preview = plan(client, review)
    login(client, "position-clerk")
    edit = client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 1, "declaration": declaration})
    assert edit.status_code == 200, edit.text
    assert edit.json()["review"]["created_at"] == review["created_at"]
    assert client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 1, "declaration": declaration}).status_code == 409
    login(client, "admin")
    assert commit(client, key, preview)[0].status_code == 409
    rejected = client.post(f"/api/iam/position-workbench/items/{key}/decision", json={"expected_source_revision": "position:2",
        "command_id": str(uuid4()), "action": "return_position", "reason": "请补充岗位名称"})
    assert rejected.status_code == 200, rejected.text
    login(client, "position-clerk")
    own = client.get("/api/auth/me/position-profile").json()
    assert own["open_review"]["status"] == "returned"
    edit = client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 3, "declaration": declaration})
    assert edit.status_code == 200 and edit.json()["review"]["status"] == "pending"
    assert edit.json()["review"]["review_comment"] == "请补充岗位名称"
    withdrawn = client.post(f"/api/auth/me/position-reviews/{review['id']}/withdraw", json={"expected_revision": 4})
    assert withdrawn.status_code == 200 and withdrawn.json()["review"]["status"] == "withdrawn"
    login(client, "admin")
    assert identity(client, uid)["identity_version"] == 1


def test_keep_pinned_version_independent_deny_and_no_implicit_upgrade(client):
    uid = employee(client)
    review = submit(client, "工程负责人")
    login(client, "admin")
    dbm, models = importlib.import_module("app.db"), importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == "molding_sample:supervisor_review"))
        db.add(models.AuthUserPermissionOverride(id="position-deny", user_id=uid, permission_id=permission.id,
            factory_id="huakang-a", department="engineering", effect="deny", status="active", employment_epoch=1))
        binding = db.scalar(select(models.AuthUserRole).where(models.AuthUserRole.user_id == uid))
        pinned = db.get(models.AuthRoleBindingMetadata, binding.id).role_version_id
        db.add(models.AuthRolePermission(id=uuid4().hex, role_id="position_engineering_engineer", permission_id=permission.id))
        db.commit()
    key, _, preview = plan(client, review, keep=True)
    assert not preview["permission_diffs"]["added"] and not preview["permission_diffs"]["removed"]
    assert preview["explicit_denials"]
    response, _ = commit(client, key, preview)
    assert response.status_code == 200, response.text
    with dbm.SessionLocal() as db:
        assert db.get(models.AuthRoleBindingMetadata, binding.id).role_version_id == pinned
        assert db.get(models.AuthUserPermissionOverride, "position-deny").status == "active"
    login(client, "position-clerk")
    assert client.post(f"/api/auth/me/position-reviews/{review['id']}/withdraw", json={"expected_revision": 2}).status_code == 409


def test_position_transaction_failure_rolls_back_every_domain(client, monkeypatch):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    key, _, preview = plan(client, review)
    before = identity(client, uid)
    service = importlib.import_module("app.services.position_workbench")
    def fail_receipt(*args):
        from fastapi import HTTPException
        raise HTTPException(409, {"code": "INJECTED", "message": "事务故障注入"})
    monkeypatch.setattr(service, "save_receipt_tx", fail_receipt)
    response, command = commit(client, key, preview)
    assert response.status_code == 409
    after = identity(client, uid)
    assert after["position"] == before["position"] and after["authorization_version"] == before["authorization_version"]
    assert client.get(f"/api/iam/position-workbench/items/{key}").json()["status"] == "pending"
    assert client.get(f"/api/iam/position-workbench/receipts/{command['command_id']}").json()["status"] == "not_observed"
    dbm = importlib.import_module("app.db")
    events = importlib.import_module("app.models.position_review")
    outbox = importlib.import_module("app.models.identity").IamOutbox
    with dbm.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(events.PositionReviewEvent)) == 1
        assert db.scalar(select(func.count()).select_from(outbox).where(outbox.kind == "position_review_applied")) == 0


def test_notification_dispatch_aggregation_unknown_kind_and_failure(client, monkeypatch):
    uid = employee(client)
    review = submit(client)
    new_declaration = {**review["declaration"], "position": "工程主管兼调度"}
    assert client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={"expected_revision": 1, "declaration": new_declaration}).status_code == 200
    dbm, out = importlib.import_module("app.db"), importlib.import_module("app.services.identity_outbox")
    models, iam = importlib.import_module("app.models.auth"), importlib.import_module("app.models.identity")
    with dbm.SessionLocal() as db:
        assert out.drain(db)["retry"] == 0
        notices = list(db.scalars(select(models.SystemNotification).where(models.SystemNotification.type == "position_review_submitted")))
        assert len(notices) == 1 and json_payload(notices[0])["revision"] == 2
        db.add(iam.IamOutbox(id="unknown-kind-test", aggregate_id="test", kind="unrecognized", payload_json="{}", created_at="2000-01-01T00:00:00Z"))
        db.commit()
        assert out.drain(db)["retry"] == 1
        assert db.get(iam.IamOutbox, "unknown-kind-test").last_error == "UNKNOWN_OUTBOX_KIND"
    login(client, "admin")
    review.update(declaration=new_declaration, revision=2)
    key, _, preview = plan(client, review)
    response, _ = commit(client, key, preview)
    assert response.status_code == 200, response.text
    delivery = importlib.import_module("app.services.position_review_notifications")
    monkeypatch.setattr(delivery, "deliver", lambda *args: (_ for _ in ()).throw(RuntimeError("injected")))
    with dbm.SessionLocal() as db:
        assert out.drain(db)["retry"] == 1
    assert identity(client, uid)["position"] == new_declaration["position"]


def json_payload(row):
    import json
    return json.loads(row.payload_json)


def test_admin_origin_reuse_employee_edit_and_writes_gate(client):
    uid = employee(client)
    login(client, "admin")
    body = {"target_user_id": uid, "proposed_profile": {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "工程主管"}, "reason": "管理员核对"}
    first = client.post("/api/iam/position-workbench/admin-adjustments", json=body)
    assert first.status_code == 200, first.text
    second = client.post("/api/iam/position-workbench/admin-adjustments", json=body)
    assert second.json()["reused"] and second.json()["item_key"] == first.json()["item_key"]
    row = first.json()["review"]
    login(client, "position-clerk")
    edit = client.patch(f"/api/auth/me/position-reviews/{row['id']}", json={"expected_revision": 1,
        "declaration": {**body["proposed_profile"], "position": "实际工程主管"}})
    assert edit.status_code == 200 and edit.json()["review"]["origin"] == "admin"
    settings = importlib.import_module("app.core.config").settings
    settings.iam_position_workbench_enabled = False
    own = client.get("/api/auth/me/position-profile")
    assert own.status_code == 200 and not own.json()["can_submit"]
    assert client.post(f"/api/auth/me/position-reviews/{row['id']}/withdraw", json={"expected_revision": 2}).status_code == 403
