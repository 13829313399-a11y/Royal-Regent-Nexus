from datetime import datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from openpyxl import Workbook, load_workbook

from test_molding_sample_api import login_as, make_client


FIXED_NOW = datetime(2026, 8, 5, 10, 35, tzinfo=ZoneInfo("Asia/Shanghai"))


def _freeze_carton_time(monkeypatch) -> None:
    import app.services.carton_procurement as service

    monkeypatch.setattr(service, "business_now", lambda: FIXED_NOW)


def _order_payload() -> dict[str, object]:
    return {
        "factory_id": "huaxing",
        "customer_code": "DICKIE",
        "customer_name": "Dickie",
        "contract_no": "SC700145365",
        "item_no": "203302044",
        "product_name": "多文盒",
        "product_order_quantity": "3600",
        "order_date": "2026-08-05",
        "due_date": "2026-08-12",
        "status": "PENDING_SUPPLIER",
        "note": "一张合同包含多类纸品",
        "lines": [
            {
                "packaging_type": "外箱",
                "paper_quality": "A33+B",
                "specification": "31.5 × 11.125 × 11.25",
                "dimension_unit": "in",
                "usage_quantity": "0.00833333",
                "unit": "个",
                "unit_price": "3.46",
            },
            {
                "packaging_type": "滑板纸",
                "paper_quality": "A9A",
                "specification": "30.75 × 10.5",
                "dimension_unit": "in",
                "usage_quantity": "1",
                "unit": "张",
                "unit_price": "0.96",
            },
        ],
    }


def _create_order(client) -> dict[str, object]:
    customers = client.get(
        "/api/carton-procurement/customers",
        params={"factory_id": "huaxing"},
    )
    assert customers.status_code == 200, customers.text
    if customers.json()["total"] == 0:
        login_as(client, "admin")
        created_customer = client.post(
            "/api/carton-procurement/customers",
            json={
                "factory_id": "huaxing",
                "customer_code": "DICKIE",
                "customer_name": "Dickie",
                "country_region": "德国",
            },
        )
        assert created_customer.status_code == 201, created_customer.text
        login_as(client, "warehouse_keeper")
    response = client.post("/api/carton-procurement/orders", json=_order_payload())
    assert response.status_code == 201, response.text
    return response.json()


def test_customer_master_crud_permission_and_order_snapshot(monkeypatch):
    with make_client(monkeypatch) as client:
        warehouse_profile = login_as(client, "warehouse_keeper")
        assert "carton_procurement:customer_manage" not in warehouse_profile["permissions"]
        forbidden = client.post(
            "/api/carton-procurement/customers",
            json={
                "factory_id": "huaxing",
                "customer_code": "DICKIE",
                "customer_name": "Dickie",
            },
        )
        assert forbidden.status_code == 403

        login_as(client, "admin")
        created = client.post(
            "/api/carton-procurement/customers",
            json={
                "factory_id": "huaxing",
                "customer_code": "dickie",
                "customer_name": "Dickie 原名称",
                "country_region": "德国",
                "contact_name": "采购联系人",
                "contact_phone": "12345678",
                "note": "纸箱部维护",
            },
        )
        assert created.status_code == 201, created.text
        customer = created.json()
        assert customer["customer_code"] == "DICKIE"

        updated = client.patch(
            f"/api/carton-procurement/customers/{customer['id']}",
            json={
                "factory_id": "huaxing",
                "expected_revision": customer["revision"],
                "customer_name": "Dickie 正式名称",
            },
        )
        assert updated.status_code == 200, updated.text
        customer = updated.json()
        assert customer["customer_name"] == "Dickie 正式名称"

        unused = client.post(
            "/api/carton-procurement/customers",
            json={
                "factory_id": "huaxing",
                "customer_code": "UNUSED",
                "customer_name": "未使用客户",
            },
        ).json()
        removed = client.delete(
            f"/api/carton-procurement/customers/{unused['id']}",
            params={"factory_id": "huaxing"},
        )
        assert removed.status_code == 204

        login_as(client, "warehouse_keeper")
        order_payload = _order_payload()
        order_payload["customer_name"] = "客户端伪造名称"
        order_response = client.post("/api/carton-procurement/orders", json=order_payload)
        assert order_response.status_code == 201, order_response.text
        assert order_response.json()["customer_name"] == "Dickie 正式名称"

        login_as(client, "admin")
        blocked_delete = client.delete(
            f"/api/carton-procurement/customers/{customer['id']}",
            params={"factory_id": "huaxing"},
        )
        assert blocked_delete.status_code == 409
        assert "停用" in blocked_delete.json()["detail"]

        disabled = client.patch(
            f"/api/carton-procurement/customers/{customer['id']}",
            json={
                "factory_id": "huaxing",
                "expected_revision": customer["revision"],
                "status": "INACTIVE",
            },
        )
        assert disabled.status_code == 200, disabled.text

        login_as(client, "warehouse_keeper")
        blocked_order = client.post("/api/carton-procurement/orders", json=_order_payload())
        assert blocked_order.status_code == 422
        assert "已停用" in blocked_order.json()["detail"]


