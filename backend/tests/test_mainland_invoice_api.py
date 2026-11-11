import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_invoice_api_auth_scope_templates_and_rollout(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "InvoiceTest123!")
    monkeypatch.setenv("AUTHZ_MODE", mode)
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    monkeypatch.setenv("MAINLAND_INVOICE_ENABLED", "true")
    monkeypatch.setenv("MAINLAND_INVOICE_TEMPLATE_DIR", str(tmp_path / "private"))
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    main = importlib.import_module("app.main")
    api = importlib.import_module("app.api.mainland_invoice")
    auth = importlib.import_module("app.services.auth")
    for factory, entries in api.TEMPLATES.items():
        for _, (_, name) in entries.items():
            file = tmp_path / "private" / factory / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"PK-test-private-" + factory.encode())

    with TestClient(main.app) as client:
        endpoint = "/api/mainland-invoices/context"
        template = "/api/mainland-invoices/templates/a-zuru"
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 401
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "admin", "password": "InvoiceTest123!"}).status_code == 200
        organization_catalog = client.get("/api/auth/organization-catalog")
        assert organization_catalog.status_code == 200
        for organization in organization_catalog.json()["organizations"]:
            if organization["id"] in api.TEMPLATES:
                assert {"code": "accounting", "name": "会计部", "revision": 1} in organization["departments"]
        permission_catalog = client.get("/api/iam/permissions")
        assert permission_catalog.status_code == 200
        invoice_permission = next(item for item in permission_catalog.json() if item["code"] == api.PERMISSION)
        assert invoice_permission["applicable_departments"] == ["accounting"]
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 200
        for factory, entries in api.TEMPLATES.items():
            response = client.get(endpoint, params={"factory_id": factory})
            assert response.status_code == 200
            assert response.json()["user_id"]
            assert response.json()["employment_epoch"] == 1
            assert set(response.json()["templates"].values()) == set(entries)
            assert "no-store" in response.headers["cache-control"]
            for key in entries:
                response = client.get(f"/api/mainland-invoices/templates/{key}", params={"factory_id": factory})
                assert response.content == b"PK-test-private-" + factory.encode()
                assert "no-store" in response.headers["cache-control"]
        for factory in ("group", "huakang-c", "huaxing", "huadeng", "xingxin", "../huakang-a"):
            assert client.get(endpoint, params={"factory_id": factory}).status_code == 422
        assert client.get("/api/mainland-invoices/templates/d-maxx", params={"factory_id": "huakang-a"}).status_code == 404
        assert client.get("/api/mainland-invoices/templates/unknown", params={"factory_id": "huakang-a"}).status_code == 404

        profile = client.get("/api/auth/me").json()
        permission = api.PERMISSION
        grant = auth.AuthGrantContext("test-invoice", "测试权限", "huakang-a", "accounting", frozenset({permission}))
        scoped = auth.AuthContext(
            id=profile["id"], username="admin", display_name="测试",
            roles=("test-invoice",), role_codes=("test-invoice",),
            permissions=frozenset({permission}), factory_scopes=("huakang-a",),
            department_scopes=("accounting",), grants=(grant,),
            active_permission_codes=frozenset({permission}), permission_catalog_loaded=True,
        )
        main.app.dependency_overrides[auth.get_current_user] = lambda: scoped
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).json()["user_id"] == scoped.id
        scoped = replace(scoped, identity={"employment_epoch": 2})
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).json()["employment_epoch"] == 2
        for factory in ("huakang-b", "huakang-d"):
            assert client.get(endpoint, params={"factory_id": factory}).status_code == 403
            assert client.get("/api/mainland-invoices/templates/b-trade", params={"factory_id": factory}).status_code == 403
        scoped = replace(scoped, grants=(replace(grant, department="sales-business"),))
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 403
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 403
        scoped = replace(scoped, grants=())
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 403
        if mode in ("legacy", "shadow", "enforce"):
            scoped = replace(scoped, grants=(grant,), active_permission_codes=frozenset())
            assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 403
            scoped = replace(scoped, active_permission_codes=frozenset({permission}),
                             overrides=(auth.AuthOverrideContext("deny", permission, "deny", "huakang-a", "accounting"),))
            assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 403
        main.app.dependency_overrides.clear()
        api.settings.mainland_invoice_enabled = False
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 503
        api.settings.mainland_invoice_enabled = True
        file = tmp_path / "private" / "huakang-a" / "华康A-zuru.xlsx"
        file.unlink()
        assert client.get(endpoint, params={"factory_id": "huakang-a"}).status_code == 503
        outside = tmp_path / "secret.xlsx"
        outside.write_bytes(b"not-allowed")
        file.symlink_to(outside)
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 503
        assert str(tmp_path) not in client.get(endpoint, params={"factory_id": "huakang-a"}).text
        # A non-symlink leaf directory must not conceal a symlink ancestor.
        file.unlink()
        file.write_bytes(b"PK-test-private-huakang-a")
        alias = tmp_path / "private-alias"
        alias.symlink_to(tmp_path / "private", target_is_directory=True)
        api.settings.mainland_invoice_template_dir = str(alias)
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 503
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "alias").symlink_to(tmp_path, target_is_directory=True)
        api.settings.mainland_invoice_template_dir = str(nested / "alias" / "private")
        assert client.get(template, params={"factory_id": "huakang-a"}).status_code == 503
        assert str(tmp_path) not in client.get(endpoint, params={"factory_id": "huakang-a"}).text


