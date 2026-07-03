import importlib
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


def login_as(client, username: str):
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200
    return response.json()


def sample_order_payload(order_id="BP-API-001", external=False):
    return {
        "order": {
            "id": order_id,
            "factory_id": "huaxing",
            "order_number": "62437",
            "doc_number": "W-G026-00",
            "product_name": "链条枪",
            "client_name": "BuzzBee",
            "date": "2026-07-01",
            "stage": "T0",
            "order_type": "啤办",
            "workshop": "模厂" if external else "A车间",
            "send_to": "发至模厂" if external else "",
            "supervisor": "华兴工程主管",
            "eng_name": "华兴工程师",
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


def test_unauthenticated_access_to_molding_sample_api_is_rejected(client):
    response = client.get("/api/injection")

    assert response.status_code == 401


def test_engineer_can_create_order_and_production_user_reads_notification_after_manager_approval(client):
    login_as(client, "engineer")
    response = client.post("/api/injection", json=sample_order_payload())

    assert response.status_code == 201
    payload = response.json()
    assert payload["order"]["status"] == "待审核"
    assert payload["audit_logs"][0]["actor_name"] == "华兴工程师"
    assert payload["audit_logs"][0]["actor_role"] == "工程师"
    assert payload["audit_logs"][0]["actor_user_id"] == "user-engineer"
    assert payload["items"][0]["order_id"] == "BP-API-001"

    login_as(client, "molding_clerk")
    early_notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={"target_module": "production_molding_sample_task", "factory_id": "huaxing"},
    )
    assert early_notifications_response.status_code == 200
    assert early_notifications_response.json() == []

    login_as(client, "supervisor")
    client.patch("/api/injection/BP-API-001/status", json={"action": "主管通过"})

    login_as(client, "manager")
    client.patch("/api/injection/BP-API-001/status", json={"action": "经理通过"})

    login_as(client, "molding_clerk")
    notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={"target_module": "production_molding_sample_task", "factory_id": "huaxing"},
    )
    assert notifications_response.status_code == 200
    notifications = notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["order_id"] == "BP-API-001"
    assert notifications[0]["target_role"] == "啤机部"


def test_workflow_uses_logged_in_roles_without_pin(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-WORKFLOW-001"))

    engineer_review_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "主管通过"},
    )
    assert engineer_review_response.status_code == 403

    login_as(client, "supervisor")
    supervisor_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "主管通过"},
    )
    assert supervisor_response.status_code == 200
    assert supervisor_response.json()["order"]["status"] == "待经理审核"
    assert supervisor_response.json()["audit_logs"][0]["actor_name"] == "华兴工程主管"

    supervisor_manager_step_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "经理通过"},
    )
    assert supervisor_manager_step_response.status_code == 403

    login_as(client, "manager")
    manager_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "经理通过"},
    )
    assert manager_response.status_code == 200
    assert manager_response.json()["order"]["status"] == "待生产"

    login_as(client, "molding_clerk")
    start_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "开始处理"},
    )
    assert start_response.status_code == 200
    assert start_response.json()["order"]["status"] == "生产中"

    blocked_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "标记完成"},
    )
    assert blocked_response.status_code == 400
    assert "actual_weight_kg" in blocked_response.json()["detail"]

    item_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/items",
        json={"items": [{"id": "BP-WORKFLOW-001-001", "actual_weight_kg": 2, "injection_cost": 100}]},
    )
    assert item_response.status_code == 200

    completed_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "标记完成", "today": "2026-07-01"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["order"]["status"] == "已完成"
    assert completed_response.json()["order"]["completed_date"] == "2026-07-01"


