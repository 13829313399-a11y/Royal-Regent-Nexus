"""Real HTTP and preserved sources on disposable IAM databases."""
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from test_iam_api import make_client, login, create_user
from test_identity_changes import confirm, identity
from test_position_reviews import commit as workbench_commit
from test_position_workbench_boundaries import registration
from test_identity_postgres import postgres


@pytest.fixture
def client(monkeypatch):
    for flag in ("IAM_IDENTITY_WRITES_ENABLED", "IAM_POSITION_WORKBENCH_ENABLED", "IAM_ACCESS_STUDIO_WRITES_ENABLED"):
        monkeypatch.setenv(flag, "true")
    with make_client(monkeypatch) as app:
        login(app, "admin")
        yield app


def draft_for(person, **edits):
    return {"reason": "核对正式任职", "source_assignment_id": person["primary_assignment"]["id"],
        "base_identity_version": person["identity_version"], "base_authorization_version": person["authorization_version"], **edits}


def source_rows(user_id):
    from app.db import SessionLocal
    from app.models.auth import AuthRoleBindingMetadata, AuthUserRole
    with SessionLocal() as db:
        pairs = db.execute(select(AuthUserRole, AuthRoleBindingMetadata).join(AuthRoleBindingMetadata,
            AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).where(AuthUserRole.user_id == user_id))
        return {binding.id: (binding.role_id, {c.name: getattr(meta, c.name) for c in meta.__table__.columns})
                for binding, meta in pairs}


def business_counts():
    from app.db import SessionLocal
    from app.models.auth import AuthAccessRequest, AuthAuthorizationEvent, AuthUserRole, SystemNotification
    from app.models.identity import EmployeeAssignment, IamOutbox, IamRoleVersion
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(model)) for model in (
            AuthAccessRequest, AuthAuthorizationEvent, AuthUserRole, SystemNotification, EmployeeAssignment, IamOutbox, IamRoleVersion)]


def test_title_and_named_binding_changes_preserve_untouched_sources(client):
    uid = create_user("studio-employee", "position_engineering_engineer", "huakang-a", "engineering")
    observer = create_user("studio-observer", "position_engineering_engineer", "huakang-a", "engineering")
    untouched_person = source_rows(observer)
    url = f"/api/iam/users/{uid}/access-studio"
    person = confirm(client, uid)
    initial = source_rows(uid)
    counts = business_counts()
    original_id = next(iter(initial))
    body = draft_for(person, official_position_title="工程技术员")
    for _ in range(2):
        preview = client.post(url + "/preview", json=body)
        assert preview.status_code == 200, preview.text
        diffs = preview.json()["permission_diffs"]
        assert diffs["retained"] and not diffs["added"] and not diffs["removed"] and not diffs["source_changed"]
        assert source_rows(uid) == initial and business_counts() == counts
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    commit_body = {"preview_token": preview.json()["preview_token"]}
    result = client.post(url + "/commit", headers=headers, json=commit_body)
    assert result.status_code == 200, result.text
    assert client.post(url + "/commit", headers=headers, json=commit_body).json() == result.json()
    assert client.get(f"/api/iam/access-studio/receipts/{key}").json()["result"] == result.json()
    assert client.post(url + "/commit", headers=headers, json={**commit_body, "risk_acknowledged": True}).status_code == 409
    assert source_rows(uid) == initial and identity(client, uid)["position"] == "工程技术员"
    assert client.post(url + "/preview", json=body).status_code == 409
    add = draft_for(identity(client, uid), add_packages=[{"role_id": "position_engineering_supervisor",
        "department": "engineering", "factory_scope": {"kind": "selected", "factory_ids": ["huaxing"]}}])
    preview = client.post(url + "/preview", json=add)
    assert preview.status_code == 200, preview.text
    assert preview.json()["high_risk"] and preview.json()["permission_diffs"]["added"]
    assert source_rows(uid) == initial
    body = {"preview_token": preview.json()["preview_token"], "risk_acknowledged": True}
    result = client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())}, json=body)
    assert result.status_code == 200, result.text
    current = source_rows(uid)
    assert current[original_id] == initial[original_id]
    added_id, = current.keys() - initial.keys()
    assert current[added_id][1]["scope_ceiling_json"] == '["huaxing"]'
    preview = client.post(url + "/preview", json=draft_for(identity(client, uid), remove_binding_ids=[added_id]))
    assert preview.status_code == 200, preview.text
    assert preview.json()["permission_diffs"]["removed"] and not preview.json()["requires_empty_confirmation"]
    result = client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": preview.json()["preview_token"], "risk_acknowledged": True})
    assert result.status_code == 200, result.text
    assert source_rows(uid)[original_id] == initial[original_id]
    assert source_rows(uid)[added_id][1]["state"] == "revoked"
    assert source_rows(observer) == untouched_person
    empty = client.post(url + "/preview", json=draft_for(identity(client, uid), remove_binding_ids=[original_id]))
    assert empty.status_code == 200 and empty.json()["requires_empty_confirmation"], empty.text
    assert client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": empty.json()["preview_token"], "risk_acknowledged": True}).status_code == 422
    from app.core.config import settings
    settings.iam_access_studio_writes_enabled = False
    assert client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": empty.json()["preview_token"], "risk_acknowledged": True, "confirm_empty_packages": True}).status_code == 503
    assert source_rows(uid)[original_id] == initial[original_id]
    login(client, "studio-observer")
    assert client.get(f"/api/iam/access-studio/receipts/{key}").json()["status"] == "not_observed"


