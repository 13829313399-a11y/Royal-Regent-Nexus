import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch, **env_overrides):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'auth_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    for name, value in env_overrides.items():
        monkeypatch.setenv(name, value)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def test_login_sets_http_only_session_cookie_and_me_returns_admin_rbac_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "HttpOnly" in login_response.headers["set-cookie"]
        assert "Secure" not in login_response.headers["set-cookie"]

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        me = me_response.json()
        assert me["username"] == "admin"
        assert me["display_name"] == "系统管理员"
        assert "系统管理员" in me["roles"]
        assert "system:user_manage" in me["permissions"]
        assert "*" in me["factory_scopes"]
        assert me["grants"] == [
            {
                "role_id": "admin",
                "role_name": "系统管理员",
                "factory_id": "*",
                "department": "system",
                "permissions": sorted(me["permissions"]),
                "data_scope": "all",
            }
        ]


def test_login_session_cookie_secure_flag_can_be_enabled_by_env(monkeypatch):
    with make_client(monkeypatch, SESSION_COOKIE_SECURE="true") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "Secure" in login_response.headers["set-cookie"]


def test_only_admin_default_account_is_seeded_and_trial_accounts_are_retired(monkeypatch):
    with make_client(monkeypatch) as client:
        admin_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert admin_response.status_code == 200
        admin_profile = admin_response.json()
        assert admin_profile["display_name"] == "系统管理员"
        assert "系统管理员" in admin_profile["roles"]
        assert "system:user_manage" in admin_profile["permissions"]
        assert admin_profile["factory_scopes"] == ["*"]

        retired_usernames = [
            "engineer",
            "supervisor",
            "manager",
            "carton_warehouse",
            "qa_inspector",
            "molding_clerk",
            "huaxing_molding_a_sales",
            "molding",
            "warehouse",
            "huaxing_buzzbee_sales",
        ]
        for retired_username in retired_usernames:
            retired_response = client.post(
                "/api/auth/login",
                json={"username": retired_username, "password": "123456"},
            )
            assert retired_response.status_code == 401

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            active_users = db.query(auth_models.AuthUser).filter(auth_models.AuthUser.status == "active").all()
            assert [user.username for user in active_users] == ["admin"]


def test_default_trial_login_self_heals_missing_seeded_user(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            db.query(auth_models.AuthUserRole).filter(auth_models.AuthUserRole.user_id == "user-admin").delete()
            db.query(auth_models.AuthUser).filter(auth_models.AuthUser.username == "admin").delete()
            db.commit()

        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        profile = login_response.json()
        assert profile["username"] == "admin"
        assert "system:user_manage" in profile["permissions"]


def test_default_admin_is_not_seeded_without_explicit_password(monkeypatch):
    with make_client(monkeypatch, SEED_ADMIN_PASSWORD="") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "123456"},
        )
        assert login_response.status_code == 401

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            default_users = db.query(auth_models.AuthUser).filter(auth_models.AuthUser.username == "admin").all()
            assert default_users == []
            assert db.get(auth_models.AuthRole, "admin") is not None
            assert db.query(auth_models.AuthPermission).filter_by(code="system:user_manage").count() == 1


def test_weak_seed_admin_password_is_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="SEED_ADMIN_PASSWORD"):
        with make_client(monkeypatch, SEED_ADMIN_PASSWORD="123456"):
            pass


def test_default_trial_accounts_can_be_disabled_without_disabling_roles(monkeypatch):
    with make_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
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


def test_production_login_cookie_is_secure_without_explicit_cookie_env(monkeypatch):
    with make_client(monkeypatch, APP_ENV="production", SESSION_COOKIE_SECURE="false") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "Secure" in login_response.headers["set-cookie"]


def test_wrong_password_and_missing_session_are_rejected(monkeypatch):
    with make_client(monkeypatch) as client:
        wrong_password_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "bad-password"},
        )
        assert wrong_password_response.status_code == 401

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401


