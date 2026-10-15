"""End-to-end regressions for account and administrator lifecycle repairs."""
import importlib
import pytest
from uuid import uuid4
from sqlalchemy import select
from test_position_reviews import client, employee, submit, plan, commit
from test_identity_changes import identity, draft, preview, commit as identity_commit
from test_iam_api import login, create_user


def modules():
    return tuple(importlib.import_module(n) for n in ("app.db", "app.models.auth", "app.services.auth"))


def test_cross_factory_reapplication_can_be_approved_by_new_factory_manager(client, monkeypatch):
    from test_system_user_management_api import register_payload, create_scoped_permission_manager
    monkeypatch.setattr(importlib.import_module("app.core.config").settings, "iam_identity_writes_enabled", False)
    payload = register_payload("reapplication-scope")
    payload["factory_id"] = "huakang-a"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200, response.text
    login(client, "admin")
    assert client.post(f"/api/system/registration-requests/{response.json()['request_id']}/reject",
        json={"review_comment": "请更正所属厂区"}).status_code == 200
    payload["factory_id"] = "huakang-b"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200, response.text
    create_scoped_permission_manager("new-factory-manager", "huakang-b", "engineering")
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        db.add(m.AuthRole(id="local-basic", code="local-basic", name="本厂基础查看"))
        db.flush()
        db.add(m.AuthRoleMetadata(role_id="local-basic", version=1, protected=0))
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "molding_sample:read"))
        db.add(m.AuthRolePermission(id=uuid4().hex, role_id="local-basic", permission_id=permission.id))
        db.commit()
    login(client, "new-factory-manager")
    approved = client.post(f"/api/system/registration-requests/{response.json()['request_id']}/approve", json={
        "role_assignments": [{"role_id": "local-basic", "factory_id": "huakang-b", "department": "engineering"}]})
    assert approved.status_code == 200, approved.text
    with dbm.SessionLocal() as db:
        profile = db.get(m.EmployeeProfile, approved.json()["user_id"])
        assert profile.primary_org_unit_id == profile.primary_factory_id == "huakang-b"


@pytest.mark.parametrize("adapter", ["legacy", "enrolled-access", "builtin", "functional"])
def test_registration_checks_proposed_package_business_scope_and_rolls_back(client, monkeypatch, adapter):
    from test_system_user_management_api import register_payload
    settings = importlib.import_module("app.core.config").settings
    if adapter == "legacy":
        monkeypatch.setattr(settings, "iam_identity_writes_enabled", False)
    payload = register_payload("destination-scope")
    payload["factory_id"] = "huakang-a"
    if adapter == "functional":
        payload.update(org_unit_id="group-management", factory_id="", department="management")
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200, response.text
    rid = response.json()["request_id"]
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        uid = db.get(m.AuthRegistrationRequest, rid).user_id
        code = "system:access_manage" if adapter == "enrolled-access" else "system:user_manage"
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == code))
        db.add(m.AuthUserPermissionOverride(id=uuid4().hex, user_id="user-admin", permission_id=permission.id,
            effect="deny", factory_id="huakang-b", department="pmc-warehouse", status="active"))
        if adapter == "builtin":
            db.get(m.AuthRoleMetadata, "position_warehouse_keeper").scope_mode = "cross_factory_operate"
        db.commit()
    login(client, "admin")
    if adapter in {"builtin", "functional"}:
        spec = {k: payload[k] for k in ("display_name", "phone", "email", "factory_id", "department", "position")}
        if adapter == "functional":
            spec.update(org_unit_id="group-management", business_factory_ids=["huakang-b"])
        approval = {"system_position_role_id": "position_warehouse_keeper", "profile": spec}
    else:
        approval = {"role_assignments": [{"role_id": "warehouse_keeper", "factory_id": "huakang-b", "department": "pmc-warehouse"}]}
    response = client.post(f"/api/system/registration-requests/{rid}/approve", json=approval)
    assert response.status_code == 403, response.text
    with dbm.SessionLocal() as db:
        assert db.get(m.AuthUser, uid).status == "pending"
        assert db.get(m.AuthRegistrationRequest, rid).status == "pending"
        assert list(db.scalars(select(m.AuthUserRole).where(m.AuthUserRole.user_id == uid))) == []


