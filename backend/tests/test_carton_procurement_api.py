from uuid import uuid4
import json
import os
import sqlite3
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
        "status": "CONFIRMED",
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


def _submit_order(client, order: dict[str, object]) -> dict[str, object]:
    response = client.post(
        f"/api/carton-procurement/orders/{order['order_no']}/submit-supplier",
        json={
            "factory_id": "huaxing",
            "expected_revision": order["revision"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_order(client, *, submit_supplier: bool = True) -> dict[str, object]:
    _ensure_dickie_customer(client)
    response = client.post("/api/carton-procurement/orders", json=_order_payload())
    assert response.status_code == 201, response.text
    order = response.json()
    return _submit_order(client, order) if submit_supplier else order


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
        # Warehouse staff select pre-maintained bins; receiving no longer creates
        # arbitrary master data as a side effect of a free-text label.
        for bin_code in ["纸箱仓 A-01", "纸箱仓 A-03", "纸箱仓 B-01", "纸箱仓 B-02", "打板区 S-01", "A-00", "A-01", "A-02", "B-02", "C-03"]:
            location = client.post("/api/carton-procurement/inventory/locations",
                json={"factory_id": "huaxing", "warehouse": "默认仓", "bin_code": bin_code})
            assert location.status_code == 201, location.text
        login_as(client, "warehouse_keeper")


def test_customer_master_crud_permission_and_order_snapshot(monkeypatch):
    with make_client(monkeypatch) as client:
        warehouse_profile = login_as(client, "warehouse_keeper")
        assert "carton_procurement:customer_manage" not in warehouse_profile["permissions"]
        forbidden = client.post(
            "/api/carton-procurement/customers",
            json={
                "factory_id": "huaxing",
                "customer_code": "WAREHOUSE-CUSTOMER",
                "customer_name": "Dickie",
            },
        )
        assert forbidden.status_code == 201

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


def test_customer_due_date_drives_server_plan_and_preserves_legacy_orders(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)

        planned_payload = _order_payload()
        planned_payload.update(
            {
                "contract_no": "SC-CUSTOMER-DUE",
                "item_no": "ITEM-CUSTOMER-DUE",
                "customer_due_date": "2026-08-20",
                "due_date": "2026-12-31",
            }
        )
        planned_response = client.post(
            "/api/carton-procurement/orders",
            json=planned_payload,
        )
        assert planned_response.status_code == 201, planned_response.text
        planned_order = planned_response.json()
        assert planned_order["customer_due_date"] == "2026-08-20"
        assert planned_order["safety_lead_days"] == 3
        assert planned_order["due_date"] == "2026-08-17"

        urgent_payload = _order_payload()
        urgent_payload.update(
            {
                "contract_no": "SC-URGENT-DUE",
                "item_no": "ITEM-URGENT-DUE",
                "customer_due_date": "2026-08-06",
                "due_date": "2026-12-31",
            }
        )
        urgent_response = client.post(
            "/api/carton-procurement/orders",
            json=urgent_payload,
        )
        assert urgent_response.status_code == 201, urgent_response.text
        assert urgent_response.json()["due_date"] == "2026-08-05"

        invalid_payload = _order_payload()
        invalid_payload.update(
            {
                "contract_no": "SC-INVALID-DUE",
                "item_no": "ITEM-INVALID-DUE",
                "customer_due_date": "2026-08-04",
            }
        )
        invalid_response = client.post(
            "/api/carton-procurement/orders",
            json=invalid_payload,
        )
        assert invalid_response.status_code == 422
        assert "客户交期不能早于下单日期" in invalid_response.text

        legacy_payload = _order_payload()
        legacy_payload.update(
            {
                "contract_no": "SC-LEGACY-DUE",
                "item_no": "ITEM-LEGACY-DUE",
            }
        )
        legacy_response = client.post(
            "/api/carton-procurement/orders",
            json=legacy_payload,
        )
        assert legacy_response.status_code == 201, legacy_response.text
        legacy_order = legacy_response.json()
        assert legacy_order["customer_due_date"] is None
        assert legacy_order["due_date"] == "2026-08-12"


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

        order = _create_order(client, submit_supplier=False)
        assert order["status"] == "CONFIRMED"
        assert order["customer_code"] == "DICKIE"
        assert len(order["lines"]) == 2
        assert order["lines"][0]["packaging_type"] == "外箱"
        assert order["lines"][0]["paper_quality"] == "A33+B"
        assert order["lines"][0]["specification"] == "31.5 × 11.125 × 11.25"
        assert Decimal(order["lines"][0]["required_quantity"]) == Decimal("30.0000")
        assert Decimal(order["lines"][1]["required_quantity"]) == Decimal("3600.0000")

        timeline = client.get("/api/carton-procurement/inventory/order-timeline",
                              params={"factory_id": "huaxing", "order_id": order["id"]})
        assert timeline.status_code == 200, timeline.text
        created_event = next(row for row in timeline.json()["events"] if row["event_type"] == "ORDER_CREATED")
        assert Decimal(created_event["quantity_change"]) == Decimal("3600")
        assert created_event["quantity_before"] == "0"
        assert created_event["quantity_basis"] == "ORDER_PRODUCT"
        assert created_event["contract_no"] == order["contract_no"]

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


def test_supplier_submission_transition_is_audited_and_required_before_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client, submit_supplier=False)

        blocked_receipt = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN-BEFORE-SUBMIT",
                "delivery_date": "2026-08-05",
                "lines": [{
                    "order_line_id": order["lines"][0]["id"],
                    "delivered_quantity": "10",
                    "received_quantity": "10",
                }],
            },
        )
        assert blocked_receipt.status_code == 409, blocked_receipt.text
        assert "必须先确认并锁定" in blocked_receipt.json()["detail"]

        submitted = _submit_order(client, order)
        assert submitted["status"] == "PENDING_SUPPLIER"
        assert submitted["revision"] == order["revision"] + 1

        duplicate_submit = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/submit-supplier",
            json={"factory_id": "huaxing", "expected_revision": submitted["revision"]},
        )
        assert duplicate_submit.status_code == 409
        assert "已经确认并锁定" in duplicate_submit.json()["detail"]

        blocked_append = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "additional_quantity": "600",
                "reason": "提交后尝试追加订单数量",
            },
        )
        assert blocked_append.status_code == 403
        blocked_cancel = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/cancel",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "reason": "确认锁定后尝试取消订单",
            },
        )
        assert blocked_cancel.status_code == 409
        assert "不能取消" in blocked_cancel.json()["detail"]
        blocked_return = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/return",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "reason": "提交未入库时尝试绕过取消锁定",
            },
        )
        assert blocked_return.status_code == 409
        assert "已确认锁定但未入库的订单不可取消" in blocked_return.json()["detail"]

        receipt = _create_receipt(client, submitted)
        assert receipt["status"] == "PENDING_CONFIRMATION"
        database_path = os.environ["DATABASE_URL"].removeprefix("sqlite:///")
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE carton_orders SET status = 'CONFIRMED' WHERE id = ?",
                (submitted["id"],),
            )
            connection.commit()
        blocked_confirmation = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert blocked_confirmation.status_code == 409, blocked_confirmation.text
        assert "不能确认入库" in blocked_confirmation.json()["detail"]
        movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        )
        assert movements.status_code == 200
        assert movements.json()["total"] == 0

        audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_SUBMITTED_SUPPLIER"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] == 1
        submitted_event = audit.json()["items"][0]
        assert submitted_event["detail"]["status"] == "PENDING_SUPPLIER"
        assert submitted_event["detail"]["order_no"] == order["order_no"]
        assert submitted_event["actor_name"]
        assert submitted_event["created_at"].startswith("2026-08-05")

        actor_filtered = client.get(
            "/api/carton-procurement/audit-events",
            params={
                "factory_id": "huaxing",
                "event_type": "ORDER_SUBMITTED_SUPPLIER",
                "actor_user_id": submitted_event["actor_user_id"],
                "date_from": "2026-08-05",
                "date_to": "2026-08-05",
            },
        )
        assert actor_filtered.status_code == 200, actor_filtered.text
        assert actor_filtered.json()["total"] == 1


