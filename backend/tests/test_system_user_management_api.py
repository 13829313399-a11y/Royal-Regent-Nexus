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
    database_url = f"sqlite:///{TEST_TMP_DIR / f'system_auth_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def register_payload(username: str = "zhangsan"):
    return {
        "username": username,
        "display_name": "张三",
        "password": "Strong123",
        "confirm_password": "Strong123",
        "phone": "13800000000",
        "email": "",
        "factory_id": "huaxing",
        "department": "engineering",
        "position": "工程师",
    }


def login(client: TestClient, username: str, password: str = "123456"):
    ensure_test_user(username)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def logout(client: TestClient):
    client.post("/api/auth/logout")


TEST_USER_SPECS = {
    "engineer": ("user-engineer", "华兴工程师", "engineer", "huaxing", "engineering"),
}


def ensure_test_user(username: str) -> None:
    if username == "admin" or username not in TEST_USER_SPECS:
        return

    user_id, display_name, role_id, factory_id, department = TEST_USER_SPECS[username]
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        user = db.get(auth_models.AuthUser, user_id)
        if user is None:
            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                auth_models.AuthUser(
                    id=user_id,
                    username=username,
                    display_name=display_name,
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=auth_service.now_text(),
                    updated_at=auth_service.now_text(),
                )
            )
        else:
            user.username = username
            user.display_name = display_name
            user.status = "active"
            user.updated_at = auth_service.now_text()

        user_role_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        if db.get(auth_models.AuthUserRole, user_role_id) is None:
            db.add(
                auth_models.AuthUserRole(
                    id=user_role_id,
                    user_id=user_id,
                    role_id=role_id,
                    factory_id=factory_id,
                    department=department,
                )
            )
        db.commit()


