from datetime import date
from decimal import Decimal
from io import BytesIO
import importlib
import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import msoffcrypto
import openpyxl


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'customer_order_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def ensure_user(username: str, role_id: str, department: str, factory_id: str = "huaxing") -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    with db_module.SessionLocal() as db:
        if db.get(auth_models.AuthUser, user_id) is None:
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
        binding_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        if db.get(auth_models.AuthUserRole, binding_id) is None:
            db.add(
                auth_models.AuthUserRole(
                    id=binding_id,
                    user_id=user_id,
                    role_id=role_id,
                    factory_id=factory_id,
                    department=department,
                )
            )
        db.commit()


def login(client: TestClient, username: str, role_id: str, department: str) -> dict:
    ensure_user(username, role_id, department)
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200
    return response.json()


def encrypt_xlsx(payload: bytes) -> bytes:
    workbook = msoffcrypto.OfficeFile(BytesIO(payload))
    output = BytesIO()
    workbook.encrypt("2026", output)
    return output.getvalue()


def decrypt_xlsx(payload: bytes) -> bytes:
    workbook = msoffcrypto.OfficeFile(BytesIO(payload))
    assert workbook.is_encrypted()
    workbook.load_key(password="2026")
    output = BytesIO()
    workbook.decrypt(output)
    return output.getvalue()


def build_wmc_po(
    *,
    contract_no: int = 53138,
    po_no: str = "0009382481",
    quantity: int = 3000,
) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet["M3"] = date(2026, 7, 24)
    sheet["L4"] = "Contract No."
    sheet["N4"] = contract_no
    sheet["P4"] = "WMC"
    sheet["A8"] = "Date of Loading:"
    sheet["F8"] = date(2026, 9, 17)
    sheet["M10"] = "INSPECTION: 17 SEPT. 26"
    sheet["A12"] = "Our Item# :"
    sheet["F12"] = 67771
    sheet["I13"] = f"PO / BON DE COMMANDE: {po_no}"
    sheet["A14"] = "Goods:"
    sheet["C14"] = "AF DOUBLE FIRE"
    sheet["A16"] = "Quantity:"
    sheet["F16"] = quantity
    sheet["A22"] = "Shipping Carton Packing"
    sheet["F22"] = 5
    sheet["A48"] = "PACKAGING REF: 67771-05-26-WMC"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def build_schedule(*, include_price: bool = True) -> bytes:
    workbook = openpyxl.Workbook()
    order = workbook.active
    order.title = "接单表"
    review = workbook.create_sheet("正单评审表")
    bullet_item = workbook.create_sheet("子弹枪ITEM表")
    water_item = workbook.create_sheet("水枪ITEM表")

    order["C3"] = "P/O#:"
    order["M3"] = "单价HK$"
    for column in range(2, 20):
        order.cell(4, column).value = ""
    order["C4"] = "0001111111"
    order["D4"] = "50000"
    order["E4"] = "WMC"
    order["F4"] = "67771"
    order["G4"] = "双管枪"
    order["H4"] = "AF DOUBLE FIRE"
    order["I4"] = 100
    order["J4"] = 5
    order["K4"] = "=I4/J4"
    order["L4"] = "加拿大标准"
    if include_price:
        order["M4"] = 23.96
    order["S4"] = date(2026, 8, 1)
    order["M5"] = "合计:HK$"
    order["O5"] = "=SUM(O4:O4)"

    review["C3"] = "PO.NO"
    review["R3"] = "单价HK$"
    for column in range(2, 24):
        review.cell(4, column).value = ""
    review["D4"] = "50000"
    review["F4"] = "67771"
    review["G4"] = "双管枪"
    review["R5"] = "子弹枪合计"
    review["T5"] = "=SUM(T4:T4)"
    review["R7"] = "水枪合计"
    review["T7"] = "=SUM(T6:T6)"

    item_headers = (
        "客出单日期",
        "预备单号（OQF NO）",
        "PO.NO",
        "客名/国家",
        "产品编号",
        "中文名称",
        "产品名称",
        "数量",
        "装箱",
        "彩盒条形码",
        "包装",
        "系统",
        "行验",
        "客验",
        "客要求走货期",
        "备注",
        "客人PO",
    )
    for sheet in (bullet_item, water_item):
        for column, header in enumerate(item_headers, 1):
            sheet.cell(3, column).value = header

    bullet_item["B4"] = "2026-6-23-67771"
    bullet_item["E4"] = "67771-2"
    bullet_item["F4"] = "双管枪"
    bullet_item["G4"] = "AF DOUBLE FIRE"
    bullet_item["H4"] = 5000
    bullet_item["I4"] = 5
    bullet_item["K4"] = "67771-05-24-WMC(r1)"
    bullet_item["L4"] = "系统"
    bullet_item["M4"] = "备料单"
    bullet_item["A5"] = date(2026, 7, 1)
    bullet_item["B5"] = "2026-7-1-40210"
    bullet_item["C5"] = "53099"
    bullet_item["D5"] = "WMC"
    bullet_item["E5"] = "40210-1"
    bullet_item["F5"] = "转盘枪"
    bullet_item["G5"] = "MAYHEM OUTRAGE"
    bullet_item["H5"] = 48
    bullet_item["I5"] = 4
    bullet_item["K5"] = "40210-03-26-WM"
    bullet_item["O5"] = date(2026, 8, 10)
    bullet_item["Q5"] = "0001111111"
    bullet_item["A7"] = "已走货子弹枪"

    water_item["B4"] = "2026-1-2-11580-1/-2"
    water_item["E4"] = "11580-1/-2"
    water_item["F4"] = "鱼缸水枪"
    water_item["G4"] = "OCEAN OUTLAW BLASTER"
    water_item["H4"] = 2352
    water_item["K4"] = "11580-10-25-EN"
    water_item["L4"] = "备料单"
    water_item["A5"] = date(2026, 7, 1)
    water_item["B5"] = "2026-7-1-19570"
    water_item["C5"] = "53098"
    water_item["D5"] = "AAFES"
    water_item["E5"] = "19570-3"
    water_item["F5"] = "中水枪"
    water_item["G5"] = "GARGOYLE 2 PACK"
    water_item["H5"] = 120
    water_item["I5"] = 6
    water_item["K5"] = "19570-10-23-EN"
    water_item["O5"] = date(2026, 8, 10)
    water_item["A7"] = "已走货水枪"

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return encrypt_xlsx(output.getvalue())


