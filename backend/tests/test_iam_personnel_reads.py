"""HTTP contracts on an isolated, freshly seeded database."""
import importlib
from sqlalchemy import event, select
from test_iam_api import create_user, login
from test_iam_workspace import seed_sources
from test_position_reviews import client, employee


ROLE = "position_engineering_engineer"


def modules():
    return (importlib.import_module("app.db"), importlib.import_module("app.models.auth"))


def test_org_counts_are_scoped_before_filter_and_paging_and_count_each_person_once(client):
    first = create_user("facet-first", ROLE, "huakang-a", "engineering")
    create_user("facet-second", ROLE, "huakang-b", "engineering")
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        db.add(models.AuthUserRole(id="facet-extra", user_id=first, role_id=ROLE,
                                   factory_id="huakang-a", department="engineering"))
        db.commit()
    params = {"q": "facet-", "role_id": ROLE, "include_org_counts": True, "org_unit_id": "huakang-a",
              "department": "engineering", "page_size": 1}
    def fetch():
        result = client.get("/api/system/people", params=params)
        assert result.status_code == 200, result.text
        return result.json()
    visible = fetch()
    assert visible["total"] == 1 and [p["id"] for p in visible["items"]] == [first]
    assert {(r["org_unit_id"], r["count"]) for r in visible["org_counts"]} == {("huakang-a", 1), ("huakang-b", 1)}
    with dbm.SessionLocal() as db:
        management = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == "system:user_manage"))
        db.add(models.AuthUserPermissionOverride(id="hide-facet", user_id="user-admin", permission_id=management.id,
               effect="deny", status="active", factory_id="huakang-b", department="engineering"))
        db.commit()
    params["page"] = 2
    result = fetch()
    assert result["org_counts"] == [{"org_unit_id": "huakang-a", "department": "engineering", "count": 1}]
    assert result["total"] == 1 and result["items"] == []


def test_mixed_role_hashes_match_single_role_definitions_without_additional_sql(client):
    uid = create_user("mixed-definitions", ROLE, "huakang-a", "engineering")
    dbm, models = modules()
    personnel = importlib.import_module("app.services.iam_personnel")
    sources = importlib.import_module("app.services.identity_sources")
    with dbm.SessionLocal() as db:
        other = db.scalar(select(models.AuthRole.id).where(models.AuthRole.id != ROLE).order_by(models.AuthRole.id))
        assert other
        db.add(models.AuthUserRole(id="mixed-extra", user_id=uid, role_id=other,
                                   factory_id="huakang-a", department="engineering"))
        db.commit()
        expected = {r: sources.definition_hash(sources.role_definition(db, r)) for r in [ROLE, other]}
        inputs = personnel.AuthReadInputs(db, [uid])
        statements = []
        def on_sql(conn, cursor, statement, params, context, many):
            statements.append(statement)
        event.listen(dbm.engine, "before_cursor_execute", on_sql)
        try:
            assert personnel.current_role_hashes(inputs) == expected
            assert not statements
        finally:
            event.remove(dbm.engine, "before_cursor_execute", on_sql)


def test_scoped_members_deduplicate_sources_and_do_not_write(client):
    uid = create_user("double-engineer", ROLE, "huakang-a", "engineering")
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        for binding, factory in (("second", "huakang-b"), ("expired", "huakang-c")):
            db.add(models.AuthUserRole(id=binding, user_id=uid, role_id=ROLE,
                                       factory_id=factory, department="engineering"))
            db.flush()
            db.add(models.AuthRoleBindingMetadata(user_role_id=binding, source_type="historical",
                   state="active", valid_until="2000-01-01T00:00:00Z" if binding == "expired" else ""))
        db.commit()
    statements = []

    def on_sql(conn, cursor, statement, params, context, many):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            statements.append(statement)

    event.listen(dbm.engine, "before_cursor_execute", on_sql)
    try:
        members = client.get(f"/api/iam/roles/{ROLE}/members", params={"q": "double-engineer"}).json()
        assert members["total"] == 1 and not members["members_restricted"]
        assert {b["factory_id"] for b in members["items"][0]["bindings"]} == {"huakang-a", "huakang-b"}
        summaries = client.get("/api/iam/system-positions?include_member_counts=true").json()
        summary = next(item for item in summaries if item["id"] == ROLE)
        assert summary["scoped_binding_count"] == 2 and summary["scoped_member_count"] == 1
        people = client.get("/api/system/people", params={"q": "double-engineer", "role_id": ROLE,
                            "has_packages": "yes", "include": "access_summary"}).json()
        assert people["total"] == 1
        summary = people["items"][0]["access_summary"]
        assert len(summary["active_packages"]) == 2
        assert set(summary["effective_factories"]) >= {"huakang-a", "huakang-b"}
        assert summary["task_coverage_complete"]
        assert client.get(f"/api/system/users/{uid}/effective-access").json()["effective_permissions_grouped"]
        assert not statements
    finally:
        event.remove(dbm.engine, "before_cursor_execute", on_sql)
    with dbm.SessionLocal() as db:
        management = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == "system:user_manage"))
        db.add(models.AuthUserPermissionOverride(id="deny-one-factory", user_id="user-admin",
               permission_id=management.id, effect="deny", status="active",
               factory_id="huakang-b", department="engineering"))
        db.commit()
    assert client.get(f"/api/iam/roles/{ROLE}/members?q=double-engineer").json()["total"] == 0
    assert client.get(f"/api/system/users/{uid}/effective-access").status_code == 403
    tree = client.get("/api/system/organization-catalog?include=personnel_scope").json()
    branch = next(o for o in tree["organizations"] if o["id"] == "huakang-b")
    assert "engineering" not in {d["code"] for d in branch["departments"]}


