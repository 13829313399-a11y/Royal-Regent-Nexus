from uuid import uuid4

import pytest

from test_carton_procurement_api import (
    _create_order, _create_receipt, _ensure_dickie_customer, _freeze_carton_time,
    _history_inventory_workbook_bytes,
)
from test_molding_sample_api import login_as, make_client


@pytest.mark.parametrize("standalone", [False, True])
def test_relocation_changes_only_current_location_and_preserves_history(monkeypatch, standalone):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        if standalone:
            _ensure_dickie_customer(client)
            content = _history_inventory_workbook_bytes([[
                "RELOCATION-OLD-1", "Dickie", "", "", "ITEM-1", "外箱", "A33",
                "1*1*1", "个", 100, 1, "CNY", "A-01", "2025-08-05", "OPEN-1", "", None,
            ]])
            response = client.post("/api/carton-procurement/inventory/history-imports",
                                   params={"factory_id": "huaxing"},
                                   files={"file": ("opening.xlsx", content)})
            assert response.status_code == 201, response.text
        else:
            receipt = _create_receipt(client, _create_order(client))
            response = client.post(f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
                                   json={"factory_id": "huaxing", "expected_revision": receipt["revision"]})
            assert response.status_code == 200, response.text

        path = "/api/carton-procurement/inventory"
        params = {"factory_id": "huaxing"}
        before = client.get(f"{path}/balances", params=params).json()[0]
        movements = client.get(f"{path}/movements", params=params).json()
        payload = {**params, "reference_movement_id": before["latest_movement_id"],
                   "expected_location_revision": 0, "location": " B-02 ", "note": "整理仓位"}
        empty = client.post(f"{path}/relocations", json={**payload, "location": "   "})
        assert empty.status_code == 422
        relocated = client.post(f"{path}/relocations", json=payload)
        assert relocated.status_code == 200, relocated.text
        after = relocated.json()
        assert after["latest_location"] == "B-02"
        assert after["location_revision"] > 0
        for key in before.keys() - {"latest_location", "location_revision"}:
            assert after[key] == before[key], key
        assert client.get(f"{path}/movements", params=params).json() == movements
        assert client.post(f"{path}/relocations", json=payload).status_code == 409
        current = {**payload, "expected_location_revision": after["location_revision"]}
        assert client.post(f"{path}/relocations", json=current).status_code == 422

        # Same-second relocations use the persisted event sequence, not timestamps.
        second = client.post(f"{path}/relocations", json={**current, "location": "C-03"})
        assert second.status_code == 200, second.text
        assert second.json()["location_revision"] > after["location_revision"]
        audits = client.get("/api/carton-procurement/audit-events",
                            params={**params, "event_type": "INVENTORY_LOCATION_CHANGED"}).json()
        assert audits["total"] == 2
        assert audits["items"][0]["detail"]["from_location"] == "B-02"
        assert audits["items"][0]["detail"]["to_location"] == "C-03"
        assert audits["items"][0]["actor_name"]

        outbound = client.post(f"{path}/movements", json={
            "request_id": uuid4().hex,
            **params, "order_line_id": before["order_line_id"],
            "reference_movement_id": None if before["order_line_id"] else before["latest_movement_id"],
            "movement_type": "OUTBOUND", "quantity": "1", "document_no": "OUT-AFTER-MOVE",
            "reason": "客户要货", "location": "OLD-STALE-LOCATION",
        })
        assert outbound.status_code == 201, outbound.text
        assert outbound.json()["location"] == "C-03"
        balances = client.get(f"{path}/balances", params=params).json()
        matching = next(row for row in balances if row["item_no"] == before["item_no"]
                        and row["packaging_type"] == before["packaging_type"])
        assert matching["latest_location"] == "C-03"
        assert matching["latest_inbound_at"] == before["latest_inbound_at"]


def test_relocation_requires_inventory_permission_and_factory_ownership(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        receipt = _create_receipt(client, _create_order(client))
        response = client.post(f"/api/carton-procurement/receipts/{receipt['id']}/confirm",
                               json={"factory_id": "huaxing", "expected_revision": receipt["revision"]})
        assert response.status_code == 200, response.text
        balance = client.get("/api/carton-procurement/inventory/balances",
                             params={"factory_id": "huaxing"}).json()[0]
        payload = {"factory_id": "huadeng", "reference_movement_id": balance["latest_movement_id"],
                   "expected_location_revision": 0, "location": "B-02"}
        login_as(client, "admin")
        payload["factory_id"] = "huadeng"
        assert client.post("/api/carton-procurement/inventory/relocations", json=payload).status_code == 404
        payload["factory_id"] = "huaxing"
        payload["reference_movement_id"] = "NOT-FOUND"
        assert client.post("/api/carton-procurement/inventory/relocations", json=payload).status_code == 404
        payload["reference_movement_id"] = balance["latest_movement_id"]
        profile = login_as(client, "qc_inspector")
        assert "carton_procurement:inventory_write" not in profile["permissions"]
        assert client.post("/api/carton-procurement/inventory/relocations", json=payload).status_code == 403
        client.cookies.clear()
        assert client.post("/api/carton-procurement/inventory/relocations", json=payload).status_code == 401
