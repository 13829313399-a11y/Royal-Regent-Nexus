"""Remaining acceptance cases use synthetic accounts and a stopped IAM worker."""
import asyncio
import importlib
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from test_iam_api import create_user, login, make_client
from test_identity_changes import commit, confirm, draft, engineer, identity, preview
from test_identity_lifecycle_contract import add_assignment, modules


@pytest.fixture
def client(monkeypatch):
    for name, value in {
        "IAM_IDENTITY_WRITES_ENABLED": "true", "IAM_IDENTITY_SCHEDULING_ENABLED": "true",
        "UV_OPS_ENABLED": "false", "SPRAY_OPS_ENABLED": "false",
        "THREE_D_CONNECTOR_ENABLED": "false",
    }.items():
        monkeypatch.setenv(name, value)
    application = make_client(monkeypatch)

    async def stopped_worker():
        await asyncio.Event().wait()

    monkeypatch.setattr(importlib.import_module("app.services.identity_outbox"), "worker", stopped_worker)
    with application as result:
        login(result, "admin")
        yield result


def set_clock(monkeypatch, at):
    # Auth, SQL projections and change status must observe the same server time.
    monkeypatch.setattr(importlib.import_module("app.services.identity_resolver"), "utc_now", lambda: at)
    monkeypatch.setattr(importlib.import_module("app.services.identity_changes"), "utc_now", lambda: at)
    monkeypatch.setattr(importlib.import_module("app.services.directory"), "business_now", lambda: at)


def test_package_change_preserves_formal_department_and_assignment(client):
    user_id = engineer(client)
    before = identity(client, user_id)
    dbm, authm, _, auth, _ = modules()
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "molding_sample:create"))
        db.execute(delete(authm.AuthRolePermission).where(authm.AuthRolePermission.role_id == "engineer",
                                                        authm.AuthRolePermission.permission_id == permission.id))
        db.commit()
        assert auth.can(auth.build_auth_context(db, db.get(authm.AuthUser, user_id)),
                        "molding_sample:create", "huakang-a", "engineering")
    row = draft(client, user_id, "upgrade_packages", source_assignment_id=before["primary_assignment"]["id"])
    plan = preview(client, row)
    assert any(p["permission_code"] == "molding_sample:create" for p in plan["permission_diffs"]["removed"])
    assert commit(client, row, plan).status_code == 200
    after = identity(client, user_id)
    for field in ("primary_factory_id", "primary_department", "position", "primary_assignment"):
        assert after[field] == before[field], field
    with dbm.SessionLocal() as db:
        assert not auth.can(auth.build_auth_context(db, db.get(authm.AuthUser, user_id)),
                            "molding_sample:create", "huakang-a", "engineering")


def test_freeze_invalidates_every_session_before_and_after_restore(client):
    user_id = engineer(client)
    cookies = []
    for _ in range(3):
        login(client, "identity-engineer")
        cookies.append(client.cookies.get("rr_session"))
    assert len(set(cookies)) == 3
    login(client, "admin")
    admin_cookie = client.cookies.get("rr_session")
    dbm, authm, _, _, _ = modules()
    for operation in ("freeze", "unfreeze"):
        assert commit(client, draft(client, user_id, operation)).status_code == 200
        with dbm.SessionLocal() as db:
            sessions = list(db.scalars(select(authm.AuthSession).where(authm.AuthSession.user_id == user_id)))
            assert len(sessions) >= 3 and all(s.status == "revoked" and s.revoked_at for s in sessions)
        for cookie in cookies:
            client.cookies.clear()
            client.cookies.set("rr_session", cookie)
            for url in ("/api/auth/me", "/api/directory/members", "/api/system/people",
                        "/api/internal-quotes/business-owners?factory_id=huakang-a"):
                response = client.get(url)
                assert response.status_code == 401, (operation, url, response.text)
        client.cookies.clear()
        client.cookies.set("rr_session", admin_cookie)
    assert login(client, "identity-engineer")["id"] == user_id