def test_multi_registration_rejects_bad_second_package_and_commits_valid_pairs(client):
    row, _ = registration(client, "studio-newhire")
    uid, key = row["user"]["id"], row["item_key"]
    url = f"/api/iam/position-workbench/items/{key}/preview"
    packages = {p["role_id"]: p for p in client.get("/api/iam/position-workbench/packages",
        params={"item_key": key}).json()["items"]}
    selections = [{"role_id": rid, "definition_hash": packages[rid]["definition_hash"], "permission_department": "engineering",
        "factory_scope": {"kind": "selected", "factory_ids": [factory]}} for rid, factory in (
            ("position_engineering_engineer", "huakang-a"), ("position_engineering_supervisor", "huaxing"))]
    body = {"expected_source_revision": row["source_revision"], "decision": "apply_package", "independent_allow_decisions": [],
        "confirmed_profile": {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "工程员"},
        "package_selections": selections}
    invalid = {**body, "package_selections": [selections[0], {**selections[1], "permission_department": "accounting"}]}
    assert client.post(url, json=invalid).status_code == 422
    before = source_rows(uid)
    preview = client.post(url, json=body)
    assert preview.status_code == 200, preview.text
    assert source_rows(uid) == before
    result, _ = workbench_commit(client, key, preview.json())
    assert result.status_code == 200, result.text
    active = {rid: meta for rid, meta in source_rows(uid).values() if meta["state"] == "active"}
    assert set(active) == {s["role_id"] for s in selections}
    assert active[selections[0]["role_id"]]["scope_ceiling_json"] == '["huakang-a"]'
    assert active[selections[1]["role_id"]]["scope_ceiling_json"] == '["huaxing"]'