def test_invoice_permission_is_catalogued_without_expanding_business_roles():
    from app.services.permission_codes import APPLICATION_PERMISSION_CODES, BUSINESS_PERMISSION_CODES
    assert "mainland_invoice:generate" in APPLICATION_PERMISSION_CODES
    assert "mainland_invoice:generate" not in BUSINESS_PERMISSION_CODES


def test_invoice_grant_preview_accepts_accounting_and_rejects_business(monkeypatch):
    from test_iam_api import create_user, login, make_client

    with make_client(monkeypatch) as client:
        user_id = create_user("invoice-scope-policy", "engineer", "huakang-a", "engineering")
        login(client, "admin")
        for department, status in (("accounting", 200), ("sales-business", 400), ("engineering", 400)):
            response = client.post(
                f"/api/iam/users/{user_id}/access/preview",
                json={
                    "base_revision": 1,
                    "reason": "验证大陆发票仅按会计部门授权",
                    "overrides": [{
                        "permission_code": "mainland_invoice:generate", "effect": "allow",
                        "factory_id": "huakang-a", "department": department,
                    }],
                },
            )
            assert response.status_code == status, response.text
            if status == 400:
                assert "当前范围不生效" in response.json()["detail"]
        # A successful preview is not a grant or a user/position migration.
        login(client, "invoice-scope-policy")
        assert client.get("/api/mainland-invoices/context", params={"factory_id": "huakang-a"}).status_code == 403


def test_accounting_catalog_seed_preserves_stopped_departments_and_revisions():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models.auth import AuthIamState
    from app.models.identity import IamOrgDepartment, IamOrgUnit
    from app.services.identity_catalog import FACTORIES, catalog, seed_identity_catalog

    engine = create_engine("sqlite:///:memory:")
    for table in (AuthIamState.__table__, IamOrgUnit.__table__, IamOrgDepartment.__table__):
        table.create(engine)
    with Session(engine) as db:
        seed_identity_catalog(db)
        for factory in FACTORIES:
            assert db.get(IamOrgDepartment, (factory, "accounting")).status == "active"
        assert db.get(IamOrgDepartment, ("group-management", "accounting")) is None
        stopped = db.get(IamOrgDepartment, ("huakang-a", "accounting"))
        stopped.status = "inactive"
        stopped.revision = 7
        db.flush()
        before = {(d.org_unit_id, d.department_code): (d.status, d.revision)
                  for d in db.scalars(select(IamOrgDepartment))}
        seed_identity_catalog(db)
        after = {(d.org_unit_id, d.department_code): (d.status, d.revision)
                 for d in db.scalars(select(IamOrgDepartment))}
        assert after == before
        organizations = {o["id"]: o for o in catalog(db)["organizations"]}
        assert all(d["code"] != "accounting" for d in organizations["huakang-a"]["departments"])
        assert {"code": "accounting", "name": "会计部", "revision": 1} in organizations["huakang-b"]["departments"]
    engine.dispose()
