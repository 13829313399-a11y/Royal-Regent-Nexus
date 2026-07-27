import importlib
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select


BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = BACKEND_DIR / ".pytest-tmp"
ADMIN_PASSWORD = "AdminSeed123!"
REAL_WORKBOOK = Path(
    r"C:\Users\匡树杰\Desktop\啤机部项目资料\华兴啤机日排版表1.xlsx"
)
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch, database_path: Path | None = None) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    target = database_path or TEST_TMP_DIR / f"injection_phase2_{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target.as_posix()}")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_test_user(
    *,
    username: str,
    role_id: str,
    factory_id: str,
    department: str,
) -> str:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"test-user-{username}"
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=username,
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.add(
            auth_models.AuthUserRole(
                id=f"{user_id}:{role_id}:{factory_id}:{department}",
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position="测试岗位",
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.commit()
    return user_id


def grant_override(
    *,
    user_id: str,
    permission_code: str,
    factory_id: str,
    department: str = "*",
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        permission = db.scalar(
            select(auth_models.AuthPermission).where(
                auth_models.AuthPermission.code == permission_code
            )
        )
        assert permission is not None
        db.add(
            auth_models.AuthUserPermissionOverride(
                id=f"override-{uuid4().hex}",
                user_id=user_id,
                permission_id=permission.id,
                effect="allow",
                factory_id=factory_id,
                department=department,
                status="active",
                valid_from="",
                valid_until="",
                reason="注塑排产跨厂只读自动化测试",
                source_type="test",
                source_id="",
                created_by_user_id="",
                approved_by_user_id="",
                revoked_by_user_id="",
                revoked_at="",
                revoke_reason="",
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.commit()


def login_user(client: TestClient, username: str) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    assert response.status_code == 200, response.text


def post_complete_master_data(
    client: TestClient,
    factory_id: str,
    *,
    prefix: str,
) -> dict[str, dict]:
    base = f"/api/factories/{factory_id}/injection-schedule"
    machines = []
    for index in (1, 2):
        response = client.post(
            f"{base}/machines",
            json={
                "machine_code": f"{prefix}-M{index}",
                "machine_name": f"{prefix} 完整机台 {index}",
                "workshop": "new",
                "machine_class": "160T",
                "tonnage_t": 160,
                "process_type": "standard",
                "screw_type": "standard",
                "robot_type": "three-axis",
                "fixture_type": "standard",
                "max_shot_weight_g": 1000,
                "tie_bar_x_mm": 800,
                "tie_bar_y_mm": 800,
                "mold_thickness_min_mm": 100,
                "mold_thickness_max_mm": 600,
                "opening_stroke_mm": 700,
                "ejector_stroke_mm": 200,
                "status": "available",
                "available_at": "",
                "capabilities": ["hot-runner"],
                "material_rules": ["ABS"],
                "quality_status": "verified",
            },
        )
        assert response.status_code == 201, response.text
        machines.append(response.json())

    response = client.post(
        f"{base}/molds",
        json={
            "mold_code": f"{prefix}-MOULD",
            "mold_name": f"{prefix} 完整模具",
            "machine_class": "160T",
            "robot_type": "three-axis",
            "fixture_type": "standard",
            "length_mm": 400,
            "width_mm": 300,
            "height_mm": 250,
            "mold_weight_kg": 500,
            "gross_shot_weight_g": 100,
            "mold_thickness_mm": 250,
            "required_opening_stroke_mm": 300,
            "required_screw_type": "standard",
            "cavities": 1,
            "cycle_seconds": 30,
            "required_capabilities": ["hot-runner"],
            "material_rules": ["ABS"],
            "quality_status": "verified",
        },
    )
    assert response.status_code == 201, response.text
    mold = response.json()

    response = client.post(
        f"{base}/orders",
        json={
            "natural_key": f"{prefix}-ORDER-NATURAL-KEY",
            "order_no": f"{prefix}-ORDER",
            "product_code": f"{prefix}-PRODUCT",
            "product_name": f"{prefix} 完整订单",
            "mold_code": mold["mold_code"],
            "color": "black",
            "pigment": "BK-01",
            "material": "ABS",
            "machine_class": "160T",
            "order_qty": 1000,
            "produced_qty": 0,
            "daily_target_qty": 1000,
            "delivery_due_date": "2026-08-15",
            "priority_flag": "normal",
            "status": "open",
            "imported_assigned_machine_code": machines[0]["machine_code"],
            "quality_status": "verified",
        },
    )
    assert response.status_code == 201, response.text
    order = response.json()
    rule_config = client.get(f"{base}/rule-config")
    assert rule_config.status_code == 200, rule_config.text
    config = rule_config.json()["config"]
    config["availability_calendar_verified_through"] = "2027-12-31 23:59:59"
    saved_config = client.patch(
        f"{base}/rule-config",
        json={
            "expected_revision": rule_config.json()["revision"],
            "reason": "测试夹具确认排产日历范围",
            "config": config,
        },
    )
    assert saved_config.status_code == 200, saved_config.text
    return {
        "machine1": machines[0],
        "machine2": machines[1],
        "mold": mold,
        "order": order,
    }


def order_update_payload(
    order: dict,
    **overrides,
) -> dict:
    payload = {
        "expected_revision": order["revision"],
        "order_no": order["order_no"],
        "product_code": order["product_code"],
        "product_name": order["product_name"],
        "mold_code": order["mold_code"],
        "color": order["color"],
        "pigment": order["pigment"],
        "material": order["material"],
        "machine_class": order["machine_class"],
        "order_qty": order["order_qty"],
        "produced_qty": order["produced_qty"],
        "daily_target_qty": order["daily_target_qty"],
        "delivery_due_date": order["delivery_due_date"],
        "priority_flag": order["priority_flag"],
        "status": order["status"],
        "imported_assigned_machine_code": order[
            "imported_assigned_machine_code"
        ],
        "quality_status": order["quality_status"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.skipif(not REAL_WORKBOOK.exists(), reason="真实华兴排版工作簿不在当前机器")
def test_real_huaxing_workbook_preview_confirm_and_restart_persistence(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "real_huaxing_phase2.db"
    workbook_bytes = REAL_WORKBOOK.read_bytes()

    with make_client(monkeypatch, database_path) as client:
        login_admin(client)
        base = "/api/factories/huaxing/injection-schedule"
        response = client.post(
            f"{base}/imports",
            files={
                "file": (
                    REAL_WORKBOOK.name,
                    workbook_bytes,
                    XLSX_CONTENT_TYPE,
                )
            },
            headers={"x-request-id": "real-huaxing-preview"},
        )
        assert response.status_code == 201, response.text
        preview = response.json()
        assert preview["status"] == "previewed"
        assert preview["revision"] == 1
        assert preview["draft_version_id"] == ""
        assert preview["summary"] == {
            "machine_count": 76,
            "old_machine_count": 39,
            "new_machine_count": 37,
            "order_count": 296,
            "assigned_order_count": 258,
            "preassigned_pending_count": 4,
            "unassigned_order_count": 34,
            "pending_pool_count": 38,
            "mold_count": 231,
            "issue_count": 550,
            "blocking_issue_count": 0,
            "formula_error_count": 105,
            "external_formula_risk_count": 25,
            "business_date": "2026-07-21",
            "pending_pool_start_row": 350,
            "archive": {
                "compressed_bytes": len(workbook_bytes),
                "uncompressed_bytes": 179385143,
                "member_count": 90,
            },
        }
        assert sum(item["blocking"] for item in preview["issues"]) == 0
        assert len(preview["preview"]["machines"]) == 76
        assert len(preview["preview"]["orders"]) == 296
        assert "1900-" not in str(preview["preview"]["orders"])

        assert client.get(f"{base}/machines").json() == []
        assert client.get(f"{base}/molds").json() == []
        assert client.get(f"{base}/orders").json() == []

        response = client.post(
            f"{base}/imports/{preview['id']}/confirm",
            json={
                "expected_revision": 1,
                "mode": "merge",
                "business_date": "2026-07-21",
                "reason": "确认导入华兴真实日排版",
                "resolutions": {},
            },
            headers={"x-request-id": "real-huaxing-confirm"},
        )
        assert response.status_code == 200, response.text
        confirmed = response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["revision"] == 2
        assert confirmed["confirm_reason"] == "确认导入华兴真实日排版"
        assert confirmed["draft_version_id"]

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            """
            SELECT status, revision, business_date, confirm_reason,
                   length(source_content), source_sha256, draft_version_id
            FROM injection_schedule_import_batches
            """
        ).fetchone() == (
            "confirmed",
            2,
            "2026-07-21",
            "确认导入华兴真实日排版",
            len(workbook_bytes),
            preview["source_sha256"],
            confirmed["draft_version_id"],
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM injection_machine_masters WHERE factory_id = 'huaxing'"
        ).fetchone() == (76,)
        assert connection.execute(
            "SELECT COUNT(*) FROM injection_mold_masters WHERE factory_id = 'huaxing'"
        ).fetchone() == (231,)
        assert connection.execute(
            "SELECT COUNT(*) FROM injection_order_masters WHERE factory_id = 'huaxing'"
        ).fetchone() == (296,)
        assert connection.execute(
            """
            SELECT status, source_batch_id
            FROM injection_schedule_versions
            WHERE id = ?
            """,
            (confirmed["draft_version_id"],),
        ).fetchone() == ("draft", preview["id"])
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM injection_schedule_tasks
            WHERE version_id = ?
            """,
            (confirmed["draft_version_id"],),
        ).fetchone() == (245,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM injection_schedule_audit_events
            WHERE factory_id = 'huaxing'
              AND entity_type = 'import_batch'
              AND action = 'confirmed'
              AND request_id = 'real-huaxing-confirm'
            """
        ).fetchone() == (1,)

    with make_client(monkeypatch, database_path) as restarted_client:
        login_admin(restarted_client)
        workspace = restarted_client.get(
            "/api/factories/huaxing/injection-schedule/workspace"
        )
        assert workspace.status_code == 200, workspace.text
        body = workspace.json()
        assert len(body["machines"]) == 76
        assert len(body["molds"]) == 231
        assert len(body["orders"]) == 296
        assert body["active_version"]["id"] == confirmed["draft_version_id"]
        assert body["active_version"]["status"] == "draft"
        assert len(body["tasks"]) == 245
        assert body["workspace_revision"] == 1


def test_injection_permissions_are_local_and_cross_factory_read_is_explicit(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "injection_permissions.db"
    with make_client(monkeypatch, database_path) as client:
        login_admin(client)
        user_id = create_test_user(
            username="phase2_molding_clerk",
            role_id="molding_clerk",
            factory_id="huakang-a",
            department="molding",
        )
        login_user(client, "phase2_molding_clerk")

        local = client.get(
            "/api/factories/huakang-a/injection-schedule/workspace"
        )
        assert local.status_code == 200, local.text
        assert local.json()["workspace_revision"] == 0
        assert local.json()["rule_config"]["revision"] == 0

        denied_cross = client.get(
            "/api/factories/huadeng/injection-schedule/workspace"
        )
        assert denied_cross.status_code == 403

        grant_override(
            user_id=user_id,
            permission_code="injection_schedule:cross_factory_read",
            factory_id="huadeng",
        )
        allowed_cross = client.get(
            "/api/factories/huadeng/injection-schedule/workspace"
        )
        assert allowed_cross.status_code == 200, allowed_cross.text

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module("app.models.injection_schedule")
        with db_module.SessionLocal() as db:
            assert db.get(
                schedule_models.InjectionScheduleFactoryState, "huadeng"
            ) is None
            assert db.get(
                schedule_models.InjectionScheduleRuleConfig, "huadeng"
            ) is None

        forbidden_cross_write = client.post(
            "/api/factories/huadeng/injection-schedule/versions",
            json={
                "name": "不允许的跨厂草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert forbidden_cross_write.status_code == 403

        local_draft = client.post(
            "/api/factories/huakang-a/injection-schedule/versions",
            json={
                "name": "本厂草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert local_draft.status_code == 201, local_draft.text

        config_denied = client.post(
            "/api/factories/huakang-a/injection-schedule/machines",
            json={"machine_code": "A-001"},
        )
        assert config_denied.status_code == 403
        import_config_denied = client.post(
            "/api/factories/huakang-a/injection-schedule/imports",
            files={
                "file": (
                    "edit-only.xlsx",
                    b"permission-check",
                    XLSX_CONTENT_TYPE,
                )
            },
        )
        assert import_config_denied.status_code == 403

        invalid_factory = client.get(
            "/api/factories/not-a-factory/injection-schedule/workspace"
        )
        assert invalid_factory.status_code == 404


def test_commands_cas_publish_immutability_diff_and_append_only_audit(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "injection_operations.db"
    with make_client(monkeypatch, database_path) as client:
        login_admin(client)
        factory_id = "huakang-a"
        base = f"/api/factories/{factory_id}/injection-schedule"
        masters = post_complete_master_data(
            client,
            factory_id,
            prefix="VALID",
        )

        created = client.post(
            f"{base}/versions",
            json={
                "name": "可发布草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert created.status_code == 201, created.text
        version = created.json()
        detail = client.get(f"{base}/versions/{version['id']}").json()
        assert len(detail["tasks"]) == 1
        original_task_id = detail["tasks"][0]["id"]

        split = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "拆分订单并验证序列",
                "request_id": "phase2-split",
                "commands": [
                    {
                        "type": "split",
                        "task_id": original_task_id,
                        "split_qty": 400,
                        "machine_id": masters["machine2"]["id"],
                        "target_index": 0,
                    }
                ],
            },
        )
        assert split.status_code == 200, split.text
        split_body = split.json()
        assert split_body["version"]["revision"] == 2
        assert sorted(item["planned_qty"] for item in split_body["tasks"]) == [
            400,
            600,
        ]
        split_child = next(
            item for item in split_body["tasks"] if item["parent_task_id"]
        )
        assert split_child["machine_id"] == masters["machine2"]["id"]
        assert split_child["sequence_no"] == 0

        stale = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "模拟旧页面提交",
                "commands": [
                    {"type": "lock", "task_id": original_task_id}
                ],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "revision_conflict"
        assert stale.json()["detail"]["current_revision"] == 2

        lock = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 2,
                "reason": "锁定首个任务",
                "commands": [
                    {"type": "lock", "task_id": original_task_id}
                ],
            },
        )
        assert lock.status_code == 200, lock.text
        assert lock.json()["version"]["revision"] == 3

        locked_reorder = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 3,
                "reason": "锁定任务不可排序",
                "commands": [
                    {
                        "type": "reorder",
                        "task_id": original_task_id,
                        "target_index": 1,
                    }
                ],
            },
        )
        assert locked_reorder.status_code == 409
        assert locked_reorder.json()["detail"]["code"] == "task_locked"

        unlock = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 3,
                "reason": "解锁后允许移动",
                "commands": [
                    {"type": "unlock", "task_id": original_task_id}
                ],
            },
        )
        assert unlock.status_code == 200, unlock.text
        assert unlock.json()["version"]["revision"] == 4

        moved = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 4,
                "reason": "移动到第二机台",
                "request_id": "phase2-audited-move",
                "commands": [
                    {
                        "type": "move",
                        "task_id": original_task_id,
                        "machine_id": masters["machine2"]["id"],
                        "target_index": 0,
                    }
                ],
            },
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["version"]["revision"] == 5
        assert {
            item["machine_id"] for item in moved.json()["tasks"]
        } == {masters["machine2"]["id"]}
        moved_split_child = next(
            item
            for item in moved.json()["tasks"]
            if item["id"] == split_child["id"]
        )
        assert moved_split_child["revision"] == split_child["revision"] + 1

        validation = client.post(
            f"{base}/versions/{version['id']}/validate",
            json={"expected_revision": 5},
        )
        assert validation.status_code == 200, validation.text
        validation_body = validation.json()
        assert validation_body["status"] == "passed"
        assert validation_body["blocking_count"] == 0

        published = client.post(
            f"{base}/versions/{version['id']}/publish",
            json={
                "expected_revision": 5,
                "validation_run_id": validation_body["id"],
                "reason": "完成硬约束校验后发布",
            },
            headers={"x-request-id": "phase2-publish"},
        )
        assert published.status_code == 200, published.text
        published_body = published.json()
        assert published_body["status"] == "published"
        assert published_body["revision"] == 6
        assert published_body["publish_reason"] == "完成硬约束校验后发布"
        assert published_body["data_hash"] == validation_body["data_hash"]

        published_validation = client.post(
            f"{base}/versions/{version['id']}/validate",
            json={"expected_revision": 6},
        )
        assert published_validation.status_code == 409
        assert "不可重新校验" in published_validation.json()["detail"]

        immutable = client.post(
            f"{base}/versions/{version['id']}/commands",
            json={
                "expected_revision": 6,
                "reason": "发布版禁止修改",
                "commands": [
                    {"type": "lock", "task_id": original_task_id}
                ],
            },
        )
        assert immutable.status_code == 409
        assert immutable.json()["detail"] == "已发布版本不可修改，请复制为新草稿"

        for path, payload in (
            (
                f"{base}/versions/{version['id']}/commands",
                {
                    "expected_revision": 6,
                    "reason": "   ",
                    "commands": [
                        {"type": "lock", "task_id": original_task_id}
                    ],
                },
            ),
            (
                f"{base}/versions/{version['id']}/publish",
                {"expected_revision": 6, "reason": "   "},
            ),
            (
                f"{base}/versions/{version['id']}/clone",
                {"name": "空白原因", "reason": "   "},
            ),
        ):
            response = client.post(path, json=payload)
            assert response.status_code == 422, response.text

        order_before_master_edit = client.get(
            f"{base}/versions/{version['id']}"
        ).json()["tasks"][0]
        updated_order = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json={
                "expected_revision": masters["order"]["revision"],
                "product_name": "主数据后来改名",
            },
        )
        assert updated_order.status_code == 200, updated_order.text
        published_after_master_edit = client.get(
            f"{base}/versions/{version['id']}"
        ).json()
        assert {
            item["product_name"] for item in published_after_master_edit["tasks"]
        } == {order_before_master_edit["product_name"]}

        second_mold = client.post(
            f"{base}/molds",
            json={
                "mold_code": "VALID-MOULD-2",
                "mold_name": "第二完整模具",
                "machine_class": "160T",
                "robot_type": "three-axis",
                "fixture_type": "standard",
                "length_mm": 350,
                "width_mm": 250,
                "height_mm": 220,
                    "mold_weight_kg": 400,
                    "gross_shot_weight_g": 90,
                    "mold_thickness_mm": 220,
                    "required_opening_stroke_mm": 280,
                    "required_screw_type": "standard",
                    "cavities": 1,
                "cycle_seconds": 28,
                "required_capabilities": ["hot-runner"],
                "material_rules": ["ABS"],
                "quality_status": "verified",
            },
        )
        assert second_mold.status_code == 201, second_mold.text
        second_order = client.post(
            f"{base}/orders",
            json={
                "natural_key": "VALID-ORDER-2-NATURAL",
                "order_no": "VALID-ORDER-2",
                "product_code": "VALID-PRODUCT-2",
                "product_name": "第二完整订单",
                "mold_code": second_mold.json()["mold_code"],
                "color": "white",
                "pigment": "WH-01",
                "material": "ABS",
                "machine_class": "160T",
                "order_qty": 500,
                "produced_qty": 0,
                "daily_target_qty": 500,
                "delivery_due_date": "2026-08-20",
                "priority_flag": "normal",
                "status": "open",
                "imported_assigned_machine_code": "",
                "quality_status": "verified",
            },
        )
        assert second_order.status_code == 201, second_order.text

        cloned = client.post(
            f"{base}/versions/{version['id']}/clone",
            json={"name": "发布版调整副本", "reason": "新增排程调整"},
        )
        assert cloned.status_code == 201, cloned.text
        clone = cloned.json()
        assert clone["status"] == "draft"
        assert clone["base_version_id"] == version["id"]

        initial_diff = client.get(f"{base}/versions/{clone['id']}/diff")
        assert initial_diff.status_code == 200, initial_diff.text
        assert all(
            initial_diff.json()["summary"][key] == 0
            for key in (
                "added",
                "removed",
                "moved",
                "rescheduled",
                "quantity_changed",
                "split_orders",
                "locked_changes",
                "added_conflict_count",
                "resolved_conflict_count",
                "changeover_minutes_delta",
                "mold_change_count_delta",
            )
        )

        clone_detail = client.get(f"{base}/versions/{clone['id']}").json()
        clone_move = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "副本移动并新增第二模具订单",
                "commands": [
                    {
                        "type": "move",
                        "task_id": clone_detail["tasks"][0]["id"],
                        "machine_id": masters["machine1"]["id"],
                        "target_index": 0,
                    },
                    {
                        "type": "assign",
                        "order_id": second_order.json()["id"],
                        "machine_id": masters["machine1"]["id"],
                        "target_index": 1,
                        "planned_qty": 500,
                    },
                ],
            },
        )
        assert clone_move.status_code == 200, clone_move.text
        clone_move_body = clone_move.json()
        moved_clone_task = next(
            item
            for item in clone_move_body["tasks"]
            if item["order_id"] == masters["order"]["id"]
            and item["machine_id"] == masters["machine1"]["id"]
        )
        remaining_base_task = next(
            item
            for item in clone_move_body["tasks"]
            if item["order_id"] == masters["order"]["id"]
            and item["id"] != moved_clone_task["id"]
        )
        clone_lock_and_split = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 2,
                "reason": "锁定并跨机拆分验证版本差异",
                "commands": [
                    {"type": "lock", "task_id": moved_clone_task["id"]},
                    {
                        "type": "split",
                        "task_id": remaining_base_task["id"],
                        "split_qty": 100,
                        "machine_id": masters["machine1"]["id"],
                        "target_index": 2,
                    },
                ],
            },
        )
        assert clone_lock_and_split.status_code == 200, clone_lock_and_split.text
        clone_validation = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 3},
        )
        assert clone_validation.status_code == 200, clone_validation.text
        assert clone_validation.json()["status"] == "blocked"

        changed_diff = client.get(f"{base}/versions/{clone['id']}/diff")
        assert changed_diff.status_code == 200, changed_diff.text
        changed_summary = changed_diff.json()["summary"]
        assert changed_summary["moved"] == 1
        assert changed_summary["added"] == 1
        assert changed_summary["split_orders"] == 1
        assert changed_summary["locked_changes"] == 1
        assert changed_summary["added_conflict_count"] > 0
        assert changed_summary["changeover_minutes_delta"] > 0
        assert changed_summary["mold_change_count_delta"] > 0

        audit = client.get(f"{base}/audit")
        assert audit.status_code == 200, audit.text
        actions = [item["action"] for item in audit.json()]
        assert "commands_applied" in actions
        assert "validated" in actions
        assert "published" in actions
        published_audit = next(
            item for item in audit.json() if item["action"] == "published"
        )
        assert published_audit["request_id"] == "phase2-publish"
        assert published_audit["reason"] == "完成硬约束校验后发布"
        move_audit = next(
            item
            for item in audit.json()
            if item["request_id"] == "phase2-audited-move"
        )
        audited_task_fields = {
            "planned_start_at",
            "planned_finish_at",
            "setup_hours",
            "duration_hours",
            "risk_level",
            "risk_reasons",
        }
        assert move_audit["before"]["tasks"]
        assert move_audit["after"]["tasks"]
        assert all(
            audited_task_fields <= set(task)
            for task in (
                move_audit["before"]["tasks"]
                + move_audit["after"]["tasks"]
            )
        )
        before_schedule = {
            task["id"]: (
                task["planned_start_at"],
                task["planned_finish_at"],
                task["setup_hours"],
                task["duration_hours"],
            )
            for task in move_audit["before"]["tasks"]
        }
        after_schedule = {
            task["id"]: (
                task["planned_start_at"],
                task["planned_finish_at"],
                task["setup_hours"],
                task["duration_hours"],
            )
            for task in move_audit["after"]["tasks"]
        }
        assert before_schedule != after_schedule

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module("app.models.injection_schedule")
        with db_module.SessionLocal() as db:
            event = db.get(
                schedule_models.InjectionScheduleAuditEvent,
                published_audit["id"],
            )
            assert event is not None
            event.reason = "tampered"
            with pytest.raises(
                ValueError,
                match="append-only",
            ):
                db.commit()
            db.rollback()

        blocker_factory = "huakang-b"
        blocker_base = (
            f"/api/factories/{blocker_factory}/injection-schedule"
        )
        incomplete_machine = client.post(
            f"{blocker_base}/machines",
            json={
                "machine_code": "BLOCK-M1",
                "machine_class": "160T",
                "status": "available",
            },
        )
        assert incomplete_machine.status_code == 201, incomplete_machine.text
        incomplete_order = client.post(
            f"{blocker_base}/orders",
            json={
                "natural_key": "BLOCK-ORDER-NATURAL",
                "order_no": "BLOCK-ORDER",
                "product_code": "BLOCK-PRODUCT",
                "product_name": "资料不全订单",
                "mold_code": "MISSING-MOLD",
                "machine_class": "160T",
                "order_qty": 500,
                "produced_qty": 0,
                "status": "open",
                "imported_assigned_machine_code": "BLOCK-M1",
            },
        )
        assert incomplete_order.status_code == 201, incomplete_order.text
        blocked_version = client.post(
            f"{blocker_base}/versions",
            json={
                "name": "阻断草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert blocked_version.status_code == 201, blocked_version.text
        blocked_version_body = blocked_version.json()
        blocked_validation = client.post(
            f"{blocker_base}/versions/{blocked_version_body['id']}/validate",
            json={"expected_revision": 1},
        )
        assert blocked_validation.status_code == 200, blocked_validation.text
        assert blocked_validation.json()["status"] == "blocked"
        assert blocked_validation.json()["blocking_count"] > 0
        blocked_publish = client.post(
            f"{blocker_base}/versions/{blocked_version_body['id']}/publish",
            json={
                "expected_revision": 1,
                "validation_run_id": blocked_validation.json()["id"],
                "reason": "阻断项不得绕过发布",
            },
        )
        assert blocked_publish.status_code == 409
        assert blocked_publish.json()["detail"]["code"] == "publish_blocked"


def test_phase2_refresh_precheck_delivery_snapshot_and_import_derived_fields(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "injection_phase2_acceptance.db"
    with make_client(monkeypatch, database_path) as client:
        login_admin(client)
        factory_id = "huakang-a"
        base = f"/api/factories/{factory_id}/injection-schedule"
        masters = post_complete_master_data(
            client,
            factory_id,
            prefix="ACCEPT",
        )

        invalid_create = client.post(
            f"{base}/orders",
            json={
                "natural_key": "INVALID-DUE-DATE",
                "order_no": "INVALID-DUE-DATE",
                "delivery_due_date": "15/08/2026",
            },
        )
        assert invalid_create.status_code == 422, invalid_create.text
        invalid_patch = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json={
                "expected_revision": masters["order"]["revision"],
                "delivery_due_date": "2026/08/15",
            },
        )
        assert invalid_patch.status_code == 422, invalid_patch.text

        created = client.post(
            f"{base}/versions",
            json={
                "name": "主数据刷新验收草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert created.status_code == 201, created.text
        version = created.json()
        original_detail = client.get(
            f"{base}/versions/{version['id']}"
        ).json()
        assert len(original_detail["tasks"]) == 1
        original_task = original_detail["tasks"][0]
        assert original_task["delivery_due_date"] == "2026-08-15"

        validation = client.post(
            f"{base}/versions/{version['id']}/validate",
            json={"expected_revision": 1},
        )
        assert validation.status_code == 200, validation.text
        assert validation.json()["status"] == "passed"
        published = client.post(
            f"{base}/versions/{version['id']}/publish",
            json={
                "expected_revision": 1,
                "validation_run_id": validation.json()["id"],
                "reason": "建立主数据刷新验收基线",
            },
        )
        assert published.status_code == 200, published.text

        cloned = client.post(
            f"{base}/versions/{version['id']}/clone",
            json={
                "name": "主数据刷新验收副本",
                "reason": "验证刷新主数据快照",
            },
        )
        assert cloned.status_code == 201, cloned.text
        clone = cloned.json()
        clone_detail = client.get(f"{base}/versions/{clone['id']}").json()
        clone_task = clone_detail["tasks"][0]

        incompatible_machine = client.post(
            f"{base}/machines",
            json={
                "machine_code": "ACCEPT-INCOMPATIBLE",
                "machine_name": "已知不兼容机台",
                "workshop": "new",
                "machine_class": "80T",
                "tonnage_t": 80,
                "process_type": "standard",
                "robot_type": "none",
                "fixture_type": "special",
                "max_shot_weight_g": 50,
                "tie_bar_x_mm": 200,
                "tie_bar_y_mm": 200,
                "mold_thickness_min_mm": 100,
                "mold_thickness_max_mm": 600,
                "opening_stroke_mm": 700,
                "ejector_stroke_mm": 200,
                "status": "available",
                "available_at": "",
                "capabilities": ["cold-runner"],
                "material_rules": ["PC"],
                "quality_status": "verified",
            },
        )
        assert incompatible_machine.status_code == 201, incompatible_machine.text
        blocked_move = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "已知硬约束冲突必须立即拒绝",
                "commands": [
                    {
                        "type": "move",
                        "task_id": clone_task["id"],
                        "machine_id": incompatible_machine.json()["id"],
                        "target_index": 0,
                    }
                ],
            },
        )
        assert blocked_move.status_code == 422, blocked_move.text
        blocked_detail = blocked_move.json()["detail"]
        assert blocked_detail["code"] == "assignment_blocked"
        assert isinstance(blocked_detail["reasons"], list)
        joined_reasons = " ".join(blocked_detail["reasons"])
        for expected_reason in (
            "机台吨位低于模具要求",
            "模具整啤毛重超过机台安全射胶量",
            "模具尺寸超过机台柱距",
            "机台机械手能力低于模具要求",
            "夹具不符合模具要求",
            "机台不具备模具要求的全部工艺能力",
            "材料不符合机台材料限制",
        ):
            assert expected_reason in joined_reasons
        after_blocked_move = client.get(
            f"{base}/versions/{clone['id']}"
        ).json()
        assert after_blocked_move["version"]["revision"] == 1
        assert after_blocked_move["tasks"] == clone_detail["tasks"]

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module("app.models.injection_schedule")
        with db_module.SessionLocal() as db:
            order = db.get(
                schedule_models.InjectionOrderMaster,
                masters["order"]["id"],
            )
            assert order is not None
            order.provenance_json = (
                '{"source":"excel","manual_fields":["outstanding_qty"]}'
            )
            db.commit()

        changed_order = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json=order_update_payload(
                masters["order"],
                product_name="刷新后的产品名称",
                delivery_due_date="2026-08-18",
            ),
        )
        assert changed_order.status_code == 200, changed_order.text
        changed_order_body = changed_order.json()
        assert changed_order_body["outstanding_qty"] == 1000
        assert changed_order_body["provenance"]["manual_fields"] == [
            "delivery_due_date",
            "product_name",
        ]

        blocked_validation = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 1},
        )
        assert blocked_validation.status_code == 200, blocked_validation.text
        assert blocked_validation.json()["status"] == "blocked"
        assert any(
            item["constraint_code"] == "master_revision"
            and item["status"] == "fail"
            for item in blocked_validation.json()["items"]
        )

        refreshed = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "重新确认最新订单主数据",
                "request_id": "phase2-refresh-masters",
                "commands": [{"type": "refresh_masters"}],
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        refreshed_body = refreshed.json()
        assert refreshed_body["version"]["revision"] == 2
        assert refreshed_body["tasks"][0]["product_name"] == "刷新后的产品名称"
        assert refreshed_body["tasks"][0]["delivery_due_date"] == "2026-08-18"

        passed_after_refresh = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 2},
        )
        assert passed_after_refresh.status_code == 200, passed_after_refresh.text
        assert passed_after_refresh.json()["status"] == "passed"

        diff = client.get(f"{base}/versions/{clone['id']}/diff")
        assert diff.status_code == 200, diff.text
        diff_body = diff.json()
        assert diff_body["summary"]["changed_delivery_dates"] == 1
        assert diff_body["summary"]["delivery_date_change_count"] == 1
        changed_item = next(
            item
            for item in diff_body["items"]
            if item["order_id"] == masters["order"]["id"]
        )
        assert changed_item["before"]["delivery_due_date"] == "2026-08-15"
        assert changed_item["after"]["delivery_due_date"] == "2026-08-18"
        assert isinstance(changed_item["before"]["delivery_slack_hours"], float)
        assert isinstance(changed_item["after"]["delivery_slack_hours"], float)

        auth_service = importlib.import_module("app.services.auth")
        import_service = importlib.import_module(
            "app.services.injection_schedule_import"
        )
        actor = auth_service.AuthContext(
            id="test-import-actor",
            username="test-import-actor",
            display_name="测试导入员",
            roles=("general_manager",),
            role_codes=("general_manager",),
            permissions=frozenset(),
            factory_scopes=(factory_id,),
            department_scopes=("molding",),
        )
        merge_source = {
            "natural_key": changed_order_body["natural_key"],
            "order_no": changed_order_body["order_no"],
            "product_code": changed_order_body["product_code"],
            "product_name": "Excel 不应覆盖手工名称",
            "mold_code": changed_order_body["mold_code"],
            "color": changed_order_body["color"],
            "pigment": changed_order_body["pigment"],
            "material": changed_order_body["material"],
            "machine_class": changed_order_body["machine_class"],
            "order_qty": 1300,
            "produced_qty": 200,
            "outstanding_qty": 999999,
            "daily_target_qty": changed_order_body["daily_target_qty"],
            "delivery_due_date": "2026-09-01",
            "priority_flag": changed_order_body["priority_flag"],
            "status": "completed",
            "quality_status": changed_order_body["quality_status"],
            "assigned_machine_code": changed_order_body[
                "imported_assigned_machine_code"
            ],
            "plan_start_at": "",
            "plan_finish_at": "",
            "source_sheet": "test",
            "source_row": 1,
            "source_values": {},
            "assignment_state": "assigned",
        }
        with db_module.SessionLocal() as db:
            before_merge = db.get(
                schedule_models.InjectionOrderMaster,
                masters["order"]["id"],
            )
            assert before_merge is not None
            provenance = import_service.json_object(
                before_merge.provenance_json
            )
            provenance["manual_fields"] = sorted(
                set(provenance.get("manual_fields", [])) | {"order_qty"}
            )
            before_merge.provenance_json = import_service.canonical_json(
                provenance
            )
            import_service.merge_order_masters(
                db,
                factory_id,
                "TEST-IMPORT-BATCH",
                [merge_source],
                actor,
                import_service.now_text(),
            )
            db.commit()
            merged = db.get(
                schedule_models.InjectionOrderMaster,
                masters["order"]["id"],
            )
            assert merged is not None
            assert merged.product_name == "刷新后的产品名称"
            assert merged.delivery_due_date == "2026-08-18"
            assert merged.order_qty == 1000
            assert merged.produced_qty == 200
            assert merged.outstanding_qty == 800
            assert merged.status == "open"
            assert (
                "outstanding_qty"
                not in import_service.json_object(
                    merged.provenance_json
                )["manual_fields"]
            )
            merged.delivery_due_date = "18/08/2026"
            merged.revision += 1
            db.commit()
            db.refresh(merged)
            legacy_order_body = import_service.serialize_order(merged)

        legacy_invalid_validation = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 2},
        )
        assert legacy_invalid_validation.status_code == 200
        assert legacy_invalid_validation.json()["status"] == "blocked"
        assert any(
            item["constraint_code"] == "delivery_due_date"
            and item["status"] == "fail"
            for item in legacy_invalid_validation.json()["items"]
        )

        canceled_order = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json=order_update_payload(
                legacy_order_body,
                status="canceled",
                delivery_due_date="2026-08-18",
            ),
        )
        assert canceled_order.status_code == 200, canceled_order.text
        with db_module.SessionLocal() as db:
            import_service.merge_order_masters(
                db,
                factory_id,
                "TEST-IMPORT-BATCH-CANCELED",
                [
                    {
                        **merge_source,
                        "produced_qty": 300,
                        "status": "open",
                    }
                ],
                actor,
                import_service.now_text(),
            )
            db.commit()
            preserved_canceled = db.get(
                schedule_models.InjectionOrderMaster,
                masters["order"]["id"],
            )
            assert preserved_canceled is not None
            assert preserved_canceled.status == "canceled"
            assert preserved_canceled.outstanding_qty == 700
            preserved_canceled_body = import_service.serialize_order(
                preserved_canceled
            )

        canceled_refresh = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 2,
                "reason": "取消订单不得重新确认排产",
                "commands": [{"type": "refresh_masters"}],
            },
        )
        assert canceled_refresh.status_code == 422, canceled_refresh.text
        assert canceled_refresh.json()["detail"]["code"] == "assignment_blocked"
        assert any(
            "订单状态为 canceled" in reason
            for reason in canceled_refresh.json()["detail"]["reasons"]
        )
        after_canceled_refresh = client.get(
            f"{base}/versions/{clone['id']}"
        ).json()
        assert after_canceled_refresh["version"]["revision"] == 2

        canceled_validation = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 2},
        )
        assert canceled_validation.status_code == 200, canceled_validation.text
        canceled_validation_body = canceled_validation.json()
        assert canceled_validation_body["status"] == "blocked"
        assert any(
            item["constraint_code"] == "order_status"
            and item["status"] == "fail"
            for item in canceled_validation_body["items"]
        )
        canceled_publish = client.post(
            f"{base}/versions/{clone['id']}/publish",
            json={
                "expected_revision": 2,
                "validation_run_id": canceled_validation_body["id"],
                "reason": "取消订单不得发布",
            },
        )
        assert canceled_publish.status_code == 409
        assert canceled_publish.json()["detail"]["code"] == "publish_blocked"

        completed_order = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json=order_update_payload(
                preserved_canceled_body,
                status="completed",
            ),
        )
        assert completed_order.status_code == 200, completed_order.text
        completed_refresh = client.post(
            f"{base}/versions/{clone['id']}/commands",
            json={
                "expected_revision": 2,
                "reason": "已完成订单不得重新确认排产",
                "commands": [{"type": "refresh_masters"}],
            },
        )
        assert completed_refresh.status_code == 422, completed_refresh.text
        assert any(
            "订单状态为 completed" in reason
            for reason in completed_refresh.json()["detail"]["reasons"]
        )
        completed_validation = client.post(
            f"{base}/versions/{clone['id']}/validate",
            json={"expected_revision": 2},
        )
        assert completed_validation.status_code == 200
        assert any(
            item["constraint_code"] == "order_status"
            and item["status"] == "fail"
            and item["details"]["order_status"] == "completed"
            for item in completed_validation.json()["items"]
        )


