import importlib
import sys
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = BACKEND_DIR / ".pytest-tmp"
ADMIN_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_path = TEST_TMP_DIR / f"injection_phase3_{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    main = importlib.import_module("app.main")
    main.init_db()
    return TestClient(main.app)


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def create_readonly_schedule_user(factory_id: str) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id="phase3-readonly",
                username="phase3-readonly",
                display_name="Phase3 只读用户",
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
                id="phase3-readonly:engineer",
                user_id="phase3-readonly",
                role_id="engineer",
                factory_id=factory_id,
                department="molding",
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id="phase3-readonly",
                primary_factory_id=factory_id,
                primary_department="molding",
                position="只读测试",
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        permission = db.scalar(
            select(auth_models.AuthPermission).where(
                auth_models.AuthPermission.code == "injection_schedule:read"
            )
        )
        assert permission is not None
        db.add(
            auth_models.AuthUserPermissionOverride(
                id="phase3-readonly:injection-read",
                user_id="phase3-readonly",
                permission_id=permission.id,
                effect="allow",
                factory_id=factory_id,
                department="*",
                status="active",
                valid_from="",
                valid_until="",
                reason="Phase3 推荐只读权限测试",
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


def configured_rules(client: TestClient, base: str) -> dict:
    virtual = client.get(f"{base}/rule-config")
    assert virtual.status_code == 200, virtual.text
    assert virtual.json()["revision"] == 0
    config = virtual.json()["config"]
    config["availability_calendar_verified_through"] = "2027-12-31 23:59:59"
    config["color_rank_dark_threshold"] = 5
    config["color_transition_matrix"] = [
        {"from_code": "*", "to_code": "*", "minutes": 30},
        {"from_code": "light", "to_code": "dark", "minutes": 10},
        {"from_code": "dark", "to_code": "light", "minutes": 80},
    ]
    config["material_transition_matrix"] = [
        {"from_code": "*", "to_code": "*", "minutes": 45},
        {"from_code": "PP", "to_code": "ABS", "minutes": 90},
        {"from_code": "ABS", "to_code": "PP", "minutes": 20},
    ]
    config["setup_minutes"] = [
        {
            "machine_class": "*",
            "same_mold_minutes": 0,
            "mold_change_minutes": 60,
        }
    ]
    response = client.patch(
        f"{base}/rule-config",
        headers={"x-request-id": "phase3-config-create"},
        json={
            "expected_revision": 0,
            "reason": "建立 Phase3 推荐规则",
            "config": config,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    return response.json()["config"]


def create_machine(
    client: TestClient,
    base: str,
    code: str,
    **overrides,
) -> dict:
    payload = {
        "machine_code": code,
        "machine_name": f"机台 {code}",
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
        "material_rules": ["ABS", "PP"],
        "quality_status": "verified",
    }
    payload.update(overrides)
    response = client.post(f"{base}/machines", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_mold(
    client: TestClient,
    base: str,
    code: str,
    *,
    material: str,
) -> dict:
    response = client.post(
        f"{base}/molds",
        json={
            "mold_code": code,
            "mold_name": f"模具 {code}",
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
            "material_rules": [material],
            "quality_status": "verified",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_order(
    client: TestClient,
    base: str,
    key: str,
    *,
    mold_code: str,
    color: str,
    color_rank: int,
    material: str,
    pigment: str = "",
    special_handling_reason: str = "",
) -> dict:
    response = client.post(
        f"{base}/orders",
        json={
            "natural_key": key,
            "order_no": key,
            "product_code": f"P-{key}",
            "product_name": f"产品 {key}",
            "mold_code": mold_code,
            "color": color,
            "color_rank": color_rank,
            "pigment": pigment,
            "material": material,
            "machine_class": "160T",
            "order_qty": 1000,
            "produced_qty": 0,
            "daily_target_qty": 1000,
            "delivery_due_date": "2026-08-15",
            "priority_flag": "normal",
            "downstream_urgency": 0.6,
            "warehouse_buffer_hours": 12,
            "downstream_buffer_hours": 12,
            "special_handling_reason": special_handling_reason,
            "status": "open",
            "imported_assigned_machine_code": "",
            "quality_status": "verified",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def apply_assign(
    client: TestClient,
    base: str,
    version_id: str,
    revision: int,
    order_id: str,
    machine_id: str,
) -> dict:
    response = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": revision,
            "reason": "建立候选机台相邻任务",
            "commands": [
                {
                    "type": "assign",
                    "order_id": order_id,
                    "machine_id": machine_id,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_rule_config_virtual_get_cas_audit_and_snapshot_revision(monkeypatch):
    client = make_client(monkeypatch)
    login_admin(client)
    factory_id = "huaxing"
    base = f"/api/factories/{factory_id}/injection-schedule"

    virtual = client.get(f"{base}/rule-config")
    assert virtual.status_code == 200
    assert virtual.json()["revision"] == 0
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.injection_schedule")
    with db_module.SessionLocal() as db:
        assert db.get(models.InjectionScheduleRuleConfig, factory_id) is None

    config_v1 = configured_rules(client, base)
    stale = client.patch(
        f"{base}/rule-config",
        json={
            "expected_revision": 0,
            "reason": "故意验证过期版本",
            "config": config_v1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    version = client.post(
        f"{base}/versions",
        json={
            "name": "Phase3 rules V1",
            "business_date": "2026-07-24",
            "plan_base_at": "2026-07-24 08:00:00",
        },
    )
    assert version.status_code == 201, version.text
    assert version.json()["rule_config_revision"] == 1
    version_id = version.json()["id"]

    config_v2 = dict(config_v1)
    config_v2["color_transition_matrix"] = [
        {"from_code": "*", "to_code": "*", "minutes": 35},
        {"from_code": "light", "to_code": "dark", "minutes": 5},
        {"from_code": "dark", "to_code": "light", "minutes": 95},
    ]
    updated = client.patch(
        f"{base}/rule-config",
        json={
            "expected_revision": 1,
            "reason": "调整有向颜色清洗时间",
            "config": config_v2,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    detail = client.get(f"{base}/versions/{version_id}")
    assert detail.json()["version"]["rule_config_revision"] == 1
    assert detail.json()["version"]["rules_snapshot"]["color_transition_matrix"] == (
        config_v1["color_transition_matrix"]
    )

    audit = client.get(f"{base}/audit")
    assert audit.status_code == 200
    config_events = [
        item for item in audit.json() if item["entity_type"] == "rule_config"
    ]
    assert {item["action"] for item in config_events[:2]} == {"updated", "created"}
    updated_event = next(item for item in config_events if item["action"] == "updated")
    assert updated_event["before"]["revision"] == 1
    assert updated_event["after"]["revision"] == 2

    create_machine(client, base, "SNAPSHOT-M1")
    mold = create_mold(client, base, "SNAPSHOT-MOULD", material="ABS")
    order = create_order(
        client,
        base,
        "SNAPSHOT-ORDER",
        mold_code=mold["mold_code"],
        color="black",
        color_rank=9,
        pigment="C09",
        material="ABS",
    )
    recommendation = client.get(
        f"{base}/versions/{version_id}/orders/{order['id']}/recommendations"
    )
    assert recommendation.status_code == 200, recommendation.text
    assert recommendation.json()["rule_config_revision"] == 1
    assert recommendation.json()["current_rule_config_revision"] == 2
    assert recommendation.json()["uses_version_rule_snapshot"] is True


def test_recommendation_read_permissions_and_factory_scope_do_not_leak(monkeypatch):
    client = make_client(monkeypatch)
    login_admin(client)
    factory_id = "huaxing"
    base = f"/api/factories/{factory_id}/injection-schedule"
    config = configured_rules(client, base)
    create_machine(client, base, "AUTH-M1")
    mold = create_mold(client, base, "AUTH-MOULD", material="ABS")
    order = create_order(
        client,
        base,
        "AUTH-ORDER",
        mold_code=mold["mold_code"],
        color="black",
        color_rank=9,
        pigment="C09",
        material="ABS",
    )
    version = client.post(
        f"{base}/versions",
        json={
            "name": "权限边界草稿",
            "business_date": "2026-07-24",
            "plan_base_at": "2026-07-24 08:00:00",
        },
    ).json()
    create_readonly_schedule_user(factory_id)
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={"username": "phase3-readonly", "password": "123456"},
    )
    assert login.status_code == 200, login.text

    assert client.get(f"{base}/rule-config").status_code == 200
    recommendation = client.get(
        f"{base}/versions/{version['id']}/orders/{order['id']}/recommendations"
    )
    assert recommendation.status_code == 200, recommendation.text
    denied_config = client.patch(
        f"{base}/rule-config",
        json={
            "expected_revision": 1,
            "reason": "只读用户不得更新规则",
            "config": config,
        },
    )
    assert denied_config.status_code == 403
    denied_assign = client.post(
        f"{base}/versions/{version['id']}/commands",
        json={
            "expected_revision": 1,
            "reason": "只读用户不得落单",
            "commands": [
                {
                    "type": "assign",
                    "order_id": order["id"],
                    "machine_id": recommendation.json()["candidates"][0][
                        "machine_id"
                    ],
                    "planned_qty": 100,
                }
            ],
        },
    )
    assert denied_assign.status_code == 403

    client.cookies.clear()
    login_admin(client)
    foreign_base = "/api/factories/huadeng/injection-schedule"
    assert client.get(
        f"{foreign_base}/versions/{version['id']}/orders/{order['id']}/recommendations"
    ).status_code == 404
    assert client.get(
        f"{base}/versions/{version['id']}/orders/not-this-factory/recommendations"
    ).status_code == 404


def test_recommendation_ranking_manual_review_and_server_snapshot_assign(monkeypatch):
    client = make_client(monkeypatch)
    login_admin(client)
    factory_id = "huaxing"
    base = f"/api/factories/{factory_id}/injection-schedule"
    configured_rules(client, base)

    machine1 = create_machine(client, base, "M1")
    machine2 = create_machine(client, base, "M2")
    machine3 = create_machine(client, base, "M3", max_shot_weight_g=50)
    machine4 = create_machine(client, base, "M4", max_shot_weight_g=None)
    mold_abs = create_mold(client, base, "MOULD-ABS", material="ABS")
    mold_pp = create_mold(client, base, "MOULD-PP", material="PP")
    previous_same = create_order(
        client,
        base,
        "PREV-SAME",
        mold_code=mold_abs["mold_code"],
        color="white",
        color_rank=1,
        material="ABS",
        pigment="C01",
    )
    previous_other = create_order(
        client,
        base,
        "PREV-OTHER",
        mold_code=mold_pp["mold_code"],
        color="black",
        color_rank=9,
        material="PP",
        pigment="C09",
    )
    target = create_order(
        client,
        base,
        "TARGET",
        mold_code=mold_abs["mold_code"],
        color="black",
        color_rank=9,
        material="ABS",
        pigment="C09",
        special_handling_reason="客户指定人工留样",
    )
    version = client.post(
        f"{base}/versions",
        json={
            "name": "Phase3 recommendation",
            "business_date": "2026-07-24",
            "plan_base_at": "2026-07-24 08:00:00",
        },
    )
    assert version.status_code == 201, version.text
    version_id = version.json()["id"]
    body = apply_assign(
        client,
        base,
        version_id,
        1,
        previous_same["id"],
        machine1["id"],
    )
    body = apply_assign(
        client,
        base,
        version_id,
        body["version"]["revision"],
        previous_other["id"],
        machine2["id"],
    )
    revision = body["version"]["revision"]
    existing_m1 = next(
        item for item in body["tasks"] if item["machine_id"] == machine1["id"]
    )

    response = client.get(
        f"{base}/versions/{version_id}/orders/{target['id']}/recommendations",
        params={"planned_qty": 250, "limit": 20},
    )
    assert response.status_code == 200, response.text
    recommendation = response.json()
    assert recommendation["planned_qty"] == 250
    assert recommendation["version_revision"] == revision
    assert recommendation["rule_config_revision"] == 1
    candidates = {item["machine_code"]: item for item in recommendation["candidates"]}
    assert candidates["M1"]["status"] == "eligible"
    assert candidates["M1"]["rank"] == 1
    assert candidates["M1"]["score"]["transition"]["same_mold"] is True
    assert candidates["M1"]["score"]["transition"]["previous_task_id"] == (
        existing_m1["id"]
    )
    transition = candidates["M1"]["score"]["transition"]
    assert existing_m1["color"] == "C01"
    assert existing_m1["color_rank"] == 1
    assert transition["previous_color"] == "C01"
    assert transition["previous_color_rank"] == 1
    assert transition["target_color"] == "C09"
    assert transition["target_color_rank"] == 9
    assert transition["color_matrix_match"] == "alias"
    assert transition["color_minutes"] == 10
    assert transition["setup_minutes_before"] == 10
    assert transition["setup_minutes_after"] == 0
    assert transition["after_color_minutes"] == 0
    assert transition["after_material_minutes"] == 0
    assert transition["after_color_matrix_match"] == "last_task"
    assert transition["after_material_matrix_match"] == "last_task"
    assert transition["replaced_setup_minutes"] == 0
    assert transition["setup_minutes_delta"] == 10
    assert candidates["M1"]["score"]["estimated"]["duration_hours"] == 6
    special = next(
        item
        for item in candidates["M1"]["score"]["breakdown"]
        if item["code"] == "special_handling_penalty"
    )
    assert special["weight"] == 8
    assert special["weighted_score"] == -8
    assert candidates["M3"]["status"] == "blocked"
    assert candidates["M3"]["score"] is None
    assert any(
        item["code"] == "shot_capacity" and item["status"] == "fail"
        for item in candidates["M3"]["hard_constraints"]
    )
    assert candidates["M4"]["status"] == "manual_review"
    assert candidates["M4"]["eligible"] is False
    assert candidates["M4"]["auto_publish_allowed"] is False
    assert candidates["M4"]["requires_manual_confirmation"] is True
    assert candidates["M4"]["rank"] is None
    assert candidates["M4"]["advisory_rank"] is not None
    assert candidates["M4"]["score"]["advisory"] is True

    selected = candidates["M1"]
    before_failed_command = client.get(f"{base}/versions/{version_id}").json()
    direct_blocked = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": revision,
            "reason": "验证直接命令不能绕过射胶量硬约束",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine3["id"],
                    "planned_qty": 100,
                }
            ],
        },
    )
    assert direct_blocked.status_code == 422
    assert direct_blocked.json()["detail"]["code"] == "assignment_blocked"
    after_direct_block = client.get(f"{base}/versions/{version_id}").json()
    assert after_direct_block["version"]["revision"] == revision
    assert after_direct_block["tasks"] == before_failed_command["tasks"]

    updated_target = client.patch(
        f"{base}/orders/{target['id']}",
        json={
            "expected_revision": target["revision"],
            "product_name": "产品 TARGET（主数据已更新）",
        },
    )
    assert updated_target.status_code == 200, updated_target.text
    audit_count_before_stale = len(client.get(f"{base}/audit").json())
    stale_assignment = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": revision,
            "reason": "验证旧推荐上下文原子回滚",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine1["id"],
                    "target_index": selected["target_index"],
                    "planned_qty": 250,
                    "recommendation_context_hash": selected[
                        "recommendation_context_hash"
                    ],
                }
            ],
        },
    )
    assert stale_assignment.status_code == 409, stale_assignment.text
    assert stale_assignment.json()["detail"]["code"] == "recommendation_stale"
    after_stale = client.get(f"{base}/versions/{version_id}").json()
    assert after_stale["version"]["revision"] == revision
    assert after_stale["tasks"] == before_failed_command["tasks"]
    assert len(client.get(f"{base}/audit").json()) == audit_count_before_stale

    refreshed = client.get(
        f"{base}/versions/{version_id}/orders/{target['id']}/recommendations",
        params={"planned_qty": 250, "limit": 20},
    )
    assert refreshed.status_code == 200, refreshed.text
    selected = next(
        item
        for item in refreshed.json()["candidates"]
        if item["machine_code"] == "M1"
    )
    assert selected["recommendation_context_hash"] != (
        candidates["M1"]["recommendation_context_hash"]
    )
    assigned = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": revision,
            "reason": "采用服务端首选机台推荐",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine1["id"],
                    "target_index": selected["target_index"],
                    "planned_qty": 250,
                    "recommendation_context_hash": selected[
                        "recommendation_context_hash"
                    ],
                }
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    assigned_body = assigned.json()
    unchanged_existing = next(
        item for item in assigned_body["tasks"] if item["id"] == existing_m1["id"]
    )
    assert (
        unchanged_existing["planned_start_at"],
        unchanged_existing["planned_finish_at"],
    ) == (
        existing_m1["planned_start_at"],
        existing_m1["planned_finish_at"],
    )
    recommended_task = next(
        item
        for item in assigned_body["tasks"]
        if item["order_id"] == target["id"]
    )
    assert recommended_task["source"] == "recommendation"
    assert recommended_task["color"] == "C09"
    assert recommended_task["color_rank"] == 9
    assert recommended_task["recommendation_score"] == selected["score"]["total"]
    assert recommended_task["score_breakdown"] == selected["score"]["breakdown"]
    assert recommended_task["constraint_snapshot"] == selected["hard_constraints"]
    assert recommended_task["planned_start_at"] == (
        selected["score"]["estimated"]["production_start_at"]
    )
    assert recommended_task["planned_finish_at"] == (
        selected["score"]["estimated"]["finish_at"]
    )
    assert recommended_task["setup_hours"] == (
        selected["score"]["transition"]["setup_minutes_before"] / 60
    )

    manual_response = client.get(
        f"{base}/versions/{version_id}/orders/{target['id']}/recommendations",
        params={"planned_qty": 100},
    )
    assert manual_response.status_code == 200, manual_response.text
    manual_candidate = next(
        item
        for item in manual_response.json()["candidates"]
        if item["machine_code"] == "M4"
    )
    without_confirmation = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": assigned_body["version"]["revision"],
            "reason": "验证未知约束不能静默采用",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine4["id"],
                    "target_index": manual_candidate["target_index"],
                    "planned_qty": 100,
                    "recommendation_context_hash": manual_candidate[
                        "recommendation_context_hash"
                    ],
                }
            ],
        },
    )
    assert without_confirmation.status_code == 422
    assert (
        without_confirmation.json()["detail"]["code"]
        == "manual_confirmation_required"
    )

    with_confirmation = client.post(
        f"{base}/versions/{version_id}/commands",
        json={
            "expected_revision": assigned_body["version"]["revision"],
            "reason": "主管确认射胶量待补后仅保存草稿",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine4["id"],
                    "target_index": manual_candidate["target_index"],
                    "planned_qty": 100,
                    "manual_confirmation": True,
                    "manual_confirmation_reason": "主管确认仅作草稿",
                    "recommendation_context_hash": manual_candidate[
                        "recommendation_context_hash"
                    ],
                }
            ],
        },
    )
    assert with_confirmation.status_code == 200, with_confirmation.text
    manual_task = next(
        item
        for item in with_confirmation.json()["tasks"]
        if item["order_id"] == target["id"]
        and item["machine_id"] == machine4["id"]
    )
    assert manual_task["risk_level"] == "unknown"
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.injection_schedule")
    with db_module.SessionLocal() as db:
        legacy_task = db.get(
            models.InjectionScheduleTask,
            recommended_task["id"],
        )
        assert legacy_task is not None
        legacy_task.setup_hours = 0
        db.commit()
    validation = client.post(
        f"{base}/versions/{version_id}/validate",
        json={"expected_revision": with_confirmation.json()["version"]["revision"]},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["status"] == "blocked"
    assert any(
        item["constraint_code"] == "shot_capacity"
        and item["status"] == "unknown"
        for item in validation.json()["items"]
    )
    assert any(
        item["constraint_code"] == "transition_setup_consistency"
        and item["status"] == "fail"
        for item in validation.json()["items"]
    )
    publish = client.post(
        f"{base}/versions/{version_id}/publish",
        json={
            "expected_revision": with_confirmation.json()["version"]["revision"],
            "validation_run_id": validation.json()["id"],
            "reason": "验证未知硬约束不能发布",
        },
    )
    assert publish.status_code == 409
    assert publish.json()["detail"]["code"] == "publish_blocked"


def test_directed_transition_matrix_and_unknown_values_are_not_same():
    from app.services.injection_schedule_rules import (
        color_code,
        transition_minutes,
    )

    rows = [
        {"from_code": "*", "to_code": "*", "minutes": 30},
        {"from_code": "light", "to_code": "dark", "minutes": 10},
        {"from_code": "dark", "to_code": "light", "minutes": 80},
    ]
    assert color_code("white", 1, dark_threshold=5) == "light"
    assert color_code("black", 9, dark_threshold=5) == "dark"
    light_dark, _ = transition_minutes(
        rows,
        "白",
        "黑",
        from_alias="light",
        to_alias="dark",
    )
    dark_light, _ = transition_minutes(
        rows,
        "黑",
        "白",
        from_alias="dark",
        to_alias="light",
    )
    missing, details = transition_minutes(rows, "unknown", "unknown")
    assert light_dark == 10
    assert dark_light == 80
    assert missing == 30
    assert details["match"] == "fallback"

    from app.services.injection_schedule_validation import validate_machine_class

    class_code_result = validate_machine_class(
        "",
        SimpleNamespace(machine_class="16A", tonnage_t=280),
        SimpleNamespace(machine_class="14A"),
        SimpleNamespace(machine_class=""),
    )
    assert class_code_result["status"] == "unknown"
    explicit_tonnage_result = validate_machine_class(
        "",
        SimpleNamespace(machine_class="16A", tonnage_t=280),
        SimpleNamespace(machine_class="160T"),
        SimpleNamespace(machine_class=""),
    )
    assert explicit_tonnage_result["status"] == "pass"


def test_adjacent_snapshot_unknown_and_missing_data_policy_cannot_be_bypassed(
    monkeypatch,
):
    client = make_client(monkeypatch)
    login_admin(client)
    factory_id = "huaxing"
    base = f"/api/factories/{factory_id}/injection-schedule"
    config_v1 = configured_rules(client, base)
    machine = create_machine(client, base, "POLICY-M1")
    mold = create_mold(client, base, "POLICY-MOULD", material="ABS")
    previous = create_order(
        client,
        base,
        "POLICY-PREV",
        mold_code=mold["mold_code"],
        color="white",
        color_rank=1,
        pigment="C01",
        material="ABS",
    )
    target = create_order(
        client,
        base,
        "POLICY-TARGET",
        mold_code=mold["mold_code"],
        color="black",
        color_rank=9,
        pigment="C09",
        material="ABS",
    )

    version_v1 = client.post(
        f"{base}/versions",
        json={
            "name": "允许未知资料人工确认",
            "business_date": "2026-07-24",
            "plan_base_at": "2026-07-24 08:00:00",
        },
    ).json()
    assigned_v1 = apply_assign(
        client,
        base,
        version_v1["id"],
        1,
        previous["id"],
        machine["id"],
    )
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.injection_schedule")
    with db_module.SessionLocal() as db:
        previous_task = db.scalar(
            select(models.InjectionScheduleTask).where(
                models.InjectionScheduleTask.version_id == version_v1["id"],
                models.InjectionScheduleTask.order_id == previous["id"],
            )
        )
        assert previous_task is not None
        previous_task.color_snapshot = ""
        db.commit()

    allowed = client.get(
        f"{base}/versions/{version_v1['id']}/orders/{target['id']}/recommendations"
    )
    assert allowed.status_code == 200, allowed.text
    allowed_candidate = allowed.json()["candidates"][0]
    assert allowed_candidate["status"] == "manual_review"
    adjacent_constraint = next(
        item
        for item in allowed_candidate["hard_constraints"]
        if item["code"] == "transition_data"
    )
    assert adjacent_constraint["status"] == "unknown"
    assert {
        (item["role"], item["task_id"], item["field"])
        for item in adjacent_constraint["details"]["missing"]
    } == {
        ("previous", assigned_v1["tasks"][0]["id"], "color_snapshot"),
    }

    config_v2 = dict(config_v1)
    config_v2["allow_missing_data_in_draft_with_manual_confirmation"] = False
    updated_config = client.patch(
        f"{base}/rule-config",
        json={
            "expected_revision": 1,
            "reason": "禁止未知硬约束进入草稿",
            "config": config_v2,
        },
    )
    assert updated_config.status_code == 200, updated_config.text
    assert updated_config.json()["revision"] == 2

    version_v2_response = client.post(
        f"{base}/versions",
        json={
            "name": "禁止未知资料草稿",
            "business_date": "2026-07-24",
            "plan_base_at": "2026-07-24 08:00:00",
        },
    )
    assert version_v2_response.status_code == 201, version_v2_response.text
    version_v2 = version_v2_response.json()
    assert version_v2["rule_config_revision"] == 2
    assigned_v2 = apply_assign(
        client,
        base,
        version_v2["id"],
        1,
        previous["id"],
        machine["id"],
    )
    with db_module.SessionLocal() as db:
        previous_task = db.scalar(
            select(models.InjectionScheduleTask).where(
                models.InjectionScheduleTask.version_id == version_v2["id"],
                models.InjectionScheduleTask.order_id == previous["id"],
            )
        )
        assert previous_task is not None
        previous_task.material_snapshot = ""
        db.commit()

    forbidden = client.get(
        f"{base}/versions/{version_v2['id']}/orders/{target['id']}/recommendations"
    )
    assert forbidden.status_code == 200, forbidden.text
    forbidden_candidate = forbidden.json()["candidates"][0]
    assert forbidden_candidate["status"] == "blocked"
    assert forbidden_candidate["score"] is None
    assert any(
        item["code"] == "transition_data" and item["status"] == "unknown"
        for item in forbidden_candidate["hard_constraints"]
    )
    assert any(
        item["code"] == "missing_data_policy" and item["status"] == "fail"
        for item in forbidden_candidate["hard_constraints"]
    )

    before_direct = client.get(f"{base}/versions/{version_v2['id']}").json()
    direct_with_confirmation = client.post(
        f"{base}/versions/{version_v2['id']}/commands",
        json={
            "expected_revision": assigned_v2["version"]["revision"],
            "reason": "人工确认也不得绕过禁用规则",
            "commands": [
                {
                    "type": "assign",
                    "order_id": target["id"],
                    "machine_id": machine["id"],
                    "target_index": 1,
                    "planned_qty": 100,
                    "manual_confirmation": True,
                    "manual_confirmation_reason": "主管要求强行确认",
                }
            ],
        },
    )
    assert direct_with_confirmation.status_code == 422
    assert (
        direct_with_confirmation.json()["detail"]["code"]
        == "missing_data_policy_blocked"
    )
    after_direct = client.get(f"{base}/versions/{version_v2['id']}").json()
    assert after_direct["version"]["revision"] == (
        before_direct["version"]["revision"]
    )
    assert after_direct["tasks"] == before_direct["tasks"]

    with db_module.SessionLocal() as db:
        changed_machine = db.get(
            models.InjectionMachineMaster,
            machine["id"],
        )
        assert changed_machine is not None
        changed_machine.max_shot_weight_g = None
        changed_machine.revision += 1
        db.commit()
    for command in (
        {
            "type": "reorder",
            "task_id": assigned_v2["tasks"][0]["id"],
            "target_index": 0,
            "manual_confirmation": True,
            "manual_confirmation_reason": "主管确认仍尝试排序",
        },
        {
            "type": "split",
            "task_id": assigned_v2["tasks"][0]["id"],
            "split_qty": 50,
            "machine_id": machine["id"],
            "target_index": 0,
            "manual_confirmation": True,
            "manual_confirmation_reason": "主管确认仍尝试拆单",
        },
    ):
        bypass = client.post(
            f"{base}/versions/{version_v2['id']}/commands",
            json={
                "expected_revision": assigned_v2["version"]["revision"],
                "reason": "未知主数据不得通过命令类型绕过禁用规则",
                "commands": [command],
            },
        )
        assert bypass.status_code == 422, bypass.text
        assert bypass.json()["detail"]["code"] in {
            "assignment_blocked",
            "missing_data_policy_blocked",
        }
        unchanged = client.get(f"{base}/versions/{version_v2['id']}").json()
        assert unchanged["version"]["revision"] == (
            assigned_v2["version"]["revision"]
        )
        assert unchanged["tasks"] == before_direct["tasks"]


def test_downstream_setup_window_is_checked_against_unavailable_calendar():
    from app.core.time import parse_business_timestamp
    from app.services.injection_schedule_recommendation import (
        _time_window_constraint,
    )
    from app.services.injection_schedule_rules import normalize_rule_config

    rules = normalize_rule_config(
        {
            "availability_calendar_verified_through": "2027-12-31 23:59:59",
        }
    )
    constraint, _ = _time_window_constraint(
        SimpleNamespace(plan_base_at="2026-07-24 08:00:00"),
        SimpleNamespace(
            daily_target_qty=1000,
            delivery_due_date="2026-08-15",
            warehouse_buffer_hours=0,
            downstream_buffer_hours=0,
        ),
        SimpleNamespace(available_at=""),
        None,
        SimpleNamespace(planned_start_at="2026-07-24 12:00:00"),
        10,
        {
            "setup_minutes_before": 0,
            "setup_minutes_after": 80,
        },
        rules,
        plan_base=parse_business_timestamp("2026-07-24 08:00:00"),
        machine_available_at=None,
        parsed_windows=[
            (
                parse_business_timestamp("2026-07-24 11:00:00"),
                parse_business_timestamp("2026-07-24 11:30:00"),
                "计划保养",
            )
        ],
        calendar_horizon=parse_business_timestamp("2027-12-31 23:59:59"),
    )
    assert constraint["status"] == "fail"
    assert "后序任务的换型占机时间命中停机窗口" in constraint["message"]
    assert constraint["details"]["downstream_setup_start_at"] == (
        "2026-07-24 10:40:00"
    )
    assert constraint["details"]["downstream_setup_unavailable_windows"] == [
        {
            "start_at": "2026-07-24 11:00:00",
            "end_at": "2026-07-24 11:30:00",
            "reason": "计划保养",
        }
    ]
    horizon_constraint, _ = _time_window_constraint(
        SimpleNamespace(plan_base_at="2026-07-24 08:00:00"),
        SimpleNamespace(
            daily_target_qty=1000,
            delivery_due_date="2026-08-15",
            warehouse_buffer_hours=0,
            downstream_buffer_hours=0,
        ),
        SimpleNamespace(available_at=""),
        None,
        SimpleNamespace(planned_start_at="2026-07-24 12:00:00"),
        10,
        {
            "setup_minutes_before": 0,
            "setup_minutes_after": 80,
        },
        rules,
        plan_base=parse_business_timestamp("2026-07-24 08:00:00"),
        machine_available_at=None,
        parsed_windows=[],
        calendar_horizon=parse_business_timestamp("2026-07-24 11:30:00"),
    )
    assert horizon_constraint["status"] == "unknown"
    assert "后序换型占机时间超出" in horizon_constraint["message"]
    assert horizon_constraint["details"]["downstream_setup_end_at"] == (
        "2026-07-24 12:00:00"
    )


def test_76_machines_1500_tasks_recompute_and_recommend_are_bounded(monkeypatch):
    make_client(monkeypatch)
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.injection_schedule")
    auth_service = importlib.import_module("app.services.auth")
    schedule_service = importlib.import_module("app.services.injection_schedule")
    recommendation_service = importlib.import_module(
        "app.services.injection_schedule_recommendation"
    )
    import_service = importlib.import_module(
        "app.services.injection_schedule_import"
    )
    rules_service = importlib.import_module(
        "app.services.injection_schedule_rules"
    )
    factory_id = "huaxing"
    version_id = "PERF-VERSION"
    mold_id = "PERF-MOLD"
    rules = rules_service.normalize_rule_config(
        {
            "availability_calendar_verified_through": "2027-12-31 23:59:59",
        }
    )
    actor = auth_service.AuthContext(
        id="perf-user",
        username="perf-user",
        display_name="性能测试",
        roles=("general_manager",),
        role_codes=("general_manager",),
        permissions=frozenset(),
        factory_scopes=(factory_id,),
        department_scopes=("molding",),
    )

    with db_module.SessionLocal() as db:
        machines = [
            models.InjectionMachineMaster(
                id=f"PERF-M-{index:03d}",
                factory_id=factory_id,
                machine_code=f"PM-{index:03d}",
                machine_name=f"性能机台 {index}",
                machine_class="160T",
                tonnage_t=160,
                screw_type="standard",
                robot_type="three-axis",
                fixture_type="standard",
                max_shot_weight_g=1000,
                tie_bar_x_mm=800,
                tie_bar_y_mm=800,
                mold_thickness_min_mm=100,
                mold_thickness_max_mm=600,
                opening_stroke_mm=700,
                status="available",
                capabilities_json='["hot-runner"]',
                material_rules_json='["ABS"]',
                quality_status="verified",
            )
            for index in range(76)
        ]
        mold = models.InjectionMoldMaster(
            id=mold_id,
            factory_id=factory_id,
            mold_code="PERF-MOULD",
            normalized_mold_code="PERF-MOULD",
            machine_class="160T",
            robot_type="three-axis",
            fixture_type="standard",
            length_mm=400,
            width_mm=300,
            gross_shot_weight_g=100,
            mold_thickness_mm=250,
            required_opening_stroke_mm=300,
            required_screw_type="standard",
            required_capabilities_json='["hot-runner"]',
            material_rules_json='["ABS"]',
            quality_status="verified",
        )
        version = models.InjectionScheduleVersion(
            id=version_id,
            factory_id=factory_id,
            version_no=1,
            name="1500任务性能边界",
            status="draft",
            revision=1,
            business_date="2026-07-24",
            plan_base_at="2026-07-24 08:00:00",
            rules_snapshot_json=import_service.canonical_json(rules),
            rule_config_revision=1,
            created_by=actor.id,
            created_by_name=actor.display_name,
            created_at="2026-07-23 23:00:00",
        )
        orders = []
        tasks = []
        for index in range(1500):
            order_id = f"PERF-O-{index:04d}"
            machine = machines[index % len(machines)]
            orders.append(
                models.InjectionOrderMaster(
                    id=order_id,
                    factory_id=factory_id,
                    natural_key=order_id,
                    order_no=order_id,
                    product_code=f"PERF-P-{index:04d}",
                    product_name=f"性能订单 {index}",
                    mold_code=mold.mold_code,
                    color="black" if index % 2 else "white",
                    pigment="C09" if index % 2 else "C01",
                    color_rank=9 if index % 2 else 1,
                    material="ABS",
                    machine_class="160T",
                    order_qty=100,
                    outstanding_qty=100,
                    daily_target_qty=1000,
                    delivery_due_date="2026-12-31",
                    status="open",
                    quality_status="verified",
                )
            )
            tasks.append(
                models.InjectionScheduleTask(
                    id=f"PERF-T-{index:04d}",
                    factory_id=factory_id,
                    version_id=version_id,
                    order_id=order_id,
                    machine_id=machine.id,
                    mold_id=mold_id,
                    sequence_no=index // len(machines),
                    planned_qty=10,
                    mold_code_snapshot=mold.mold_code,
                    color_snapshot="C09" if index % 2 else "C01",
                    color_rank_snapshot=9 if index % 2 else 1,
                    material_snapshot="ABS",
                    machine_code_snapshot=machine.machine_code,
                    order_revision_snapshot=1,
                    machine_revision_snapshot=1,
                    mold_revision_snapshot=1,
                    revision=1,
                )
            )
        target = models.InjectionOrderMaster(
            id="PERF-TARGET",
            factory_id=factory_id,
            natural_key="PERF-TARGET",
            order_no="PERF-TARGET",
            product_code="PERF-TARGET",
            product_name="推荐性能目标",
            mold_code=mold.mold_code,
            color="black",
            pigment="C09",
            color_rank=9,
            material="ABS",
            machine_class="160T",
            order_qty=100,
            outstanding_qty=100,
            daily_target_qty=1000,
            delivery_due_date="2026-12-31",
            status="open",
            quality_status="verified",
        )
        db.add_all([*machines, mold, version, *orders, target, *tasks])
        db.commit()

        recompute_sql = 0

        def count_recompute(*_args):
            nonlocal recompute_sql
            recompute_sql += 1

        event.listen(
            db_module.engine,
            "before_cursor_execute",
            count_recompute,
        )
        started = perf_counter()
        try:
            schedule_service.recompute_lanes(
                db,
                version,
                {machine.id for machine in machines},
                actor,
                "2026-07-23 23:10:00",
            )
        finally:
            event.remove(
                db_module.engine,
                "before_cursor_execute",
                count_recompute,
            )
        recompute_elapsed = perf_counter() - started
        assert recompute_sql <= 6
        assert recompute_elapsed < 10
        db.commit()
        revisions_after_change = {
            task_id: revision
            for task_id, revision in db.execute(
                select(
                    models.InjectionScheduleTask.id,
                    models.InjectionScheduleTask.revision,
                ).where(
                    models.InjectionScheduleTask.version_id == version_id
                )
            ).all()
        }
        schedule_service.recompute_lanes(
            db,
            version,
            {machine.id for machine in machines},
            actor,
            "2026-07-23 23:11:00",
        )
        db.flush()
        assert {
            task_id: revision
            for task_id, revision in db.execute(
                select(
                    models.InjectionScheduleTask.id,
                    models.InjectionScheduleTask.revision,
                ).where(
                    models.InjectionScheduleTask.version_id == version_id
                )
            ).all()
        } == revisions_after_change

        task_count_before = db.scalar(
            select(func.count(models.InjectionScheduleTask.id)).where(
                models.InjectionScheduleTask.version_id == version_id
            )
        )
        audit_count_before = db.scalar(
            select(func.count(models.InjectionScheduleAuditEvent.id)).where(
                models.InjectionScheduleAuditEvent.factory_id == factory_id
            )
        )
        version_revision_before = db.get(
            models.InjectionScheduleVersion,
            version_id,
        ).revision
        recommendation_sql = 0

        def count_recommendation(*_args):
            nonlocal recommendation_sql
            recommendation_sql += 1

        event.listen(
            db_module.engine,
            "before_cursor_execute",
            count_recommendation,
        )
        started = perf_counter()
        try:
            response = recommendation_service.recommend_order_machines(
                db,
                factory_id,
                version_id,
                target.id,
                limit=100,
                planned_qty=10,
            )
        finally:
            event.remove(
                db_module.engine,
                "before_cursor_execute",
                count_recommendation,
            )
        recommendation_elapsed = perf_counter() - started
        assert response["total_candidates"] == 76
        assert len(response["candidates"]) == 76
        assert recommendation_sql <= 6
        assert recommendation_elapsed < 10
        assert db.scalar(
            select(func.count(models.InjectionScheduleTask.id)).where(
                models.InjectionScheduleTask.version_id == version_id
            )
        ) == task_count_before
        assert db.scalar(
            select(func.count(models.InjectionScheduleAuditEvent.id)).where(
                models.InjectionScheduleAuditEvent.factory_id == factory_id
            )
        ) == audit_count_before
        assert db.get(
            models.InjectionScheduleVersion,
            version_id,
        ).revision == version_revision_before