def test_registration_approval_notification_and_login_flow(monkeypatch):
    with make_client(monkeypatch) as client:
        register_response = client.post("/api/auth/register", json=register_payload())

        assert register_response.status_code == 200
        assert register_response.json() == {
            "status": "pending",
            "message": "账号申请已提交，请等待管理员审批",
        }

        pending_login_response = client.post(
            "/api/auth/login",
            json={"username": "zhangsan", "password": "Strong123"},
        )
        assert pending_login_response.status_code == 401
        assert pending_login_response.json()["detail"] == "账号申请正在审批中，请等待管理员开通"

        login(client, "admin")
        notifications_response = client.get("/api/system/notifications")
        assert notifications_response.status_code == 200
        notifications = notifications_response.json()
        assert len(notifications) == 1
        assert notifications[0]["type"] == "user_registration"
        assert notifications[0]["target_permission"] == "system:user_manage"
        assert notifications[0]["status"] == "unread"
        assert "张三" in notifications[0]["message"]

        requests_response = client.get("/api/system/registration-requests?status=pending")
        assert requests_response.status_code == 200
        requests = requests_response.json()
        assert len(requests) == 1
        assert requests[0]["username"] == "zhangsan"
        assert requests[0]["status"] == "pending"
        assert requests[0]["recommended_role_ids"] == ["engineer"]
        request_id = requests[0]["id"]

        approve_response = client.post(
            f"/api/system/registration-requests/{request_id}/approve",
            json={
                "role_assignments": [
                    {"role_id": "engineer", "factory_id": "huaxing", "department": "engineering"}
                ],
                "review_comment": "资料完整",
            },
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"

        notifications_after_approval = client.get("/api/system/notifications").json()
        assert notifications_after_approval[0]["status"] == "handled"
        assert notifications_after_approval[0]["handled_at"]

        logout(client)
        approved_profile = login(client, "zhangsan", "Strong123")
        assert approved_profile["username"] == "zhangsan"
        assert "molding_sample:create" in approved_profile["permissions"]
        assert approved_profile["factory_scopes"] == ["huaxing"]


def test_non_admin_cannot_use_system_user_management(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineer")

        assert client.get("/api/system/users").status_code == 403
        assert client.get("/api/system/registration-requests").status_code == 403
        assert client.get("/api/system/roles").status_code == 403


def test_reject_suspend_restore_and_last_admin_guard(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_test_user("engineer")
        client.post("/api/auth/register", json=register_payload("lisi"))
        login(client, "admin")

        request_id = client.get("/api/system/registration-requests?status=pending").json()[0]["id"]
        reject_response = client.post(
            f"/api/system/registration-requests/{request_id}/reject",
            json={"review_comment": "资料不完整"},
        )
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"

        logout(client)
        rejected_login = client.post("/api/auth/login", json={"username": "lisi", "password": "Strong123"})
        assert rejected_login.status_code == 401
        assert rejected_login.json()["detail"] == "账号申请未通过，原因：资料不完整"

        login(client, "admin")
        users = client.get("/api/system/users?status=active").json()
        engineer_user = next(user for user in users if user["username"] == "engineer")

        suspend_response = client.patch(
            f"/api/system/users/{engineer_user['id']}/status",
            json={"status": "suspended"},
        )
        assert suspend_response.status_code == 200
        assert suspend_response.json()["status"] == "suspended"

        logout(client)
        suspended_login = client.post("/api/auth/login", json={"username": "engineer", "password": "123456"})
        assert suspended_login.status_code == 401
        assert suspended_login.json()["detail"] == "账号已停用，请联系管理员"

        login(client, "admin")
        restore_response = client.patch(
            f"/api/system/users/{engineer_user['id']}/status",
            json={"status": "active"},
        )
        assert restore_response.status_code == 200
        assert restore_response.json()["status"] == "active"

        admin_user = next(user for user in client.get("/api/system/users?status=active").json() if user["username"] == "admin")
        last_admin_response = client.patch(
            f"/api/system/users/{admin_user['id']}/status",
            json={"status": "suspended"},
        )
        assert last_admin_response.status_code == 400
        assert last_admin_response.json()["detail"] == "不能停用最后一个系统管理员"


def test_rejected_registration_can_be_resubmitted_with_same_username(monkeypatch):
    with make_client(monkeypatch) as client:
        client.post("/api/auth/register", json=register_payload("resubmit-user"))
        login(client, "admin")

        first_request_id = client.get("/api/system/registration-requests?status=pending").json()[0]["id"]
        reject_response = client.post(
            f"/api/system/registration-requests/{first_request_id}/reject",
            json={"review_comment": "补充手机号"},
        )
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"
        logout(client)

        resubmitted_payload = register_payload("resubmit-user")
        resubmitted_payload.update(
            {
                "display_name": "张三二次提交",
                "password": "NewStrong123",
                "confirm_password": "NewStrong123",
                "phone": "13900000000",
                "position": "高级工程师",
            }
        )
        resubmit_response = client.post("/api/auth/register", json=resubmitted_payload)
        assert resubmit_response.status_code == 200
        assert resubmit_response.json()["status"] == "pending"

        pending_login_response = client.post(
            "/api/auth/login",
            json={"username": "resubmit-user", "password": "NewStrong123"},
        )
        assert pending_login_response.status_code == 401
        assert pending_login_response.json()["detail"] == "账号申请正在审批中，请等待管理员开通"

        login(client, "admin")
        pending_requests = client.get("/api/system/registration-requests?status=pending").json()
        resubmitted_request = next(item for item in pending_requests if item["username"] == "resubmit-user")
        assert resubmitted_request["id"] != first_request_id
        assert resubmitted_request["display_name"] == "张三二次提交"
        assert resubmitted_request["phone"] == "13900000000"
        assert resubmitted_request["position"] == "高级工程师"

        rejected_requests = client.get("/api/system/registration-requests?status=rejected").json()
        assert any(item["id"] == first_request_id for item in rejected_requests)

        notifications = client.get("/api/system/notifications").json()
        assert any(
            notification["type"] == "user_registration"
            and notification["status"] == "unread"
            and notification["payload"]["registration_request_id"] == resubmitted_request["id"]
            for notification in notifications
        )


def test_system_notification_access_is_limited_to_targeted_accounts(monkeypatch):
    with make_client(monkeypatch) as client:
        client.post("/api/auth/register", json=register_payload("wangwu"))
        login(client, "admin")
        notification_id = client.get("/api/system/notifications").json()[0]["id"]
        logout(client)

        login(client, "engineer")
        update_response = client.patch(
            f"/api/system/notifications/{notification_id}",
            json={"status": "handled"},
        )
        assert update_response.status_code == 403


def test_admin_can_reset_user_password_from_password_reset_notification(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_test_user("engineer")

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            engineer = db.get(auth_models.AuthUser, "user-engineer")
            salt, password_hash = auth_service.make_password_hash("OldStrong123")
            engineer.password_salt = salt
            engineer.password_hash = password_hash
            engineer.force_password_change = 0
            db.commit()

        request_response = client.post(
            "/api/auth/password-reset-requests",
            json={
                "username": "engineer",
                "display_name": "华兴工程师",
                "contact": "13800000000",
                "note": "忘记密码",
            },
        )
        assert request_response.status_code == 200

        login(client, "admin")
        password_reset_notification = next(
            notification
            for notification in client.get("/api/system/notifications").json()
            if notification["type"] == "password_reset"
        )

        reset_response = client.post(
            "/api/system/users/user-engineer/reset-password",
            json={"temporary_password": "123456", "notification_id": password_reset_notification["id"]},
        )
        assert reset_response.status_code == 200
        assert reset_response.json()["force_password_change"] is True

        handled_notification = next(
            notification
            for notification in client.get("/api/system/notifications").json()
            if notification["id"] == password_reset_notification["id"]
        )
        assert handled_notification["status"] == "handled"
        assert handled_notification["handled_at"]

        logout(client)
        old_password_login = client.post("/api/auth/login", json={"username": "engineer", "password": "OldStrong123"})
        assert old_password_login.status_code == 401

        temporary_password_login = client.post("/api/auth/login", json={"username": "engineer", "password": "123456"})
        assert temporary_password_login.status_code == 200
        assert temporary_password_login.json()["force_password_change"] is True