def test_missing_mold_material_conflict_and_empty_draft_are_blocking(
    monkeypatch,
    tmp_path,
):
    with make_client(
        monkeypatch,
        tmp_path / "injection_empty_draft.db",
    ) as client:
        login_admin(client)
        factory_id = "huakang-b"
        base = f"/api/factories/{factory_id}/injection-schedule"
        machine = client.post(
            f"{base}/machines",
            json={
                "machine_code": "PC-ONLY-MACHINE",
                "machine_name": "仅允许 PC 的机台",
                "machine_class": "160T",
                "tonnage_t": 160,
                "status": "available",
                "material_rules": ["PC"],
                "quality_status": "verified",
            },
        )
        assert machine.status_code == 201, machine.text
        order = client.post(
            f"{base}/orders",
            json={
                "natural_key": "ABS-MISSING-MOLD",
                "order_no": "ABS-MISSING-MOLD",
                "product_code": "ABS-PRODUCT",
                "product_name": "缺模具但材料已知冲突",
                "mold_code": "MISSING-MOLD",
                "material": "ABS",
                "machine_class": "160T",
                "order_qty": 100,
                "produced_qty": 0,
                "daily_target_qty": 100,
                "delivery_due_date": "2026-08-20",
                "status": "open",
                "imported_assigned_machine_code": "",
                "quality_status": "verified",
            },
        )
        assert order.status_code == 201, order.text
        version = client.post(
            f"{base}/versions",
            json={
                "name": "空任务验收草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert version.status_code == 201, version.text
        version_body = version.json()
        assert client.get(
            f"{base}/versions/{version_body['id']}"
        ).json()["tasks"] == []

        blocked_assign = client.post(
            f"{base}/versions/{version_body['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "材料已知冲突不得人工绕过",
                "commands": [
                    {
                        "type": "assign",
                        "order_id": order.json()["id"],
                        "machine_id": machine.json()["id"],
                        "planned_qty": 100,
                        "manual_confirmation": True,
                        "manual_confirmation_reason": "主管确认资料",
                    }
                ],
            },
        )
        assert blocked_assign.status_code == 422, blocked_assign.text
        assert blocked_assign.json()["detail"]["code"] == "assignment_blocked"
        assert any(
            "材料不符合机台材料限制" in reason
            for reason in blocked_assign.json()["detail"]["reasons"]
        )
        assert client.get(
            f"{base}/versions/{version_body['id']}"
        ).json()["version"]["revision"] == 1

        empty_validation = client.post(
            f"{base}/versions/{version_body['id']}/validate",
            json={"expected_revision": 1},
        )
        assert empty_validation.status_code == 200, empty_validation.text
        empty_validation_body = empty_validation.json()
        assert empty_validation_body["status"] == "blocked"
        assert any(
            item["constraint_code"] == "schedule_has_tasks"
            and item["status"] == "fail"
            for item in empty_validation_body["items"]
        )
        empty_publish = client.post(
            f"{base}/versions/{version_body['id']}/publish",
            json={
                "expected_revision": 1,
                "validation_run_id": empty_validation_body["id"],
                "reason": "空草稿不得发布",
            },
        )
        assert empty_publish.status_code == 409
        assert empty_publish.json()["detail"]["code"] == "publish_blocked"


def test_task_snapshot_stays_authoritative_until_refresh_and_revision_guard(
    monkeypatch,
    tmp_path,
):
    with make_client(
        monkeypatch,
        tmp_path / "injection_snapshot_authority.db",
    ) as client:
        login_admin(client)
        factory_id = "huadeng"
        base = f"/api/factories/{factory_id}/injection-schedule"
        masters = post_complete_master_data(
            client,
            factory_id,
            prefix="SNAPSHOT",
        )
        cleared_due = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json={
                "expected_revision": masters["order"]["revision"],
                "delivery_due_date": "",
            },
        )
        assert cleared_due.status_code == 200, cleared_due.text
        version = client.post(
            f"{base}/versions",
            json={
                "name": "空交期快照草稿",
                "business_date": "2026-07-23",
                "plan_base_at": "2026-07-23 08:00:00",
            },
        )
        assert version.status_code == 201, version.text
        version_body = version.json()
        before_master_change = client.get(
            f"{base}/versions/{version_body['id']}"
        ).json()
        assert before_master_change["tasks"][0]["delivery_due_date"] == ""

        supplied_due = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json={
                "expected_revision": cleared_due.json()["revision"],
                "delivery_due_date": "2026-08-25",
            },
        )
        assert supplied_due.status_code == 200, supplied_due.text
        before_refresh = client.get(
            f"{base}/versions/{version_body['id']}"
        ).json()
        assert before_refresh["tasks"][0]["delivery_due_date"] == ""

        stale_validation = client.post(
            f"{base}/versions/{version_body['id']}/validate",
            json={"expected_revision": 1},
        )
        assert stale_validation.status_code == 200, stale_validation.text
        assert any(
            item["constraint_code"] == "master_revision"
            and item["status"] == "fail"
            for item in stale_validation.json()["items"]
        )
        refreshed = client.post(
            f"{base}/versions/{version_body['id']}/commands",
            json={
                "expected_revision": 1,
                "reason": "补齐交期后刷新快照",
                "commands": [{"type": "refresh_masters"}],
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["tasks"][0]["delivery_due_date"] == "2026-08-25"
        refreshed_validation = client.post(
            f"{base}/versions/{version_body['id']}/validate",
            json={"expected_revision": 2},
        )
        assert refreshed_validation.status_code == 200
        assert refreshed_validation.json()["status"] == "passed"
        published = client.post(
            f"{base}/versions/{version_body['id']}/publish",
            json={
                "expected_revision": 2,
                "validation_run_id": refreshed_validation.json()["id"],
                "reason": "发布交期快照验收版本",
            },
        )
        assert published.status_code == 200, published.text
        later_master_due = client.patch(
            f"{base}/orders/{masters['order']['id']}",
            json={
                "expected_revision": supplied_due.json()["revision"],
                "delivery_due_date": "2026-09-01",
            },
        )
        assert later_master_due.status_code == 200, later_master_due.text
        published_detail = client.get(
            f"{base}/versions/{version_body['id']}"
        ).json()
        assert published_detail["tasks"][0]["delivery_due_date"] == "2026-08-25"

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module("app.models.injection_schedule")
        schedule_service = importlib.import_module(
            "app.services.injection_schedule"
        )
        with db_module.SessionLocal() as db:
            task = db.get(
                schedule_models.InjectionScheduleTask,
                refreshed.json()["tasks"][0]["id"],
            )
            assert task is not None
            orders, machines, molds = (
                schedule_service.lock_task_master_dependencies(
                    db,
                    factory_id,
                    [task],
                )
            )
            revision_snapshot = schedule_service.master_revision_snapshot(
                orders,
                machines,
                molds,
            )
            orders[task.order_id].revision += 1
            db.flush()
            with pytest.raises(HTTPException) as error:
                schedule_service.verify_master_revision_snapshot(
                    db,
                    factory_id,
                    revision_snapshot,
                )
            assert error.value.status_code == 409
            assert error.value.detail["code"] == "master_revision_changed"
            db.rollback()