def test_bulk_supplier_submission_submits_pending_orders_and_skips_other_statuses(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        pending = _create_order(client, submit_supplier=False)
        already_submitted = _submit_order(client, _create_order(client, submit_supplier=False))

        response = client.post(
            "/api/carton-procurement/orders/bulk-submit-supplier",
            json={
                "factory_id": "huaxing",
                "items": [
                    {"order_no": pending["order_no"], "expected_revision": pending["revision"]},
                    {
                        "order_no": already_submitted["order_no"],
                        "expected_revision": already_submitted["revision"],
                    },
                ],
            },
        )

        assert response.status_code == 200, response.text
        submitted = response.json()
        assert len(submitted) == 1
        assert submitted[0]["order_no"] == pending["order_no"]
        assert submitted[0]["status"] == "PENDING_SUPPLIER"
        assert submitted[0]["revision"] == pending["revision"] + 1

        atomic_first = _create_order(client, submit_supplier=False)
        atomic_stale = _create_order(client, submit_supplier=False)
        conflict = client.post(
            "/api/carton-procurement/orders/bulk-submit-supplier",
            json={
                "factory_id": "huaxing",
                "items": [
                    {
                        "order_no": atomic_first["order_no"],
                        "expected_revision": atomic_first["revision"],
                    },
                    {
                        "order_no": atomic_stale["order_no"],
                        "expected_revision": atomic_stale["revision"] + 1,
                    },
                ],
            },
        )
        assert conflict.status_code == 409, conflict.text
        listed = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing", "limit": 200},
        )
        assert listed.status_code == 200, listed.text
        statuses = {item["order_no"]: item["status"] for item in listed.json()["items"]}
        assert statuses[atomic_first["order_no"]] == "CONFIRMED"
        assert statuses[atomic_stale["order_no"]] == "CONFIRMED"

        audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_SUBMITTED_SUPPLIER"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] == 2
        bulk_event = next(
            item for item in audit.json()["items"] if item["detail"]["order_no"] == pending["order_no"]
        )
        assert bulk_event["detail"]["bulk"] is True


def test_supervisor_adjusts_submitted_order_and_protects_pending_receipt_quantities(monkeypatch):
    with make_client(monkeypatch) as client:
        warehouse_profile = login_as(client, "warehouse_keeper")
        assert "carton_procurement:order_adjust" not in warehouse_profile["permissions"]
        _freeze_carton_time(monkeypatch)
        submitted = _create_order(client)

        denied_append = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "additional_quantity": "600",
                "reason": "普通仓管尝试调整已提交订单",
            },
        )
        assert denied_append.status_code == 403, denied_append.text
        denied_reduce = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "reduction_quantity": "600",
                "reason": "普通仓管尝试减少已提交订单",
            },
        )
        assert denied_reduce.status_code == 403, denied_reduce.text

        manager_profile = login_as(client, "carton_supervisor")
        assert "carton_procurement:order_adjust" in manager_profile["permissions"]
        appended_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "additional_quantity": "600",
                "reason": "客户确认追加六百套产品",
            },
        )
        assert appended_response.status_code == 200, appended_response.text
        appended = appended_response.json()
        assert appended["status"] == "PENDING_SUPPLIER"
        assert Decimal(appended["product_order_quantity"]) == Decimal("4200")
        assert Decimal(appended["lines"][0]["required_quantity"]) == Decimal("35")

        reduced_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended["revision"],
                "reduction_quantity": "600",
                "reason": "客户确认减少六百套产品",
            },
        )
        assert reduced_response.status_code == 200, reduced_response.text
        reduced = reduced_response.json()
        assert reduced["status"] == "PENDING_SUPPLIER"
        assert Decimal(reduced["product_order_quantity"]) == Decimal("3600")
        assert Decimal(reduced["lines"][0]["required_quantity"]) == Decimal("30")

        returned_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": reduced["revision"],
                "reduction_quantity": "3600",
                "reason": "客户确认整张订单全部退单",
            },
        )
        assert returned_response.status_code == 200, returned_response.text
        returned = returned_response.json()
        assert returned["status"] == "CANCELLED"
        # A full return closes the operational balance at zero while retaining
        # the original contracted quantities on the cancelled order as history.
        assert Decimal(returned["product_order_quantity"]) == Decimal("3600")
        assert Decimal(returned["lines"][0]["required_quantity"]) == Decimal("30")

        login_as(client, "warehouse_keeper")
        receipt_order = _create_order(client)
        pending_receipt = _create_receipt(client, receipt_order)
        assert pending_receipt["status"] == "PENDING_CONFIRMATION"
        login_as(client, "carton_supervisor")
        reduced_around_pending = client.post(
            f"/api/carton-procurement/orders/{receipt_order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": receipt_order["revision"],
                "reduction_quantity": "100",
                "reason": "保留待确认数量后减少未收料部分",
            },
        )
        assert reduced_around_pending.status_code == 200, reduced_around_pending.text
        pending_adjusted = reduced_around_pending.json()
        assert pending_adjusted["status"] == "PENDING_SUPPLIER"
        assert Decimal(pending_adjusted["product_order_quantity"]) == Decimal("3500")

        blocked_below_pending = client.post(
            f"/api/carton-procurement/orders/{receipt_order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": pending_adjusted["revision"],
                "reduction_quantity": "2540",
                "reason": "尝试减到低于待确认收料数量",
            },
        )
        assert blocked_below_pending.status_code == 409, blocked_below_pending.text
        assert "超过尚未入库的可退范围" in blocked_below_pending.json()["detail"]

        audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_REDUCED"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] == 3
        assert {item["detail"]["full_return"] for item in audit.json()["items"]} == {False, True}
        full_return_event = next(
            item for item in audit.json()["items"] if item["detail"]["full_return"]
        )
        assert Decimal(full_return_event["detail"]["after_quantity"]) == 0
        assert all(
            Decimal(value) == 0
            for value in full_return_event["detail"]["after_required"].values()
        )


