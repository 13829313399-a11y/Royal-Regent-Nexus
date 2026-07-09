import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch, **env_overrides):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'auth_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    for name, value in env_overrides.items():
        monkeypatch.setenv(name, value)

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
        assert "Secure" not in login_response.headers["set-cookie"]

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
        assert me["grants"] == [
            {
                "role_id": "engineer",
                "role_name": "工程师",
                "factory_id": "huaxing",
                "department": "engineering",
                "permissions": [
                    "molding_sample:create",
                    "molding_sample:delete_draft",
                    "molding_sample:edit_draft",
                    "molding_sample:notification_read",
                    "molding_sample:read",
                ],
                "data_scope": "department",
            }
        ]


def test_login_session_cookie_secure_flag_can_be_enabled_by_env(monkeypatch):
    with make_client(monkeypatch, SESSION_COOKIE_SECURE="true") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "engineer", "password": "123456"},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "Secure" in login_response.headers["set-cookie"]


def test_huaxing_trial_accounts_are_seeded_without_legacy_default_users(monkeypatch):
    with make_client(monkeypatch) as client:
        expected_accounts = {
            "engineer": ("华兴工程师", "工程师", "molding_sample:create", ["huaxing"]),
            "supervisor": ("华兴工程主管", "工程主管", "molding_sample:supervisor_review", ["huaxing"]),
            "manager": ("华兴经理", "经理", "molding_sample:manager_review", ["huaxing"]),
            "carton_warehouse": ("华兴纸箱仓管", "纸箱仓管", "carton_mark:template_upload", ["huaxing"]),
            "qa_inspector": ("华兴QA检验员", "QA 检验员", "carton_mark:review", ["huaxing"]),
            "molding_clerk": ("华兴啤机部文员", "啤机部文员", "molding_sample:production_start", ["huaxing"]),
            "huaxing_molding_a_sales": ("华兴啤机车间 A 跟客业务", "车间业务跟客", "customer_price:export_customer_quote", ["huaxing"]),
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
            if username == "huaxing_molding_a_sales":
                assert profile["department_scopes"] == ["sales-business"]
            client.post("/api/auth/logout")

        for retired_username in ["molding", "warehouse", "huaxing_buzzbee_sales"]:
            retired_response = client.post(
                "/api/auth/login",
                json={"username": retired_username, "password": "123456"},
            )
            assert retired_response.status_code == 401


def test_default_trial_login_self_heals_missing_seeded_user(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            db.query(auth_models.AuthUserRole).filter(auth_models.AuthUserRole.user_id == "user-carton-warehouse").delete()
            db.query(auth_models.AuthUser).filter(auth_models.AuthUser.username == "carton_warehouse").delete()
            db.commit()

        login_response = client.post(
            "/api/auth/login",
            json={"username": "carton_warehouse", "password": "123456"},
        )

        assert login_response.status_code == 200
        profile = login_response.json()
        assert profile["username"] == "carton_warehouse"
        assert "carton_mark:template_upload" in profile["permissions"]


def test_default_trial_accounts_can_be_disabled_without_disabling_roles(monkeypatch):
    with make_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "123456"},
        )
        assert login_response.status_code == 401

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            default_users = db.query(auth_models.AuthUser).filter(
                auth_models.AuthUser.username.in_(["admin", "engineer", "carton_warehouse"])
            ).all()
            assert default_users == []
            assert db.get(auth_models.AuthRole, "admin") is not None
            assert db.query(auth_models.AuthPermission).filter_by(code="system:user_manage").count() == 1


def test_wrong_password_and_missing_session_are_rejected(monkeypatch):
    with make_client(monkeypatch) as client:
        wrong_password_response = client.post(
            "/api/auth/login",
            json={"username": "engineer", "password": "bad-password"},
        )
        assert wrong_password_response.status_code == 401

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401


def test_login_and_registration_passwords_cannot_contain_chinese_characters(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "engineer", "password": "Strong密码123"},
        )
        assert login_response.status_code == 400
        assert login_response.json()["detail"] == "密码不能包含中文，请使用英文、数字或符号"

        register_response = client.post(
            "/api/auth/register",
            json={
                "username": "zhongwen-password",
                "display_name": "中文密码",
                "password": "Strong密码123",
                "confirm_password": "Strong密码123",
                "phone": "13800000000",
                "email": "",
                "factory_id": "huaxing",
                "department": "engineering",
                "position": "工程师",
            },
        )
        assert register_response.status_code == 400
        assert register_response.json()["detail"] == "密码不能包含中文，请使用英文、数字或符号"


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
