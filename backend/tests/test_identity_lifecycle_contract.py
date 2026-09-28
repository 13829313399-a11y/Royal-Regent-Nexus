import importlib
import json
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from test_identity_changes import client, engineer, identity, draft, preview, commit, confirm
from test_iam_api import create_user, login


def modules():
    return tuple(importlib.import_module("app." + name) for name in
                 ("db", "models.auth", "models.identity", "services.auth", "services.identity_resolver"))


def add_assignment(client, user_id, factory="huakang-b", department="sales-business", role="position_sales_supervisor", **kwargs):
    return draft(client, user_id, "add_assignment", new_assignment={"org_unit_id": factory, "department_code": department,
        "official_position_title": "测试兼任", "is_primary": False, "assignment_type": "part_time",
        "role_bindings": [{"role_id": role, "department": department}], **kwargs})


def test_registration_declaration_does_not_grant_and_group_approval(client):
    public = client.get("/api/auth/organization-catalog")
    assert public.status_code == 200
    assert "group" not in [o["id"] for o in public.json()["organizations"]]
    payload = {"username": "group-applicant", "display_name": "申请测试", "password": "TestPass123!", "confirm_password": "TestPass123!",
        "phone": "13800000000", "email": "", "factory_id": "", "org_unit_id": "group-management", "department": "management", "position": "超级管理员"}
    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 200, registered.text
    dbm, authm, _, auth, _ = modules()
    with dbm.SessionLocal() as db:
        user = db.scalar(select(authm.AuthUser).where(authm.AuthUser.username == payload["username"]))
        assert not auth.can(auth.build_auth_context(db, user), "system:user_manage", "*", "*")
        user_id = user.id
    request = next(r for r in client.get("/api/system/registration-requests").json() if r["username"] == payload["username"])
    response = client.post(f"/api/system/registration-requests/{request['id']}/approve", json={
        "system_position_role_id": "position_warehouse_manager", "review_comment": "核实集团总务任职",
        "profile": {"display_name": "集团测试", "phone": payload["phone"], "email": "", "factory_id": "", "org_unit_id": "group-management",
                    "department": "management", "position": "总务仓务协作", "business_factory_ids": ["huakang-a"]}})
    assert response.status_code == 200, response.text
    current = identity(client, user_id)
    assert current["primary_assignment"]["org_unit_id"] == "group-management" and current["primary_factory_id"] == ""
    people = client.get("/api/system/people?org_unit_id=group-management").json()["items"]
    assert next(p for p in people if p["id"] == user_id)["primary_org_unit_id"] == "group-management"
    with dbm.SessionLocal() as db:
        context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
        assert auth.can(context, "carton_procurement:read", "huakang-a", "pmc-warehouse")
        assert not auth.can(context, "carton_procurement:read", "huakang-b", "pmc-warehouse")
        assert not auth.can(context, "system:user_manage", "*", "*")
        saved = db.get(authm.AuthRegistrationRequest, request["id"])
        assert json.loads(saved.declared_profile_json)["position"] == "超级管理员"
    bad = client.post("/api/auth/register", json={**payload, "username": "contradictory", "factory_id": "huaxing"})
    assert bad.status_code == 422


def test_tuple_integrity_formal_sales_and_time_expiry_without_worker(client):
    user_id = engineer(client)
    dbm, authm, _, auth, clock = modules()
    expiry = clock.utc_now() + timedelta(days=1)
    row = add_assignment(client, user_id, valid_until=clock.stamp(expiry), assignment_type="temporary")
    assert commit(client, row).status_code == 200
    reviewer = importlib.import_module("app.services.internal_quote")
    with dbm.SessionLocal() as db:
        user = db.get(authm.AuthUser, user_id)
        before = auth.build_auth_context(db, user, at=expiry - timedelta(microseconds=1))
        after = auth.build_auth_context(db, user, at=expiry)
        assert reviewer._is_sales_quote_reviewer(before, "huakang-b")
        assert not reviewer._is_sales_quote_reviewer(before, "huakang-a")
        assert not reviewer._is_sales_quote_reviewer(after, "huakang-b")
        assert auth.can(before, "internal_quote:sales_review", "huakang-b", "sales-business", at=expiry - timedelta(microseconds=1))
        assert not auth.can(before, "internal_quote:sales_review", "huakang-a", "sales-business", at=expiry - timedelta(microseconds=1))
        assert not auth.can(after, "internal_quote:sales_review", "huakang-b", "sales-business", at=expiry)