def test_supervisor_can_append_and_reduce_unreceived_balance_after_partial_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        partial_receipt = _create_receipt(client, order)
        confirmed = client.post(
            f"/api/carton-procurement/receipts/{partial_receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": partial_receipt["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text

        partially_received = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["items"][0]
        assert partially_received["status"] == "PARTIALLY_RECEIVED"

        denied_append = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": partially_received["revision"],
                "additional_quantity": "600",
                "reason": "普通仓管尝试在入库后追加",
            },
        )
        assert denied_append.status_code == 403, denied_append.text

        login_as(client, "carton_supervisor")
        appended_partial_response = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": partially_received["revision"],
                "additional_quantity": "600",
                "reason": "部分到货后客户追加六百套",
            },
        )
        assert appended_partial_response.status_code == 200, appended_partial_response.text
        appended_partial = appended_partial_response.json()
        assert appended_partial["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(appended_partial["product_order_quantity"]) == Decimal("4200")
        assert Decimal(appended_partial["lines"][0]["required_quantity"]) == Decimal("35")
        assert Decimal(appended_partial["lines"][0]["received_quantity"]) == Decimal("9")
        assert Decimal(appended_partial["lines"][0]["remaining_quantity"]) == Decimal("26")

        reduced_partial_response = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended_partial["revision"],
                "reduction_quantity": "100",
                "reason": "部分到货后减少未入库数量",
            },
        )
        assert reduced_partial_response.status_code == 200, reduced_partial_response.text
        reduced_partial = reduced_partial_response.json()
        assert reduced_partial["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(reduced_partial["product_order_quantity"]) == Decimal("4100")
        assert Decimal(reduced_partial["lines"][0]["received_quantity"]) == Decimal("9")

        login_as(client, "warehouse_keeper")
        completion_receipt_response = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN26080502",
                "delivery_date": "2026-08-05",
                "note": "补齐追加前后的待入库数量",
                "lines": [
                    {
                        "order_line_id": reduced_partial["lines"][0]["id"],
                        "delivered_quantity": "26",
                        "received_quantity": "26",
                        "damaged_quantity": "0",
                        "rejected_quantity": "0",
                        "unusable_quantity": "0",
                        "location": "纸箱仓 A-03",
                        "feedback_note": "数量核对无误",
                    },
                    {
                        "order_line_id": reduced_partial["lines"][1]["id"],
                        "delivered_quantity": "4100",
                        "received_quantity": "4100",
                        "damaged_quantity": "0",
                        "rejected_quantity": "0",
                        "unusable_quantity": "0",
                        "location": "纸箱仓 B-01",
                        "feedback_note": "数量核对无误",
                    }
                ],
            },
        )
        assert completion_receipt_response.status_code == 201, completion_receipt_response.text
        completion_receipt = completion_receipt_response.json()
        completion_confirmed = client.post(
            f"/api/carton-procurement/receipts/{completion_receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": completion_receipt["revision"]},
        )
        assert completion_confirmed.status_code == 200, completion_confirmed.text

        completed = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["items"][0]
        assert completed["status"] == "COMPLETED"

        login_as(client, "carton_supervisor")
        appended_completed_response = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": completed["revision"],
                "additional_quantity": "600",
                "reason": "全部到货后客户再次追加六百套",
            },
        )
        assert appended_completed_response.status_code == 200, appended_completed_response.text
        reopened = appended_completed_response.json()
        assert reopened["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(reopened["product_order_quantity"]) == Decimal("4700")
        assert Decimal(reopened["lines"][0]["required_quantity"]) == Decimal("40")
        assert Decimal(reopened["lines"][0]["received_quantity"]) == Decimal("35")
        assert Decimal(reopened["lines"][0]["remaining_quantity"]) == Decimal("5")

        blocked_below_received = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": reopened["revision"],
                "reduction_quantity": "601",
                "reason": "尝试减少超过尚未入库的数量",
            },
        )
        assert blocked_below_received.status_code == 409, blocked_below_received.text
        assert "超过尚未入库的可退范围" in blocked_below_received.json()["detail"]

        close_balance_response = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": reopened["revision"],
                "reduction_quantity": "600",
                "reason": "退掉全部尚未入库的追加数量",
            },
        )
        assert close_balance_response.status_code == 200, close_balance_response.text
        closed_again = close_balance_response.json()
        assert closed_again["status"] == "COMPLETED"
        assert Decimal(closed_again["product_order_quantity"]) == Decimal("4100")
        assert all(Decimal(line["remaining_quantity"]) == 0 for line in closed_again["lines"])

        blocked_completed_reduce = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": closed_again["revision"],
                "reduction_quantity": "1",
                "reason": "全部到货后尝试继续减单",
            },
        )
        assert blocked_completed_reduce.status_code == 409, blocked_completed_reduce.text

        audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_APPENDED"},
        )
        assert audit.status_code == 200, audit.text
        reopened_event = next(
            item for item in audit.json()["items"]
            if item["detail"]["previous_status"] == "COMPLETED"
        )
        assert reopened_event["detail"]["status"] == "PARTIALLY_RECEIVED"


