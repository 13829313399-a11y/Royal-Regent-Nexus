import importlib
import sqlite3
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image


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


def make_avatar_png() -> bytes:
    image = Image.new("RGB", (480, 320), color=(13, 148, 136))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


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
        assert me["authorization_version"] == 1
        assert me["profile"]["confirmation_status"] == "needs_review"
        assert any(
            item["permission_code"] == "system:user_manage"
            and item["effect"] == "allow"
            and item["source_type"] == "superadmin"
            for item in me["effective_access"]
        )
        assert me["grants"] == [
            {
                "role_id": "admin",
                "role_name": "系统管理员",
                "factory_id": "*",
                "department": "*",
                "permissions": sorted(me["permissions"]),
                "data_scope": "all",
                "scope_mode": "own_factory",
                "read_permission_codes": [
                    code
                    for code in sorted(me["permissions"])
                    if code in {
                        "carton_mark:read",
                        "carton_procurement:read",
                        "customer_price:compare",
                        "customer_price:read",
                        "customer_order:audit_read",
                        "customer_order:read",
                        "internal_quote:baseline_read",
                        "internal_quote:read",
                        "internal_quote:summary_read",
                        "internal_quote:timeline_read",
                        "injection_scheduling:read",
                        "molding_sample:audit_read",
                        "molding_sample:cross_factory_cost_read",
                        "molding_sample:cross_factory_read",
                        "molding_sample:notification_read",
                        "molding_sample:production_read",
                        "molding_sample:read",
                        "system:audit_read",
                        "system:permission_catalog_read",
                    }
                ],
                "unrestricted_department": False,
            }
        ]


