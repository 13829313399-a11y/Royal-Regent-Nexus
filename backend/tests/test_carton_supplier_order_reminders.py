"""Acknowledgement warnings and supplier due-date differences use current evidence."""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
import json
from openpyxl import load_workbook

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import BASE, accept_all, setup_portal, supplier_login


def purchase(client):
    return next(row for row in client.get(BASE + "/documents", params={"factory_id": "huaxing"}).json()
                if row["kind"] == "PURCHASE")


def test_legacy_unaccepted_export_retains_its_original_warning_and_never_accepts(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        with SessionLocal() as db:
            issue = db.get(CartonPurchaseOrderIssue, order["issue_id"])
            snapshot = json.loads(issue.snapshot_json)
            del snapshot["supplier_document_after_acceptance"]
            issue.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
            db.commit()
        document = purchase(client)
        selection = {"factory_id": "huaxing", "kind": "PURCHASE", "id": document["id"]}
        assert document["supplier_acceptance"]["status"] == "PENDING"
        assert client.post(BASE + "/documents/order-import.xlsx", json={"documents": [selection]}).status_code == 409
        assert purchase(client)["export_count"] == 0
        exported = client.post(BASE + "/documents/order-import.xlsx", json={
            "documents": [selection], "acknowledge_unaccepted": True})
        assert exported.status_code == 200, exported.text
        after = purchase(client)
        assert after["export_count"] == 1 and after["supplier_acceptance"]["status"] == "PENDING"
        assert all(not line["accepted"] for line in client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]["lines"])


def test_partial_and_full_acceptance_compare_each_paper_due_date_without_overwriting_plan(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        planned = date.fromisoformat(order["planned_date"])
        for index, line in enumerate(order["lines"]):
            response = client.put(BASE + f"/papers/{line['id']}/commitment", json={
                "factory_id": "huaxing", "issue_id": order["issue_id"], "expected_revision": 0,
                "promised_date": (planned + timedelta(days=-1 if index == 0 else 2)).isoformat()})
            assert response.status_code == 200, response.text
            selection = {"factory_id": "huaxing", "kind": "PURCHASE", "id": order["issue_id"]}
            exported = client.post(BASE + "/documents/order-import.xlsx", json={"documents": [selection]})
            assert exported.status_code == (404 if index == 0 else 200), exported.text
        summary = purchase(client)["supplier_acceptance"]
        assert summary["status"] == "ACCEPTED"
        assert sorted(row["difference_days"] for row in summary["delivery_differences"]) == [-1, 2]
        login_as(client, "warehouse_keeper")
        internal = next(row for row in client.get("/api/carton-procurement/orders", params={"factory_id": "huaxing"}).json()["items"]
                        if row["order_no"] == raw["order_no"])
        assert internal["due_date"] == order["planned_date"]
        assert internal["supplier_acceptance"]["delivery_differences"] == summary["delivery_differences"]
        supplier_login(client)
        assert client.get(BASE + "/documents", params={"factory_id": "huakang-a"}).status_code == 403


def test_old_issue_acceptance_cannot_authorize_changed_or_historical_import(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        accept_all(client)
        old = purchase(client)
        login_as(client, "admin")
        changed = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": raw["revision"], "additional_quantity": 120,
            "reason": "客户追加需要新版本接单"})
        assert changed.status_code == 200, changed.text
        supplier_login(client)
        assert purchase(client)["supplier_acceptance"]["status"] == "PENDING_CHANGE"
        login_as(client, "admin")
        issued = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/purchase-order-issues.xlsx", json={
            "factory_id": "huaxing", "expected_revision": changed.json()["revision"]})
        assert issued.status_code == 200, issued.text
        supplier_login(client)
        rows = client.get(BASE + "/documents", params={"factory_id": "huaxing"}).json()
        assert len(rows) == 1
        old = next(row for row in rows if row["id"] == old["id"])
        assert old["supplier_acceptance"]["status"] == "HISTORICAL"
        response = client.post(BASE + "/documents/order-import.xlsx", json={"documents": [
            {"factory_id": "huaxing", "kind": "PURCHASE", "id": old["id"]}]})
        assert response.status_code == 409 and "旧版本" in response.text


def test_first_accepted_change_exports_current_full_demand_when_initial_document_never_opened(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        initial_id = workspace["orders"][0]["issue_id"]
        login_as(client, "admin")
        changed = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": raw["revision"], "additional_quantity": 120,
            "reason": "首次接单前客户追加", "issue_to_supplier": True,
        })
        assert changed.status_code == 200, changed.text
        supplier_login(client)
        assert client.get(BASE + "/documents", params={"factory_id": "huaxing"}).json() == []
        current = accept_all(client)
        document = purchase(client)
        assert document["id"] == current["issue_id"] != initial_id
        expected = [Decimal(line["required_quantity"]) for line in current["lines"]]
        assert [Decimal(line["change_quantity"]) for line in document["lines"]] == expected
        selection = {"factory_id": "huaxing", "kind": "PURCHASE", "id": document["id"]}
        exported = client.post(BASE + "/documents/order-import.xlsx", json={"documents": [selection]})
        assert exported.status_code == 200, exported.text
        with BytesIO(exported.content) as stream:
            book = load_workbook(stream, read_only=True, data_only=True)
            assert [Decimal(str(row[6])) for row in list(book.active.values)[1:]] == expected
            book.close()
        response = client.post(BASE + "/documents/order-import.xlsx", json={
            "documents": [{**selection, "id": initial_id}], "acknowledge_unaccepted": True,
        })
        assert response.status_code == 404