def upload_preview(client: TestClient):
    return client.post(
        "/api/customer-orders/buzzbee/preview",
        data={"factory_id": "huaxing", "received_date": "2026-07-27"},
        files={
            "po_file": (
                "WM-67771-53138-WMC.xlsx",
                build_wmc_po(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "schedule_file": (
                "2026年 BUZZ BEE 生产排期表.xls.xlsx",
                build_schedule(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )


def test_buzzbee_preview_requires_sales_permission_and_maps_seventeen_fields(monkeypatch):
    with make_client(monkeypatch) as client:
        assert upload_preview(client).status_code == 401

        login(client, "customer_order_engineer", "engineer", "engineering")
        assert upload_preview(client).status_code == 403

        client.post("/api/auth/logout")
        profile = login(client, "customer_order_sales", "sales_customer_owner", "sales-business")
        assert "customer_order:read" in profile["permissions"]
        assert "customer_order:export" in profile["permissions"]

        response = upload_preview(client)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["summary"] == {"total": 1, "valid": 1, "warning": 0, "blocked": 0}
        assert preview["input_template"] == "BUZZBEE_WALMART_WMC_INLINE_V1"
        assert preview["target_template"] == "BUZZBEE_PRODUCTION_SCHEDULE_V1"
        assert preview["po_file_count"] == 1
        assert preview["po_file_names"] == ["WM-67771-53138-WMC.xlsx"]
        assert preview["output_file_name"] == "2026年 BUZZ BEE 生产排期表.xls.xlsx"
        row = preview["rows"][0]
        assert {
            "received_date": row["received_date"],
            "po_no": row["po_no"],
            "contract_no": row["contract_no"],
            "customer_country": row["customer_country"],
            "product_no": row["product_no"],
            "product_name_zh": row["product_name_zh"],
            "product_name_en": row["product_name_en"],
            "quantity": row["quantity"],
            "units_per_carton": row["units_per_carton"],
            "carton_count": row["carton_count"],
            "standard": row["standard"],
            "unit_price_hkd": row["unit_price_hkd"],
            "amount_hkd": row["amount_hkd"],
            "packaging": row["packaging"],
            "line_q": row["line_q"],
            "customer_q": row["customer_q"],
            "requested_ship_date": row["requested_ship_date"],
        } == {
            "received_date": "2026-07-27",
            "po_no": "0009382481",
            "contract_no": "53138",
            "customer_country": "WMC / 加拿大",
            "product_no": "67771",
            "product_name_zh": "双管枪",
            "product_name_en": "AF DOUBLE FIRE",
            "quantity": "3000",
            "units_per_carton": "5",
            "carton_count": "600",
            "standard": "加拿大标准",
            "unit_price_hkd": "23.96",
            "amount_hkd": "71880",
            "packaging": "67771-05-26-WMC",
            "line_q": "2026-09-17",
            "customer_q": "2026-09-17",
            "requested_ship_date": "2026-09-17",
        }
        assert len(row["lineage"]) == 17
        assert row["item_sheet_name"] == "子弹枪ITEM表"


def test_buzzbee_export_requires_confirmation_and_returns_updated_encrypted_schedule(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "customer_order_exporter", "sales_customer_owner", "sales-business")
        common = {
            "factory_id": "huaxing",
            "received_date": "2026-07-27",
        }
        files = {
            "po_file": (
                "WM-67771-53138-WMC.xlsx",
                build_wmc_po(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "schedule_file": (
                "2026年 BUZZ BEE 生产排期表.xls.xlsx",
                build_schedule(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        }
        rejected = client.post(
            "/api/customer-orders/buzzbee/export",
            data={**common, "confirmed": "false"},
            files=files,
        )
        assert rejected.status_code == 400

        exported = client.post(
            "/api/customer-orders/buzzbee/export",
            data={**common, "confirmed": "true"},
            files=files,
        )
        assert exported.status_code == 200, exported.text
        assert exported.content.startswith(b"\xd0\xcf\x11\xe0")
        assert exported.headers["x-workbook-password-required"] == "true"
        assert exported.headers["x-output-template"] == "BUZZBEE_PRODUCTION_SCHEDULE_V1"
        assert "2026%E5%B9%B4%20BUZZ%20BEE" in exported.headers["content-disposition"]

        service = importlib.import_module("app.services.customer_order_buzzbee")
        workbook = service.OoxmlSchedule(decrypt_xlsx(exported.content))
        order_rows = workbook.read_rows("接单表")
        review_rows = workbook.read_rows("正单评审表")
        item_rows = workbook.read_rows("子弹枪ITEM表")
        assert order_rows[5]["C"] == "0009382481"
        assert order_rows[5]["D"] == "53138"
        assert order_rows[5]["F"] == "67771"
        assert order_rows[5]["K"] == "600"
        assert order_rows[5]["O"] == "71880"
        assert review_rows[5]["C"] == "0009382481"
        assert review_rows[5]["D"] == "53138"
        assert review_rows[5]["F"] == "67771"
        assert review_rows[5]["K"] == "600"
        assert review_rows[5]["T"] == "71880"
        assert order_rows[6]["M"] == "合计:HK$"
        assert review_rows[6]["R"] == "子弹枪合计"
        assert workbook.read_cell_formula("接单表", 6, "O") == "SUM(O4:O5)"
        assert workbook.read_cell_formula("正单评审表", 6, "T") == "SUM(T4:T5)"
        assert item_rows[4]["B"] == "2026-6-23-67771"
        assert item_rows[4]["C"] == "53138"
        assert item_rows[4]["D"] == "WMC"
        assert item_rows[4]["E"] == "67771-2"
        assert item_rows[4]["H"] == "3000"
        assert item_rows[4]["I"] == "5"
        assert item_rows[4]["K"] == "67771-05-26-WMC"
        assert item_rows[4]["L"] == "系统"
        assert item_rows[4]["M"] == item_rows[4]["N"] == item_rows[4]["O"]
        assert item_rows[4]["Q"] == "0009382481"
        assert item_rows[5]["H"] == "2000"
        assert item_rows[5]["M"] == "备料单"
        assert workbook.read_cell_formula("子弹枪ITEM表", 5, "H") == "5000-3000"


def test_batch_preview_and_export_merge_multiple_po_files_without_renaming_schedule(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "customer_order_batch", "sales_customer_owner", "sales-business")
        common = {
            "factory_id": "huaxing",
            "received_date": "2026-07-27",
        }

        def batch_files():
            return [
                (
                    "po_files",
                    (
                        "WM-67771-53138-WMC.xlsx",
                        build_wmc_po(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
                (
                    "po_files",
                    (
                        "WM-67771-53139-WMC.xlsx",
                        build_wmc_po(contract_no=53139, po_no="0009382482"),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
                (
                    "schedule_file",
                    (
                        "2026年 BUZZ BEE 生产排期表.xls.xlsx",
                        build_schedule(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            ]

        preview_response = client.post(
            "/api/customer-orders/buzzbee/preview-batch",
            data=common,
            files=batch_files(),
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["po_file_count"] == 2
        assert preview["po_file_names"] == [
            "WM-67771-53138-WMC.xlsx",
            "WM-67771-53139-WMC.xlsx",
        ]
        assert preview["summary"] == {"total": 2, "valid": 2, "warning": 0, "blocked": 0}
        assert preview["output_file_name"] == "2026年 BUZZ BEE 生产排期表.xls.xlsx"
        assert [row["source_po_file_name"] for row in preview["rows"]] == preview["po_file_names"]

        exported = client.post(
            "/api/customer-orders/buzzbee/export-batch",
            data={**common, "confirmed": "true", "skipped_issue_keys": "[]"},
            files=batch_files(),
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["x-po-file-count"] == "2"
        disposition = exported.headers["content-disposition"]
        assert "%E5%B7%B2%E5%A1%AB" not in disposition
        assert disposition.endswith(
            "2026%E5%B9%B4%20BUZZ%20BEE%20%E7%94%9F%E4%BA%A7%E6%8E%92%E6%9C%9F%E8%A1%A8.xls.xlsx"
        )

        service = importlib.import_module("app.services.customer_order_buzzbee")
        workbook = service.OoxmlSchedule(decrypt_xlsx(exported.content))
        order_rows = workbook.read_rows("接单表")
        review_rows = workbook.read_rows("正单评审表")
        item_rows = workbook.read_rows("子弹枪ITEM表")
        assert [order_rows[row]["D"] for row in (5, 6)] == ["53138", "53139"]
        assert [review_rows[row]["D"] for row in (5, 6)] == ["53138", "53139"]
        assert [item_rows[row]["C"] for row in (4, 5)] == ["53138", "53139"]
        assert [item_rows[row]["Q"] for row in (4, 5)] == ["0009382481", "0009382482"]
        assert item_rows[6]["H"] == "-1000"
        assert item_rows[6]["M"] == "备料单"
        assert workbook.read_cell_formula("子弹枪ITEM表", 6, "H") == "5000-3000-3000"
        assert order_rows[7]["M"] == "合计:HK$"
        assert review_rows[7]["R"] == "子弹枪合计"
        assert workbook.read_cell_formula("接单表", 7, "O") == "SUM(O4:O6)"
        assert workbook.read_cell_formula("正单评审表", 7, "T") == "SUM(T4:T6)"


def test_missing_price_can_be_explicitly_skipped_and_exports_blank_amounts(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "customer_order_price_skip", "sales_customer_owner", "sales-business")
        common = {
            "factory_id": "huaxing",
            "received_date": "2026-07-27",
        }

        def files():
            return {
                "po_file": (
                    "WM-67771-53138-WMC.xlsx",
                    build_wmc_po(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "schedule_file": (
                    "2026年 BUZZ BEE 生产排期表.xls.xlsx",
                    build_schedule(include_price=False),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            }

        preview_response = client.post(
            "/api/customer-orders/buzzbee/preview",
            data=common,
            files=files(),
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["summary"] == {"total": 1, "valid": 0, "warning": 0, "blocked": 1}
        price_issue = next(
            issue
            for issue in preview["rows"][0]["issues"]
            if issue["code"] == "missing_unit_price"
        )
        assert price_issue["can_skip"] is True
        assert price_issue["skip_label"] == "单价及金额留空，稍后由跟客补充"
        assert price_issue["skip_key"]

        rejected = client.post(
            "/api/customer-orders/buzzbee/export",
            data={**common, "confirmed": "true", "skipped_issue_keys": "[]"},
            files=files(),
        )
        assert rejected.status_code == 400
        assert "没有可确认的 HKD 单价" in rejected.json()["detail"]

        exported = client.post(
            "/api/customer-orders/buzzbee/export",
            data={
                **common,
                "confirmed": "true",
                "skipped_issue_keys": json.dumps([price_issue["skip_key"]]),
            },
            files=files(),
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["x-skipped-issue-count"] == "1"

        service = importlib.import_module("app.services.customer_order_buzzbee")
        workbook = service.OoxmlSchedule(decrypt_xlsx(exported.content))
        order_rows = workbook.read_rows("接单表")
        review_rows = workbook.read_rows("正单评审表")
        assert order_rows[5].get("M") in (None, "")
        assert order_rows[5].get("O") in (None, "")
        assert review_rows[5].get("R") in (None, "")
        assert review_rows[5].get("T") in (None, "")


def test_item_export_routes_water_product_and_deducts_preparation_stock():
    service = importlib.import_module("app.services.customer_order_buzzbee")
    plain_schedule, _ = service._decrypt_schedule(build_schedule())
    workbook = service.OoxmlSchedule(plain_schedule)
    result = service._write_item_order_row(
        workbook,
        {
            "received_date": "2026-07-27",
            "po_no": "",
            "contract_no": "52335",
            "customer_name": "AAFES",
            "product_no": "11580",
            "product_name_zh": "鱼缸水枪",
            "product_name_en": "OCEAN OUTLAW BLASTER",
            "quantity": "180",
            "units_per_carton": "6",
            "packaging": "11580-10-25-EN",
            "line_q": "2026-01-28",
            "customer_q": "To be Advised",
            "requested_ship_date": "2026-02-02",
        },
    )
    item_rows = workbook.read_rows("水枪ITEM表")
    assert result == {
        "sheet_name": "水枪ITEM表",
        "inserted_row": 4,
        "item_no": "11580-1/-2",
        "oqf_no": "2026-1-2-11580-1/-2",
    }
    assert item_rows[4]["C"] == "52335"
    assert item_rows[4]["D"] == "AAFES"
    assert item_rows[4]["E"] == "11580-1/-2"
    assert item_rows[4]["H"] == "180"
    assert item_rows[4]["I"] == "6"
    assert item_rows[4]["L"] == "系统"
    assert item_rows[4]["M"] == str((date(2026, 1, 28) - date(1899, 12, 30)).days)
    assert item_rows[4]["N"] == "To be Advised"
    assert item_rows[4]["O"] == str((date(2026, 2, 2) - date(1899, 12, 30)).days)
    assert item_rows[4].get("Q") in (None, "")
    assert item_rows[5]["H"] == "2172"
    assert item_rows[5]["L"] == "备料单"
    assert workbook.read_cell_formula("水枪ITEM表", 5, "H") == "2352-180"


def test_po_number_is_optional_for_standard_customer_but_required_for_walmart():
    service = importlib.import_module("app.services.customer_order_buzzbee")
    base_values = {
        "po_no": "",
        "contract_no": "52496",
        "customer_name": "AAFES",
        "country": "美国",
        "product_no": "40210",
        "product_name_en": "MAYHEM OUTRAGE",
        "quantity": "48",
        "units_per_carton": "4",
        "requested_ship_date": "2026-08-10",
        "inspection_date": "2026-08-10",
        "standard": "美国标准",
        "packaging": "40210-01-26-EN",
    }
    schedule_index = {
        "40210": service.ScheduleLookup(
            product_name_zh="转盘枪",
            unit_price_hkd=Decimal("9.25"),
            existing_rows=[],
        )
    }
    standard = service.ParsedPoLine(
        values=base_values,
        lineage={},
        input_template=service.STANDARD_TEMPLATE,
    )
    ordinary_row = service._build_preview_rows(
        [standard],
        schedule_index,
        "2026-07-27",
    )[0]
    assert ordinary_row["po_no"] == ""
    assert ordinary_row["status"] == "valid"
    assert not any(issue["field"] == "po_no" for issue in ordinary_row["issues"])

    walmart = service.ParsedPoLine(
        values={**base_values, "customer_name": "WMC", "country": "加拿大"},
        lineage={},
        input_template=service.WMC_TEMPLATE,
    )
    walmart_row = service._build_preview_rows(
        [walmart],
        schedule_index,
        "2026-07-27",
    )[0]
    po_issue = next(issue for issue in walmart_row["issues"] if issue["field"] == "po_no")
    assert walmart_row["status"] == "blocked"
    assert po_issue["message"] == "WM 客 P/O# 未能从 PO 提取"
    assert po_issue["can_skip"] is False
