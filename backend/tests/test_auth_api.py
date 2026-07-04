import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'auth_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def test_login_sets_http_only_session_cookie_and_me_returns_rbac_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "engineer", "password": "123456"},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "HttpOnly" in login_response.headers["set-cookie"]

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        me = me_response.json()
        assert me["username"] == "engineer"
        assert me["display_name"] == "华兴工程师"
        assert "工程师" in me["roles"]
        assert "molding_sample:create" in me["permissions"]
        assert "molding_sample:supervisor_review" not in me["permissions"]
        assert "molding_sample:manager_review" not in me["permissions"]
        assert "huaxing" in me["factory_scopes"]


def test_huaxing_trial_accounts_are_seeded_without_legacy_default_users(monkeypatch):
    with make_client(monkeypatch) as client:
        expected_accounts = {
            "engineer": ("华兴工程师", "工程师", "molding_sample:create", ["huaxing"]),
            "supervisor": ("华兴工程主管", "工程主管", "molding_sample:supervisor_review", ["huaxing"]),
            "manager": ("华兴经理", "经理", "molding_sample:manager_review", ["huaxing"]),
            "molding_clerk": ("华兴啤机部文员", "啤机部文员", "molding_sample:production_start", ["huaxing"]),
            "admin": ("系统管理员", "系统管理员", "system:user_manage", ["*"]),
        }

        for username, (display_name, role_name, permission, factory_scopes) in expected_accounts.items():
            login_response = client.post(
                "/api/auth/login",
                json={"username": username, "password": "123456"},
            )
            assert login_response.status_code == 200
            profile = login_response.json()
            assert profile["display_name"] == display_name
            assert role_name in profile["roles"]
            assert permission in profile["permissions"]
            assert profile["factory_scopes"] == factory_scopes
            client.post("/api/auth/logout")

        for retired_username in ["molding", "warehouse"]:
            retired_response = client.post(
                "/api/auth/login",
                json={"username": retired_username, "password": "123456"},
            )
            assert retired_response.status_code == 401


def test_wrong_password_and_missing_session_are_rejected(monkeypatch):
    with make_client(monkeypatch) as client:
        wrong_password_response = client.post(
            "/api/auth/login",
            json={"username": "engineer", "password": "bad-password"},
        )
        assert wrong_password_response.status_code == 401

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401


def test_logout_clears_session_cookie(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "manager", "password": "123456"},
        )
        assert login_response.status_code == 200

        logout_response = client.post("/api/auth/logout")
        assert logout_response.status_code == 204
        assert "rr_session=" in logout_response.headers["set-cookie"]

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401
