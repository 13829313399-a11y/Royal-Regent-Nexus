from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from test_carton_procurement_api import _ensure_dickie_customer, _freeze_carton_time, _history_inventory_workbook_bytes
from test_molding_sample_api import make_client, login_as


def test_stocktake_real_api_permissions_factory_cutoff_and_concurrent_review(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _ensure_dickie_customer(client)
        _freeze_carton_time(monkeypatch)
        content = _history_inventory_workbook_bytes([[
            "COUNT-1", "Dickie", "", "COUNT-C", "COUNT-I", "外箱", "A33", "1*1*1",
            "个", 100, 2, "CNY", "A-01", "2026-08-01", "OPEN-COUNT", "", None,
        ]])
        response = client.post("/api/carton-procurement/inventory/history-imports", params={"factory_id": "huaxing"},
                               files={"file": ("stock.xlsx", content)})
        assert response.status_code == 201, response.text
        balance = client.get("/api/carton-procurement/inventory/balances", params={"factory_id": "huaxing"}).json()[0]
        response = client.post("/api/carton-procurement/stocktakes", json={"factory_id": "huaxing", "reference_movement_ids": [balance["latest_movement_id"]]})
        assert response.status_code == 201, response.text
        doc = response.json()
        assert isinstance(doc["lines"][0]["current_quantity"], str)
        path = f"/api/carton-procurement/stocktakes/{doc['id']}"
        values = dict(factory_id="huaxing", expected_revision=doc["revision"], action="SUBMIT",
                      ledger_token=doc["ledger_token"], cutoff_acknowledged=True,
                      lines=[{"id": doc["lines"][0]["id"], "actual_quantity": "98", "reason": "盘点短少两箱"}])
        response = client.post(path + "/actions", json=values)
        assert response.status_code == 200, response.text
        doc = response.json()
        approve = dict(factory_id="huaxing", expected_revision=doc["revision"], action="APPROVE")
        assert client.post(path + "/actions", json=approve).status_code == 403
        outbound = client.post("/api/carton-procurement/inventory/movements", json={"request_id": uuid4().hex,
            "factory_id": "huaxing", "reference_movement_id": balance["latest_movement_id"],
            "movement_type": "OUTBOUND", "quantity": "10", "document_no": "AFTER-COUNT", "reason": "客户要货"})
        assert outbound.status_code == 201, outbound.text
        login_as(client, "qc_inspector")
        assert client.post(path + "/actions", json=approve).status_code == 403
        login_as(client, "admin")
        assert client.get(path, params={"factory_id": "huadeng"}).status_code == 404
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(path + "/actions", json=approve), range(2)))
        assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
        posted = client.get(path, params={"factory_id": "huaxing"}).json()
        assert posted["status"] == "POSTED" and posted["reviewed_by"] != posted["created_by"]
        assert Decimal(posted["lines"][0]["current_quantity"]) == 88
        assert len([event for event in posted["events"] if event["action"] == "STOCKTAKE_APPROVE"]) == 1
        client.cookies.clear()
        assert client.get(path, params={"factory_id": "huaxing"}).status_code == 401