def test_missing_username_login_still_runs_password_hash(monkeypatch):
    with make_client(monkeypatch) as client:
        auth_service = importlib.import_module("app.services.auth")
        original_hash_password = auth_service.hash_password
        hash_calls: list[tuple[str, str]] = []

        def recording_hash_password(password: str, salt: str) -> str:
            hash_calls.append((password, salt))
            return original_hash_password(password, salt)

        monkeypatch.setattr(auth_service, "hash_password", recording_hash_password)

        response = client.post(
            "/api/auth/login",
            json={"username": "not-a-real-user", "password": "bad-password"},
        )

        assert response.status_code == 401
        assert len(hash_calls) == 1


def test_repeated_failed_login_attempts_temporarily_lock_username_and_ip(monkeypatch):
    with make_client(monkeypatch) as client:
        for _ in range(10):
            response = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "bad-password"},
            )
            assert response.status_code == 401

        locked_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "bad-password"},
        )
        assert locked_response.status_code == 429
        assert locked_response.json()["detail"] == "登录失败次数过多，请 15 分钟后再试"

        correct_password_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert correct_password_response.status_code == 429


def test_login_and_registration_passwords_cannot_contain_chinese_characters(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Strong密码123"},
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


def test_register_flushes_new_user_before_registration_request(monkeypatch):
    with make_client(monkeypatch) as client:
        from sqlalchemy.orm import Session as OrmSession

        original_flush = OrmSession.flush
        flush_new_sets: list[set[str]] = []

        def recording_flush(self, objects=None):
            flush_new_sets.append({type(item).__name__ for item in self.new})
            return original_flush(self, objects)

        monkeypatch.setattr(OrmSession, "flush", recording_flush)

        register_response = client.post(
            "/api/auth/register",
            json={
                "username": "postgres-fk-order",
                "display_name": "Postgres FK Order",
                "password": "Strong123",
                "confirm_password": "Strong123",
                "phone": "13800000000",
                "email": "",
                "factory_id": "huaxing",
                "department": "engineering",
                "position": "工程师",
            },
        )

        assert register_response.status_code == 200
        assert flush_new_sets[0] == {"AuthUser"}


def test_password_reset_request_creates_admin_system_notification(monkeypatch):
    with make_client(monkeypatch) as client:
        reset_response = client.post(
            "/api/auth/password-reset-requests",
            json={
                "username": "admin",
                "display_name": "系统管理员",
                "contact": "13800000000",
                "note": "忘记密码，申请重置",
            },
        )

        assert reset_response.status_code == 200
        assert reset_response.json() == {
            "status": "submitted",
            "message": "密码重置申请已提交，请等待管理员核验处理",
        }

        client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_TEST_PASSWORD})
        notifications_response = client.get("/api/system/notifications")
        assert notifications_response.status_code == 200
        notifications = notifications_response.json()
        password_reset_notification = next(
            notification for notification in notifications if notification["type"] == "password_reset"
        )
        assert password_reset_notification["title"] == "密码重置待处理"
        assert password_reset_notification["target_permission"] == "system:user_manage"
        assert password_reset_notification["status"] == "unread"
        assert password_reset_notification["payload"]["username"] == "admin"
        assert password_reset_notification["payload"]["contact"] == "13800000000"
        assert password_reset_notification["payload"]["matched_user_id"] == "user-admin"


def test_password_reset_request_requires_account_and_contact(monkeypatch):
    with make_client(monkeypatch) as client:
        missing_username_response = client.post(
            "/api/auth/password-reset-requests",
            json={"username": "", "display_name": "张三", "contact": "13800000000", "note": ""},
        )
        assert missing_username_response.status_code == 400
        assert missing_username_response.json()["detail"] == "请输入需要重置密码的账号"

        missing_contact_response = client.post(
            "/api/auth/password-reset-requests",
            json={"username": "zhangsan", "display_name": "张三", "contact": "", "note": ""},
        )
        assert missing_contact_response.status_code == 400
        assert missing_contact_response.json()["detail"] == "请填写联系电话或邮箱"


def test_logout_clears_session_cookie(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert login_response.status_code == 200

        logout_response = client.post("/api/auth/logout")
        assert logout_response.status_code == 204
        assert "rr_session=" in logout_response.headers["set-cookie"]

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401
