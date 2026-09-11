from decimal import Decimal
from io import BytesIO
from openpyxl import load_workbook
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order, _freeze_carton_time


def explicit_payload():
    data = _order_payload()
    data.update(quantity_basis="EXPLICIT", product_order_quantity=None, customer_due_date="2026-08-20", due_date="2026-08-12")
    data["lines"] = [{**data["lines"][0], "usage_quantity": None, "required_quantity": "100"},
                     {**data["lines"][1], "usage_quantity": None, "required_quantity": "20"}]
    return data


def create(client, payload):
    response = client.post("/api/carton-procurement/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_explicit_unknown_quantities_preserve_demand_and_require_complete_materials(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        login_as(client, "carton_supervisor")
        data = explicit_payload()
        data["lines"][0]["paper_quality"] = ""
        order = create(client, data)
        assert order["quantity_basis"] == "EXPLICIT"
        assert order["product_order_quantity"] is None
        assert order["maximum_reducible_quantity"] is None
        assert order["due_date"] == "2026-08-12"
        assert order["customer_due_date"] == "2026-08-20"
        assert order["lines"][0]["usage_quantity"] is None
        assert Decimal(order["lines"][0]["required_quantity"]) == 100
        bad = client.post(f"/api/carton-procurement/orders/{order['order_no']}/submit-supplier", json={"factory_id":"huaxing","expected_revision":order["revision"]})
        assert bad.status_code == 422, bad.text
        update = {**data, "expected_revision":order["revision"], "reason":"补全历史纸质资料"}
        update["lines"][0]["paper_quality"] = "K3K"
        response = client.patch(f"/api/carton-procurement/orders/{order['order_no']}", json=update)
        assert response.status_code == 200, response.text
        order = _submit_order(client, response.json())
        issue = client.post(f"/api/carton-procurement/orders/{order['order_no']}/purchase-order-issues.xlsx", json={"factory_id":"huaxing","expected_revision":order["revision"]})
        assert issue.status_code == 200, issue.text
        workbook = load_workbook(BytesIO(issue.content), data_only=True)
        cells = [cell.value for row in workbook.active for cell in row]
        assert "待完善" in cells
        context = client.get(f"/api/carton-procurement/orders/{order['order_no']}/purchase-order-context", params={"factory_id":"huaxing"})
        assert context.status_code == 200, context.text
        assert context.json()["issues"][0]["after_product_quantity"] is None
        # Null packing quantities must never become selectable standard configurations.
        from app import db as app_db
        from app.models.carton_master import CartonMasterRecord
        from sqlalchemy import select
        with app_db.SessionLocal() as db:
            assert not list(db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.kind == "CONFIG")))


def test_explicit_adjustments_protect_pending_receipts_and_issue_real_paper_deltas(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        login_as(client, "carton_supervisor")
        order = _submit_order(client, create(client, explicit_payload()))
        url = f"/api/carton-procurement/orders/{order['order_no']}"
        def issue():
            response = client.post(url+"/purchase-order-issues.xlsx", json={"factory_id":"huaxing","expected_revision":order["revision"]})
            assert response.status_code == 200, response.text
        issue()
        receipt = client.post("/api/carton-procurement/receipts", json={"factory_id":"huaxing", "delivery_note_no":"EXPLICIT-DN", "delivery_date":"2026-08-05", "acceptance_date":"2026-08-05", "lines":[{"order_line_id":order["lines"][0]["id"],"delivered_quantity":"40","received_quantity":"40","location":""}]})
        assert receipt.status_code == 201, receipt.text
        def adjust(action, quantities):
            return client.post(url+"/"+action, json={"factory_id":"huaxing", "expected_revision":order["revision"],"line_quantities":[{"order_line_id":line["id"],"required_quantity":str(q)} for line,q in zip(order["lines"], quantities)]})
        assert adjust("reduce", [39, 20]).status_code == 409
        bad = client.post(url+"/append", json={"factory_id":"huaxing","expected_revision":order["revision"],"additional_quantity":"10"})
        assert bad.status_code == 422
        response = adjust("append", [120,20]); assert response.status_code == 200, response.text
        order = response.json(); assert order["product_order_quantity"] is None
        issue()
        response = adjust("reduce", [40,0]); assert response.status_code == 200, response.text
        order = response.json()
        assert Decimal(order["lines"][1]["required_quantity"]) == 0
        assert order["status"] == "PENDING_SUPPLIER"
        issue()
        response = client.post(f"/api/carton-procurement/receipts/{receipt.json()['id']}/confirm", json={"factory_id":"huaxing","expected_revision":receipt.json()["revision"]})
        assert response.status_code == 200, response.text
        orders = client.get("/api/carton-procurement/orders", params={"factory_id":"huaxing"}).json()["items"]
        assert orders[0]["status"] == "COMPLETED"
        order = orders[0]
        context = client.get(url+"/purchase-order-context", params={"factory_id":"huaxing"}).json()
        assert [entry["document_type"] for entry in context["issues"]] == ["REDUCE","APPEND","INITIAL"]
        statement = client.get("/api/carton-procurement/supplier-settlements/workspace", params={"factory_id":"huaxing", "period":"2026-08", "currency":"CNY"})
        assert statement.status_code == 200, statement.text
        assert len(statement.json()["sources"]) == 1
        assert Decimal(statement.json()["sources"][0]["quantity"]) == 40
        assert Decimal(statement.json()["sources"][0]["amount"]) == Decimal("138.40")
        response = adjust("append", [41,0]); assert response.status_code == 200, response.text
        assert response.json()["status"] == "PARTIALLY_RECEIVED"
