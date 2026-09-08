import importlib
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from test_carton_procurement_api import (
    _ensure_dickie_customer, _freeze_carton_time, _history_inventory_workbook_bytes,
)
from test_molding_sample_api import login_as, make_client


def test_concurrent_outbound_cannot_overdraw_the_same_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        content = _history_inventory_workbook_bytes([[
            "CONCURRENT-OPEN", "Dickie", "", "", "ITEM-1", "外箱", "A33",
            "1*1*1", "个", 10, 1, "CNY", "A-01", "2025-08-05", "OPEN-1", "", None,
        ]])
        base = "/api/carton-procurement/inventory"
        params = {"factory_id": "huaxing"}
        imported = client.post(base + "/history-imports", params=params, files={"file": ("opening.xlsx", content)})
        assert imported.status_code == 201, imported.text
        balance = client.get(base + "/balances", params=params).json()[0]
        service = importlib.import_module("app.services.carton_procurement")
        original = service.lock_transaction
        barrier = Barrier(2)

        def synchronized_lock(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "lock_transaction", synchronized_lock)
        def outbound(number):
            return client.post(base + "/movements", json={
                **params, "request_id": uuid4().hex, "reference_movement_id": balance["latest_movement_id"],
                "movement_type": "OUTBOUND", "quantity": "7", "location": "A-01",
                "document_no": f"OUT-{number}", "reason": "并发出库回归",
            })
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(outbound, [1, 2]))
        assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
        movements = client.get(base + "/movements", params=params).json()["items"]
        assert sum(Decimal(row["quantity"]) for row in movements) == Decimal(3)
        assert Decimal(client.get(base + "/balances", params=params).json()[0]["balance"]) == Decimal(3)