def test_explicit_upgrade_keeps_old_binding_and_deny_until_commit(client):
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthRolePermission, AuthUserPermissionOverride
    from app.core.config import settings
    uid = create_user("studio-upgrade", "position_engineering_engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    before = source_rows(uid)
    bid = next(iter(before))
    with SessionLocal() as db:
        permission = db.scalar(select(AuthPermission).where(AuthPermission.code == "molding_sample:supervisor_review"))
        db.add(AuthRolePermission(id=uuid4().hex, role_id="position_engineering_engineer", permission_id=permission.id))
        db.add(AuthUserPermissionOverride(id="persistent-deny", user_id=uid, permission_id=permission.id,
            effect="deny", factory_id="huakang-a", department="engineering", employment_epoch=1, status="active"))
        db.commit()
    body = draft_for(person, upgrade_binding_ids=[bid])
    url = f"/api/iam/users/{uid}/access-studio"
    pre = client.post(url + "/preview", json=body)
    assert pre.status_code == 200, pre.text
    assert any(d["permission_code"] == "molding_sample:supervisor_review" for d in pre.json()["explicit_denials"])
    assert source_rows(uid) == before
    result = client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": pre.json()["preview_token"], "risk_acknowledged": True})
    assert result.status_code == 200, result.text
    after = source_rows(uid)
    assert after.keys() == before.keys()
    assert after[bid][1]["role_version_id"] != before[bid][1]["role_version_id"]
    for field in ("scope_ceiling_json", "employment_epoch", "valid_from", "valid_until", "assignment_id"):
        assert after[bid][1][field] == before[bid][1][field]
    with SessionLocal() as db:
        assert db.get(AuthUserPermissionOverride, "persistent-deny").status == "active"
    key = result.json()["command_id"]
    settings.iam_access_studio_writes_enabled = False
    assert client.get(f"/api/iam/access-studio/receipts/{key}").json()["result"] == result.json()


def test_non_delegated_request_requires_different_reviewer(client):
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthUserPermissionOverride
    uid = create_user("studio-subject", "position_engineering_engineer", "huakang-a", "engineering")
    manager = create_user("studio-manager", "engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    from test_position_reviews import submit
    login(client, "studio-subject")
    application = submit(client, "工程复核")
    item = "position:" + application["id"]
    with SessionLocal() as db:
        for code in ("system:user_manage", "system:access_manage", "system:permission_catalog_read"):
            perm = db.scalar(select(AuthPermission).where(AuthPermission.code == code))
            db.add(AuthUserPermissionOverride(id=uuid4().hex, user_id=manager, permission_id=perm.id,
                effect="allow", factory_id="huakang-a", department="engineering", status="active"))
        db.commit()
    login(client, "studio-manager")
    url = f"/api/iam/users/{uid}/access-studio"
    body = draft_for(person, position_review={"item_key": item, "expected_source_revision": "position:1",
        "confirmed_profile": {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "工程复核"}},
        add_packages=[{"role_id": "position_engineering_supervisor", "department": "engineering",
        "factory_scope": {"kind": "selected", "factory_ids": ["huakang-a"]}}])
    before = source_rows(uid)
    preview = client.post(url + "/preview", json=body)
    assert preview.status_code == 200 and preview.json()["requires_approval"], preview.text
    submitted = client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": preview.json()["preview_token"], "risk_acknowledged": True})
    assert submitted.status_code == 200 and submitted.json()["decision"] == "pending_approval", submitted.text
    assert source_rows(uid) == before
    change_url = "/api/iam/identity-changes/" + submitted.json()["change_id"]
    for actor, status in (("studio-manager", 403), ("admin", 200)):
        login(client, actor)
        plan = client.post(change_url + "/preview")
        assert plan.status_code == 200, plan.text
        result = client.post(change_url + "/approve", headers={"Idempotency-Key": str(uuid4())},
            json={"preview_token": plan.json()["preview_token"], "expected_request_revision": 2, "confirm_high_risk": True})
        assert result.status_code == status, result.text
        if status == 403:
            assert source_rows(uid) == before
    assert len(source_rows(uid)) == len(before) + 1
    assert client.get("/api/iam/position-workbench/items/" + item).json()["status"] == "applied"


@pytest.mark.parametrize("engine", ["sqlite", "postgres"])
def test_expired_and_concurrent_commands_leave_one_change(client, engine, request):
    if engine == "postgres":
        request.getfixturevalue("postgres")
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models.auth import AuthAuthorizationPreview
    from app.services.iam import _token_hash
    from app.services.identity_resolver import utc_now
    uid = create_user("studio-concurrency", "engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    url = f"/api/iam/users/{uid}/access-studio"
    changes = draft_for(person, official_position_title="并发核实")
    first = client.post(url + "/preview", json=changes).json()["preview_token"]
    with SessionLocal() as db:
        preview = db.scalar(select(AuthAuthorizationPreview).where(AuthAuthorizationPreview.token_hash == _token_hash(first)))
        preview.expires_at = (utc_now().astimezone() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
    assert client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())}, json={"preview_token": first}).status_code == 410
    assert identity(client, uid)["identity_version"] == person["identity_version"]
    token = client.post(url + "/preview", json=changes).json()["preview_token"]
    keys = [str(uuid4()), str(uuid4())]
    def send(key):
        return client.post(url + "/commit", headers={"Idempotency-Key": key}, json={"preview_token": token})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, keys))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    current = identity(client, uid)
    assert current["identity_version"] == person["identity_version"] + 1
    assert current["authorization_version"] == person["authorization_version"] + 1
    for key, result in zip(keys, responses):
        receipt = client.get(f"/api/iam/access-studio/receipts/{key}").json()
        assert receipt["status"] == ("committed" if result.status_code == 200 else "not_observed")


