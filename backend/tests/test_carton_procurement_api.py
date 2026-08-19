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
                "usage_quantity": "120",
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
    _ensure_dickie_customer(client)
    response = client.post("/api/carton-procurement/orders", json=_order_payload())
    assert response.status_code == 201, response.text
    return response.json()


def _ensure_dickie_customer(client) -> None:
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
                "customer_name": "未使用客户",
            },
        ).json()
        assert unused["customer_code"].startswith("CUST-")
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


def _history_workbook_bytes(
    rows: list[list[object]],
    *,
    units_per_carton_header: str = "每箱个数*",
) -> bytes:
    headers = [
        "历史订单号（选填）",
        "合同号*",
        "客户名称*",
        "货号*",
        "产品名称",
        "产品订单数量*",
        "下单日期*",
        "计划交期*",
        "订单备注",
        "纸品类型*",
        "纸质*",
        "规格*",
        "规格单位",
        units_per_carton_header,
        "纸品单位*",
        "单价",
        "币种",
        "价格来源",
        "明细备注",
        "纸箱数量（自动校验）",
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "历史订单导入"
    sheet.append(["纸箱历史订单导入模板"])
    sheet.append(["填写说明"])
    sheet.append(["分组规则"])
    sheet.append([])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _history_inventory_workbook_bytes(rows: list[list[object]]) -> bytes:
    headers = [
        "历史库存行号（选填）",
        "客户名称*",
        "纸箱订单号（选填）",
        "合同号/PO",
        "货号*",
        "纸品类型*",
        "纸质*",
        "规格*",
        "单位*",
        "期初库存数量*",
        "单价",
        "币种",
        "仓位",
        "盘点日期*",
        "来源单号",
        "备注",
        "库存金额（自动校验）",
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "历史库存导入"
    sheet.append(["纸箱历史库存导入模板"])
    sheet.append(["填写说明"])
    sheet.append(["入账规则"])
    sheet.append([])
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


def test_carton_quantity_divides_by_units_per_carton_and_rounds_up(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        payload = _order_payload()
        payload["contract_no"] = "SC700145366"
        payload["item_no"] = "203302045"
        payload["product_order_quantity"] = "3601"
        payload["lines"] = [payload["lines"][0]]

        response = client.post("/api/carton-procurement/orders", json=payload)

        assert response.status_code == 201, response.text
        line = response.json()["lines"][0]
        assert Decimal(line["usage_quantity"]) == Decimal("120.00000000")
        assert Decimal(line["required_quantity"]) == Decimal("31.0000")


def test_order_update_and_cancel_are_controlled_by_revision_and_business_activity(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)

        order = _create_order(client)
        update_payload = _order_payload()
        update_payload.update(
            {
                "expected_revision": order["revision"],
                "reason": "客户确认合同数量及交期需要修正",
                "contract_no": "SC700145365-R1",
                "product_order_quantity": "4800",
                "due_date": "2026-08-15",
                "note": "经纸箱部复核后修订",
            }
        )
        update_payload["lines"][0]["usage_quantity"] = "100"
        updated = client.patch(
            f"/api/carton-procurement/orders/{order['order_no']}",
            json=update_payload,
        )
        assert updated.status_code == 200, updated.text
        revised = updated.json()
        assert revised["revision"] == order["revision"] + 1
        assert revised["contract_no"] == "SC700145365-R1"
        assert revised["due_date"] == "2026-08-15"
        assert Decimal(revised["lines"][0]["required_quantity"]) == Decimal("48.0000")

        stale = client.patch(
            f"/api/carton-procurement/orders/{order['order_no']}",
            json={**update_payload, "reason": "使用旧版本再次提交"},
        )
        assert stale.status_code == 409
        assert "刷新" in stale.json()["detail"]

        cancelled = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/cancel",
            json={
                "factory_id": "huaxing",
                "expected_revision": revised["revision"],
                "reason": "客户正式通知取消该合同",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["revision"] == revised["revision"] + 1

        active_order = _create_order(client)
        receipt = _create_receipt(client, active_order)
        assert receipt["status"] == "PENDING_CONFIRMATION"

        schedule_update = _order_payload()
        schedule_update.update(
            {
                "expected_revision": active_order["revision"],
                "reason": "送货安排变化，更新计划交期",
                "due_date": "2026-08-16",
                "note": "已有待确认收料，仅调整交期",
            }
        )
        schedule_only = client.patch(
            f"/api/carton-procurement/orders/{active_order['order_no']}",
            json=schedule_update,
        )
        assert schedule_only.status_code == 200, schedule_only.text
        assert schedule_only.json()["due_date"] == "2026-08-16"

        structural_update = {
            **schedule_update,
            "expected_revision": schedule_only.json()["revision"],
            "reason": "尝试在已有收料后修改产品数量",
            "product_order_quantity": "7200",
        }
        blocked_update = client.patch(
            f"/api/carton-procurement/orders/{active_order['order_no']}",
            json=structural_update,
        )
        assert blocked_update.status_code == 409
        assert "只能修改计划交期和备注" in blocked_update.json()["detail"]

        blocked_cancel = client.post(
            f"/api/carton-procurement/orders/{active_order['order_no']}/cancel",
            json={
                "factory_id": "huaxing",
                "expected_revision": schedule_only.json()["revision"],
                "reason": "尝试取消已有收料业务的订单",
            },
        )
        assert blocked_cancel.status_code == 409
        assert "不能取消" in blocked_cancel.json()["detail"]


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
        assert sheet["E9"].value == "每箱个数"
        assert sheet["G9"].value == "纸箱数量"
        assert sheet["G10"].value == "=ROUNDUP(F10/E10,0)"
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


def test_manual_full_receipt_without_import_batch_completes_order(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        receipt_response = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN-MANUAL-260805-001",
                "delivery_date": "2026-08-05",
                "import_batch_id": None,
                "note": "仓管人工录入完整收料",
                "lines": [
                    {
                        "order_line_id": line["id"],
                        "delivered_quantity": line["required_quantity"],
                        "received_quantity": line["required_quantity"],
                        "damaged_quantity": "0",
                        "rejected_quantity": "0",
                        "unusable_quantity": "0",
                        "location": f"A-{index:02d}",
                        "feedback_note": "人工录入",
                    }
                    for index, line in enumerate(order["lines"], start=1)
                ],
            },
        )
        assert receipt_response.status_code == 201, receipt_response.text
        receipt = receipt_response.json()
        assert receipt["import_batch_id"] is None
        assert receipt["status"] == "PENDING_CONFIRMATION"

        confirmed = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "POSTED"

        refreshed_order = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["items"][0]
        assert refreshed_order["status"] == "COMPLETED"
        assert all(
            Decimal(line["remaining_quantity"]) == Decimal("0.0000")
            for line in refreshed_order["lines"]
        )
        movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()
        assert movements["total"] == len(order["lines"])


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
        assert closing["currency"] == "CNY"
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


def test_delivery_photo_uses_quality_and_specification_to_select_order_line(monkeypatch):
    with make_client(monkeypatch) as client:
        import app.services.carton_procurement_imports as imports

        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        monkeypatch.setattr(
            imports,
            "_parse_delivery_image_table",
            lambda _content: {
                "rows": [
                    {
                        "source_sheet": "OCR四列表格",
                        "source_row": 1,
                        "delivery_note_no": "DN26061301",
                        "delivery_date": "2026-06-13",
                        "order_reference": "SC700145365-203302044",
                        "contract_no": "SC700145365",
                        "item_no": "203302044",
                        "packaging_type": "普通箱",
                        "paper_quality": "A33+B",
                        "specification": "31.5 × 11.125 × 11.25 in",
                        "delivered_quantity": 10,
                        "unit_price": 0,
                        "location": "",
                    }
                ],
                "warnings": ["四列表格识别"],
                "engine": "rapidocr-delivery-table-v1",
                "document": {
                    "delivery_note_no": "DN26061301",
                    "delivery_date": "2026-06-13",
                    "raw_text_excerpt": "DN26061301",
                },
            },
        )

        response = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN26061301.jpg", b"delivery-photo", "image/jpeg")},
        )

        assert response.status_code == 201, response.text
        summary = response.json()["parse_summary"]
        assert summary["engine"] == "rapidocr-delivery-table-v1"
        assert summary["row_count"] == 1
        assert summary["matched_count"] == 1
        row = summary["rows"][0]
        assert row["match_status"] == "MATCHED"
        assert row["order_line_id"] == order["lines"][0]["id"]
        assert row["packaging_type"] == "外箱"
        assert row["paper_quality"] == "A33+B"
        assert row["specification"] == "31.5 × 11.125 × 11.25"
        assert "纸质" in row["match_basis"]
        assert "规格" in row["match_basis"]
        assert summary["document"]["delivery_note_no"] == "DN26061301"


def test_unmatched_delivery_import_can_be_deleted_with_derived_exceptions(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        content = _workbook_bytes(
            ["日期", "入库单号", "PO", "货号", "外箱", "纸质"],
            [["2026-08-05", "DN-UNMATCHED-001", "SC-NOT-ORDERED", "209999999", 5, "B3B内箱"]],
        )
        imported = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-UNMATCHED-001.xlsx", content)},
        )
        assert imported.status_code == 201, imported.text
        batch = imported.json()
        assert batch["parse_summary"]["matched_count"] == 0
        assert client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 1

        deleted = client.delete(
            f"/api/carton-procurement/receipt-imports/{batch['id']}",
            params={"factory_id": "huaxing"},
        )
        assert deleted.status_code == 204, deleted.text
        assert client.get(
            f"/api/carton-procurement/imports/{batch['id']}",
            params={"factory_id": "huaxing"},
        ).status_code == 404
        assert client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 0
        assert client.get(
            "/api/carton-procurement/receipt-imports/latest",
            params={"factory_id": "huaxing"},
        ).json() is None

        reimported = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-UNMATCHED-001.xlsx", content)},
        )
        assert reimported.status_code == 201, reimported.text
        assert reimported.json()["id"] != batch["id"]
        assert reimported.json()["duplicate"] is False


def test_matched_delivery_import_cannot_be_deleted(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _create_order(client)
        content = _workbook_bytes(
            ["日期", "入库单号", "PO", "货号", "外箱", "纸质"],
            [["2026-08-05", "DN-MATCHED-001", "SC700145365", "203302044", 10, "A33+B外箱"]],
        )
        imported = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-MATCHED-001.xlsx", content)},
        )
        assert imported.status_code == 201, imported.text
        batch = imported.json()
        assert batch["parse_summary"]["matched_count"] == 1

        blocked = client.delete(
            f"/api/carton-procurement/receipt-imports/{batch['id']}",
            params={"factory_id": "huaxing"},
        )
        assert blocked.status_code == 409
        assert "匹配正式订单" in blocked.json()["detail"]
        assert client.get(
            f"/api/carton-procurement/imports/{batch['id']}",
            params={"factory_id": "huaxing"},
        ).status_code == 200


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


def test_inspection_schedule_import_calculates_delivery_reminders_without_writing_inventory(monkeypatch):
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
            "/api/carton-procurement/inspection-imports",
            params={"factory_id": "huaxing", "advance_days": 3},
            files={"file": ("下周查货合同.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        summary = result["parse_summary"]
        assert result["import_type"] == "INSPECTION_SCHEDULE"
        assert result["import_profile"] == '{"advance_days":3}'
        assert summary["row_count"] == 2
        assert summary["matched_count"] == 1
        assert summary["reminder_count"] == 2
        assert summary["overdue_count"] == 0
        assert summary["due_soon_count"] == 0
        assert summary["creates_order"] is False
        assert summary["creates_inventory"] is False
        matched, missing = summary["rows"]
        assert matched["inspection_start_date"] == "2026-08-10"
        assert matched["required_delivery_date"] == "2026-08-07"
        assert matched["days_until_delivery"] == 2
        assert matched["reminder_status"] == "UPCOMING"
        assert missing["reminder_status"] == "MISSING_ORDER"

        exceptions = client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing"},
        ).json()
        assert {item["category"] for item in exceptions["items"]} == {
            "INSPECTION_DELIVERY_REMINDER",
            "INSPECTION_ORDER_MISSING",
        }
        assert all(item["owner_department"] == "纸箱部" for item in exceptions["items"])
        assert client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 1
        assert client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 0

        changed_profile = client.post(
            "/api/carton-procurement/inspection-imports",
            params={"factory_id": "huaxing", "advance_days": 5},
            files={"file": ("下周查货合同.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert changed_profile.status_code == 201, changed_profile.text
        assert changed_profile.json()["id"] != result["id"]
        assert changed_profile.json()["parse_summary"]["rows"][0]["reminder_status"] == "DUE_SOON"


def test_history_order_import_groups_lines_skips_duplicates_and_validates(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)

        common = [
            "HIST-2025-001",
            "SC700145365",
            "Dickie",
            "203302044",
            "产品示例",
            3600,
            "2025-08-05",
            "2025-08-12",
            "历史订单补录",
        ]
        content = _history_workbook_bytes(
            [
                [*common, "外箱", "A33+B", "31.5 × 11.125 × 11.25", "in", 120, "个", 3.46, "CNY", "历史合同", "", None],
                [*common, "内箱", "B3B", "15.5 × 10.625 × 5.25", "in", 30, "个", 0.96, "CNY", "历史合同", "", None],
                [*common, "滑板纸", "A9A", "30.75 × 10.5", "in", 1, "张", 0.96, "CNY", "历史合同", "", None],
                [*common, "卡纸", "250g 灰底白", "8.5 × 5.5", "in", 1, "张", 0.45, "CNY", "历史合同", "", None],
            ]
        )
        response = client.post(
            "/api/carton-procurement/orders/history-imports",
            params={"factory_id": "huaxing"},
            files={
                "file": (
                    "纸箱历史订单导入模板.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["row_count"] == 4
        assert result["group_count"] == 1
        assert result["imported_count"] == 1
        assert result["imported_line_count"] == 4
        assert result["imported_orders"] == ["HIST-2025-001"]

        orders = client.get(
            "/api/carton-procurement/orders", params={"factory_id": "huaxing"}
        ).json()
        assert orders["total"] == 1
        assert len(orders["items"][0]["lines"]) == 4
        assert Decimal(orders["items"][0]["lines"][0]["required_quantity"]) == Decimal("30.0000")

        duplicate = client.post(
            "/api/carton-procurement/orders/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("纸箱历史订单导入模板.xlsx", content)},
        )
        assert duplicate.status_code == 201, duplicate.text
        assert duplicate.json()["imported_count"] == 0
        assert duplicate.json()["skipped_count"] == 1
        assert client.get(
            "/api/carton-procurement/orders", params={"factory_id": "huaxing"}
        ).json()["total"] == 1

        legacy_common = list(common)
        legacy_common[0] = "HIST-2025-LEGACY"
        legacy_common[1] = "SC700145367"
        legacy_common[2] = "Dickie"
        legacy_content = _history_workbook_bytes(
            [[
                *legacy_common,
                "外箱",
                "A33+B",
                "31.5 × 11.125 × 11.25",
                "in",
                1 / 120,
                "个",
                3.46,
                "CNY",
                "历史合同",
                "",
                None,
            ]],
            units_per_carton_header="单件用量*",
        )
        legacy = client.post(
            "/api/carton-procurement/orders/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("旧版纸箱历史订单.xlsx", legacy_content)},
        )
        assert legacy.status_code == 201, legacy.text
        assert any("自动换算" in warning for warning in legacy.json()["warnings"])
        imported_orders = client.get(
            "/api/carton-procurement/orders", params={"factory_id": "huaxing"}
        ).json()["items"]
        legacy_order = next(
            order for order in imported_orders if order["order_no"] == "HIST-2025-LEGACY"
        )
        assert Decimal(legacy_order["lines"][0]["usage_quantity"]) == Decimal("120")
        assert Decimal(legacy_order["lines"][0]["required_quantity"]) == Decimal("30.0000")

        first_conflict = list(common)
        second_conflict = list(common)
        first_conflict[0] = second_conflict[0] = "HIST-2025-002"
        first_conflict[1] = second_conflict[1] = "SC700145366"
        first_conflict[5] = 3600
        second_conflict[5] = 7200
        conflicting_rows = [
            [*first_conflict, "外箱", "A33+B", "31 × 11 × 11", "in", 1, "个", 1, "CNY", "历史合同", "", None],
            [*second_conflict, "内箱", "B3B", "15 × 10 × 5", "in", 1, "个", 1, "CNY", "历史合同", "", None],
        ]
        invalid = client.post(
            "/api/carton-procurement/orders/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("纸箱历史订单导入模板.xlsx", _history_workbook_bytes(conflicting_rows))},
        )
        assert invalid.status_code == 422
        assert "主信息不一致" in invalid.json()["detail"]


def test_history_inventory_import_is_idempotent_and_supports_standalone_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        content = _history_inventory_workbook_bytes(
            [
                [
                    "HSTOCK-2025-001",
                    "Dickie",
                    order["order_no"],
                    order["contract_no"],
                    order["item_no"],
                    "外箱",
                    "A33+B",
                    "31.5 × 11.125 × 11.25",
                    "个",
                    30,
                    3.46,
                    "CNY",
                    "纸箱仓 A-01",
                    "2025-08-05",
                    "STOCKTAKE-20250805",
                    "系统上线前盘点",
                    None,
                ],
                [
                    "HSTOCK-2025-002",
                    "Dickie",
                    "",
                    "",
                    "209999999",
                    "卡纸",
                    "250g 灰底白",
                    "8.5 × 5.5",
                    "张",
                    100,
                    0.45,
                    "CNY",
                    "纸箱仓 B-02",
                    "2025-08-05",
                    "STOCKTAKE-20250805",
                    "未找到旧订单，保留独立库存",
                    None,
                ],
            ]
        )
        first = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("纸箱历史库存导入模板.xlsx", content)},
        )
        assert first.status_code == 201, first.text
        result = first.json()
        assert result["row_count"] == 2
        assert result["imported_count"] == 2
        assert result["matched_order_line_count"] == 1
        assert result["standalone_count"] == 1
        assert Decimal(result["total_quantity"]) == Decimal("130.0000")
        assert result["duplicate"] is False

        movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()
        assert movements["total"] == 2
        assert {item["source_type"] for item in movements["items"]} == {"HISTORY_INVENTORY"}
        assert {item["movement_type"] for item in movements["items"]} == {"ADJUSTMENT"}
        assert sum(item["order_line_id"] is None for item in movements["items"]) == 1

        duplicate = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("纸箱历史库存导入模板.xlsx", content)},
        )
        assert duplicate.status_code == 201, duplicate.text
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["imported_count"] == 0
        assert duplicate.json()["skipped_count"] == 2
        assert client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()["total"] == 2

        invalid = _history_inventory_workbook_bytes(
            [["BAD-1", "Dickie", "", "", "203302044", "外箱", "A33+B", "31 × 11 × 11", "个", 0, 1, "CNY", "A-01", "2025-08-05", "", "", None]]
        )
        rejected = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("invalid.xlsx", invalid)},
        )
        assert rejected.status_code == 422
        assert "必须大于 0" in rejected.json()["detail"]

        unknown_customer = _history_inventory_workbook_bytes(
            [["BAD-2", "不存在的客户", "", "", "203302044", "外箱", "A33+B", "31 × 11 × 11", "个", 1, 1, "CNY", "A-01", "2025-08-05", "", "", None]]
        )
        unknown = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("unknown-customer.xlsx", unknown_customer)},
        )
        assert unknown.status_code == 422
        assert "客户名称“不存在的客户”不存在或未启用" in unknown.json()["detail"]