def test_completed_order_append_locks_exact_completed_product_baseline(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)

        payload = _order_payload()
        payload["product_order_quantity"] = "2100"
        payload["lines"] = [payload["lines"][0]]
        created_response = client.post("/api/carton-procurement/orders", json=payload)
        assert created_response.status_code == 201, created_response.text
        submitted = _submit_order(client, created_response.json())
        assert Decimal(submitted["lines"][0]["required_quantity"]) == Decimal("18")

        receipt_response = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN260805-ROUNDING",
                "delivery_date": "2026-08-05",
                "lines": [
                    {
                        "order_line_id": submitted["lines"][0]["id"],
                        "delivered_quantity": "18",
                        "received_quantity": "18",
                        "damaged_quantity": "0",
                        "rejected_quantity": "0",
                        "unusable_quantity": "0",
                        "location": "纸箱仓 A-03",
                    }
                ],
            },
        )
        assert receipt_response.status_code == 201, receipt_response.text
        receipt = receipt_response.json()
        confirmed_response = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert confirmed_response.status_code == 200, confirmed_response.text

        completed = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing"},
        ).json()["items"][0]
        assert completed["status"] == "COMPLETED"
        assert Decimal(completed["maximum_reducible_quantity"]) == 0

        login_as(client, "carton_supervisor")
        appended_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": completed["revision"],
                "additional_quantity": "1000",
            },
        )
        assert appended_response.status_code == 200, appended_response.text
        appended = appended_response.json()
        assert Decimal(appended["product_order_quantity"]) == Decimal("3100")
        assert Decimal(appended["maximum_reducible_quantity"]) == Decimal("1000")

        blocked_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended["revision"],
                "reduction_quantity": "1059",
                "reason": "",
            },
        )
        assert blocked_response.status_code == 409, blocked_response.text
        assert "当前最大可减 1000" in blocked_response.json()["detail"]

        reduced_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended["revision"],
                "reduction_quantity": "1000",
            },
        )
        assert reduced_response.status_code == 200, reduced_response.text
        reduced = reduced_response.json()
        assert reduced["status"] == "COMPLETED"
        assert Decimal(reduced["product_order_quantity"]) == Decimal("2100")

        audit_response = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing"},
        )
        assert audit_response.status_code == 200, audit_response.text
        events = audit_response.json()["items"]
        append_event = next(item for item in events if item["event_type"] == "ORDER_APPENDED")
        reduce_event = next(item for item in events if item["event_type"] == "ORDER_REDUCED")
        assert append_event["detail"]["reason"] == "客人追加订单"
        assert reduce_event["detail"]["reason"] == "客人退单"


