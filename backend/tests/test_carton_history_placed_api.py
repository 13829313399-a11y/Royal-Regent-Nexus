from test_carton_history_preview_api import upload, BASE
from test_carton_history_wide import workbook, row, MINIMAL_HEADERS
from test_carton_history_identity_api import _customer, _orders
from test_molding_sample_api import make_client, login_as
from test_carton_direct_receipt_api import payload


def test_history_skips_purchase_and_completes_material_per_received_line(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _customer(client, "迪奇")
        content = workbook([row(内箱需求数量=20)], MINIMAL_HEADERS)
        preview = upload(client, content).json()
        result = upload(client, content, preview=False, fingerprint=preview["source_fingerprint"])
        assert result.status_code == 201, result.text
        order = _orders(client)[0]
        assert order["status"] == "PENDING_SUPPLIER"
        context = client.get(f"{BASE}/orders/{order['order_no']}/purchase-order-context", params={"factory_id": "huaxing"}).json()
        assert context["historical_baseline"] and context["pending_type"] == "NONE"
        assert not context["can_generate"] and context["issues"] == []
        body = payload(order)
        body["lines"] = body["lines"][:1]
        rejected = client.post(BASE + "/receipts", json=body)
        assert rejected.status_code == 422 and "纸质" in rejected.text
        body["lines"][0].update(paper_quality="A33", specification="30*20*15", unit_price=0)
        rejected = client.post(BASE + "/receipts", json=body)
        assert rejected.status_code == 422 and "单价" in rejected.text
        assert _orders(client)[0]["lines"][0]["paper_quality"] == ""
        body["lines"][0]["unit_price"] = 2
        result = client.post(BASE + "/receipts", json=body)
        assert result.status_code == 201, result.text
        assert result.json()["status"] == "POSTED"
        updated = _orders(client)[0]
        assert updated["status"] == "PARTIALLY_RECEIVED"
        assert updated["lines"][0]["paper_quality"] == "A33"
        assert updated["lines"][1]["paper_quality"] == ""
        assert client.post(BASE + "/receipts", json=body).json()["id"] == result.json()["id"]
        context = client.get(f"{BASE}/orders/{order['order_no']}/purchase-order-context", params={"factory_id": "huaxing"}).json()
        assert context["pending_type"] == "NONE"
        assert client.get(BASE + "/inventory/movements", params={"factory_id": "huaxing"}).json()["total"] == 1
