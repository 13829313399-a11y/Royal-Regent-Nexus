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
        f"sqlite:///{TEST_TMP_DIR / f'injection_phase5_{uuid4().hex}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text


def machine_payload(code: str, *, capacity: float = 617, arms=None) -> dict:
    return {
        "factory_id": "huaxing",
        "expected_revision": 0,
        "machine_code": code,
        "area": "老车间",
        "position": code,
        "machine_class": "32A",
        "clamping_force_tons": 320,
        "injection_capacity_g": capacity,
        "tie_bar_x_mm": 680,
        "tie_bar_y_mm": 680,
        "platen_x_mm": 820,
        "platen_y_mm": 820,
        "min_mold_thickness_mm": None,
        "max_mold_thickness_mm": None,
        "opening_stroke_mm": None,
        "machine_type": "standard",
        "robot_capabilities": ["single", "dual"] if arms is None else arms,
        "fixture_capabilities": ["suction_cup"],
        "process_restrictions": [],
        "status": "available",
    }


def mold_payload() -> dict:
    return {
        "factory_id": "huaxing",
        "expected_revision": 0,
        "mold_no": "GT1214",
        "name": "自卸车轮",
        "length_mm": 550,
        "width_mm": 450,
        "height_mm": 850,
        "weight_kg": None,
        "recommended_machine_class": "32A",
        "whole_shot_net_weight_g": 379,
        "whole_shot_gross_weight_g": None,
        "required_arm_type": "dual",
        "required_fixture_type": "suction_cup",
        "material_code": "PP",
        "material_name": "PP 5100NA",
        "color_profile": "",
        "process_requirements": [],
        "copy_count": 1,
        "data_quality_status": "complete",
        "status": "available",
    }


def order_payload(mold_id: str) -> dict:
    return {
        "factory_id": "huaxing",
        "expected_revision": 0,
        "order_no": "BJB260001",
        "item_no": "GT1214-A",
        "product_name": "自卸车轮",
        "mold_id": mold_id,
        "order_quantity": 3528,
        "source_completed_quantity": 10,
        "delivery_start_date": "2026-08-01",
        "delivery_due_date": "2026-08-03",
        "priority_code": "CRITICAL",
        "material_readiness_status": "ready",
        "warehouse_text": "007",
        "remark": "阶段5候选测试",
        "source_ref": "phase5-test",
        "source_version": "1",
        "lineage": {},
    }


def test_phase5_hard_constraints_explanations_and_human_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client)
        old2 = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("旧2"),
        ).json()
        single = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("单臂机", arms=["single"]),
        ).json()
        review = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("机械手待复核", arms=[]),
        ).json()
        small = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("射胶357", capacity=357),
        ).json()
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(),
        ).json()
        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(mold["id"]),
        ).json()

        evaluation = client.post(
            "/api/injection-scheduling/matches/evaluate",
            json={"factory_id": "huaxing", "order_id": order["id"], "machine_ids": []},
        )
        assert evaluation.status_code == 200, evaluation.text
        body = evaluation.json()
        assert body["rule_set_revision"] == 1
        results = {item["machine_id"]: item for item in body["results"]}
        assert results[old2["id"]]["decision"] == "PASS"
        assert results[old2["id"]]["score"] is not None
        assert results[old2["id"]]["warnings"] == []
        assert not {
            "INSTALLATION_DIMENSIONS_MISSING",
            "INSTALLATION_DIMENSIONS_EXCEEDED",
            "MOLD_THICKNESS_UNCONFIRMED",
            "MOLD_THICKNESS_OUT_OF_RANGE",
        }.intersection(
            reason["rule_code"]
            for result in results.values()
            for reason in (*result["hard_failures"], *result["warnings"])
        )
        assert results[review["id"]]["decision"] == "REVIEW_REQUIRED"
        assert any(
            warning["rule_code"] == "ARM_CAPABILITY_MISSING"
            for warning in results[review["id"]]["warnings"]
        )
        assert results[single["id"]]["decision"] == "FAIL"
        assert any(
            failure["rule_code"] == "ROBOT_ARM_UNSUPPORTED"
            for failure in results[single["id"]]["hard_failures"]
        )
        assert results[small["id"]]["decision"] == "FAIL"
        assert any(
            failure["rule_code"] == "SHOT_CAPACITY_EXCEEDED"
            for failure in results[small["id"]]["hard_failures"]
        )

        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": "huaxing",
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        ).json()
        base_confirm = {
            "factory_id": "huaxing",
            "order_id": order["id"],
            "expected_plan_revision": draft["revision"],
            "expected_rule_revision": body["rule_set_revision"],
            "request_id": "phase5-confirm-0001",
            "override_reason": "",
        }
        hard_failure = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/suggest",
            json={**base_confirm, "machine_id": small["id"]},
        )
        assert hard_failure.status_code == 409
        assert "硬约束失败" in str(hard_failure.json()["detail"])

        missing_reason = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/suggest",
            json={**base_confirm, "machine_id": review["id"]},
        )
        assert missing_reason.status_code == 409
        assert missing_reason.json()["detail"]["override_reason_required"] is True

        stale_rule = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/suggest",
            json={
                **base_confirm,
                "machine_id": review["id"],
                "expected_rule_revision": 99,
                "request_id": "phase5-confirm-stale",
                "override_reason": "机械手能力待现场复核",
            },
        )
        assert stale_rule.status_code == 409
        assert "规则版本" in stale_rule.json()["detail"]["message"]

        confirmed = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/suggest",
            json={
                **base_confirm,
                "machine_id": review["id"],
                "request_id": "phase5-confirm-0002",
                "override_reason": "主管确认机械手能力待上机前现场复核",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_body = confirmed.json()
        assert confirmed_body["match"]["decision"] == "REVIEW_REQUIRED"
        assert confirmed_body["plan"]["revision"] == 2
        assert confirmed_body["plan"]["tasks"][0]["machine_id"] == review["id"]
        assert (
            confirmed_body["plan"]["tasks"][0]["manual_override_reason"]
            == "主管确认机械手能力待上机前现场复核"
        )

        events = client.get(
            "/api/injection-scheduling/events",
            params={"factory_id": "huaxing", "after_sequence": 0},
        ).json()["events"]
        confirmation_event = next(
            event for event in events if event["request_id"] == "phase5-confirm-0002"
        )
        saved_match = confirmation_event["detail"]["match_result"]
        assert saved_match["rule_set_id"] == body["rule_set_id"]
        assert saved_match["rule_set_revision"] == body["rule_set_revision"]
        assert saved_match["decision"] == "REVIEW_REQUIRED"
        assert saved_match["score"] == results[review["id"]]["score"]
        assert saved_match["warnings"]

        current = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": "huaxing"},
        ).json()
        assert current["plan"]["orders"][0]["order_no"] == "BJB260001"
