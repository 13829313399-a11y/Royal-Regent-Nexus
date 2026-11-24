"""Explicit personnel commands on a separately seeded SQLite database per test."""
from uuid import uuid4
from sqlalchemy import select
from test_access_studio import client, draft_for, source_rows, business_counts
from test_identity_changes import confirm, identity
from test_iam_api import create_user


def binding_contexts(uid):
    from app.db import SessionLocal
    from app.models.auth import AuthUserRole
    with SessionLocal() as db:
        return {row.id: (row.role_id, row.factory_id, row.department) for row in db.scalars(
            select(AuthUserRole).where(AuthUserRole.user_id == uid))}


def preview(client, uid, body):
    before = business_counts()
    response = client.post(f"/api/iam/users/{uid}/access-studio/preview", json=body)
    assert response.status_code == 200, response.text
    assert business_counts() == before
    return response.json()


def commit(client, uid, plan):
    url = f"/api/iam/users/{uid}/access-studio/commit"
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"preview_token": plan["preview_token"], "risk_acknowledged": True, "confirm_empty_packages": True}
    first = client.post(url, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert client.post(url, json=body, headers=headers).json() == first.json()
    return first.json()


def action(client, uid, kind, **fields):
    person = identity(client, uid)
    return {"request_type": kind, "target_user_id": uid, "base_identity_version": person["identity_version"],
            "base_authorization_version": person["authorization_version"], "reason": "人工核对单项变更", **fields}


def test_named_ceiling_and_primary_posting(client):
    uid = create_user("studio-named-ceiling", "position_engineering_engineer", "huakang-a", "engineering")
    other = create_user("studio-ceiling-witness", "position_engineering_engineer", "huakang-a", "engineering")
    confirm(client, other)
    witness = source_rows(other)
    witness_contexts = binding_contexts(other)
    person = confirm(client, uid)
    original, = source_rows(uid)
    added = {"role_id": "position_engineering_supervisor", "department": "engineering",
             "factory_scope": {"kind": "selected", "factory_ids": ["huaxing"]}}
    commit(client, uid, preview(client, uid, draft_for(person, add_packages=[added])))
    before = source_rows(uid)
    original_contexts = binding_contexts(uid)
    edit = draft_for(identity(client, uid), scope_updates=[{"binding_id": original, "factory_ids": ["huakang-a"]}])
    plan = preview(client, uid, edit)
    assert source_rows(uid) == before
    commit(client, uid, plan)
    after = source_rows(uid)
    assert binding_contexts(uid) == original_contexts
    for binding, old in before.items():
        if binding != original:
            assert after[binding] == old
            continue
        for key in ("role_version_id", "assignment_id", "valid_from", "valid_until", "source_id"):
            assert after[binding][1][key] == old[1][key]
        assert after[binding][1]["scope_ceiling_json"] == '["huakang-a"]'
    official = {"org_unit_id": "huaxing", "department_code": "engineering", "position": "新任工程师"}
    plan = preview(client, uid, draft_for(identity(client, uid), official_posting=official))
    assert not plan["permission_diffs"]["added"] and not plan["permission_diffs"]["removed"]
    commit(client, uid, plan)
    assert identity(client, uid)["primary_assignment"]["org_unit_id"] == "huaxing"
    for binding, old in after.items():
        updated = source_rows(uid)[binding][1]
        assert {k: v for k, v in updated.items() if k != "assignment_id"} == {k: v for k, v in old[1].items() if k != "assignment_id"}
        assert binding_contexts(uid)[binding] == original_contexts[binding]
    assert source_rows(other) == witness and binding_contexts(other) == witness_contexts


def test_explicit_exceptions_do_not_replace_overlapping_sources(client):
    uid = create_user("studio-overrides", "position_engineering_engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    bindings = source_rows(uid)
    entry = {"permission_code": "carton_mark:read", "factory_id": "huakang-a", "department": "qc"}
    def edit(**delta):
        return preview(client, uid, draft_for(identity(client, uid), **delta))
    commit(client, uid, edit(add_overrides=[{**entry, "effect": "allow"}]))
    allow, = identity(client, uid)["overrides"]
    deny_plan = edit(add_overrides=[{**entry, "effect": "deny"}])
    assert deny_plan["explicit_denials"]
    commit(client, uid, deny_plan)
    url = f"/api/iam/users/{uid}/access/explain"
    result = client.post(url, json=entry).json()
    assert not result["allowed"] and [s["key"] for s in result["steps"] if s["state"] == "hit"] == ["deny"]
    deny, = result["source_ids"]
    end = edit(end_override_ids=[deny])
    assert not end["explicit_denials"]
    commit(client, uid, end)
    result = client.post(url, json=entry).json()
    assert result["allowed"] and result["source_ids"] == [allow["id"]]
    assert source_rows(uid) == bindings


def test_secondary_and_lifecycle_keep_main_and_recheck_kind(client):
    uid = create_user("studio-secondary", "position_engineering_engineer", "huakang-a", "engineering")
    person = confirm(client, uid)
    original, = source_rows(uid)
    before = source_rows(uid)[original]
    spec = {"org_unit_id": "huaxing", "department_code": "engineering", "official_position_title": "兼任工程主管",
        "is_primary": False, "assignment_type": "part_time", "role_bindings": [{"role_id": "position_engineering_supervisor",
            "department": "engineering", "factory_scope": {"kind": "selected", "factory_ids": ["huaxing"]}}]}
    commit(client, uid, preview(client, uid, action(client, uid, "add_assignment", new_assignment=spec)))
    secondary, = [a for a in identity(client, uid)["active_assignments_summary"] if not a["is_primary"]]
    rejected = client.post(f"/api/iam/users/{uid}/access-studio/preview", json=action(
        client, uid, "end_assignment", source_assignment_id=person["primary_assignment"]["id"]))
    assert rejected.status_code == 422
    commit(client, uid, preview(client, uid, action(client, uid, "end_assignment", source_assignment_id=secondary["id"])))
    commit(client, uid, preview(client, uid, action(client, uid, "freeze")))
    assert identity(client, uid)["employment_status"] == "frozen"
    commit(client, uid, preview(client, uid, action(client, uid, "unfreeze")))
    assert identity(client, uid)["employment_status"] == "active" and source_rows(uid)[original] == before
    commit(client, uid, preview(client, uid, action(client, uid, "leave")))
    departed = identity(client, uid)
    assert departed["employment_status"] == "left"
    assert source_rows(uid)[original][1]["state"] == "revoked"
    rehire = {**spec, "is_primary": True, "assignment_type": "regular", "role_bindings": []}
    plan = preview(client, uid, action(client, uid, "rehire", new_assignment=rehire))
    assert not plan["permission_diffs"]["added"]
    commit(client, uid, plan)
    rehired = identity(client, uid)
    assert rehired["employment_epoch"] > departed["employment_epoch"] and rehired["status"] == "active"
    assert source_rows(uid)[original][1]["state"] == "revoked"
