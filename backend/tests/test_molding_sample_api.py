import importlib
import sqlite3
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

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


def make_client_with_database(monkeypatch, database_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app, raise_server_exceptions=False)


def create_legacy_molding_sample_sqlite_database(database_path: Path):
    database_path.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE molding_sample_orders (
              id VARCHAR(64) PRIMARY KEY,
              factory_id VARCHAR(64),
              order_number VARCHAR(128),
              doc_number VARCHAR(128),
              product_name VARCHAR(255),
              client_name VARCHAR(255),
              date VARCHAR(20),
              stage VARCHAR(20),
              order_type VARCHAR(20),
              workshop VARCHAR(64),
              send_to VARCHAR(64),
              supervisor VARCHAR(128),
              eng_name VARCHAR(128),
              reason TEXT,
              status VARCHAR(32),
              reject_reason TEXT,
              completed_date VARCHAR(20),
              created_at VARCHAR(32),
              updated_at VARCHAR(32)
            );
            CREATE TABLE molding_sample_items (
              id VARCHAR(64) PRIMARY KEY,
              order_id VARCHAR(64),
              sort_order INTEGER,
              mold_id VARCHAR(128),
              mold_name VARCHAR(255),
              machine_type VARCHAR(64),
              material VARCHAR(255),
              color VARCHAR(255),
              pigment_no VARCHAR(128),
              quantity VARCHAR(64),
              shoot_qty INTEGER,
              gross_weight_g FLOAT,
              required_material_kg FLOAT,
              mold_return_time VARCHAR(32),
              completion_time VARCHAR(32),
              notes TEXT,
              receipt_no VARCHAR(128),
              collected_weight_kg FLOAT,
              actual_weight_kg FLOAT,
              actual_amount_hkd FLOAT,
              injection_cost FLOAT,
              injection_cost_hkd FLOAT,
              exchange_rate_at_save FLOAT
            );
            CREATE TABLE molding_sample_audit_logs (
              id VARCHAR(96) PRIMARY KEY,
              order_id VARCHAR(64),
              action VARCHAR(128),
              actor_name VARCHAR(128),
              actor_role VARCHAR(64),
              from_status VARCHAR(32),
              to_status VARCHAR(32),
              reason TEXT,
              created_at VARCHAR(32)
            );
            CREATE TABLE molding_sample_sensitive_audit_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              action VARCHAR(128),
              actor_name VARCHAR(128),
              actor_role VARCHAR(64),
              target_type VARCHAR(64),
              target_name VARCHAR(128),
              detail TEXT,
              created_at VARCHAR(32)
            );
            INSERT INTO molding_sample_orders (
              id, factory_id, order_number, doc_number, product_name, client_name, date, stage,
              order_type, workshop, send_to, supervisor, eng_name, reason, status,
              reject_reason, completed_date, created_at, updated_at
            ) VALUES (
              'BP-LEGACY-001', 'huaxing', 'LEGACY-001', 'W-G026-00', '旧库啤办单',
              'Legacy Client', '2026-07-01', 'T0', '啤办', 'A车间', '',
              '华兴工程主管', '华兴工程师', '旧库兼容测试', '待审核',
              '', '', '2026-07-01 08:00', '2026-07-01 08:00'
            );
            INSERT INTO molding_sample_audit_logs (
              id, order_id, action, actor_name, actor_role, from_status, to_status, reason, created_at
            ) VALUES (
              'BP-LEGACY-001-audit-001', 'BP-LEGACY-001', '工程提交',
              '华兴工程师', '工程师', '待审核', '待审核', '旧库审核记录', '2026-07-01 08:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


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


def huaxing_engineering_template_workbook() -> bytes:
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    rows = [
        ["华兴玩具制品(河源)有限公司"],
        ["啤办通知单"],
        [
            "客户：ShuShuPaPa",
            "",
            "",
            "产品编号：P50002008",
            "",
            "",
            "",
            "",
            "产品名称:30寸黑武士",
            "",
            "",
            "",
            "",
            "文件编号:W-G026-00 版本:00 修订:1",
        ],
        [
            "序号",
            "模具编号",
            "模具名称",
            "用料",
            "所需颜色",
            "PMS",
            "色粉",
            "套/啤",
            "啤办数（啤）",
            "用料重量（KG)",
            "报价周期",
            "需办日期",
            "要求",
            "备注",
        ],
        [
            "M01",
            "P50002008-01-01",
            "30寸黑武士-头盔",
            "PP（AV161）",
            "黑色",
            "Black C",
            "黑种",
            "2",
            30,
            15,
            "3天",
            "2026.2.10",
            "加急",
            "第一次试模",
        ],
        [
            "M02",
            "P50002008-01-02",
            "30寸黑武士-面罩",
            "ABS",
            "透明",
            "",
            "",
            "1",
            20,
            3.5,
            "",
            "2026/02/11",
            "",
            "",
        ],
        [],
        ["", "落单人：杨敬作", "", "", "", "", "", "", "落单日期：2026.2.3"],
    ]

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", excel_service._content_types_xml())
        workbook.writestr("_rels/.rels", excel_service._root_rels_xml())
        workbook.writestr("docProps/app.xml", excel_service._app_xml())
        workbook.writestr("docProps/core.xml", excel_service._core_xml())
        workbook.writestr("xl/workbook.xml", excel_service._workbook_xml())
        workbook.writestr("xl/_rels/workbook.xml.rels", excel_service._workbook_rels_xml())
        workbook.writestr("xl/styles.xml", excel_service._styles_xml())
        workbook.writestr("xl/worksheets/sheet1.xml", excel_service._sheet_xml(rows))

    return buffer.getvalue()


@pytest.fixture()
def client(monkeypatch):
    with make_client(monkeypatch) as test_client:
        yield test_client


def test_unauthenticated_access_to_molding_sample_api_is_rejected(client):
    response = client.get("/api/injection")

    assert response.status_code == 401


def test_legacy_sqlite_molding_sample_audit_columns_are_added_on_startup(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_path = TEST_TMP_DIR / f"legacy_molding_sample_{uuid4().hex}.db"
    create_legacy_molding_sample_sqlite_database(database_path)

    with make_client_with_database(monkeypatch, database_path) as legacy_client:
        login_as(legacy_client, "engineer")
        response = legacy_client.get("/api/injection")

    assert response.status_code == 200
    orders = response.json()
    assert orders[0]["order"]["id"] == "BP-LEGACY-001"
    assert orders[0]["audit_logs"][0]["actor_user_id"] == ""
    assert orders[0]["audit_logs"][0]["actor_roles"] == ""
    assert orders[0]["audit_logs"][0]["factory_scope"] == ""

    connection = sqlite3.connect(database_path)
    try:
        audit_columns = {row[1] for row in connection.execute("PRAGMA table_info(molding_sample_audit_logs)")}
        sensitive_audit_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(molding_sample_sensitive_audit_logs)")
        }
    finally:
        connection.close()

    assert {"actor_user_id", "actor_roles", "factory_scope"} <= audit_columns
    assert {"actor_user_id", "actor_roles", "factory_scope"} <= sensitive_audit_columns


def test_engineer_can_create_order_and_production_user_reads_notification_after_supervisor_approval(client):
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
    supervisor_response = client.patch("/api/injection/BP-API-001/status", json={"action": "主管通过"})
    assert supervisor_response.status_code == 200
    assert supervisor_response.json()["order"]["status"] == "待生产"

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


def test_engineer_submission_notifies_engineering_supervisor(client):
    login_as(client, "engineer")
    create_response = client.post("/api/injection", json=sample_order_payload("BP-NOTIFY-SUP-001"))
    assert create_response.status_code == 201

    login_as(client, "supervisor")
    notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={
            "target_module": "engineering_molding_sample",
            "target_role": "工程主管",
            "factory_id": "huaxing",
            "status": "未读",
        },
    )

    assert notifications_response.status_code == 200
    notifications = notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["order_id"] == "BP-NOTIFY-SUP-001"
    assert notifications[0]["target_role"] == "工程主管"
    assert notifications[0]["event_type"] == "待主管审核"