def test_legacy_confirmation_preserves_pinned_scope_and_checks_future_boundary(client):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthRoleBindingMetadata, AuthRolePermission
    from app.services.identity_resolver import utc_now, stamp
    from app.services.identity_sources import snapshot_role
    from test_identity_changes import draft
    uid = create_user("studio-historical", "position_engineering_engineer", "huakang-a", "engineering")
    binding_id, = source_rows(uid)
    with SessionLocal() as db:
        meta = db.get(AuthRoleBindingMetadata, binding_id)
        original_version = snapshot_role(db, "position_engineering_engineer", "user-admin").id
        meta.role_version_id, meta.scope_ceiling_json = original_version, '["huakang-a"]'
        permission = db.scalar(select(AuthPermission).where(AuthPermission.code == "molding_sample:supervisor_review"))
        db.add(AuthRolePermission(id=uuid4().hex, role_id="position_engineering_engineer", permission_id=permission.id))
        db.commit()
    legacy = identity(client, uid)
    url = f"/api/iam/users/{uid}/access-studio/preview"
    assert client.post(url, json={"base_identity_version": legacy["identity_version"], "base_authorization_version": legacy["authorization_version"],
        "source_assignment_id": "unconfirmed", "official_position_title": "历史岗位", "reason": "核实"}).status_code == 409
    row = draft(client, uid, "confirm_identity", new_assignment={"org_unit_id": legacy["primary_factory_id"],
        "department_code": legacy["primary_department"], "official_position_title": legacy["position"],
        "valid_until": stamp(utc_now() + timedelta(days=1))},
        binding_dispositions=[{"binding_id": binding_id, "source": "assignment"}])
    refused = client.post(f"/api/iam/identity-changes/{row['id']}/preview")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "MIGRATION_PERMISSION_DRIFT", refused.text
    assert identity(client, uid)["identity_mode"] == "legacy"
    confirm(client, uid)
    source = source_rows(uid)[binding_id][1]
    assert (source["role_version_id"], source["scope_ceiling_json"]) == (original_version, '["huakang-a"]')


