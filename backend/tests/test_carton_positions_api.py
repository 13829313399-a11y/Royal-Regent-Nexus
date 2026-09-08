from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from uuid import uuid4

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, draft, confirm, ledger, outbound


def test_split_receipt_transfer_and_concurrent_issue_close_the_loop(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        login_as(client, "admin")
        places = []
        for warehouse, bin_code in [("一仓", "a"), ("二仓", "b"), ("三仓", "c")]:
            response = client.post(BASE + "/inventory/locations", json={"factory_id": " huaxing ", "warehouse": warehouse, "bin_code": bin_code})
            assert response.status_code == 201, response.text
            assert response.json()["factory_id"] == "huaxing"
            places.append(response.json())
        a, b, c = places
        login_as(client, "warehouse_keeper")
        allocations = [{"location_id": a["id"], "quantity": "7"}, {"location_id": b["id"], "quantity": "3"}]
        lines = [{"order_line_id": row["lines"][0]["id"], "delivered_quantity": "10", "received_quantity": "10", "unit_price": "2", "location_allocations": allocations}]
        receipt = draft(client, row, 10, lines=lines)
        assert receipt.status_code == 201, receipt.text
        assert receipt.json()["lines"][0]["location_allocations"][0]["label"] == "一仓／A"
        assert confirm(client, receipt.json()).status_code == 200
        assert len(ledger(client)) == 1  # splitting locations never duplicates the receipt

        def balances():
            response = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"})
            assert response.status_code == 200, response.text
            return {r["location_id"]: r for r in response.json()}

        stocks = balances()
        transfer = {"factory_id": "huaxing", "request_id": uuid4().hex, "position_key": stocks[a["id"]]["position_key"],
                    "expected_position_revision": stocks[a["id"]]["position_revision"], "location_id": c["id"], "quantity": "2"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post(BASE + "/inventory/transfers", json=transfer), range(2)))
        assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
        assert results[0].json() == results[1].json()
        stocks = balances()
        assert stocks[c["id"]]["latest_inbound_at"] == stocks[a["id"]]["latest_inbound_at"]
        assert len(ledger(client)) == 1
        assert [D(stocks[p["id"]]["balance"]) for p in places] == [5, 3, 2]
        excessive = client.post(BASE + "/inventory/movements", json=outbound(row, 4, location_id=b["id"], issue_kind="USAGE"))
        assert excessive.status_code == 409, excessive.text

        payload = outbound(row, 2, location_id=c["id"], issue_kind="USAGE")
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(BASE + "/inventory/movements", json=payload), range(2)))
        assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
        assert responses[0].json() == responses[1].json()
        assert len(ledger(client)) == 2
        assert sum(D(r["balance"]) for r in balances().values()) == 8
        orders = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"]
        assert orders[0]["usage_status"] == "PARTIAL"
        report = client.get(BASE + "/inventory/report", params={"factory_id": "huaxing"})
        assert report.status_code == 200, report.text
        # A different factory cannot read or use the selected location.
        assert client.get(BASE + "/inventory/positions", params={"factory_id": "huadeng"}).status_code == 403
        wrong = {**transfer, "request_id": uuid4().hex, "factory_id": "huadeng"}
        assert client.post(BASE + "/inventory/transfers", json=wrong).status_code in {403, 409}
        login_as(client, "qc_inspector")
        assert client.post(BASE + "/inventory/locations", json={"factory_id": "huaxing", "warehouse": "X", "bin_code": "X"}).status_code == 403
