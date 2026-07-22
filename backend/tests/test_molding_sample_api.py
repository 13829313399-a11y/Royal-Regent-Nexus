import importlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event, Thread
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"
TEST_BUSINESS_NOW = datetime(2026, 7, 18, 16, 30, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
TEST_BUSINESS_DATE = TEST_BUSINESS_NOW.date().isoformat()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'molding_sample_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    molding_sample_service = importlib.import_module("app.services.molding_sample")
    molding_sample_excel_service = importlib.import_module("app.services.molding_sample_excel")
    business_tick = 0

    def ticking_business_now():
        nonlocal business_tick
        value = TEST_BUSINESS_NOW + timedelta(microseconds=business_tick)
        business_tick += 1
        return value

    monkeypatch.setattr(molding_sample_service, "business_now", ticking_business_now)
    monkeypatch.setattr(molding_sample_service, "business_today", lambda: TEST_BUSINESS_DATE)
    monkeypatch.setattr(molding_sample_excel_service, "business_now", lambda: TEST_BUSINESS_NOW)
    return TestClient(main.app)


def make_client_with_database(monkeypatch, database_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    molding_sample_service = importlib.import_module("app.services.molding_sample")
    molding_sample_excel_service = importlib.import_module("app.services.molding_sample_excel")
    business_tick = 0

    def ticking_business_now():
        nonlocal business_tick
        value = TEST_BUSINESS_NOW + timedelta(microseconds=business_tick)
        business_tick += 1
        return value

    monkeypatch.setattr(molding_sample_service, "business_now", ticking_business_now)
    monkeypatch.setattr(molding_sample_service, "business_today", lambda: TEST_BUSINESS_DATE)
    monkeypatch.setattr(molding_sample_excel_service, "business_now", lambda: TEST_BUSINESS_NOW)
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
              updated_at VARCHAR(32),
              production_factory_id VARCHAR(64),
              production_assigned_at VARCHAR(32) NOT NULL DEFAULT '',
              production_assigned_by VARCHAR(128) NOT NULL DEFAULT '',
              production_assignment_version INTEGER NOT NULL DEFAULT 0
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
            CREATE TABLE molding_sample_requisitions (
              id VARCHAR(96) PRIMARY KEY,
              factory_id VARCHAR(64) NOT NULL
            );
            CREATE TABLE molding_sample_inventory_batches (
              id VARCHAR(96) PRIMARY KEY,
              factory_id VARCHAR(64) NOT NULL
            );
            CREATE TABLE molding_sample_inventory_movements (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              factory_id VARCHAR(64) NOT NULL
            );
            CREATE TABLE molding_sample_dispatch_logs (
              id VARCHAR(96) PRIMARY KEY,
              order_id VARCHAR(64) NOT NULL,
              origin_factory_id VARCHAR(64) NOT NULL,
              from_production_factory_id VARCHAR(64),
              to_production_factory_id VARCHAR(64) NOT NULL,
              action VARCHAR(64) NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              actor_user_id VARCHAR(64) NOT NULL DEFAULT '',
              actor_name VARCHAR(128) NOT NULL DEFAULT '',
              created_at VARCHAR(32) NOT NULL DEFAULT ''
            );
            INSERT INTO molding_sample_orders (
              id, factory_id, order_number, doc_number, product_name, client_name, date, stage,
              order_type, workshop, send_to, supervisor, eng_name, reason, status,
              reject_reason, completed_date, created_at, updated_at, production_factory_id
            ) VALUES (
              'BP-LEGACY-001', 'huaxing', 'LEGACY-001', 'W-G026-00', '旧库啤办单',
              'Legacy Client', '2026-07-01', 'T0', '啤办', 'A车间', '',
              '华兴工程主管', '华兴工程师', '旧库兼容测试', '待审核',
              '', '', '2026-07-01 08:00', '2026-07-01 08:00', 'huaxing'
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
    ensure_test_user(username)
    password = ADMIN_TEST_PASSWORD if username == "admin" else "123456"
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()


TEST_USER_SPECS = {
    "engineer": ("user-engineer", "华兴工程师", "engineer", "huaxing", "engineering"),
    "engineer_peer": ("user-engineer-peer", "华兴工程同事", "engineer", "huaxing", "engineering"),
    "supervisor": ("user-supervisor", "华兴工程主管", "engineering_supervisor", "huaxing", "engineering"),
    "manager": ("user-manager", "华兴经理", "manager", "huaxing", "management"),
    "warehouse_keeper": (
        "user-warehouse-keeper",
        "华兴PMC仓管",
        "warehouse_keeper",
        "huaxing",
        "pmc-warehouse",
    ),
    "carton_warehouse": ("user-carton-warehouse", "华兴纸箱仓管", "carton_warehouse_keeper", "huaxing", "pmc-warehouse"),
    "qa_inspector": ("user-qa-inspector", "华兴QA检验员", "qa_inspector", "huaxing", "qa"),
    "molding_clerk": ("user-molding-clerk", "华兴啤机部文员", "molding_clerk", "huaxing", "molding"),
    "c_engineer": ("user-c-engineer", "华康C工程师", "engineer", "huakang-c", "engineering"),
    "c_supervisor": (
        "user-c-supervisor",
        "华康C工程主管",
        "engineering_supervisor",
        "huakang-c",
        "engineering",
    ),
    "d_engineer": ("user-d-engineer", "华康D工程师", "engineer", "huakang-d", "engineering"),
    "d_supervisor": (
        "user-d-supervisor",
        "华康D工程主管",
        "engineering_supervisor",
        "huakang-d",
        "engineering",
    ),
    "a_molding_clerk": (
        "user-a-molding-clerk",
        "华康A啤机部文员",
        "molding_clerk",
        "huakang-a",
        "molding",
    ),
    "b_molding_clerk": (
        "user-b-molding-clerk",
        "华康B啤机部文员",
        "molding_clerk",
        "huakang-b",
        "molding",
    ),
    "a_warehouse_keeper": (
        "user-a-warehouse-keeper",
        "华康A仓管",
        "warehouse_keeper",
        "huakang-a",
        "pmc-warehouse",
    ),
    "b_warehouse_keeper": (
        "user-b-warehouse-keeper",
        "华康B仓管",
        "warehouse_keeper",
        "huakang-b",
        "pmc-warehouse",
    ),
    "huaxing_molding_a_sales": (
        "user-huaxing-molding-a-sales",
        "华兴啤机车间 A 跟客业务",
        "sales_customer_owner",
        "huaxing",
        "sales-business",
    ),
}


def ensure_test_user(username: str) -> None:
    if username == "admin" or username not in TEST_USER_SPECS:
        return

    user_id, display_name, role_id, factory_id, department = TEST_USER_SPECS[username]
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        user = db.get(auth_models.AuthUser, user_id)
        if user is None:
            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                auth_models.AuthUser(
                    id=user_id,
                    username=username,
                    display_name=display_name,
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=auth_service.now_text(),
                    updated_at=auth_service.now_text(),
                )
            )
        else:
            user.username = username
            user.display_name = display_name
            user.status = "active"
            user.updated_at = auth_service.now_text()

        user_role_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        if db.get(auth_models.AuthUserRole, user_role_id) is None:
            db.add(
                auth_models.AuthUserRole(
                    id=user_role_id,
                    user_id=user_id,
                    role_id=role_id,
                    factory_id=factory_id,
                    department=department,
                )
            )
        profile = db.get(auth_models.EmployeeProfile, user_id)
        if profile is None:
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
        else:
            profile.primary_factory_id = factory_id
            profile.primary_department = department
            profile.confirmation_status = "confirmed"
            profile.updated_at = auth_service.now_text()
        db.commit()


def grant_permission_override(
    username: str,
    permission_code: str,
    *,
    factory_id: str = "*",
    department: str = "*",
    effect: str = "allow",
) -> None:
    ensure_test_user(username)
    user_id = TEST_USER_SPECS[username][0]
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        permission = db.scalar(
            select(auth_models.AuthPermission).where(
                auth_models.AuthPermission.code == permission_code
            )
        )
        assert permission is not None, f"permission is not registered: {permission_code}"
        override_id = f"test:{user_id}:{permission.id}:{effect}:{factory_id}:{department}"
        if db.get(auth_models.AuthUserPermissionOverride, override_id) is None:
            db.add(
                auth_models.AuthUserPermissionOverride(
                    id=override_id,
                    user_id=user_id,
                    permission_id=permission.id,
                    effect=effect,
                    factory_id=factory_id,
                    department=department,
                    status="active",
                    valid_from="",
                    valid_until="",
                    reason="跨厂啤办只读测试",
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
                "mold_dimensions": "650 × 450 × 380 mm",
                "mold_presence_status": "in_factory",
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


_UNSET = object()


def set_board_order_state(order_id, *, status=None, actual_weight_kg=_UNSET):
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, order_id)
        assert order is not None
        if status is not None:
            order.status = status
        if actual_weight_kg is not _UNSET:
            item = db.scalar(
                select(molding_models.MoldingSampleItem)
                .where(molding_models.MoldingSampleItem.order_id == order_id)
                .order_by(molding_models.MoldingSampleItem.sort_order)
            )
            assert item is not None
            item.actual_weight_kg = actual_weight_kg
        db.commit()


def create_fixed_position_test_user(
    username: str,
    role_id: str,
    department: str,
    factory_id: str = "huaxing",
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    with db_module.SessionLocal() as db:
        if db.get(auth_models.AuthUser, user_id) is not None:
            return
        now = auth_service.now_text()
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
                created_at=now,
                updated_at=now,
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
                position=username,
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserAuthorizationRevision(
                user_id=user_id,
                revision=1,
                updated_at=now,
            )
        )
        db.commit()


def login_fixed_position_test_user(client, username: str):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    assert response.status_code == 200
    return response.json()


def add_board_problem(order_id, *, suffix="1", problem_status="待处理", description="表面缩痕"):
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, order_id)
        assert order is not None
        db.add(
            molding_models.MoldingSampleProblem(
                id=f"{order_id}-problem-{suffix}",
                factory_id=order.factory_id,
                order_type="injection",
                order_id=order.id,
                order_number=order.order_number,
                description=description,
                reported_by="啤机部",
                status=problem_status,
                created_at="2026-07-15 08:00",
                resolved_at="2026-07-15 09:00" if problem_status == "已解决" else "",
            )
        )
        db.commit()


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


@pytest.fixture()
def enforce_client(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    with make_client(monkeypatch) as test_client:
        yield test_client


@pytest.fixture(params=["legacy", "shadow", "enforce"])
def position_scope_client(monkeypatch, request):
    monkeypatch.setenv("AUTHZ_MODE", request.param)
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
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
        item_columns = {row[1] for row in connection.execute("PRAGMA table_info(molding_sample_items)")}
    finally:
        connection.close()

    assert {"actor_user_id", "actor_roles", "factory_scope"} <= audit_columns
    assert {"actor_user_id", "actor_roles", "factory_scope"} <= sensitive_audit_columns
    assert {
        "mold_dimensions",
        "mold_presence_status",
        "material_components",
        "material_usage_type",
        "actual_material_cost_components",
    } <= item_columns


def test_create_generates_order_and_item_ids_when_client_omits_them(client):
    login_as(client, "engineer")
    payload = sample_order_payload("")
    payload["order"].pop("id")
    first_item = payload["items"][0]
    first_item.pop("id")
    second_item = {
        **first_item,
        "id": "stale-client-item-id",
        "order_id": "stale-client-order-id",
        "sort_order": 2,
        "mold_id": "M-002",
        "mold_name": "弹匣",
    }
    payload["items"] = [first_item, second_item]

    response = client.post("/api/injection", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    generated_order_id = body["order"]["id"]
    assert re.fullmatch(r"BP-\d{14}-[0-9A-F]{12}", generated_order_id)
    assert [item["id"] for item in body["items"]] == [
        f"{generated_order_id}-001",
        f"{generated_order_id}-002",
    ]
    assert {item["order_id"] for item in body["items"]} == {generated_order_id}


@pytest.mark.parametrize("item_count", [1, 2])
def test_explicit_legacy_order_id_generates_any_missing_item_ids(client, item_count):
    login_as(client, "engineer")
    order_id = f"BP-LEGACY-MISSING-ITEM-{item_count}"
    payload = sample_order_payload(order_id)
    first_item = payload["items"][0]
    first_item.pop("id")
    payload["items"] = [
        {
            **first_item,
            "sort_order": index,
            "mold_id": f"M-{index:03d}",
        }
        for index in range(1, item_count + 1)
    ]

    response = client.post("/api/injection", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        f"{order_id}-{index:03d}"
        for index in range(1, item_count + 1)
    ]
    assert {item["order_id"] for item in body["items"]} == {order_id}


def test_same_product_number_can_create_two_orders_with_distinct_generated_ids(client):
    login_as(client, "engineer")
    payload = sample_order_payload("")
    payload["order"].pop("id")
    payload["items"][0].pop("id")

    first_response = client.post("/api/injection", json=payload)
    payload["order"]["stage"] = "EP"
    second_response = client.post("/api/injection", json=payload)

    assert first_response.status_code == 201, first_response.text
    assert second_response.status_code == 201, second_response.text
    first_body = first_response.json()
    second_body = second_response.json()
    assert first_body["order"]["order_number"] == "62437"
    assert second_body["order"]["order_number"] == "62437"
    assert first_body["order"]["stage"] == "T0"
    assert second_body["order"]["stage"] == "EP"
    assert first_body["order"]["id"] != second_body["order"]["id"]
    assert first_body["items"][0]["id"] == f'{first_body["order"]["id"]}-001'
    assert second_body["items"][0]["id"] == f'{second_body["order"]["id"]}-001'


def test_edit_request_still_requires_the_explicit_order_id(client):
    login_as(client, "engineer")
    order_id = "BP-EDIT-ID-REQUIRED-001"
    assert client.post("/api/injection", json=sample_order_payload(order_id)).status_code == 201
    edit_payload = sample_order_payload(order_id)
    edit_payload["order"].pop("id")

    response = client.put(f"/api/injection/{order_id}", json=edit_payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "order", "id"]


def test_create_with_an_explicit_duplicate_order_id_returns_stable_conflict(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-EXPLICIT-DUPLICATE-001")

    first_response = client.post("/api/injection", json=payload)
    duplicate_response = client.post("/api/injection", json=payload)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "啤办单编号已存在"}

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        orders = list(db.scalars(
            select(molding_models.MoldingSampleOrder).where(
                molding_models.MoldingSampleOrder.id == "BP-EXPLICIT-DUPLICATE-001",
            )
        ).all())
        items = list(db.scalars(
            select(molding_models.MoldingSampleItem).where(
                molding_models.MoldingSampleItem.order_id == "BP-EXPLICIT-DUPLICATE-001",
            )
        ).all())
    assert len(orders) == 1
    assert len(items) == 1


def test_concurrent_create_with_the_same_explicit_order_id_has_one_winner(client, monkeypatch):
    login_as(client, "engineer")
    main_module = importlib.import_module("app.main")
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    order_id = "BP-EXPLICIT-CONCURRENT-001"

    with TestClient(main_module.app) as other_client:
        login_as(other_client, "engineer")
        original_flush = db_module.Session.flush
        order_flush_barrier = Barrier(2)

        def synchronized_order_flush(session, *args, **kwargs):
            if any(
                isinstance(record, molding_models.MoldingSampleOrder) and record.id == order_id
                for record in session.new
            ):
                order_flush_barrier.wait(timeout=10)
            return original_flush(session, *args, **kwargs)

        monkeypatch.setattr(db_module.Session, "flush", synchronized_order_flush)
        results: list[object] = []

        def create(test_client):
            try:
                results.append(test_client.post("/api/injection", json=sample_order_payload(order_id)))
            except BaseException as error:  # pragma: no cover - surfaced below
                results.append(error)

        threads = [Thread(target=create, args=(test_client,)) for test_client in (client, other_client)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)

    errors = [result for result in results if isinstance(result, BaseException)]
    assert errors == []
    responses = [result for result in results if not isinstance(result, BaseException)]
    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json() == {"detail": "啤办单编号已存在"}

    with db_module.SessionLocal() as db:
        orders = list(db.scalars(
            select(molding_models.MoldingSampleOrder).where(molding_models.MoldingSampleOrder.id == order_id)
        ).all())
        items = list(db.scalars(
            select(molding_models.MoldingSampleItem).where(molding_models.MoldingSampleItem.order_id == order_id)
        ).all())
    assert len(orders) == 1
    assert len(items) == 1


def test_generated_order_id_collision_rolls_back_and_retries(client, monkeypatch):
    login_as(client, "engineer")
    collision_id = "BP-GENERATED-COLLISION"
    retry_id = "BP-GENERATED-RETRY"
    assert client.post("/api/injection", json=sample_order_payload(collision_id)).status_code == 201

    service = importlib.import_module("app.services.molding_sample")
    generated_ids = iter([collision_id, retry_id])
    monkeypatch.setattr(service, "generate_molding_sample_order_id", lambda: next(generated_ids))
    payload = sample_order_payload("")
    payload["order"].pop("id")
    payload["items"][0].pop("id")

    response = client.post("/api/injection", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["order"]["id"] == retry_id
    assert body["items"][0]["id"] == f"{retry_id}-001"
    assert body["items"][0]["order_id"] == retry_id


def test_molding_sample_create_and_edit_keep_timing_fields_server_owned(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-SERVER-TIME-001")
    payload["order"].update(
        {
            "completed_date": "2099-01-01",
            "created_at": "2000-01-01 00:00:00",
            "updated_at": "2000-01-01 00:00:00",
        }
    )

    created_response = client.post("/api/injection", json=payload)

    assert created_response.status_code == 201
    assert created_response.json()["order"]["created_at"].startswith("2026-07-18 16:30:45.")
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-SERVER-TIME-001")
        assert order is not None
        assert order.completed_date == ""
        assert order.created_at == "2026-07-18 16:30:45"
        assert order.updated_at == "2026-07-18 16:30:45"
        order.completed_date = "2026-07-17"
        db.commit()

    edit_payload = sample_order_payload("BP-SERVER-TIME-001")
    edit_payload["order"].update(
        {
            "completed_date": "2099-12-31",
            "created_at": "1999-12-31 23:59:59",
            "updated_at": "1999-12-31 23:59:59",
        }
    )
    edit_payload["order"]["product_name"] = "服务端时间字段保护"
    edited_response = client.put("/api/injection/BP-SERVER-TIME-001", json=edit_payload)

    assert edited_response.status_code == 200
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-SERVER-TIME-001")
        assert order is not None
        assert order.product_name == "服务端时间字段保护"
        assert order.completed_date == "2026-07-17"
        assert order.created_at == "2026-07-18 16:30:45"
        assert order.updated_at == "2026-07-18 16:30:45"


def test_molding_sample_response_derives_legacy_dates_from_audits_without_writing_database(client):
    login_as(client, "engineer")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-LEGACY-TIME-DERIVE-001"),
    ).status_code == 201

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-LEGACY-TIME-DERIVE-001")
        assert order is not None
        order.status = "已完成"
        order.created_at = "2026-02-03 09:00:00"
        order.completed_date = "2026-07-03"

        initial_audit = db.scalar(
            select(molding_models.MoldingSampleAuditLog).where(
                molding_models.MoldingSampleAuditLog.order_id == order.id,
            )
        )
        assert initial_audit is not None
        initial_audit.created_at = "2026-07-14 08:00:00"
        db.add_all(
            [
                molding_models.MoldingSampleAuditLog(
                    id="BP-LEGACY-TIME-DERIVE-001-complete-old",
                    order_id=order.id,
                    action="标记完成",
                    actor_name="华兴啤机部文员",
                    actor_role="啤机部文员",
                    from_status="生产中",
                    to_status="已完成",
                    created_at="2026-07-15T15:30:00Z",
                ),
                molding_models.MoldingSampleAuditLog(
                    id="BP-LEGACY-TIME-DERIVE-001-complete-latest",
                    order_id=order.id,
                    action="标记完成",
                    actor_name="华兴啤机部文员",
                    actor_role="啤机部文员",
                    from_status="生产中",
                    to_status="已完成",
                    created_at="2026-07-15T16:30:00Z",
                ),
            ]
        )
        db.commit()

    response = client.get("/api/injection/BP-LEGACY-TIME-DERIVE-001")

    assert response.status_code == 200
    assert response.json()["order"]["created_at"] == "2026-07-14 08:00:00"
    assert response.json()["order"]["completed_date"] == "2026-07-16"
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-LEGACY-TIME-DERIVE-001")
        assert order is not None
        assert order.created_at == "2026-02-03 09:00:00"
        assert order.completed_date == "2026-07-03"


def test_server_side_material_price_seed_is_additive_once_and_never_overwrites_existing_rows(client):
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    molding_service = importlib.import_module("app.services.molding_sample")
    source_rows = json.loads(molding_service.RAW_MATERIAL_PRICES_PATH.read_text(encoding="utf-8"))
    assert len(source_rows) == 196
    assert sum("other_cost_hkd_per_lb" in row for row in source_rows) == 48
    assert next(row for row in source_rows if row["material"] == "HIPS HI425") == {
        "material": "HIPS HI425",
        "unit_price": 6.27,
        "other_cost_hkd_per_lb": 0.12,
    }
    with db_module.SessionLocal() as db:
        prices = list(db.scalars(select(molding_models.MoldingSampleMaterialPrice)).all())
        price_by_material = {price.material: price.unit_price for price in prices}
        assert len(prices) == len(price_by_material)
        assert len(prices) == 203
        assert price_by_material["HIPS HI425"] == pytest.approx(6.27)
        assert price_by_material["ABS SD0150W"] == pytest.approx(7.537445)
        assert price_by_material["HIPS 425"] == pytest.approx(5.5)

        db.query(molding_models.MoldingSampleMaterialPrice).delete()
        marker = db.get(
            molding_models.MoldingSampleSetting,
            molding_service.RAW_MATERIAL_PRICES_MARKER_KEY,
        )
        db.delete(marker)
        db.add_all(
            [
                molding_models.MoldingSampleMaterialPrice(
                    material="HIPS HI425",
                    unit_price=99.0,
                    notes="经理自定义同名价不得覆盖",
                ),
                molding_models.MoldingSampleMaterialPrice(
                    material="经理自定义材料",
                    unit_price=9.99,
                    notes="不得删除",
                ),
            ]
        )
        db.commit()

        molding_service.seed_molding_sample_defaults(db)
        first_pass = list(db.scalars(select(molding_models.MoldingSampleMaterialPrice)).all())
        first_pass_by_material = {price.material: price for price in first_pass}
        assert len(first_pass) == 204
        assert first_pass_by_material["HIPS HI425"].unit_price == 99.0
        assert first_pass_by_material["HIPS HI425"].notes == "经理自定义同名价不得覆盖"
        assert first_pass_by_material["经理自定义材料"].unit_price == 9.99
        assert db.get(
            molding_models.MoldingSampleSetting,
            molding_service.RAW_MATERIAL_PRICES_MARKER_KEY,
        ) is not None

        db.delete(first_pass_by_material["ABS SD0150W"])
        db.commit()
        molding_service.seed_molding_sample_defaults(db)
        assert db.scalar(
            select(molding_models.MoldingSampleMaterialPrice).where(
                molding_models.MoldingSampleMaterialPrice.material == "ABS SD0150W"
            )
        ) is None


def test_material_components_are_canonicalized_and_priced_per_component(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-COMPONENT-COST-001")
    payload["items"][0].update({
        "material": "客户端冲突文本",
        "material_usage_type": "trial",
        "material_components": [
            {"material": "HIPS 425", "ratio_percent": 80, "source_type": "virgin"},
            {"material": "HIPS 425", "ratio_percent": 20, "source_type": "runner"},
        ],
    })
    payload["items"].append({
        **payload["items"][0],
        "id": "BP-COMPONENT-COST-001-002",
        "material_usage_type": "production",
        "material_components": [
            {"material": "HIPS 425", "ratio_percent": 80, "source_type": "virgin"},
            {"material": "ABS 740", "ratio_percent": 20, "source_type": "runner"},
        ],
    })

    created = client.post("/api/injection", json=payload)
    assert created.status_code == 201
    assert created.json()["items"][0]["material"] == "80% HIPS 425 + 20% HIPS 425 水口料"
    assert created.json()["items"][0]["material_usage_type"] == "trial"
    assert created.json()["items"][1]["material"] == "80% HIPS 425 + 20% ABS 740 水口料"

    login_as(client, "supervisor")
    assert client.patch(
        "/api/injection/BP-COMPONENT-COST-001/status",
        json={"action": "主管通过"},
    ).status_code == 200
    login_as(client, "molding_clerk")
    costed = client.patch(
        "/api/injection/BP-COMPONENT-COST-001/items",
        json={"items": [
            {"id": "BP-COMPONENT-COST-001-001", "actual_weight_kg": 10},
            {"id": "BP-COMPONENT-COST-001-002", "actual_weight_kg": 10},
        ]},
    )
    assert costed.status_code == 200
    assert costed.json()["items"][0]["actual_amount_hkd"] == 121.25
    assert costed.json()["items"][1]["actual_amount_hkd"] == 132.27
    assert costed.json()["items"][0]["actual_material_cost_components"] == [
        {
            "material": "HIPS 425",
            "source_type": "virgin",
            "ratio_percent": 80.0,
            "weight_kg": 8.0,
            "unit_price": 5.5,
            "amount_hkd": 97.0,
        },
        {
            "material": "HIPS 425",
            "source_type": "runner",
            "ratio_percent": 20.0,
            "weight_kg": 2.0,
            "unit_price": 5.5,
            "amount_hkd": 24.25,
        },
    ]


def test_forced_component_recalculation_clears_stale_total_and_snapshot_when_price_is_missing(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-COMPONENT-MISSING-001")
    payload["items"][0].update({
        "material_components": [
            {"material": "未维护价格原料", "ratio_percent": 100, "source_type": "virgin"},
        ],
    })
    assert client.post("/api/injection", json=payload).status_code == 201
    login_as(client, "supervisor")
    client.patch("/api/injection/BP-COMPONENT-MISSING-001/status", json={"action": "主管通过"})
    login_as(client, "molding_clerk")
    response = client.patch(
        "/api/injection/BP-COMPONENT-MISSING-001/items",
        json={"items": [{
            "id": "BP-COMPONENT-MISSING-001-001",
            "actual_weight_kg": 1,
            "actual_amount_hkd": 999,
        }]},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["actual_amount_hkd"] is None
    assert response.json()["items"][0]["actual_material_cost_components"] == []


def test_legacy_runner_material_strings_use_base_and_named_runner_prices(client):
    login_as(client, "manager")
    prices = client.post(
        "/api/manager-update-prices",
        json={
            "prices": [
                {"material": "ABS", "unit_price": 8, "notes": "测试"},
                {"material": "PVC", "unit_price": 5, "notes": "测试"},
            ],
            "rmb_to_hkd_rate": 1.08,
        },
    )
    assert prices.status_code == 200

    login_as(client, "engineer")
    payload = sample_order_payload("BP-LEGACY-MIX-001")
    payload["items"][0]["material"] = "80%ABS+20%水口料"
    payload["items"].append({
        **payload["items"][0],
        "id": "BP-LEGACY-MIX-001-002",
        "material": "80%ABS+20%PVC水口料",
    })
    assert client.post("/api/injection", json=payload).status_code == 201
    login_as(client, "supervisor")
    client.patch("/api/injection/BP-LEGACY-MIX-001/status", json={"action": "主管通过"})
    login_as(client, "molding_clerk")
    response = client.patch(
        "/api/injection/BP-LEGACY-MIX-001/items",
        json={"items": [
            {"id": "BP-LEGACY-MIX-001-001", "actual_weight_kg": 10},
            {"id": "BP-LEGACY-MIX-001-002", "actual_weight_kg": 10},
        ]},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["actual_amount_hkd"] == 176.37
    assert response.json()["items"][1]["actual_amount_hkd"] == 163.15


def test_legacy_material_parser_is_strict_and_accepts_single_full_ratio_segment():
    molding_service = importlib.import_module("app.services.molding_sample")
    assert molding_service.parse_legacy_material_components("100%ABS") == [
        {"material": "ABS", "ratio_percent": 100.0, "source_type": "virgin"}
    ]
    assert molding_service.parse_legacy_material_components("80%PC+ABS + 20%水口料") == [
        {"material": "PC+ABS", "ratio_percent": 80.0, "source_type": "virgin"},
        {"material": "PC+ABS", "ratio_percent": 20.0, "source_type": "runner"},
    ]
    assert molding_service.parse_legacy_material_components("PA66+30%GF") == []
    assert molding_service.parse_legacy_material_components("80%ABS+错误段") is None
    assert molding_service.parse_legacy_material_components("80%ABS+19%PVC水口料") is None
    assert molding_service.parse_legacy_material_components("80%ABS+0%PVC水口料") is None


@pytest.mark.parametrize(
    "components",
    [
        [
            {"material": "ABS", "ratio_percent": 50, "source_type": "virgin"},
            {"material": "ABS", "ratio_percent": 50, "source_type": "virgin"},
        ],
        [
            {"material": "ABS", "ratio_percent": 80, "source_type": "virgin"},
            {"material": "PVC", "ratio_percent": 19.98, "source_type": "runner"},
        ],
        [{"material": "   ", "ratio_percent": 100, "source_type": "virgin"}],
    ],
)
def test_material_component_validation_rejects_invalid_explicit_components(client, components):
    login_as(client, "engineer")
    payload = sample_order_payload(f"BP-COMPONENT-INVALID-{uuid4().hex[:8]}")
    payload["items"][0]["material_components"] = components
    assert client.post("/api/injection", json=payload).status_code == 422


def test_authenticated_users_without_molding_read_cannot_browse_samples(client):
    login_as(client, "engineer")
    create_response = client.post("/api/injection", json=sample_order_payload("BP-BROWSE-001"))
    assert create_response.status_code == 201

    profile = login_as(client, "qa_inspector")
    assert "molding_sample:read" not in profile["permissions"]

    list_response = client.get("/api/injection")
    assert list_response.status_code == 200
    assert list_response.json() == []

    detail_response = client.get("/api/injection/BP-BROWSE-001")
    assert detail_response.status_code == 403
    assert client.get("/api/injection/BP-BROWSE-001/export-excel").status_code == 403
    assert client.get(
        "/api/injection/export-excel",
        params=[("order_ids", "BP-BROWSE-001")],
    ).status_code == 403
    problems_response = client.get("/api/problems", params={"order_id": "BP-BROWSE-001"})
    assert problems_response.status_code == 403


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
    assert payload["items"][0]["mold_dimensions"] == "650 × 450 × 380 mm"
    assert payload["items"][0]["mold_presence_status"] == "in_factory"

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


def test_create_order_ignores_client_supplied_status_and_starts_review(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-STATUS-BYPASS-001")
    payload["order"]["status"] = "已完成"

    response = client.post("/api/injection", json=payload)

    assert response.status_code == 201
    created = response.json()
    assert created["order"]["status"] == "待审核"
    assert created["audit_logs"][0]["from_status"] == "待审核"
    assert created["audit_logs"][0]["to_status"] == "待审核"
    assert created["notifications"][0]["target_role"] == "工程主管"
    assert created["notifications"][0]["event_type"] == "待主管审核"


def test_factory_scope_limits_molding_sample_reads_and_writes(client):
    login_as(client, "admin")
    huadeng_payload = sample_order_payload("BP-HD-SCOPE-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    create_response = client.post("/api/injection", json=huadeng_payload)
    assert create_response.status_code == 201

    login_as(client, "engineer")
    list_response = client.get("/api/injection")
    assert list_response.status_code == 200
    assert all(record["order"]["id"] != "BP-HD-SCOPE-001" for record in list_response.json())

    detail_response = client.get("/api/injection/BP-HD-SCOPE-001")
    assert detail_response.status_code == 403

    single_export_response = client.get("/api/injection/BP-HD-SCOPE-001/export-excel")
    assert single_export_response.status_code == 403

    batch_export_response = client.get(
        "/api/injection/export-excel",
        params=[("order_ids", "BP-HD-SCOPE-001")],
    )
    assert batch_export_response.status_code == 403

    edited_payload = sample_order_payload("BP-HD-SCOPE-001")
    edited_payload["order"]["factory_id"] = "huadeng"
    edited_payload["order"]["product_name"] = "华登跨厂区误改"
    edit_response = client.put("/api/injection/BP-HD-SCOPE-001", json=edited_payload)
    assert edit_response.status_code == 403

    login_as(client, "supervisor")
    approval_response = client.patch("/api/injection/BP-HD-SCOPE-001/status", json={"action": "主管通过"})
    assert approval_response.status_code == 403

    login_as(client, "admin")
    admin_approval_response = client.patch("/api/injection/BP-HD-SCOPE-001/status", json={"action": "主管通过"})
    assert admin_approval_response.status_code == 200
    assert admin_approval_response.json()["order"]["status"] == "待生产"


def test_factory_filtered_order_list_returns_only_the_requested_factory_data(client):
    login_as(client, "admin")
    huaxing_payload = sample_order_payload("BP-HX-FACTORY-LIST-001")
    huadeng_payload = sample_order_payload("BP-HD-FACTORY-LIST-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"

    assert client.post("/api/injection", json=huaxing_payload).status_code == 201
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201

    huadeng_response = client.get("/api/injection", params={"factory_id": "huadeng"})
    assert huadeng_response.status_code == 200
    assert [record["order"]["id"] for record in huadeng_response.json()] == ["BP-HD-FACTORY-LIST-001"]

    empty_response = client.get("/api/injection", params={"factory_id": "huakang-b"})
    assert empty_response.status_code == 200
    assert empty_response.json() == []


def test_engineering_board_page_uses_true_five_row_pages_and_keeps_legacy_list_contract(client):
    login_as(client, "admin")
    for sequence in range(1, 13):
        order_id = f"BP-BOARD-PAGE-{sequence:03d}"
        payload = sample_order_payload(order_id)
        payload["order"]["created_at"] = f"2026-07-{sequence:02d} 08:00"
        payload["order"]["product_name"] = f"分页啤办 {sequence:02d}"
        assert client.post("/api/injection", json=payload).status_code == 201

    set_board_order_state("BP-BOARD-PAGE-012", status="待经理审核")

    first_page_response = client.get(
        "/api/injection/board/page",
        params={"factory_id": "huaxing", "status": "待审核"},
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total"] == 12
    assert first_page["page"] == 1
    assert first_page["page_size"] == 5
    assert first_page["page_count"] == 3
    assert [row["order"]["id"] for row in first_page["rows"]] == [
        "BP-BOARD-PAGE-012",
        "BP-BOARD-PAGE-011",
        "BP-BOARD-PAGE-010",
        "BP-BOARD-PAGE-009",
        "BP-BOARD-PAGE-008",
    ]
    assert first_page["rows"][0]["order"]["status"] == "待经理审核"
    assert len(first_page["rows"][0]["items"]) == 1
    assert first_page["rows"][0]["audit_logs"]

    second_page_response = client.get(
        "/api/injection/board/page",
        params={
            "factory_id": "huaxing",
            "status": "待审核",
            "page": 2,
            "page_size": 5,
        },
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert [row["order"]["id"] for row in second_page["rows"]] == [
        "BP-BOARD-PAGE-007",
        "BP-BOARD-PAGE-006",
        "BP-BOARD-PAGE-005",
        "BP-BOARD-PAGE-004",
        "BP-BOARD-PAGE-003",
    ]

    clamped_page_response = client.get(
        "/api/injection/board/page",
        params={
            "factory_id": "huaxing",
            "status": "待审核",
            "page": 99,
            "page_size": 5,
        },
    )
    assert clamped_page_response.status_code == 200
    clamped_page = clamped_page_response.json()
    assert clamped_page["page"] == 3
    assert clamped_page["page_count"] == 3
    assert [row["order"]["id"] for row in clamped_page["rows"]] == [
        "BP-BOARD-PAGE-002",
        "BP-BOARD-PAGE-001",
    ]

    legacy_response = client.get("/api/injection", params={"factory_id": "huaxing"})
    assert legacy_response.status_code == 200
    legacy_rows = legacy_response.json()
    assert len(legacy_rows) == 12
    assert set(legacy_rows[0]) == {
        "order",
        "items",
        "audit_logs",
        "dispatch_logs",
        "notifications",
        "problems",
        "trial_reports",
        "read_source",
        "can_view_cost",
    }

    formerly_conflicting_payload = sample_order_payload("board-page")
    assert client.post("/api/injection", json=formerly_conflicting_payload).status_code == 201
    formerly_conflicting_detail = client.get("/api/injection/board-page")
    assert formerly_conflicting_detail.status_code == 200
    assert formerly_conflicting_detail.json()["order"]["id"] == "board-page"


def test_engineering_board_summary_reports_normalized_status_and_attention_counts(client):
    login_as(client, "admin")
    order_specs = [
        ("BP-BOARD-SUM-PENDING", "待审核", False, _UNSET),
        ("BP-BOARD-SUM-MANAGER", "待经理审核", False, _UNSET),
        ("BP-BOARD-SUM-WAITING", "待生产", False, _UNSET),
        ("BP-BOARD-SUM-RUN-MISSING", "生产中", False, None),
        ("BP-BOARD-SUM-RUN-FILLED", "生产中", False, 1.25),
        ("BP-BOARD-SUM-RUN-EXTERNAL", "生产中", True, None),
        ("BP-BOARD-SUM-COMPLETED", "已完成", False, 1.0),
        ("BP-BOARD-SUM-REJECTED", "已驳回", False, _UNSET),
        ("BP-BOARD-SUM-WITHDRAWN", "已撤回", False, _UNSET),
    ]
    for sequence, (order_id, order_status, external, actual_weight) in enumerate(order_specs, start=1):
        payload = sample_order_payload(order_id, external=external)
        payload["order"]["created_at"] = f"2026-07-{sequence:02d} 08:00"
        assert client.post("/api/injection", json=payload).status_code == 201
        set_board_order_state(order_id, status=order_status, actual_weight_kg=actual_weight)

    add_board_problem("BP-BOARD-SUM-RUN-MISSING", suffix="1")
    add_board_problem("BP-BOARD-SUM-RUN-MISSING", suffix="2", description="披锋")
    add_board_problem(
        "BP-BOARD-SUM-COMPLETED",
        suffix="resolved",
        problem_status="已解决",
    )

    response = client.get(
        "/api/injection/board/summary",
        params={"factory_id": "huaxing"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "total": 9,
        "status_counts": {
            "待审核": 2,
            "待生产": 1,
            "生产中": 3,
            "已完成": 1,
            "已驳回": 1,
            "已撤回": 1,
        },
        "review_count": 2,
        "production_count": 4,
        "completed_count": 1,
        "rejected_count": 1,
        "withdrawn_count": 1,
        "unresolved_problem_count": 1,
        "production_data_pending_count": 1,
    }


def test_engineering_board_search_matches_normalized_order_item_component_and_problem_fields(client):
    login_as(client, "admin")
    searchable_payload = sample_order_payload("BP-BOARD-SEARCH-001")
    searchable_payload["order"].update(
        {
            "doc_number": "W-G026-00",
            "product_name": "ShuShuPaPa 黑武士",
            "created_at": "2026-07-15 10:00",
        }
    )
    searchable_payload["items"][0].update(
        {
            "mold_id": "jp-5678",
            "material": "70% ABS PA-757 + 30% PVC 90度（本白,普通）水口料",
            "material_components": [
                {"material": "ABS PA-757", "ratio_percent": 70, "source_type": "virgin"},
                {"material": "PVC 90度（本白,普通）", "ratio_percent": 30, "source_type": "runner"},
            ],
        }
    )
    assert client.post("/api/injection", json=searchable_payload).status_code == 201
    add_board_problem("BP-BOARD-SEARCH-001", description="啤件表面缩痕")

    unrelated_payload = sample_order_payload("BP-BOARD-SEARCH-OTHER")
    unrelated_payload["order"]["doc_number"] = "DOC-OTHER"
    unrelated_payload["order"]["product_name"] = "无关产品"
    assert client.post("/api/injection", json=unrelated_payload).status_code == 201

    keyword = "ｗｇ０２６ ｊｐ５６７８ pvc 水口料 缩痕"
    page_response = client.get(
        "/api/injection/board/page",
        params={
            "factory_id": "huaxing",
            "status": "待审核",
            "q": keyword,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["total"] == 1
    assert [row["order"]["id"] for row in page["rows"]] == ["BP-BOARD-SEARCH-001"]

    summary_response = client.get(
        "/api/injection/board/summary",
        params={"factory_id": "huaxing", "q": keyword},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total"] == 1
    assert summary["status_counts"]["待审核"] == 1
    assert summary["unresolved_problem_count"] == 1

    single_material_response = client.get(
        "/api/injection/board/page",
        params={
            "factory_id": "huaxing",
            "status": "待审核",
            "q": "docother 原料 virgin 100",
        },
    )
    assert single_material_response.status_code == 200
    assert [row["order"]["id"] for row in single_material_response.json()["rows"]] == [
        "BP-BOARD-SEARCH-OTHER"
    ]


def test_engineering_board_queries_are_factory_isolated_and_keep_cross_factory_cost_redaction(client):
    login_as(client, "admin")
    huaxing_payload = sample_order_payload("BP-BOARD-FACTORY-HX")
    huadeng_payload = sample_order_payload("BP-BOARD-FACTORY-HD")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    huadeng_payload["items"][0]["actual_weight_kg"] = 2.2
    huadeng_payload["items"][0]["actual_amount_hkd"] = 88.5
    huadeng_payload["items"][0]["injection_cost"] = 120
    assert client.post("/api/injection", json=huaxing_payload).status_code == 201
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201

    huaxing_summary = client.get(
        "/api/injection/board/summary",
        params={"factory_id": "huaxing"},
    )
    huadeng_summary = client.get(
        "/api/injection/board/summary",
        params={"factory_id": "huadeng"},
    )
    assert huaxing_summary.status_code == 200
    assert huadeng_summary.status_code == 200
    assert huaxing_summary.json()["total"] == 1
    assert huadeng_summary.json()["total"] == 1

    grant_permission_override(
        "engineer",
        "molding_sample:cross_factory_read",
        factory_id="*",
        department="*",
    )
    login_as(client, "engineer")
    cross_factory_page = client.get(
        "/api/injection/board/page",
        params={"factory_id": "huadeng", "status": "待审核"},
    )
    assert cross_factory_page.status_code == 200
    rows = cross_factory_page.json()["rows"]
    assert [row["order"]["id"] for row in rows] == ["BP-BOARD-FACTORY-HD"]
    assert rows[0]["read_source"] == "cross"
    assert rows[0]["can_view_cost"] is False
    assert rows[0]["items"][0]["actual_weight_kg"] == 2.2
    assert rows[0]["items"][0]["actual_amount_hkd"] is None
    assert rows[0]["items"][0]["injection_cost"] is None


def test_same_factory_shared_departments_can_read_molding_samples(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-SHARED-LOCAL-READ-001"),
    ).status_code == 201

    for username in ("engineer", "supervisor", "manager", "warehouse_keeper", "molding_clerk"):
        login_as(client, username)
        response = client.get("/api/injection/BP-SHARED-LOCAL-READ-001")
        assert response.status_code == 200, username
        assert response.json()["read_source"] == "local"
        assert response.json()["can_view_cost"] is True

    login_as(client, "qa_inspector")
    qa_response = client.get("/api/injection/BP-SHARED-LOCAL-READ-001")
    assert qa_response.status_code == 403


def test_production_read_keeps_local_cost_view_while_foreign_factory_is_default_read_only(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    huaxing_payload = sample_order_payload("BP-PRODUCTION-READ-HX-001")
    huadeng_payload = sample_order_payload("BP-PRODUCTION-READ-HD-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=huaxing_payload).status_code == 201
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201
    for order_id in ("BP-PRODUCTION-READ-HX-001", "BP-PRODUCTION-READ-HD-001"):
        approved_response = client.patch(
            f"/api/injection/{order_id}/status",
            json={"action": "主管通过"},
        )
        assert approved_response.status_code == 200
        assert approved_response.json()["order"]["status"] == "待生产"

    grant_permission_override(
        "qa_inspector",
        "molding_sample:production_read",
        factory_id="huaxing",
        department="molding",
    )
    grant_permission_override(
        "qa_inspector",
        "molding_sample:production_read",
        factory_id="huadeng",
        department="molding",
    )
    login_as(client, "qa_inspector")

    local_response = client.get("/api/injection/BP-PRODUCTION-READ-HX-001")
    assert local_response.status_code == 200
    assert local_response.json()["read_source"] == "local"
    foreign_response = client.get("/api/injection/BP-PRODUCTION-READ-HD-001")
    assert foreign_response.status_code == 200
    assert foreign_response.json()["read_source"] == "cross"
    assert foreign_response.json()["can_view_cost"] is False

    list_response = client.get("/api/injection")
    assert list_response.status_code == 200
    assert {row["order"]["id"] for row in list_response.json()} == {
        "BP-PRODUCTION-READ-HX-001",
        "BP-PRODUCTION-READ-HD-001",
    }

    # A fixed molding position must not narrow an independent custom/override
    # production_read source on the same account.
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    with db_module.SessionLocal() as db:
        db.add(
            auth_models.AuthUserRole(
                id="user-qa-inspector:position_molding_clerk:huaxing:production",
                user_id="user-qa-inspector",
                role_id="position_molding_clerk",
                factory_id="huaxing",
                department="production",
            )
        )
        db.commit()

    login_as(client, "qa_inspector")
    assert client.get("/api/injection/BP-PRODUCTION-READ-HX-001").status_code == 200
    assert client.get("/api/injection/BP-PRODUCTION-READ-HD-001").status_code == 200


def test_manager_keeps_existing_draft_edit_and_delete_permissions(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-MANAGER-DRAFT-WRITE-001"),
    ).status_code == 201

    login_as(client, "manager")
    edited_payload = sample_order_payload("BP-MANAGER-DRAFT-WRITE-001")
    edited_payload["order"]["product_name"] = "经理修正草稿"
    edit_response = client.put(
        "/api/injection/BP-MANAGER-DRAFT-WRITE-001",
        json=edited_payload,
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["order"]["product_name"] == "经理修正草稿"

    assert client.delete("/api/injection/BP-MANAGER-DRAFT-WRITE-001").status_code == 204


def test_engineer_can_only_edit_and_delete_orders_they_created(enforce_client):
    client = enforce_client
    login_as(client, "engineer")
    payload = sample_order_payload("BP-ENGINEER-OWNER-001")
    payload["order"]["eng_name"] = "华兴工程同事"
    assert client.post("/api/injection", json=payload).status_code == 201

    login_as(client, "engineer_peer")
    peer_edit_payload = sample_order_payload("BP-ENGINEER-OWNER-001")
    peer_edit_payload["order"]["eng_name"] = "华兴工程同事"
    peer_edit_payload["order"]["product_name"] = "非开单工程师误改"
    peer_edit_response = client.put(
        "/api/injection/BP-ENGINEER-OWNER-001",
        json=peer_edit_payload,
    )
    assert peer_edit_response.status_code == 403
    assert "本人创建" in peer_edit_response.json()["detail"]

    peer_delete_response = client.delete("/api/injection/BP-ENGINEER-OWNER-001")
    assert peer_delete_response.status_code == 403
    assert "本人创建" in peer_delete_response.json()["detail"]

    login_as(client, "engineer")
    owner_edit_payload = sample_order_payload("BP-ENGINEER-OWNER-001")
    owner_edit_payload["order"]["product_name"] = "开单工程师修正"
    owner_edit_response = client.put(
        "/api/injection/BP-ENGINEER-OWNER-001",
        json=owner_edit_payload,
    )
    assert owner_edit_response.status_code == 200
    assert owner_edit_response.json()["order"]["product_name"] == "开单工程师修正"
    assert client.delete("/api/injection/BP-ENGINEER-OWNER-001").status_code == 204


@pytest.mark.parametrize(
    ("status", "suffix"),
    [
        ("待审核", "pending"),
        ("待生产", "waiting-production"),
        ("生产中", "producing"),
        ("已完成", "completed"),
        ("已驳回", "rejected"),
        ("已撤回", "withdrawn"),
    ],
)
def test_opening_engineer_can_delete_order_in_business_allowed_statuses(enforce_client, status, suffix):
    client = enforce_client
    order_id = f"BP-OWNER-DELETE-{suffix.upper()}"
    login_as(client, "engineer")
    assert client.post("/api/injection", json=sample_order_payload(order_id)).status_code == 201
    set_board_order_state(order_id, status=status)

    delete_response = client.delete(f"/api/injection/{order_id}")

    assert delete_response.status_code == 204, delete_response.text


@pytest.mark.parametrize(
    ("status", "suffix"),
    [
        ("待审核", "pending"),
        ("待生产", "waiting-production"),
        ("生产中", "producing"),
        ("已完成", "completed"),
        ("已驳回", "rejected"),
        ("已撤回", "withdrawn"),
    ],
)
def test_engineering_supervisor_can_delete_other_engineers_order_in_business_allowed_statuses(
    enforce_client,
    status,
    suffix,
):
    client = enforce_client
    order_id = f"BP-SUPERVISOR-DELETE-{suffix.upper()}"
    login_as(client, "engineer")
    assert client.post("/api/injection", json=sample_order_payload(order_id)).status_code == 201
    set_board_order_state(order_id, status=status)

    login_as(client, "supervisor")
    delete_response = client.delete(f"/api/injection/{order_id}")

    assert delete_response.status_code == 204, delete_response.text


def test_waiting_manager_review_order_remains_admin_only_for_delete(enforce_client):
    client = enforce_client
    order_id = "BP-WAITING-MANAGER-DELETE-001"
    login_as(client, "engineer")
    assert client.post("/api/injection", json=sample_order_payload(order_id)).status_code == 201
    set_board_order_state(order_id, status="待经理审核")

    owner_response = client.delete(f"/api/injection/{order_id}")
    assert owner_response.status_code == 403
    assert "仅管理员" in owner_response.json()["detail"]

    login_as(client, "supervisor")
    supervisor_response = client.delete(f"/api/injection/{order_id}")
    assert supervisor_response.status_code == 403
    assert "仅管理员" in supervisor_response.json()["detail"]

    login_as(client, "admin")
    assert client.delete(f"/api/injection/{order_id}").status_code == 204


def test_molding_clerk_cannot_edit_or_delete_engineering_draft(enforce_client):
    client = enforce_client
    login_as(client, "engineer")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-MOLDING-DRAFT-BLOCK-001"),
    ).status_code == 201

    login_as(client, "molding_clerk")
    edit_payload = sample_order_payload("BP-MOLDING-DRAFT-BLOCK-001")
    edit_payload["order"]["product_name"] = "啤机部误改"
    assert client.put(
        "/api/injection/BP-MOLDING-DRAFT-BLOCK-001",
        json=edit_payload,
    ).status_code == 403
    assert client.delete("/api/injection/BP-MOLDING-DRAFT-BLOCK-001").status_code == 403

    detail_response = client.get("/api/injection/BP-MOLDING-DRAFT-BLOCK-001")
    assert detail_response.status_code == 200
    assert detail_response.json()["order"]["product_name"] == "链条枪"


def test_cross_factory_read_is_read_only_and_hides_costs_until_separately_allowed(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    huadeng_payload = sample_order_payload("BP-CROSS-FACTORY-READ-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-CROSS-FACTORY-READ-001")
        item = db.get(molding_models.MoldingSampleItem, "BP-CROSS-FACTORY-READ-001-001")
        order.status = "已完成"
        order.completed_date = "2026-07-12"
        item.actual_weight_kg = 2.2
        item.actual_amount_hkd = 26.4
        item.actual_material_cost_components = [{
            "material": "HIPS 425",
            "source_type": "virgin",
            "ratio_percent": 100,
            "weight_kg": 2.2,
            "unit_price": 5.5,
            "amount_hkd": 26.4,
        }]
        item.injection_cost = 80
        item.injection_cost_hkd = 86.4
        item.exchange_rate_at_save = 1.08
        db.commit()

    grant_permission_override(
        "engineer",
        "molding_sample:cross_factory_read",
        factory_id="*",
        department="*",
    )
    login_as(client, "engineer")

    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    with db_module.SessionLocal() as db:
        role_bindings_before = [
            (binding.role_id, binding.factory_id, binding.department)
            for binding in db.query(auth_models.AuthUserRole)
            .filter_by(user_id="user-engineer")
            .order_by(auth_models.AuthUserRole.id)
        ]
        overrides_before = [
            (override.permission_id, override.effect, override.factory_id, override.department)
            for override in db.query(auth_models.AuthUserPermissionOverride)
            .filter_by(user_id="user-engineer")
            .order_by(auth_models.AuthUserPermissionOverride.id)
        ]

    detail_response = client.get("/api/injection/BP-CROSS-FACTORY-READ-001")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["read_source"] == "cross"
    assert detail["can_view_cost"] is False
    assert detail["items"][0]["actual_weight_kg"] == 2.2
    assert detail["items"][0]["actual_amount_hkd"] is None
    assert detail["items"][0]["actual_material_cost_components"] == []
    assert detail["items"][0]["injection_cost"] is None
    assert detail["items"][0]["injection_cost_hkd"] is None
    assert detail["items"][0]["exchange_rate_at_save"] is None

    listed = client.get("/api/injection", params={"factory_id": "huadeng"})
    assert listed.status_code == 200
    assert listed.json()[0]["read_source"] == "cross"
    assert listed.json()[0]["items"][0]["actual_amount_hkd"] is None

    assert client.get(
        "/api/injection/BP-CROSS-FACTORY-READ-001/export-excel"
    ).status_code == 403
    assert client.get(
        "/api/injection/export-excel",
        params=[("order_ids", "BP-CROSS-FACTORY-READ-001")],
    ).status_code == 403
    assert client.get(
        "/api/material-prices",
        params={"factory_id": "huadeng"},
    ).status_code == 403
    assert client.get(
        "/api/injection-total-costs",
        params={"factory_id": "huadeng"},
    ).status_code == 403
    unscoped_totals = client.get("/api/injection-total-costs")
    assert unscoped_totals.status_code == 200
    assert "BP-CROSS-FACTORY-READ-001" not in {
        row["order_id"] for row in unscoped_totals.json()
    }

    edited_payload = sample_order_payload("BP-CROSS-FACTORY-READ-001")
    edited_payload["order"]["factory_id"] = "huadeng"
    edited_payload["order"]["product_name"] = "跨厂不可修改"
    assert client.put(
        "/api/injection/BP-CROSS-FACTORY-READ-001",
        json=edited_payload,
    ).status_code == 403

    with db_module.SessionLocal() as db:
        assert [
            (binding.role_id, binding.factory_id, binding.department)
            for binding in db.query(auth_models.AuthUserRole)
            .filter_by(user_id="user-engineer")
            .order_by(auth_models.AuthUserRole.id)
        ] == role_bindings_before
        assert [
            (override.permission_id, override.effect, override.factory_id, override.department)
            for override in db.query(auth_models.AuthUserPermissionOverride)
            .filter_by(user_id="user-engineer")
            .order_by(auth_models.AuthUserPermissionOverride.id)
        ] == overrides_before

    grant_permission_override(
        "engineer",
        "molding_sample:cross_factory_cost_read",
        factory_id="*",
        department="*",
    )
    login_as(client, "engineer")

    cost_detail_response = client.get("/api/injection/BP-CROSS-FACTORY-READ-001")
    assert cost_detail_response.status_code == 200
    cost_detail = cost_detail_response.json()
    assert cost_detail["read_source"] == "cross"
    assert cost_detail["can_view_cost"] is True
    assert cost_detail["items"][0]["actual_amount_hkd"] == 26.4
    assert cost_detail["items"][0]["actual_material_cost_components"][0]["unit_price"] == 5.5
    assert cost_detail["items"][0]["injection_cost"] == 80
    assert cost_detail["items"][0]["injection_cost_hkd"] == 86.4
    assert cost_detail["items"][0]["exchange_rate_at_save"] == 1.08

    assert client.get(
        "/api/material-prices",
        params={"factory_id": "huadeng"},
    ).status_code == 200
    total_cost_response = client.get(
        "/api/injection-total-costs",
        params={"factory_id": "huadeng"},
    )
    assert total_cost_response.status_code == 200
    assert [row["order_id"] for row in total_cost_response.json()] == ["BP-CROSS-FACTORY-READ-001"]
    assert "BP-CROSS-FACTORY-READ-001" in {
        row["order_id"] for row in client.get("/api/injection-total-costs").json()
    }

    assert client.get(
        "/api/injection/BP-CROSS-FACTORY-READ-001/export-excel"
    ).status_code == 403


def test_cross_factory_read_is_denied_without_an_explicit_grant(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    payload = sample_order_payload("BP-CROSS-READ-DENY-001")
    payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=payload).status_code == 201

    login_as(client, "qa_inspector")

    assert client.get("/api/injection/BP-CROSS-READ-DENY-001").status_code == 403
    assert client.get("/api/injection", params={"factory_id": "huadeng"}).status_code == 403


def test_system_position_scope_modes_control_cross_factory_read_and_operate(position_scope_client):
    client = position_scope_client
    login_as(client, "admin")
    foreign_order = sample_order_payload("BP-POSITION-SCOPE-FOREIGN-001")
    foreign_order["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=foreign_order).status_code == 201

    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        now = auth_service.now_text()
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id="user-position-scope",
                username="position_scope",
                display_name="跨厂职位测试",
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserRole(
                id="user-position-scope:position_engineering_engineer:huaxing:sales-business",
                user_id="user-position-scope",
                role_id="position_engineering_engineer",
                factory_id="huaxing",
                department="sales-business",
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id="user-position-scope",
                primary_factory_id="huaxing",
                primary_department="sales-business",
                position="业务技术员",
                phone="",
                email="",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserAuthorizationRevision(
                user_id="user-position-scope",
                revision=1,
                updated_at=now,
            )
        )
        metadata = db.get(auth_models.AuthRoleMetadata, "position_engineering_engineer")
        metadata.scope_mode = "cross_factory_read"
        db.commit()

    profile = login_as(client, "position_scope")
    position_grant = next(
        item for item in profile["grants"]
        if item["role_id"] == "position_engineering_engineer"
    )
    assert position_grant["factory_id"] == "huaxing"
    assert position_grant["scope_mode"] == "cross_factory_read"
    assert position_grant["unrestricted_department"] is True
    assert "molding_sample:read" in position_grant["read_permission_codes"]
    assert "*" in profile["factory_scopes"]

    foreign_detail = client.get("/api/injection/BP-POSITION-SCOPE-FOREIGN-001")
    assert foreign_detail.status_code == 200
    assert foreign_detail.json()["read_source"] == "cross"

    blocked_create = sample_order_payload("BP-POSITION-SCOPE-READ-BLOCK-001")
    blocked_create["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=blocked_create).status_code == 403

    # Department labels no longer constrain a built-in position's configured
    # functions inside its home factory.
    local_create = sample_order_payload("BP-POSITION-SCOPE-LOCAL-001")
    assert client.post("/api/injection", json=local_create).status_code == 201

    with db_module.SessionLocal() as db:
        metadata = db.get(auth_models.AuthRoleMetadata, "position_engineering_engineer")
        metadata.scope_mode = "cross_factory_operate"
        revision = db.get(auth_models.AuthUserAuthorizationRevision, "user-position-scope")
        revision.revision += 1
        revision.updated_at = auth_service.now_text()
        db.commit()

    login_as(client, "position_scope")
    operated_detail = client.get("/api/injection/BP-POSITION-SCOPE-FOREIGN-001")
    assert operated_detail.status_code == 200
    assert operated_detail.json()["read_source"] == "cross_operate"

    allowed_create = sample_order_payload("BP-POSITION-SCOPE-OPERATE-001")
    allowed_create["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=allowed_create).status_code == 201
    assert client.get(
        "/api/injection/BP-POSITION-SCOPE-FOREIGN-001/export-excel"
    ).status_code == 200


def test_fixed_non_molding_positions_get_all_factory_task_read_without_task_writes(
    position_scope_client,
):
    client = position_scope_client
    create_fixed_position_test_user(
        "fixed_production_clerk_readonly",
        "position_production_clerk",
        "production",
    )
    create_fixed_position_test_user(
        "fixed_qa_clerk_task_observer",
        "position_qa_clerk",
        "qa",
    )

    login_as(client, "admin")
    for order_id, factory_id in (
        ("BP-FIXED-READONLY-HOME", "huaxing"),
        ("BP-FIXED-READONLY-FOREIGN", "huadeng"),
    ):
        payload = sample_order_payload(order_id)
        payload["order"]["factory_id"] = factory_id
        assert client.post("/api/injection", json=payload).status_code == 201
        approved = client.patch(
            f"/api/injection/{order_id}/status",
            json={"action": "主管通过"},
        )
        assert approved.status_code == 200
        assert approved.json()["order"]["status"] == "待生产"

    foreign_review_payload = sample_order_payload("BP-FIXED-READONLY-FOREIGN-REVIEW")
    foreign_review_payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=foreign_review_payload).status_code == 201
    production_problem = client.post(
        "/api/problems",
        json={
            "order_id": "BP-FIXED-READONLY-FOREIGN",
            "description": "正式生产任务问题可只读查看",
        },
    )
    assert production_problem.status_code == 201
    add_board_problem(
        "BP-FIXED-READONLY-FOREIGN-REVIEW",
        suffix="readonly-hidden",
        description="非生产阶段问题不得泄露",
    )

    home_notification = next(
        notification
        for notification in client.get(
            "/api/molding-sample-notifications",
            params={
                "target_module": "production_molding_sample_task",
                "order_id": "BP-FIXED-READONLY-HOME",
            },
        ).json()
        if notification["order_id"] == "BP-FIXED-READONLY-HOME"
    )

    production_profile = login_fixed_position_test_user(
        client,
        "fixed_production_clerk_readonly",
    )
    production_grant = next(
        grant
        for grant in production_profile["grants"]
        if grant["role_id"] == "position_production_clerk"
    )
    assert "molding_sample:production_read" in production_grant["permissions"]
    assert {
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
    }.isdisjoint(production_grant["permissions"])

    foreign_tasks = client.get(
        "/api/injection",
        params={"factory_id": "huadeng"},
    )
    assert foreign_tasks.status_code == 200
    foreign_task = next(
        row
        for row in foreign_tasks.json()
        if row["order"]["id"] == "BP-FIXED-READONLY-FOREIGN"
    )
    assert foreign_task["read_source"] == "cross"
    assert foreign_task["can_view_cost"] is False
    assert {
        notification["target_module"]
        for notification in foreign_task["notifications"]
    } == {"production_molding_sample_task"}
    assert "BP-FIXED-READONLY-FOREIGN-REVIEW" not in {
        row["order"]["id"] for row in foreign_tasks.json()
    }
    assert client.get(
        "/api/injection/BP-FIXED-READONLY-FOREIGN-REVIEW"
    ).status_code == 403

    assert client.patch(
        "/api/injection/BP-FIXED-READONLY-HOME/status",
        json={"action": "开始处理"},
    ).status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-READONLY-HOME/items",
        json={
            "items": [
                {
                    "id": "BP-FIXED-READONLY-HOME-001",
                    "actual_weight_kg": 2.4,
                }
            ]
        },
    ).status_code == 403
    assert client.put(
        "/api/injection/BP-FIXED-READONLY-HOME/trial-reports/"
        "BP-FIXED-READONLY-HOME-001",
        json={"data": {"trial_summary": "只读职位不得保存"}},
    ).status_code == 403
    assert client.post(
        "/api/problems",
        json={
            "order_id": "BP-FIXED-READONLY-HOME",
            "description": "只读职位不得上报",
        },
    ).status_code == 403
    assert client.patch(
        f"/api/molding-sample-notifications/{home_notification['id']}",
        json={"status": "已读"},
    ).status_code == 403

    qa_profile = login_fixed_position_test_user(
        client,
        "fixed_qa_clerk_task_observer",
    )
    qa_grant = next(
        grant
        for grant in qa_profile["grants"]
        if grant["role_id"] == "position_qa_clerk"
    )
    assert qa_grant["scope_mode"] == "own_factory"
    assert "molding_sample:production_read" in qa_grant["permissions"]
    qa_foreign_detail = client.get("/api/injection/BP-FIXED-READONLY-FOREIGN")
    assert qa_foreign_detail.status_code == 200
    assert qa_foreign_detail.json()["read_source"] == "cross"
    assert {
        notification["target_module"]
        for notification in qa_foreign_detail.json()["notifications"]
    } == {"production_molding_sample_task"}
    qa_problems = client.get("/api/problems")
    assert qa_problems.status_code == 200
    assert production_problem.json()["id"] in {
        problem["id"] for problem in qa_problems.json()
    }
    assert "BP-FIXED-READONLY-FOREIGN-REVIEW-problem-readonly-hidden" not in {
        problem["id"] for problem in qa_problems.json()
    }
    assert client.get(
        "/api/raw-materials",
        params={"factory_id": "huadeng"},
    ).status_code == 403
    assert client.get("/api/material-prices").status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-READONLY-FOREIGN/status",
        json={"action": "开始处理"},
    ).status_code == 403


def test_fixed_engineering_and_molding_positions_enforce_workflow_and_bell_boundaries(
    position_scope_client,
):
    client = position_scope_client
    fixed_users = (
        ("fixed_engineer", "position_engineering_engineer", "engineering"),
        (
            "fixed_engineering_supervisor",
            "position_engineering_supervisor",
            "engineering",
        ),
        ("fixed_engineering_manager", "position_engineering_manager", "engineering"),
        ("fixed_molding_clerk", "position_molding_clerk", "production"),
        ("fixed_molding_supervisor", "position_molding_supervisor", "production"),
        ("fixed_molding_manager", "position_molding_manager", "production"),
    )
    for username, role_id, department in fixed_users:
        create_fixed_position_test_user(username, role_id, department)

    review_orders = (
        ("BP-FIXED-ENGINEER-HOME", "huaxing"),
        ("BP-FIXED-ENGINEER-FOREIGN", "huadeng"),
        ("BP-FIXED-SUPERVISOR-HOME", "huaxing"),
        ("BP-FIXED-SUPERVISOR-FOREIGN", "huadeng"),
        ("BP-FIXED-MANAGER-HOME", "huaxing"),
        ("BP-FIXED-MANAGER-FOREIGN", "huadeng"),
    )
    production_orders = (
        ("BP-FIXED-CLERK-HOME", "huaxing"),
        ("BP-FIXED-CLERK-FOREIGN", "huadeng"),
        ("BP-FIXED-MOLDING-SUPERVISOR-FOREIGN", "huadeng"),
        ("BP-FIXED-MOLDING-MANAGER-FOREIGN", "huadeng"),
    )

    login_as(client, "admin")
    for order_id, factory_id in (*review_orders, *production_orders):
        payload = sample_order_payload(order_id)
        payload["order"]["factory_id"] = factory_id
        assert client.post("/api/injection", json=payload).status_code == 201
    for order_id, _ in production_orders:
        approved = client.patch(
            f"/api/injection/{order_id}/status",
            json={"action": "主管通过"},
        )
        assert approved.status_code == 200
        assert approved.json()["order"]["status"] == "待生产"
    production_notification_ids = {
        notification["order_id"]: notification["id"]
        for notification in client.get(
            "/api/molding-sample-notifications",
            params={"target_module": "production_molding_sample_task"},
        ).json()
    }

    engineer_profile = login_fixed_position_test_user(client, "fixed_engineer")
    engineer_grant = next(
        grant
        for grant in engineer_profile["grants"]
        if grant["role_id"] == "position_engineering_engineer"
    )
    assert engineer_grant["scope_mode"] == "cross_factory_read"
    assert client.get("/api/injection/BP-FIXED-ENGINEER-FOREIGN").status_code == 200
    local_create = sample_order_payload("BP-FIXED-ENGINEER-CREATE-HOME")
    assert client.post("/api/injection", json=local_create).status_code == 201
    foreign_create = sample_order_payload("BP-FIXED-ENGINEER-CREATE-FOREIGN")
    foreign_create["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=foreign_create).status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-ENGINEER-HOME/status",
        json={"action": "主管通过"},
    ).status_code == 403
    engineer_notifications = client.get(
        "/api/molding-sample-notifications",
        params={"target_module": "engineering_molding_sample"},
    )
    assert engineer_notifications.status_code == 200
    assert engineer_notifications.json()
    assert {
        notification["factory_id"] for notification in engineer_notifications.json()
    } == {"huaxing"}

    for username, home_order_id, foreign_order_id in (
        (
            "fixed_engineering_supervisor",
            "BP-FIXED-SUPERVISOR-HOME",
            "BP-FIXED-SUPERVISOR-FOREIGN",
        ),
        (
            "fixed_engineering_manager",
            "BP-FIXED-MANAGER-HOME",
            "BP-FIXED-MANAGER-FOREIGN",
        ),
    ):
        profile = login_fixed_position_test_user(client, username)
        grant = next(
            item
            for item in profile["grants"]
            if item["role_id"].startswith("position_engineering_")
        )
        assert grant["scope_mode"] == "cross_factory_read"
        assert "molding_sample:create" in grant["permissions"]
        assert "molding_sample:supervisor_review" in grant["permissions"]
        approved = client.patch(
            f"/api/injection/{home_order_id}/status",
            json={"action": "主管通过"},
        )
        assert approved.status_code == 200
        assert approved.json()["order"]["status"] == "待生产"
        assert client.patch(
            f"/api/injection/{foreign_order_id}/status",
            json={"action": "主管通过"},
        ).status_code == 403

    task_permissions = {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
    }
    clerk_profile = login_fixed_position_test_user(client, "fixed_molding_clerk")
    clerk_grant = next(
        grant
        for grant in clerk_profile["grants"]
        if grant["role_id"] == "position_molding_clerk"
    )
    assert clerk_grant["scope_mode"] == "cross_factory_read"
    assert set(clerk_grant["permissions"]) == task_permissions
    assert client.get("/api/injection/BP-FIXED-CLERK-FOREIGN").status_code == 200
    foreign_engineering_detail = client.get(
        "/api/injection/BP-FIXED-ENGINEER-FOREIGN"
    )
    assert foreign_engineering_detail.status_code == 200
    assert foreign_engineering_detail.json()["notifications"] == []
    foreign_tasks = client.get(
        "/api/injection",
        params={"factory_id": "huadeng"},
    )
    assert foreign_tasks.status_code == 200
    assert {
        "BP-FIXED-ENGINEER-FOREIGN",
        "BP-FIXED-CLERK-FOREIGN",
    } <= {
        row["order"]["id"] for row in foreign_tasks.json()
    }
    foreign_task_detail = client.get("/api/injection/BP-FIXED-CLERK-FOREIGN")
    assert foreign_task_detail.status_code == 200
    assert foreign_task_detail.json()["notifications"]
    assert {
        notification["target_module"]
        for notification in foreign_task_detail.json()["notifications"]
    } == {"production_molding_sample_task"}
    board_page = client.get(
        "/api/injection/board/page",
        params={"factory_id": "huadeng", "status": "待审核"},
    )
    assert board_page.status_code == 200
    assert "BP-FIXED-ENGINEER-FOREIGN" in {
        row["order"]["id"] for row in board_page.json()["rows"]
    }
    board_summary = client.get(
        "/api/injection/board/summary",
        params={"factory_id": "huadeng"},
    )
    assert board_summary.status_code == 200
    assert board_summary.json()["total"] >= 2
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-FIXED-CLERK-CREATE-BLOCKED"),
    ).status_code == 403
    clerk_edit_payload = sample_order_payload("BP-FIXED-ENGINEER-HOME")
    clerk_edit_payload["order"]["product_name"] = "啤机文员不得修改工程单"
    assert client.put(
        "/api/injection/BP-FIXED-ENGINEER-HOME",
        json=clerk_edit_payload,
    ).status_code == 403
    assert client.delete(
        "/api/injection/BP-FIXED-ENGINEER-HOME"
    ).status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-ENGINEER-HOME/status",
        json={"action": "主管通过"},
    ).status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-ENGINEER-HOME/status",
        json={"action": "主管驳回", "reason": "权限边界验证"},
    ).status_code == 403
    assert client.get(
        "/api/injection/export-excel",
        params={"order_ids": ["BP-FIXED-ENGINEER-HOME"]},
    ).status_code == 403
    assert client.patch(
        f"/api/molding-sample-notifications/"
        f"{production_notification_ids['BP-FIXED-CLERK-HOME']}",
        json={"status": "已读"},
    ).status_code == 200
    assert client.patch(
        f"/api/molding-sample-notifications/"
        f"{production_notification_ids['BP-FIXED-CLERK-FOREIGN']}",
        json={"status": "已读"},
    ).status_code == 403
    assert client.patch(
        "/api/injection/BP-FIXED-CLERK-HOME/status",
        json={"action": "开始处理"},
    ).status_code == 200
    handled_notification_response = client.patch(
        f"/api/molding-sample-notifications/"
        f"{production_notification_ids['BP-FIXED-CLERK-HOME']}",
        json={"status": "已读"},
    )
    assert handled_notification_response.status_code == 200
    assert handled_notification_response.json()["status"] == "已处理"
    assert client.patch(
        "/api/injection/BP-FIXED-CLERK-FOREIGN/status",
        json={"action": "开始处理"},
    ).status_code == 403
    clerk_notifications = client.get(
        "/api/molding-sample-notifications",
        params={"target_module": "production_molding_sample_task"},
    )
    assert clerk_notifications.status_code == 200
    assert clerk_notifications.json()
    assert {
        notification["factory_id"] for notification in clerk_notifications.json()
    } == {"huaxing"}
    assert client.get(
        "/api/molding-sample-notifications",
        params={"target_module": "engineering_molding_sample"},
    ).json() == []

    for username, role_id, foreign_order_id in (
        (
            "fixed_molding_supervisor",
            "position_molding_supervisor",
            "BP-FIXED-MOLDING-SUPERVISOR-FOREIGN",
        ),
        (
            "fixed_molding_manager",
            "position_molding_manager",
            "BP-FIXED-MOLDING-MANAGER-FOREIGN",
        ),
    ):
        profile = login_fixed_position_test_user(client, username)
        grant = next(item for item in profile["grants"] if item["role_id"] == role_id)
        assert grant["scope_mode"] == "cross_factory_operate"
        assert set(grant["permissions"]) == task_permissions
        assert client.get(
            "/api/injection/BP-FIXED-ENGINEER-FOREIGN"
        ).status_code == 200
        assert client.post(
            "/api/injection",
            json=sample_order_payload(f"BP-{role_id}-CREATE-BLOCKED"),
        ).status_code == 403
        blocked_edit_payload = sample_order_payload(
            "BP-FIXED-ENGINEER-FOREIGN"
        )
        blocked_edit_payload["order"]["factory_id"] = "huadeng"
        blocked_edit_payload["order"]["product_name"] = "啤机职位不得修改工程单"
        assert client.put(
            "/api/injection/BP-FIXED-ENGINEER-FOREIGN",
            json=blocked_edit_payload,
        ).status_code == 403
        assert client.delete(
            "/api/injection/BP-FIXED-ENGINEER-FOREIGN"
        ).status_code == 403
        assert client.patch(
            "/api/injection/BP-FIXED-ENGINEER-FOREIGN/status",
            json={"action": "主管通过"},
        ).status_code == 403
        assert client.patch(
            "/api/injection/BP-FIXED-ENGINEER-FOREIGN/status",
            json={"action": "主管驳回", "reason": "权限边界验证"},
        ).status_code == 403
        assert client.get(
            "/api/injection/export-excel",
            params={"order_ids": ["BP-FIXED-ENGINEER-FOREIGN"]},
        ).status_code == 403
        assert client.patch(
            f"/api/molding-sample-notifications/"
            f"{production_notification_ids[foreign_order_id]}",
            json={"status": "已读"},
        ).status_code == 200
        started = client.patch(
            f"/api/injection/{foreign_order_id}/status",
            json={"action": "开始处理"},
        )
        assert started.status_code == 200
        assert started.json()["order"]["status"] == "生产中"
        notifications = client.get(
            "/api/molding-sample-notifications",
            params={"target_module": "production_molding_sample_task"},
        )
        assert notifications.status_code == 200
        assert {
            notification["factory_id"] for notification in notifications.json()
        } == {"huaxing", "huadeng"}
        assert client.get(
            "/api/molding-sample-notifications",
            params={"target_module": "engineering_molding_sample"},
        ).json() == []


@pytest.mark.parametrize(
    ("authz_mode", "expects_legacy_notification"),
    (("legacy", True), ("shadow", True), ("enforce", False)),
)
def test_mixed_fixed_and_nonfixed_notification_scope_keeps_mode_aware_compatibility(
    monkeypatch,
    authz_mode,
    expects_legacy_notification,
):
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        assert client.post(
            "/api/injection",
            json=sample_order_payload("BP-NONFIXED-NOTIFICATION-COMPAT"),
        ).status_code == 201

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        with db_module.SessionLocal() as db:
            now = auth_service.now_text()
            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                auth_models.AuthUser(
                    id="user-nonfixed-notification-compat",
                    username="nonfixed_notification_compat",
                    display_name="旧角色通知兼容测试",
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                auth_models.AuthUserRole(
                    id="user-nonfixed-notification-compat:engineer:huaxing:qa",
                    user_id="user-nonfixed-notification-compat",
                    role_id="engineer",
                    factory_id="huaxing",
                    department="qa",
                )
            )
            db.add(
                auth_models.AuthUserRole(
                    id=(
                        "user-nonfixed-notification-compat:"
                        "position_molding_clerk:huaxing:production"
                    ),
                    user_id="user-nonfixed-notification-compat",
                    role_id="position_molding_clerk",
                    factory_id="huaxing",
                    department="production",
                )
            )
            db.add(
                auth_models.EmployeeProfile(
                    user_id="user-nonfixed-notification-compat",
                    primary_factory_id="huaxing",
                    primary_department="qa",
                    position="旧工程角色",
                    phone="",
                    email="",
                    confirmation_status="confirmed",
                    source_registration_request_id="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                auth_models.AuthUserAuthorizationRevision(
                    user_id="user-nonfixed-notification-compat",
                    revision=1,
                    updated_at=now,
                )
            )
            db.commit()

        login_as(client, "nonfixed_notification_compat")
        response = client.get(
            "/api/molding-sample-notifications",
            params={"target_module": "engineering_molding_sample"},
        )
        assert response.status_code == 200
        assert bool(response.json()) is expects_legacy_notification


def test_foreign_factory_regular_permissions_cannot_bypass_organization_gate(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    huadeng_payload = sample_order_payload("BP-FOREIGN-HARD-GATE-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201
    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-FOREIGN-HARD-GATE-001")
        order.status = "待生产"
        db.commit()

    for permission_code in (
        "molding_sample:read",
        "molding_sample:create",
        "molding_sample:edit_draft",
        "molding_sample:export",
    ):
        grant_permission_override(
            "engineer",
            permission_code,
            factory_id="huadeng",
            department="engineering",
        )

    login_as(client, "engineer")
    default_readable = client.get("/api/injection/BP-FOREIGN-HARD-GATE-001")
    assert default_readable.status_code == 200
    assert default_readable.json()["read_source"] == "cross"
    assert default_readable.json()["can_view_cost"] is False

    grant_permission_override(
        "engineer",
        "molding_sample:cross_factory_read",
        factory_id="huadeng",
        department="*",
    )
    grant_permission_override(
        "engineer",
        "system:user_manage",
        factory_id="huadeng",
        department="management",
    )
    login_as(client, "engineer")
    readable = client.get("/api/injection/BP-FOREIGN-HARD-GATE-001")
    assert readable.status_code == 200
    assert readable.json()["read_source"] == "cross"
    assert readable.json()["can_view_cost"] is False

    forbidden_create = sample_order_payload("BP-FOREIGN-HARD-GATE-CREATE")
    forbidden_create["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=forbidden_create).status_code == 403

    forbidden_edit = sample_order_payload("BP-FOREIGN-HARD-GATE-001")
    forbidden_edit["order"]["factory_id"] = "huadeng"
    forbidden_edit["order"]["product_name"] = "外厂越权修改"
    assert client.put(
        "/api/injection/BP-FOREIGN-HARD-GATE-001",
        json=forbidden_edit,
    ).status_code == 403
    assert client.get(
        "/api/injection/BP-FOREIGN-HARD-GATE-001/export-excel"
    ).status_code == 403
    assert client.delete("/api/injection/BP-FOREIGN-HARD-GATE-001").status_code == 403

    login_as(client, "admin")
    unchanged = client.get("/api/injection/BP-FOREIGN-HARD-GATE-001")
    assert unchanged.status_code == 200
    assert unchanged.json()["order"]["product_name"] == "链条枪"


def test_update_order_cannot_move_order_to_another_factory(enforce_client):
    client = enforce_client
    login_as(client, "engineer")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-FACTORY-IMMUTABLE-001"),
    ).status_code == 201

    moved_payload = sample_order_payload("BP-FACTORY-IMMUTABLE-001")
    moved_payload["order"]["factory_id"] = "huadeng"
    moved_payload["order"]["product_name"] = "不应提交的跨厂变更"
    response = client.put(
        "/api/injection/BP-FACTORY-IMMUTABLE-001",
        json=moved_payload,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "啤办单厂区归属不可通过编辑接口变更"

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        order = db.get(molding_models.MoldingSampleOrder, "BP-FACTORY-IMMUTABLE-001")
        assert order.factory_id == "huaxing"
        assert order.product_name == "链条枪"


def test_default_cross_read_does_not_activate_local_create_permission(enforce_client):
    client = enforce_client
    grant_permission_override(
        "qa_inspector",
        "molding_sample:create",
        factory_id="huaxing",
        department="engineering",
    )
    login_as(client, "qa_inspector")

    response = client.post(
        "/api/injection",
        json=sample_order_payload("BP-CREATE-WITHOUT-READ-001"),
    )
    assert response.status_code == 403

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        assert db.get(molding_models.MoldingSampleOrder, "BP-CREATE-WITHOUT-READ-001") is None


def test_scoped_permission_prevents_cross_factory_permission_reuse(client):
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    salt, password_hash = auth_service.make_password_hash("123456")
    with db_module.SessionLocal() as db:
        db.add(
            auth_models.AuthUser(
                id="user-cross-scope",
                username="cross_scope",
                display_name="跨厂区多角色用户",
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
                id="user-cross-scope:engineer:huaxing:engineering",
                user_id="user-cross-scope",
                role_id="engineer",
                factory_id="huaxing",
                department="engineering",
            )
        )
        db.add(
            auth_models.AuthUserRole(
                id="user-cross-scope:qa_inspector:huakang-a:qa",
                user_id="user-cross-scope",
                role_id="qa_inspector",
                factory_id="huakang-a",
                department="qa",
            )
        )
        db.commit()

    profile = login_as(client, "cross_scope")
    assert "molding_sample:create" in profile["permissions"]
    assert profile["factory_scopes"] == ["huakang-a", "huaxing"]

    login_as(client, "admin")
    huakang_payload = sample_order_payload("BP-CROSS-READ-BLOCKED")
    huakang_payload["order"]["factory_id"] = "huakang-a"
    assert client.post("/api/injection", json=huakang_payload).status_code == 201

    login_as(client, "cross_scope")
    scoped_list_response = client.get("/api/injection")
    assert scoped_list_response.status_code == 200
    assert all(
        record["order"]["id"] != "BP-CROSS-READ-BLOCKED"
        for record in scoped_list_response.json()
    )
    assert client.get("/api/injection/BP-CROSS-READ-BLOCKED").status_code == 403

    blocked_payload = sample_order_payload("BP-CROSS-BLOCKED")
    blocked_payload["order"]["factory_id"] = "huakang-a"
    blocked_response = client.post("/api/injection", json=blocked_payload)
    assert blocked_response.status_code == 403

    allowed_payload = sample_order_payload("BP-CROSS-ALLOWED")
    allowed_payload["order"]["factory_id"] = "huaxing"
    allowed_response = client.post("/api/injection", json=allowed_payload)
    assert allowed_response.status_code == 201


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
    waiting_fillback_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/items",
        json={
            "items": [
                {
                    "id": "BP-WORKFLOW-001-001",
                    "production_machine": "待生产机台-01",
                }
            ]
        },
    )
    assert waiting_fillback_response.status_code == 200
    assert waiting_fillback_response.json()["items"][0]["production_machine"] == "待生产机台-01"

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
    assert completed_response.json()["order"]["completed_date"] == TEST_BUSINESS_DATE

    completed_fillback_response = client.patch(
        "/api/injection/BP-WORKFLOW-001/items",
        json={
            "items": [
                {
                    "id": "BP-WORKFLOW-001-001",
                    "actual_weight_kg": 99,
                }
            ]
        },
    )
    assert completed_fillback_response.status_code == 403
    assert "待生产或生产中" in completed_fillback_response.json()["detail"]

    completed_detail_response = client.get("/api/injection/BP-WORKFLOW-001")
    assert completed_detail_response.status_code == 200
    assert completed_detail_response.json()["items"][0]["actual_weight_kg"] == 2


def test_molding_clerk_can_save_one_trial_report_per_mold_item(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-TRIAL-REPORT-001"))

    login_as(client, "supervisor")
    approved_response = client.patch(
        "/api/injection/BP-TRIAL-REPORT-001/status",
        json={"action": "主管通过"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["order"]["status"] == "待生产"

    login_as(client, "molding_clerk")
    report_response = client.put(
        "/api/injection/BP-TRIAL-REPORT-001/trial-reports/BP-TRIAL-REPORT-001-001",
        json={
            "data": {
                "mold_supplier": "华兴模具厂",
                "sample_category": "首板",
                "material_name": "HIPS 425",
                "material_shots": "30",
                "color": "深绿色",
                "color_code": "71139",
                "front_mold_water": "冻水",
                "rear_mold_water": "热水",
                "other_trial_requirement_note": "首件确认后再连续生产",
                "plastic_model": "HIPS 425",
                "machine_model": "海天",
                "machine_no": "A-08",
                "ejector_count": "3",
                "cushion_pressure": "30",
                "clamping_force": "75",
                "high_pressure": "80",
                "low_pressure": "55",
                "pressure_stage_1": "88",
                "barrel_temperature_head": "230",
                "molding_mode": "全自动",
                "mold_issues": ["困气"],
                "part_issues": ["缩水"],
                "trial_summary": "首件尺寸正常，需继续观察水口。",
                "trial_round": "第 1 次试模",
                "verdict": "合格试模",
                "tester_name": "华兴啤机部文员",
            }
        },
    )

    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["order_id"] == "BP-TRIAL-REPORT-001"
    assert report_payload["item_id"] == "BP-TRIAL-REPORT-001-001"
    assert report_payload["factory_id"] == "huaxing"
    assert report_payload["data"]["mold_supplier"] == "华兴模具厂"
    assert report_payload["data"]["sample_category"] == "首板"
    assert report_payload["data"]["other_trial_requirement_note"] == "首件确认后再连续生产"
    assert report_payload["data"]["ejector_count"] == "3"
    assert report_payload["data"]["clamping_force"] == "75"
    assert report_payload["data"]["mold_issues"] == ["困气"]
    assert report_payload["created_by"] == "华兴啤机部文员"

    updated_report_response = client.put(
        "/api/injection/BP-TRIAL-REPORT-001/trial-reports/BP-TRIAL-REPORT-001-001",
        json={"data": {"trial_summary": "复核后可以量产。", "verdict": "合格试模"}},
    )
    assert updated_report_response.status_code == 200
    assert updated_report_response.json()["id"] == report_payload["id"]
    assert updated_report_response.json()["data"]["trial_summary"] == "复核后可以量产。"

    detail_response = client.get("/api/injection/BP-TRIAL-REPORT-001")
    assert detail_response.status_code == 200
    trial_reports = detail_response.json()["trial_reports"]
    assert len(trial_reports) == 1
    assert trial_reports[0]["data"]["verdict"] == "合格试模"

    missing_item_response = client.put(
        "/api/injection/BP-TRIAL-REPORT-001/trial-reports/BP-TRIAL-REPORT-001-404",
        json={"data": {}},
    )
    assert missing_item_response.status_code == 404
    assert "模具明细不存在" in missing_item_response.json()["detail"]


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
    assert completed_response.json()["order"]["completed_date"] == TEST_BUSINESS_DATE

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


def test_molding_clerk_can_withdraw_started_production_to_pending(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-PROD-START-ROLLBACK-001"))

    login_as(client, "supervisor")
    approved_response = client.patch(
        "/api/injection/BP-PROD-START-ROLLBACK-001/status",
        json={"action": "主管通过"},
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["order"]["status"] == "待生产"

    login_as(client, "molding_clerk")
    start_response = client.patch(
        "/api/injection/BP-PROD-START-ROLLBACK-001/status",
        json={"action": "开始处理"},
    )
    assert start_response.status_code == 200
    assert start_response.json()["order"]["status"] == "生产中"

    rollback_response = client.patch(
        "/api/injection/BP-PROD-START-ROLLBACK-001/status",
        json={"action": "撤回开始生产", "reason": "啤机部误点开始生产，退回待生产"},
    )

    assert rollback_response.status_code == 200
    rollback_payload = rollback_response.json()
    assert rollback_payload["order"]["status"] == "待生产"
    assert rollback_payload["order"]["completed_date"] == ""
    assert rollback_payload["audit_logs"][0]["action"] == "撤回开始生产"
    assert rollback_payload["audit_logs"][0]["from_status"] == "生产中"
    assert rollback_payload["audit_logs"][0]["to_status"] == "待生产"
    assert rollback_payload["audit_logs"][0]["reason"] == "啤机部误点开始生产，退回待生产"


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
    assert payload["order"]["completed_date"] == TEST_BUSINESS_DATE
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


def test_problem_update_denial_does_not_commit_status_change(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    assert client.post(
        "/api/injection",
        json=sample_order_payload("BP-PROBLEM-ATOMIC-001"),
    ).status_code == 201

    db_module = importlib.import_module("app.db")
    molding_models = importlib.import_module("app.models.molding_sample")
    with db_module.SessionLocal() as db:
        db.add(
            molding_models.MoldingSampleProblem(
                id="problem-atomic-001",
                factory_id="huaxing",
                order_type="injection",
                order_id="BP-PROBLEM-ATOMIC-001",
                order_number="62437",
                description="不得被未授权处理",
                reported_by="测试",
                status="待处理",
                created_at="2026-07-12 12:00:00",
                resolved_at="",
            )
        )
        db.commit()

    grant_permission_override(
        "qa_inspector",
        "molding_sample:edit_draft",
        factory_id="huaxing",
        department="engineering",
    )
    login_as(client, "qa_inspector")
    response = client.patch(
        "/api/problems/problem-atomic-001",
        json={"status": "已解决"},
    )
    assert response.status_code == 403

    with db_module.SessionLocal() as db:
        problem = db.get(molding_models.MoldingSampleProblem, "problem-atomic-001")
        assert problem.status == "待处理"
        assert problem.resolved_at == ""


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
    assert edit_response.json()["items"][0]["mold_dimensions"] == "650 × 450 × 380 mm"
    assert edit_response.json()["items"][0]["mold_presence_status"] == "in_factory"

    delete_response = client.delete("/api/injection/BP-EDIT-001")
    assert delete_response.status_code == 204

    client.post("/api/injection", json=sample_order_payload("BP-LOCK-001"))
    login_as(client, "supervisor")
    client.patch("/api/injection/BP-LOCK-001/status", json={"action": "主管通过"})

    login_as(client, "engineer")
    locked_payload = sample_order_payload("BP-LOCK-001")
    locked_payload["order"]["product_name"] = "普通工程误改"
    assert client.put("/api/injection/BP-LOCK-001", json=locked_payload).status_code == 403

    login_as(client, "manager")
    manager_payload = sample_order_payload("BP-LOCK-001")
    manager_payload["order"]["product_name"] = "经理修正名称"
    manager_edit_response = client.put("/api/injection/BP-LOCK-001", json=manager_payload)
    assert manager_edit_response.status_code == 200
    assert manager_edit_response.json()["order"]["product_name"] == "经理修正名称"

    login_as(client, "engineer")
    assert client.delete("/api/injection/BP-LOCK-001").status_code == 204


def test_completed_order_header_edit_preserves_material_settlement_snapshot(client):
    login_as(client, "engineer")
    payload = sample_order_payload("BP-COMPLETE-EDIT-SNAPSHOT-001")
    payload["items"][0]["material_components"] = [
        {"material": "HIPS 425", "ratio_percent": 100, "source_type": "virgin"},
    ]
    assert client.post("/api/injection", json=payload).status_code == 201

    login_as(client, "supervisor")
    assert client.patch(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001/status",
        json={"action": "主管通过"},
    ).status_code == 200

    login_as(client, "molding_clerk")
    assert client.patch(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001/status",
        json={"action": "开始处理"},
    ).status_code == 200
    assert client.patch(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001/items",
        json={"items": [{"id": "BP-COMPLETE-EDIT-SNAPSHOT-001-001", "actual_weight_kg": 2}]},
    ).status_code == 200
    completed_response = client.patch(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001/status",
        json={"action": "标记完成", "today": "2026-07-15"},
    )
    assert completed_response.status_code == 200
    completed = completed_response.json()
    saved_snapshot = completed["items"][0]["actual_material_cost_components"]
    assert saved_snapshot

    login_as(client, "manager")
    edit_payload = {"order": completed["order"], "items": completed["items"]}
    edit_payload["order"]["product_name"] = "只修正单头名称"
    edited_response = client.put(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001",
        json=edit_payload,
    )
    assert edited_response.status_code == 200
    assert edited_response.json()["items"][0]["actual_material_cost_components"] == saved_snapshot

    changed_settlement_payload = {
        "order": edited_response.json()["order"],
        "items": edited_response.json()["items"],
    }
    changed_settlement_payload["items"][0]["actual_weight_kg"] = 3
    rejected_response = client.put(
        "/api/injection/BP-COMPLETE-EDIT-SNAPSHOT-001",
        json=changed_settlement_payload,
    )
    assert rejected_response.status_code == 400
    assert "先撤回完成" in rejected_response.json()["detail"]


def test_admin_can_delete_locked_molding_sample_order_when_manager_cannot(client):
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


def test_warehouse_read_endpoints_enforce_permissions_and_factory_scope(enforce_client):
    client = enforce_client
    login_as(client, "admin")
    huaxing_payload = sample_order_payload("BP-WAREHOUSE-READ-HX-001")
    huadeng_payload = sample_order_payload("BP-WAREHOUSE-READ-HD-001")
    huadeng_payload["order"]["factory_id"] = "huadeng"
    assert client.post("/api/injection", json=huaxing_payload).status_code == 201
    assert client.post("/api/injection", json=huadeng_payload).status_code == 201

    for order_id in ("BP-WAREHOUSE-READ-HX-001", "BP-WAREHOUSE-READ-HD-001"):
        approval = client.patch(
            f"/api/injection/{order_id}/status",
            json={"action": "主管通过"},
        )
        assert approval.status_code == 200
        response = client.post(
            "/api/requisitions",
            json={
                "date": "2026-07-12",
                "order_id": order_id,
                "material": "HIPS 425",
                "requested_weight_kg": 1.5,
                "applicant": "测试申请人",
                "notes": order_id,
            },
        )
        assert response.status_code == 201

    assert client.post(
        "/api/inventory-batches",
        json={
            "factory_id": "huaxing",
            "material": "HIPS 425",
            "batch_no": "HIPS-20260712-A",
            "location": "A-01",
            "initial_weight_kg": 10,
        },
    ).status_code == 201

    login_as(client, "qa_inspector")
    assert client.get("/api/requisitions").status_code == 403
    assert client.get("/api/inventory-batches").status_code == 403
    assert client.get("/api/inventory-movements").status_code == 403
    assert client.get("/api/material-prices").status_code == 403

    login_as(client, "warehouse_keeper")
    requisitions = client.get("/api/requisitions")
    assert requisitions.status_code == 200
    assert [item["order_id"] for item in requisitions.json()] == ["BP-WAREHOUSE-READ-HX-001"]
    assert client.get("/api/inventory-batches").status_code == 200
    assert client.get("/api/inventory-movements").status_code == 200


def test_export_and_import_molding_sample_excel_template(client):
    login_as(client, "engineer")
    source_payload = sample_order_payload("BP-XLSX-001")
    source_payload["items"][0].update(
        {
            "mold_dimensions": "650 × 450 × 380 mm",
            "machine_type": "160T",
            "mold_presence_status": "out_of_factory",
            "mold_return_time": "2026-07-18",
            "completion_time": "2026-07-22",
            "material_usage_type": "production",
        }
    )
    source_payload["items"].append(
        {
            **source_payload["items"][0],
            "id": "BP-XLSX-001-002",
            "sort_order": 2,
            "mold_id": "M-TRIAL-002",
            "mold_name": "客户试料模具",
            "material": "客户自带试料 X-01",
            "material_components": [
                {
                    "material": "客户自带试料 X-01",
                    "ratio_percent": 100,
                    "source_type": "virgin",
                }
            ],
            "material_usage_type": "trial",
        }
    )
    create_response = client.post("/api/injection", json=source_payload)
    assert create_response.status_code == 201

    export_response = client.get("/api/injection/BP-XLSX-001/export-excel")
    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"

    with ZipFile(BytesIO(export_response.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "工模尺寸" in sheet_xml
    assert "适配机型" in sheet_xml
    assert "模具是否在厂" in sheet_xml
    assert "模具回厂时间" in sheet_xml
    assert "用料用途" in sheet_xml
    assert sheet_xml.index("<t>原料</t>") < sheet_xml.index("<t>用料用途</t>") < sheet_xml.index("<t>颜色</t>")
    assert "正式生产" in sheet_xml
    assert "试料" in sheet_xml
    assert "客户自带试料 X-01" in sheet_xml
    assert "不在厂" in sheet_xml

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
    assert imported["items"][0]["mold_dimensions"] == "650 × 450 × 380 mm"
    assert imported["items"][0]["machine_type"] == "160T"
    assert imported["items"][0]["mold_presence_status"] == "out_of_factory"
    assert imported["items"][0]["mold_return_time"] == "2026-07-18"
    assert imported["items"][0]["completion_time"] == "2026-07-22"
    assert imported["items"][0]["material_usage_type"] == "production"
    assert imported["items"][1]["id"] == "BP-XLSX-002-002"
    assert imported["items"][1]["material_usage_type"] == "trial"
    assert imported["items"][1]["material_components"] == [
        {
            "material": "客户自带试料 X-01",
            "ratio_percent": 100.0,
            "source_type": "virgin",
        }
    ]


def test_download_engineering_import_template_matches_current_manual_fields(client):
    login_as(client, "engineer")

    response = client.get("/api/injection/import-excel-template", params={"factory_id": "huaxing"})

    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert 'filename="engineering-molding-sample-import-template.xlsx"' in response.headers["content-disposition"]

    with ZipFile(BytesIO(response.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        guide_xml = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")

    for current_manual_header in [
        "模具编号",
        "模具名称",
        "所需用料",
        "用料用途",
        "颜色",
        "PMS",
        "色粉",
        "啤/套",
        "啤数",
        "所需用料(kg)",
        "需办日期",
        "工模尺寸",
        "模具状态（是否在厂）",
        "备注",
    ]:
        assert current_manual_header in sheet_xml

    assert sheet_xml.index("<t>所需用料</t>") < sheet_xml.index("<t>用料用途</t>") < sheet_xml.index("<t>颜色</t>")
    assert "原料价格(HKD/磅)" not in sheet_xml
    assert "客模具编号" not in sheet_xml
    assert "模具是否在厂" not in sheet_xml
    assert "模具回厂时间" not in sheet_xml
    assert "适配机型" not in sheet_xml
    assert "毛重g" not in sheet_xml
    assert "预计料费HKD" not in sheet_xml
    assert '<autoFilter ref="A8:N8"/>' in sheet_xml
    assert '<dimension ref="A1:N38"/>' in sheet_xml
    assert '<row r="38">' in sheet_xml
    assert '<dataValidations count="2">' in sheet_xml
    assert 'sqref="D9:D38"' in sheet_xml
    assert '<formula1>"正式生产,试料"</formula1>' in sheet_xml
    assert 'sqref="M9:M38"' in sheet_xml
    assert '<formula1>"在厂,不在厂,待确认"</formula1>' in sheet_xml

    assert '<sheet name="啤办单" sheetId="1" r:id="rId1"/>' in workbook_xml
    assert '<sheet name="填写说明" sheetId="2" r:id="rId2"/>' in workbook_xml
    for guide_text in [
        "字段映射",
        "80%ABS PA-757 + 20%ABS PA-757水口料",
        "80%ABS PA-757 + 20%水口料",
        "80%ABS PA-757 + 20%PVC 90度（本白,普通）水口料",
        "同一种原料",
        "不同原料",
        "正式生产的所需用料须填写原料数据库中的启用名称",
        "试料可自定义输入且不从原料数据库搜索",
        "试料用量保留，金额不计入物料结余",
        "原料价格、预计料费、实际用料和实际料费由系统维护",
    ]:
        assert guide_text in guide_xml


def test_parse_molding_sample_excel_accepts_current_engineering_headers():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    current_rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "ShuShuPaPa", "产品编号", "P50002008", "产品名称", "30寸黑武士"],
        ["开单日期", "2026/07/14", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "杨敬作", "落单人", "工程A"],
        ["注意事项", "首次打样"],
        [],
        [],
        [
            "模具编号", "模具名称", "所需用料", "用料用途", "颜色", "PMS", "色粉", "啤/套",
            "啤数", "所需用料(kg)", "需办日期", "工模尺寸", "模具状态（是否在厂）", "备注",
        ],
        [
            "P50002008-01-01", "30寸黑武士-头盔", "客户自带再生料 X-01", "试料", "黑色", "Black C", "黑种", "2",
            30, 15, "2026-07-22", "650 × 450 × 380 mm", "在厂", "第一次试模",
        ],
    ]

    parsed = excel_service.parse_order_excel(
        excel_service._build_workbook(excel_service._sheet_xml(current_rows, header_row_index=8))
    )

    assert parsed.order.order_number == "P50002008"
    assert parsed.order.product_name == "30寸黑武士"
    assert parsed.order.date == "2026-07-14"
    assert parsed.order.workshop == "工程部"
    assert parsed.order.reason == "首次打样"
    assert parsed.items[0].mold_id == "P50002008-01-01"
    assert parsed.items[0].mold_presence_status == "in_factory"
    assert parsed.items[0].material == "客户自带再生料 X-01"
    assert [component.model_dump() for component in parsed.items[0].material_components] == [
        {"material": "客户自带再生料 X-01", "ratio_percent": 100.0, "source_type": "virgin"}
    ]
    assert parsed.items[0].color == "黑色 / PMS Black C"
    assert parsed.items[0].required_material_kg == 15
    assert parsed.items[0].mold_return_time == ""
    assert parsed.items[0].completion_time == "2026-07-22"
    assert parsed.items[0].machine_type == ""
    assert parsed.items[0].gross_weight_g is None
    assert parsed.items[0].material_usage_type == "trial"


def test_parse_molding_sample_excel_leaves_ids_for_create_service_and_uses_business_date(monkeypatch):
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    import_time = datetime(2026, 7, 19, 0, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(excel_service, "business_now", lambda: import_time)
    current_rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "ShuShuPaPa", "产品编号", "P50002008", "产品名称", "日期缺省测试"],
        ["开单日期", "", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "杨敬作", "落单人", "工程A"],
        ["注意事项", "测试业务时区默认值"],
        [],
        [],
        [
            "模具编号", "模具名称", "所需用料", "颜色", "PMS", "色粉", "啤/套", "啤数",
            "所需用料(kg)", "需办日期", "工模尺寸", "模具状态（是否在厂）", "用料用途", "备注",
        ],
        [
            "P50002008-01-01", "日期缺省模具", "PP（AV161）", "黑色", "", "", "1", 1,
            1, "", "", "在厂", "试料", "",
        ],
    ]

    parsed = excel_service.parse_order_excel(
        excel_service._build_workbook(excel_service._sheet_xml(current_rows, header_row_index=8))
    )

    assert parsed.order.id == ""
    assert parsed.items[0].id == ""
    assert parsed.order.date == "2026-07-19"
    assert parsed.items[0].material == "PP（AV161）"
    assert parsed.items[0].material_usage_type == "trial"


def test_parse_molding_sample_excel_builds_and_canonicalizes_multi_material_components():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    current_rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "ShuShuPaPa", "产品编号", "P50002008", "产品名称", "多原料映射测试"],
        ["开单日期", "2026/07/15", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "杨敬作", "落单人", "工程A"],
        ["注意事项", "多原料测试"],
        [],
        [],
        [
            "模具编号", "模具名称", "所需用料", "用料用途", "颜色", "PMS", "色粉", "啤/套",
            "啤数", "所需用料(kg)", "需办日期", "工模尺寸", "模具状态（是否在厂）", "备注",
        ],
        [
            "M-MIX-001", "混料模具", "80%ABS PA-757 + 20%PVC 90度（本白,普通）水口料",
            "正式生产", "黑色", "Black C", "", "1", 10, 10, "2026-07-20", "207*789", "在厂", "",
        ],
        [
            "M-MIX-002", "同料水口模具", "80%ABS PA-757 + 20%水口料",
            "正式生产", "本白", "", "", "1", 10, 10, "2026-07-20", "207*789", "在厂", "",
        ],
        [
            "M-SINGLE-003", "加号单料模具", "PC+ABS",
            "正式生产", "本白", "", "", "1", 10, 10, "2026-07-20", "207*789", "在厂", "",
        ],
        [
            "M-MIX-004", "加号混料模具", "80%PC+ABS + 20%水口料",
            "正式生产", "本白", "", "", "1", 10, 10, "2026-07-20", "207*789", "在厂", "",
        ],
        [
            "M-SINGLE-005", "含百分号单料模具", "PA66+30%GF",
            "正式生产", "本白", "", "", "1", 10, 10, "2026-07-20", "207*789", "在厂", "",
        ],
    ]

    parsed = excel_service.parse_order_excel(
        excel_service._build_workbook(excel_service._sheet_xml(current_rows, header_row_index=8))
    )

    assert parsed.items[0].material == "80% ABS PA-757 + 20% PVC 90度（本白,普通） 水口料"
    assert [component.model_dump() for component in parsed.items[0].material_components] == [
        {"material": "ABS PA-757", "ratio_percent": 80.0, "source_type": "virgin"},
        {"material": "PVC 90度（本白,普通）", "ratio_percent": 20.0, "source_type": "runner"},
    ]
    assert parsed.items[1].material == "80% ABS PA-757 + 20% ABS PA-757 水口料"
    assert [component.model_dump() for component in parsed.items[1].material_components] == [
        {"material": "ABS PA-757", "ratio_percent": 80.0, "source_type": "virgin"},
        {"material": "ABS PA-757", "ratio_percent": 20.0, "source_type": "runner"},
    ]
    assert parsed.items[2].material == "PC+ABS"
    assert [component.model_dump() for component in parsed.items[2].material_components] == [
        {"material": "PC+ABS", "ratio_percent": 100.0, "source_type": "virgin"}
    ]
    assert parsed.items[3].material == "80% PC+ABS + 20% PC+ABS 水口料"
    assert [component.model_dump() for component in parsed.items[3].material_components] == [
        {"material": "PC+ABS", "ratio_percent": 80.0, "source_type": "virgin"},
        {"material": "PC+ABS", "ratio_percent": 20.0, "source_type": "runner"},
    ]
    assert parsed.items[4].material == "PA66+30%GF"
    assert [component.model_dump() for component in parsed.items[4].material_components] == [
        {"material": "PA66+30%GF", "ratio_percent": 100.0, "source_type": "virgin"}
    ]


def test_parse_molding_sample_excel_reports_invalid_engineering_material_row_number():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    current_rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "ShuShuPaPa", "产品编号", "P50002008", "产品名称", "多原料格式错误测试"],
        ["开单日期", "2026/07/15", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "杨敬作", "落单人", "工程A"],
        ["注意事项", ""],
        [],
        [],
        [
            "模具编号", "模具名称", "所需用料", "用料用途", "颜色", "PMS", "色粉", "啤/套",
            "啤数", "所需用料(kg)", "需办日期", "工模尺寸", "模具状态（是否在厂）", "备注",
        ],
        ["M-BAD-001", "错误混料", "80%ABS PA-757 + 错误段", "正式生产", "", "", "", "1", 10, 10, "", "", "在厂", ""],
    ]

    with pytest.raises(ValueError, match="Excel 第 9 行.*所需用料.*比例合计必须为 100%"):
        excel_service.parse_order_excel(
            excel_service._build_workbook(excel_service._sheet_xml(current_rows, header_row_index=8))
        )


def test_parse_molding_sample_excel_allows_arbitrary_trial_material_text():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    current_rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "Trial Client", "产品编号", "TRIAL-001", "产品名称", "自定义试料映射测试"],
        ["开单日期", "2026/07/21", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "杨敬作", "落单人", "工程A"],
        ["注意事项", ""],
        [],
        [],
        [
            "模具编号", "模具名称", "所需用料", "用料用途", "颜色", "PMS", "色粉", "啤/套",
            "啤数", "所需用料(kg)", "需办日期", "工模尺寸", "模具状态（是否在厂）", "备注",
        ],
        [
            "M-TRIAL-001", "试料模具", "80% 客户回收料 + 临时辅料", "试料", "本白", "", "", "1",
            10, 2.5, "2026-07-25", "207*789", "在厂", "客户提供的自由文本，不作为正式配比解析",
        ],
    ]

    parsed = excel_service.parse_order_excel(
        excel_service._build_workbook(excel_service._sheet_xml(current_rows, header_row_index=8))
    )

    assert parsed.items[0].material_usage_type == "trial"
    assert parsed.items[0].material == "80% 客户回收料 + 临时辅料"
    assert [component.model_dump() for component in parsed.items[0].material_components] == [
        {
            "material": "80% 客户回收料 + 临时辅料",
            "ratio_percent": 100.0,
            "source_type": "virgin",
        }
    ]


def test_excel_expected_material_amount_uses_component_prices():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    item = SimpleNamespace(
        required_material_kg=10,
        material="80%ABS + 20%PVC水口料",
        material_components=[
            {"material": "ABS", "ratio_percent": 80, "source_type": "virgin"},
            {"material": "PVC", "ratio_percent": 20, "source_type": "runner"},
        ],
    )
    prices = [
        SimpleNamespace(material="ABS", unit_price=8),
        SimpleNamespace(material="PVC", unit_price=5),
    ]

    assert excel_service._calculate_expected_amount_hkd(item, prices) == 163.15


def test_parse_molding_sample_excel_accepts_legacy_mold_metadata_headers():
    excel_service = importlib.import_module("app.services.molding_sample_excel")
    legacy_rows = [
        ["单据ID", "BP-XLSX-LEGACY-001"],
        ["工厂ID", "huaxing"],
        ["产品名称", "旧模板兼容测试"],
        ["日期", "2026-07-01"],
        ["模具编号", "模具名称", "机型", "模具是否在厂", "回模时间", "需办日期", "原料"],
        ["M-LEGACY-001", "旧模具", "160T", "在厂", "2026-07-18", "2026-07-22", "HIPS 425"],
    ]

    parsed = excel_service.parse_order_excel(
        excel_service._build_workbook(excel_service._sheet_xml(legacy_rows, header_row_index=5))
    )

    assert parsed.items[0].machine_type == "160T"
    assert parsed.items[0].mold_return_time == "2026-07-18"
    assert parsed.items[0].mold_presence_status == "in_factory"


def test_export_molding_sample_excel_template_has_report_styling(client):
    login_as(client, "engineer")
    client.post("/api/injection", json=sample_order_payload("BP-XLSX-STYLE-001"))

    export_response = client.get("/api/injection/BP-XLSX-STYLE-001/export-excel")
    assert export_response.status_code == 200

    detail_header_row = 5

    with ZipFile(BytesIO(export_response.content)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = workbook.read("xl/styles.xml").decode("utf-8")

    assert "啤办单 · 链条枪（BP-XLSX-STYLE-001） · 待审核" in sheet_xml
    assert "产品 / 客户" in sheet_xml
    assert "预计料费HKD" in sheet_xml
    assert "29.83" in sheet_xml
    assert "缺" in sheet_xml
    assert "原料小计" in sheet_xml
    assert "总计" in sheet_xml
    assert '<mergeCell ref="A1:Z1"/>' in sheet_xml
    assert '<mergeCell ref="F2:Z2"/>' in sheet_xml
    assert '<pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/>' in sheet_xml
    assert f'<autoFilter ref="A{detail_header_row}:Z{detail_header_row}"/>' in sheet_xml
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
    assert '<cellXfs count="13">' in styles_xml
    assert '<fgColor rgb="FF0F172A"/>' in styles_xml
    assert '<fgColor rgb="FFECFDF5"/>' in styles_xml
    assert '<fgColor rgb="FFFEF2F2"/>' in styles_xml
    assert '<fgColor rgb="FFFFFBEB"/>' in styles_xml
    assert '<fgColor rgb="FF0F766E"/>' in styles_xml
    assert '<sheetView workbookViewId="0">' in sheet_xml
    assert '<pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/>' in sheet_xml


def test_export_multiple_molding_sample_orders_as_one_excel_table(client):
    login_as(client, "engineer")
    first_order_payload = sample_order_payload("BP-XLSX-BATCH-001")
    first_order_payload["items"].append(
        {
            **first_order_payload["items"][0],
            "id": "BP-XLSX-BATCH-001-002",
            "sort_order": 2,
            "mold_id": "M-002",
            "mold_name": "装饰件",
            "material": "ABS 740",
        }
    )
    client.post("/api/injection", json=first_order_payload)
    client.post("/api/injection", json=sample_order_payload("BP-XLSX-BATCH-002"))

    export_response = client.get(
        "/api/injection/export-excel",
        params=[
            ("order_ids", "BP-XLSX-BATCH-001"),
            ("order_ids", "BP-XLSX-BATCH-002"),
        ],
    )

    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"
    assert 'filename="molding-sample-2-orders.xlsx"' in export_response.headers["content-disposition"]

    with ZipFile(BytesIO(export_response.content)) as workbook:
        worksheet_names = [name for name in workbook.namelist() if name.startswith("xl/worksheets/")]
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert worksheet_names == ["xl/worksheets/sheet1.xml"]
    assert "啤办单批量导出 · 2 张" in sheet_xml
    assert "单据ID" in sheet_xml
    assert "明细ID" in sheet_xml
    assert "BP-XLSX-BATCH-001" in sheet_xml
    assert "BP-XLSX-BATCH-001-001" in sheet_xml
    assert "BP-XLSX-BATCH-001-002" in sheet_xml
    assert "BP-XLSX-BATCH-002" in sheet_xml
    assert "BP-XLSX-BATCH-002-001" in sheet_xml
    assert sheet_xml.count("<t>BP-XLSX-BATCH-001</t>") == 1
    assert '<mergeCell ref="A3:A4"/>' in sheet_xml
    assert ' s="9"' in sheet_xml
    assert ' s="10"' in sheet_xml
    assert ' s="11"' in sheet_xml


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


def test_direct_excel_import_without_ids_uses_the_central_order_id_generator(client):
    login_as(client, "engineer")

    import_response = client.post(
        "/api/injection/import-excel",
        content=huaxing_engineering_template_workbook(),
        headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    assert import_response.status_code == 201, import_response.text
    imported = import_response.json()
    generated_order_id = imported["order"]["id"]
    assert re.fullmatch(r"BP-\d{14}-[0-9A-F]{12}", generated_order_id)
    assert [item["id"] for item in imported["items"]] == [
        f"{generated_order_id}-001",
        f"{generated_order_id}-002",
    ]
    assert {item["order_id"] for item in imported["items"]} == {generated_order_id}


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
    assert first_item["material"] == "100% PP（AV161）"
    assert first_item["material_components"] == [
        {"material": "PP（AV161）", "ratio_percent": 100.0, "source_type": "virgin"}
    ]
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


def cross_factory_order_payload(
    order_id: str,
    *,
    origin_factory_id: str,
    production_factory_id: str | None,
):
    payload = sample_order_payload(order_id)
    payload["order"].update(
        {
            "factory_id": origin_factory_id,
            "production_factory_id": production_factory_id,
            "supervisor": f"{origin_factory_id}工程主管",
            "eng_name": f"{origin_factory_id}工程师",
        }
    )
    return payload


def test_huakang_c_order_runs_in_huakang_a_without_leaking_engineering_stage(client):
    order_id = "BP-HKC-TO-HKA-001"
    login_as(client, "c_engineer")
    create_response = client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["order"]["factory_id"] == "huakang-c"
    assert created["order"]["production_factory_id"] == "huakang-a"
    assert created["order"]["production_assignment_version"] == 1
    assert created["dispatch_logs"][0]["origin_factory_id"] == "huakang-c"
    assert created["dispatch_logs"][0]["to_production_factory_id"] == "huakang-a"

    login_as(client, "a_molding_clerk")
    assert client.get(f"/api/injection/{order_id}").status_code == 403

    login_as(client, "c_supervisor")
    approve_response = client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "主管通过"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["order"]["status"] == "待生产"

    login_as(client, "a_molding_clerk")
    a_tasks = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-a"},
    )
    assert a_tasks.status_code == 200
    assert order_id in {row["order"]["id"] for row in a_tasks.json()}
    a_detail = client.get(f"/api/injection/{order_id}")
    assert a_detail.status_code == 200
    assert a_detail.json()["order"]["factory_id"] == "huakang-c"
    assert a_detail.json()["order"]["production_factory_id"] == "huakang-a"

    login_as(client, "b_molding_clerk")
    b_tasks = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-b"},
    )
    assert b_tasks.status_code == 200
    assert order_id not in {row["order"]["id"] for row in b_tasks.json()}
    assert client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "开始处理"},
    ).status_code == 403

    login_as(client, "c_engineer")
    assert client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "开始处理"},
    ).status_code == 403

    login_as(client, "a_molding_clerk")
    start_response = client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "开始处理"},
    )
    assert start_response.status_code == 200
    item = start_response.json()["items"][0]
    item_response = client.patch(
        f"/api/injection/{order_id}/items",
        json={
            "items": [
                {
                    "id": item["id"],
                    "actual_weight_kg": 2.4,
                    "collected_weight_kg": 2.5,
                }
            ]
        },
    )
    assert item_response.status_code == 200, item_response.text

    trial_response = client.put(
        f"/api/injection/{order_id}/trial-reports/{item['id']}",
        json={"data": {"trial_summary": "华康A试模完成", "tester_name": "A啤机文员"}},
    )
    assert trial_response.status_code == 200
    assert trial_response.json()["factory_id"] == "huakang-a"

    problem_response = client.post(
        "/api/problems",
        json={"order_id": order_id, "description": "生产中发现轻微缩水", "reported_by": "A啤机文员"},
    )
    assert problem_response.status_code == 201
    assert problem_response.json()["factory_id"] == "huakang-a"

    complete_response = client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "标记完成"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["order"]["status"] == "已完成"

    login_as(client, "c_engineer")
    origin_detail = client.get(f"/api/injection/{order_id}")
    assert origin_detail.status_code == 200
    assert origin_detail.json()["trial_reports"][0]["factory_id"] == "huakang-a"
    assert origin_detail.json()["problems"][0]["factory_id"] == "huakang-a"
    engineering_notifications = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-c",
            "order_id": order_id,
            "target_module": "engineering_molding_sample",
        },
    )
    assert engineering_notifications.status_code == 200
    assert {notification["event_type"] for notification in engineering_notifications.json()} >= {
        "生产问题反馈",
        "生产完成回传",
    }


def test_huakang_d_routes_to_b_and_c_d_assignment_validation_is_authoritative(client):
    login_as(client, "c_engineer")
    missing_order_id = "BP-HKC-NO-EXECUTOR"
    missing_response = client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            missing_order_id,
            origin_factory_id="huakang-c",
            production_factory_id=None,
        ),
    )
    assert missing_response.status_code == 201
    login_as(client, "c_supervisor")
    blocked_approval = client.patch(
        f"/api/injection/{missing_order_id}/status",
        json={"action": "主管通过"},
    )
    assert blocked_approval.status_code == 400
    assert "华康A或华康B" in blocked_approval.json()["detail"]

    for index, invalid_factory_id in enumerate(("huakang-c", "group", "*", "unknown"), start=1):
        login_as(client, "c_engineer")
        invalid_response = client.post(
            "/api/injection",
            json=cross_factory_order_payload(
                f"BP-HKC-INVALID-{index}",
                origin_factory_id="huakang-c",
                production_factory_id=invalid_factory_id,
            ),
        )
        assert invalid_response.status_code == 400

    external_order_id = "BP-HKC-EXTERNAL-NO-DISPATCH"
    login_as(client, "c_engineer")
    external_payload = cross_factory_order_payload(
        external_order_id,
        origin_factory_id="huakang-c",
        production_factory_id="huakang-a",
    )
    external_payload["order"]["workshop"] = "模厂"
    external_payload["order"]["send_to"] = "发至模厂"
    external_create = client.post("/api/injection", json=external_payload)
    assert external_create.status_code == 201
    assert external_create.json()["order"]["production_factory_id"] is None
    login_as(client, "c_supervisor")
    external_dispatch = client.patch(
        f"/api/injection/{external_order_id}/production-assignment",
        json={
            "production_factory_id": "huakang-b",
            "reason": "外发单不应进入内部派厂",
            "expected_assignment_version": 0,
        },
    )
    assert external_dispatch.status_code == 400

    d_order_id = "BP-HKD-TO-HKB-001"
    login_as(client, "d_engineer")
    d_create = client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            d_order_id,
            origin_factory_id="huakang-d",
            production_factory_id="huakang-b",
        ),
    )
    assert d_create.status_code == 201
    login_as(client, "d_supervisor")
    assert client.patch(
        f"/api/injection/{d_order_id}/status",
        json={"action": "主管通过"},
    ).status_code == 200
    login_as(client, "b_molding_clerk")
    b_tasks = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-b"},
    )
    assert d_order_id in {row["order"]["id"] for row in b_tasks.json()}

    login_as(client, "admin")
    capability_response = client.get("/api/injection/factory-capabilities")
    assert capability_response.status_code == 200
    capabilities = {
        item["factory_id"]: item for item in capability_response.json()
    }
    assert capabilities["huakang-c"] == {
        "factory_id": "huakang-c",
        "has_molding_department": False,
        "allowed_production_factory_ids": ["huakang-a", "huakang-b"],
        "suggested_production_factory_id": "huakang-a",
    }
    assert capabilities["huakang-d"]["allowed_production_factory_ids"] == [
        "huakang-a",
        "huakang-b",
    ]
    assert capabilities["huakang-d"]["suggested_production_factory_id"] == "huakang-b"
    c_queue_response = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-c"},
    )
    assert c_queue_response.status_code == 400

    own_order_id = "BP-HKA-SELF-001"
    own_payload = cross_factory_order_payload(
        own_order_id,
        origin_factory_id="huakang-a",
        production_factory_id=None,
    )
    own_create = client.post("/api/injection", json=own_payload)
    assert own_create.status_code == 201
    assert own_create.json()["order"]["production_factory_id"] == "huakang-a"


def test_waiting_cross_factory_order_can_be_reassigned_once_with_queue_and_notification_handoff(client):
    order_id = "BP-HKC-REASSIGN-001"
    login_as(client, "c_engineer")
    assert client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    ).status_code == 201
    login_as(client, "c_supervisor")
    assert client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "主管通过"},
    ).status_code == 200

    reassign_response = client.patch(
        f"/api/injection/{order_id}/production-assignment",
        json={
            "production_factory_id": "huakang-b",
            "reason": "华康A机台维护，改由华康B承接",
            "expected_assignment_version": 1,
        },
    )
    assert reassign_response.status_code == 200
    reassigned = reassign_response.json()
    assert reassigned["order"]["production_factory_id"] == "huakang-b"
    assert reassigned["order"]["production_assignment_version"] == 2
    assert [log["to_production_factory_id"] for log in reassigned["dispatch_logs"]] == [
        "huakang-a",
        "huakang-b",
    ]
    assert reassigned["dispatch_logs"][-1]["reason"] == "华康A机台维护，改由华康B承接"

    stale_response = client.patch(
        f"/api/injection/{order_id}/production-assignment",
        json={
            "production_factory_id": "huakang-a",
            "reason": "并发旧页面提交",
            "expected_assignment_version": 1,
        },
    )
    assert stale_response.status_code == 409

    login_as(client, "a_molding_clerk")
    a_tasks = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-a"},
    ).json()
    assert order_id not in {row["order"]["id"] for row in a_tasks}
    a_notifications = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-a",
            "order_id": order_id,
            "target_module": "production_molding_sample_task",
        },
    )
    assert a_notifications.status_code == 200
    assert a_notifications.json()
    assert all(
        notification["status"] == "已处理"
        for notification in a_notifications.json()
    ), a_notifications.json()

    login_as(client, "b_molding_clerk")
    b_tasks = client.get(
        "/api/injection/production-tasks",
        params={"production_factory_id": "huakang-b"},
    ).json()
    assert order_id in {row["order"]["id"] for row in b_tasks}
    b_notifications = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-b",
            "order_id": order_id,
            "target_module": "production_molding_sample_task",
        },
    )
    assert b_notifications.status_code == 200
    assert any(notification["status"] == "未读" for notification in b_notifications.json())
    assert client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "开始处理"},
    ).status_code == 200

    login_as(client, "c_supervisor")
    production_stage_reassign = client.patch(
        f"/api/injection/{order_id}/production-assignment",
        json={
            "production_factory_id": "huakang-a",
            "reason": "生产中直接改派",
            "expected_assignment_version": 2,
        },
    )
    assert production_stage_reassign.status_code == 409


