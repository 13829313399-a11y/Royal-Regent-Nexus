import importlib

import pytest

from test_internal_quote_api import make_client, login, ensure_user, create_payload, grant_user_permission


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_direct_owner_choices_and_all_assignment_paths_keep_factory_sales_edit_boundary(monkeypatch, authz_mode):
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    with make_client(monkeypatch) as client:
        for name in ("sales-a", "sales-b", "sales-denied", "sales-disabled"):
            ensure_user(name, "position_sales_business", "sales-business", "huakang-d")
        ensure_user("sales-foreign", "position_sales_business", "sales-business", "huakang-c")
        ensure_user("engineer-owner", "engineering_supervisor", "engineering", "huakang-d")
        ensure_user("wildcard-admin", "admin", "*", "*")
        grant_user_permission("sales-denied", "internal_quote:sales_edit", "sales-business", "huakang-d")
        dbm = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            db.get(models.AuthUser, "user-sales-disabled").status = "suspended"
            db.get(models.AuthUserPermissionOverride, "override-sales-denied-internal_quote-sales_edit").effect = "deny"
            db.commit()
        login(client, "creator-admin", "admin", "*", "*")
        url = "/api/internal-quotes/business-owners"
        options = client.get(url, params={"factory_id": "huakang-d", "workflow_mode": "direct_output"})
        assert options.status_code == 200, options.text
        ids = {item["id"] for item in options.json()}
        assert {"user-sales-a", "user-sales-b"} <= ids
        invalid = ["sales-denied", "sales-disabled", "sales-foreign", "engineer-owner", "wildcard-admin"]
        assert not ids.intersection(f"user-{name}" for name in invalid)
        payload = create_payload(suffix="DIRECT-OWNER", participating_sections=["sales", "engineering", "assembly"])
        payload.update(factory_id="huakang-d", workflow_mode="direct_output", business_owner_id="user-sales-a", business_owner_name="untrusted-name")
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        quote = response.json()
        assert quote["module_version"] == "v4" and quote["business_owner_name"] == "sales-a"
        for name in invalid:
            denied = client.post("/api/internal-quotes", json={**payload, "business_owner_id": f"user-{name}", "business_owner_name": "untrusted-name"})
            assert denied.status_code == 400, denied.text
            denied = client.patch(f"/api/internal-quotes/{quote['id']}", json={"revision": quote["header_revision"], "business_owner_id": f"user-{name}", "business_owner_name": "untrusted-name"})
            assert denied.status_code == 400, denied.text
        updated = client.patch(f"/api/internal-quotes/{quote['id']}", json={"revision": quote["header_revision"], "business_owner_id": "user-sales-b", "business_owner_name": "untrusted-name"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["business_owner_name"] == "sales-b"
        clone = {"quote_no": "OWNER-CLONE", "version_label": "V2", "business_owner_id": "user-sales-a", "business_owner_name": "untrusted-name"}
        cloned = client.post(f"/api/internal-quotes/{quote['id']}/clone", json=clone)
        assert cloned.status_code == 201, cloned.text
        assert cloned.json()["module_version"] == "v4" and cloned.json()["business_owner_name"] == "sales-a"
        wrong_factory = client.get(url, params={"factory_id": "huakang-c", "quote_id": quote["id"]})
        assert wrong_factory.status_code == 400
        with dbm.SessionLocal() as db:
            auth = importlib.import_module("app.services.auth")
            ctx = auth.build_auth_context(db, db.get(models.AuthUser, "user-sales-a"))
            assert not auth.can(ctx, "internal_quote:sales_review", "huakang-d", "sales-business")


@pytest.mark.parametrize("mode", ["section_review", "whole_quote_review"])
def test_legacy_owners_still_require_review_even_when_candidate_request_claims_direct_output(monkeypatch, mode):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login(client, "owner-admin", "admin", "*", "*")
        ensure_user("ordinary-owner", "position_sales_business", "sales-business")
        payload = create_payload(suffix="LEGACY-OWNER")
        payload["workflow_mode"] = mode
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        quote = response.json()
        choices = client.get("/api/internal-quotes/business-owners", params={"factory_id": "huaxing", "workflow_mode": "direct_output", "quote_id": quote["id"]})
        assert choices.status_code == 200, choices.text
        assert "user-ordinary-owner" not in {row["id"] for row in choices.json()}
        assert client.post("/api/internal-quotes", json={**payload, "business_owner_id": "user-ordinary-owner", "business_owner_name": "ordinary-owner"}).status_code == 400
        changed = client.patch(f"/api/internal-quotes/{quote['id']}", json={"revision": quote["header_revision"], "business_owner_id": "user-ordinary-owner", "business_owner_name": "ordinary-owner"})
        assert changed.status_code == 400, changed.text
        clone = {"quote_no": "CLONE-LEGACY", "version_label": "V2", "business_owner_id": "user-ordinary-owner", "business_owner_name": "ordinary-owner"}
        for requested_mode in (mode, None):
            denied = client.post(f"/api/internal-quotes/{quote['id']}/clone", json={**clone, "workflow_mode": requested_mode})
            assert denied.status_code == 400, denied.text
        upgraded = client.post(f"/api/internal-quotes/{quote['id']}/clone", json={**clone, "workflow_mode": "direct_output"})
        assert upgraded.status_code == 201, upgraded.text
        assert upgraded.json()["module_version"] == "v4"