def test_admin_resumes_returned_declaration_without_employee_resubmission(client):
    uid = employee(client)
    row = submit(client)
    login(client, "admin")
    key = "position:" + row["id"]
    response = client.post(f"/api/iam/position-workbench/items/{key}/decision", json={
        "expected_source_revision": "position:1", "command_id": str(uuid4()), "action": "return_position", "reason": "核实岗位"})
    assert response.status_code == 200, response.text
    response = client.post("/api/iam/position-workbench/admin-adjustments", json={"target_user_id": uid,
        "proposed_profile": {k: v for k, v in row["declaration"].items() if k != "note"}, "reason": "管理员已核实"})
    assert response.status_code == 200, response.text
    resumed = response.json()
    assert resumed["reused"] and resumed["review"]["id"] == row["id"]
    assert resumed["review"]["status"] == "pending" and resumed["review"]["revision"] == 3
    key, _, impact = plan(client, resumed["review"], keep=True)
    assert commit(client, key, impact)[0].status_code == 200
    assert identity(client, uid)["position"] == row["declaration"]["position"]


def test_business_scope_denial_requires_independent_approval_and_notifies_reviewer(client):
    uid = employee(client)
    login(client, "admin")
    create_user("second-admin", "admin", "*", "*")
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        for code in ("system:user_manage", "system:access_manage"):
            p = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == code))
            db.add(m.AuthUserPermissionOverride(id=uuid4().hex, user_id="user-admin", permission_id=p.id,
                effect="deny", factory_id="huakang-b", department="pmc-warehouse", status="active"))
        db.commit()
    row = draft(client, uid, "add_assignment", new_assignment={"org_unit_id": "huakang-a", "department_code": "engineering",
        "official_position_title": "兼任仓库", "is_primary": False, "assignment_type": "part_time",
        "role_bindings": [{"role_id": "warehouse_keeper", "department": "pmc-warehouse",
            "factory_scope": {"kind": "selected", "factory_ids": ["huakang-b"]}}]})
    impact = preview(client, row)
    assert impact["requires_approval"] is True
    response = identity_commit(client, row, impact)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "pending_approval"
    assert not any(a["department_code"] == "pmc-warehouse" for a in identity(client, uid)["active_assignments_summary"])
    # A denied destination must not leak through either historical API.
    assert client.get(f"/api/iam/identity-changes/{row['id']}").status_code == 403
    assert row["id"] not in {r["id"] for r in client.get("/api/iam/identity-changes").json()["items"]}
    with dbm.SessionLocal() as db:
        importlib.import_module("app.services.identity_outbox").drain(db)
        notifications = list(db.scalars(select(m.SystemNotification).where(m.SystemNotification.type == "identity_change_submitted")))
        assert [n.target_user_id for n in notifications] == ["user-second-admin"]
        notification_id = notifications[0].id
    login(client, "second-admin")
    snapshot = client.get("/api/work-center/snapshot")
    assert snapshot.status_code == 200, snapshot.text
    task = next(t for t in snapshot.json()["items"] if t["title"] == "审核职位与权限调整")
    assert task["can_act_now"] is True
    assert task["actions"][0]["target"]["route_key"] == "identity_approval"
    assert task["actions"][0]["target"]["params"]["id"] == row["id"]
    pending = client.get(f"/api/iam/identity-changes/{row['id']}").json()
    impact = preview(client, pending)
    assert impact["requires_approval"] is False
    approved = client.post(f"/api/iam/identity-changes/{row['id']}/approve", headers={"Idempotency-Key": uuid4().hex}, json={
        "preview_token": impact["preview_token"], "expected_request_revision": pending["revision"], "confirm_high_risk": True})
    assert approved.status_code == 200, approved.text
    with dbm.SessionLocal() as db:
        assert db.get(m.SystemNotification, notification_id).status == "handled"
    assert task["id"] not in {t["id"] for t in client.get("/api/work-center/snapshot").json()["items"]}
    assert task["id"] in {t["id"] for t in client.get("/api/work-center/snapshot?view=history").json()["items"]}