def test_external_order_auto_completes_after_manager_approval(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-EXT-001", external=True))

    login_as(client, "supervisor")
    client.patch("/api/injection/BP-EXT-001/status", json={"action": "主管通过"})

    login_as(client, "manager")
    response = client.patch(
        "/api/injection/BP-EXT-001/status",
        json={"action": "经理通过", "today": "2026-07-01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "已完成"
    assert payload["order"]["completed_date"] == "2026-07-01"
    assert payload["items"][0]["actual_weight_kg"] == 2.46
    assert payload["items"][0]["actual_amount_hkd"] == 29.83


def test_manager_price_update_uses_logged_in_user_and_sensitive_audit(client):
    login_as(client, "engineer")
    blocked_response = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [{"material": "HIPS 425", "unit_price": 6.0, "notes": "新经理价"}],
            "rmb_to_hkd_rate": 1.1,
        },
    )
    assert blocked_response.status_code == 403

    login_as(client, "manager")
    update_response = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [{"material": "HIPS 425", "unit_price": 6.0, "notes": "新经理价"}],
            "rmb_to_hkd_rate": 1.1,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["rmb_to_hkd_rate"] == 1.1

    logs_response = client.get("/api/sensitive-audit-logs")
    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert logs[0]["action"] == "经理更新价格口径"
    assert logs[0]["actor_user_id"] == "user-manager"
    assert logs[0]["actor_name"] == "华兴经理"
    assert logs[0]["actor_role"] == "经理"


def test_old_pin_routes_are_removed(client):
    assert client.get("/api/roles").status_code == 404
    assert client.post("/api/verify-pin", json={"name": "王经理", "role": "经理", "pin": "1234"}).status_code == 404
    assert client.post("/api/change-pin", json={"name": "王经理", "role": "经理", "old_pin": "1234", "new_pin": "6789"}).status_code == 404
    assert client.post(
        "/api/reset-supervisor-pin",
        json={"manager_name": "王经理", "manager_pin": "6789", "supervisor_name": "李主管"},
    ).status_code == 404


def test_engineering_edit_delete_permissions_use_login_role(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-EDIT-001"))

    edited_payload = sample_order_payload("BP-EDIT-001")
    edited_payload["order"]["product_name"] = "链条枪改版"
    edited_payload["items"][0]["mold_name"] = "左右枪身改"

    edit_response = client.put("/api/injection/BP-EDIT-001", json=edited_payload)
    assert edit_response.status_code == 200
    assert edit_response.json()["order"]["product_name"] == "链条枪改版"

    delete_response = client.delete("/api/injection/BP-EDIT-001")
    assert delete_response.status_code == 204

    client.post("/api/injection", json=sample_order_payload("BP-LOCK-001"))
    login_as(client, "supervisor")
    client.patch("/api/injection/BP-LOCK-001/status", json={"action": "主管通过"})

    login_as(client, "engineer")
    locked_payload = sample_order_payload("BP-LOCK-001")
    locked_payload["order"]["product_name"] = "普通工程误改"
    assert client.put("/api/injection/BP-LOCK-001", json=locked_payload).status_code == 403
    assert client.delete("/api/injection/BP-LOCK-001").status_code == 403

    login_as(client, "manager")
    manager_payload = sample_order_payload("BP-LOCK-001")
    manager_payload["order"]["product_name"] = "经理修正名称"
    manager_edit_response = client.put("/api/injection/BP-LOCK-001", json=manager_payload)
    assert manager_edit_response.status_code == 200
    assert manager_edit_response.json()["order"]["product_name"] == "经理修正名称"


def test_trial_accounts_do_not_expose_unused_warehouse_permissions(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-REQ-001"))

    blocked_batch_response = client.post(
        "/api/inventory-batches",
        json={"material": "HIPS 425", "batch_no": "HIPS-20260701-A", "location": "A-01", "initial_weight_kg": 3},
    )
    assert blocked_batch_response.status_code == 403

    retired_login_response = client.post("/api/auth/login", json={"username": "warehouse", "password": "123456"})
    assert retired_login_response.status_code == 401

    login_as(client, "molding_clerk")
    clerk_batch_response = client.post(
        "/api/inventory-batches",
        json={"material": "HIPS 425", "batch_no": "HIPS-20260701-A", "location": "A-01", "initial_weight_kg": 3},
    )
    assert clerk_batch_response.status_code == 403


def test_export_and_import_molding_sample_excel_template(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-XLSX-001"))

    export_response = client.get("/api/injection/BP-XLSX-001/export-excel")
    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"

    import_response = client.post(
        "/api/injection/import-excel",
        params={"order_id": "BP-XLSX-002"},
        content=export_response.content,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert import_response.status_code == 201
    imported = import_response.json()
    assert imported["order"]["id"] == "BP-XLSX-002"
    assert imported["items"][0]["id"] == "BP-XLSX-002-001"


def test_sensitive_audit_logs_return_latest_200_rows(client):
    db_module = importlib.import_module("app.db")
    model_module = importlib.import_module("app.models.molding_sample")

    with db_module.SessionLocal() as db:
        for index in range(205):
            db.add(
                model_module.MoldingSampleSensitiveAuditLog(
                    action=f"审计{index}",
                    actor_user_id="user-admin",
                    actor_name="系统",
                    actor_role="审计",
                    actor_roles="系统管理员",
                    factory_scope="*",
                    target_type="test",
                    target_name=f"target-{index}",
                    detail=f"敏感操作审计 {index}",
                    created_at=f"2026-07-01 12:{index % 60:02d}",
                )
            )
        db.commit()

    login_as(client, "manager")
    logs_response = client.get("/api/sensitive-audit-logs")
    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert len(logs) == 200
    assert logs[0]["action"] == "审计204"
    assert logs[-1]["action"] == "审计5"