def test_self_suggestions_remain_only_declaration_and_deny_is_effective(client):
    uid = employee(client)
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(models.AuthPermission).join(models.AuthRolePermission)
                          .where(models.AuthRolePermission.role_id == ROLE))
        code = permission.code
        db.add(models.AuthUserPermissionOverride(id="existing-deny", user_id=uid, permission_id=permission.id,
               effect="deny", status="active", factory_id="*", department="*", employment_epoch=1))
        db.commit()
    profile = client.get("/api/auth/me/position-profile").json()
    assert all(p["code"] != code for g in profile["effective_permissions_grouped"] for p in g["items"])
    assert [p["role_id"] for p in profile["current_packages"]] == [ROLE]
    public_ids = [p["role_id"] for p in profile["reference_packages"]]
    assert ROLE in public_ids
    assert not {"role-admin", "position_external_carton_warehouse_keeper"}.intersection(public_ids)
    assert all(set(p) == {"role_id", "name", "department_code", "description"} for p in profile["reference_packages"])
    current = profile["official_position"]
    for invalid in ({"requested_role_ids": ["role-admin"]}, {"requested_role_ids": [ROLE, ROLE]},
                    {"requested_role_ids": public_ids[:4]}, {"requested_factory_ids": ["group-management"]}):
        response = client.post("/api/auth/me/position-reviews", json={"declaration": {**current, **invalid}})
        assert response.status_code == 422
    refs = {"requested_role_ids": public_ids[:3], "requested_factory_ids": ["huakang-b"]}
    response = client.post("/api/auth/me/position-reviews", json={"declaration": {**current, **refs}})
    assert response.status_code == 200, response.text
    assert response.json()["changed"]
    after = client.get("/api/auth/me/position-profile").json()
    assert {k: after["open_review"]["declaration"][k] for k in refs} == refs
    assert after["current_packages"] == profile["current_packages"]
    assert after["effective_permissions_grouped"] == profile["effective_permissions_grouped"]
    assert after["official_position"] == current
    assert client.get(f"/api/iam/roles/{ROLE}/members").status_code == 403
    login(client, "admin")
    with dbm.SessionLocal() as db:
        extra = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == "molding_sample:supervisor_review"))
        db.add(models.AuthRolePermission(id="new-live-permission", role_id=ROLE, permission_id=extra.id))
        db.commit()
    members = client.get(f"/api/iam/roles/{ROLE}/members", params={"only_outdated": "true", "q": "position-clerk"}).json()
    assert members["total"] == members["outdated_total"] == 1
    assert members["items"][0]["bindings"][0]["version_outdated"]
    assert client.get(f"/api/system/users/{uid}/effective-access").json()["effective_permissions_grouped"] == profile["effective_permissions_grouped"]


def test_partial_count_preserves_other_buckets_and_directory(client, monkeypatch):
    uid = employee(client)
    login(client, "admin")
    seed_sources(uid, 1)
    history = {"state": "", "target_user_id": uid, "page_size": 100}
    oldest = client.get("/api/iam/workspace/tasks", params=history).json()
    newest = client.get("/api/iam/workspace/tasks", params={**history, "sort": "newest"}).json()
    assert [r["key"] for r in newest["items"]] == [r["key"] for r in reversed(oldest["items"])]
    service = importlib.import_module("app.services.iam_workspace")
    def unavailable(self):
        raise RuntimeError("simulated unavailable source")
    monkeypatch.setattr(service.Projection, "password", unavailable)
    data = client.get("/api/iam/workspace/tasks", params={"kind": "position", "include_bucket_counts": "true",
                      "target_user_id": uid, "state": "closed", "q": "position-clerk"}).json()
    assert not data["partial"] and data["visible_total"] == 0
    assert data["bucket_counts"]["position"] == data["bucket_counts"]["identity-change"] == 1
    assert data["bucket_counts"]["password-reset"] is None
    assert data["bucket_counts"]["registration"] == 0
    summary = client.get("/api/system/people", params={"q": "position-clerk", "include": "access_summary"}).json()
    assert not summary["items"][0]["access_summary"]["task_coverage_complete"]
    assert summary["items"][0]["access_summary"]["open_task"]["key"].endswith(":mixed-000")

def test_catalog_authority_cannot_read_members_or_global_counts(client):
    uid = create_user("catalog-only-manager", ROLE, "huakang-a", "engineering")
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        for index, code in enumerate(("system:access_manage", "system:permission_catalog_read")):
            permission = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == code))
            db.add(models.AuthUserPermissionOverride(id=f"catalog-{index}", user_id=uid, permission_id=permission.id,
                   effect="allow", status="active", factory_id="huakang-a", department="engineering"))
        db.commit()
    login(client, "catalog-only-manager")
    members = client.get(f"/api/iam/roles/{ROLE}/members").json()
    assert members["members_restricted"] and members["total"] is None and members["items"] == []
    for params in ({}, {"include_member_counts": "true"}):
        detail = client.get(f"/api/iam/roles/{ROLE}/access", params=params).json()
        assert detail["binding_count"] == 0 and detail["scoped_member_count"] is None
        roles = client.get("/api/iam/roles", params=params).json()
        assert all(r["binding_count"] == 0 and r["scoped_binding_count"] is None for r in roles)
