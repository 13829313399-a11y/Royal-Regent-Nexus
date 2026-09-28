from decimal import Decimal
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order, _freeze_carton_time

BASE = "/api/carton-procurement"


def setup(client, monkeypatch, *, explicit=False):
    login_as(client, "warehouse_keeper")
    _freeze_carton_time(monkeypatch)
    _ensure_dickie_customer(client)
    body = _order_payload()
    body.update(product_order_quantity="100", customer_po="ORIGINAL")
    body["lines"] = [body["lines"][0]]
    body["lines"][0].update(usage_quantity="10", unit_price="1")
    if explicit:
        body.update(quantity_basis="EXPLICIT", product_order_quantity=None)
        body["lines"][0].update(usage_quantity=None, required_quantity="10")
    result = client.post(BASE + "/orders", json=body)
    assert result.status_code == 201, result.text
    return _submit_order(client, result.json())


def latest(client):
    return client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"][0]


def context(client, order):
    response = client.get(BASE + f"/orders/{order['order_no']}/splits", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def split_body(order, *, pending="4", stock=(), product="40", contract="NEW-CONTRACT"):
    return {"factory_id": "huaxing", "request_id": uuid4().hex, "expected_revision": order["revision"],
        "reason": "按客户要求拆分合同", "targets": [{"contract_no": contract, "customer_po": "NEW-PO", "product_quantity": product,
        "lines": [{"order_line_id": order["lines"][0]["id"], "pending_quantity": pending, "stock": list(stock)}]}]}


def save(client, order, body):
    result = client.post(BASE + f"/orders/{order['order_no']}/splits", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def action(client, plan, name, **changes):
    return client.post(BASE + f"/order-splits/{plan['id']}/{name}", json={
        "factory_id": "huaxing", "expected_revision": plan["revision"], "reason": "仓库已核对拆分归属", **changes})


def preview(client, order, qty):
    result = client.post(BASE + "/order-splits/receipt-preview", json={"factory_id": "huaxing", "lines": [
        {"order_line_id": order["lines"][0]["id"], "effective_quantity": qty}]})
    assert result.status_code == 200, result.text
    return result.json()


def receive(client, order, qty, *, price="1", token="", post=True, rejected="0"):
    result = client.post(BASE + "/receipts", json={"factory_id": "huaxing", "delivery_note_no": "DN-" + uuid4().hex,
        "delivery_date": "2026-08-05", "acceptance_date": "2026-08-05", "post_immediately": post,
        "request_id": uuid4().hex, "split_confirmation": token, "lines": [{"order_line_id": order["lines"][0]["id"],
        "delivered_quantity": qty, "received_quantity": qty, "rejected_quantity": rejected, "unit_price": price}]})
    return result


def balances(client):
    response = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def valuation():
    from app.db import SessionLocal
    from app.services.carton_inventory_valuation import load_valuation
    with SessionLocal() as db:
        return load_valuation(db, "huaxing")


def test_pending_split_receives_in_parts_and_preserves_one_purchase_and_receipt_source(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        body = split_body(order)
        plan = save(client, order, body)
        assert plan["status"] == "ACTIVE"
        assert save(client, order, body)["id"] == plan["id"]
        assert context(client, order)["lines"][0]["pending_available"] == "6.0000"
        assert receive(client, order, "3").status_code == 409
        token = preview(client, order, "3")["confirmation"]
        first = receive(client, order, "3", token=token)
        assert first.status_code == 201, first.text
        assert first.json()["status"] == "POSTED"
        plan = context(client, order)["plans"][0]
        assert Decimal(plan["targets"][0]["lines"][0]["pending_remaining"]) == 1
        assert receive(client, order, "2", token=token).status_code == 409  # stale allocation
        second = receive(client, order, "2", token=preview(client, order, "2")["confirmation"])
        assert second.status_code == 201, second.text
        stocks = balances(client)
        child = next(row for row in stocks if row["order_line_id"].startswith("CSL-"))
        parent = next(row for row in stocks if row["order_line_id"] == order["lines"][0]["id"])
        assert Decimal(child["balance"]) == 4 and Decimal(parent["balance"]) == 1
        assert child["contract_no"] == "NEW-CONTRACT" and child["cost_status"] == "已计价"
        assert Decimal(latest(client)["lines"][0]["received_quantity"]) == 5
        report = client.get(BASE + "/inventory/report", params={"factory_id": "huaxing"})
        assert report.status_code == 200, report.text
        child_report = next(row for row in report.json()["order_rows"] if row["order_line_id"] == child["order_line_id"])
        timeline = client.get(BASE + "/inventory/order-timeline", params={"factory_id": "huaxing", "inventory_key": child_report["key"]})
        assert timeline.status_code == 200, timeline.text
        assert {row["contract_no"] for row in timeline.json()["events"]} == {"NEW-CONTRACT"}
        assert len(timeline.json()["events"]) == 2
        assert sum(Decimal(row["quantity_change"]) for row in timeline.json()["events"]) == 4
        parent_timeline = client.get(BASE + "/inventory/order-timeline", params={"factory_id": "huaxing", "order_id": order["id"]})
        assert any(row["event_label"] == "记录拆单方案" for row in parent_timeline.json()["events"])
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonPurchaseOrderIssue, CartonReceipt
        from app.services.carton_supplier_settlement import sources
        from sqlalchemy import select
        with SessionLocal() as db:
            assert len(list(db.scalars(select(CartonOrder)))) == 1
            assert len(list(db.scalars(select(CartonPurchaseOrderIssue)))) == 1
            assert len(list(db.scalars(select(CartonReceipt)))) == 2
            evidence = sources(db, "huaxing", order["supplier_id"], "2026-08", "CNY")
            assert len(evidence[0]) == 2  # adjustments do not become another payable
        value = valuation()
        assert value.errors == []
        assert sum(pool.quantity for pool in value.balances.values()) == 5
        assert sum(pool.amount for pool in value.balances.values()) == 5


def test_stock_split_requires_warehouse_confirmation_conserves_fractional_cost_and_undo(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        assert receive(client, order, "3", price="1").status_code == 201
        assert receive(client, order, "6", price="2").status_code == 201
        order = latest(client)
        position = context(client, order)["lines"][0]["positions"][0]
        stock = [{"location_id": position["location_id"], "expected_position_revision": position["position_revision"], "quantity": "4"}]
        plan = save(client, order, split_body(order, pending="0", stock=stock))
        assert plan["status"] == "PENDING_WAREHOUSE"
        assert sum(Decimal(row["balance"]) for row in balances(client)) == 9
        assert receive(client, order, "1").status_code == 409
        login_as(client, "qc_inspector")
        assert action(client, plan, "confirm").status_code == 403
        login_as(client, "warehouse_keeper")
        result = action(client, plan, "confirm")
        assert result.status_code == 200, result.text
        plan = result.json()
        assert plan["status"] == "ACTIVE"
        value = valuation()
        assert value.errors == []
        assert sum(pool.quantity for pool in value.balances.values()) == 9
        assert abs(sum(pool.amount for pool in value.balances.values()) - 15) < Decimal("1e-24")
        assert all(row["cost_status"] == "已计价" for row in balances(client))
        result = action(client, plan, "cancel")
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "CANCELLED"
        value = valuation()
        assert value.errors == []
        assert abs(sum(pool.amount for pool in value.balances.values()) - 15) < Decimal("1e-24")


def test_mixed_split_short_receipt_uses_only_effective_quantity_and_can_issue_child_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        assert receive(client, order, "3").status_code == 201
        order = latest(client)
        position = context(client, order)["lines"][0]["positions"][0]
        plan = save(client, order, split_body(order, pending="2", stock=[{
            "location_id": position["location_id"], "expected_position_revision": position["position_revision"], "quantity": "2"}]))
        result = action(client, plan, "confirm")
        assert result.status_code == 200, result.text
        plan = result.json()
        incoming = receive(client, order, "2", rejected="1", token=preview(client, order, "1")["confirmation"])
        assert incoming.status_code == 201, incoming.text
        record = context(client, order)["plans"][0]
        assert Decimal(record["targets"][0]["lines"][0]["pending_remaining"]) == 1
        child = next(row for row in balances(client) if row["order_line_id"].startswith("CSL-"))
        issue = client.post(BASE + "/inventory/movements", json={"factory_id": "huaxing", "request_id": uuid4().hex,
            "order_line_id": child["order_line_id"], "location_id": child["location_id"], "quantity": "1", "movement_type": "OUTBOUND",
            "document_no": "OUT-SPLIT", "reason": "客户车间领用", "issue_kind": "USAGE"})
        assert issue.status_code == 201, issue.text
        assert action(client, record, "cancel").status_code == 409
        # Parent demand and original receipt evidence still exist.
        assert Decimal(latest(client)["lines"][0]["required_quantity"]) == 10
        assert Decimal(latest(client)["lines"][0]["received_quantity"]) == 4
        assert valuation().errors == []


@pytest.mark.parametrize("kind", ["pending", "stock", "rounding", "foreign_line", "duplicate", "stale"])
def test_invalid_split_is_atomic(monkeypatch, kind):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        body = split_body(order)
        if kind == "pending":
            body["targets"][0].update(product_quantity="110")
            body["targets"][0]["lines"][0]["pending_quantity"] = "11"
        elif kind == "stock":
            body["targets"][0]["lines"][0].update(pending_quantity="0", stock=[{
                "location_id": "FOREIGN-LOCATION", "expected_position_revision": 1, "quantity": "4"}])
        elif kind == "rounding":
            body["targets"][0].update(product_quantity="41")
            body["targets"][0]["lines"][0]["pending_quantity"] = "5"
        elif kind == "foreign_line":
            body["targets"][0]["lines"][0]["order_line_id"] = "FOREIGN-LINE"
        elif kind == "duplicate":
            body["targets"][0].update(contract_no=order["contract_no"], customer_po=order["customer_po"])
        else:
            body["expected_revision"] = 99
        result = client.post(BASE + f"/orders/{order['order_no']}/splits", json=body)
        assert result.status_code in {409, 404}, result.text
        assert context(client, order)["plans"] == []
        assert latest(client)["revision"] == order["revision"]


def test_split_permissions_factory_and_request_conflict(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        body = split_body(order)
        login_as(client, "qc_inspector")
        assert client.post(BASE + f"/orders/{order['order_no']}/splits", json=body).status_code == 403
        login_as(client, "admin")
        assert client.post(BASE + f"/orders/{order['order_no']}/splits", json={**body, "factory_id": "huadeng"}).status_code == 404
        plan = save(client, order, body)
        changed = {**body, "reason": "另外一个操作理由"}
        assert client.post(BASE + f"/orders/{order['order_no']}/splits", json=changed).status_code == 409
        assert action(client, plan, "cancel", factory_id="huadeng").status_code == 404
        assert client.post(BASE + f"/orders/{order['order_no']}/reduce", json={"factory_id": "huaxing", "expected_revision": latest(client)["revision"], "reduction_quantity": "10"}).status_code == 409


def test_explicit_historical_demand_splits_without_inventing_product_quantity(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch, explicit=True)
        plan = save(client, order, split_body(order, product=None))
        assert plan["targets"][0]["product_quantity"] is None
        assert latest(client)["product_order_quantity"] is None
        assert action(client, plan, "cancel").status_code == 200
        assert context(client, order)["lines"][0]["pending_available"] == "10.0000"


def test_multiple_targets_use_separate_receipt_allocations_and_cancel_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        body = split_body(order, pending="2", product="20")
        other = split_body(order, pending="3", product="30", contract="SECOND-CONTRACT")["targets"][0]
        body["targets"].append(other)
        plan = save(client, order, body)
        proposed = preview(client, order, "4")
        assert [Decimal(row["quantity"]) for row in proposed["allocations"]] == [2, 2]
        result = receive(client, order, "4", token=proposed["confirmation"])
        assert result.status_code == 201, result.text
        assert len([row for row in balances(client) if row["order_line_id"].startswith("CSL-")]) == 2
        record = context(client, order)["plans"][0]
        assert [Decimal(target["lines"][0]["pending_remaining"]) for target in record["targets"]] == [0, 1]
        assert action(client, record, "cancel").status_code == 200
        stock = [row for row in balances(client) if Decimal(row["balance"]) > 0]
        assert len(stock) == 1 and Decimal(stock[0]["balance"]) == 4
        assert valuation().errors == []
        assert context(client, order)["lines"][0]["pending_available"] == "6.0000"


def test_schedule_split_matches_and_later_cancellation_reminds_without_duplicate_procurement(monkeypatch):
    from test_carton_item_schedule import workbook, source_row
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        plan = save(client, order, split_body(order))
        row = source_row(contract="NEW-CONTRACT", item=order["item_no"], qty=40)
        row[3] = "NEW-PO"
        direct = _order_payload()
        direct.update(contract_no="NEW-CONTRACT", customer_po="NEW-PO", product_order_quantity="40")
        assert client.post(BASE + "/orders", json=direct).status_code == 409
        initial_cancel = client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"}, data={"customer_code": "DICKIE"},
            files={"file": ("initial-cancel.xlsx", workbook([["退单"], row]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert initial_cancel.status_code == 201, initial_cancel.text
        initial_source = initial_cancel.json()["parse_summary"]["rows"][0]
        assert initial_source["split_id"] == plan["id"] and initial_source["order_id"] == order["id"]
        assert initial_source["schedule_change"] == "CANCELLED_AFTER_ORDER"
        response = client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"}, data={"customer_code": "DICKIE"},
            files={"file": ("schedule.xlsx", workbook([row]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert response.status_code == 201, response.text
        batch = response.json()
        source = batch["parse_summary"]["rows"][0]
        assert source["split_id"] == plan["id"] and source["order_id"] == order["id"]
        assert source["procurement_state"] == "ORDERED"
        new_body = _order_payload()
        new_body.update(contract_no="NEW-CONTRACT", item_no=order["item_no"], product_order_quantity="40",
            schedule_source={"batch_id": batch["id"], "source_sheet": source["source_sheet"], "source_row": source["source_row"]})
        assert client.post(BASE + "/orders", json=new_body).status_code == 409
        cancelled = client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"}, data={"customer_code": "DICKIE"},
            files={"file": ("cancelled.xlsx", workbook([["退单"], row]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert cancelled.status_code == 201, cancelled.text
        changed = cancelled.json()["parse_summary"]["rows"][0]
        assert changed["schedule_change"] == "CANCELLED_AFTER_ORDER"
        assert latest(client)["status"] == "PENDING_SUPPLIER"


def test_supplier_import_keeps_original_note_and_allocates_only_accepted_split_quantity(monkeypatch):
    import json
    from test_carton_supplier_portal import setup_portal, accept_all, _dongkang_delivery_file, receive_payload
    portal = "/api/carton-supplier"
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        supplier_order = accept_all(client)
        login_as(client, "warehouse_keeper")
        body = split_body(order, pending="1", product="120")
        body["targets"][0]["lines"].append({"order_line_id": order["lines"][1]["id"], "pending_quantity": "120", "stock": []})
        plan = save(client, order, body)
        from test_carton_supplier_portal import supplier_login
        supplier_login(client)
        upload = {"file": ("东康送货.xlsx", _dongkang_delivery_file(supplier_order, source_price=2))}
        candidate = client.post(portal + "/shipments/import-preview", files=upload)
        assert candidate.status_code == 200, candidate.text
        form = {"sha256": candidate.json()["sha256"], "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "DK-IMPORT-01"}])}
        sent = client.post(portal + "/shipments/import-confirm", data=form, files=upload)
        assert sent.status_code == 200, sent.text
        shipment = sent.json()["shipments"][0]
        assert shipment["status"] == "SENT"
        assert all(line["contract_no"] == order["contract_no"] for line in shipment["lines"])
        login_as(client, "warehouse_keeper")
        incoming = receive_payload(client, shipment)
        preview_response = client.post(BASE + "/order-splits/receipt-preview", json={"factory_id": "huaxing", "lines": [
            {"order_line_id": line["order_line_id"], "effective_quantity": "8"} for line in shipment["lines"]]})
        assert preview_response.status_code == 200, preview_response.text
        endpoint = portal + f"/internal/shipments/{shipment['id']}/receive"
        assert client.post(endpoint, json=incoming).status_code == 409
        assert client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["total"] == 0
        incoming["split_confirmation"] = preview_response.json()["confirmation"]
        accepted = client.post(endpoint, json=incoming)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["delivery_note_no"] == "DK-IMPORT-01"
        assert client.post(endpoint, json=incoming).json()["receipt_id"] == accepted.json()["receipt_id"]
        record = context(client, order)["plans"][0]
        assert record["id"] == plan["id"]
        assert [Decimal(line["received_quantity"]) for line in record["targets"][0]["lines"]] == [1, 8]
        value = valuation()
        assert value.errors == []
        assert sum(pool.quantity for pool in value.balances.values()) == 16
        assert sum(pool.amount for pool in value.balances.values()) == 32
