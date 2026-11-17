import base64
import json
from dataclasses import replace
from types import SimpleNamespace
import httpx2 as httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.api import indonesia_shipping as shipping
from app.core.config import settings
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.permission_codes import INDONESIA_SHIPPING_BUSINESS_PERMISSION_CODES


def user(actions=("read", "shipments_read"), factory="huaxing", department="sales-business"):
    codes = frozenset("indonesia_shipping:" + value for value in actions)
    grant = AuthGrantContext("shipping-reader", "印尼走货", factory, department, codes)
    return AuthContext("nexus-user-1", "tester", "测试人员", (), (), codes, (factory,), (department,), grants=(grant,))

@pytest.fixture
def client(monkeypatch):
    app = FastAPI(); app.include_router(shipping.router)
    actor = {"value": user(), "session": "test-session"}
    def current(request: Request):
        request.state.auth_session_id = actor["session"]
        if actor.get("revoked"): raise HTTPException(401, "会话已撤回")
        return actor["value"]
    app.dependency_overrides[get_current_user] = current
    app.dependency_overrides[shipping.get_db] = lambda: SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(shipping, "get_current_user", lambda request, db: current(request))
    monkeypatch.setattr(settings, "indonesia_shipping_upstreams", {"huaxing": "http://private-shipping:5180"})
    monkeypatch.setattr(settings, "indonesia_shipping_bridge_key", SecretStr("test-key-never-used-in-production-123456789"))
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path.startswith("/api/"):
            return httpx.Response(200, stream=httpx.ByteStream(b'{"items": []}'), headers={"content-type": "application/json", "set-cookie": "legacy=bad", "x-secret": "bad", "x-blob-version": "123"})
        return httpx.Response(200, text='<html><head></head><body>original app</body></html>', headers={"content-type": "text/html"})
    original = httpx.AsyncClient
    monkeypatch.setattr(shipping.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with TestClient(app) as test: yield test, actor, requests

def headers(actor):
    return {"X-Nexus-Shipping": "1", "X-Nexus-Shipping-Identity": shipping.identity_key(actor["value"], actor["session"])}

def test_blob_version_headers_survive_gateway(client):
    test, actor, requests = client
    actor["value"] = user(("read", "quotes_read", "quotes_write"))
    url = "/api/indonesia-shipping/huaxing/app/api/quotes"
    response = test.get(url, headers=headers(actor))
    assert response.headers["x-blob-version"] == "123"
    assert test.put(url, json=[], headers={**headers(actor), "X-Expected-Version": "123"}).status_code == 200
    assert requests[-1].headers["x-expected-version"] == "123"

def test_new_login_for_same_account_cannot_reuse_old_workspace(client):
    test, actor, requests = client
    old = headers(actor)
    actor["session"] = "new-session-same-person"
    response = test.get("/api/indonesia-shipping/huaxing/app/api/shipments", headers=old)
    assert response.status_code == 409
    assert response.headers["x-nexus-shipping-session"] == "invalid"
    assert not requests

@pytest.mark.parametrize("change,expected", [("revoke", 401), ("deny", 403), ("identity", 409)])
@pytest.mark.parametrize("method", ["POST", "GET", "HEAD"])
def test_upload_reauthenticates_after_receiving_body(client, monkeypatch, change, expected, method):
    test, actor, requests = client
    actor["value"] = user(("read", "shipments_read", "shipments_write"))
    original = Request.stream
    async def stream(request):
        async for chunk in original(request):
            yield chunk
        if change == "revoke": actor["revoked"] = True
        elif change == "deny": actor["value"] = user(("read",))
        else: actor["session"] = "replacement-session"
    monkeypatch.setattr(Request, "stream", stream)
    assert test.request(method, "/api/indonesia-shipping/huaxing/app/api/shipments", content=b"uploaded-content", headers=headers(actor)).status_code == expected
    assert not requests

@pytest.mark.parametrize("method,actions,expected", [
    ("GET", ("read", "products_read"), 403),
    ("GET", ("read", "products_read", "materials_read"), 200),
    ("DELETE", ("read", "products_read", "materials_read", "products_write"), 403),
    ("DELETE", ("read", "products_read", "materials_read", "products_write", "materials_write"), 200),
])
def test_product_material_composite_permissions(client, method, actions, expected):
    test, actor, _ = client
    actor["value"] = user(actions)
    assert test.request(method, "/api/indonesia-shipping/huaxing/app/api/products/by-code?code=X", headers=headers(actor)).status_code == expected

@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_canonical_scope_and_deny_every_mode(client, monkeypatch, mode):
    test, actor, requests = client; monkeypatch.setattr(settings, "authz_mode", mode)
    for wrong in (user(factory="huadeng"), user(department="production"), user(actions=())):
        actor["value"] = wrong
        assert test.get("/api/indonesia-shipping/huaxing/status").status_code == 403
    actor["value"] = replace(user(), overrides=(AuthOverrideContext("deny", "indonesia_shipping:read", "deny", "huaxing", "sales-business"),))
    assert test.get("/api/indonesia-shipping/huaxing/status").status_code == 403
    assert requests == []

def test_group_missing_and_v2_ceiling_fail_closed(client):
    test, actor, requests = client
    assert test.get("/api/indonesia-shipping/group/status").status_code == 422
    actor["value"] = user(factory="huadeng")
    assert test.get("/api/indonesia-shipping/huadeng/status").status_code == 503
    grant = replace(user().grants[0], factory_id="*", factory_ceiling=("huadeng",), assignment_id="v2")
    actor["value"] = replace(user(), grants=(grant,))
    assert test.get("/api/indonesia-shipping/huaxing/status").status_code == 403
    for wrong in (replace(user(), account_available=False), replace(user(), force_password_change=True)):
        actor["value"] = wrong
        assert test.get("/api/indonesia-shipping/huaxing/status").status_code == 403
    assert requests == []

def test_anonymous():
    app = FastAPI(); app.include_router(shipping.router)
    def anonymous(): raise HTTPException(401, "请先登录")
    app.dependency_overrides[get_current_user] = anonymous
    assert TestClient(app).get("/api/indonesia-shipping/huaxing/status").status_code == 401

def test_readonly_and_legacy_login_are_blocked(client):
    test, actor, requests = client
    for method, path in (("post", "shipments"), ("delete", "shipments/1"), ("get", "users"), ("get", "db"), ("post", "auth/login"), ("post", "users/me/password")):
        assert getattr(test, method)("/api/indonesia-shipping/huaxing/app/api/" + path, headers=headers(actor)).status_code == 403
    assert requests == []

def test_business_bits_do_not_grant_admin(client):
    test, actor, _ = client
    actor["value"] = user(tuple(code.split(":")[1] for code in INDONESIA_SHIPPING_BUSINESS_PERMISSION_CODES))
    session = test.get("/api/indonesia-shipping/huaxing/app/api/session").json()
    assert session["userbqrpower"] == session["usereditpower"] == "111111111"
    assert "usersManage" not in session and not session["databaseManage"]
    assert test.get("/api/indonesia-shipping/huaxing/app/api/db", headers=headers(actor)).status_code == 403
    actor["value"] = user(("read", "users_manage"))
    assert test.get("/api/indonesia-shipping/huaxing/app/api/users", headers=headers(actor)).status_code == 403
    assert test.get("/api/indonesia-shipping/huaxing/app/api/db", headers=headers(actor)).status_code == 403

def test_stale_identity_csrf_and_upload_limit(client, monkeypatch):
    test, actor, requests = client
    actor["value"] = user(("read", "shipments_read", "shipments_write")); endpoint = "/api/indonesia-shipping/huaxing/app/api/shipments"
    assert test.post(endpoint).status_code == 403
    assert test.post(endpoint, headers={**headers(actor), "Sec-Fetch-Site": "cross-site"}).status_code == 403
    old = headers(actor); actor["value"] = replace(actor["value"], id="different-user")
    assert test.post(endpoint, headers=old).status_code == 409
    monkeypatch.setattr(settings, "indonesia_shipping_max_upload_mb", 1)
    assert test.post(endpoint, content=b"x" * (1024 * 1024 + 1), headers=headers(actor)).status_code == 413
    assert requests == []

def test_server_only_token_and_forwarded_headers(client):
    test, actor, requests = client
    actor["value"] = replace(actor["value"], identity={"employment_epoch": 3})
    response = test.get("/api/indonesia-shipping/huaxing/app/api/shipments?q=001", headers={**headers(actor), "Authorization": "Bearer malicious", "Cookie": "rr_session=private"})
    assert response.status_code == 200 and response.json() == {"items": []}
    request = requests[-1]; assert request.url.host == "private-shipping" and request.url.query == b"q=001"
    assert "cookie" not in request.headers
    encoded = request.headers["authorization"].split()[1].split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert payload["sub"] == actor["value"].id and payload["nexus_factory"] == "huaxing"
    assert payload["nexus_employment_epoch"] == "3" and payload["nexus_display_name"] == "测试人员"
    assert "nexus_users_manage" not in payload
    assert "nexus_database_manage" not in payload
    assert payload["exp"] - payload["iat"] == 60
    assert "set-cookie" not in response.headers and "x-secret" not in response.headers
    assert "token" not in test.get("/api/indonesia-shipping/huaxing/app/api/session").json()

def test_nested_html_base_and_duplicate_config(client, monkeypatch):
    test, actor, requests = client
    response = test.get("/api/indonesia-shipping/huaxing/app/shipments/2026")
    assert response.status_code == 200
    assert '<base href="/api/indonesia-shipping/huaxing/app/">' in response.text and 'name="nexus-shipping-base"' in response.text
    assert response.headers["cache-control"] == "no-store" and response.headers["x-frame-options"] == "SAMEORIGIN"
    assert requests[-1].url.path == "/shipments/2026"
    monkeypatch.setattr(settings, "indonesia_shipping_upstreams", {"huaxing": "http://private-shipping:5180", "huadeng": "http://private-shipping:5180/"})
    assert test.get("/api/indonesia-shipping/huaxing/status").status_code == 503

@pytest.mark.parametrize("path", ["api/../users", "api/%2fusers", "api\\users", "api//users", "api/unknown", "api/auth/login", "api/users/me/password"])
def test_unknown_and_ambiguous_routes(path):
    with pytest.raises(HTTPException): shipping.required_action(path, "POST")


def test_time_driven_v2_identity_change_invalidates_old_workspace():
    before = replace(user(), identity={"employment_epoch": 1, "identity_version": 2, "effective_context_key": "assignment-a"})
    after = replace(before, identity={**before.identity, "effective_context_key": "assignment-b"})
    assert shipping.identity_key(before) != shipping.identity_key(after)


@pytest.mark.parametrize("factory", sorted(shipping.FACTORIES))
def test_every_factory_uses_its_own_endpoint_and_signed_identity(client, monkeypatch, factory):
    test, actor, requests = client
    monkeypatch.setattr(settings, "indonesia_shipping_upstreams", {f: f"http://shipping-{f}:5180" for f in shipping.FACTORIES})
    actor["value"] = user(("read", "shipments_read", "shipments_write"), factory=factory)
    assert test.get(f"/api/indonesia-shipping/{factory}/status").json()["factoryId"] == factory
    assert test.post(f"/api/indonesia-shipping/{factory}/app/api/shipments", json={}, headers=headers(actor)).status_code == 200
    request = requests[-1]
    assert request.url.host == f"shipping-{factory}"
    encoded = request.headers["authorization"].split()[1].split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert payload["nexus_factory"] == factory
    count = len(requests)
    for other in shipping.FACTORIES - {factory}:
        assert test.get(f"/api/indonesia-shipping/{other}/status").status_code == 403
    assert len(requests) == count


@pytest.mark.parametrize("actions", [("read", "users_manage"), ("read", "database_manage"),
    tuple(code.split(":")[1] for code in INDONESIA_SHIPPING_BUSINESS_PERMISSION_CODES)])
def test_retired_accounts_cannot_be_reenabled_by_old_or_admin_grants(client, actions):
    test, actor, requests = client
    actor["value"] = user(actions)
    for method, path in [("get", "users"), ("get", "users/me"), ("post", "users"),
                         ("put", "users/1"), ("delete", "users/1"), ("post", "users/1/password"),
                         ("post", "users/me/password")]:
        assert getattr(test, method)("/api/indonesia-shipping/huaxing/app/api/" + path, headers=headers(actor)).status_code == 403
    assert requests == []


@pytest.mark.parametrize("factory", sorted(shipping.FACTORIES))
@pytest.mark.parametrize("actions", [("read", "database_manage"),
    (*[code.split(":")[1] for code in INDONESIA_SHIPPING_BUSINESS_PERMISSION_CODES], "database_manage")])
def test_database_maintenance_is_retired_even_with_historical_grants(client, monkeypatch, factory, actions):
    test, actor, requests = client
    monkeypatch.setattr(settings, "indonesia_shipping_upstreams", {f: f"http://shipping-{f}:5180" for f in shipping.FACTORIES})
    actor["value"] = user(actions, factory=factory)
    assert not test.get(f"/api/indonesia-shipping/{factory}/app/api/session").json()["databaseManage"]
    for method, path in [("GET", "db"), ("HEAD", "db/customers"), ("POST", "db/customers"),
                         ("PUT", "db/customers/1"), ("PATCH", "db/settings/1"),
                         ("DELETE", "db/customers/1"), ("DELETE", "DB/customers?confirm=YES")]:
        assert test.request(method, f"/api/indonesia-shipping/{factory}/app/api/" + path, headers=headers(actor)).status_code == 403
    assert requests == []
    from app.services.permission_codes import APPLICATION_PERMISSION_CODES
    assert "indonesia_shipping:users_manage" not in APPLICATION_PERMISSION_CODES
    assert "indonesia_shipping:database_manage" not in APPLICATION_PERMISSION_CODES


@pytest.mark.parametrize("action", ["users_manage", "database_manage"])
def test_retired_permission_is_inactive_even_with_historical_active_metadata(action):
    from app.models.auth import AuthPermission, AuthPermissionMetadata
    from app.services import iam
    permission = AuthPermission(id="old-admin", code=f"indonesia_shipping:{action}", name="旧管理功能", description="历史授权")
    metadata = AuthPermissionMetadata(permission_id=permission.id, module_code="indonesia_shipping", action=action,
        risk_level="high", access_kind="write", scope_type="department", status="active", sort_order=0)
    assert iam._permission_out(permission, metadata).status == "inactive"
    assert iam._permission_out(permission, None).status == "inactive"
    assert iam._permission_status(None, permission) == "inactive"