@pytest.mark.parametrize("engine", ["sqlite", "postgres"])
def test_studio_legacy_preview_has_no_draft_and_confirm_is_separate(client, engine, request):
    if engine == "postgres":
        request.getfixturevalue("postgres")
    uid = create_user("studio-review-first", "engineer", "huakang-a", "engineering")
    legacy = identity(client, uid)
    url = f"/api/iam/users/{uid}/access-studio"
    body = {"request_type": "confirm_identity", "target_user_id": uid, "reason": "逐项人工核实",
        "base_identity_version": legacy["identity_version"], "base_authorization_version": legacy["authorization_version"],
        "new_assignment": {"org_unit_id": legacy["primary_factory_id"], "department_code": legacy["primary_department"],
            "official_position_title": legacy["position"]},
        "binding_dispositions": [{"binding_id": b["id"], "source": "assignment"} for b in legacy["role_bindings"]]}
    counts, sources = business_counts(), source_rows(uid)
    for _ in range(2):
        pre = client.post(url + "/legacy-preview", json=body)
        assert pre.status_code == 200, pre.text
        assert not pre.json()["permission_diffs"]["added"] and not pre.json()["permission_diffs"]["removed"]
        assert business_counts() == counts and source_rows(uid) == sources
    key = str(uuid4())
    command = {"preview_token": pre.json()["preview_token"]}
    if pre.json()["high_risk"]:
        denied = client.post(url + "/commit", headers={"Idempotency-Key": key}, json=command)
        assert denied.status_code == 422 and denied.json()["code"] == "CONFIRM_HIGH_RISK"
        assert source_rows(uid) == sources
        command["risk_acknowledged"] = True
    result = client.post(url + "/commit", headers={"Idempotency-Key": key}, json=command)
    assert result.status_code == 200 and result.json()["decision"] == "applied", result.text
    assert identity(client, uid)["identity_mode"] == "v2"
    assert client.get(f"/api/iam/access-studio/receipts/{key}").json()["result"] == result.json()
    assert business_counts()[0] == counts[0] + 1


