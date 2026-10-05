"""Current-issue supplier acknowledgement visible to authorized procurement readers."""
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order
from test_carton_supplier_portal import setup_portal, supplier_login, accept_all, BASE


def internal_order(client, order_no):
    login_as(client, "warehouse_keeper")
    response = client.get("/api/carton-procurement/orders", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["items"] if row["order_no"] == order_no)


def accept_paper(client, order, line, revision=0):
    supplier_login(client)
    response = client.put(BASE + f"/papers/{line['id']}/commitment", json={
        "factory_id": "huaxing", "issue_id": order["issue_id"],
        "expected_revision": revision, "promised_date": "2026-09-23"})
    assert response.status_code == 200, response.text


def test_internal_ledger_tracks_partial_and_complete_supplier_acceptance(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        assert client.get("/api/carton-procurement/orders", params={"factory_id": "huaxing"}).status_code == 403
        order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        pending = internal_order(client, raw["order_no"])
        assert pending["status"] == "PENDING_SUPPLIER"
        assert pending["supplier_acceptance"] == {
            "status": "PENDING", "label": "供应商待接单", "issue_id": order["issue_id"],
            "document_no": order["document_no"], "total_line_count": 2,
            "accepted_line_count": 0, "accepted_at": ""}

        accept_paper(client, order, order["lines"][0])
        partial = internal_order(client, raw["order_no"])["supplier_acceptance"]
        assert partial["status"] == "PARTIAL" and partial["accepted_line_count"] == 1
        assert partial["total_line_count"] == 2 and partial["accepted_at"]

        accept_paper(client, order, order["lines"][1])
        accepted = internal_order(client, raw["order_no"])
        assert accepted["supplier_acceptance"]["status"] == "ACCEPTED"
        assert accepted["supplier_acceptance"]["accepted_line_count"] == 2
        assert accepted["status"] == pending["status"]
        assert accepted["revision"] == pending["revision"]
        assert all(float(line["received_quantity"]) == 0 for line in accepted["lines"])
        assert client.get("/api/carton-procurement/orders", params={"factory_id": "huakang-a"}).status_code == 403


def test_old_acceptance_does_not_confirm_unissued_or_new_purchase_changes(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        previous = accept_all(client)
        assert internal_order(client, raw["order_no"])["supplier_acceptance"]["status"] == "ACCEPTED"
        login_as(client, "admin")
        response = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": raw["revision"],
            "additional_quantity": 120, "reason": "客户追加需要重新确认"})
        assert response.status_code == 200, response.text
        changed = response.json()
        summary = changed["supplier_acceptance"]
        assert summary["status"] == "PENDING_CHANGE" and summary["accepted_line_count"] == 0
        assert summary["accepted_at"] == "" and summary["issue_id"] == previous["issue_id"]
        issued = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": changed["revision"]})
        assert issued.status_code == 200, issued.text
        pending = internal_order(client, raw["order_no"])["supplier_acceptance"]
        assert pending["status"] == "PENDING" and pending["accepted_line_count"] == 0
        assert pending["issue_id"] != previous["issue_id"] and pending["accepted_at"] == ""
        supplier_login(client)
        current = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        for line in current["lines"]:
            accept_paper(client, current, line, revision=line["commitment_revision"])
        assert internal_order(client, raw["order_no"])["supplier_acceptance"]["status"] == "ACCEPTED"


def test_drafts_cancelled_orders_and_zero_demand_have_explicit_acceptance_states(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        login_as(client, "admin")
        draft = _create_order(client, submit_supplier=False)
        assert draft["supplier_acceptance"]["status"] == "NOT_ISSUED"
        assert draft["supplier_acceptance"]["accepted_at"] == ""
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonOrderLine
        with SessionLocal() as db:
            db.get(CartonOrderLine, raw["lines"][1]["id"]).required_quantity = 0
            db.commit()
        issued = client.post(f"/api/carton-procurement/orders/{raw['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": raw["revision"]})
        assert issued.status_code == 200, issued.text
        supplier_login(client)
        current = next(row for row in client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"]
            if row["order_no"] == raw["order_no"])
        accept_paper(client, current, current["lines"][0])
        summary = internal_order(client, raw["order_no"])["supplier_acceptance"]
        assert summary["status"] == "ACCEPTED" and summary["total_line_count"] == summary["accepted_line_count"] == 1
        with SessionLocal() as db:
            db.get(CartonOrder, raw["id"]).status = "CANCELLED"
            db.commit()
        cancelled = internal_order(client, raw["order_no"])["supplier_acceptance"]
        assert cancelled["status"] == "CANCELLED" and cancelled["accepted_line_count"] == 0