def test_order_update_and_cancel_are_controlled_by_supplier_submission(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)

        order = _create_order(client, submit_supplier=False)
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
        updated_structure = client.patch(
            f"/api/carton-procurement/orders/{order['order_no']}",
            json=update_payload,
        )
        assert updated_structure.status_code == 200, updated_structure.text
        order = updated_structure.json()
        assert order["contract_no"] == "SC700145365-R1"
        assert Decimal(order["lines"][0]["required_quantity"]) == Decimal("48.0000")

        schedule_payload = _order_payload()
        schedule_payload.update(
            {
                "expected_revision": order["revision"],
                "reason": "供应商排期变化，更新计划交期",
                "due_date": "2026-08-15",
                "note": "仅调整交期和备注",
            }
        )
        updated = client.patch(
            f"/api/carton-procurement/orders/{order['order_no']}",
            json=schedule_payload,
        )
        assert updated.status_code == 200, updated.text
        revised = updated.json()
        assert revised["revision"] == order["revision"] + 1
        assert revised["contract_no"] == "SC700145365"
        assert revised["due_date"] == "2026-08-15"
        assert Decimal(revised["lines"][0]["required_quantity"]) == Decimal("30.0000")

        update_audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_UPDATED"},
        )
        assert update_audit.status_code == 200, update_audit.text
        assert update_audit.json()["total"] == 2
        assert all(item["detail"]["order_no"] == order["order_no"] for item in update_audit.json()["items"])
        assert all(item["actor_name"] for item in update_audit.json()["items"])

        stale = client.patch(
            f"/api/carton-procurement/orders/{order['order_no']}",
            json={**schedule_payload, "reason": "使用旧版本再次提交"},
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
        assert schedule_only.status_code == 409, schedule_only.text
        assert "已确认并锁定" in schedule_only.json()["detail"]

        structural_update = {
            **schedule_update,
            "expected_revision": active_order["revision"],
            "reason": "尝试在已有收料后修改产品数量",
            "product_order_quantity": "7200",
        }
        blocked_update = client.patch(
            f"/api/carton-procurement/orders/{active_order['order_no']}",
            json=structural_update,
        )
        assert blocked_update.status_code == 409
        assert "已确认并锁定" in blocked_update.json()["detail"]

        blocked_cancel = client.post(
            f"/api/carton-procurement/orders/{active_order['order_no']}/cancel",
            json={
                "factory_id": "huaxing",
                "expected_revision": active_order["revision"],
                "reason": "尝试取消已有收料业务的订单",
            },
        )
        assert blocked_cancel.status_code == 409
        assert "不能取消" in blocked_cancel.json()["detail"]


def test_order_append_bulk_cancel_export_filters_and_audit(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)

        order = _create_order(client, submit_supplier=False)
        appended = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": order["revision"],
                "additional_quantity": "600",
                "reason": "客户正式追加六百套产品",
                "customer_due_date": "2026-08-18",
                "due_date": "2026-12-31",
            },
        )
        assert appended.status_code == 200, appended.text
        appended_order = appended.json()
        assert Decimal(appended_order["product_order_quantity"]) == Decimal("4200.000000")
        assert Decimal(appended_order["lines"][0]["required_quantity"]) == Decimal("35.0000")
        assert appended_order["customer_due_date"] == "2026-08-18"
        assert appended_order["safety_lead_days"] == 3
        assert appended_order["due_date"] == "2026-08-15"

        reminders = client.get(
            "/api/carton-procurement/exceptions",
            params={"factory_id": "huaxing", "search": "追加订单"},
        )
        assert reminders.status_code == 200, reminders.text
        assert any(item["category"] == "ORDER_APPENDED" for item in reminders.json()["items"])

        audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_APPENDED"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] == 1
        assert audit.json()["items"][0]["detail"]["reason"] == "客户正式追加六百套产品"
        assert audit.json()["items"][0]["detail"]["order_no"] == order["order_no"]
        assert audit.json()["items"][0]["actor_name"]

        returned = client.post(
            f"/api/carton-procurement/orders/{order['order_no']}/cancel",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended_order["revision"],
                "reason": "客户取消追加后的整张合同",
            },
        )
        assert returned.status_code == 200, returned.text
        assert returned.json()["status"] == "CANCELLED"

        first = _create_order(client, submit_supplier=False)
        second = _create_order(client, submit_supplier=False)
        combined = client.post(
            "/api/carton-procurement/orders/purchase-orders.xlsx",
            json={"factory_id": "huaxing", "order_nos": [first["order_no"], second["order_no"]]},
        )
        assert combined.status_code == 200, combined.text
        assert combined.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "纸箱累计对账表" in unquote(combined.headers["content-disposition"])
        assert unquote(combined.headers["content-disposition"]).endswith(".xlsx")
        combined_workbook = load_workbook(BytesIO(combined.content), data_only=False)
        assert combined_workbook.sheetnames == ["纸箱累计对账表"]
        combined_sheet = combined_workbook["纸箱累计对账表"]
        assert "华兴厂纸箱累计对账表" in combined_sheet["A1"].value
        assert "不代表向供应商" in combined_sheet.cell(row=combined_sheet.max_row, column=1).value
        assert combined_sheet["I4"].value == "河源东康纸品有限公司"
        assert combined_sheet["O7"].value == "单位"
        exported_order_nos = {
            combined_sheet.cell(row=row, column=2).value
            for row in range(8, combined_sheet.max_row + 1)
        }
        assert {first["order_no"], second["order_no"]}.issubset(exported_order_nos)
        first_order_row = next(
            row
            for row in range(8, combined_sheet.max_row + 1)
            if combined_sheet.cell(row=row, column=2).value == first["order_no"]
        )
        assert combined_sheet.cell(row=first_order_row, column=14).value == (
            f"=ROUNDUP(I{first_order_row}/M{first_order_row},0)"
        )
        combined_workbook.close()

        cancelled = client.post(
            "/api/carton-procurement/orders/bulk-cancel",
            json={
                "factory_id": "huaxing",
                "reason": "客户统一取消本批未生产订单",
                "items": [
                    {"order_no": first["order_no"], "expected_revision": first["revision"]},
                    {"order_no": second["order_no"], "expected_revision": second["revision"]},
                ],
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert [item["status"] for item in cancelled.json()] == ["CANCELLED", "CANCELLED"]

        filtered = client.get(
            "/api/carton-procurement/orders",
            params={
                "factory_id": "huaxing",
                "status_filter": "CANCELLED",
                "due_from": "2026-08-01",
                "due_to": "2026-08-31",
            },
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 3

        invalid_payload = _order_payload()
        invalid_payload["contract_no"] = "<script>"
        invalid = client.post("/api/carton-procurement/orders", json=invalid_payload)
        assert invalid.status_code == 422
        assert "合同号格式无效" in invalid.text


def test_batch_receipt_bulk_outbound_summary_and_return(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        first = _create_order(client)
        second = _create_order(client)
        receipt_response = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN-BULK-001",
                "delivery_date": "2026-08-05",
                "note": "两张订单批量登记入库",
                "lines": [
                    {
                        "order_line_id": first["lines"][0]["id"],
                        "delivered_quantity": "30",
                        "received_quantity": "30",
                        "location": "A-01",
                    },
                    {
                        "order_line_id": second["lines"][0]["id"],
                        "delivered_quantity": "30",
                        "received_quantity": "30",
                        "location": "A-02",
                    },
                ],
            },
        )
        assert receipt_response.status_code == 201, receipt_response.text
        receipt = receipt_response.json()
        assert len(receipt["lines"]) == 2
        blocked_pre_inventory_return = client.post(
            f"/api/carton-procurement/orders/{first['order_no']}/return",
            json={
                "factory_id": "huaxing",
                "expected_revision": first["revision"],
                "reason": "测试跨订单待确认收料保护",
            },
        )
        assert blocked_pre_inventory_return.status_code == 409
        assert "已确认锁定但未入库的订单不可取消" in blocked_pre_inventory_return.json()["detail"]
        confirmed = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text

        balances = client.get(
            "/api/carton-procurement/inventory/balances",
            params={"factory_id": "huaxing"},
        )
        assert balances.status_code == 200, balances.text
        selected = [row for row in balances.json() if row["balance"] == "30.0000"]
        assert len(selected) == 2
        outbound = client.post(
            "/api/carton-procurement/inventory/movements/bulk",
            json={
                "request_id": uuid4().hex,
                "factory_id": "huaxing",
                "document_no": "OUT-BULK-001",
                "reason": "客户要货",
                "items": [
                    {
                        "order_line_id": row["order_line_id"],
                        "quantity": row["balance"],
                        "location": row["latest_location"],
                    }
                    for row in selected
                ],
            },
        )
        assert outbound.status_code == 201, outbound.text
        assert len(outbound.json()) == 2
        assert all(Decimal(item["quantity"]) == Decimal("-30.0000") for item in outbound.json())

        summary = client.get(
            "/api/carton-procurement/inventory/summary",
            params={
                "factory_id": "huaxing",
                "date_from": "2026-08-05",
                "date_to": "2026-08-05",
            },
        )
        assert summary.status_code == 200, summary.text
        by_type = {item["movement_type"]: Decimal(item["quantity"]) for item in summary.json()}
        assert by_type == {"INBOUND": Decimal("60.0000"), "OUTBOUND": Decimal("60.0000")}

        refreshed = client.get(
            "/api/carton-procurement/orders",
            params={"factory_id": "huaxing", "search": first["order_no"]},
        ).json()["items"][0]
        returned = client.post(
            f"/api/carton-procurement/orders/{first['order_no']}/return",
            json={
                "factory_id": "huaxing",
                "expected_revision": refreshed["revision"],
                "reason": "客户退货并终止剩余纸品订单",
            },
        )
        assert returned.status_code == 200, returned.text
        assert returned.json()["status"] == "CANCELLED"

        return_audit = client.get(
            "/api/carton-procurement/audit-events",
            params={"factory_id": "huaxing", "event_type": "ORDER_RETURNED"},
        )
        assert return_audit.status_code == 200, return_audit.text
        assert return_audit.json()["total"] == 1
        returned_event = return_audit.json()["items"][0]
        assert returned_event["detail"]["order_no"] == first["order_no"]
        assert returned_event["detail"]["reason"] == "客户退货并终止剩余纸品订单"
        assert returned_event["actor_name"]
        assert returned_event["created_at"].startswith("2026-08-05")


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


def test_purchase_order_issues_export_only_net_supplier_change(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        payload = _order_payload()
        payload["product_order_quantity"] = "2100"
        payload["lines"] = [payload["lines"][0]]
        created_response = client.post("/api/carton-procurement/orders", json=payload)
        assert created_response.status_code == 201, created_response.text
        submitted = _submit_order(client, created_response.json())

        initial_context_response = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"},
        )
        assert initial_context_response.status_code == 200, initial_context_response.text
        initial_context = initial_context_response.json()
        assert initial_context["pending_type"] == "INITIAL"
        assert Decimal(initial_context["pending_product_quantity"]) == Decimal("2100")
        assert initial_context["issues"] == []

        initial_issue_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": submitted["revision"]},
        )
        assert initial_issue_response.status_code == 200, initial_issue_response.text
        assert initial_issue_response.headers["x-purchase-order-document-no"].endswith("-P00")
        initial_workbook = load_workbook(BytesIO(initial_issue_response.content), data_only=False)
        initial_sheet = initial_workbook["首次采购单"]
        assert initial_sheet["G10"].value == 18
        assert "本次变化" in initial_sheet[f"A{initial_sheet.max_row - 2}"].value
        initial_workbook.close()

        login_as(client, "carton_supervisor")
        appended_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": submitted["revision"],
                "additional_quantity": "1000",
            },
        )
        assert appended_response.status_code == 200, appended_response.text
        appended = appended_response.json()
        assert Decimal(appended["lines"][0]["required_quantity"]) == Decimal("26")

        append_context_response = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"},
        )
        assert append_context_response.status_code == 200, append_context_response.text
        append_context = append_context_response.json()
        assert append_context["pending_type"] == "APPEND"
        assert Decimal(append_context["pending_product_quantity"]) == Decimal("1000")
        assert len(append_context["issues"]) == 1

        append_issue_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": appended["revision"]},
        )
        assert append_issue_response.status_code == 200, append_issue_response.text
        assert append_issue_response.headers["x-purchase-order-document-no"].endswith("-A01")
        append_workbook = load_workbook(BytesIO(append_issue_response.content), data_only=False)
        append_sheet = append_workbook["追加采购单"]
        assert append_sheet["F6"].value == 1000
        assert append_sheet["F10"].value == 18
        assert append_sheet["G10"].value == 8
        assert append_sheet["H10"].value == 26
        assert "不得把“变更后累计”重复作为新增订单" in append_sheet[f"A{append_sheet.max_row - 2}"].value
        append_workbook.close()

        no_change_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": appended["revision"]},
        )
        assert no_change_response.status_code == 409, no_change_response.text
        assert "没有尚未生成" in no_change_response.json()["detail"]

        reduced_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/reduce",
            json={
                "factory_id": "huaxing",
                "expected_revision": appended["revision"],
                "reduction_quantity": "100",
            },
        )
        assert reduced_response.status_code == 200, reduced_response.text
        reduced = reduced_response.json()
        reduce_context = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"},
        ).json()
        assert reduce_context["pending_type"] == "REDUCE"
        assert Decimal(reduce_context["pending_product_quantity"]) == Decimal("-100")

        reduce_issue_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": reduced["revision"]},
        )
        assert reduce_issue_response.status_code == 200, reduce_issue_response.text
        assert reduce_issue_response.headers["x-purchase-order-document-no"].endswith("-R01")
        reduce_workbook = load_workbook(BytesIO(reduce_issue_response.content), data_only=False)
        reduce_sheet = reduce_workbook["减单通知"]
        assert reduce_sheet["F6"].value == -100
        assert reduce_sheet["G10"].value == -1
        reduce_workbook.close()

        final_context = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"},
        ).json()
        assert final_context["pending_type"] == "NONE"
        assert [item["document_type"] for item in final_context["issues"]] == [
            "REDUCE", "APPEND", "INITIAL"
        ]

        reuse_batch_response = client.post(
            "/api/carton-procurement/orders/purchase-order-issues.xlsx",
            json={
                "factory_id": "huaxing",
                "items": [{
                    "order_no": reduced["order_no"],
                    "expected_revision": reduced["revision"],
                }],
            },
        )
        assert reuse_batch_response.status_code == 200, reuse_batch_response.text
        assert reuse_batch_response.headers["x-purchase-order-issue-count"] == "1"
        reuse_batch_workbook = load_workbook(BytesIO(reuse_batch_response.content), data_only=False)
        reuse_batch_sheet = reuse_batch_workbook["供应商采购单批次"]
        assert any(
            reuse_batch_sheet.cell(row=row, column=2).value == f"{reduced['order_no']}-R01"
            for row in range(6, reuse_batch_sheet.max_row)
        )
        reuse_batch_workbook.close()
        context_after_reuse = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"},
        ).json()
        assert len(context_after_reuse["issues"]) == len(final_context["issues"])

        append_issue = next(
            item for item in final_context["issues"] if item["document_type"] == "APPEND"
        )
        redownload_response = client.get(
            f"/api/carton-procurement/orders/{submitted['order_no']}/purchase-order-issues/{append_issue['id']}.xlsx",
            params={"factory_id": "huaxing"},
        )
        assert redownload_response.status_code == 200, redownload_response.text
        redownload_workbook = load_workbook(BytesIO(redownload_response.content), data_only=False)
        assert redownload_workbook["追加采购单"]["G10"].value == 8
        redownload_workbook.close()

        appended_again_response = client.post(
            f"/api/carton-procurement/orders/{submitted['order_no']}/append",
            json={
                "factory_id": "huaxing",
                "expected_revision": reduced["revision"],
                "additional_quantity": "120",
            },
        )
        assert appended_again_response.status_code == 200, appended_again_response.text
        appended_again = appended_again_response.json()

        second_payload = _order_payload()
        second_payload["product_order_quantity"] = "240"
        second_payload["lines"] = [second_payload["lines"][0]]
        second_created_response = client.post("/api/carton-procurement/orders", json=second_payload)
        assert second_created_response.status_code == 201, second_created_response.text
        second_submitted = _submit_order(client, second_created_response.json())

        batch_response = client.post(
            "/api/carton-procurement/orders/purchase-order-issues.xlsx",
            json={
                "factory_id": "huaxing",
                "items": [
                    {
                        "order_no": appended_again["order_no"],
                        "expected_revision": appended_again["revision"],
                    },
                    {
                        "order_no": second_submitted["order_no"],
                        "expected_revision": second_submitted["revision"],
                    },
                ],
            },
        )
        assert batch_response.status_code == 200, batch_response.text
        assert batch_response.headers["x-purchase-order-issue-count"] == "2"
        batch_workbook = load_workbook(BytesIO(batch_response.content), data_only=False)
        batch_sheet = batch_workbook["供应商采购单批次"]
        document_numbers = {
            batch_sheet.cell(row=row, column=2).value
            for row in range(6, batch_sheet.max_row)
            if batch_sheet.cell(row=row, column=2).value
        }
        assert f"{submitted['order_no']}-A02" in document_numbers
        assert f"{second_submitted['order_no']}-P00" in document_numbers
        assert "只执行“本次箱数变化”" in batch_sheet["A2"].value
        batch_workbook.close()


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


