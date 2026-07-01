import importlib
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'molding_sample_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def sample_order_payload(order_id="BP-API-001", external=False):
    return {
        "order": {
            "id": order_id,
            "factory_id": "huakang-a",
            "order_number": "62437",
            "doc_number": "W-G026-00",
            "product_name": "链条枪",
            "client_name": "BuzzBee",
            "date": "2026-07-01",
            "stage": "T0",
            "order_type": "啤办",
            "workshop": "模厂" if external else "A车间",
            "send_to": "发至模厂" if external else "",
            "supervisor": "李主管",
            "eng_name": "肖科",
            "reason": "对办颜色和试啤。",
        },
        "items": [
            {
                "id": f"{order_id}-001",
                "sort_order": 1,
                "mold_id": "M-001",
                "mold_name": "左右枪身",
                "machine_type": "160T",
                "material": "HIPS 425",
                "color": "深绿色",
                "pigment_no": "71139",
                "quantity": "1/1",
                "shoot_qty": 30,
                "gross_weight_g": 82,
                "required_material_kg": 2.46,
                "mold_return_time": "2026-07-01",
                "completion_time": "2026-07-03",
                "notes": "",
            }
        ],
    }


@pytest.fixture()
def client(monkeypatch):
    with make_client(monkeypatch) as test_client:
        yield test_client


def test_create_injection_order_defaults_to_pending_review(client):
    response = client.post("/api/injection", json=sample_order_payload())

    assert response.status_code == 201
    payload = response.json()
    assert payload["order"]["status"] == "待审核"
    assert payload["order"]["order_type"] == "啤办"
    assert payload["items"][0]["order_id"] == "BP-API-001"

    list_response = client.get("/api/injection")
    assert list_response.status_code == 200
    assert list_response.json()[0]["order"]["id"] == "BP-API-001"