def test_month_end_closings_are_separated_by_inventory_currency(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        content = _history_inventory_workbook_bytes(
            [
                [
                    "HSTOCK-HKD-001",
                    "Dickie",
                    "",
                    "HK-HIST-001",
                    "2033HKD01",
                    "外箱",
                    "A33+B",
                    "31 × 11 × 11",
                    "个",
                    10,
                    2,
                    "港币",
                    "A-01",
                    "2026-08-05",
                    "STOCKTAKE-HKD",
                    "港币期初库存",
                    None,
                ],
                [
                    "HSTOCK-CNY-001",
                    "Dickie",
                    "",
                    "CN-HIST-001",
                    "2033CNY01",
                    "内箱",
                    "B3B",
                    "15 × 10 × 5",
                    "个",
                    5,
                    3,
                    "人民币",
                    "A-02",
                    "2026-08-05",
                    "STOCKTAKE-CNY",
                    "人民币期初库存",
                    None,
                ],
            ]
        )
        imported = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("纸箱历史库存多币种.xlsx", content)},
        )
        assert imported.status_code == 201, imported.text

        generated = client.post(
            "/api/carton-procurement/closings/generate",
            json={
                "factory_id": "huaxing",
                "period": "2026-08",
                "customer_code": "DICKIE",
            },
        )
        assert generated.status_code == 200, generated.text
        by_currency = {row["currency"]: row for row in generated.json()}

        assert set(by_currency) == {"CNY", "HKD"}
        assert Decimal(by_currency["HKD"]["ending_quantity"]) == Decimal("10.0000")
        assert Decimal(by_currency["HKD"]["ending_amount"]) == Decimal("20.0000")
        assert Decimal(by_currency["CNY"]["ending_quantity"]) == Decimal("5.0000")
        assert Decimal(by_currency["CNY"]["ending_amount"]) == Decimal("15.0000")


