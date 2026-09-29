"""The access response exposes only the mode within its existing read boundary."""

import importlib

import pytest

from test_iam_api import create_user, login, make_client


@pytest.mark.parametrize("mode,status", [("legacy", "active"), ("v2", "active"), ("v2", "left"), (None, None)])
def test_access_identity_mode_preserves_existing_response(monkeypatch, mode, status):
    with make_client(monkeypatch) as client:
        target = create_user("identity-mode", "engineer", "huaxing", "engineering")
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            profile = db.get(models.EmployeeProfile, target)
            if mode is None:
                db.delete(profile)
            else:
                profile.identity_mode = mode
                profile.employment_status = status
            db.commit()

        login(client, "admin")
        response = client.get(f"/api/iam/users/{target}/access")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["identity_mode"] == (mode or "legacy")
        # Old clients still receive the same fields and types. No full identity
        # detail, assignment history or new read endpoint is added to this DTO.
        assert set(body) == {
            "identity_mode", "user", "profile", "authorization_version", "role_bindings",
            "overrides", "effective_access", "system_position_role_id", "system_position_role_name",
            "recommended_system_position_role_id", "legacy_role_count", "active_override_count",
            "cleanup_role_count", "cleanup_override_count",
        }
        assert body["user"]["id"] == target
        assert body["authorization_version"] == 1
        assert isinstance(body["role_bindings"], list)
        assert isinstance(body["overrides"], list)
        assert isinstance(body["effective_access"], list)
        if mode is None:
            assert body["profile"] is None
        else:
            # With no current assignment, V2 resolves no primary factory but
            # must remain V2 (including after leaving), never fall back to legacy.
            assert body["profile"]["primary_factory_id"] == ("" if mode == "v2" else "huaxing")
            assert "identity_mode" not in body["profile"]
        assert client.get(f"/api/iam/users/{target}/access").json() == body
        with db_module.SessionLocal() as db:
            assert db.get(models.AuthUserAuthorizationRevision, target).revision == 1
            profile = db.get(models.EmployeeProfile, target)
            assert (profile.identity_mode if profile else None) == mode


def test_access_manage_only_keeps_existing_read_scope_and_identity_denial(monkeypatch):
    with make_client(monkeypatch) as client:
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(code="system:access_manage").one()
            db.add(models.AuthRolePermission(
                id=f"position_engineering_engineer:{permission.id}",
                role_id="position_engineering_engineer", permission_id=permission.id,
            ))
            db.commit()
        create_user("mode-access-manager", "position_engineering_engineer", "huaxing", "engineering")
        local = create_user("mode-local", "engineer", "huaxing", "engineering")
        foreign = create_user("mode-foreign", "engineer", "huadeng", "engineering")

        login(client, "mode-access-manager")
        response = client.get(f"/api/iam/users/{local}/access")
        assert response.status_code == 200, response.text
        assert response.json()["identity_mode"] == "legacy"
        assert client.get(f"/api/iam/users/{foreign}/access").status_code == 403
        assert client.get(f"/api/system/users/{local}/identity").status_code == 403

        with db_module.SessionLocal() as db:
            db.get(models.EmployeeProfile, local).identity_mode = "v2"
            db.commit()
        # V2 access already requires the existing full-person reader permission.
        # Adding a display field must not turn this 403 into an authorized read.
        denied = client.get(f"/api/iam/users/{local}/access")
        assert denied.status_code == 403, denied.text
        assert "identity_mode" not in denied.json()
        assert client.get(f"/api/system/users/{local}/identity").status_code == 403

        login(client, "mode-foreign")
        assert client.get(f"/api/iam/users/{foreign}/access").status_code == 403
        client.cookies.clear()
        assert client.get(f"/api/iam/users/{local}/access").status_code == 401