def test_internal_order_workflow_blocks_completion_until_actual_weight_is_filled(client):
    client.post("/api/injection", json=sample_order_payload("BP-API-002"))

    supervisor_response = client.patch(
        "/api/injection/BP-API-002/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
            "pin": "1234",
        },
    )
    assert supervisor_response.status_code == 200
    assert supervisor_response.json()["order"]["status"] == "待经理审核"

    manager_response = client.patch(
        "/api/injection/BP-API-002/status",
        json={
            "action": "经理通过",
            "reviewer_name": "王经理",
            "reviewer_role": "经理",
            "pin": "1234",
        },
    )
    assert manager_response.status_code == 200
    assert manager_response.json()["order"]["status"] == "待生产"

    start_response = client.patch(
        "/api/injection/BP-API-002/status",
        json={
            "action": "开始处理",
            "reviewer_name": "啤机部",
            "reviewer_role": "啤机部",
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["order"]["status"] == "生产中"

    blocked_response = client.patch(
        "/api/injection/BP-API-002/status",
        json={
            "action": "标记完成",
            "reviewer_name": "啤机部",
            "reviewer_role": "啤机部",
        },
    )
    assert blocked_response.status_code == 400
    assert "actual_weight_kg" in blocked_response.json()["detail"]

    item_response = client.patch(
        "/api/injection/BP-API-002/items",
        json={
            "items": [
                {
                    "id": "BP-API-002-001",
                    "receipt_no": "LL-20260701-001",
                    "collected_weight_kg": 2.5,
                    "actual_weight_kg": 2,
                    "injection_cost": 100,
                }
            ]
        },
    )
    assert item_response.status_code == 200
    item = item_response.json()["items"][0]
    assert item["actual_amount_hkd"] == 24.25
    assert item["injection_cost_hkd"] == 108
    assert item["exchange_rate_at_save"] == 1.08

    completed_response = client.patch(
        "/api/injection/BP-API-002/status",
        json={
            "action": "标记完成",
            "reviewer_name": "啤机部",
            "reviewer_role": "啤机部",
            "today": "2026-07-01",
        },
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["order"]["status"] == "已完成"
    assert completed_response.json()["order"]["completed_date"] == "2026-07-01"

    summary_response = client.get("/api/injection-total-costs")
    assert summary_response.status_code == 200
    summary = summary_response.json()[0]
    assert summary["order_id"] == "BP-API-002"
    assert summary["total_material_cost"] == 24.25
    assert summary["total_injection_cost"] == 108
    assert summary["has_missing_injection_cost"] is False


def test_external_order_auto_completes_after_manager_approval(client):
    client.post("/api/injection", json=sample_order_payload("BP-API-003", external=True))
    client.patch(
        "/api/injection/BP-API-003/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
            "pin": "1234",
        },
    )

    response = client.patch(
        "/api/injection/BP-API-003/status",
        json={
            "action": "经理通过",
            "reviewer_name": "王经理",
            "reviewer_role": "经理",
            "pin": "1234",
            "today": "2026-07-01",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "已完成"
    assert payload["order"]["completed_date"] == "2026-07-01"
    assert payload["items"][0]["actual_weight_kg"] == 2.46
    assert payload["items"][0]["actual_amount_hkd"] == 29.83
    assert payload["items"][0]["injection_cost_hkd"] is None


def test_manager_can_update_material_prices_and_exchange_rate(client):
    prices_response = client.get("/api/material-prices")
    assert prices_response.status_code == 200
    assert any(row["material"] == "HIPS 425" for row in prices_response.json()["prices"])

    update_response = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [
                {"material": "HIPS 425", "unit_price": 6.0, "notes": "新经理价"},
                {"material": "ABS 740", "unit_price": 8.0, "notes": "经理价"},
            ],
            "rmb_to_hkd_rate": 1.1,
            "manager_name": "王经理",
            "manager_pin": "1234",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["rmb_to_hkd_rate"] == 1.1
    assert update_response.json()["prices"][0]["unit_price"] == 6.0


def test_supervisor_and_manager_review_actions_require_valid_pin(client):
    client.post("/api/injection", json=sample_order_payload("BP-PIN-001"))

    missing_pin_response = client.patch(
        "/api/injection/BP-PIN-001/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
        },
    )
    assert missing_pin_response.status_code == 401

    wrong_pin_response = client.patch(
        "/api/injection/BP-PIN-001/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
            "pin": "0000",
        },
    )
    assert wrong_pin_response.status_code == 401

    supervisor_response = client.patch(
        "/api/injection/BP-PIN-001/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
            "pin": "1234",
        },
    )
    assert supervisor_response.status_code == 200
    assert supervisor_response.json()["order"]["status"] == "待经理审核"

    manager_missing_pin_response = client.patch(
        "/api/injection/BP-PIN-001/status",
        json={
            "action": "经理通过",
            "reviewer_name": "王经理",
            "reviewer_role": "经理",
        },
    )
    assert manager_missing_pin_response.status_code == 401

    manager_response = client.patch(
        "/api/injection/BP-PIN-001/status",
        json={
            "action": "经理通过",
            "reviewer_name": "王经理",
            "reviewer_role": "经理",
            "pin": "1234",
        },
    )
    assert manager_response.status_code == 200
    assert manager_response.json()["order"]["status"] == "待生产"


def test_roles_pin_verification_change_pin_and_manager_price_gate(client):
    roles_response = client.get("/api/roles")
    assert roles_response.status_code == 200
    roles = roles_response.json()
    assert {"name": "李主管", "role": "主管", "must_change": True} in roles["supervisors"]
    assert {"name": "王经理", "role": "经理", "must_change": True} in roles["managers"]

    verify_response = client.post(
        "/api/verify-pin",
        json={"name": "王经理", "role": "经理", "pin": "1234"},
    )
    assert verify_response.status_code == 200
    assert verify_response.json() == {
        "valid": True,
        "name": "王经理",
        "role": "经理",
        "must_change": True,
    }

    update_without_pin_response = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [{"material": "HIPS 425", "unit_price": 6.0, "notes": "新经理价"}],
            "rmb_to_hkd_rate": 1.1,
            "manager_name": "王经理",
        },
    )
    assert update_without_pin_response.status_code == 401

    change_wrong_pin_response = client.post(
        "/api/change-pin",
        json={
            "name": "王经理",
            "role": "经理",
            "old_pin": "0000",
            "new_pin": "6789",
        },
    )
    assert change_wrong_pin_response.status_code == 401

    change_response = client.post(
        "/api/change-pin",
        json={
            "name": "王经理",
            "role": "经理",
            "old_pin": "1234",
            "new_pin": "6789",
        },
    )
    assert change_response.status_code == 200
    assert change_response.json()["must_change"] is False

    old_pin_response = client.post(
        "/api/verify-pin",
        json={"name": "王经理", "role": "经理", "pin": "1234"},
    )
    assert old_pin_response.status_code == 401

    update_with_new_pin_response = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [{"material": "HIPS 425", "unit_price": 6.0, "notes": "新经理价"}],
            "rmb_to_hkd_rate": 1.1,
            "manager_name": "王经理",
            "manager_pin": "6789",
        },
    )
    assert update_with_new_pin_response.status_code == 200
    assert update_with_new_pin_response.json()["rmb_to_hkd_rate"] == 1.1