def test_stopped_worker_boundary_all_identity_consumers_and_frozen_scheduled_package(client, monkeypatch):
    user_id = engineer(client)
    dbm, authm, _, auth, clock = modules()
    boundary = clock.utc_now() + timedelta(days=1)
    row = draft(client, user_id, "primary_assignment_transfer",
        source_assignment_id=identity(client, user_id)["primary_assignment"]["id"], effective_at=clock.stamp(boundary),
        new_assignment={"org_unit_id": "huakang-b", "department_code": "sales-business", "official_position_title": "业务主管",
                        "role_bindings": [{"role_id": "position_sales_supervisor", "department": "sales-business"}]})
    assert commit(client, row).status_code == 200
    # Publish a changed live template after approval. The scheduled snapshot stays fixed.
    with dbm.SessionLocal() as db:
        extra = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "system:user_manage"))
        db.add(authm.AuthRolePermission(id=uuid4().hex, role_id="position_sales_supervisor", permission_id=extra.id))
        db.commit()
    login(client, "identity-engineer")
    target_cookie = client.cookies.get("rr_session")
    login(client, "admin")
    admin_cookie = client.cookies.get("rr_session")
    contexts = []
    for at, factory, department in ((boundary - timedelta(microseconds=1), "huakang-a", "engineering"),
                                    (boundary, "huakang-b", "sales-business"),
                                    (boundary + timedelta(seconds=1), "huakang-b", "sales-business")):
        set_clock(monkeypatch, at)
        client.cookies.clear()
        client.cookies.set("rr_session", target_cookie)
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["profile"]["primary_factory_id"] == factory
        assert me.json()["profile"]["primary_department"] == department
        contexts.append(me.json()["identity"]["effective_context_key"])
        client.cookies.clear()
        client.cookies.set("rr_session", admin_cookie)
        for url in ("/api/system/people?page_size=100", "/api/directory/members?page_size=50", "/api/system/users"):
            response = client.get(url)
            assert response.status_code == 200, response.text
            data = response.json()
            found = next(p for p in (data["items"] if isinstance(data, dict) else data) if p["id"] == user_id)
            assert found["primary_factory_id"] == factory, (url, found)
            assert found["primary_department"] == department, (url, found)
        for candidate_factory in ("huakang-a", "huakang-b"):
            owners = client.get("/api/internal-quotes/business-owners", params={"factory_id": candidate_factory})
            assert owners.status_code == 200, owners.text
            assert (user_id in {p["id"] for p in owners.json()}) == (at >= boundary and candidate_factory == "huakang-b")
        with dbm.SessionLocal() as db:
            context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
            assert not auth.can(context, "system:user_manage", "huakang-b", "sales-business")
            assert auth.can(context, "molding_sample:create", "huakang-a", "engineering") == (at < boundary)
            assert auth.can(context, "internal_quote:sales_review", "huakang-b", "sales-business") == (at >= boundary)
            assert db.get(authm.EmployeeProfile, user_id).primary_factory_id == "huakang-a"
        record = client.get(f"/api/iam/identity-changes/{row['id']}").json()
        assert record["handover_refresh_pending"] == (at >= boundary)
    assert contexts[0] != contexts[1] == contexts[2]
    reset = client.post("/api/auth/password-reset-requests", json={"username": "identity-engineer",
        "display_name": "测试用户", "contact": "13800000000", "note": "跨预约边界找回密码"})
    assert reset.status_code == 200, reset.text
    requests = client.get("/api/system/password-reset-requests").json()
    request = next(r for r in requests if r["user_id"] == user_id)
    assert request["factory_id"] == request["matched_user"]["factory_id"] == "huakang-b"
    assert request["department"] == request["matched_user"]["department"] == "sales-business"
    assert request["match_checks"]["scope"] is True


def test_restart_and_seed_reconcile_preserve_revoked_expired_and_future_sources(client):
    user_id = engineer(client)
    dbm, authm, _, auth, clock = modules()
    now = clock.utc_now()
    for factory in ("huakang-b", "huaxing", "huadeng"):
        assert commit(client, add_assignment(client, user_id, factory=factory)).status_code == 200
    with dbm.SessionLocal() as db:
        links = list(db.scalars(select(authm.AuthUserRole).where(authm.AuthUserRole.user_id == user_id,
                                                               authm.AuthUserRole.role_id == "position_sales_supervisor")))
        for binding in links:
            meta = db.get(authm.AuthRoleBindingMetadata, binding.id)
            if binding.factory_id == "huakang-b":
                meta.state = "revoked"
            elif binding.factory_id == "huaxing":
                meta.valid_until = clock.stamp(now - timedelta(seconds=1))
            else:
                meta.valid_from = clock.stamp(now + timedelta(days=7))
        db.commit()
        before = {b.id: (db.get(authm.AuthRoleBindingMetadata, b.id).state,
                         db.get(authm.AuthRoleBindingMetadata, b.id).valid_from,
                         db.get(authm.AuthRoleBindingMetadata, b.id).valid_until) for b in links}
    for _ in range(2):
        dbm.init_db()  # The actual application startup/reconcile path.
        with dbm.SessionLocal() as db:
            context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
            assert auth.can(context, "molding_sample:create", "huakang-a", "engineering")
            for factory in ("huakang-b", "huaxing", "huadeng"):
                assert not auth.can(context, "internal_quote:sales_review", factory, "sales-business"), factory
            assert before == {key: (db.get(authm.AuthRoleBindingMetadata, key).state,
                                    db.get(authm.AuthRoleBindingMetadata, key).valid_from,
                                    db.get(authm.AuthRoleBindingMetadata, key).valid_until) for key in before}


