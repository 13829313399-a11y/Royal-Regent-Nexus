"""Pre-release rehearsal with an independent September/October quantity and money oracle.

All business writes use the HTTP API against make_client's disposable database.
The operating-system clock and the user's database are never changed.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal as D
from io import BytesIO
import json
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from test_molding_sample_api import make_client, login_as
from test_carton_history_wide import workbook as history_book, row as history_row
from test_carton_opening_preview import workbook as opening_book

BASE = "/api/carton-procurement"
FACTORY = {"factory_id": "huaxing"}


def test_complete_order_import_opening_receive_issue_and_two_month_closing(monkeypatch, tmp_path):
    evidence = []
    output = Path(os.environ.get("CARTON_FINAL_QA_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    with make_client(monkeypatch) as client:
        from app.services import carton_procurement as core
        current = [datetime(2026, 9, 1, 9, tzinfo=ZoneInfo("Asia/Shanghai"))]

        def now():
            value = current[0]
            current[0] += timedelta(seconds=1)
            return value

        monkeypatch.setattr(core, "business_now", now)
        login_as(client, "admin")
        (output / "isolated-database.txt").write_text(os.environ["DATABASE_URL"], encoding="utf-8")

        def day(value):
            current[0] = datetime.fromisoformat(value + "T09:00:00+08:00")

        def get(path, **params):
            result = client.get(BASE + path, params={**FACTORY, **params})
            assert result.status_code == 200, (path, result.text)
            return result.json()

        def post(path, data, status=200):
            result = client.post(BASE + path, json={**FACTORY, **data})
            assert result.status_code == status, (path, result.status_code, result.text)
            return result.json() if result.content else None

        def orders():
            return get("/orders", limit=100)["items"]

        def refreshed(order):
            return next(row for row in orders() if row["order_no"] == order["order_no"])

        def check(label, expected_stock, expected_amount):
            positions = get("/inventory/positions")
            actual = defaultdict(D)
            for row in positions:
                actual[(row["item_no"], row["packaging_type"]) ] += D(row["balance"])
                assert row["cost_amount"] is not None, (label, row)
            actual = {key: value for key, value in actual.items() if value}
            assert actual == {key: D(value) for key, value in expected_stock.items()}, (label, actual, expected_stock)
            amount = sum((D(row["cost_amount"]) for row in positions), D(0))
            assert amount == D(expected_amount), (label, amount, expected_amount)
            movements = get("/inventory/movements", limit=500)["items"]
            units = defaultdict(D)
            for row in movements:
                units[row["unit"]] += D(row["quantity"])
            position_units = defaultdict(D)
            for row in positions:
                position_units[row["unit"]] += D(row["balance"])
            assert units == position_units, (label, units, position_units)
            report = get("/inventory/report")
            report_stock = defaultdict(D)
            for row in report["order_rows"]:
                assert D(row["opening_quantity"]) + D(row["inbound_quantity"]) - D(row["outbound_quantity"]) + D(row["adjustment_quantity"]) == D(row["ending_quantity"])
                report_stock[(row["item_no"], row["packaging_type"])] += D(row["ending_quantity"])
            assert {key: value for key, value in report_stock.items() if value} == actual
            for row in report["rows"]:
                assert D(row["opening_quantity"]) + D(row["inbound_quantity"]) - D(row["outbound_quantity"]) + D(row["adjustment_quantity"]) == D(row["ending_quantity"])
            dashboard = get("/dashboard")
            assert D(dashboard["inventory_balance"]) == sum(units.values())
            audit = get("/audit-events", limit=200)
            evidence.append({"step": label, "business_time": current[0].isoformat(),
                "stock": [{"item": k[0], "paper": k[1], "quantity": str(v)} for k, v in actual.items()],
                "amount": str(amount), "quantities_by_unit": dict(units), "movement_count": len(movements),
                "orders": [{"contract": row["contract_no"], "status": row["status"],
                    "received": [line["received_quantity"] for line in row["lines"]]} for row in orders()],
                "dashboard": dashboard, "receipt_count": get("/receipts")["total"], "audit_count": audit["total"]})
            (output / "business-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return positions

        customer = post("/customers", {"customer_code": "QA-FINAL", "customer_name": "上线验收客户"}, 201)
        locations = [post("/inventory/locations", {"warehouse": "验收仓", "bin_code": code}, 201) for code in ("A1", "A2")]
        loc = locations[0]["id"]
        opening = opening_book([
            ["QA-OPEN", "QA-OPEN", "A33外箱", 30, 20, 15, "A1", 90, 2],
            ["QA-OPEN", "QA-OPEN", "H5A平卡", 30, 20, 0, "A1", 50, .3],
        ])
        (output / "opening-input.xlsx").write_bytes(opening)
        options = {"customer_name": customer["customer_name"], "warehouse": "验收仓", "snapshot_date": "2026-08-31", "dimension_unit": "cm", "currency": "CNY"}
        form = {"options": json.dumps(options)}
        def upload_open(preview=True):
            return client.post(BASE + "/inventory/history-imports" + ("/preview" if preview else ""), params=FACTORY,
                files={"file": ("opening.xlsx", opening)}, data=form)
        response = upload_open(); assert response.status_code == 200, response.text
        assert response.json()["errors"] == []
        assert get("/inventory/positions") == []
        form["expected_preview_fingerprint"] = response.json()["source_fingerprint"]
        response = upload_open(False); assert response.status_code == 201, response.text
        stock = {("QA-OPEN", "外箱"): 90, ("QA-OPEN", "平卡"): 50}
        check("期初90个外箱及50张平卡入账，未产生收料", stock, 195)

        history = history_book([history_row(**{"客户名称": customer["customer_name"], "合同号": "QA-HISTORY", "货号": "QA-HISTORY",
            "历史订单号": "QA-HISTORY-ORDER", "下单日期": "2026-08-20", "计划交期": "2026-09-25", "外箱需求数量": 30,
            "外箱纸质": "A33", "外箱规格": "30*20*15"})])
        (output / "history-input.xlsx").write_bytes(history)
        upload_args = {"params": FACTORY, "files": {"file": ("history.xlsx", history)}}
        response = client.post(BASE + "/history-orders/preview", **upload_args)
        assert response.status_code == 200 and not response.json()["errors"], response.text
        response = client.post(BASE + "/orders/history-imports", **upload_args, data={"expected_preview_fingerprint": response.json()["source_fingerprint"]})
        assert response.status_code == 201, response.text
        old = orders()[0]
        assert old["quantity_basis"] == "EXPLICIT" and old["product_order_quantity"] is None
        assert D(old["lines"][0]["received_quantity"]) == 0
        old = post(f"/orders/{old['order_no']}/submit-supplier", {"expected_revision": old["revision"]})
        check("历史订单30个需求导入并锁定，库存未增加", stock, 195)

        day("2026-09-10")
        order = post("/orders", {"customer_code": customer["customer_code"], "customer_name": customer["customer_name"],
            "contract_no": "QA-NEW", "item_no": "QA-NEW", "product_name": "验收纸箱产品", "product_order_quantity": "1200",
            "order_date": "2026-09-10", "customer_due_date": "2026-09-25", "due_date": "2026-09-22",
            "lines": [{"packaging_type": kind, "paper_quality": quality, "specification": spec, "dimension_unit": "cm",
                "usage_quantity": packing, "unit": unit, "unit_price": price} for kind, quality, spec, packing, unit, price in [
                ("外箱", "A33", "30*20*15", 12, "个", 3), ("内箱", "B3B", "15*10*5", 6, "个", 1), ("平卡", "H5A", "30*20", 12, "张", .5)]]}, 201)
        assert [D(line["required_quantity"]) for line in order["lines"]] == [100, 200, 100]
        order = post(f"/orders/{order['order_no']}/submit-supplier", {"expected_revision": order["revision"]})
        issued = client.post(BASE + f"/orders/{order['order_no']}/purchase-order-issues.xlsx", json={**FACTORY, "expected_revision": order["revision"]})
        assert issued.status_code == 200, issued.text
        purchase = load_workbook(BytesIO(issued.content), data_only=True)
        assert "QA-NEW" in str([cell for row in purchase.active.values for cell in row])
        (output / "issued-purchase-order.xlsx").write_bytes(issued.content)
        check("新单三种纸品需求及采购单生成，库存仍未增加", stock, 195)

        def receive(row, doc, values, date):
            data = {"delivery_note_no": doc, "delivery_date": date, "acceptance_date": date,
                "post_immediately": True, "request_id": uuid4().hex,
                "lines": [{"order_line_id": line["id"], "delivered_quantity": quantity, "received_quantity": quantity,
                    "unit_price": price, "location_allocations": [{"location_id": loc, "quantity": quantity}]}
                    for line, (quantity, price) in zip(row["lines"], values, strict=True)]}
            result = post("/receipts", data, 201)
            assert result["status"] == "POSTED"
            assert post("/receipts", data, 201)["id"] == result["id"]
            return result

        day("2026-09-15")
        receive(order, "QA-DN-SEP-1", [(60, 3), (100, 1), (60, .5)], "2026-09-15")
        stock.update({("QA-NEW", "外箱"): 60, ("QA-NEW", "内箱"): 100, ("QA-NEW", "平卡"): 60})
        assert refreshed(order)["status"] == "PARTIALLY_RECEIVED"
        check("第一批部分收料，重复点击仅入账一次", stock, 505)
        day("2026-09-20")
        receive(order, "QA-DN-SEP-2", [(40, 4), (100, 1), (40, .5)], "2026-09-20")
        stock.update({("QA-NEW", "外箱"): 100, ("QA-NEW", "内箱"): 200, ("QA-NEW", "平卡"): 100})
        assert refreshed(order)["status"] == "COMPLETED"
        check("第二批收齐，外箱两次进价形成3.4元平均库存成本", stock, 785)

        def issue(item, paper, quantity, doc, kind="USAGE"):
            balance = next(row for row in get("/inventory/positions") if row["item_no"] == item and row["packaging_type"] == paper and D(row["balance"]) >= quantity)
            data = {"request_id": uuid4().hex, "reference_movement_id": balance["latest_movement_id"], "location_id": balance["location_id"],
                "movement_type": "OUTBOUND", "quantity": quantity, "document_no": doc, "reason": "上线验收生产领料" if kind == "USAGE" else "上线验收供应商退货", "issue_kind": kind}
            result = post("/inventory/movements", data, 201)
            assert post("/inventory/movements", data, 201)["id"] == result["id"]
            stock[(item, paper)] -= quantity
            return result

        day("2026-09-21")
        issue("QA-NEW", "外箱", 50, "QA-OUT-1")
        issue("QA-NEW", "内箱", 80, "QA-OUT-2")
        issue("QA-NEW", "平卡", 30, "QA-OUT-3")
        check("三种纸品领料，按单位分开核对库存与流水", stock, 520)
        day("2026-09-25")
        receive(old, "QA-DN-HISTORY", [(30, 4)], "2026-09-25")
        stock[("QA-HISTORY", "外箱")] = 30
        issue("QA-HISTORY", "外箱", 5, "QA-OUT-HISTORY")
        issue("QA-OPEN", "外箱", 10, "QA-OUT-OPEN-BOX")
        issue("QA-OPEN", "平卡", 20, "QA-OUT-OPEN-CARD")
        check("历史订单正常收料出库，期初库存也可领用", stock, 594)
        day("2026-09-26")
        issue("QA-NEW", "外箱", 10, "QA-RETURN-SEP", "RETURN")
        check("供应商退货10个，库存扣平均成本34元", stock, 560)

        day("2026-09-30")
        late = post("/orders", {"customer_code": customer["customer_code"], "customer_name": customer["customer_name"],
            "contract_no": "QA-CROSS-MONTH", "item_no": "QA-CROSS-MONTH", "product_name": "跨月到货产品", "quantity_basis": "EXPLICIT",
            "product_order_quantity": None, "order_date": "2026-09-30", "due_date": "2026-10-02", "lines": [{
                "packaging_type": "外箱", "paper_quality": "A33", "specification": "30*20*15", "dimension_unit": "cm",
                "required_quantity": 20, "usage_quantity": None, "unit": "个", "unit_price": 5}]}, 201)
        late = post(f"/orders/{late['order_no']}/submit-supplier", {"expected_revision": late["revision"]})
        work = get("/supplier-settlements/workspace", period="2026-09", currency="CNY")
        assert len(work["sources"]) == 8
        assert not any(row["item_no"] in {"QA-OPEN", "QA-CROSS-MONTH"} for row in work["sources"])
        # Independent supplier bill values: they are not copied from application totals.
        bill_values = {("QA-DN-SEP-1", "外箱"): (60, 3), ("QA-DN-SEP-1", "内箱"): (100, 1), ("QA-DN-SEP-1", "平卡"): (60, .5),
            ("QA-DN-SEP-2", "外箱"): (40, 4), ("QA-DN-SEP-2", "内箱"): (100, 1), ("QA-DN-SEP-2", "平卡"): (40, .5),
            ("QA-DN-HISTORY", "外箱"): (30, 4), ("QA-RETURN-SEP", "外箱"): (10, 4)}

        def supplier_bill(workspace, values):
            lines = []
            for i, source in enumerate(workspace["sources"]):
                quantity, price = values[(source["document_no"], source["packaging_type"])]
                line = {"id": str(i), "source_key": source["source_key"], "document_no": source["document_no"],
                    "quantity": str(quantity), "unit_price": str(price), "amount": str(D(str(quantity)) * D(str(price)))}
                if source["kind"] == "RETURN":
                    line.update(approved_return_unit_price="4", credit_document_no="QA-CREDIT-SEP", credit_date="2026-09-26", note="验收独立退货凭据：10个，每个4元")
                else:
                    assert D(source["quantity"]) == D(str(quantity)) and D(source["amount"]) == D(line["amount"])
                lines.append(line)
            return {"supplier_id": workspace["supplier_id"], "period": workspace["period"], "currency": "CNY",
                "source_fingerprint": workspace["source_fingerprint"], "statement_no": "QA-BILL-" + workspace["period"],
                "same_price_basis": True, "tax_basis": "INCLUSIVE", "lines": lines}

        bill = post("/supplier-settlements", supplier_bill(work, bill_values))
        assert D(bill["result"]["net_amount"]) == 670 and not bill["result"]["issues"], bill
        post(f"/supplier-settlements/{bill['id']}/confirm", {"expected_revision": bill["revision"]}, 409)
        closing = post("/closings/generate", {"period": "2026-09"})[0]
        assert D(closing["ending_amount"]) == 560 and not closing["pricing_issues"]
        unit_rows = {row["unit"]: row for row in closing["quantities_by_unit"]}
        assert [D(unit_rows["个"][field]) for field in ("opening_quantity", "inbound_quantity", "outbound_quantity", "ending_quantity")] == [90, 330, 155, 265]
        assert [D(unit_rows["张"][field]) for field in ("opening_quantity", "inbound_quantity", "outbound_quantity", "ending_quantity")] == [50, 100, 50, 100]
        day("2026-10-01")
        bill = post(f"/supplier-settlements/{bill['id']}/confirm", {"expected_revision": bill["revision"]})
        assert bill["status"] == "CONFIRMED"
        for status in ("PENDING", "CONFIRMED", "LOCKED"):
            closing = post(f"/closings/{closing['id']}/status", {"expected_revision": closing["revision"], "status": status})
        evidence.append({"month": "2026-09", "supplier_expected": "670", "supplier": bill, "inventory_expected": "560", "inventory": closing})
        check("切换10月后完成9月供应商确认和库存锁账", stock, 560)

        day("2026-10-02")
        receive(late, "QA-DN-OCT", [(20, 5)], "2026-10-02")
        stock[("QA-CROSS-MONTH", "外箱")] = 20
        check("9月30日落单10月2日到货，记入10月供应商来源", stock, 660)
        assert D(get("/supplier-settlements/workspace", period="2026-09")["documents"][0]["result"]["net_amount"]) == 670
        october = get("/supplier-settlements/workspace", period="2026-10")
        assert len(october["sources"]) == 1 and D(october["sources"][0]["amount"]) == 100
        day("2026-10-05")
        issue("QA-CROSS-MONTH", "外箱", 5, "QA-OUT-OCT-NEW")
        issue("QA-NEW", "外箱", 10, "QA-OUT-OCT-SEP")
        issue("QA-HISTORY", "外箱", 5, "QA-OUT-OCT-HISTORY")
        issue("QA-OPEN", "平卡", 10, "QA-OUT-OCT-OPEN")
        check("10月领用新货及9月结转库存，金额独立核算为578元", stock, 578)
        october = get("/supplier-settlements/workspace", period="2026-10")
        assert len(october["sources"]) == 1
        october_bill = post("/supplier-settlements", supplier_bill(october, {("QA-DN-OCT", "外箱"): (20, 5)}))
        post(f"/supplier-settlements/{october_bill['id']}/confirm", {"expected_revision": october_bill["revision"]}, 409)
        october_closing = post("/closings/generate", {"period": "2026-10"})[0]
        assert D(october_closing["ending_amount"]) == 578
        quantities = {row["unit"]: row for row in october_closing["quantities_by_unit"]}
        assert [D(quantities["个"][field]) for field in ("opening_quantity", "inbound_quantity", "outbound_quantity", "ending_quantity")] == [265, 20, 20, 265]
        assert [D(quantities["张"][field]) for field in ("opening_quantity", "inbound_quantity", "outbound_quantity", "ending_quantity")] == [100, 0, 10, 90]
        day("2026-11-01")
        october_bill = post(f"/supplier-settlements/{october_bill['id']}/confirm", {"expected_revision": october_bill["revision"]})
        for status in ("PENDING", "CONFIRMED", "LOCKED"):
            october_closing = post(f"/closings/{october_closing['id']}/status", {"expected_revision": october_closing["revision"], "status": status})
        evidence.append({"month": "2026-10", "supplier_expected": "100", "supplier": october_bill, "inventory_expected": "578", "inventory": october_closing})
        check("切换11月后完成10月供应商确认和库存锁账", stock, 578)
        assert get("/exceptions")["total"] == 0
        assert get("/inventory/positions", factory_id="huadeng") == []
        (output / "complete.json").write_text(json.dumps({"status": "PASS", "steps": len(evidence), "database": os.environ["DATABASE_URL"], "system_clock_changed": False}, indent=2), encoding="utf-8")
