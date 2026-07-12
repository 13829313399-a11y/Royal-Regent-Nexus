import importlib
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch, authz_mode: str = "enforce"):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'system_auth_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

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


def make_avatar_png() -> bytes:
    image = Image.new("RGB", (64, 64), color=(13, 148, 136))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def login(client: TestClient, username: str, password: str = "123456"):
    ensure_test_user(username)
    if username == "admin" and password == "123456":
        password = ADMIN_TEST_PASSWORD
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


def create_scoped_permission_manager(
    username: str = "factory-permission-admin",
    factory_id: str = "huaxing",
    department: str = "engineering",
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    now = auth_service.now_text()
    user_id = f"user-{username}"
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=f"{factory_id}/{department} 权限管理员",
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        binding_id = f"{user_id}:factory_permission_admin:{factory_id}:{department}"
        db.add(
            auth_models.AuthUserRole(
                id=binding_id,
                user_id=user_id,
                role_id="factory_permission_admin",
                factory_id=factory_id,
                department=department,
            )
        )
        db.add(
            auth_models.AuthRoleBindingMetadata(
                user_role_id=binding_id,
                state="active",
                source_type="test",
                valid_from=now,
                valid_until="",
                reason="范围管理测试",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position="权限管理员",
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(auth_models.AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
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
        assert notifications[0]["target_factory_id"] == "huaxing"
        assert notifications[0]["target_department"] == "engineering"
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


def test_sales_business_supervisor_registration_recommends_quote_supervisor_role(monkeypatch):
    with make_client(monkeypatch) as client:
        payload = register_payload("sales-supervisor")
        payload.update({
            "display_name": "张赛英",
            "department": "sales-business",
            "position": "车间业务主管",
        })
        register_response = client.post("/api/auth/register", json=payload)
        assert register_response.status_code == 200

        login(client, "admin")
        roles_response = client.get("/api/system/roles")
        assert roles_response.status_code == 200
        sales_supervisor_role = next(
            role for role in roles_response.json() if role["id"] == "sales_customer_supervisor"
        )
        assert sales_supervisor_role["name"] == "车间业务主管"

        requests = client.get("/api/system/registration-requests?status=pending").json()
        request = next(item for item in requests if item["username"] == "sales-supervisor")
        assert request["recommended_role_ids"] == ["sales_customer_supervisor"]

        approve_response = client.post(
            f"/api/system/registration-requests/{request['id']}/approve",
            json={
                "role_assignments": [
                    {"role_id": "sales_customer_supervisor", "factory_id": "huaxing", "department": "sales-business"}
                ],
                "review_comment": "车间业务主管账号",
            },
        )
        assert approve_response.status_code == 200

        logout(client)
        profile = login(client, "sales-supervisor", "Strong123")
        assert "车间业务主管" in profile["roles"]
        assert "customer_price:read" in profile["permissions"]
        assert "customer_price:export_customer_quote" in profile["permissions"]
        assert profile["department_scopes"] == ["sales-business"]


def test_non_admin_cannot_use_system_user_management(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineer")

        assert client.get("/api/system/users").status_code == 403
        assert client.get("/api/system/registration-requests").status_code == 403
        assert client.get("/api/system/roles").status_code == 403


def test_user_list_includes_registration_contact_info(monkeypatch):
    with make_client(monkeypatch) as client:
        payload = register_payload("contact-user")
        payload["phone"] = "13811112222"
        payload["email"] = "contact@example.com"
        client.post("/api/auth/register", json=payload)

        login(client, "admin")
        response = client.get("/api/system/users")

        assert response.status_code == 200
        contact_user = next(user for user in response.json() if user["username"] == "contact-user")
        assert contact_user["phone"] == "13811112222"
        assert contact_user["email"] == "contact@example.com"


def test_system_user_list_uses_each_users_current_avatar(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineer")
        upload_response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("engineer.png", make_avatar_png(), "image/png")},
        )
        assert upload_response.status_code == 200
        logout(client)

        login(client, "admin")
        users_response = client.get("/api/system/users")
        assert users_response.status_code == 200
        engineer = next(user for user in users_response.json() if user["username"] == "engineer")
        avatar_url = engineer["avatar_url"]
        assert avatar_url.startswith(f"/api/system/users/{engineer['id']}/avatar?v=")

        avatar_response = client.get(avatar_url)
        assert avatar_response.status_code == 200
        assert avatar_response.headers["content-type"] == "image/png"
        assert avatar_response.headers["cache-control"] == "private, no-store"
        assert avatar_response.content.startswith(b"\x89PNG")

        logout(client)
        login(client, "engineer")
        assert client.get(avatar_url).status_code == 403


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
        assert last_admin_response.json()["detail"] == "不能停用最后一个集团超级管理员"


def test_scoped_manager_cannot_bypass_iam_with_registration_approval(monkeypatch):
    with make_client(monkeypatch) as client:
        huaxing = register_payload("scope-huaxing")
        huadeng = register_payload("scope-huadeng")
        huadeng["factory_id"] = "huadeng"
        high_risk = register_payload("scope-high-risk")
        assert client.post("/api/auth/register", json=huaxing).status_code == 200
        assert client.post("/api/auth/register", json=huadeng).status_code == 200
        assert client.post("/api/auth/register", json=high_risk).status_code == 200

        create_scoped_permission_manager()
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            db.add(auth_models.AuthRole(id="basic_reader", code="basic_reader", name="基础查看", description="普通权限测试"))
            read_permission = db.query(auth_models.AuthPermission).filter_by(code="molding_sample:read").one()
            db.add(
                auth_models.AuthRolePermission(
                    id=f"basic_reader:{read_permission.id}",
                    role_id="basic_reader",
                    permission_id=read_permission.id,
                )
            )
            db.commit()
        login(client, "factory-permission-admin")

        visible = client.get("/api/system/registration-requests?status=pending")
        assert visible.status_code == 200
        visible_by_username = {item["username"]: item for item in visible.json()}
        assert set(visible_by_username) == {"scope-huaxing", "scope-high-risk"}

        approved = client.post(
            f"/api/system/registration-requests/{visible_by_username['scope-huaxing']['id']}/approve",
            json={
                "role_assignments": [
                    {"role_id": "basic_reader", "factory_id": "huaxing", "department": "engineering"}
                ],
                "review_comment": "本厂工程岗位资料核对完成",
            },
        )
        assert approved.status_code == 200, approved.text

        high_risk_response = client.post(
            f"/api/system/registration-requests/{visible_by_username['scope-high-risk']['id']}/approve",
            json={
                "role_assignments": [
                    {"role_id": "admin", "factory_id": "huaxing", "department": "engineering"}
                ],
                "review_comment": "尝试直接授予管理员",
            },
        )
        assert high_risk_response.status_code == 403
        assert "权限申请" in high_risk_response.json()["detail"]

        with db_module.SessionLocal() as db:
            remote_request = db.query(auth_models.AuthRegistrationRequest).filter_by(username="scope-huadeng").one()
            remote_request_id = remote_request.id

        cross_scope_response = client.post(
            f"/api/system/registration-requests/{remote_request_id}/approve",
            json={
                "role_assignments": [
                    {"role_id": "engineer", "factory_id": "huadeng", "department": "engineering"}
                ],
                "review_comment": "尝试跨厂审批",
            },
        )
        assert cross_scope_response.status_code == 403


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


def test_registration_notifications_are_isolated_by_factory_and_department(monkeypatch):
    with make_client(monkeypatch) as client:
        huaxing_engineering = register_payload("registration-hx-engineering")
        huaxing_production = register_payload("registration-hx-production")
        huaxing_production["department"] = "production"
        huaxing_production["position"] = "生产文员"
        huadeng_engineering = register_payload("registration-hd-engineering")
        huadeng_engineering["factory_id"] = "huadeng"

        assert client.post("/api/auth/register", json=huaxing_engineering).status_code == 200
        assert client.post("/api/auth/register", json=huaxing_production).status_code == 200
        assert client.post("/api/auth/register", json=huadeng_engineering).status_code == 200

        login(client, "admin")
        notifications = {
            item["payload"]["registration_request_id"]: item
            for item in client.get("/api/system/notifications").json()
            if item["type"] == "user_registration"
        }
        requests = {
            item["username"]: item
            for item in client.get("/api/system/registration-requests?status=pending").json()
        }
        engineering_notification = notifications[requests["registration-hx-engineering"]["id"]]
        production_notification = notifications[requests["registration-hx-production"]["id"]]
        huadeng_notification = notifications[requests["registration-hd-engineering"]["id"]]
        assert engineering_notification["target_department"] == "engineering"
        assert production_notification["target_department"] == "production"
        assert huadeng_notification["target_factory_id"] == "huadeng"
        logout(client)

        create_scoped_permission_manager("notification-hx-engineering", "huaxing", "engineering")
        create_scoped_permission_manager("notification-hx-production", "huaxing", "production")
        create_scoped_permission_manager("notification-hd-engineering", "huadeng", "engineering")

        login(client, "notification-hx-engineering")
        visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert engineering_notification["id"] in visible_ids
        assert production_notification["id"] not in visible_ids
        assert huadeng_notification["id"] not in visible_ids
        assert client.patch(
            f"/api/system/notifications/{production_notification['id']}",
            json={"status": "read"},
        ).status_code == 403
        assert client.patch(
            f"/api/system/notifications/{huadeng_notification['id']}",
            json={"status": "handled"},
        ).status_code == 403


def test_notification_department_scope_is_observational_in_shadow_and_enforced_only_in_enforce(
    monkeypatch,
    caplog,
):
    with make_client(monkeypatch, authz_mode="shadow") as client:
        payload = register_payload("shadow-production-registration")
        payload["department"] = "production"
        payload["position"] = "生产文员"
        assert client.post("/api/auth/register", json=payload).status_code == 200

        login(client, "admin")
        notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["type"] == "user_registration"
        )
        logout(client)

        create_scoped_permission_manager("shadow-hx-engineering", "huaxing", "engineering")
        login(client, "shadow-hx-engineering")
        with caplog.at_level("WARNING", logger="app.services.system"):
            visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert notification["id"] in visible_ids
        assert any(
            "authz shadow mismatch" in record.message
            and f"notification={notification['id']}" in record.message
            for record in caplog.records
        )

    with make_client(monkeypatch, authz_mode="legacy") as client:
        payload = register_payload("legacy-production-registration")
        payload["department"] = "production"
        payload["position"] = "生产文员"
        assert client.post("/api/auth/register", json=payload).status_code == 200

        login(client, "admin")
        notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["type"] == "user_registration"
        )
        logout(client)

        create_scoped_permission_manager("legacy-hx-engineering", "huaxing", "engineering")
        login(client, "legacy-hx-engineering")
        visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert notification["id"] in visible_ids


def test_password_reset_notifications_follow_profile_scope_and_unmatched_are_superadmin_only(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_test_user("engineer")
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            profile = db.get(auth_models.EmployeeProfile, "user-engineer")
            if profile is None:
                db.add(
                    auth_models.EmployeeProfile(
                        user_id="user-engineer",
                        primary_factory_id="huaxing",
                        primary_department="engineering",
                        position="工程师",
                        phone="",
                        email="",
                        confirmation_status="confirmed",
                        source_registration_request_id="",
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                profile.primary_factory_id = "huaxing"
                profile.primary_department = "engineering"
                profile.updated_at = now
            db.commit()

        assert client.post(
            "/api/auth/password-reset-requests",
            json={
                "username": "engineer",
                "display_name": "华兴工程师",
                "contact": "13800000000",
                "note": "忘记密码",
            },
        ).status_code == 200
        assert client.post(
            "/api/auth/password-reset-requests",
            json={
                "username": "unknown-reset-user",
                "display_name": "未知账号",
                "contact": "13900000000",
                "note": "账号无法匹配",
            },
        ).status_code == 200

        login(client, "admin")
        reset_notifications = [
            item
            for item in client.get("/api/system/notifications").json()
            if item["type"] == "password_reset"
        ]
        matched_notification = next(
            item for item in reset_notifications if item["payload"]["username"] == "engineer"
        )
        unmatched_notification = next(
            item for item in reset_notifications if item["payload"]["username"] == "unknown-reset-user"
        )
        assert matched_notification["target_factory_id"] == "huaxing"
        assert matched_notification["target_department"] == "engineering"
        assert unmatched_notification["target_factory_id"] == "*"
        assert unmatched_notification["target_department"] == "system"
        logout(client)

        create_scoped_permission_manager("reset-hx-engineering", "huaxing", "engineering")
        create_scoped_permission_manager("reset-hx-production", "huaxing", "production")

        login(client, "reset-hx-engineering")
        visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert matched_notification["id"] in visible_ids
        assert unmatched_notification["id"] not in visible_ids
        logout(client)

        login(client, "reset-hx-production")
        visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert matched_notification["id"] not in visible_ids
        assert unmatched_notification["id"] not in visible_ids
        assert client.patch(
            f"/api/system/notifications/{matched_notification['id']}",
            json={"status": "read"},
        ).status_code == 403
        assert client.patch(
            f"/api/system/notifications/{unmatched_notification['id']}",
            json={"status": "handled"},
        ).status_code == 403


def test_unmatched_password_reset_keeps_legacy_visibility_until_enforce(monkeypatch):
    with make_client(monkeypatch, authz_mode="legacy") as client:
        assert client.post(
            "/api/auth/password-reset-requests",
            json={
                "username": "unknown-legacy-reset-user",
                "display_name": "历史未知账号",
                "contact": "13900000001",
                "note": "验证灰度兼容",
            },
        ).status_code == 200

        login(client, "admin")
        notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["type"] == "password_reset"
        )
        logout(client)

        create_scoped_permission_manager("legacy-reset-manager", "huaxing", "engineering")
        login(client, "legacy-reset-manager")
        visible_ids = {item["id"] for item in client.get("/api/system/notifications").json()}
        assert notification["id"] in visible_ids


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
