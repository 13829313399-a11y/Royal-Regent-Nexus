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
        assert cross_read_permission["requires_global_factory"] is True
        assert cross_read_permission["applicable_departments"] == ["*"]
        create_permission = next(item for item in catalog.json() if item["code"] == "molding_sample:create")
        assert create_permission["applicable_departments"] == ["engineering"]
        assert "工程部" in create_permission["scope_guidance"]
        assert all(
            {
                "module_code",
                "module_name",
                "action",
                "risk_level",
                "applicable_departments",
                "requires_global_factory",
                "scope_guidance",
            }
            <= item.keys()
            for item in catalog.json()
        )

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
        assert any(item["permission_code"] == "molding_sample:raw_material_write" for item in body["effective_access"])

        roles = client.get("/api/iam/roles")
        assert roles.status_code == 200, roles.text
        engineer_role = next(item for item in roles.json() if item["id"] == "engineer")
        group_readonly_role = next(item for item in roles.json() if item["id"] == "group_molding_readonly")
        observer_role = next(item for item in roles.json() if item["id"] == "molding_production_observer")
        admin_role = next(item for item in roles.json() if item["id"] == "admin")
        assert {
            "version",
            "is_protected",
            "binding_count",
            "permission_count",
            "applicable_departments",
            "requires_global_factory",
            "scope_guidance",
        } <= engineer_role.keys()
        assert engineer_role["applicable_departments"] == ["engineering"]
        assert group_readonly_role["name"] == "集团啤办只读"
        assert group_readonly_role["requires_global_factory"] is True
        assert observer_role["applicable_departments"] == ["production", "molding"]
        assert admin_role["requires_global_factory"] is True
        assert admin_role["applicable_departments"] == ["*"]
        role_access = client.get("/api/iam/roles/engineer/access")
        assert role_access.status_code == 200, role_access.text
        assert role_access.json()["id"] == "engineer"
        assert set(role_access.json()["permission_codes"]) == {
            "internal_quote:read",
            "internal_quote:create",
            "internal_quote:clone",
            "internal_quote:summary_read",
            "internal_quote:timeline_read",
            "internal_quote:engineering_edit",
            "molding_sample:read",
            "molding_sample:export",
            "molding_sample:create",
            "molding_sample:raw_material_write",
            "molding_sample:edit_draft",
            "molding_sample:delete_draft",
            "molding_sample:notification_read",
        }
        group_readonly_access = client.get("/api/iam/roles/group_molding_readonly/access")
        assert group_readonly_access.status_code == 200, group_readonly_access.text
        assert group_readonly_access.json()["permission_codes"] == ["molding_sample:cross_factory_read"]
        observer_access = client.get("/api/iam/roles/molding_production_observer/access")
        assert observer_access.status_code == 200, observer_access.text
        assert observer_access.json()["permission_codes"] == ["molding_sample:production_read"]
        molding_clerk_access = client.get("/api/iam/roles/molding_clerk/access")
        assert molding_clerk_access.status_code == 200, molding_clerk_access.text
        assert "molding_sample:edit_draft" not in molding_clerk_access.json()["permission_codes"]
        assert "molding_sample:delete_draft" not in molding_clerk_access.json()["permission_codes"]