def test_upgrade_preserves_revoked_role_history_and_rejects_ended_assignment(client):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    key, _, impact = plan(client, review)
    assert commit(client, key, impact)[0].status_code == 200
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        old = db.scalar(select(m.AuthRoleBindingMetadata).join(m.AuthUserRole, m.AuthUserRole.id == m.AuthRoleBindingMetadata.user_role_id)
            .where(m.AuthUserRole.user_id == uid, m.AuthRoleBindingMetadata.state == "revoked"))
        old_id, before = old.user_role_id, (old.role_version_id, old.version)
        p = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "three_d_printing:read"))
        db.add(m.AuthRolePermission(id=uuid4().hex, role_id="position_engineering_engineer", permission_id=p.id))
        db.commit()
    assignment = identity(client, uid)["primary_assignment"]["id"]
    assert identity_commit(client, draft(client, uid, "upgrade_packages", source_assignment_id=assignment)).status_code == 200
    with dbm.SessionLocal() as db:
        old = db.get(m.AuthRoleBindingMetadata, old_id)
        assert (old.role_version_id, old.version) == before
    assert identity_commit(client, draft(client, uid, "end_assignment", source_assignment_id=assignment)).status_code == 200
    ended = draft(client, uid, "upgrade_packages", source_assignment_id=assignment)
    assert client.post(f"/api/iam/identity-changes/{ended['id']}/preview").status_code == 409


def test_admin_direct_transfer_combines_custom_and_builtin_packages(client):
    uid = employee(client)
    login(client, "admin")
    dbm, m, auth = modules()
    with dbm.SessionLocal() as db:
        db.add(m.AuthRole(id="extra-print", code="extra-print", name="附加打印读取"))
        db.flush()
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "three_d_printing:read"))
        db.add(m.AuthRolePermission(id=uuid4().hex, role_id="extra-print", permission_id=permission.id))
        db.commit()
    current = identity(client, uid)
    row = draft(client, uid, "primary_assignment_transfer", source_assignment_id=current["primary_assignment"]["id"],
        new_assignment={"org_unit_id": "huakang-a", "department_code": "engineering", "official_position_title": "主管兼打印核对",
            "role_bindings": [{"role_id": r, "department": "engineering"} for r in ("position_engineering_supervisor", "extra-print")]})
    assert identity_commit(client, row).status_code == 200
    assert identity(client, uid)["position"] == "主管兼打印核对"
    with dbm.SessionLocal() as db:
        context = auth.build_auth_context(db, db.get(m.AuthUser, uid))
        assert auth.can(context, "molding_sample:supervisor_review", "huakang-a", "engineering")
        assert auth.can(context, "three_d_printing:read", "huakang-a", "engineering")
        review_model = importlib.import_module("app.models.position_review").PositionReview
        assert db.scalar(select(review_model).where(review_model.user_id == uid)) is None


def test_legacy_functional_organization_is_preserved_in_detail_and_filter(client):
    uid = create_user("legacy-functional", "engineer", "huakang-a", "engineering")
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        profile = db.get(m.EmployeeProfile, uid)
        profile.primary_org_unit_id = "group-management"
        profile.primary_factory_id = ""
        profile.primary_department = "management"
        db.commit()
    assert identity(client, uid)["primary_org_unit_id"] == "group-management"
    response = client.get("/api/system/people", params={"org_unit_id": "group-management"})
    assert uid in {p["id"] for p in response.json()["items"]}


def test_old_registration_paths_and_notifications_use_complete_scope(client):
    from test_system_user_management_api import create_scoped_permission_manager, register_payload
    create_scoped_permission_manager("scope-reviewer", "huaxing", "engineering")
    response = client.post("/api/auth/register", json=register_payload("scope-applicant"))
    assert response.status_code == 200, response.text
    rid = response.json()["request_id"]
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        request = db.get(m.AuthRegistrationRequest, rid)
        db.add(m.AuthUserRole(id=uuid4().hex, user_id=request.user_id, role_id="engineer", factory_id="huadeng", department="engineering"))
        db.commit()
    login(client, "scope-reviewer")
    assert rid not in {r["id"] for r in client.get("/api/system/registration-requests").json()}
    assert client.post(f"/api/system/registration-requests/{rid}/reject", json={"review_comment": "不能越权"}).status_code == 403
    assert client.post(f"/api/system/registration-requests/{rid}/approve", json={"role_assignments": [{"role_id": "engineer", "factory_id": "huaxing", "department": "engineering"}]}).status_code == 403
    notices = client.get("/api/system/notifications").json()
    assert all(n["payload"].get("registration_request_id") != rid for n in notices)
    tasks = client.get("/api/work-center/snapshot").json()
    assert all(t["actions"][0]["target"]["params"]["id"] != rid for t in tasks["items"])