def test_cd_factory_and_disabled_modules_reject_wildcard_administrator(client, monkeypatch):
    # An actual wildcard admin is stronger than a broad C/D organization role.
    for factory in ("huakang-c", "huakang-d"):
        for path, status in (("/api/three-d-printing/dashboard", 400),
                             ("/api/uv-operations/access", 422),
                             ("/api/spray-operations/access", 422)):
            response = client.get(path, params={"factory_id": factory})
            assert response.status_code == status, (path, response.text)
        command = client.post("/api/three-d-printing/printers/not-a-real-printer/commands",
                              json={"factory_id": factory, "action": "pause", "reason": "验证范围拒绝",
                                    "idempotency_key": uuid4().hex})
        assert command.status_code == 400 and "华康A" in command.text, command.text
    for path, factory in (("/api/uv-operations/access", "huakang-a"),
                          ("/api/spray-operations/access", "huaxing")):
        response = client.get(path, params={"factory_id": factory})
        assert response.status_code == 503 and response.json()["code"] == "module_disabled", response.text


@pytest.mark.parametrize("source,factory,future", [("role", "huakang-b", True), ("allow", "*", False), ("deny", "huakang-b", True)])
def test_all_management_paths_protect_independent_sources(client, source, factory, future):
    target = engineer(client)
    manager = create_user("scope-manager", "engineer", "huakang-a", "engineering")
    dbm, authm, identitym, auth, clock = modules()
    with dbm.SessionLocal() as db:
        for code in ("system:user_manage", "system:access_manage"):
            permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == code))
            db.add(authm.AuthUserPermissionOverride(id=uuid4().hex, user_id=manager, permission_id=permission.id,
                effect="allow", factory_id="huakang-a", department="engineering", status="active"))
        db.add(identitym.IamDelegation(id=uuid4().hex, user_id=manager, org_unit_id="huakang-a", department="engineering",
            role_ids_json="[]", factory_ids_json='["huakang-a"]', status="active"))
        starts = clock.stamp(clock.utc_now() + timedelta(days=1)) if future else ""
        if source == "role":
            from app.services.identity_sources import snapshot_role
            binding = authm.AuthUserRole(id=uuid4().hex, user_id=target, role_id="warehouse_keeper", factory_id=factory, department="pmc-warehouse")
            db.add(binding)
            db.flush()
            db.add(authm.AuthRoleBindingMetadata(user_role_id=binding.id, state="active", source_type="individual_exception",
                employment_epoch=1, valid_from=starts, role_version_id=snapshot_role(db, binding.role_id).id))
        else:
            permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "carton_procurement:read"))
            db.add(authm.AuthUserPermissionOverride(id=uuid4().hex, user_id=target, permission_id=permission.id,
                effect=source, factory_id=factory, department="pmc-warehouse", status="active", valid_from=starts, employment_epoch=1))
        db.commit()
    login(client, "scope-manager")
    people = client.get("/api/system/people")
    assert people.status_code == 200, people.text
    assert target not in {p["id"] for p in people.json()["items"]}
    assert people.json()["total"] == 1
    assert client.get(f"/api/system/users/{target}/identity").status_code == 403
    assert client.get(f"/api/system/users/{target}/assignments").status_code == 403
    assert client.patch(f"/api/system/users/{target}/status", json={"status": "suspended"}).status_code == 403
    rejected = client.post("/api/iam/identity-changes", json={"request_type": "leave", "target_user_id": target,
        "reason": "越范围不能办理", "base_identity_version": 1, "base_authorization_version": 2})
    assert rejected.status_code == 403, rejected.text
    with dbm.SessionLocal() as db:
        assert db.get(authm.AuthUser, target).status == "active"


def test_registration_system_permission_is_an_independent_source(client):
    dbm, authm, _, _, _ = modules()
    role_id = "registration-custom-system"
    with dbm.SessionLocal() as db:
        db.add(authm.AuthRole(id=role_id, code=role_id, name="范围内人员管理"))
        db.flush()
        db.add(authm.AuthRoleMetadata(role_id=role_id, scope_mode="own_factory"))
        permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "system:user_manage"))
        db.add(authm.AuthRolePermission(id=uuid4().hex, role_id=role_id, permission_id=permission.id))
        db.commit()
    result = client.post("/api/auth/register", json={"username": "review-custom-system", "display_name": "审核人员",
        "password": "Testing123!", "confirm_password": "Testing123!", "phone": "13800000002", "email": "",
        "factory_id": "huakang-a", "department": "engineering", "position": "工程"})
    assert result.status_code == 200, result.text
    request = next(r for r in client.get("/api/system/registration-requests").json() if r["username"] == "review-custom-system")
    approved = client.post(f"/api/system/registration-requests/{request['id']}/approve", json={
        "role_assignments": [{"role_id": role_id, "factory_id": "huakang-a", "department": "engineering"}], "review_comment": "独立确认管理权"})
    assert approved.status_code == 200, approved.text
    with dbm.SessionLocal() as db:
        binding = db.scalar(select(authm.AuthUserRole).where(authm.AuthUserRole.user_id == request["user_id"], authm.AuthUserRole.role_id == role_id))
        meta = db.get(authm.AuthRoleBindingMetadata, binding.id)
        assert meta.source_type == "system_administration" and meta.assignment_id is None