def test_sqlite_legacy_iam_columns_are_added_and_read_permissions_are_reconciled(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_path = TEST_TMP_DIR / f"legacy_iam_{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    db_module = importlib.import_module("app.db")
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE auth_permissions (
              id VARCHAR(64) PRIMARY KEY,
              code VARCHAR(128) NOT NULL
            );
            CREATE TABLE auth_permission_metadata (
              permission_id VARCHAR(64) PRIMARY KEY
            );
            CREATE TABLE auth_role_metadata (
              role_id VARCHAR(64) PRIMARY KEY
            );
            INSERT INTO auth_permissions (id, code) VALUES
              ('permission-read', 'molding_sample:read'),
              ('permission-compare', 'customer_price:compare'),
              ('permission-operate', 'molding_sample:create');
            INSERT INTO auth_permission_metadata (permission_id) VALUES
              ('permission-read'),
              ('permission-compare'),
              ('permission-operate');
            INSERT INTO auth_role_metadata (role_id) VALUES ('position_engineering_engineer');
            """
        )
        connection.commit()
    finally:
        connection.close()

    db_module.ensure_sqlite_legacy_columns()

    connection = sqlite3.connect(database_path)
    try:
        permission_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(auth_permission_metadata)")
        }
        role_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(auth_role_metadata)")
        }
        access_kinds = dict(
            connection.execute(
                "SELECT permission_id, access_kind FROM auth_permission_metadata"
            )
        )
        scope_mode = connection.execute(
            "SELECT scope_mode FROM auth_role_metadata "
            "WHERE role_id = 'position_engineering_engineer'"
        ).fetchone()[0]
    finally:
        connection.close()

    db_module.engine.dispose()
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    assert "access_kind" in permission_columns
    assert "scope_mode" in role_columns
    assert access_kinds == {
        "permission-read": "read",
        "permission-compare": "read",
        "permission-operate": "operate",
    }
    assert scope_mode == "own_factory"


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_auth_me_exposes_current_authz_mode_without_removing_existing_fields(monkeypatch, authz_mode):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        me_response = client.get("/api/auth/me")

        assert login_response.status_code == 200
        assert me_response.status_code == 200
        for response in (login_response, me_response):
            body = response.json()
            assert body["authz_mode"] == authz_mode
            assert {
                "id",
                "username",
                "display_name",
                "roles",
                "permissions",
                "factory_scopes",
                "department_scopes",
                "grants",
                "force_password_change",
                "avatar_url",
                "profile",
                "authorization_version",
                "effective_access",
            }.issubset(body)


def test_wildcard_superadmin_keeps_scoped_access_in_legacy_without_role_permission(monkeypatch):
    with make_client(
        monkeypatch,
        AUTHZ_MODE="legacy",
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        business_authz = importlib.import_module("app.services.business_authz")
        permission = "customer_price:export_customer_quote"
        superadmin = auth_service.AuthContext(
            id="user-admin",
            username="admin",
            display_name="系统管理员",
            roles=("系统管理员",),
            role_codes=("admin",),
            permissions=frozenset({permission}),
            factory_scopes=("*",),
            department_scopes=("system",),
            grants=(
                auth_service.AuthGrantContext(
                    role_id="admin",
                    role_code="admin",
                    role_name="系统管理员",
                    factory_id="*",
                    department="system",
                    permissions=frozenset(),
                    data_scope="all",
                    binding_id="user-admin:admin:*:system",
                ),
            ),
            active_permission_codes=frozenset({permission}),
        )

        assert auth_service.legacy_has_permission_in_scope(
            superadmin,
            permission,
            "huaxing",
            "sales-business",
        ) is False
        assert auth_service.authorization_decision(
            superadmin,
            permission,
            "huaxing",
            "sales-business",
        )[1] == "superadmin"
        assert auth_service.has_permission_in_scope(
            superadmin,
            permission,
            "huaxing",
            "sales-business",
        ) is True
        assert business_authz.has_permission_for_departments(
            superadmin,
            permission,
            "huaxing",
            ("sales-business", "engineering"),
        ) is True

        ordinary_user = auth_service.AuthContext(
            id="user-sales",
            username="sales",
            display_name="普通业务",
            roles=("普通业务",),
            role_codes=("sales",),
            permissions=frozenset(),
            factory_scopes=("huaxing",),
            department_scopes=("sales-business",),
            grants=(
                auth_service.AuthGrantContext(
                    role_id="sales",
                    role_code="sales",
                    role_name="普通业务",
                    factory_id="huaxing",
                    department="sales-business",
                    permissions=frozenset(),
                    binding_id="user-sales:sales:huaxing:sales-business",
                ),
            ),
            active_permission_codes=frozenset({permission}),
        )
        assert auth_service.has_permission_in_scope(
            ordinary_user,
            permission,
            "huaxing",
            "sales-business",
        ) is False
        assert business_authz.has_permission_for_departments(
            ordinary_user,
            permission,
            "huaxing",
            ("sales-business", "engineering"),
        ) is False


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


def test_sales_customer_supervisor_role_is_seeded_with_customer_price_permissions(monkeypatch):
    with make_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false"):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            role = db.get(auth_models.AuthRole, "sales_customer_supervisor")
            assert role is not None
            assert role.name == "车间业务主管"

            role_permissions = db.query(auth_models.AuthRolePermission).filter_by(
                role_id="sales_customer_supervisor",
            ).all()
            permission_ids = [item.permission_id for item in role_permissions]
            permissions = db.query(auth_models.AuthPermission).filter(
                auth_models.AuthPermission.id.in_(permission_ids),
            ).all()
            assert {permission.code for permission in permissions} == {
                "customer_price:read",
                "customer_price:import_internal_quote",
                "customer_price:export_customer_quote",
                "customer_price:compare",
                "customer_order:read",
                "customer_order:export",
                "customer_order:duplicate_confirm",
                "customer_order:audit_read",
                "internal_quote:read",
                "internal_quote:create",
                "internal_quote:clone",
                "internal_quote:header_edit",
                "internal_quote:summary_read",
                "internal_quote:timeline_read",
                "internal_quote:archive",
                "internal_quote:baseline_read",
                "internal_quote:baseline_manage",
                "internal_quote:customer_manage",
                "internal_quote:export",
                "internal_quote:final_submit",
                "internal_quote:final_approve",
                "internal_quote:self_review",
                "internal_quote:sales_edit",
                "internal_quote:sales_review",
                "internal_quote:reference_manage",
            }


def test_seed_preserves_existing_account_role_template_and_additional_binding(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            admin = db.get(auth_models.AuthUser, "user-admin")
            admin.status = "suspended"
            admin_role = db.get(auth_models.AuthRole, "admin")
            admin_role.name = "自定义管理员模板"
            removed_mapping_id = "admin:perm-system-user_manage"
            removed_mapping = db.get(auth_models.AuthRolePermission, removed_mapping_id)
            assert removed_mapping is not None
            db.delete(removed_mapping)
            extra_binding_id = "user-admin:engineer:huaxing:engineering"
            db.add(
                auth_models.AuthUserRole(
                    id=extra_binding_id,
                    user_id=admin.id,
                    role_id="engineer",
                    factory_id="huaxing",
                    department="engineering",
                )
            )
            db.commit()

            auth_service.seed_auth_defaults(db)

            assert db.get(auth_models.AuthUser, admin.id).status == "suspended"
            assert db.get(auth_models.AuthRole, "admin").name == "自定义管理员模板"
            assert db.get(auth_models.AuthRolePermission, removed_mapping_id) is None
            assert db.get(auth_models.AuthUserRole, extra_binding_id) is not None
            binding_metadata = db.get(auth_models.AuthRoleBindingMetadata, extra_binding_id)
            assert binding_metadata is not None
            assert binding_metadata.state == "active"
            assert binding_metadata.source_type == "legacy_import"


def test_seed_upgrades_existing_engineering_and_warehouse_roles_with_raw_material_write_once(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            permission = db.scalar(
                auth_service.select(auth_models.AuthPermission).where(
                    auth_models.AuthPermission.code == "molding_sample:raw_material_write"
                )
            )
            assert permission is not None

            marker = db.get(auth_models.AuthIamState, auth_service.RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER)
            assert marker is not None
            db.delete(marker)

            for role_id in auth_service.RAW_MATERIAL_WRITE_DEFAULT_ROLE_IDS:
                mapping = db.get(
                    auth_models.AuthRolePermission,
                    f"{role_id}:{permission.id}",
                )
                assert mapping is not None
                db.delete(mapping)
            db.commit()

            auth_service.seed_auth_defaults(db)

            for role_id in auth_service.RAW_MATERIAL_WRITE_DEFAULT_ROLE_IDS:
                assert db.get(auth_models.AuthRolePermission, f"{role_id}:{permission.id}") is not None
            assert db.get(auth_models.AuthIamState, auth_service.RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER) is not None


def test_seed_upgrades_existing_business_roles_with_internal_quote_p4_release_permissions_once(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            marker = db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_P4_RELEASE_GRANT_MARKER,
            )
            assert marker is not None
            db.delete(marker)

            expected_mappings = []
            for role_id, permission_codes in auth_service.INTERNAL_QUOTE_P4_RELEASE_ROLE_PERMISSIONS.items():
                for permission_code in permission_codes:
                    permission = db.scalar(
                        auth_service.select(auth_models.AuthPermission).where(
                            auth_models.AuthPermission.code == permission_code
                        )
                    )
                    assert permission is not None
                    mapping_id = f"{role_id}:{permission.id}"
                    mapping = db.get(auth_models.AuthRolePermission, mapping_id)
                    assert mapping is not None
                    db.delete(mapping)
                    expected_mappings.append(mapping_id)
            db.commit()

            auth_service.seed_auth_defaults(db)

            for mapping_id in expected_mappings:
                assert db.get(auth_models.AuthRolePermission, mapping_id) is not None
            assert db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_P4_RELEASE_GRANT_MARKER,
            ) is not None

            auth_service.seed_auth_defaults(db)
            assert db.query(auth_models.AuthRolePermission).filter(
                auth_models.AuthRolePermission.id.in_(expected_mappings)
            ).count() == len(expected_mappings)


def test_seed_upgrades_existing_business_supervisor_with_self_review_once(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            permission = db.scalar(
                auth_service.select(auth_models.AuthPermission).where(
                    auth_models.AuthPermission.code
                    == auth_service.INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE
                )
            )
            assert permission is not None

            marker = db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_SELF_REVIEW_GRANT_MARKER,
            )
            assert marker is not None
            db.delete(marker)

            mapping_id = f"sales_customer_supervisor:{permission.id}"
            mapping = db.get(auth_models.AuthRolePermission, mapping_id)
            assert mapping is not None
            db.delete(mapping)
            db.commit()

            auth_service.seed_auth_defaults(db)

            assert db.get(auth_models.AuthRolePermission, mapping_id) is not None
            assert db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_SELF_REVIEW_GRANT_MARKER,
            ) is not None

            auth_service.seed_auth_defaults(db)
            assert db.query(auth_models.AuthRolePermission).filter_by(id=mapping_id).count() == 1


def test_seed_upgrades_existing_engineering_supervisor_with_customer_manage_once(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            permission = db.scalar(
                auth_service.select(auth_models.AuthPermission).where(
                    auth_models.AuthPermission.code
                    == auth_service.INTERNAL_QUOTE_CUSTOMER_PERMISSION
                )
            )
            assert permission is not None

            marker = db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_CUSTOMER_GRANT_MARKER,
            )
            assert marker is not None
            db.delete(marker)
            db.add(
                auth_models.AuthIamState(
                    key="internal_quote_customer_grant_v1_completed",
                    value_json="{}",
                    updated_at=auth_service.now_text(),
                )
            )

            mapping_id = f"engineering_supervisor:{permission.id}"
            mapping = db.get(auth_models.AuthRolePermission, mapping_id)
            assert mapping is not None
            db.delete(mapping)
            db.commit()

            auth_service.seed_auth_defaults(db)

            assert db.get(auth_models.AuthRolePermission, mapping_id) is not None
            assert db.get(
                auth_models.AuthIamState,
                auth_service.INTERNAL_QUOTE_CUSTOMER_GRANT_MARKER,
            ) is not None

            auth_service.seed_auth_defaults(db)
            assert db.query(auth_models.AuthRolePermission).filter_by(id=mapping_id).count() == 1


def test_seed_reconciles_fixed_system_position_template_from_code(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        positions = importlib.import_module("app.services.system_positions")
        with db_module.SessionLocal() as db:
            role_id = "position_engineering_engineer"
            definition = positions.get_system_position(role_id)
            role = db.get(auth_models.AuthRole, role_id)
            metadata = db.get(auth_models.AuthRoleMetadata, role_id)
            baseline_version = metadata.version
            removed_permission = db.query(auth_models.AuthPermission).filter_by(
                code="molding_sample:read"
            ).one()
            removed_link = db.query(auth_models.AuthRolePermission).filter_by(
                role_id=role_id,
                permission_id=removed_permission.id,
            ).one()
            db.delete(removed_link)
            extra_permission = db.query(auth_models.AuthPermission).filter_by(
                code="system:user_manage"
            ).one()
            db.add(
                auth_models.AuthRolePermission(
                    id=f"{role_id}:{extra_permission.id}",
                    role_id=role_id,
                    permission_id=extra_permission.id,
                )
            )
            role.name = "管理员修改的职位名"
            role.description = "管理员修改的职位说明"
            metadata.scope_mode = "cross_factory_operate"
            db.commit()

            auth_service.seed_auth_defaults(db)

            updated = db.get(auth_models.AuthRole, role.id)
            updated_metadata = db.get(auth_models.AuthRoleMetadata, role_id)
            actual_permission_ids = {
                item.permission_id
                for item in db.query(auth_models.AuthRolePermission).filter_by(
                    role_id=role_id
                ).all()
            }
            expected_permission_ids = {
                db.query(auth_models.AuthPermission).filter_by(code=code).one().id
                for code in definition.permission_codes
            }
            assert updated.name == definition.name
            assert updated.description == definition.description
            assert updated_metadata.scope_mode == definition.scope_mode
            assert updated_metadata.version == baseline_version + 1
            assert actual_permission_ids == expected_permission_ids

            version_after_reconcile = updated_metadata.version
            auth_service.seed_auth_defaults(db)
            assert (
                db.get(auth_models.AuthRoleMetadata, role_id).version
                == version_after_reconcile
            )


def test_canonical_can_uses_deny_then_allow_then_role_and_scope(monkeypatch):
    with make_client(monkeypatch):
        auth_service = importlib.import_module("app.services.auth")
        grant = auth_service.AuthGrantContext(
            role_id="engineer",
            role_name="工程师",
            factory_id="huaxing",
            department="engineering",
            permissions=frozenset({"module:read"}),
            binding_id="binding-engineer",
            role_code="engineer",
        )
        allow = auth_service.AuthOverrideContext(
            id="override-allow",
            permission_code="module:update",
            effect="allow",
            factory_id="huaxing",
            department="engineering",
        )
        deny = auth_service.AuthOverrideContext(
            id="override-deny",
            permission_code="module:update",
            effect="deny",
            factory_id="huaxing",
            department="engineering",
        )
        context = auth_service.AuthContext(
            id="user-test",
            username="test",
            display_name="测试",
            roles=("工程师",),
            role_codes=("engineer",),
            permissions=frozenset(),
            factory_scopes=("huaxing",),
            department_scopes=("engineering",),
            grants=(grant,),
            overrides=(allow, deny),
            active_permission_codes=frozenset({"module:read", "module:update"}),
        )

        assert auth_service.can(context, "module:update", "huaxing", "engineering") is False
        assert auth_service.can(
            auth_service.replace(context, overrides=(allow,)),
            "module:update",
            "huaxing",
            "engineering",
        ) is True
        assert auth_service.can(context, "module:read", "huaxing", "engineering") is True
        assert auth_service.can(context, "module:read", "huadeng", "engineering") is False

        superadmin_grant = auth_service.AuthGrantContext(
            role_id="admin",
            role_name="系统管理员",
            role_code="admin",
            factory_id="*",
            department="*",
            permissions=frozenset(),
            binding_id="binding-superadmin",
        )
        wildcard_deny = auth_service.AuthOverrideContext(
            id="override-superadmin-deny",
            permission_code="module:read",
            effect="deny",
            factory_id="*",
            department="*",
        )
        superadmin_context = auth_service.replace(
            context,
            grants=(superadmin_grant,),
            overrides=(wildcard_deny,),
        )
        assert auth_service.can(
            superadmin_context,
            "module:read",
            "huaxing",
            "engineering",
        ) is False
        assert auth_service.can(
            auth_service.replace(superadmin_context, overrides=()),
            "module:read",
            "huaxing",
            "engineering",
        ) is True


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_system_position_scope_contract_is_consistent_across_authz_modes(monkeypatch, authz_mode):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        read_permission = "molding_sample:read"
        operate_permission = "molding_sample:create"

        def context_for(grant):
            return auth_service.AuthContext(
                id="user-position-scope",
                username="position-scope",
                display_name="内置职位范围测试",
                roles=(grant.role_name,),
                role_codes=(grant.role_id,),
                permissions=frozenset({read_permission, operate_permission}),
                factory_scopes=(grant.factory_id,),
                department_scopes=("*",),
                grants=(grant,),
                active_permission_codes=frozenset({read_permission, operate_permission}),
            )

        def grant(factory_id, scope_mode):
            return auth_service.AuthGrantContext(
                role_id="position_engineering_engineer",
                role_name="工程师",
                factory_id=factory_id,
                department="engineering",
                permissions=frozenset({read_permission, operate_permission}),
                scope_mode=scope_mode,
                read_permissions=frozenset({read_permission}),
                unrestricted_department=True,
            )

        anchored = context_for(grant("huaxing", "own_factory"))
        assert auth_service.has_permission_in_scope(
            anchored, operate_permission, "huaxing", "sales-business"
        )
        assert not auth_service.has_permission_in_scope(
            anchored, read_permission, "huadeng", "engineering"
        )

        wildcard_own = context_for(grant("*", "own_factory"))
        assert not auth_service.has_permission_in_scope(
            wildcard_own, read_permission, "huadeng", "engineering"
        )
        assert not auth_service.has_permission_in_scope(
            wildcard_own, operate_permission, "huadeng", "engineering"
        )

        wildcard_read = context_for(grant("*", "cross_factory_read"))
        assert auth_service.has_permission_in_scope(
            wildcard_read, read_permission, "huadeng", "engineering"
        )
        assert not auth_service.has_permission_in_scope(
            wildcard_read, operate_permission, "huadeng", "engineering"
        )

        wildcard_operate = context_for(grant("*", "cross_factory_operate"))
        assert auth_service.has_permission_in_scope(
            wildcard_operate, read_permission, "huadeng", "engineering"
        )
        assert auth_service.has_permission_in_scope(
            wildcard_operate, operate_permission, "huadeng", "engineering"
        )


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_system_position_production_task_read_is_the_only_own_factory_permission_expanded(
    monkeypatch,
    authz_mode,
):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        production_read = "molding_sample:production_read"
        unrelated_read = "carton_mark:read"
        production_write = "molding_sample:production_fillback"
        permissions = frozenset({production_read, unrelated_read, production_write})

        position_grant = auth_service.AuthGrantContext(
            role_id="position_qa_clerk",
            role_name="QA文员",
            factory_id="huaxing",
            department="qa",
            permissions=permissions,
            scope_mode="own_factory",
            read_permissions=frozenset({production_read, unrelated_read}),
            unrestricted_department=True,
        )
        context = auth_service.AuthContext(
            id="user-position-production-read",
            username="position-production-read",
            display_name="全厂生产任务只读",
            roles=(position_grant.role_name,),
            role_codes=(position_grant.role_id,),
            permissions=permissions,
            factory_scopes=("huaxing", "*"),
            department_scopes=("qa", "*"),
            grants=(position_grant,),
            active_permission_codes=permissions,
        )

        allowed, source_type, _, _ = auth_service.authorization_decision(
            context,
            production_read,
            "huadeng",
            "production",
        )
        assert allowed is True
        assert source_type == "role_binding_cross_read"
        assert auth_service.has_permission_in_scope(
            context, production_read, "huadeng", "production"
        )
        assert not auth_service.has_permission_in_scope(
            context, unrelated_read, "huadeng", "qa"
        )
        assert not auth_service.has_permission_in_scope(
            context, production_write, "huadeng", "production"
        )

        custom_grant = auth_service.replace(
            position_grant,
            role_id="custom_production_observer",
            unrestricted_department=False,
        )
        custom_context = auth_service.replace(context, grants=(custom_grant,))
        assert not auth_service.has_permission_in_scope(
            custom_context, production_read, "huadeng", "production"
        )

        deny = auth_service.AuthOverrideContext(
            id="deny-foreign-production-task-read",
            permission_code=production_read,
            effect="deny",
            factory_id="huadeng",
            department="*",
        )
        denied_context = auth_service.replace(context, overrides=(deny,))
        assert not auth_service.authorization_decision(
            denied_context, production_read, "huadeng", "production"
        )[0]
        assert auth_service.has_permission_in_scope(
            denied_context, production_read, "huadeng", "production"
        ) is (authz_mode != "enforce")


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_system_position_notifications_follow_factory_and_department_contract(
    monkeypatch,
    authz_mode,
):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        notification_permission = "molding_sample:notification_read"

        def context_for(grant):
            return auth_service.AuthContext(
                id=f"user-{grant.role_id}",
                username=grant.role_id,
                display_name=grant.role_name,
                roles=(grant.role_name,),
                role_codes=(grant.role_id,),
                permissions=grant.permissions,
                factory_scopes=("*", grant.factory_id),
                department_scopes=("*", grant.department),
                grants=(grant,),
                active_permission_codes=grant.permissions,
            )

        engineering_grant = auth_service.AuthGrantContext(
            role_id="position_engineering_engineer",
            role_name="工程师",
            factory_id="huaxing",
            department="engineering",
            permissions=frozenset(
                {notification_permission, "molding_sample:read"}
            ),
            scope_mode="cross_factory_read",
            read_permissions=frozenset(
                {notification_permission, "molding_sample:read"}
            ),
            unrestricted_department=True,
        )
        engineer = context_for(engineering_grant)
        assert auth_service.has_permission_in_scope(
            engineer, "molding_sample:read", "huadeng", "engineering"
        )
        assert auth_service.has_permission_in_scope(
            engineer, notification_permission, "huaxing", "engineering"
        )
        assert not auth_service.has_permission_in_scope(
            engineer, notification_permission, "huaxing", "production"
        )
        assert not auth_service.has_permission_in_scope(
            engineer, notification_permission, "huadeng", "engineering"
        )

        molding_grant = auth_service.AuthGrantContext(
            role_id="position_molding_supervisor",
            role_name="啤机主管",
            factory_id="huaxing",
            department="production",
            permissions=frozenset(
                {notification_permission, "molding_sample:production_read"}
            ),
            scope_mode="cross_factory_operate",
            read_permissions=frozenset(
                {notification_permission, "molding_sample:production_read"}
            ),
            unrestricted_department=True,
        )
        molding_supervisor = context_for(molding_grant)
        assert auth_service.has_permission_in_scope(
            molding_supervisor, notification_permission, "huadeng", "molding"
        )
        assert not auth_service.has_permission_in_scope(
            molding_supervisor, notification_permission, "huadeng", "engineering"
        )

        manager_grant = auth_service.replace(
            molding_grant,
            role_id="position_general_manager",
            role_name="总经理",
            department="management",
        )
        general_manager = context_for(manager_grant)
        assert auth_service.has_permission_in_scope(
            general_manager, notification_permission, "huadeng", "engineering"
        )
        assert auth_service.has_permission_in_scope(
            general_manager, notification_permission, "huadeng", "production"
        )


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_molding_sample_dispatch_fixed_positions_keep_source_factory_and_department_scope(
    monkeypatch,
    authz_mode,
):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        positions = importlib.import_module("app.services.system_positions")
        dispatch_permission = positions.MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE

        def context_for(role_id: str):
            definition = positions.get_system_position(role_id)
            assert definition is not None
            grant = auth_service.AuthGrantContext(
                role_id=definition.role_id,
                role_name=definition.name,
                factory_id="huakang-c",
                department=definition.department,
                permissions=frozenset(definition.permission_codes),
                scope_mode=definition.scope_mode,
                read_permissions=frozenset(),
                unrestricted_department=True,
            )
            return auth_service.AuthContext(
                id=f"user-{role_id}",
                username=role_id,
                display_name=definition.name,
                roles=(definition.name,),
                role_codes=(definition.role_id,),
                permissions=grant.permissions,
                factory_scopes=("huakang-c", "*"),
                department_scopes=(definition.department, "*"),
                grants=(grant,),
                active_permission_codes=grant.permissions,
            )

        for role_id in (
            "position_engineering_manager",
            "position_engineering_supervisor",
        ):
            engineering_user = context_for(role_id)
            assert auth_service.has_permission_in_scope(
                engineering_user,
                dispatch_permission,
                "huakang-c",
                "engineering",
            )
            assert not auth_service.has_permission_in_scope(
                engineering_user,
                dispatch_permission,
                "huakang-c",
                "management",
            )
            assert not auth_service.has_permission_in_scope(
                engineering_user,
                dispatch_permission,
                "huakang-d",
                "engineering",
            )

        general_manager = context_for("position_general_manager")
        assert auth_service.has_permission_in_scope(
            general_manager,
            dispatch_permission,
            "huakang-d",
            "engineering",
        )
        assert auth_service.has_permission_in_scope(
            general_manager,
            dispatch_permission,
            "huakang-d",
            "management",
        )

        for role_id in (
            "position_engineering_engineer",
            "position_molding_manager",
            "position_production_manager",
        ):
            assert not auth_service.has_permission_in_scope(
                context_for(role_id),
                dispatch_permission,
                "huakang-c",
                "engineering",
            )


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_general_manager_business_matrix_and_system_denials_across_authz_modes(
    monkeypatch,
    authz_mode,
):
    with make_client(
        monkeypatch,
        AUTHZ_MODE=authz_mode,
        AUTHZ_WRITES_ENABLED="false",
    ):
        auth_service = importlib.import_module("app.services.auth")
        business_authz = importlib.import_module("app.services.business_authz")
        permission_codes = importlib.import_module("app.services.permission_codes")
        positions = importlib.import_module("app.services.system_positions")

        definition = positions.get_system_position("position_general_manager")
        assert definition is not None
        grant = auth_service.AuthGrantContext(
            role_id=definition.role_id,
            role_name=definition.name,
            factory_id="huaxing",
            department="management",
            permissions=frozenset(definition.permission_codes),
            scope_mode=definition.scope_mode,
            read_permissions=frozenset(definition.permission_codes),
            unrestricted_department=True,
            binding_id="binding-general-manager",
            role_code=definition.role_id,
        )
        context = auth_service.AuthContext(
            id="user-general-manager",
            username="general-manager",
            display_name="集团总经理",
            roles=(definition.name,),
            role_codes=(definition.role_id,),
            permissions=frozenset(definition.permission_codes),
            factory_scopes=("*", "huaxing"),
            department_scopes=("*", "management"),
            grants=(grant,),
            profile=auth_service.AuthProfileContext(
                primary_factory_id="huaxing",
                primary_department="management",
                position="集团总经理",
                confirmation_status="confirmed",
            ),
            active_permission_codes=frozenset(
                permission_codes.APPLICATION_PERMISSION_CODES
            ),
        )

        representative_business_access = (
            ("molding_sample:cross_factory_read", "huadeng", "engineering"),
            ("molding_sample:cross_factory_cost_read", "huadeng", "engineering"),
            ("molding_sample:create", "huadeng", "engineering"),
            ("molding_sample:raw_material_write", "huadeng", "pmc-warehouse"),
            ("molding_sample:inventory_issue", "huaxing", "pmc-warehouse"),
            ("carton_mark:template_upload", "huadeng", "carton"),
            ("carton_mark:photo_upload", "huaxing", "qa"),
            ("internal_quote:read", "huadeng", "sales-business"),
            ("internal_quote:engineering_edit", "huadeng", "engineering"),
            ("internal_quote:molding_review", "huaxing", "molding"),
            ("customer_price:read", "huadeng", "sales-business"),
            ("customer_price:import_internal_quote", "huadeng", "sales-business"),
            ("customer_price:export_customer_quote", "huaxing", "sales-business"),
        )
        for permission, factory_id, department in representative_business_access:
            assert auth_service.can(context, permission, factory_id, department)
            assert auth_service.has_permission_in_scope(
                context,
                permission,
                factory_id,
                department,
            )

        # Every business permission assigned to the general-manager position is
        # available at the home and foreign factory. Deliberately excluded
        # domain permissions (currently 3D printing) remain denied.
        expected_business_permissions = (
            set(permission_codes.BUSINESS_PERMISSION_CODES)
            - positions.GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
        )
        for permission in expected_business_permissions:
            assert auth_service.can(context, permission, "huaxing", "management")
            assert auth_service.can(context, permission, "huadeng", "engineering")
            assert auth_service.has_permission_in_scope(
                context,
                permission,
                "huadeng",
                "engineering",
            )
        for permission in positions.GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES:
            assert not auth_service.can(context, permission, "huaxing", "management")

        assert not business_authz.is_wildcard_super_admin(context)
        assert grant.factory_id == "huaxing"
        assert context.profile.primary_factory_id == "huaxing"
        for permission in permission_codes.SYSTEM_MANAGEMENT_PERMISSION_CODES:
            assert not auth_service.can(context, permission, "huaxing", "management")
            assert not auth_service.can(context, permission, "huadeng", "system")
            assert not auth_service.has_permission_in_scope(
                context,
                permission,
                "huadeng",
                "system",
            )


def test_authz_writes_require_enforce_mode(monkeypatch):
    with pytest.raises(RuntimeError, match="AUTHZ_WRITES_ENABLED=true requires AUTHZ_MODE=enforce"):
        make_client(monkeypatch, AUTHZ_MODE="legacy", AUTHZ_WRITES_ENABLED="true")


def test_active_configurable_override_blocks_legacy_and_shadow_but_allows_enforce(monkeypatch):
    with make_client(monkeypatch, AUTHZ_MODE="legacy", AUTHZ_WRITES_ENABLED="false"):
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            permission = db.query(auth_models.AuthPermission).filter_by(code="carton_mark:read").one()
            now = auth_service.now_text()
            db.add(
                auth_models.AuthUserPermissionOverride(
                    id="manual-rollout-guard",
                    user_id="user-admin",
                    permission_id=permission.id,
                    effect="deny",
                    factory_id="*",
                    department="*",
                    status="active",
                    valid_from=now,
                    valid_until="",
                    reason="验证回退保护",
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

            with pytest.raises(RuntimeError, match="AUTHZ_MODE must remain enforce"):
                auth_service.ensure_authz_startup_safety(db)
            monkeypatch.setattr(auth_service.settings, "authz_mode", "shadow")
            with pytest.raises(RuntimeError, match="AUTHZ_MODE must remain enforce"):
                auth_service.ensure_authz_startup_safety(db)
            monkeypatch.setattr(auth_service.settings, "authz_mode", "enforce")
            auth_service.ensure_authz_startup_safety(db)


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


def test_production_http_login_cookie_can_disable_secure_flag(monkeypatch):
    with make_client(monkeypatch, APP_ENV="production", SESSION_COOKIE_SECURE="false") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        assert "rr_session=" in login_response.headers["set-cookie"]
        assert "Secure" not in login_response.headers["set-cookie"]


def test_wrong_password_and_missing_session_are_rejected(monkeypatch):
    with make_client(monkeypatch) as client:
        wrong_password_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "bad-password"},
        )
        assert wrong_password_response.status_code == 401

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401


def test_avatar_endpoints_require_an_active_session(monkeypatch):
    with make_client(monkeypatch) as client:
        upload_response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("avatar.png", make_avatar_png(), "image/png")},
        )
        assert upload_response.status_code == 401

        assert client.get("/api/auth/me/avatar").status_code == 401
        assert client.delete("/api/auth/me/avatar").status_code == 401


def test_current_user_can_upload_read_persist_and_remove_avatar(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert login_response.status_code == 200
        assert login_response.json()["avatar_url"] == ""

        upload_response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("portrait.png", make_avatar_png(), "image/png")},
        )
        assert upload_response.status_code == 200
        profile = upload_response.json()
        avatar_url = profile["avatar_url"]
        assert avatar_url.startswith("/api/auth/me/avatar?v=")

        avatar_response = client.get(avatar_url)
        assert avatar_response.status_code == 200
        assert avatar_response.headers["content-type"] == "image/png"
        assert avatar_response.headers["cache-control"] == "private, no-store"
        assert avatar_response.content.startswith(b"\x89PNG")

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["avatar_url"] == avatar_url

        client.post("/api/auth/logout")
        relogin_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert relogin_response.status_code == 200
        assert relogin_response.json()["avatar_url"] == avatar_url

        delete_response = client.delete("/api/auth/me/avatar")
        assert delete_response.status_code == 200
        assert delete_response.json()["avatar_url"] == ""
        assert client.get("/api/auth/me/avatar").status_code == 404


def test_avatar_upload_rejects_invalid_or_oversize_files(monkeypatch):
    with make_client(monkeypatch) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
        )
        assert login_response.status_code == 200

        invalid_response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("avatar.svg", b"<svg></svg>", "image/svg+xml")},
        )
        assert invalid_response.status_code == 400
        assert "头像" in invalid_response.json()["detail"]

        oversize_response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("avatar.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")},
        )
        assert oversize_response.status_code == 413


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


@pytest.mark.parametrize("factory_id", ["huakang-c", "huakang-d"])
def test_registration_accepts_new_huakang_factory_scopes(monkeypatch, factory_id):
    with make_client(monkeypatch) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "username": f"{factory_id}-applicant",
                "display_name": factory_id.upper(),
                "password": "Strong123",
                "confirm_password": "Strong123",
                "phone": "13800000000",
                "email": "",
                "factory_id": factory_id,
                "department": "engineering",
                "position": "工程师",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending"


def test_registration_rejects_position_longer_than_storage_limit(monkeypatch):
    with make_client(monkeypatch) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "username": "position-too-long",
                "display_name": "职位长度测试",
                "password": "Strong123",
                "confirm_password": "Strong123",
                "phone": "13800000000",
                "email": "",
                "factory_id": "huaxing",
                "department": "engineering",
                "position": "岗" * 129,
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "职位不能超过 128 个字符"


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
        reset_payload = reset_response.json()
        assert reset_payload["status"] == "submitted"
        assert reset_payload["message"] == (
            "申请已提交。请保留当前浏览器，管理员审核通过后可在此直接设置新密码。"
        )
        assert reset_response.cookies.get("rr_password_reset_claim")
        assert reset_payload["request_id"].startswith("password-reset-")

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
        assert password_reset_notification["payload"]["password_reset_request_id"] == reset_payload["request_id"]
        assert password_reset_notification["payload"]["matched_user_id"] == "user-admin"
        assert "contact" not in password_reset_notification["payload"]


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