def test_cross_factory_requisition_and_inventory_remain_scoped_to_executor(client):
    order_id = "BP-HKC-HKA-INVENTORY-001"
    login_as(client, "c_engineer")
    assert client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    ).status_code == 201
    login_as(client, "c_supervisor")
    assert client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "主管通过"},
    ).status_code == 200

    login_as(client, "a_warehouse_keeper")
    batch_response = client.post(
        "/api/inventory-batches",
        json={
            "factory_id": "huakang-a",
            "material": "HIPS 425",
            "batch_no": "HKA-HIPS-001",
            "location": "A-01",
            "initial_weight_kg": 50,
        },
    )
    assert batch_response.status_code == 201
    batch = batch_response.json()
    assert batch["factory_id"] == "huakang-a"

    requisition_response = client.post(
        "/api/requisitions",
        json={
            "date": "2026-07-18",
            "order_id": order_id,
            "material": "HIPS 425",
            "requested_weight_kg": 2.5,
            "applicant": "华康A啤机部",
        },
    )
    assert requisition_response.status_code == 201
    requisition = requisition_response.json()
    assert requisition["factory_id"] == "huakang-a"
    issue_response = client.patch(
        f"/api/requisitions/{requisition['id']}/status",
        json={
            "status": "已出库",
            "inventory_batch_id": batch["id"],
            "issued_at": "2026-07-18 17:00:00",
        },
    )
    assert issue_response.status_code == 200

    movements_response = client.get(
        "/api/inventory-movements",
        params={"factory_id": "huakang-a", "requisition_id": requisition["id"]},
    )
    assert movements_response.status_code == 200
    assert movements_response.json()[0]["factory_id"] == "huakang-a"

    login_as(client, "b_warehouse_keeper")
    assert client.get(
        "/api/inventory-batches",
        params={"factory_id": "huakang-a"},
    ).status_code == 403
    own_batches = client.get(
        "/api/inventory-batches",
        params={"factory_id": "huakang-b"},
    )
    assert own_batches.status_code == 200
    assert own_batches.json() == []