def test_standalone_history_inventory_supports_outbound_adjustment_and_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        content = _history_inventory_workbook_bytes(
            [[
                "HSTOCK-OPERABLE-001",
                "Dickie",
                "",
                "",
                "209999999",
                "卡纸",
                "250g 灰底白",
                "8.5 × 5.5",
                "张",
                100,
                0.45,
                "CNY",
                "纸箱仓 B-02",
                "2025-08-05",
                "STOCKTAKE-OPERABLE",
                "独立旧库存",
                None,
            ]]
        )
        imported = client.post(
            "/api/carton-procurement/inventory/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("独立历史库存.xlsx", content)},
        )
        assert imported.status_code == 201, imported.text

        balance = client.get(
            "/api/carton-procurement/inventory/balances",
            params={"factory_id": "huaxing"},
        ).json()[0]
        assert balance["order_line_id"] is None
        assert balance["latest_movement_id"]

        outbound = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "factory_id": "huaxing",
                "order_line_id": None,
                "reference_movement_id": balance["latest_movement_id"],
                "movement_type": "OUTBOUND",
                "quantity": "40",
                "location": "纸箱仓 B-02",
                "document_no": "OUT-HISTORY-001",
                "reason": "历史库存生产领料",
            },
        )
        assert outbound.status_code == 201, outbound.text
        assert Decimal(outbound.json()["balance"]) == Decimal("60.0000")

        negative = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "factory_id": "huaxing",
                "reference_movement_id": outbound.json()["id"],
                "movement_type": "ADJUSTMENT",
                "quantity": "-61",
                "document_no": "ADJ-HISTORY-001",
                "reason": "错误盘亏",
            },
        )
        assert negative.status_code == 409
        assert "不能小于 0" in negative.json()["detail"]

        reversed_movement = client.post(
            f"/api/carton-procurement/inventory/movements/{outbound.json()['id']}/reverse",
            json={"factory_id": "huaxing", "reason": "领料单作废"},
        )
        assert reversed_movement.status_code == 201, reversed_movement.text
        assert Decimal(reversed_movement.json()["balance"]) == Decimal("100.0000")