@pytest.mark.parametrize("engine", ["sqlite", "postgres"])
def test_position_application_delta_moves_only_named_sources_and_closes_atomically(client, monkeypatch, engine, request):
    if engine == "postgres":
        request.getfixturevalue("postgres")
    from fastapi import HTTPException
    from app.services import access_studio_reviews
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context, can
    from app.services.identity_resolver import utc_now
    from test_position_reviews import submit
    uid = create_user("studio-reassignment", "position_engineering_engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    before, historical_at = source_rows(uid), utc_now()
    login(client, "studio-reassignment")
    review = submit(client, "工程负责人")
    login(client, "admin")
    item = "position:" + review["id"]
    url = f"/api/iam/users/{uid}/access-studio"
    detail_url = "/api/iam/position-workbench/items/" + item
    link = {"item_key": item, "expected_source_revision": "position:1", "confirmed_profile": {
        "org_unit_id": "huaxing", "department_code": "engineering", "position": "工程负责人"}}
    extra = {"role_id": "position_engineering_supervisor", "department": "engineering", "factory_scope": {"kind": "home"}}
    body = draft_for(person, position_review=link, add_packages=[extra])
    counts = business_counts()
    pre = client.post(url + "/preview", json=body)
    assert pre.status_code == 200 and pre.json()["permission_diffs"]["added"], pre.text
    assert source_rows(uid) == before and business_counts() == counts
    assert client.get(detail_url).json()["status"] == "pending"
    headers, command = {"Idempotency-Key": str(uuid4())}, {"preview_token": pre.json()["preview_token"], "risk_acknowledged": True}
    original = access_studio_reviews.complete_review
    def interrupted(*args):
        raise HTTPException(409, "岗位单故障注入")
    monkeypatch.setattr(access_studio_reviews, "complete_review", interrupted)
    assert client.post(url + "/commit", headers=headers, json=command).status_code == 409
    assert source_rows(uid) == before and client.get(detail_url).json()["status"] == "pending"
    monkeypatch.setattr(access_studio_reviews, "complete_review", original)
    res = client.post(url + "/commit", headers=headers, json=command)
    assert res.status_code == 200 and res.json()["decision"] == "applied", res.text
    assert client.get(detail_url).json()["status"] == "applied"
    assert client.get("/api/iam/identity-changes/" + res.json()["change_id"]).status_code == 200
    now = identity(client, uid)
    assert now["primary_factory_id"] == "huaxing" and now["position"] == "工程负责人"
    current = source_rows(uid)
    for bid, (role_id, meta) in before.items():
        assert current[bid][0] == role_id and current[bid][1]["assignment_id"] == now["primary_assignment"]["id"]
        assert {k: v for k, v in current[bid][1].items() if k != "assignment_id"} == {k: v for k, v in meta.items() if k != "assignment_id"}
    with SessionLocal() as db:
        subject = db.get(AuthUser, uid)
        past = build_auth_context(db, subject, at=historical_at)
        present = build_auth_context(db, subject)
        assert can(past, "molding_sample:read", "huakang-a", "engineering", at=historical_at)
        assert can(present, "molding_sample:supervisor_review", "huaxing", "engineering")
    login(client, "studio-reassignment")
    second = submit(client, "工程负责人")
    login(client, "admin")
    second_link = {**link, "item_key": "position:" + second["id"]}
    no_change = client.post(url + "/preview", json=draft_for(now, position_review=second_link))
    assert no_change.status_code == 200, no_change.text
    assert not any(no_change.json()["permission_diffs"][k] for k in ("added", "removed", "source_changed"))
    supervisor = next(bid for bid, (rid, _) in current.items() if rid == "position_engineering_supervisor")
    remove = client.post(url + "/preview", json=draft_for(now, position_review=second_link, remove_binding_ids=[supervisor]))
    assert remove.status_code == 200, remove.text
    res = client.post(url + "/commit", headers={"Idempotency-Key": str(uuid4())},
        json={"preview_token": remove.json()["preview_token"], "risk_acknowledged": True})
    assert res.status_code == 200 and source_rows(uid)[supervisor][1]["state"] == "revoked", res.text
    assert all(source_rows(uid)[bid] == current[bid] for bid in before)

def test_omitted_department_separate_from_wildcard_and_rollback_on_omitted_only_drift(client, monkeypatch):
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthUserPermissionOverride
    from app.services import identity_changes as changes
    from app.services.identity_resolver import utc_now
    uid = create_user("studio-omit-department", "engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    code = "system:audit_read"
    with SessionLocal() as db:
        permission_id = db.scalar(select(AuthPermission.id).where(AuthPermission.code == code))
        db.add(AuthUserPermissionOverride(id="department-only", user_id=uid, permission_id=permission_id,
            effect="allow", status="active", factory_id="huakang-a", department="engineering", employment_epoch=1))
        db.commit()
    body = draft_for(person, official_position_title="工程技术员")
    url = f"/api/iam/users/{uid}/access-studio/preview"
    preview = client.post(url, json=body)
    assert preview.status_code == 200, preview.text
    summary = preview.json()
    assert summary["allowed_to_commit"] and summary["blocked_reasons"] == [] and summary["handover_summary"]
    retained = {t["department"]: t["department_name"] for t in summary["permission_diffs"]["retained"]
                if t["permission_code"] == code and t["factory_id"] == "huakang-a"}
    assert "未指定部门" in retained[""] and "engineering" in retained and "*" not in retained
    original = changes.apply_plan
    def simulate_drift(db, row, actor, plan):
        result = original(db, row, actor, plan)
        before, configured = changes.access_matrix(db, uid, utc_now())
        db.add(AuthUserPermissionOverride(id="rollback-probe", user_id=uid, permission_id=permission_id,
            effect="deny", status="active", factory_id="huakang-a", department="accounting", employment_epoch=1))
        db.flush()
        after, runtime = changes.access_matrix(db, uid, utc_now())
        assert set(before) ^ set(after) == configured ^ runtime == {(code, "huakang-a", "")}
        return result
    monkeypatch.setattr(changes, "apply_plan", simulate_drift)
    counts = business_counts()
    refused = client.post(url, json=body)
    assert refused.status_code == 409 and refused.json()["code"] == "MIGRATION_PERMISSION_DRIFT", refused.text
    assert refused.json()["details"]["blocked_reasons"] and not refused.json()["details"]["allowed_to_commit"]
    assert business_counts() == counts
    with SessionLocal() as db:
        assert db.get(AuthUserPermissionOverride, "rollback-probe") is None
    assert identity(client, uid)["position"] == person["position"]

    from app.models.auth import AuthRoleBindingMetadata
    original_sources = source_rows(uid)
    binding_id, = original_sources
    def change_origin_only(db, row, actor, plan):
        result = original(db, row, actor, plan)
        db.get(AuthRoleBindingMetadata, binding_id).source_id = "unexpected-title-side-effect"
        db.flush()
        return result
    monkeypatch.setattr(changes, "apply_plan", change_origin_only)
    refused = client.post(url, json=body)
    assert refused.status_code == 409 and refused.json()["code"] == "MIGRATION_SOURCE_DRIFT", refused.text
    assert source_rows(uid) == original_sources and business_counts() == counts



def test_legacy_matrix_tracks_configured_path_separately(client, monkeypatch):
    from app.core.config import settings
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthUserPermissionOverride
    from app.services import identity_changes as changes
    from app.services.identity_resolver import utc_now
    uid = create_user("studio-legacy-configured", "engineer", "huakang-a", "engineering")
    code = "system:audit_read"
    with SessionLocal() as db:
        permission_id = db.scalar(select(AuthPermission.id).where(AuthPermission.code == code))
        db.add(AuthUserPermissionOverride(id="legacy-only-canonical", user_id=uid, permission_id=permission_id,
            effect="allow", status="active", factory_id="huakang-a", department="engineering", employment_epoch=1))
        db.commit()
        monkeypatch.setattr(settings, "authz_mode", "legacy")
        canonical, runtime = changes.access_matrix(db, uid, utc_now())
        key = (code, "huakang-a", "")
        assert key in canonical and key not in runtime
        monkeypatch.setattr(settings, "authz_mode", "enforce")
        canonical, runtime = changes.access_matrix(db, uid, utc_now())
        assert key in canonical and key in runtime

def test_pinned_high_risk_source_change_requires_acknowledgement_with_zero_net_grants(client):
    import json
    from sqlalchemy import delete
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthPermissionMetadata, AuthRoleBindingMetadata, AuthRolePermission, AuthUserRole
    from app.models.identity import IamRoleVersion
    from app.services.system import role_is_high_risk
    uid = create_user("studio-source-only-risk", "engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    original_id, = source_rows(uid)
    duplicate = "second-retained-source"
    with SessionLocal() as db:
        original = db.get(AuthRoleBindingMetadata, original_id)
        definition = json.loads(db.get(IamRoleVersion, original.role_version_id).definition_json)
        code = definition["permissions"][0]
        pid = db.scalar(select(AuthPermission.id).where(AuthPermission.code == code))
        db.get(AuthPermissionMetadata, pid).risk_level = "high"
        db.add(AuthUserRole(id=duplicate, role_id="engineer", user_id=uid, factory_id="huakang-a", department="engineering"))
        db.flush()
        db.add(AuthRoleBindingMetadata(**{col.name: duplicate if col.name == "user_role_id" else getattr(original, col.name)
                                         for col in original.__table__.columns}))
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.role_id == "engineer"))
        db.commit()
        assert not role_is_high_risk(db, "engineer")  # The former pinned version contains the high-risk permission.
    original_sources = source_rows(uid)
    url = f"/api/iam/users/{uid}/access-studio"
    plan = client.post(url + "/preview", json=draft_for(person, remove_binding_ids=[duplicate]))
    assert plan.status_code == 200, plan.text
    preview = plan.json()
    diff = preview["permission_diffs"]
    assert not diff["added"] and not diff["removed"] and any(t["permission_code"] == code for t in diff["source_changed"])
    assert preview["high_risk"] and not preview["requires_empty_confirmation"]
    command_id = str(uuid4())
    headers = {"Idempotency-Key": command_id}
    command = {"preview_token": preview["preview_token"]}
    assert client.post(url + "/commit", headers=headers, json=command).json()["code"] == "CONFIRM_HIGH_RISK"
    assert source_rows(uid) == original_sources
    command["risk_acknowledged"] = True
    result = client.post(url + "/commit", headers=headers, json=command)
    assert result.status_code == 200, result.text
    assert client.post(url + "/commit", headers=headers, json=command).json() == result.json()
    assert source_rows(uid)[original_id] == original_sources[original_id] and source_rows(uid)[duplicate][1]["state"] == "revoked"

def test_studio_lifecycle_requires_confirmed_sources_and_explicit_package_department(client):
    uid = create_user("studio-before-confirmation", "engineer", "huakang-a", "engineering")
    legacy = identity(client, uid)
    url = f"/api/iam/users/{uid}/access-studio/preview"
    base = {"base_identity_version": legacy["identity_version"], "base_authorization_version": legacy["authorization_version"],
            "target_user_id": uid, "reason": "核对单项办理"}
    counts, sources = business_counts(), source_rows(uid)
    for action in ("freeze", "unfreeze", "leave"):
        refused = client.post(url, json={**base, "request_type": action})
        assert refused.status_code == 409 and refused.json()["code"] == "IDENTITY_REVIEW_REQUIRED", refused.text
        assert not refused.json()["details"]["allowed_to_commit"]
    assert counts == business_counts() and sources == source_rows(uid)
    person = confirm(client, uid)
    counts = business_counts()
    missing = {"role_id": "position_engineering_supervisor", "factory_scope": {"kind": "selected", "factory_ids": ["huakang-a"]}}
    refused = client.post(url, json=draft_for(person, add_packages=[missing]))
    assert refused.status_code == 422 and "作用部门" in refused.json()["details"]["blocked_reasons"][0], refused.text
    assert not refused.json()["details"]["allowed_to_commit"] and counts == business_counts()


def test_commit_reaching_authorization_boundary_rolls_back_and_keeps_receipt_retryable(client, monkeypatch):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models.auth import AuthPermission, AuthUserPermissionOverride
    from app.services import identity_changes as changes
    from app.services.identity_resolver import utc_now, stamp
    uid = create_user("studio-clock-boundary", "engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    deadline = utc_now() + timedelta(days=1)
    with SessionLocal() as db:
        pid = db.scalar(select(AuthPermission.id).where(AuthPermission.code == "system:audit_read"))
        db.add(AuthUserPermissionOverride(id="future-boundary", user_id=uid, permission_id=pid, valid_until=stamp(deadline),
            effect="deny", status="active", factory_id="huakang-a", department="engineering", employment_epoch=1))
        db.commit()
    url = f"/api/iam/users/{uid}/access-studio"
    preview = client.post(url + "/preview", json=draft_for(person, official_position_title="核实后的职位"))
    assert preview.status_code == 200, preview.text
    command = {"preview_token": preview.json()["preview_token"]}
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    counts, sources = business_counts(), source_rows(uid)
    original = changes.apply_or_submit
    with monkeypatch.context() as boundary:
        def at_boundary(db, row, actor, plan):
            assert plan["authorization_deadline"] == deadline
            boundary.setattr(changes, "utc_now", lambda: deadline)
            return original(db, row, actor, plan)
        boundary.setattr(changes, "apply_or_submit", at_boundary)
        refused = client.post(url + "/commit", headers=headers, json=command)
    assert refused.status_code == 409 and refused.json()["code"] == "AUTHORIZATION_CHANGED", refused.text
    assert client.get(f"/api/iam/access-studio/receipts/{key}").json()["status"] == "not_observed"
    assert identity(client, uid)["position"] == person["position"] and counts == business_counts() and sources == source_rows(uid)
    applied = client.post(url + "/commit", headers=headers, json=command)
    assert applied.status_code == 200, applied.text
    assert client.post(url + "/commit", headers=headers, json=command).json() == applied.json()
    assert sources == source_rows(uid)
