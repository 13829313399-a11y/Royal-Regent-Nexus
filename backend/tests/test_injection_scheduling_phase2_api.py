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


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{TEST_TMP_DIR / f'injection_phase2_{uuid4().hex}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(
    client: TestClient,
    username: str,
    password: str = "123456",
) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def ensure_user(
    username: str,
    role_id: str,
    *,
    factory_id: str,
    department: str,
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
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
        db.commit()


def machine_payload(factory_id: str, machine_code: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "machine_code": machine_code,
        "area": "A区",
        "position": "A-02",
        "machine_class": "32A",
        "clamping_force_tons": 320,
        "injection_capacity_g": 617,
        "tie_bar_x_mm": 680,
        "tie_bar_y_mm": 680,
        "platen_x_mm": 820,
        "platen_y_mm": 820,
        "min_mold_thickness_mm": 250,
        "max_mold_thickness_mm": 850,
        "opening_stroke_mm": 700,
        "machine_type": "standard",
        "robot_capabilities": ["single", "dual"],
        "fixture_capabilities": ["suction_cup"],
        "process_restrictions": [],
        "equipment_details": {
            "manufacturer": "博创",
            "model": "BH320",
            "manufacture_year": "2017.3",
        },
        "remarks": "PC 螺杆",
        "status": "available",
    }


def mold_payload(factory_id: str, mold_no: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "mold_no": mold_no,
        "name": "GT1214",
        "length_mm": 550,
        "width_mm": 450,
        "height_mm": 850,
        "weight_kg": None,
        "recommended_machine_class": "32A",
        "whole_shot_net_weight_g": 379,
        "whole_shot_gross_weight_g": None,
        "required_arm_type": "dual",
        "required_fixture_type": "suction_cup",
        "material_code": "ABS",
        "material_name": "ABS",
        "color_profile": "",
        "process_requirements": [],
        "copy_count": 1,
        "data_quality_status": "complete",
        "status": "available",
    }


def test_phase2_master_data_revision_rules_and_factory_isolation(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huaxing"},
        )
        assert anonymous.status_code == 401

        admin = login(client, "admin", ADMIN_TEST_PASSWORD)
        assert "injection_scheduling:manage_master" in admin["permissions"]
        assert "injection_scheduling:manage_rules" in admin["permissions"]

        initial_rules = client.get(
            "/api/injection-scheduling/rules/current",
            params={"factory_id": "huaxing"},
        )
        assert initial_rules.status_code == 200, initial_rules.text
        assert initial_rules.json()["revision"] == 1
        assert initial_rules.json()["configured_max_utilization"] == 1.0

        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huaxing", "旧2"),
        )
        assert machine.status_code == 201, machine.text
        machine_body = machine.json()
        assert machine_body["factory_id"] == "huaxing"
        assert machine_body["injection_capacity_g"] == 617
        assert machine_body["machine_class_raw"] == "32A"
        assert machine_body["machine_a_class"] == 32
        assert machine_body["normalization_status"] == "COMPLETE"
        assert machine_body["equipment_details"]["model"] == "BH320"
        assert machine_body["remarks"] == "PC 螺杆"
        assert machine_body["revision"] == 1

        duplicate = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huaxing", "旧2"),
        )
        assert duplicate.status_code == 409

        other_factory_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huakang-b", "旧2"),
        )
        assert other_factory_machine.status_code == 201, other_factory_machine.text

        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload("huaxing", "GT1214"),
        )
        assert mold.status_code == 201, mold.text
        assert mold.json()["whole_shot_net_weight_g"] == 379
        assert mold.json()["mold_class_raw"] == "32A"
        assert mold.json()["mold_a_class"] == 32
        assert mold.json()["normalization_status"] == "COMPLETE"

        incomplete = mold_payload("huaxing", "MISSING-SIZE")
        incomplete["length_mm"] = None
        engineering_data_only = client.post(
            "/api/injection-scheduling/molds",
            json=incomplete,
        )
        assert engineering_data_only.status_code == 201
        assert engineering_data_only.json()["length_mm"] is None

        huaxing_machines = client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huaxing", "search": "旧2"},
        )
        huakang_machines = client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huakang-b"},
        )
        assert [item["factory_id"] for item in huaxing_machines.json()["items"]] == [
            "huaxing"
        ]
        assert [item["factory_id"] for item in huakang_machines.json()["items"]] == [
            "huakang-b"
        ]

        stale_update = machine_payload("huaxing", "旧2")
        stale_update["expected_revision"] = 99
        conflict = client.put(
            f"/api/injection-scheduling/machines/{machine_body['id']}",
            json=stale_update,
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["current_revision"] == 1

        correct_update = machine_payload("huaxing", "旧2")
        correct_update["expected_revision"] = 1
        correct_update["status"] = "maintenance"
        correct_update["remarks"] = "待更换油封"
        updated = client.put(
            f"/api/injection-scheduling/machines/{machine_body['id']}",
            json=correct_update,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert updated.json()["status"] == "maintenance"
        assert updated.json()["remarks"] == "待更换油封"

        cross_factory_object = machine_payload("huakang-b", "旧2")
        cross_factory_object["expected_revision"] = 2
        hidden = client.put(
            f"/api/injection-scheduling/machines/{machine_body['id']}",
            json=cross_factory_object,
        )
        assert hidden.status_code == 404

        rule_update = {
            "factory_id": "huaxing",
            "expected_revision": 1,
            "configured_max_utilization": 0.9,
            "allow_mold_rotation_90": True,
            "config": {
                **initial_rules.json()["config"],
                "notes": "阶段2规则版本测试",
            },
        }
        rules_v2 = client.put(
            "/api/injection-scheduling/rules/current",
            json=rule_update,
        )
        assert rules_v2.status_code == 200, rules_v2.text
        assert rules_v2.json()["revision"] == 2
        assert rules_v2.json()["configured_max_utilization"] == 0.9
        stale_rules = client.put(
            "/api/injection-scheduling/rules/current",
            json=rule_update,
        )
        assert stale_rules.status_code == 409
        assert stale_rules.json()["detail"]["current_revision"] == 2


def test_phase2_permissions_keep_local_writes_and_explicit_cross_factory_reads(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        created = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huakang-b", "B-01"),
        )
        assert created.status_code == 201, created.text
        client.post("/api/auth/logout")

        ensure_user(
            "local-schedule-clerk",
            "molding_clerk",
            factory_id="huaxing",
            department="molding",
        )
        local_user = login(client, "local-schedule-clerk")
        assert "injection_scheduling:read" in local_user["permissions"]
        assert "injection_scheduling:manage_master" not in local_user["permissions"]
        assert client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huaxing"},
        ).status_code == 200
        assert client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huakang-b"},
        ).status_code == 403
        assert client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huaxing", "HX-DENIED"),
        ).status_code == 403
        client.post("/api/auth/logout")

        ensure_user(
            "cross-read-molding-clerk",
            "position_molding_clerk",
            factory_id="huaxing",
            department="production",
        )
        cross_user = login(client, "cross-read-molding-clerk")
        assert "injection_scheduling:read" in cross_user["permissions"]
        cross_read = client.get(
            "/api/injection-scheduling/machines",
            params={"factory_id": "huakang-b"},
        )
        assert cross_read.status_code == 200, cross_read.text
        assert [item["machine_code"] for item in cross_read.json()["items"]] == [
            "B-01"
        ]
        assert client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huakang-b", "B-DENIED"),
        ).status_code == 403
