import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'iam_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(client: TestClient, username: str, password: str = "123456"):
    if username == "admin":
        password = ADMIN_TEST_PASSWORD
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def create_user(
    username: str,
    role_id: str,
    factory_id: str,
    department: str,
    *,
    display_name: str = "测试用户",
):
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    now = auth_service.now_text()
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            models.AuthUser(
                id=user_id,
                username=username,
                display_name=display_name,
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        binding_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        db.add(
            models.AuthUserRole(
                id=binding_id,
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.add(
            models.AuthRoleBindingMetadata(
                user_role_id=binding_id,
                state="active",
                source_type="test",
                source_id="",
                valid_from="",
                valid_until="",
                reason="测试账号",
                created_by_user_id="user-admin",
                approved_by_user_id="user-admin",
                revoked_by_user_id="",
                revoked_at="",
                revoke_reason="",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position="测试职位",
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(models.AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
        db.commit()
    return user_id


def test_admin_catalog_scope_and_user_access_contract(monkeypatch):
    with make_client(monkeypatch) as client:
        engineer_id = create_user("iam-engineer", "engineer", "huaxing", "engineering")
        login(client, "admin")

        catalog = client.get("/api/iam/permissions")
        assert catalog.status_code == 200, catalog.text
        assert any(item["code"] == "molding_sample:create" for item in catalog.json())
        export_permission = next(item for item in catalog.json() if item["code"] == "molding_sample:export")
        assert export_permission["risk_level"] == "high"
        cross_read_permission = next(
            item for item in catalog.json() if item["code"] == "molding_sample:cross_factory_read"
        )
        cross_cost_permission = next(
            item for item in catalog.json() if item["code"] == "molding_sample:cross_factory_cost_read"
        )
        assert cross_read_permission["risk_level"] == "high"
        assert cross_cost_permission["risk_level"] == "high"
        assert all({"module_code", "module_name", "action", "risk_level"} <= item.keys() for item in catalog.json())

        scopes = client.get("/api/iam/manageable-scopes")
        assert scopes.status_code == 200
        assert scopes.json()["is_super_admin"] is True
        assert scopes.json()["scopes"] == [
            {
                "factory_id": "*",
                "factory_name": "全部厂区",
                "department": "*",
                "department_name": "全部部门",
            }
        ]

        access = client.get(f"/api/iam/users/{engineer_id}/access")
        assert access.status_code == 200, access.text
        body = access.json()
        assert body["user"]["username"] == "iam-engineer"
        assert body["authorization_version"] == 1
        assert body["profile"]["primary_factory_id"] == "huaxing"
        assert body["role_bindings"][0]["role_id"] == "engineer"
        assert any(item["permission_code"] == "molding_sample:create" for item in body["effective_access"])

        roles = client.get("/api/iam/roles")
        assert roles.status_code == 200, roles.text
        engineer_role = next(item for item in roles.json() if item["id"] == "engineer")
        group_readonly_role = next(item for item in roles.json() if item["id"] == "group_molding_readonly")
        assert {"version", "is_protected", "binding_count", "permission_count"} <= engineer_role.keys()
        assert group_readonly_role["name"] == "集团啤办只读"
        role_access = client.get("/api/iam/roles/engineer/access")
        assert role_access.status_code == 200, role_access.text
        assert role_access.json()["id"] == "engineer"
        assert "molding_sample:create" in role_access.json()["permission_codes"]
        group_readonly_access = client.get("/api/iam/roles/group_molding_readonly/access")
        assert group_readonly_access.status_code == 200, group_readonly_access.text
        assert group_readonly_access.json()["permission_codes"] == ["molding_sample:cross_factory_read"]


def test_user_override_preview_commit_is_atomic_and_token_is_one_time(monkeypatch):
    with make_client(monkeypatch) as client:
        engineer_id = create_user("iam-override", "engineer", "huaxing", "engineering")
        login(client, "admin")

        preview = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "临时关闭开单权限",
                "overrides": [
                    {
                        "permission_code": "molding_sample:create",
                        "effect": "deny",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert preview.status_code == 200, preview.text
        preview_body = preview.json()
        assert preview_body["requires_approval"] is False
        assert preview_body["high_risk"] is False
        assert preview_body["diffs"][0]["before"] == "allow"
        assert preview_body["diffs"][0]["after"] == "deny"

        commit = client.post(
            f"/api/iam/users/{engineer_id}/access/commit",
            json={"preview_token": preview_body["preview_token"], "confirm_high_risk": False},
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["status"] == "committed"
        assert commit.json()["authorization_version"] == 2

        replay = client.post(
            f"/api/iam/users/{engineer_id}/access/commit",
            json={"preview_token": preview_body["preview_token"], "confirm_high_risk": False},
        )
        assert replay.status_code == 409

        access = client.get(f"/api/iam/users/{engineer_id}/access").json()
        deny = next(
            item for item in access["effective_access"]
            if item["permission_code"] == "molding_sample:create"
            and item["factory_id"] == "huaxing"
            and item["department"] == "engineering"
        )
        assert deny["effect"] == "deny"
        assert deny["allowed"] is False
        assert deny["source_type"] == "user_override"

        events = client.get(f"/api/iam/audit-events?target_user_id={engineer_id}")
        assert events.status_code == 200
        assert events.json()[0]["event_type"] == "permission_override_set"


def test_scoped_manager_cross_scope_change_creates_request_for_superadmin(monkeypatch):
    with make_client(monkeypatch) as client:
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            db.add(models.AuthRole(id="factory_iam_manager", code="factory_iam_manager", name="厂区权限管理员", description=""))
            db.add(
                models.AuthRoleMetadata(
                    role_id="factory_iam_manager",
                    version=1,
                    protected=0,
                    created_at=now,
                    updated_at=now,
                    updated_by_user_id="",
                )
            )
            for permission_code in ("system:access_manage", "system:access_request"):
                permission = db.query(models.AuthPermission).filter_by(code=permission_code).one()
                db.add(
                    models.AuthRolePermission(
                        id=f"factory_iam_manager:{permission.id}",
                        role_id="factory_iam_manager",
                        permission_id=permission.id,
                    )
                )
            db.commit()

        create_user("scoped-manager", "factory_iam_manager", "huaxing", "engineering", display_name="华兴权限管理员")
        target_id = create_user("remote-user", "engineer", "huadeng", "engineering", display_name="华登工程师")
        login(client, "scoped-manager")

        assert client.get(f"/api/iam/users/{target_id}/access").status_code == 403
        preview = client.post(
            f"/api/iam/users/{target_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "申请跨厂查看排产",
                "overrides": [
                    {
                        "permission_code": "injection_schedule:read",
                        "effect": "allow",
                        "factory_id": "huadeng",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["requires_approval"] is True

        commit = client.post(
            f"/api/iam/users/{target_id}/access/commit",
            json={"preview_token": preview.json()["preview_token"], "confirm_high_risk": False},
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["status"] == "pending_approval"
        request_id = commit.json()["request_id"]

        client.post("/api/auth/logout")
        login(client, "admin")
        approve = client.post(
            f"/api/iam/access-requests/{request_id}/approve",
            json={"reason": "确认业务需要"},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "approved"
        access = client.get(f"/api/iam/users/{target_id}/access").json()
        assert any(
            item["permission_code"] == "injection_schedule:read"
            and item["factory_id"] == "huadeng"
            and item["effect"] == "allow"
            for item in access["effective_access"]
        )


def test_last_superadmin_binding_cannot_be_revoked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin")
        access = client.get("/api/iam/users/user-admin/access").json()
        admin_binding = next(item for item in access["role_bindings"] if item["role_code"] == "admin")

        preview = client.post(
            "/api/iam/users/user-admin/access/preview",
            json={
                "base_revision": access["authorization_version"],
                "reason": "验证最后超级管理员保护",
                "role_bindings": [
                    {
                        "operation": "revoke",
                        "binding_id": admin_binding["id"],
                        "factory_id": "*",
                        "department": "system",
                    }
                ],
                "overrides": [],
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["high_risk"] is True

        missing_confirmation = client.post(
            "/api/iam/users/user-admin/access/commit",
            json={"preview_token": preview.json()["preview_token"], "confirm_high_risk": False},
        )
        assert missing_confirmation.status_code == 400

        protected = client.post(
            "/api/iam/users/user-admin/access/commit",
            json={"preview_token": preview.json()["preview_token"], "confirm_high_risk": True},
        )
        assert protected.status_code == 400
        assert "最后一个集团超级管理员" in protected.json()["detail"]

        unchanged = client.get("/api/iam/users/user-admin/access").json()
        assert unchanged["authorization_version"] == access["authorization_version"]
        assert any(item["id"] == admin_binding["id"] and item["state"] == "active" for item in unchanged["role_bindings"])


def test_role_template_preview_commit_updates_bound_user_revision(monkeypatch):
    with make_client(monkeypatch) as client:
        engineer_id = create_user("role-template-user", "engineer", "huaxing", "engineering")
        login(client, "admin")
        role_access = client.get("/api/iam/roles/engineer/access").json()
        desired_codes = sorted(set(role_access["permission_codes"]) | {"injection_schedule:read"})

        preview = client.post(
            "/api/iam/roles/engineer/access/preview",
            json={
                "base_version": role_access["version"],
                "reason": "工程师增加排产查看权限",
                "permission_codes": desired_codes,
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["affected_user_count"] == 1
        assert any(item["permission_code"] == "injection_schedule:read" for item in preview.json()["diffs"])

        commit = client.post(
            "/api/iam/roles/engineer/access/commit",
            json={
                "preview_token": preview.json()["preview_token"],
                "confirm_high_risk": preview.json()["high_risk"],
            },
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["status"] == "committed"
        assert commit.json()["authorization_version"] == role_access["version"] + 1

        updated_role = client.get("/api/iam/roles/engineer/access").json()
        assert "injection_schedule:read" in updated_role["permission_codes"]
        updated_user = client.get(f"/api/iam/users/{engineer_id}/access").json()
        assert updated_user["authorization_version"] == 2