def test_supervisor_review_notification_is_handled_after_approval(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-NOTIFY-HANDLED-001"))

    login_as(client, "supervisor")
    approve_response = client.patch(
        "/api/injection/BP-NOTIFY-HANDLED-001/status",
        json={"action": "主管通过"},
    )
    assert approve_response.status_code == 200

    notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={
            "target_module": "engineering_molding_sample",
            "target_role": "工程主管",
            "order_id": "BP-NOTIFY-HANDLED-001",
            "status": "已处理",
        },
    )

    assert notifications_response.status_code == 200
    notifications = notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["event_type"] == "待主管审核"
    assert notifications[0]["actor_name"] == "华兴工程主管"


def test_supervisor_rejection_notifies_engineering_rework_queue(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-NOTIFY-REJECT-001"))

    login_as(client, "supervisor")
    reject_response = client.patch(
        "/api/injection/BP-NOTIFY-REJECT-001/status",
        json={"action": "主管驳回", "reason": "资料不完整"},
    )
    assert reject_response.status_code == 200

    login_as(client, "engineer")
    notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={
            "target_module": "engineering_molding_sample",
            "target_role": "工程部",
            "factory_id": "huaxing",
            "status": "未读",
        },
    )

    assert notifications_response.status_code == 200
    notifications = notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["order_id"] == "BP-NOTIFY-REJECT-001"
    assert notifications[0]["target_role"] == "工程部"
    assert notifications[0]["event_type"] == "审核驳回"