def test_ad_hoc_receipt_requires_human_confirmation_before_inventory_and_month_end(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _create_order(client)

        created = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN-SAMPLE-260805-001",
                "delivery_date": "2026-08-05",
                "note": "送货单未匹配正式订单，打板纸箱待人工确认",
                "lines": [
                    {
                        "source_type": "AD_HOC",
                        "order_line_id": None,
                        "customer_code": "DICKIE",
                        "contract_no": "SAMPLE-BOARD-001",
                        "item_no": "SAMPLE-203399999",
                        "packaging_type": "打板外箱",
                        "paper_quality": "A33+B",
                        "specification": "12 × 10 × 5 in",
                        "delivered_quantity": "5",
                        "received_quantity": "5",
                        "damaged_quantity": "0",
                        "rejected_quantity": "0",
                        "unusable_quantity": "0",
                        "unit": "个",
                        "unit_price": "2.5",
                        "currency": "CNY",
                        "location": "打板区 S-01",
                        "feedback_note": "非正式打板收料",
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        receipt = created.json()
        assert receipt["status"] == "PENDING_CONFIRMATION"
        assert receipt["lines"][0]["source_type"] == "AD_HOC"
        assert receipt["lines"][0]["order_line_id"] is None

        before_movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()
        assert before_movements["total"] == 0
        before_closing = client.post(
            "/api/carton-procurement/closings/generate",
            json={"factory_id": "huaxing", "period": "2026-08"},
        )
        assert before_closing.status_code == 200, before_closing.text
        assert before_closing.json() == []

        confirmed = client.post(
            f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
            json={"factory_id": "huaxing", "expected_revision": receipt["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "POSTED"

        movements = client.get(
            "/api/carton-procurement/inventory/movements",
            params={"factory_id": "huaxing"},
        ).json()
        assert movements["total"] == 1
        movement = movements["items"][0]
        assert movement["order_line_id"] is None
        assert movement["document_no"] == "DN-SAMPLE-260805-001"
        assert "非正式/打板收料" in movement["reason"]
        assert Decimal(movement["quantity"]) == Decimal("5.0000")

        closings = client.post(
            "/api/carton-procurement/closings/generate",
            json={"factory_id": "huaxing", "period": "2026-08"},
        )
        assert closings.status_code == 200, closings.text
        assert len(closings.json()) == 1
        closing = closings.json()[0]
        assert closing["customer_code"] == "DICKIE"
        assert Decimal(closing["inbound_quantity"]) == Decimal("5.0000")
        assert Decimal(closing["ending_amount"]) == Decimal("12.5000")


def test_ad_hoc_receipt_rejects_incomplete_material_snapshot(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        response = client.post(
            "/api/carton-procurement/receipts",
            json={
                "factory_id": "huaxing",
                "delivery_note_no": "DN-SAMPLE-INCOMPLETE",
                "delivery_date": "2026-08-05",
                "lines": [
                    {
                        "source_type": "AD_HOC",
                        "customer_code": "DICKIE",
                        "item_no": "",
                        "packaging_type": "打板外箱",
                        "paper_quality": "A33+B",
                        "specification": "12 × 10 × 5 in",
                        "delivered_quantity": "5",
                        "received_quantity": "5",
                    }
                ],
            },
        )
        assert response.status_code == 422
        assert "非正式收料必须补齐" in response.text


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
                        "unit_price": "2.567891",
                    }
                    for index, line in enumerate(order["lines"], start=1)
                ],
            },
        )
        assert receipt_response.status_code == 201, receipt_response.text
        receipt = receipt_response.json()
        assert receipt["import_batch_id"] is None
        assert receipt["status"] == "PENDING_CONFIRMATION"
        assert all(Decimal(line["unit_price"]) == Decimal("2.567891") for line in receipt["lines"])

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
        assert all(Decimal(row["unit_price"]) == Decimal("2.567891") for row in movements["items"])
        assert {line["id"]: line["unit_price"] for line in refreshed_order["lines"]} == {
            line["id"]: line["unit_price"] for line in order["lines"]
        }


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
                "request_id": uuid4().hex,
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

        login_as(client, "admin")
        for next_status in ("PENDING", "CONFIRMED", "LOCKED"):
            if next_status == "LOCKED":
                monkeypatch.setattr("app.services.carton_procurement.business_now", lambda: datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
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

        # A backdated posting into the locked period must still be rejected.
        _freeze_carton_time(monkeypatch)
        blocked = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "request_id": uuid4().hex,
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
        assert first.json()["parse_summary"]["parser_version"] == "delivery-note-local-v6-po"
        assert json.loads(first.json()["import_profile"])["parser_version"] == "delivery-note-local-v6-po"
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


def test_delivery_import_parser_version_reprocesses_an_older_file(monkeypatch):
    with make_client(monkeypatch) as client:
        import app.services.carton_procurement as service
        import app.services.carton_procurement_imports as imports

        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _create_order(client)
        content = _workbook_bytes(
            ["日期", "入库单号", "PO", "货号", "外箱", "纸质"],
            [["2026-08-05", "DN-PARSER-VERSION", "SC700145365", "203302044", 10, "A33+B外箱"]],
        )

        monkeypatch.setattr(service, "DELIVERY_IMPORT_PARSER_VERSION", "delivery-note-v1")
        monkeypatch.setattr(imports, "DELIVERY_IMPORT_PARSER_VERSION", "delivery-note-v1")
        first = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-PARSER-VERSION.xlsx", content)},
        )
        assert first.status_code == 201, first.text
        assert first.json()["duplicate"] is False
        assert first.json()["parse_summary"]["parser_version"] == "delivery-note-v1"

        monkeypatch.setattr(service, "DELIVERY_IMPORT_PARSER_VERSION", "delivery-note-v2")
        monkeypatch.setattr(imports, "DELIVERY_IMPORT_PARSER_VERSION", "delivery-note-v2")
        reprocessed = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-PARSER-VERSION.xlsx", content)},
        )
        assert reprocessed.status_code == 201, reprocessed.text
        assert reprocessed.json()["duplicate"] is False
        assert reprocessed.json()["id"] != first.json()["id"]
        assert reprocessed.json()["parse_summary"]["parser_version"] == "delivery-note-v2"

        duplicate = client.post(
            "/api/carton-procurement/receipt-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("DN-PARSER-VERSION.xlsx", content)},
        )
        assert duplicate.status_code == 201, duplicate.text
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["id"] == reprocessed.json()["id"]


def test_delivery_heic_photo_uses_quality_and_specification_to_select_order_line(monkeypatch):
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
            files={"file": ("DN26061301.heic", b"delivery-photo", "image/heic")},
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
        assert json.loads(result["import_profile"]) == {"advance_days": 3, "matching_version": "customer-po-v1"}
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


def test_history_order_item_suggestions_rank_and_return_latest_reusable_snapshot(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)

        content = _history_workbook_bytes(
            [
                [
                    "HIST-2024-ITEM-001", "SC-HIST-OLD", "Dickie", "203302044",
                    "旧产品名称", 1200, "2024-08-05", "2024-08-12", "旧资料",
                    "外箱", "A33", "30 × 20 × 15", "cm", 120, "个", 2.8,
                    "CNY", "历史合同", "旧版纸箱", None,
                ],
                [
                    "HIST-2025-ITEM-001", "SC-HIST-LATEST", "Dickie", "203302044",
                    "消防车套装", 3600, "2025-08-05", "2025-08-12", "最近资料",
                    "外箱", "A33+B", "31.5 × 11.125 × 11.25", "in", 120, "个", 3.46,
                    "CNY", "历史合同", "主箱", None,
                ],
                [
                    "HIST-2025-ITEM-001", "SC-HIST-LATEST", "Dickie", "203302044",
                    "消防车套装", 3600, "2025-08-05", "2025-08-12", "最近资料",
                    "内箱", "B3B", "15.5 × 10.625 × 5.25", "in", 30, "个", 0.96,
                    "CNY", "历史合同", "内盒", None,
                ],
                [
                    "HIST-2025-ITEM-002", "SC-HIST-NEAR", "Dickie", "203302045",
                    "近似货号产品", 2400, "2025-07-01", "2025-07-08", "近似资料",
                    "外箱", "A9A", "29 × 19", "cm", 60, "个", 1.8,
                    "CNY", "历史合同", "", None,
                ],
            ]
        )
        imported = client.post(
            "/api/carton-procurement/orders/history-imports",
            params={"factory_id": "huaxing"},
            files={"file": ("历史订单.xlsx", content)},
        )
        assert imported.status_code == 201, imported.text
        assert imported.json()["imported_count"] == 3

        exact = client.get(
            "/api/carton-procurement/order-history/item-suggestions",
            params={"factory_id": "huaxing", "item_no": "203302044"},
        )
        assert exact.status_code == 200, exact.text
        exact_result = exact.json()
        assert exact_result["query"] == "203302044"
        assert exact_result["items"][0]["match_type"] == "EXACT"
        assert exact_result["items"][0]["latest_order_no"] == "HIST-2025-ITEM-001"
        assert exact_result["items"][0]["latest_contract_no"] == "SC-HIST-LATEST"
        assert exact_result["items"][0]["product_name"] == "消防车套装"
        assert exact_result["items"][0]["order_count"] == 2
        assert [line["packaging_type"] for line in exact_result["items"][0]["lines"]] == [
            "外箱", "内箱"
        ]
        assert exact_result["items"][0]["lines"][0]["paper_quality"] == "A33+B"
        assert Decimal(exact_result["items"][0]["lines"][0]["usage_quantity"]) == Decimal("120")
        assert Decimal(exact_result["items"][0]["lines"][0]["unit_price"]) == Decimal("3.46")

        prefix = client.get(
            "/api/carton-procurement/order-history/item-suggestions",
            params={"factory_id": "huaxing", "item_no": "20330204"},
        )
        assert prefix.status_code == 200, prefix.text
        assert {item["item_no"] for item in prefix.json()["items"]} == {
            "203302044", "203302045"
        }
        assert {item["match_type"] for item in prefix.json()["items"]} == {"PREFIX"}

        similar = client.get(
            "/api/carton-procurement/order-history/item-suggestions",
            params={"factory_id": "huaxing", "item_no": "20330204X", "limit": 1},
        )
        assert similar.status_code == 200, similar.text
        assert similar.json()["items"][0]["match_type"] == "SIMILAR"


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
        assert balance["latest_document_no"] == "STOCKTAKE-OPERABLE"
        # Opening stock stays an adjustment but its document date is searchable.
        assert balance["latest_inbound_at"].startswith("2025-08-05")

        outbound = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "request_id": uuid4().hex,
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
        after_outbound = client.get(
            "/api/carton-procurement/inventory/balances",
            params={"factory_id": "huaxing"},
        ).json()[0]
        assert after_outbound["latest_movement_at"].startswith("2026-08-05")
        assert after_outbound["latest_inbound_at"] == balance["latest_inbound_at"]

        negative = client.post(
            "/api/carton-procurement/inventory/movements",
            json={
                "request_id": uuid4().hex,
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
        after_reversal = client.get(
            "/api/carton-procurement/inventory/balances",
            params={"factory_id": "huaxing"},
        ).json()[0]
        assert after_reversal["latest_inbound_at"] == balance["latest_inbound_at"]


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

        balance = client.get(
            "/api/carton-procurement/inventory/balances",
            params={"factory_id": "huaxing"},
        ).json()[0]
        assert balance["latest_inbound_at"] == FIXED_NOW.isoformat()
        import app.services.carton_procurement as service

        for index, movement_type in enumerate(("OUTBOUND", "ADJUSTMENT")):
            monkeypatch.setattr(service, "business_now", lambda: FIXED_NOW.replace(day=6, second=index))
            movement = client.post(
                "/api/carton-procurement/inventory/movements",
                json={
                    "request_id": uuid4().hex,
                    "factory_id": "huaxing",
                    "order_line_id": balance["order_line_id"],
                    "movement_type": movement_type,
                    "quantity": "1",
                    "document_no": f"DATE-CHECK-{movement_type}",
                    "reason": "核对入库时间不受后续作业影响",
                },
            )
            assert movement.status_code == 201, movement.text
            balances = client.get(
                "/api/carton-procurement/inventory/balances",
                params={"factory_id": "huaxing"},
            ).json()
            changed = next(row for row in balances if row["latest_movement_id"] == movement.json()["id"])
            assert changed["latest_movement_at"].startswith("2026-08-06")
            assert changed["latest_inbound_at"] == balance["latest_inbound_at"]
