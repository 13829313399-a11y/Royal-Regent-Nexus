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
        assert me["display_name"] == "肖科"
        assert "工程师" in me["roles"]
        assert "molding_sample:create" in me["permissions"]
        assert "huakang-a" in me["factory_scopes"]


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
