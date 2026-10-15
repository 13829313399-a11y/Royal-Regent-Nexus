"""The six standards keep independent identities across the existing supplier chain."""
from copy import deepcopy
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import setup_portal, supplier_login, ship_payload, receive_payload


def test_standard_boxes_and_cards_reach_supplier_receipt_and_monthly_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        names = ["普通箱", "半翼箱", "平卡", "刀卡", "压线卡", "啤卡"]
        body = _order_payload(); body.update(customer_po="STANDARD-PO", item_no="STANDARD-PAPERS")
        original = body["lines"][0]
        body["lines"] = [{**deepcopy(original), "packaging_type": name, "unit": "个" if index < 2 else "张"} for index, name in enumerate(names)]
        created = client.post("/api/carton-procurement/orders", json=body)
        assert created.status_code == 201, created.text
        order = _submit_order(client, created.json())
        supplier_login(client)
        workspace = client.get("/api/carton-supplier/workspace", params={"factory_id": "huaxing"}).json()
        supplier_order = next(row for row in workspace["orders"] if row["order_no"] == order["order_no"])
        assert {line["packaging_type"] for line in supplier_order["lines"]} == set(names)
        for line in supplier_order["lines"]:
            accepted = client.put(f"/api/carton-supplier/papers/{line['id']}/commitment", json={
                "factory_id": "huaxing", "issue_id": supplier_order["issue_id"], "expected_revision": 0, "promised_date": "2026-09-23"})
            assert accepted.status_code == 200, accepted.text
        sent = client.post("/api/carton-supplier/shipments", json=ship_payload(supplier_order))
        assert sent.status_code == 201, sent.text
        shipment = sent.json()
        login_as(client, "admin")
        posted = client.post(f"/api/carton-supplier/internal/shipments/{shipment['id']}/receive", json=receive_payload(client, shipment))
        assert posted.status_code == 200, posted.text
        monthly = client.get("/api/carton-procurement/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": "2026-09"})
        assert monthly.status_code == 200, monthly.text
        sources = monthly.json()["sources"]
        assert {row["packaging_type"] for row in sources} == set(names)
        assert all(row["quantity"] == "8.0000" or float(row["quantity"]) == 8 for row in sources)
        assert len({row["source_key"] for row in sources}) == 6