@pytest.mark.parametrize("operation", ["approve", "reopen", "reject"])
def test_password_reset_reloads_actor_after_revocation(client, operation):
    from fastapi import HTTPException
    target = engineer(client)
    actor_id = create_user("reset-reviewer", "admin", "*", "*")
    result = client.post("/api/auth/password-reset-requests", json={"username": "identity-engineer",
        "display_name": "测试用户", "contact": "13800000000", "note": "旧审核上下文不能使用"})
    assert result.status_code == 200, result.text
    reset = next(r for r in client.get("/api/system/password-reset-requests").json() if r["user_id"] == target)
    dbm, authm, _, auth, _ = modules()
    with dbm.SessionLocal() as db:
        stale_actor = auth.build_auth_context(db, db.get(authm.AuthUser, actor_id))
    assert commit(client, draft(client, actor_id, "freeze")).status_code == 200
    service = importlib.import_module("app.services.system")
    schemas = importlib.import_module("app.schemas.system")
    payload = schemas.PasswordResetReviewRequest(identity_verified=True, review_comment="已核实本人")
    with dbm.SessionLocal() as db:
        with pytest.raises(HTTPException) as rejected:
            if operation == "reject":
                service.reject_password_reset_request(db, stale_actor, reset["id"], payload)
            else:
                service.open_password_reset_claim_window(db, stale_actor, reset["id"], payload, operation)
        assert rejected.value.status_code == 401
        db.rollback()
        assert db.get(authm.AuthPasswordResetRequest, reset["id"]).status == "pending"


def test_late_commit_failure_rolls_back_identity_audit_outbox_and_receipt(client):
    from fastapi import HTTPException
    from sqlalchemy import event, func
    from sqlalchemy.orm import Session
    user_id = engineer(client)
    before = identity(client, user_id)
    dbm, authm, identitym, _, _ = modules()
    tables = (authm.AuthAuthorizationEvent, identitym.IamOutbox, identitym.IamMutationReceipt)
    row = draft(client, user_id, "profile_correction", official_position_title="不得留下的修改")
    plan = preview(client, row)
    with dbm.SessionLocal() as db:
        counts = [db.scalar(select(func.count()).select_from(model)) for model in tables]
    injected = []
    def fail_durable_commit(db):
        # Work-center's earlier before_commit listener already flushes db.new.
        # Inspect this transaction's durable rows so listener order cannot skip
        # the fault injection, and exercise rollback after all actual INSERTs.
        db.flush()
        if db.scalar(select(func.count()).select_from(identitym.IamMutationReceipt)) > counts[-1]:
            injected.append(True)
            raise HTTPException(409, "injected failure immediately before commit")
    event.listen(Session, "before_commit", fail_durable_commit)
    try:
        failed = commit(client, row, plan)
        assert failed.status_code == 409, failed.text
        assert injected == [True]
    finally:
        event.remove(Session, "before_commit", fail_durable_commit)
    after = identity(client, user_id)
    assert after["position"] == before["position"] and after["identity_version"] == before["identity_version"]
    with dbm.SessionLocal() as db:
        assert counts == [db.scalar(select(func.count()).select_from(model)) for model in tables]
    assert commit(client, row, plan).status_code == 200  # The same preview was not consumed.


def test_v2_supplier_transfer_preserves_portal_data_scope(client):
    from test_carton_supplier_portal import BASE, setup_portal, supplier_login
    setup_portal(client)
    memberships_before = client.get(BASE + "/memberships").json()
    assert [m["factory_id"] for m in memberships_before] == ["huaxing"]
    login(client, "admin")
    confirm(client, "supplier-test")
    row = draft(client, "supplier-test", "primary_assignment_transfer",
        source_assignment_id=identity(client, "supplier-test")["primary_assignment"]["id"],
        new_assignment={"org_unit_id": "huakang-b", "department_code": "engineering", "official_position_title": "工程师",
                        "role_bindings": [{"role_id": "engineer", "department": "engineering"}]})
    assert commit(client, row).status_code == 200
    supplier_login(client)
    assert client.get(BASE + "/memberships").json() == memberships_before
    assert client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).status_code == 200
    assert client.get(BASE + "/workspace", params={"factory_id": "huakang-b"}).status_code == 403