def _create_receipt(client, order: dict[str, object]) -> dict[str, object]:
    first_line = order["lines"][0]
    response = client.post(
        "/api/carton-procurement/receipts",
        json={
            "factory_id": "huaxing",
            "delivery_note_no": "DN26080501",
            "delivery_date": "2026-08-05",
            "note": "人工核对送货单",
            "lines": [
                {
                    "order_line_id": first_line["id"],
                    "delivered_quantity": "10",
                    "received_quantity": "10",
                    "damaged_quantity": "1",
                    "rejected_quantity": "0",
                    "unusable_quantity": "0",
                    "location": "纸箱仓 A-03",
                    "feedback_note": "1 个破损",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _workbook_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_grouped_order_calculation_and_factory_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        unauthenticated = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        )
        assert unauthenticated.status_code == 401

        profile = login_as(client, "warehouse_keeper")
        assert "carton_procurement:read" in profile["permissions"]
        assert "carton_procurement:order_write" in profile["permissions"]
        _freeze_carton_time(monkeypatch)

        order = _create_order(client)
        assert order["status"] == "CONFIRMED"
        assert order["customer_code"] == "DICKIE"
        assert len(order["lines"]) == 2
        assert order["lines"][0]["packaging_type"] == "外箱"
        assert order["lines"][0]["paper_quality"] == "A33+B"
        assert order["lines"][0]["specification"] == "31.5 × 11.125 × 11.25"
        assert Decimal(order["lines"][0]["required_quantity"]) == Decimal("30.0000")
        assert Decimal(order["lines"][1]["required_quantity"]) == Decimal("3600.0000")

        listed = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing", "search": "203302044"},
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["id"] == order["id"]

        forbidden = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huadeng"},
        )
        assert forbidden.status_code == 403


def test_purchase_order_export_contains_grouped_lines_and_formula(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)

        response = client.get(
            f"/api/carton-procurement/orders/{order['order_no']}/purchase-order.xlsx",
            params={"factory_id": "huaxing"},
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "纸箱采购单.xlsx" in unquote(response.headers["content-disposition"])

        workbook = load_workbook(BytesIO(response.content), data_only=False)
        sheet = workbook["纸箱采购单"]
        assert "华兴厂纸箱采购单" in sheet["A1"].value
        assert sheet["B4"].value == order["order_no"]
        assert sheet["E5"].value == "河源东康纸品有限公司"
        assert sheet["B6"].value == "Dickie"
        assert sheet["E6"].value == "SC700145365"
        assert sheet["H6"].value == "203302044"
        assert sheet["H7"].value == "已下单"
        assert sheet["A9"].value == "序号"
        assert sheet["B10"].value == "外箱"
        assert sheet["B11"].value == "滑板纸"
        assert sheet["G10"].value == "=ROUND(E10*F10,4)"
        assert "无需供应商回签确认" in sheet[f"A{sheet.max_row}"].value
        workbook.close()


def test_receipt_confirmation_is_human_gated_idempotent_and_creates_inventory(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        receipt = _create_receipt(client, order)

        assert receipt["status"] == "PENDING_CONFIRMATION"
        assert Decimal(receipt["lines"][0]["effective_quantity"]) == Decimal("9.0000")

        before = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        )
        assert before.status_code == 200
        assert before.json()["total"] == 0

        confirmed = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": 1},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "POSTED"

        duplicate_confirm = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": 1},
        )
        assert duplicate_confirm.status_code == 200

        movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()
        assert movements["total"] == 1
        assert movements["items"][0]["movement_type"] == "INBOUND"
        assert Decimal(movements["items"][0]["quantity"]) == Decimal("9.0000")
        assert Decimal(movements["items"][0]["balance"]) == Decimal("9.0000")

        refreshed_order = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["items"][0]
        assert refreshed_order["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(refreshed_order["lines"][0]["received_quantity"]) == Decimal("9.0000")
        assert Decimal(refreshed_order["lines"][0]["remaining_quantity"]) == Decimal("21.0000")


def test_manual_movement_reversal_and_locked_month(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        receipt = _create_receipt(client, order)
        client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": 1},
        )
        order_line_id = order["lines"][0]["id"]

        outbound = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "factory_id": "huaxing",
                "order_line_id": order_line_id,
                "movement_type": "OUTBOUND",
                "quantity": "4",
                "location": "纸箱仓 A-03",
                "document_no": "OUT-260805-001",
                "reason": "车间领料",
            },
        )
        assert outbound.status_code == 201, outbound.text
        assert Decimal(outbound.json()["quantity"]) == Decimal("-4.0000")
        assert Decimal(outbound.json()["balance"]) == Decimal("5.0000")

        reversal = client.post(
            f"/api/carton-procurement/inventory/movements/{outbound.json()['id']}/reverse",
            json={"factory_id": "huaxing", "reason": "领料单录入错误"},
        )
        assert reversal.status_code == 201, reversal.text
        assert Decimal(reversal.json()["quantity"]) == Decimal("4.0000")
        assert Decimal(reversal.json()["balance"]) == Decimal("9.0000")

        duplicate_reversal = client.post(
            f"/api/carton-procurement/inventory/movements/{outbound.json()['id']}/reverse",
            json={"factory_id": "huaxing", "reason": "重复冲销"},
        )
        assert duplicate_reversal.status_code == 409

        closings = client.post(
            "/api/carton-procurement/closings/generate",
            json={"factory_id": "huaxing", "period": "2026-08", "customer_code": "DICKIE"},
        )
        assert closings.status_code == 200, closings.text
        closing = closings.json()[0]
        assert Decimal(closing["ending_quantity"]) == Decimal("9.0000")

        for next_status in ("PENDING", "CONFIRMED", "LOCKED"):
            response = client.post(
                f"/api/carton-procurement/closings/{closing['id']}/status",
                json={
                    "factory_id": "huaxing",
                    "expected_revision": closing["revision"],
                    "status": next_status,
                },
            )
            assert response.status_code == 200, response.text
            closing = response.json()

        blocked = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "factory_id": "huaxing",
                "order_line_id": order_line_id,
                "movement_type": "ADJUSTMENT",
                "quantity": "1",
                "location": "纸箱仓 A-03",
                "document_no": "ADJ-260805-002",
                "reason": "盘点调整",
            },
        )
        assert blocked.status_code == 409
        assert "已锁账" in blocked.json()["detail"]


