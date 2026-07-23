import importlib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = (
        f"sqlite:///{TEST_TMP_DIR / f'system_position_catalog_{uuid4().hex}.db'}"
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def test_fixed_system_position_definition_contract():
    permission_codes = importlib.import_module("app.services.permission_codes")
    positions = importlib.import_module("app.services.system_positions")

    definitions = positions.SYSTEM_POSITION_DEFINITIONS
    assert positions.SYSTEM_POSITION_DEFINITION_VERSION == "fixed-v5"
    assert len(definitions) == 29
    assert len({item.role_id for item in definitions}) == 29
    assert len({(item.department, item.name) for item in definitions}) == 29
    assert not hasattr(positions.SystemPositionDefinition, "permission_profile")

    registered_codes = set(permission_codes.APPLICATION_PERMISSION_CODES)
    assert len(registered_codes) == 65
    assert len(permission_codes.BUSINESS_PERMISSION_CODES) == 58
    assert len(permission_codes.SYSTEM_MANAGEMENT_PERMISSION_CODES) == 7
    for definition in definitions:
        assert len(definition.permission_codes) == len(set(definition.permission_codes))
        assert set(definition.permission_codes) <= registered_codes
        assert definition.scope_mode in positions.VALID_SCOPE_MODES
        assert positions.PRODUCTION_TASK_READ_PERMISSION_CODE in definition.permission_codes

    production_task_operating_role_ids = {
        definition.role_id
        for definition in definitions
        if positions.PRODUCTION_TASK_OPERATE_PERMISSION_CODES
        & set(definition.permission_codes)
    }
    assert production_task_operating_role_ids == {
        "position_general_manager",
        "position_molding_manager",
        "position_molding_supervisor",
        "position_molding_clerk",
    }

    dispatch_role_ids = {
        definition.role_id
        for definition in definitions
        if positions.MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE
        in definition.permission_codes
    }
    assert dispatch_role_ids == positions.MOLDING_SAMPLE_DISPATCH_POSITION_ROLE_IDS
    assert dispatch_role_ids == {
        "position_general_manager",
        "position_engineering_manager",
        "position_engineering_supervisor",
    }

    general_manager = positions.get_system_position("position_general_manager")
    assert general_manager is not None
    assert general_manager.scope_mode == positions.CROSS_FACTORY_OPERATE_SCOPE
    assert len(general_manager.permission_codes) == 58
    assert set(general_manager.permission_codes) == set(
        permission_codes.BUSINESS_PERMISSION_CODES
    )
    assert set(general_manager.permission_codes) == positions.GENERAL_MANAGER_PERMISSION_CODES
    assert positions.GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES == frozenset()
    assert not any(code.startswith("system:") for code in general_manager.permission_codes)

    engineer = positions.get_system_position("position_engineering_engineer")
    engineering_supervisor = positions.get_system_position(
        "position_engineering_supervisor"
    )
    engineering_manager = positions.get_system_position("position_engineering_manager")
    assert engineer.scope_mode == positions.CROSS_FACTORY_READ_SCOPE
    assert engineering_supervisor.scope_mode == positions.CROSS_FACTORY_READ_SCOPE
    assert engineering_manager.scope_mode == positions.CROSS_FACTORY_READ_SCOPE
    assert set(engineer.permission_codes) < set(
        engineering_supervisor.permission_codes
    )
    assert engineering_manager.permission_codes == engineering_supervisor.permission_codes
    assert "molding_sample:supervisor_review" not in engineer.permission_codes
    assert "molding_sample:manager_review" not in engineer.permission_codes
    assert "molding_sample:dispatch" not in engineer.permission_codes
    assert "molding_sample:dispatch" in engineering_supervisor.permission_codes
    assert "molding_sample:dispatch" in engineering_manager.permission_codes
    assert all(
        "molding_sample:raw_material_write" in definition.permission_codes
        for definition in (engineer, engineering_supervisor, engineering_manager)
    )

    sales_business = positions.get_system_position("position_sales_business")
    sales_supervisor = positions.get_system_position("position_sales_supervisor")
    sales_manager = positions.get_system_position("position_sales_manager")
    assert all(
        definition.scope_mode == positions.CROSS_FACTORY_READ_SCOPE
        for definition in (sales_business, sales_supervisor, sales_manager)
    )
    assert "internal_quote:read" in sales_business.permission_codes
    assert "internal_quote:create" in sales_business.permission_codes
    assert "internal_quote:baseline_read" in sales_business.permission_codes
    assert "internal_quote:baseline_manage" not in sales_business.permission_codes
    assert "internal_quote:customer_manage" not in sales_business.permission_codes
    assert "internal_quote:baseline_read" in sales_supervisor.permission_codes
    assert "internal_quote:baseline_manage" in sales_supervisor.permission_codes
    assert "internal_quote:customer_manage" in sales_supervisor.permission_codes
    assert sales_manager.permission_codes == sales_supervisor.permission_codes
    assert set(sales_business.permission_codes) < set(sales_supervisor.permission_codes)

    painting_clerk = positions.get_system_position("position_painting_clerk")
    painting_supervisor = positions.get_system_position("position_painting_supervisor")
    painting_manager = positions.get_system_position("position_painting_manager")
    assert "internal_quote:painting_edit" in painting_clerk.permission_codes
    assert "internal_quote:painting_review" not in painting_clerk.permission_codes
    assert "internal_quote:painting_review" in painting_supervisor.permission_codes
    assert painting_manager.permission_codes == painting_supervisor.permission_codes

    molding_clerk = positions.get_system_position("position_molding_clerk")
    molding_supervisor = positions.get_system_position("position_molding_supervisor")
    molding_manager = positions.get_system_position("position_molding_manager")
    expected_task_permissions = {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
    }
    assert molding_clerk.scope_mode == positions.CROSS_FACTORY_READ_SCOPE
    assert molding_supervisor.scope_mode == positions.CROSS_FACTORY_OPERATE_SCOPE
    assert molding_manager.scope_mode == positions.CROSS_FACTORY_OPERATE_SCOPE
    assert set(molding_clerk.permission_codes) == expected_task_permissions
    assert molding_supervisor.permission_codes == molding_clerk.permission_codes
    assert molding_manager.permission_codes == molding_clerk.permission_codes

    production_supervisor = positions.get_system_position(
        "position_production_supervisor"
    )
    assert "internal_quote:molding_review" in production_supervisor.permission_codes
    assert not (
        positions.PRODUCTION_TASK_OPERATE_PERMISSION_CODES
        & set(production_supervisor.permission_codes)
    )
    assert all(
        not permission.startswith("injection_schedule:")
        for definition in positions.SYSTEM_POSITION_DEFINITIONS
        for permission in definition.permission_codes
    )

    assert all(
        "molding_sample:raw_material_write"
        in positions.get_system_position(role_id).permission_codes
        for role_id in (
            "position_warehouse_manager",
            "position_warehouse_supervisor",
            "position_warehouse_keeper",
        )
    )

    hashes = [
        positions.system_position_definition_hash(definition)
        for definition in definitions
    ]
    assert len(set(hashes)) == 29
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes)
    assert re.fullmatch(r"[0-9a-f]{64}", positions.system_position_catalog_hash())