def test_user_access_preview_rejects_inapplicable_scope_but_allows_cleanup(monkeypatch):
    with make_client(monkeypatch) as client:
        engineer_id = create_user("iam-scope-policy", "engineer", "huaxing", "engineering")
        login(client, "admin")

        for effect in ("allow", "deny"):
            invalid_override = client.post(
                f"/api/iam/users/{engineer_id}/access/preview",
                json={
                    "base_revision": 1,
                    "reason": "验证错范围权限被拒绝",
                    "overrides": [
                        {
                            "permission_code": "molding_sample:production_read",
                            "effect": effect,
                            "factory_id": "huaxing",
                            "department": "engineering",
                        }
                    ],
                },
            )
            assert invalid_override.status_code == 400, invalid_override.text
            assert "当前范围不生效" in invalid_override.json()["detail"]

        invalid_role = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "验证错范围角色被拒绝",
                "role_bindings": [
                    {
                        "operation": "add",
                        "role_id": "molding_production_observer",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert invalid_role.status_code == 400, invalid_role.text
        assert "当前范围不生效" in invalid_role.json()["detail"]

        invalid_role_update = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "验证更新角色时也拒绝错范围",
                "role_bindings": [
                    {
                        "operation": "update",
                        "binding_id": f"{engineer_id}:engineer:huaxing:engineering",
                        "role_id": "molding_production_observer",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert invalid_role_update.status_code == 400, invalid_role_update.text
        assert "当前范围不生效" in invalid_role_update.json()["detail"]

        invalid_global_role = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "验证跨厂角色必须使用全局范围",
                "role_bindings": [
                    {
                        "operation": "add",
                        "role_id": "group_molding_readonly",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert invalid_global_role.status_code == 400, invalid_global_role.text
        assert "全部厂区 / 全部部门" in invalid_global_role.json()["detail"]

        invalid_admin_role = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "验证超级管理员不能绑定到局部范围",
                "role_bindings": [
                    {
                        "operation": "add",
                        "role_id": "admin",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert invalid_admin_role.status_code == 400, invalid_admin_role.text
        assert "全部厂区 / 全部部门" in invalid_admin_role.json()["detail"]

        valid_role = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "工程师只读查看本厂生产进度",
                "role_bindings": [
                    {
                        "operation": "add",
                        "role_id": "molding_production_observer",
                        "factory_id": "huaxing",
                        "department": "production",
                    }
                ],
            },
        )
        assert valid_role.status_code == 200, valid_role.text
        assert valid_role.json()["diffs"] == [
            {
                "permission_code": "molding_sample:production_read",
                "factory_id": "huaxing",
                "department": "production",
                "before": "none",
                "after": "allow",
                "before_source": "default",
                "after_source": "role",
                "risk_level": "normal",
            }
        ]

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(code="molding_sample:production_read").one()
            now = auth_service.now_text()
            db.add(
                models.AuthUserPermissionOverride(
                    id="legacy-invalid-production-read",
                    user_id=engineer_id,
                    permission_id=permission.id,
                    effect="allow",
                    factory_id="huaxing",
                    department="engineering",
                    status="active",
                    valid_from="",
                    valid_until="",
                    reason="历史错范围授权",
                    source_type="legacy_import",
                    source_id="",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        cleanup = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 1,
                "reason": "清理历史错范围授权",
                "overrides": [
                    {
                        "permission_code": "molding_sample:production_read",
                        "effect": "inherit",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert cleanup.status_code == 200, cleanup.text
        cleanup_commit = client.post(
            f"/api/iam/users/{engineer_id}/access/commit",
            json={"preview_token": cleanup.json()["preview_token"], "confirm_high_risk": False},
        )
        assert cleanup_commit.status_code == 200, cleanup_commit.text
        assert cleanup_commit.json()["authorization_version"] == 2

        with db_module.SessionLocal() as db:
            db.add(
                models.AuthUserRole(
                    id="legacy-invalid-observer-binding",
                    user_id=engineer_id,
                    role_id="molding_production_observer",
                    factory_id="huaxing",
                    department="engineering",
                )
            )
            db.commit()

        revoke_cleanup = client.post(
            f"/api/iam/users/{engineer_id}/access/preview",
            json={
                "base_revision": 2,
                "reason": "撤销历史错范围角色",
                "role_bindings": [
                    {
                        "operation": "revoke",
                        "binding_id": "legacy-invalid-observer-binding",
                        "factory_id": "huaxing",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert revoke_cleanup.status_code == 200, revoke_cleanup.text
        revoke_commit = client.post(
            f"/api/iam/users/{engineer_id}/access/commit",
            json={"preview_token": revoke_cleanup.json()["preview_token"], "confirm_high_risk": False},
        )
        assert revoke_commit.status_code == 200, revoke_commit.text
        assert revoke_commit.json()["authorization_version"] == 3


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


def test_scoped_manager_cross_scope_change_requires_direct_superadmin_action(monkeypatch):
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
                        "permission_code": "carton_mark:read",
                        "effect": "allow",
                        "factory_id": "huadeng",
                        "department": "engineering",
                    }
                ],
            },
        )
        assert preview.status_code == 403, preview.text
        assert "集团超级管理员直接操作" in preview.json()["detail"]

        position_preview = client.post(
            f"/api/iam/users/{target_id}/system-position/preview",
            json={
                "base_revision": 1,
                "system_position_role_id": "position_engineering_engineer",
                "reason": "申请归类到工程师权限职位",
            },
        )
        assert position_preview.status_code == 403, position_preview.text
        assert "集团超级管理员直接操作" in position_preview.json()["detail"]

        with db_module.SessionLocal() as db:
            assert db.query(models.AuthAccessRequest).count() == 0


def test_system_position_access_manager_candidates_follow_position_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(
                code="system:access_manage"
            ).one()
            db.add(
                models.AuthRolePermission(
                    id=f"position_engineering_engineer:{permission.id}",
                    role_id="position_engineering_engineer",
                    permission_id=permission.id,
                )
            )
            db.commit()

        create_user(
            "position-access-manager",
            "position_engineering_engineer",
            "huaxing",
            "engineering",
        )
        local_target_id = create_user(
            "position-local-target",
            "position_sales_business",
            "huaxing",
            "sales-business",
        )
        foreign_target_id = create_user(
            "position-foreign-target",
            "position_sales_business",
            "huadeng",
            "sales-business",
        )

        login(client, "position-access-manager")
        own_scopes = client.get("/api/iam/manageable-scopes")
        assert own_scopes.status_code == 200, own_scopes.text
        assert {
            (item["factory_id"], item["department"])
            for item in own_scopes.json()["scopes"]
        } == {("huaxing", "*")}
        assert client.get(f"/api/iam/users/{local_target_id}/access").status_code == 200
        assert client.get(f"/api/iam/users/{foreign_target_id}/access").status_code == 403

        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleMetadata, "position_engineering_engineer")
            metadata.scope_mode = "cross_factory_operate"
            db.commit()

        login(client, "position-access-manager")
        cross_scopes = client.get("/api/iam/manageable-scopes")
        assert cross_scopes.status_code == 200, cross_scopes.text
        assert ("huadeng", "*") in {
            (item["factory_id"], item["department"])
            for item in cross_scopes.json()["scopes"]
        }
        assert client.get(f"/api/iam/users/{foreign_target_id}/access").status_code == 200


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
        assert role_access["is_system_position"] is False
        assert role_access["is_editable"] is True
        assert role_access["source"] == "database"
        assert role_access["scope_mode_locked"] is False
        assert role_access["definition_version"] == ""
        assert role_access["definition_hash"] == ""
        invalid_preview = client.post(
            "/api/iam/roles/engineer/access/preview",
            json={
                "base_version": role_access["version"],
                "reason": "验证不能把生产写权限混入工程师模板",
                "permission_codes": sorted(
                    set(role_access["permission_codes"]) | {"molding_sample:production_start"}
                ),
            },
        )
        assert invalid_preview.status_code == 400
        assert "范围不相容" in invalid_preview.json()["detail"]

        desired_codes = sorted(set(role_access["permission_codes"]) | {"carton_mark:read"})

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
        assert any(item["permission_code"] == "carton_mark:read" for item in preview.json()["diffs"])

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
        assert "carton_mark:read" in updated_role["permission_codes"]
        updated_user = client.get(f"/api/iam/users/{engineer_id}/access").json()
        assert updated_user["authorization_version"] == 2


def test_permission_catalog_supports_active_inactive_and_all(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        inactive_code = "carton_mark:review"

        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(
                code=inactive_code
            ).one()
            metadata = db.get(models.AuthPermissionMetadata, permission.id)
            metadata.status = "inactive"
            db.commit()

        default_active = client.get("/api/iam/permissions")
        explicit_active = client.get("/api/iam/permissions?status=active")
        inactive = client.get("/api/iam/permissions?status=inactive")
        all_permissions = client.get("/api/iam/permissions?status=all")
        invalid = client.get("/api/iam/permissions?status=unknown")

        assert default_active.status_code == 200, default_active.text
        assert explicit_active.status_code == 200, explicit_active.text
        assert inactive.status_code == 200, inactive.text
        assert all_permissions.status_code == 200, all_permissions.text
        assert invalid.status_code == 400
        assert inactive_code not in {item["code"] for item in default_active.json()}
        assert inactive_code not in {item["code"] for item in explicit_active.json()}
        assert {item["code"] for item in inactive.json()} == {inactive_code}
        assert len(all_permissions.json()) == 74
        inactive_item = next(
            item for item in all_permissions.json() if item["code"] == inactive_code
        )
        assert inactive_item["status"] == "inactive"

        access_kinds = {
            item["code"]: item["access_kind"] for item in all_permissions.json()
        }
        assert access_kinds["molding_sample:read"] == "read"
        assert access_kinds["molding_sample:create"] == "operate"
        assert access_kinds["molding_sample:dispatch"] == "operate"
        assert access_kinds["internal_quote:read"] == "read"
        assert access_kinds["internal_quote:create"] == "operate"


def test_system_position_get_contract_is_code_locked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin")
        response = client.get("/api/iam/system-positions")
        assert response.status_code == 200, response.text
        positions = response.json()
        assert len(positions) == 29
        assert all(item["is_system_position"] for item in positions)
        assert all(item["is_editable"] is False for item in positions)
        assert all(item["source"] == "code" for item in positions)
        assert all(item["scope_mode_locked"] is True for item in positions)
        assert all(item["definition_version"] == "fixed-v6" for item in positions)
        assert all(len(item["definition_hash"]) == 64 for item in positions)

        general_manager = next(
            item for item in positions if item["id"] == "position_general_manager"
        )
        assert general_manager["scope_mode"] == "cross_factory_operate"
        assert general_manager["permission_count"] == 67

        detail = client.get(
            "/api/iam/roles/position_general_manager/access"
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["is_editable"] is False
        assert detail.json()["source"] == "code"
        assert detail.json()["scope_mode_locked"] is True
        assert detail.json()["definition_hash"] == general_manager["definition_hash"]
        assert len(detail.json()["permission_codes"]) == 67
        assert not any(
            code.startswith("system:") for code in detail.json()["permission_codes"]
        )


def test_general_manager_cannot_use_iam_or_system_management_but_admin_can_assign_position(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        create_user(
            "iam-general-manager",
            "position_general_manager",
            "huaxing",
            "management",
            display_name="集团总经理",
        )
        target_user_id = create_user(
            "iam-position-target",
            "engineer",
            "huaxing",
            "engineering",
            display_name="职位分配目标",
        )

        login(client, "iam-general-manager")
        denied_gets = (
            "/api/iam/permissions?status=all",
            "/api/iam/system-positions",
            "/api/iam/roles/position_general_manager/access",
            "/api/iam/users/search?query=iam-position-target",
            f"/api/iam/users/{target_user_id}/access",
            "/api/iam/audit-events",
            "/api/system/users?status=active",
            "/api/system/positions",
        )
        for endpoint in denied_gets:
            response = client.get(endpoint)
            assert response.status_code == 403, (endpoint, response.text)

        denied_assignment = client.post(
            f"/api/iam/users/{target_user_id}/system-position/preview",
            json={
                "base_revision": 1,
                "system_position_role_id": "position_sales_business",
                "reason": "总经理不得分配权限职位",
            },
        )
        assert denied_assignment.status_code == 403, denied_assignment.text

        login(client, "admin")
        for endpoint in denied_gets:
            response = client.get(endpoint)
            assert response.status_code == 200, (endpoint, response.text)

        access_before = client.get(f"/api/iam/users/{target_user_id}/access")
        assert access_before.status_code == 200, access_before.text
        assert access_before.json()["profile"]["position"] == "测试职位"
        preview = client.post(
            f"/api/iam/users/{target_user_id}/system-position/preview",
            json={
                "base_revision": access_before.json()["authorization_version"],
                "system_position_role_id": "position_sales_business",
                "reason": "管理员分配固定业务权限职位",
            },
        )
        assert preview.status_code == 200, preview.text
        commit = client.post(
            f"/api/iam/users/{target_user_id}/system-position/commit",
            json={
                "preview_token": preview.json()["preview_token"],
                "confirm_high_risk": preview.json()["high_risk"],
            },
        )
        assert commit.status_code == 200, commit.text

        access_after = client.get(f"/api/iam/users/{target_user_id}/access")
        assert access_after.status_code == 200, access_after.text
        assert access_after.json()["system_position_role_id"] == "position_sales_business"
        assert access_after.json()["profile"]["position"] == "测试职位"


@pytest.mark.parametrize(
    "role_id",
    ["position_sales_manager", "position_general_manager"],
)
def test_system_position_template_preview_and_commit_are_rejected(
    monkeypatch,
    role_id,
):
    with make_client(monkeypatch) as client:
        login(client, "admin")
        role_access = client.get(f"/api/iam/roles/{role_id}/access").json()
        preview = client.post(
            f"/api/iam/roles/{role_id}/access/preview",
            json={
                "base_version": role_access["version"],
                "reason": "尝试在线修改代码固定职位",
                "permission_codes": role_access["permission_codes"],
                "scope_mode": role_access["scope_mode"],
            },
        )
        assert preview.status_code == 409, preview.text
        assert preview.json()["detail"] == "系统内置职位由代码固定维护，不能在线修改"

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        iam_service = importlib.import_module("app.services.iam")
        with db_module.SessionLocal() as db:
            historical_token, _ = iam_service._store_preview(
                db,
                actor_user_id="user-admin",
                target_type="role",
                target_id=role_id,
                base_revision=role_access["version"],
                payload={
                    "reason": "历史系统职位编辑预览",
                    "permission_codes": role_access["permission_codes"],
                    "permission_security": {},
                    "scope_mode": role_access["scope_mode"],
                    "name": None,
                    "description": None,
                    "active_binding_ids": [],
                },
                summary={"high_risk": False},
            )
            db.commit()

        commit = client.post(
            f"/api/iam/roles/{role_id}/access/commit",
            json={
                "preview_token": historical_token,
                "confirm_high_risk": True,
            },
        )
        assert commit.status_code == 409, commit.text
        assert commit.json()["detail"] == "系统内置职位由代码固定维护，不能在线修改"

        with db_module.SessionLocal() as db:
            historical_preview = db.query(models.AuthAuthorizationPreview).filter_by(
                target_type="role",
                target_id=role_id,
            ).one()
            assert historical_preview.consumed_at == ""


def test_flat_permission_union_keeps_foreign_cross_allow_but_respects_global_deny(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "flat-cross-scope",
            "position_engineering_engineer",
            "huaxing",
            "engineering",
        )
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleMetadata, "position_engineering_engineer")
            metadata.scope_mode = "cross_factory_read"
            permission = db.query(models.AuthPermission).filter_by(
                code="molding_sample:read"
            ).one()
            now = auth_service.now_text()
            db.add(
                models.AuthUserPermissionOverride(
                    id="flat-cross-home-deny",
                    user_id=user_id,
                    permission_id=permission.id,
                    effect="deny",
                    factory_id="huaxing",
                    department="*",
                    status="active",
                    valid_from="",
                    valid_until="",
                    reason="本厂禁止",
                    source_type="test",
                    source_id="",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        home_denied = login(client, "flat-cross-scope")
        assert "molding_sample:read" in home_denied["permissions"]

        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(
                code="molding_sample:read"
            ).one()
            now = auth_service.now_text()
            db.add(
                models.AuthUserPermissionOverride(
                    id="flat-cross-global-deny",
                    user_id=user_id,
                    permission_id=permission.id,
                    effect="deny",
                    factory_id="*",
                    department="*",
                    status="active",
                    valid_from="",
                    valid_until="",
                    reason="全厂禁止",
                    source_type="test",
                    source_id="",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        globally_denied = login(client, "flat-cross-scope")
        assert "molding_sample:read" not in globally_denied["permissions"]


@pytest.mark.parametrize("binding_change", ["add", "remove"])
def test_role_template_commit_rejects_changed_binding_snapshot(monkeypatch, binding_change):
    with make_client(monkeypatch) as client:
        if binding_change == "remove":
            changed_user_id = create_user(
                "binding-snapshot-remove",
                "engineer",
                "huaxing",
                "engineering",
            )
        login(client, "admin")
        role_access = client.get("/api/iam/roles/engineer/access").json()
        preview = client.post(
            "/api/iam/roles/engineer/access/preview",
            json={
                "base_version": role_access["version"],
                "reason": "验证绑定用户快照",
                "permission_codes": sorted(
                    set(role_access["permission_codes"]) | {"carton_mark:read"}
                ),
            },
        )
        assert preview.status_code == 200, preview.text

        if binding_change == "add":
            create_user(
                "binding-snapshot-add",
                "engineer",
                "huaxing",
                "engineering",
            )
        else:
            db_module = importlib.import_module("app.db")
            models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                binding = db.query(models.AuthUserRole).filter_by(
                    user_id=changed_user_id,
                    role_id="engineer",
                ).one()
                db.delete(binding)
                db.commit()

        commit = client.post(
            "/api/iam/roles/engineer/access/commit",
            json={
                "preview_token": preview.json()["preview_token"],
                "confirm_high_risk": preview.json()["high_risk"],
            },
        )
        assert commit.status_code == 409
        assert commit.json()["detail"] == "绑定用户已变化，请重新预览"


def test_system_position_preview_replaces_legacy_grants_and_overrides(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "legacy-position-user",
            "engineer",
            "huaxing",
            "engineering",
            display_name="旧工程账号",
        )
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            legacy_binding_id = f"{user_id}:group_molding_readonly:*:*"
            db.add(
                models.AuthUserRole(
                    id=legacy_binding_id,
                    user_id=user_id,
                    role_id="group_molding_readonly",
                    factory_id="*",
                    department="*",
                )
            )
            db.add(
                models.AuthRoleBindingMetadata(
                    user_role_id=legacy_binding_id,
                    state="active",
                    source_type="registration_default",
                    source_id="legacy-registration",
                    valid_from=now,
                    valid_until="",
                    reason="旧组合授权",
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
            permission = db.query(models.AuthPermission).filter_by(code="carton_mark:read").one()
            db.add(
                models.AuthUserPermissionOverride(
                    id="legacy-position-override",
                    user_id=user_id,
                    permission_id=permission.id,
                    effect="allow",
                    factory_id="huaxing",
                    department="engineering",
                    status="active",
                    valid_from=now,
                    valid_until="",
                    reason="旧单独授权",
                    source_type="manual",
                    source_id="",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        login(client, "admin")
        positions_response = client.get("/api/iam/system-positions")
        assert positions_response.status_code == 200, positions_response.text
        positions = positions_response.json()
        assert len(positions) == 29
        assert all(item["is_system_position"] for item in positions)
        assert [
            item["name"]
            for item in positions
            if item["position_department"] == "engineering"
        ] == ["经理", "主管", "工程师"]

        access = client.get(f"/api/iam/users/{user_id}/access").json()
        assert access["system_position_role_id"] == ""
        assert access["recommended_system_position_role_id"] == "position_engineering_engineer"
        assert access["legacy_role_count"] == 2
        assert access["active_override_count"] == 1

        preview_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": access["authorization_version"],
                "system_position_role_id": "position_engineering_engineer",
            },
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["before_role_ids"] == []
        assert preview["after_role_id"] == "position_engineering_engineer"
        assert preview["after_role_name"] == "工程师"
        assert preview["removed_role_count"] == 2
        assert preview["removed_override_count"] == 1

        commit_response = client.post(
            f"/api/iam/users/{user_id}/system-position/commit",
            json={
                "preview_token": preview["preview_token"],
                "confirm_high_risk": preview["high_risk"],
            },
        )
        assert commit_response.status_code == 200, commit_response.text
        assert commit_response.json()["status"] == "committed"
        assert commit_response.json()["authorization_version"] == 2

        updated = client.get(f"/api/iam/users/{user_id}/access").json()
        assert updated["system_position_role_id"] == "position_engineering_engineer"
        assert updated["system_position_role_name"] == "工程师"
        assert updated["legacy_role_count"] == 0
        assert updated["active_override_count"] == 0
        assert [
            item["role_id"]
            for item in updated["role_bindings"]
            if item["state"] == "active"
        ] == ["position_engineering_engineer"]
        assert all(item["state"] != "active" for item in updated["overrides"])

        with db_module.SessionLocal() as db:
            position_binding = db.query(models.AuthUserRole).filter_by(
                user_id=user_id,
                role_id="position_engineering_engineer",
            ).one()
            position_metadata = db.get(models.AuthRoleBindingMetadata, position_binding.id)
            legacy_metadata = db.get(models.AuthRoleBindingMetadata, legacy_binding_id)
            assert position_metadata.reason == "系统调整内置权限职位为工程部 · 工程师"
            assert legacy_metadata.revoke_reason == "系统调整内置权限职位为工程部 · 工程师"


def test_system_position_can_cross_profile_department_with_position_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "cross-department-position",
            "engineer",
            "huaxing",
            "engineering",
            display_name="工程资料生产权限账号",
        )
        login(client, "admin")
        access = client.get(f"/api/iam/users/{user_id}/access").json()

        preview_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": access["authorization_version"],
                "system_position_role_id": "position_production_clerk",
                "reason": "员工资料保留工程部，权限归类到生产文员",
            },
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["after_role_id"] == "position_production_clerk"
        assert any(item["department"] == "production" for item in preview["diffs"])

        commit_response = client.post(
            f"/api/iam/users/{user_id}/system-position/commit",
            json={
                "preview_token": preview["preview_token"],
                "confirm_high_risk": preview["high_risk"],
            },
        )
        assert commit_response.status_code == 200, commit_response.text

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            profile = db.get(models.EmployeeProfile, user_id)
            active_bindings = [
                binding
                for binding in db.query(models.AuthUserRole).filter_by(user_id=user_id).all()
                if (metadata := db.get(models.AuthRoleBindingMetadata, binding.id)) is None
                or metadata.state == "active"
            ]
            assert profile.primary_department == "engineering"
            assert [
                (binding.role_id, binding.factory_id, binding.department)
                for binding in active_bindings
            ] == [("position_production_clerk", "huaxing", "production")]

        client.post("/api/auth/logout")
        session = login(client, "cross-department-position")
        assert session["profile"]["primary_department"] == "engineering"
        assert session["roles"] == ["生产文员"]
        assert "molding_sample:production_read" in session["permissions"]
        assert "molding_sample:production_start" not in session["permissions"]
        assert "molding_sample:production_fillback" not in session["permissions"]
        assert "molding_sample:production_complete" not in session["permissions"]
        assert "molding_sample:create" not in session["permissions"]


def test_scoped_manager_cannot_assign_own_position_scope_to_out_of_scope_user(monkeypatch):
    with make_client(monkeypatch) as client:
        target_user_id = create_user(
            "unbound-engineering-target",
            "engineer",
            "huaxing",
            "engineering",
        )
        create_user(
            "production-position-manager",
            "department_permission_admin",
            "huaxing",
            "production",
        )

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            target_bindings = db.query(models.AuthUserRole).filter_by(user_id=target_user_id).all()
            for binding in target_bindings:
                metadata = db.get(models.AuthRoleBindingMetadata, binding.id)
                if metadata is not None:
                    db.delete(metadata)
                db.delete(binding)
            db.commit()

        login(client, "production-position-manager")
        response = client.post(
            f"/api/iam/users/{target_user_id}/system-position/preview",
            json={
                "base_revision": 1,
                "system_position_role_id": "position_production_clerk",
                "reason": "尝试给范围外工程用户授予本部门职位",
            },
        )
        assert response.status_code == 403, response.text
        assert "集团超级管理员直接操作" in response.json()["detail"]


def test_system_position_cleanup_revokes_future_dated_grants(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "future-position-cleanup",
            "position_engineering_engineer",
            "huaxing",
            "engineering",
            display_name="未来授权清理账号",
        )
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        future_binding_id = f"{user_id}:future-legacy-role"
        future_override_id = f"{user_id}:future-override"
        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            db.add(
                models.AuthUserRole(
                    id=future_binding_id,
                    user_id=user_id,
                    role_id="engineer",
                    factory_id="huaxing",
                    department="engineering",
                )
            )
            db.flush()
            db.add(
                models.AuthRoleBindingMetadata(
                    user_role_id=future_binding_id,
                    state="active",
                    source_type="manual",
                    source_id="",
                    valid_from="2999-01-01 00:00:00",
                    valid_until="",
                    reason="未来生效的旧角色",
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
            permission = db.query(models.AuthPermission).filter_by(code="carton_mark:read").one()
            db.add(
                models.AuthUserPermissionOverride(
                    id=future_override_id,
                    user_id=user_id,
                    permission_id=permission.id,
                    effect="allow",
                    factory_id="huaxing",
                    department="engineering",
                    status="active",
                    valid_from="2999-01-01 00:00:00",
                    valid_until="",
                    reason="未来生效的个人权限",
                    source_type="manual",
                    source_id="",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        login(client, "admin")
        access_response = client.get(f"/api/iam/users/{user_id}/access")
        assert access_response.status_code == 200, access_response.text
        access = access_response.json()
        assert access["system_position_role_id"] == "position_engineering_engineer"
        assert access["legacy_role_count"] == 0
        assert access["active_override_count"] == 0
        assert access["cleanup_role_count"] == 1
        assert access["cleanup_override_count"] == 1

        preview_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": access["authorization_version"],
                "system_position_role_id": "position_engineering_engineer",
            },
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["removed_role_count"] == 1
        assert preview["removed_override_count"] == 1

        commit_response = client.post(
            f"/api/iam/users/{user_id}/system-position/commit",
            json={
                "preview_token": preview["preview_token"],
                "confirm_high_risk": preview["high_risk"],
            },
        )
        assert commit_response.status_code == 200, commit_response.text

        with db_module.SessionLocal() as db:
            binding_metadata = db.get(models.AuthRoleBindingMetadata, future_binding_id)
            future_override = db.get(models.AuthUserPermissionOverride, future_override_id)
            assert binding_metadata.state == "revoked"
            assert future_override.status == "revoked"
            assert binding_metadata.revoke_reason == "系统清理内置权限职位历史授权，保留工程部 · 工程师"
            assert future_override.revoke_reason == "系统清理内置权限职位历史授权，保留工程部 · 工程师"

        updated = client.get(f"/api/iam/users/{user_id}/access").json()
        assert updated["system_position_role_id"] == "position_engineering_engineer"
        assert updated["cleanup_role_count"] == 0
        assert updated["cleanup_override_count"] == 0


def test_system_position_commit_rejects_role_template_version_drift(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "position-template-drift",
            "engineer",
            "huaxing",
            "engineering",
        )
        login(client, "admin")
        access = client.get(f"/api/iam/users/{user_id}/access").json()
        preview_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": access["authorization_version"],
                "system_position_role_id": "position_engineering_engineer",
                "reason": "验证职位模板版本漂移保护",
            },
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleMetadata, "position_engineering_engineer")
            metadata.version += 1
            db.commit()

        commit_response = client.post(
            f"/api/iam/users/{user_id}/system-position/commit",
            json={
                "preview_token": preview["preview_token"],
                "confirm_high_risk": preview["high_risk"],
            },
        )
        assert commit_response.status_code == 409
        assert "职位模板已变化" in commit_response.json()["detail"]


def test_iam_writes_fail_closed_when_sidecar_metadata_is_missing(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "missing-sidecar-guard",
            "engineer",
            "huaxing",
            "engineering",
        )
        login(client, "admin")
        access = client.get(f"/api/iam/users/{user_id}/access").json()
        preview_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": access["authorization_version"],
                "system_position_role_id": "position_engineering_engineer",
                "reason": "验证职位模板元数据缺失时安全拒绝",
            },
        )
        assert preview_response.status_code == 200, preview_response.text

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            db.delete(db.get(models.AuthRoleMetadata, "position_engineering_engineer"))
            db.commit()

        commit_response = client.post(
            f"/api/iam/users/{user_id}/system-position/commit",
            json={
                "preview_token": preview_response.json()["preview_token"],
                "confirm_high_risk": preview_response.json()["high_risk"],
            },
        )
        assert commit_response.status_code == 409
        assert "角色权限模板元数据缺失" in commit_response.json()["detail"]

        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            db.add(
                models.AuthRoleMetadata(
                    role_id="position_engineering_engineer",
                    version=1,
                    protected=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.delete(db.get(models.AuthUserAuthorizationRevision, user_id))
            db.commit()

        missing_revision_response = client.post(
            f"/api/iam/users/{user_id}/system-position/preview",
            json={
                "base_revision": 0,
                "system_position_role_id": "position_engineering_engineer",
                "reason": "验证用户授权版本元数据缺失时安全拒绝",
            },
        )
        assert missing_revision_response.status_code == 409
        assert "用户授权版本元数据缺失" in missing_revision_response.json()["detail"]


def test_expired_system_position_is_not_reported_as_current(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = create_user(
            "expired-system-position",
            "position_engineering_engineer",
            "huaxing",
            "engineering",
        )
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        binding_id = f"{user_id}:position_engineering_engineer:huaxing:engineering"
        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleBindingMetadata, binding_id)
            metadata.valid_until = "2000-01-01 00:00:00"
            db.commit()

        login(client, "admin")
        access_response = client.get(f"/api/iam/users/{user_id}/access")
        assert access_response.status_code == 200, access_response.text
        access = access_response.json()
        assert access["system_position_role_id"] == ""
        assert access["system_position_role_name"] == ""
        assert access["legacy_role_count"] == 0
        assert access["effective_access"] == []