def test_engineering_can_edit_and_delete_unlocked_orders(client):
    client.post("/api/injection", json=sample_order_payload("BP-EDIT-001"))

    edited_payload = sample_order_payload("BP-EDIT-001")
    edited_payload["actor_name"] = "肖科"
    edited_payload["actor_role"] = "工程部"
    edited_payload["order"]["product_name"] = "链条枪改版"
    edited_payload["order"]["reason"] = "补充试色说明。"
    edited_payload["items"][0]["mold_name"] = "左右枪身改"
    edited_payload["items"].append(
        {
            "id": "BP-EDIT-001-002",
            "sort_order": 2,
            "mold_id": "M-002",
            "mold_name": "弹匣",
            "machine_type": "120T",
            "material": "ABS 740",
            "color": "黑色",
            "pigment_no": "",
            "quantity": "1/1",
            "shoot_qty": 20,
            "gross_weight_g": 40,
            "required_material_kg": 0.8,
            "mold_return_time": "2026-07-01",
            "completion_time": "2026-07-03",
            "notes": "",
        }
    )

    edit_response = client.put("/api/injection/BP-EDIT-001", json=edited_payload)
    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["order"]["product_name"] == "链条枪改版"
    assert len(edited["items"]) == 2
    assert edited["items"][0]["mold_name"] == "左右枪身改"

    delete_response = client.delete(
        "/api/injection/BP-EDIT-001",
        params={"actor_name": "肖科", "actor_role": "工程部"},
    )
    assert delete_response.status_code == 204

    missing_response = client.get("/api/injection/BP-EDIT-001")
    assert missing_response.status_code == 404


def test_locked_orders_reject_engineering_edit_and_delete_but_allow_manager_with_pin(client):
    client.post("/api/injection", json=sample_order_payload("BP-LOCK-001"))
    client.patch(
        "/api/injection/BP-LOCK-001/status",
        json={
            "action": "主管通过",
            "reviewer_name": "李主管",
            "reviewer_role": "主管",
            "pin": "1234",
        },
    )

    locked_edit_payload = sample_order_payload("BP-LOCK-001")
    locked_edit_payload["actor_name"] = "肖科"
    locked_edit_payload["actor_role"] = "工程部"
    locked_edit_payload["order"]["product_name"] = "普通工程误改"

    blocked_edit_response = client.put("/api/injection/BP-LOCK-001", json=locked_edit_payload)
    assert blocked_edit_response.status_code == 403

    blocked_delete_response = client.delete(
        "/api/injection/BP-LOCK-001",
        params={"actor_name": "肖科", "actor_role": "工程部"},
    )
    assert blocked_delete_response.status_code == 403

    manager_edit_payload = sample_order_payload("BP-LOCK-001")
    manager_edit_payload["actor_name"] = "王经理"
    manager_edit_payload["actor_role"] = "经理"
    manager_edit_payload["pin"] = "1234"
    manager_edit_payload["order"]["product_name"] = "经理修正名称"

    manager_edit_response = client.put("/api/injection/BP-LOCK-001", json=manager_edit_payload)
    assert manager_edit_response.status_code == 200
    assert manager_edit_response.json()["order"]["product_name"] == "经理修正名称"


def test_warehouse_requisitions_create_filter_issue_and_delete(client):
    client.post("/api/injection", json=sample_order_payload("BP-REQ-001"))
    client.post("/api/injection", json=sample_order_payload("BP-REQ-002"))

    first_response = client.post(
        "/api/requisitions",
        json={
            "date": "2026-07-01",
            "order_id": "BP-REQ-001",
            "material": "HIPS 425",
            "requested_weight_kg": 2.46,
            "applicant": "肖科",
            "notes": "左右枪身试啤领料",
        },
    )
    assert first_response.status_code == 201
    first = first_response.json()
    assert first["req_number"] == "LL-20260701-001"
    assert first["order_id"] == "BP-REQ-001"
    assert first["order_number"] == "62437"
    assert first["status"] == "待出库"
    assert first["issued_at"] == ""

    second_response = client.post(
        "/api/requisitions",
        json={
            "date": "2026-07-01",
            "order_id": "BP-REQ-002",
            "material": "ABS 740",
            "requested_weight_kg": 1.2,
            "applicant": "肖科",
        },
    )
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["req_number"] == "LL-20260701-002"

    filtered_response = client.get("/api/requisitions", params={"order_id": "BP-REQ-001"})
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert [row["id"] for row in filtered] == [first["id"]]

    issue_response = client.patch(
        f"/api/requisitions/{first['id']}/status",
        json={
            "status": "已出库",
            "issued_at": "2026-07-01 15:30",
        },
    )
    assert issue_response.status_code == 200
    assert issue_response.json()["status"] == "已出库"
    assert issue_response.json()["issued_at"] == "2026-07-01 15:30"

    delete_response = client.delete(f"/api/requisitions/{first['id']}")
    assert delete_response.status_code == 204

    after_delete_response = client.get("/api/requisitions", params={"order_id": "BP-REQ-001"})
    assert after_delete_response.status_code == 200
    assert after_delete_response.json() == []


def test_warehouse_requisition_rejects_duplicate_line(client):
    client.post("/api/injection", json=sample_order_payload("BP-REQ-DUP"))
    payload = {
        "date": "2026-07-01",
        "order_id": "BP-REQ-DUP",
        "material": "HIPS 425",
        "requested_weight_kg": 2.46,
        "applicant": "肖科",
        "notes": "M-001 · 左右枪身",
    }

    first_response = client.post("/api/requisitions", json=payload)
    assert first_response.status_code == 201

    duplicate_response = client.post("/api/requisitions", json=payload)
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "该明细已生成领料单"