def test_import_parses_matches_and_registers_exceptions_without_creating_business_data(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        content = _workbook_bytes(
            ["日期", "入库单号", "PO", "货号", "外箱", "纸质", "长", "宽", "高", "单价", "仓位"],
            [
                ["2026-08-05", "DN26080501", "SC700145365", "203302044", 10, "A33+B外箱", 31.5, 11.125, 11.25, 3.46, "纸箱仓 A-03"],
                ["2026-08-05", "DN26080501", "SC-NOT-ORDERED", "209999999", 5, "B3B内箱", 15.5, 10.625, 5.25, 0.96, "纸箱仓 A-04"],
            ],
        )
        first = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN26080501.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert first.status_code == 201, first.text
        assert first.json()["status"] == "REQUIRES_REVIEW"
        assert first.json()["duplicate"] is False
        assert first.json()["parse_summary"]["row_count"] == 2
        assert first.json()["parse_summary"]["matched_count"] == 1
        assert first.json()["parse_summary"]["issue_count"] == 1
        matched = first.json()["parse_summary"]["rows"][0]
        assert matched["match_status"] == "MATCHED"
        assert matched["order_line_id"] == order["lines"][0]["id"]
        assert matched["packaging_type"] == "外箱"
        assert matched["paper_quality"] == "A33+B"
        assert first.json()["parse_summary"]["creates_inventory"] is False

        duplicate = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN26080501.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == first.json()["id"]
        assert duplicate.json()["duplicate"] is True

        latest = client.get(
            "/api/carton-procurement/receipt-imports/latest",
            params={"factory_id": "huaxing"},
        )
        assert latest.status_code == 200, latest.text
        assert latest.json()["id"] == first.json()["id"]
        assert latest.json()["parse_summary"]["row_count"] == 2

        exceptions = client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing"},
        )
        assert exceptions.status_code == 200, exceptions.text
        assert exceptions.json()["total"] == 1
        exception = exceptions.json()["items"][0]
        assert exception["category"] == "RECEIPT_UNMATCHED"
        assert exception["status"] == "OPEN"

        started = client.patch(
            f"/api/carton-procurement/exceptions/{exception['id']}",
            json={
                "factory_id": "huaxing",
                "expected_revision": exception["revision"],
                "status": "IN_PROGRESS",
                "owner_department": "纸箱仓管",
                "resolution_note": "",
            },
        )
        assert started.status_code == 200, started.text
        resolved = client.patch(
            f"/api/carton-procurement/exceptions/{exception['id']}",
            json={
                "factory_id": "huaxing",
                "expected_revision": started.json()["revision"],
                "status": "RESOLVED",
                "owner_department": "纸箱仓管",
                "resolution_note": "已人工确认该货号尚未建立正式纸箱订单",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "RESOLVED"

        assert client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 1
        assert client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 0


def test_weekly_schedule_import_never_creates_formal_orders(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _create_order(client)
        content = _workbook_bytes(
            ["Reference", "PO.NO", "客名/国家", "产品编号", "产品名称", "数量", "装箱", "验货期（请提前准备好货物）"],
            [
                ["SC700145365", "PO-001", "Dickie", "203302044", "多文盒", 3600, "1/120", "8月10日-8月13日"],
                ["SC-NOT-ORDERED", "PO-002", "Dickie", "209999999", "漏单样例", 1200, "1/60", "8月15日-8月18日"],
            ],
        )
        response = client.post(
            "/api/carton-procurement/weekly-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("每周客人查货排期.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 201, response.text
        summary = response.json()["parse_summary"]
        assert summary["row_count"] == 2
        assert summary["matched_count"] == 1
        assert summary["issue_count"] == 1
        assert summary["creates_order"] is False
        assert [row["match_status"] for row in summary["rows"]] == ["MATCHED", "MISSING_ORDER"]
        assert client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 1
        exceptions = client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing"},
        ).json()
        assert exceptions["total"] == 1
        assert exceptions["items"][0]["category"] == "MISSING_ORDER"