def test_cross_factory_approval_retry_is_idempotent_and_does_not_duplicate_notice(client):
    order_id = "BP-HKC-APPROVAL-IDEMPOTENT-001"
    login_as(client, "c_engineer")
    assert client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    ).status_code == 201

    login_as(client, "c_supervisor")
    first_approval = client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "主管通过"},
    )
    repeated_approval = client.patch(
        f"/api/injection/{order_id}/status",
        json={"action": "主管通过"},
    )

    assert first_approval.status_code == 200
    assert repeated_approval.status_code == 200
    repeated_detail = repeated_approval.json()
    assert repeated_detail["order"]["status"] == "待生产"
    assert len([
        audit
        for audit in repeated_detail["audit_logs"]
        if audit["action"] == "主管通过"
    ]) == 1

    login_as(client, "a_molding_clerk")
    notifications = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-a",
            "order_id": order_id,
            "target_module": "production_molding_sample_task",
        },
    )
    assert notifications.status_code == 200
    effective_waiting_notices = [
        notification
        for notification in notifications.json()
        if notification["event_type"] == "待生产"
        and notification["status"] != "已处理"
    ]
    assert len(effective_waiting_notices) == 1


def test_approval_refreshes_assignment_when_reassignment_wins_the_race(client, monkeypatch):
    order_id = "BP-HKC-APPROVAL-REASSIGN-RACE-001"
    login_as(client, "c_engineer")
    assert client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    ).status_code == 201

    service = importlib.import_module("app.services.molding_sample")
    main_module = importlib.import_module("app.main")
    original_guard = service.acquire_approval_transition_guard
    approval_reached_guard = Event()
    allow_approval_to_continue = Event()

    def delayed_approval_guard(db, *args, **kwargs):
        # End the initial read transaction so the second session can commit the
        # reassignment. The approval request still holds its original A snapshot.
        db.rollback()
        approval_reached_guard.set()
        assert allow_approval_to_continue.wait(timeout=10)
        return original_guard(db, *args, **kwargs)

    monkeypatch.setattr(
        service,
        "acquire_approval_transition_guard",
        delayed_approval_guard,
    )
    approval_result: dict[str, object] = {}

    with TestClient(main_module.app) as approval_client:
        login_as(approval_client, "c_supervisor")
        login_as(client, "c_supervisor")

        def approve_order() -> None:
            try:
                approval_result["response"] = approval_client.patch(
                    f"/api/injection/{order_id}/status",
                    json={"action": "主管通过"},
                )
            except BaseException as error:  # pragma: no cover - surfaced below
                approval_result["error"] = error

        approval_thread = Thread(target=approve_order)
        approval_thread.start()
        assert approval_reached_guard.wait(timeout=10)

        try:
            reassignment = client.patch(
                f"/api/injection/{order_id}/production-assignment",
                json={
                    "production_factory_id": "huakang-b",
                    "reason": "审批并发测试：改由华康B承接",
                    "expected_assignment_version": 1,
                },
            )
            assert reassignment.status_code == 200, reassignment.text
        finally:
            allow_approval_to_continue.set()
            approval_thread.join(timeout=10)
        assert not approval_thread.is_alive()

    assert "error" not in approval_result, approval_result.get("error")
    approval_response = approval_result.get("response")
    assert approval_response is not None
    assert hasattr(approval_response, "status_code")
    assert approval_response.status_code == 200
    approved = approval_response.json()
    assert approved["order"]["production_factory_id"] == "huakang-b"
    assert approved["order"]["status"] == "待生产"

    login_as(client, "a_molding_clerk")
    old_factory_notices = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-a",
            "order_id": order_id,
            "target_module": "production_molding_sample_task",
        },
    )
    assert old_factory_notices.status_code == 200
    assert old_factory_notices.json() == []

    login_as(client, "b_molding_clerk")
    new_factory_notices = client.get(
        "/api/molding-sample-notifications",
        params={
            "factory_id": "huakang-b",
            "order_id": order_id,
            "target_module": "production_molding_sample_task",
        },
    )
    assert new_factory_notices.status_code == 200
    assert [
        notice["event_type"] for notice in new_factory_notices.json()
    ] == ["待生产"]