def test_molding_sample_dispatch_permission_catalog_and_legacy_role_contract():
    auth_service = importlib.import_module("app.services.auth")
    iam_scope = importlib.import_module("app.services.iam_scope")
    permission_codes = importlib.import_module("app.services.permission_codes")
    scope_policy = importlib.import_module("app.services.permission_scope_policy")

    dispatch_permission = "molding_sample:dispatch"
    assert dispatch_permission in permission_codes.MOLDING_SAMPLE_PERMISSION_CODES
    assert (
        iam_scope.default_permission_access_kind(dispatch_permission)
        == iam_scope.OPERATE_ACCESS_KIND
    )

    policy = scope_policy.permission_scope_policy(dispatch_permission)
    assert policy.departments == ("engineering", "management")
    assert policy.requires_global_factory is False

    assert dispatch_permission in auth_service.ROLE_PERMISSIONS["engineering_supervisor"]
    assert dispatch_permission in auth_service.ROLE_PERMISSIONS["manager"]
    assert dispatch_permission in auth_service.ROLE_PERMISSIONS["admin"]
    assert dispatch_permission not in auth_service.ROLE_PERMISSIONS["engineer"]
    assert dispatch_permission not in auth_service.ROLE_PERMISSIONS["molding_clerk"]


def test_reconcile_restores_drift_preserves_bindings_and_is_idempotent(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        positions = importlib.import_module("app.services.system_positions")
        reconcile = importlib.import_module(
            "app.services.system_position_reconcile"
        )

        role_id = "position_engineering_engineer"
        definition = positions.get_system_position(role_id)
        assert definition is not None
        expected_codes = set(definition.permission_codes)
        removed_code = "molding_sample:read"
        extra_code = "system:user_manage"
        binding_id = "user-reconcile-position:position_engineering_engineer:huaxing:engineering"
        timestamp = "2030-01-02 03:04:05"

        with db_module.SessionLocal() as db:
            role = db.get(models.AuthRole, role_id)
            metadata = db.get(models.AuthRoleMetadata, role_id)
            assert role is not None
            assert metadata is not None
            baseline_version = metadata.version

            permissions_by_code = {
                item.code: item
                for item in db.scalars(select(models.AuthPermission)).all()
            }
            removed_permission = permissions_by_code[removed_code]
            removed_link = db.scalar(
                select(models.AuthRolePermission).where(
                    models.AuthRolePermission.role_id == role_id,
                    models.AuthRolePermission.permission_id == removed_permission.id,
                )
            )
            assert removed_link is not None
            db.delete(removed_link)

            extra_permission = permissions_by_code[extra_code]
            db.add(
                models.AuthRolePermission(
                    id=f"{role_id}:{extra_permission.id}",
                    role_id=role_id,
                    permission_id=extra_permission.id,
                )
            )
            role.name = "漂移后的工程职位"
            role.description = "管理员在线修改的漂移说明"
            metadata.scope_mode = "cross_factory_operate"

            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                models.AuthUser(
                    id="user-reconcile-position",
                    username="reconcile-position",
                    display_name="同步绑定测试用户",
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            db.add(
                models.AuthUserRole(
                    id=binding_id,
                    user_id="user-reconcile-position",
                    role_id=role_id,
                    factory_id="huaxing",
                    department="engineering",
                )
            )
            db.add(
                models.AuthRoleBindingMetadata(
                    user_role_id=binding_id,
                    state="active",
                    source_type="system_position",
                    source_id="",
                    valid_from="",
                    valid_until="",
                    reason="同步测试",
                    created_by_user_id="user-admin",
                    approved_by_user_id="user-admin",
                    revoked_by_user_id="",
                    revoked_at="",
                    revoke_reason="",
                    version=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            db.add(
                models.AuthUserAuthorizationRevision(
                    user_id="user-reconcile-position",
                    revision=7,
                    updated_at=timestamp,
                )
            )
            db.commit()

            event_count_before = db.query(models.AuthAuthorizationEvent).filter_by(
                event_type="system_position_reconciled",
                target_type="role",
                target_id=role_id,
            ).count()

            result = reconcile.reconcile_system_position_catalog(db, now=timestamp)
            assert result.changed_role_ids == (role_id,)
            assert result.changed_user_ids == ("user-reconcile-position",)

            updated_role = db.get(models.AuthRole, role_id)
            updated_metadata = db.get(models.AuthRoleMetadata, role_id)
            assert updated_role.name == definition.name
            assert updated_role.description == definition.description
            assert updated_metadata.scope_mode == definition.scope_mode
            assert updated_metadata.version == baseline_version + 1

            actual_codes = {
                item.code
                for item in db.scalars(
                    select(models.AuthPermission)
                    .join(
                        models.AuthRolePermission,
                        models.AuthRolePermission.permission_id
                        == models.AuthPermission.id,
                    )
                    .where(models.AuthRolePermission.role_id == role_id)
                ).all()
            }
            assert actual_codes == expected_codes
            assert db.get(models.AuthUserRole, binding_id) is not None
            assert db.get(models.AuthRoleBindingMetadata, binding_id).state == "active"
            assert (
                db.get(
                    models.AuthUserAuthorizationRevision,
                    "user-reconcile-position",
                ).revision
                == 8
            )

            events = db.query(models.AuthAuthorizationEvent).filter_by(
                event_type="system_position_reconciled",
                target_type="role",
                target_id=role_id,
            ).all()
            assert len(events) == event_count_before + 1
            event = next(item for item in events if item.created_at == timestamp)
            before = json.loads(event.before_json)
            after = json.loads(event.after_json)
            assert removed_code not in before["permission_codes"]
            assert extra_code in before["permission_codes"]
            assert before["scope_mode"] == "cross_factory_operate"
            assert set(after["permission_codes"]) == expected_codes
            assert after["scope_mode"] == definition.scope_mode
            assert after["definition_hash"] == positions.system_position_definition_hash(
                definition
            )
            assert event.actor_user_id == reconcile.SYSTEM_POSITION_RECONCILE_ACTOR_ID

            state = db.get(
                models.AuthIamState,
                reconcile.SYSTEM_POSITION_CATALOG_STATE_KEY,
            )
            state_value = json.loads(state.value_json)
            assert state_value["catalog_hash"] == result.catalog_hash
            assert state_value["role_hashes"][role_id] == after["definition_hash"]

            version_after_first_run = updated_metadata.version
            revision_after_first_run = db.get(
                models.AuthUserAuthorizationRevision,
                "user-reconcile-position",
            ).revision
            second_result = reconcile.reconcile_system_position_catalog(
                db,
                now="2030-01-02 03:05:05",
            )
            assert second_result.changed_role_ids == ()
            assert second_result.changed_user_ids == ()
            assert db.get(models.AuthRoleMetadata, role_id).version == version_after_first_run
            assert (
                db.get(
                    models.AuthUserAuthorizationRevision,
                    "user-reconcile-position",
                ).revision
                == revision_after_first_run
            )
            assert db.query(models.AuthAuthorizationEvent).filter_by(
                event_type="system_position_reconciled",
                target_type="role",
                target_id=role_id,
            ).count() == event_count_before + 1

            # A change to a code-owned, derived-only field is still a real
            # template change even though AuthRole has no sort-order column.
            changed_definition = replace(
                definition,
                sort_order=definition.sort_order + 1,
            )
            changed_definitions = tuple(
                changed_definition if item.role_id == role_id else item
                for item in positions.SYSTEM_POSITION_DEFINITIONS
            )
            monkeypatch.setattr(
                positions,
                "SYSTEM_POSITION_DEFINITIONS",
                changed_definitions,
            )
            monkeypatch.setattr(
                reconcile,
                "SYSTEM_POSITION_DEFINITIONS",
                changed_definitions,
            )

            hash_change_result = reconcile.reconcile_system_position_catalog(
                db,
                now="2030-01-02 03:06:05",
            )
            assert hash_change_result.changed_role_ids == (role_id,)
            assert hash_change_result.changed_user_ids == (
                "user-reconcile-position",
            )
            assert (
                db.get(models.AuthRoleMetadata, role_id).version
                == version_after_first_run + 1
            )
            assert (
                db.get(
                    models.AuthUserAuthorizationRevision,
                    "user-reconcile-position",
                ).revision
                == revision_after_first_run + 1
            )
            hash_change_event = db.query(models.AuthAuthorizationEvent).filter_by(
                event_type="system_position_reconciled",
                target_type="role",
                target_id=role_id,
                created_at="2030-01-02 03:06:05",
            ).one()
            assert json.loads(hash_change_event.before_json)["definition_hash"] != (
                json.loads(hash_change_event.after_json)["definition_hash"]
            )

            version_after_hash_change = db.get(
                models.AuthRoleMetadata,
                role_id,
            ).version
            revision_after_hash_change = db.get(
                models.AuthUserAuthorizationRevision,
                "user-reconcile-position",
            ).revision
            hash_noop_result = reconcile.reconcile_system_position_catalog(
                db,
                now="2030-01-02 03:07:05",
            )
            assert hash_noop_result.changed_role_ids == ()
            assert hash_noop_result.changed_user_ids == ()
            assert (
                db.get(models.AuthRoleMetadata, role_id).version
                == version_after_hash_change
            )
            assert (
                db.get(
                    models.AuthUserAuthorizationRevision,
                    "user-reconcile-position",
                ).revision
                == revision_after_hash_change
            )


def test_reconcile_upgrades_legacy_production_task_position_matrix_without_losing_sessions(
    monkeypatch,
):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        positions = importlib.import_module("app.services.system_positions")
        reconcile = importlib.import_module(
            "app.services.system_position_reconcile"
        )

        readonly_role_ids = {
            definition.role_id
            for definition in positions.SYSTEM_POSITION_DEFINITIONS
            if definition.role_id
            not in positions.PRODUCTION_TASK_OPERATING_POSITION_ROLE_IDS
        }
        legacy_production_role_ids = {
            "position_production_manager",
            "position_production_supervisor",
            "position_production_clerk",
        }
        legacy_without_task_read_role_ids = (
            readonly_role_ids - legacy_production_role_ids
        )
        timestamp = "2030-02-03 04:05:06"
        user_id = "user-legacy-production-position"
        binding_id = (
            f"{user_id}:position_production_clerk:huaxing:production"
        )
        session_id = "session-legacy-production-position"

        with db_module.SessionLocal() as db:
            permissions_by_code = {
                permission.code: permission
                for permission in db.scalars(select(models.AuthPermission)).all()
            }
            production_read = permissions_by_code[
                positions.PRODUCTION_TASK_READ_PERMISSION_CODE
            ]

            for role_id in sorted(legacy_without_task_read_role_ids):
                link = db.scalar(
                    select(models.AuthRolePermission).where(
                        models.AuthRolePermission.role_id == role_id,
                        models.AuthRolePermission.permission_id
                        == production_read.id,
                    )
                )
                assert link is not None
                db.delete(link)

            for role_id in sorted(legacy_production_role_ids):
                for permission_code in sorted(
                    positions.PRODUCTION_TASK_OPERATE_PERMISSION_CODES
                ):
                    permission = permissions_by_code[permission_code]
                    db.add(
                        models.AuthRolePermission(
                            id=f"legacy:{role_id}:{permission.id}",
                            role_id=role_id,
                            permission_id=permission.id,
                        )
                    )

            state = db.get(
                models.AuthIamState,
                reconcile.SYSTEM_POSITION_CATALOG_STATE_KEY,
            )
            state_value = json.loads(state.value_json)
            for role_id in readonly_role_ids:
                state_value["role_hashes"][role_id] = (
                    f"legacy-production-task:{role_id}"
                )
            state_value["catalog_hash"] = "legacy-production-task-catalog"
            state.value_json = json.dumps(state_value, ensure_ascii=False)

            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                models.AuthUser(
                    id=user_id,
                    username="legacy-production-position",
                    display_name="旧生产文员",
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            db.add(
                models.AuthUserRole(
                    id=binding_id,
                    user_id=user_id,
                    role_id="position_production_clerk",
                    factory_id="huaxing",
                    department="production",
                )
            )
            db.add(
                models.AuthUserAuthorizationRevision(
                    user_id=user_id,
                    revision=4,
                    updated_at=timestamp,
                )
            )
            db.add(
                models.AuthSession(
                    id=session_id,
                    user_id=user_id,
                    token_hash="legacy-production-position-token",
                    status="active",
                    ip_address="127.0.0.1",
                    user_agent="pytest",
                    expires_at="2031-02-03 04:05:06",
                    created_at=timestamp,
                    revoked_at="",
                )
            )
            db.commit()

            result = reconcile.reconcile_system_position_catalog(
                db,
                now=timestamp,
            )
            assert set(result.changed_role_ids) == readonly_role_ids
            assert result.changed_user_ids == (user_id,)

            for definition in positions.SYSTEM_POSITION_DEFINITIONS:
                permission_codes = {
                    permission.code
                    for permission in db.scalars(
                        select(models.AuthPermission)
                        .join(
                            models.AuthRolePermission,
                            models.AuthRolePermission.permission_id
                            == models.AuthPermission.id,
                        )
                        .where(
                            models.AuthRolePermission.role_id
                            == definition.role_id
                        )
                    ).all()
                }
                assert permission_codes == set(definition.permission_codes)

            assert db.get(models.AuthUserRole, binding_id) is not None
            assert db.get(models.AuthSession, session_id).status == "active"
            assert (
                db.get(models.AuthUserAuthorizationRevision, user_id).revision
                == 5
            )
            assert db.query(models.AuthAuthorizationEvent).filter(
                models.AuthAuthorizationEvent.event_type
                == "system_position_reconciled",
                models.AuthAuthorizationEvent.target_id.in_(readonly_role_ids),
                models.AuthAuthorizationEvent.created_at == timestamp,
            ).count() == len(readonly_role_ids)

            second_result = reconcile.reconcile_system_position_catalog(
                db,
                now="2030-02-03 04:06:06",
            )
            assert second_result.changed_role_ids == ()
            assert second_result.changed_user_ids == ()
            assert db.get(models.AuthSession, session_id).status == "active"
            assert (
                db.get(models.AuthUserAuthorizationRevision, user_id).revision
                == 5
            )


def test_reconcile_metadata_repair_advances_the_virtual_version(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        reconcile = importlib.import_module(
            "app.services.system_position_reconcile"
        )

        role_id = "position_qa_clerk"
        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleMetadata, role_id)
            assert metadata is not None
            assert metadata.version == 1
            db.delete(metadata)
            db.commit()

            result = reconcile.reconcile_system_position_catalog(
                db,
                now="2030-01-02 04:05:06",
            )
            assert result.changed_role_ids == (role_id,)
            assert db.get(models.AuthRoleMetadata, role_id).version == 2

            event = db.query(models.AuthAuthorizationEvent).filter_by(
                event_type="system_position_reconciled",
                target_type="role",
                target_id=role_id,
                created_at="2030-01-02 04:05:06",
            ).one()
            assert json.loads(event.before_json)["version"] == 0
            assert json.loads(event.after_json)["version"] == 2


def test_reconcile_rejects_an_unregistered_definition_permission(monkeypatch):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        positions = importlib.import_module("app.services.system_positions")
        reconcile = importlib.import_module(
            "app.services.system_position_reconcile"
        )

        role_id = "position_engineering_engineer"
        definition = positions.get_system_position(role_id)
        assert definition is not None
        invalid_definition = replace(
            definition,
            permission_codes=(*definition.permission_codes, "future_module:undeclared"),
        )
        monkeypatch.setattr(
            reconcile,
            "SYSTEM_POSITION_DEFINITIONS",
            (invalid_definition,),
        )

        with db_module.SessionLocal() as db:
            role = db.get(models.AuthRole, role_id)
            name_before = role.name
            with pytest.raises(RuntimeError, match="权限目录缺少.*future_module:undeclared"):
                reconcile.reconcile_system_position_catalog(db)
            assert db.get(models.AuthRole, role_id).name == name_before