def test_notification_list_filters_by_target_role(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-NOTIFY-FILTER-001"))

    login_as(client, "supervisor")
    approve_response = client.patch(
        "/api/injection/BP-NOTIFY-FILTER-001/status",
        json={"action": "主管通过"},
    )
    assert approve_response.status_code == 200

    login_as(client, "molding_clerk")
    problem_response = client.post(
        "/api/problems",
        json={"order_id": "BP-NOTIFY-FILTER-001", "description": "啤机异常停机", "reported_by": "啤机部"},
    )
    assert problem_response.status_code == 201

    login_as(client, "supervisor")
    supervisor_notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={
            "target_module": "engineering_molding_sample",
            "target_role": "工程主管",
            "order_id": "BP-NOTIFY-FILTER-001",
            "status": "未读",
        },
    )
    assert supervisor_notifications_response.status_code == 200
    assert supervisor_notifications_response.json() == []

    login_as(client, "engineer")
    engineer_notifications_response = client.get(
        "/api/molding-sample-notifications",
        params={
            "target_module": "engineering_molding_sample",
            "target_role": "工程部",
            "order_id": "BP-NOTIFY-FILTER-001",
            "status": "未读",
        },
    )
    assert engineer_notifications_response.status_code == 200
    notifications = engineer_notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["event_type"] == "生产问题反馈"


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
    assert supervisor_response.json()["order"]["status"] == "待生产"
    assert supervisor_response.json()["audit_logs"][0]["actor_name"] == "华兴工程主管"

    supervisor_manager_step_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "经理通过"},
    )
    assert supervisor_manager_step_response.status_code == 403

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
        json={
            "items": [
                {
                    "id": "BP-WORKFLOW-001-001",
                    "actual_weight_kg": 2,
                    "injection_cost": 100,
                    "production_machine": "啤办机台-08",
                }
            ]
        },
    )
    assert item_response.status_code == 200
    assert item_response.json()["items"][0]["production_machine"] == "啤办机台-08"

    login_as(client, "engineer")
    engineering_detail_response = client.get("/api/injection/BP-WORKFLOW-001")
    assert engineering_detail_response.status_code == 200
    assert engineering_detail_response.json()["items"][0]["production_machine"] == "啤办机台-08"

    login_as(client, "molding_clerk")

    completed_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/status",
        json={"action": "标记完成", "today": "2026-07-01"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["order"]["status"] == "已完成"
    assert completed_response.json()["order"]["completed_date"] == "2026-07-01"


def test_engineer_can_withdraw_pending_order_and_resubmit(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-WITHDRAW-001"))

    withdraw_response = client.patch(
        "/api/injection/BP-WITHDRAW-001/status",
        json={"action": "工程撤回", "reason": "资料需要重新确认"},
    )
    assert withdraw_response.status_code == 200
    withdrawn_payload = withdraw_response.json()
    assert withdrawn_payload["order"]["status"] == "已撤回"
    assert withdrawn_payload["audit_logs"][0]["action"] == "工程撤回"
    assert withdrawn_payload["audit_logs"][0]["from_status"] == "待审核"
    assert withdrawn_payload["audit_logs"][0]["to_status"] == "已撤回"
    assert withdrawn_payload["audit_logs"][0]["reason"] == "资料需要重新确认"

    edited_payload = sample_order_payload("BP-WITHDRAW-001")
    edited_payload["order"]["product_name"] = "链条枪撤回修正版"
    edited_payload["items"][0]["color"] = "深蓝色"

    edit_response = client.put("/api/injection/BP-WITHDRAW-001", json=edited_payload)
    assert edit_response.status_code == 200
    assert edit_response.json()["order"]["status"] == "已撤回"
    assert edit_response.json()["order"]["product_name"] == "链条枪撤回修正版"

    resubmit_response = client.patch(
        "/api/injection/BP-WITHDRAW-001/status",
        json={"action": "工程重提", "reason": "撤回后已修正资料"},
    )
    assert resubmit_response.status_code == 200
    assert resubmit_response.json()["order"]["status"] == "待审核"
    assert resubmit_response.json()["audit_logs"][0]["action"] == "工程重提"


def test_molding_clerk_can_withdraw_completed_production_handoff(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-PROD-ROLLBACK-001"))

    login_as(client, "supervisor")
    approved_response = client.patch(
        "/api/injection/BP-PROD-ROLLBACK-001/status",
        json={"action": "主管通过"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["order"]["status"] == "待生产"

    login_as(client, "molding_clerk")
    start_response = client.patch(
        "/api/injection/BP-PROD-ROLLBACK-001/status",
        json={"action": "开始处理"},
    )
    assert start_response.status_code == 200
    assert start_response.json()["order"]["status"] == "生产中"

    item_response = client.patch(
        "/api/injection/BP-PROD-ROLLBACK-001/items",
        json={
            "items": [
                {
                    "id": "BP-PROD-ROLLBACK-001-001",
                    "actual_weight_kg": 2,
                    "injection_cost": 100,
                    "production_machine": "啤办机台-08",
                }
            ]
        },
    )
    assert item_response.status_code == 200

    completed_response = client.patch(
        "/api/injection/BP-PROD-ROLLBACK-001/status",
        json={"action": "标记完成", "today": "2026-07-03"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["order"]["status"] == "已完成"
    assert completed_response.json()["order"]["completed_date"] == "2026-07-03"

    rollback_response = client.patch(
        "/api/injection/BP-PROD-ROLLBACK-001/status",
        json={"action": "撤回完成", "reason": "啤机部发现回填用料需修正"},
    )

    assert rollback_response.status_code == 200
    rollback_payload = rollback_response.json()
    assert rollback_payload["order"]["status"] == "生产中"
    assert rollback_payload["order"]["completed_date"] == ""
    assert rollback_payload["audit_logs"][0]["action"] == "撤回完成"
    assert rollback_payload["audit_logs"][0]["from_status"] == "已完成"
    assert rollback_payload["audit_logs"][0]["to_status"] == "生产中"
    assert rollback_payload["audit_logs"][0]["reason"] == "啤机部发现回填用料需修正"


def test_engineer_can_withdraw_order_they_submitted_when_display_engineer_name_differs(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-WITHDRAW-ACTOR-001")
    payload["order"]["eng_name"] = "工程部协作"
    create_response = client.post("/api/injection", json=payload)
    assert create_response.status_code == 201
    assert create_response.json()["order"]["eng_name"] == "工程部协作"
    assert create_response.json()["audit_logs"][0]["actor_user_id"] == "user-engineer"

    withdraw_response = client.patch(
        "/api/injection/BP-WITHDRAW-ACTOR-001/status",
        json={"action": "工程撤回", "reason": "提交账号撤回主管审核"},
    )

    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["order"]["status"] == "已撤回"
    assert withdraw_response.json()["audit_logs"][0]["actor_user_id"] == "user-engineer"


def test_engineer_can_withdraw_legacy_order_submitted_by_actor_name(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-WITHDRAW-LEGACY-ACTOR-001")
    payload["order"]["eng_name"] = "杨敬作"
    create_response = client.post("/api/injection", json=payload)
    assert create_response.status_code == 201

    db_module = importlib.import_module("app.db")
    model_module = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        audit_log = (
            db.query(model_module.MoldingSampleAuditLog)
            .filter(model_module.MoldingSampleAuditLog.order_id == "BP-WITHDRAW-LEGACY-ACTOR-001")
            .first()
        )
        assert audit_log is not None
        audit_log.actor_user_id = ""
        db.commit()

    withdraw_response = client.patch(
        "/api/injection/BP-WITHDRAW-LEGACY-ACTOR-001/status",
        json={"action": "工程撤回", "reason": "历史账号撤回主管审核"},
    )

    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["order"]["status"] == "已撤回"
    assert withdraw_response.json()["audit_logs"][0]["actor_name"] == "华兴工程师"


def test_engineer_cannot_withdraw_after_supervisor_approval(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-WITHDRAW-LOCK-001"))

    login_as(client, "supervisor")
    approved_response = client.patch(
        "/api/injection/BP-WITHDRAW-LOCK-001/status",
        json={"action": "主管通过"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["order"]["status"] == "待生产"

    login_as(client, "engineer")
    withdraw_response = client.patch(
        "/api/injection/BP-WITHDRAW-LOCK-001/status",
        json={"action": "工程撤回", "reason": "主管已通过后尝试撤回"},
    )
    assert withdraw_response.status_code == 403
    assert "待审核" in withdraw_response.json()["detail"]


def test_rejected_order_can_be_edited_and_resubmitted_by_engineering(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-REJECT-001"))

    login_as(client, "supervisor")
    rejected_response = client.patch(
        "/api/injection/BP-REJECT-001/status",
        json={"action": "主管驳回", "reason": "原料和颜色需要修正"},
    )
    assert rejected_response.status_code == 200
    assert rejected_response.json()["order"]["status"] == "已驳回"
    assert rejected_response.json()["order"]["reject_reason"] == "原料和颜色需要修正"

    login_as(client, "engineer")
    edited_payload = sample_order_payload("BP-REJECT-001")
    edited_payload["order"]["product_name"] = "链条枪修正版"
    edited_payload["items"][0]["material"] = "ABS 740"
    edited_payload["items"][0]["color"] = "深蓝色"

    edit_response = client.put("/api/injection/BP-REJECT-001", json=edited_payload)
    assert edit_response.status_code == 200
    assert edit_response.json()["order"]["status"] == "已驳回"
    assert edit_response.json()["order"]["product_name"] == "链条枪修正版"
    assert edit_response.json()["items"][0]["material"] == "ABS 740"

    resubmit_response = client.patch(
        "/api/injection/BP-REJECT-001/status",
        json={"action": "工程重提", "reason": "工程已修正原料和颜色"},
    )
    assert resubmit_response.status_code == 200
    payload = resubmit_response.json()
    assert payload["order"]["status"] == "待审核"
    assert payload["order"]["reject_reason"] == ""
    assert payload["order"]["product_name"] == "链条枪修正版"
    assert payload["audit_logs"][0]["action"] == "工程重提"


def test_external_order_auto_completes_after_supervisor_approval(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-EXT-001", external=True))

    login_as(client, "supervisor")
    response = client.patch(
        "/api/injection/BP-EXT-001/status",
        json={"action": "主管通过", "today": "2026-07-01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["status"] == "已完成"
    assert payload["order"]["completed_date"] == "2026-07-01"
    assert payload["items"][0]["actual_weight_kg"] == 2.46
    assert payload["items"][0]["actual_amount_hkd"] == 29.83


def test_production_problem_feedback_is_saved_and_visible_to_engineering(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-PROBLEM-001"))

    blocked_response = client.post(
        "/api/problems",
        json={"order_id": "BP-PROBLEM-001", "description": "未到生产节点不应反馈"},
    )
    assert blocked_response.status_code == 403

    login_as(client, "supervisor")
    client.patch("/api/injection/BP-PROBLEM-001/status", json={"action": "主管通过"})

    login_as(client, "molding_clerk")
    client.patch("/api/injection/BP-PROBLEM-001/status", json={"action": "开始处理"})
    problem_response = client.post(
        "/api/problems",
        json={
            "order_id": "BP-PROBLEM-001",
            "description": "左枪身缩水，需工程确认胶口。",
        },
    )
    assert problem_response.status_code == 201
    problem = problem_response.json()
    assert problem["order_id"] == "BP-PROBLEM-001"
    assert problem["reported_by"] == "华兴啤机部文员"
    assert problem["status"] == "待处理"

    login_as(client, "engineer")
    detail_response = client.get("/api/injection/BP-PROBLEM-001")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["problems"][0]["description"] == "左枪身缩水，需工程确认胶口。"
    assert detail["audit_logs"][0]["action"] == "生产问题反馈"
    assert detail["notifications"][0]["event_type"] == "生产问题反馈"

    list_response = client.get("/api/problems", params={"order_id": "BP-PROBLEM-001"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == problem["id"]

    resolved_response = client.patch(f"/api/problems/{problem['id']}", json={"status": "已解决"})
    assert resolved_response.status_code == 200
    assert resolved_response.json()["status"] == "已解决"
    assert resolved_response.json()["resolved_at"] != ""


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


def test_only_admin_can_delete_locked_molding_sample_order(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-ADMIN-DELETE-001"))

    login_as(client, "supervisor")
    approved_response = client.patch(
        "/api/injection/BP-ADMIN-DELETE-001/status",
        json={"action": "主管通过"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["order"]["status"] == "待生产"

    login_as(client, "manager")
    manager_delete_response = client.delete("/api/injection/BP-ADMIN-DELETE-001")
    assert manager_delete_response.status_code == 403

    login_as(client, "admin")
    admin_delete_response = client.delete("/api/injection/BP-ADMIN-DELETE-001")
    assert admin_delete_response.status_code == 204
    assert client.get("/api/injection/BP-ADMIN-DELETE-001").status_code == 404


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

    carton_warehouse_profile = login_as(client, "carton_warehouse")
    assert "carton_mark:template_upload" in carton_warehouse_profile["permissions"]
    assert "molding_sample:inventory_issue" not in carton_warehouse_profile["permissions"]
    carton_warehouse_batch_response = client.post(
        "/api/inventory-batches",
        json={"material": "HIPS 425", "batch_no": "HIPS-20260701-A", "location": "A-01", "initial_weight_kg": 3},
    )
    assert carton_warehouse_batch_response.status_code == 403

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


def test_export_molding_sample_excel_template_has_report_styling(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-XLSX-STYLE-001"))

    export_response = client.get("/api/injection/BP-XLSX-STYLE-001/export-excel")
    assert export_response.status_code == 200

    detail_header_row = 10

    with ZipFile(BytesIO(export_response.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = workbook.read("xl/styles.xml").decode("utf-8")

    assert '<mergeCell ref="A1:V1"/>' in sheet_xml
    assert '<pane ySplit="10" topLeftCell="A11" activePane="bottomLeft" state="frozen"/>' in sheet_xml
    assert f'<autoFilter ref="A{detail_header_row}:V{detail_header_row}"/>' in sheet_xml
    assert '<cols>' in sheet_xml
    assert 'customWidth="1"' in sheet_xml
    assert '<col min="2" max="2" width="24" customWidth="1"/>' in sheet_xml
    assert '<col min="4" max="4" width="30" customWidth="1"/>' in sheet_xml
    assert '<row r="2" ht="22" customHeight="1">' in sheet_xml
    assert f'<row r="{detail_header_row}" ht="24" customHeight="1">' in sheet_xml
    assert ' s="1"' in sheet_xml
    assert ' s="2"' in sheet_xml
    assert ' s="3"' in sheet_xml
    assert ' s="4"' in sheet_xml
    assert ' s="5"' in sheet_xml
    assert '<cellXfs count="6">' in styles_xml
    assert '<fgColor rgb="FF0F172A"/>' in styles_xml
    assert '<fgColor rgb="FFECFDF5"/>' in styles_xml
    assert '<sheetView workbookViewId="0">' in sheet_xml
    assert '<pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/>' in sheet_xml


def test_preview_molding_sample_excel_import_does_not_create_order(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-XLSX-SOURCE"))

    export_response = client.get("/api/injection/BP-XLSX-SOURCE/export-excel")
    assert export_response.status_code == 200

    preview_response = client.post(
        "/api/injection/import-excel-preview",
        params={"order_id": "BP-XLSX-PREVIEW"},
        content=export_response.content,
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    assert preview_response.status_code == 200
    previewed = preview_response.json()
    assert previewed["order"]["id"] == "BP-XLSX-PREVIEW"
    assert previewed["items"][0]["id"] == "BP-XLSX-PREVIEW-001"
    assert "audit_logs" not in previewed

    lookup_response = client.get("/api/injection/BP-XLSX-PREVIEW")
    assert lookup_response.status_code == 404


def test_import_huaxing_engineering_molding_sample_template(client):
    login_as(client, "engineer")
    import_response = client.post(
        "/api/injection/import-excel",
        params={"order_id": "BP-HX-XLSX-001"},
        content=huaxing_engineering_template_workbook(),
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    assert import_response.status_code == 201
    imported = import_response.json()
    assert imported["order"] == {
        **imported["order"],
        "id": "BP-HX-XLSX-001",
        "factory_id": "huaxing",
        "order_number": "P50002008",
        "doc_number": "W-G026-00",
        "product_name": "30寸黑武士",
        "client_name": "ShuShuPaPa",
        "date": "2026-02-03",
        "stage": "T0",
        "order_type": "啤办",
        "workshop": "工程部",
        "supervisor": "",
        "eng_name": "杨敬作",
        "reason": "工程部啤办通知单导入",
    }
    assert len(imported["items"]) == 2

    first_item = imported["items"][0]
    assert first_item["id"] == "BP-HX-XLSX-001-001"
    assert first_item["sort_order"] == 1
    assert first_item["mold_id"] == "P50002008-01-01"
    assert first_item["mold_name"] == "30寸黑武士-头盔"
    assert first_item["material"] == "PP（AV161）"
    assert first_item["color"] == "黑色 / PMS Black C"
    assert first_item["pigment_no"] == "黑种"
    assert first_item["quantity"] == "2"
    assert first_item["shoot_qty"] == 30
    assert first_item["required_material_kg"] == 15
    assert first_item["mold_return_time"] == "2026-02-10"
    assert first_item["completion_time"] == "2026-02-10"
    assert first_item["notes"] == "报价周期：3天；要求：加急；备注：第一次试模"


def test_import_engineering_molding_sample_template_uses_selected_factory(client):
    login_as(client, "admin")
    import_response = client.post(
        "/api/injection/import-excel",
        params={"order_id": "BP-HD-XLSX-001", "factory_id": "huadeng"},
        content=huaxing_engineering_template_workbook(),
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    assert import_response.status_code == 201
    imported = import_response.json()
    assert imported["order"]["id"] == "BP-HD-XLSX-001"
    assert imported["order"]["factory_id"] == "huadeng"
    assert imported["order"]["workshop"] == "工程部"
    assert imported["order"]["supervisor"] == ""
    assert imported["order"]["reason"] == "工程部啤办通知单导入"
    assert imported["items"][0]["id"] == "BP-HD-XLSX-001-001"


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