def test_pending_cross_factory_order_cannot_create_or_list_requisitions(client):
    order_id = "BP-HKC-PENDING-REQUISITION-BLOCK-001"
    login_as(client, "c_engineer")
    assert client.post(
        "/api/injection",
        json=cross_factory_order_payload(
            order_id,
            origin_factory_id="huakang-c",
            production_factory_id="huakang-a",
        ),
    ).status_code == 201

    login_as(client, "a_warehouse_keeper")
    create_response = client.post(
        "/api/requisitions",
        json={
            "date": "2026-07-18",
            "order_id": order_id,
            "material": "HIPS 425",
            "requested_weight_kg": 2.5,
            "applicant": "华康A仓库",
        },
    )
    list_response = client.get(
        "/api/requisitions",
        params={"order_id": order_id},
    )

    assert create_response.status_code == 403
    assert "待生产或生产中" in create_response.json()["detail"]
    assert list_response.status_code == 403
    assert "正式生产阶段" in list_response.json()["detail"]


def test_full_order_edit_cannot_switch_between_internal_and_external_flow(client):
    internal_order_id = "BP-HKC-INTERNAL-TO-EXTERNAL-BLOCK-001"
    login_as(client, "c_engineer")
    internal_payload = cross_factory_order_payload(
        internal_order_id,
        origin_factory_id="huakang-c",
        production_factory_id="huakang-a",
    )
    assert client.post("/api/injection", json=internal_payload).status_code == 201
    internal_payload["order"]["workshop"] = "模厂"
    internal_payload["order"]["send_to"] = "发至模厂"
    internal_to_external = client.put(
        f"/api/injection/{internal_order_id}",
        json=internal_payload,
    )
    assert internal_to_external.status_code == 400
    assert "不可通过全单编辑切换内部生产与外发流程" in internal_to_external.json()["detail"]
    unchanged_internal = client.get(f"/api/injection/{internal_order_id}").json()
    assert unchanged_internal["order"]["production_factory_id"] == "huakang-a"
    assert unchanged_internal["order"]["send_to"] != "发至模厂"

    external_order_id = "BP-HKC-EXTERNAL-TO-INTERNAL-BLOCK-001"
    external_payload = cross_factory_order_payload(
        external_order_id,
        origin_factory_id="huakang-c",
        production_factory_id="huakang-a",
    )
    external_payload["order"]["workshop"] = "模厂"
    external_payload["order"]["send_to"] = "发至模厂"
    external_create = client.post("/api/injection", json=external_payload)
    assert external_create.status_code == 201
    assert external_create.json()["order"]["production_factory_id"] is None

    external_payload["order"]["workshop"] = "A车间"
    external_payload["order"]["send_to"] = ""
    external_to_internal = client.put(
        f"/api/injection/{external_order_id}",
        json=external_payload,
    )
    assert external_to_internal.status_code == 400
    assert "不可通过全单编辑切换内部生产与外发流程" in external_to_internal.json()["detail"]
    unchanged_external = client.get(f"/api/injection/{external_order_id}").json()
    assert unchanged_external["order"]["production_factory_id"] is None
    assert unchanged_external["order"]["send_to"] == "发至模厂"
