from decimal import Decimal

from test_carton_procurement_api import (
    _ensure_dickie_customer, _freeze_carton_time, _history_inventory_workbook_bytes,
)
from test_molding_sample_api import login_as, make_client


def test_pricing_api_permission_factory_scope_and_recheck_workflow(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _ensure_dickie_customer(client)
        _freeze_carton_time(monkeypatch)
        content = _history_inventory_workbook_bytes([[
            "PRICE-OLD-1", "Dickie", "", "C-PRICE", "ITEM-1", "外箱", "A33", "1*1*1",
            "个", 100, 0, "CNY", "A-01", "2026-08-01", "OPEN-PRICE", "", None,
        ]])
        imported = client.post("/api/carton-procurement/inventory/history-imports",
                               params={"factory_id": "huaxing"}, files={"file": ("opening.xlsx", content)})
        assert imported.status_code == 201, imported.text
        login_as(client, "admin")
        generated = client.post("/api/carton-procurement/closings/generate",
                                json={"factory_id": "huaxing", "period": "2026-08"})
        assert generated.status_code == 200, generated.text
        closing = generated.json()[0]
        issue = closing["pricing_issues"][0]
        assert issue["document_no"] == "OPEN-PRICE"
        assert issue["can_price"] is True
        pending = client.post(f"/api/carton-procurement/closings/{closing['id']}/status",
                              json={"factory_id": "huaxing", "expected_revision": closing["revision"], "status": "PENDING"})
        assert pending.status_code == 200, pending.text
        closing = pending.json()
        blocked = client.post(f"/api/carton-procurement/closings/{closing['id']}/status",
                              json={"factory_id": "huaxing", "expected_revision": closing["revision"], "status": "CONFIRMED"})
        assert blocked.status_code == 409
        assert "OPEN-PRICE" in blocked.json()["detail"]
        path = f"/api/carton-procurement/inventory/movements/{issue['movement_id']}/price-confirmation"
        payload = {"factory_id": "huaxing", "unit_price": "2.5", "reason": "供应商报价单确认"}
        login_as(client, "qc_inspector")
        assert client.post(path, json=payload).status_code == 403
        login_as(client, "admin")
        assert client.post(path, json={**payload, "factory_id": "huadeng"}).status_code == 404
        assert client.post(path, json={**payload, "unit_price": 0}).status_code == 422
        saved = client.post(path, json=payload)
        assert saved.status_code == 204, saved.text
        assert client.post(path, json=payload).status_code == 409
        refreshed = client.get("/api/carton-procurement/closings", params={"factory_id": "huaxing"}).json()[0]
        assert refreshed["status"] == "DRAFT"
        assert refreshed["pricing_issues"] == []
        assert Decimal(refreshed["ending_amount"]) == 250
        original = client.get("/api/carton-procurement/inventory/movements", params={"factory_id": "huaxing"}).json()["items"][0]
        assert Decimal(original["unit_price"]) == 0
        from datetime import datetime
        from zoneinfo import ZoneInfo
        monkeypatch.setattr("app.services.carton_procurement.business_now", lambda: datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
        for status in ("PENDING", "CONFIRMED", "LOCKED"):
            response = client.post(f"/api/carton-procurement/closings/{refreshed['id']}/status",
                                   json={"factory_id": "huaxing", "expected_revision": refreshed["revision"], "status": status})
            assert response.status_code == 200, response.text
            refreshed = response.json()
        client.cookies.clear()
        assert client.post(path, json=payload).status_code == 401