def test_scheduled_transfer_runtime_directory_and_cancellation_conflict(client, monkeypatch):
    user_id = engineer(client)
    dbm, authm, _, auth, clock = modules()
    settings = importlib.import_module("app.core.config").settings
    monkeypatch.setattr(settings, "iam_identity_scheduling_enabled", True)
    boundary = clock.utc_now() + timedelta(days=2)
    row = draft(client, user_id, "primary_assignment_transfer", source_assignment_id=identity(client, user_id)["primary_assignment"]["id"],
        effective_at=clock.stamp(boundary), new_assignment={"org_unit_id": "huaxing", "department_code": "pmc-warehouse",
            "official_position_title": "仓管", "role_bindings": [{"role_id": "warehouse_keeper", "department": "pmc-warehouse"}]})
    applied = commit(client, row)
    assert applied.status_code == 200, applied.text
    with dbm.SessionLocal() as db:
        assert db.get(authm.EmployeeProfile, user_id).primary_factory_id == "huakang-a"  # stale projection intentionally retained
        for at, expected in [(boundary - timedelta(microseconds=1), "huakang-a"), (boundary, "huaxing"), (boundary + timedelta(seconds=1), "huaxing")]:
            context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id), at=at)
            assert context.profile.primary_factory_id == expected
            factory, department, title = clock.identity_columns(at)
            projected = db.execute(select(factory, department, title).where(authm.EmployeeProfile.user_id == user_id)).one()
            assert projected[0] == expected
    correction = draft(client, user_id, "profile_correction", official_position_title="已核实工程师")
    assert commit(client, correction).status_code == 200
    cancel = client.post(f"/api/iam/identity-changes/{row['id']}/cancel", json={"expected_request_revision": applied.json()["revision"], "reason": "撤回测试"})
    assert cancel.status_code == 409 and cancel.json()["detail"]["code"] == "SOURCE_CHANGED"
    changes = importlib.import_module("app.services.identity_changes")
    monkeypatch.setattr(changes, "utc_now", lambda: boundary + timedelta(seconds=1))
    with dbm.SessionLocal() as db:
        output = changes.result_out(db.get(authm.AuthAccessRequest, row["id"]))
        assert output["state"] == "applied" and output["handover_refresh_pending"]
    late_cancel = client.post(f"/api/iam/identity-changes/{row['id']}/cancel", json={"expected_request_revision": applied.json()["revision"], "reason": "生效后撤回"})
    assert late_cancel.status_code == 409 and late_cancel.json()["detail"]["code"] == "CHANGE_ALREADY_EFFECTIVE"
    assert len(identity(client, user_id)["assignments"]) == 2


def test_frozen_packages_inactive_permission_and_seed_replay(client):
    user_id = engineer(client)
    dbm, authm, identitym, auth, clock = modules()
    with dbm.SessionLocal() as db:
        target = db.get(authm.AuthUser, user_id)
        original = auth.build_auth_context(db, target)
        permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "system:user_manage"))
        db.add(authm.AuthRolePermission(id=uuid4().hex, role_id="engineer", permission_id=permission.id))
        db.commit()
        # Live role growth cannot widen a pinned assignment package.
        assert not auth.can(auth.build_auth_context(db, target), "system:user_manage", "huakang-a", "engineering")
        existing_code = next(p for p in original.grants[0].permissions if auth.can(original, p, "huakang-a", "engineering"))
        existing = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == existing_code))
        db.get(authm.AuthPermissionMetadata, existing.id).status = "inactive"
        db.commit()
        assert not auth.can(auth.build_auth_context(db, target), existing_code, "huakang-a", "engineering")
    upgrade = draft(client, user_id, "upgrade_packages", source_assignment_id=identity(client, user_id)["primary_assignment"]["id"])
    denied = client.post(f"/api/iam/identity-changes/{upgrade['id']}/preview")
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "ADMINISTRATION_SEPARATE"
    leave = draft(client, user_id, "leave")
    assert commit(client, leave).status_code == 200
    with dbm.SessionLocal() as db:
        auth.seed_iam_sidecars(db, auth.now_text())
        db.commit()
        context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
        assert not context.account_available and not context.grants


def test_permission_registry_or_actor_change_invalidates_preview(client):
    user_id = engineer(client)
    row = draft(client, user_id, "freeze")
    plan = preview(client, row)
    dbm, authm, _, _, _ = modules()
    with dbm.SessionLocal() as db:
        meta = db.scalars(select(authm.AuthPermissionMetadata)).first()
        meta.risk_level = "high"  # unrelated display risk does not silently grant anything
        meta.status = "inactive"
        db.commit()
    result = commit(client, row, plan)
    assert result.status_code == 409 and result.json()["detail"]["code"] == "AUTHORIZATION_CHANGED"


def test_batch_partial_failure_and_idempotent_retry(client):
    user_id = engineer(client)
    rows = [draft(client, user_id, "profile_correction", official_position_title=name) for name in ("第一次", "冲突项")]
    items = [{"change_id": r["id"], "idempotency_key": uuid4().hex,
              "commit": {"preview_token": preview(client, r)["preview_token"], "expected_request_revision": r["revision"], "confirm_high_risk": True}} for r in rows]
    for _ in range(2):
        result = client.post("/api/iam/identity-batches/commit", json={"items": items})
        assert result.status_code == 200
        assert [r["status"] for r in result.json()["items"]] == [200, 409]
    assert identity(client, user_id)["position"] == "第一次"


def test_local_manager_request_requires_delegation_and_no_count_leak(client):
    user_id = engineer(client)
    assert commit(client, add_assignment(client, user_id)).status_code == 200
    manager = create_user("local-manager", "engineer", "huakang-a", "engineering")
    dbm, authm, _, _, _ = modules()
    with dbm.SessionLocal() as db:
        for code in ("system:user_manage", "system:access_manage"):
            permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == code))
            db.add(authm.AuthUserPermissionOverride(id=uuid4().hex, user_id=manager, permission_id=permission.id,
                effect="allow", factory_id="huakang-a", department="engineering", status="active"))
        db.commit()
    login(client, "local-manager")
    people = client.get("/api/system/people")
    assert people.status_code == 200, people.text
    assert user_id not in {u["id"] for u in people.json()["items"]}
    assert client.get(f"/api/system/users/{user_id}/identity").status_code == 403
    own = draft(client, manager, "freeze")
    response = commit(client, own)
    assert response.status_code == 200 and response.json()["state"] == "pending_approval"
    plan = preview(client, response.json())
    approve = client.post(f"/api/iam/identity-changes/{own['id']}/approve", headers={"Idempotency-Key": uuid4().hex},
        json={"preview_token": plan["preview_token"], "expected_request_revision": response.json()["revision"], "confirm_high_risk": True})
    assert approve.status_code == 403