def test_import_batch_history_is_persisted_and_filterable(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _create_order(client)
        content = _workbook_bytes(
            ["Reference", "PO.NO", "客户", "货号", "产品名称", "数量", "装箱", "验货期"],
            [["SC700145365", "PO-001", "Dickie", "203302044", "多文盒", 3600, "1/120", "8月10日-8月13日"]],
        )
        weekly = client.post(
            "/api/carton-procurement/weekly-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("本周排期.xlsx", content)},
        )
        inspection = client.post(
            "/api/carton-procurement/inspection-imports",
            params={"factory_id": "huaxing", "advance_days": 3},
            files={"file": ("下周查货.xlsx", content)},
        )
        assert weekly.status_code == 201, weekly.text
        assert inspection.status_code == 201, inspection.text

        weekly_history = client.get(
            "/api/carton-procurement/imports",
            params={"factory_id": "huaxing", "import_type": "WEEKLY_SCHEDULE"},
        )
        assert weekly_history.status_code == 200, weekly_history.text
        assert weekly_history.json()["total"] == 1
        assert weekly_history.json()["items"][0]["id"] == weekly.json()["id"]
        assert weekly_history.json()["items"][0]["parse_summary"]["row_count"] == 1

        all_history = client.get(
            "/api/carton-procurement/imports",
            params={"factory_id": "huaxing"},
        )
        assert all_history.status_code == 200
        assert all_history.json()["total"] == 2

        invalid = client.get(
            "/api/carton-procurement/imports",
            params={"factory_id": "huaxing", "import_type": "UNKNOWN"},
        )
        assert invalid.status_code == 422


def test_receipt_history_can_be_searched_after_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        receipt = _create_receipt(client, order)
        confirmed = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text

        history = client.get(
            "/api/carton-procurement/receipts",
            params={"factory_id": "huaxing", "search": order["contract_no"]},
        )
        assert history.status_code == 200, history.text
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["status"] == "POSTED"
        assert history.json()["items"][0]["lines"][0]["contract_no"] == order["contract_no"]