def test_password_review_and_account_stop_honor_concrete_denies_on_wildcard_sources(client):
    uid = create_user("wide-source", "engineer", "*", "engineering")
    local_uid = create_user("local-with-wide-request", "engineer", "huakang-a", "engineering")
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(m.AuthPermission).where(m.AuthPermission.code == "system:user_manage"))
        db.add(m.AuthUserPermissionOverride(id=uuid4().hex, user_id="user-admin", permission_id=permission.id,
            effect="deny", factory_id="huakang-b", department="engineering", status="active"))
        db.add(m.AuthPasswordResetRequest(id="denied-reset", user_id=uid, username="wide-source", factory_id="huakang-a",
            department="engineering", status="pending", claim_token_hash="a" * 64))
        db.add(m.AuthPasswordResetRequest(id="wide-request", user_id=local_uid, username="local-with-wide-request", factory_id="*",
            department="engineering", status="pending", claim_token_hash="c" * 64))
        db.add(m.AuthUser(id="no-profile", username="no-profile", display_name="待核实", status="active",
            password_salt="test-only", password_hash="test-only"))
        db.commit()
    login(client, "admin")
    assert client.patch(f"/api/system/users/{uid}/status", json={"status": "suspended"}).status_code == 403
    assert client.get(f"/api/system/users/{uid}/identity").status_code == 403
    assert client.get("/api/system/users/no-profile/identity").status_code == 403
    assert uid not in {p["id"] for p in client.get("/api/system/people").json()["items"]}
    assert all(r["id"] != "denied-reset" for r in client.get("/api/system/password-reset-requests").json())
    for action in ("approve", "reject", "reissue"):
        result = client.post(f"/api/system/password-reset-requests/denied-reset/{action}",
            json={"identity_verified": True, "review_comment": "禁止跨范围办理"})
        assert result.status_code == 403, result.text
    data = client.get("/api/work-center/snapshot").json()
    assert all(t["actions"][0]["target"]["params"]["id"] != "denied-reset" for t in data["items"])
    assert client.get("/api/iam/workspace/password-resets/wide-request").status_code == 403
    tasks = client.get("/api/iam/workspace/tasks", params={"kind": "password-reset"}).json()
    assert not {"denied-reset", "wide-request"} & {t["source_id"] for t in tasks["items"]}


def test_password_review_requires_original_request_scope_after_transfer(client):
    from test_system_user_management_api import create_scoped_permission_manager
    uid = create_user("transferred-reset", "engineer", "huakang-a", "engineering")
    create_scoped_permission_manager("local-reset-reviewer", "huakang-a", "engineering")
    dbm, m, _ = modules()
    with dbm.SessionLocal() as db:
        db.add(m.AuthPasswordResetRequest(id="old-scope-reset", user_id=uid, username="transferred-reset", factory_id="huadeng",
            department="engineering", status="pending", claim_token_hash="b" * 64))
        db.commit()
    login(client, "local-reset-reviewer")
    assert not client.get("/api/system/password-reset-requests").json()
    assert client.post("/api/system/password-reset-requests/old-scope-reset/approve",
        json={"identity_verified": True, "review_comment": "原申请超出范围"}).status_code == 403


def test_registration_history_remains_visible_with_only_a_scoped_part_time_assignment(client):
    from test_system_user_management_api import create_scoped_permission_manager
    uid = employee(client)
    login(client, "admin")
    primary = identity(client, uid)["primary_assignment"]["id"]
    row = draft(client, uid, "add_assignment", new_assignment={"org_unit_id": "huakang-a", "department_code": "engineering",
        "official_position_title": "兼任工程", "is_primary": False, "assignment_type": "part_time",
        "role_bindings": [{"role_id": "engineer", "department": "engineering"}]})
    assert identity_commit(client, row).status_code == 200
    assert identity_commit(client, draft(client, uid, "end_assignment", source_assignment_id=primary)).status_code == 200
    create_scoped_permission_manager("part-time-reviewer", "huakang-a", "engineering")
    dbm, m, auth = modules()
    with dbm.SessionLocal() as db:
        db.add(m.AuthRegistrationRequest(id="part-time-history", user_id=uid, username="position-clerk", display_name="兼任人员",
            factory_id="huakang-a", department="engineering", status="approved"))
        db.commit()
        actor = auth.build_auth_context(db, db.get(m.AuthUser, "user-part-time-reviewer"))
        reads = importlib.import_module("app.services.position_workbench_read")
        reads.ensure_item_scope(db, actor, db.get(m.AuthRegistrationRequest, "part-time-history"))
        assert "part-time-history" in reads.visible_registration_ids(db, actor)
