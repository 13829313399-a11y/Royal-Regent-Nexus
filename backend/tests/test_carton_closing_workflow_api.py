from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _freeze_carton_time
from test_carton_receipt_correction_api import receipt


def test_review_is_open_for_warehouse_but_final_lock_and_unlock_are_supervised(monkeypatch):
    with make_client(monkeypatch) as client:
        import app.services.carton_procurement as service
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        receipt(client, order)
        generated = client.post("/api/carton-procurement/closings/generate", json={"factory_id": "huaxing", "period": "2026-08"})
        assert generated.status_code == 200, generated.text
        row = generated.json()[0]
        path = f"/api/carton-procurement/closings/{row['id']}"
        def status(value):
            return client.post(path + "/status", json={"factory_id": "huaxing", "expected_revision": row["revision"], "status": value})
        for value in ("PENDING", "CONFIRMED"):
            result = status(value)
            assert result.status_code == 200, result.text
            row = result.json()
        assert status("LOCKED").status_code == 403
        # Normal receipt/outbound work remains possible after review confirmation.
        out = client.post("/api/carton-procurement/inventory/movements", json={"request_id": uuid4().hex, "factory_id": "huaxing",
            "order_line_id": order["lines"][0]["id"], "movement_type": "OUTBOUND", "quantity": "1",
            "document_no": "OUT-REVIEW", "reason": "核对后正常出库"})
        assert out.status_code == 201, out.text
        login_as(client, "admin")
        assert status("LOCKED").status_code == 409
        monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
        stale = status("LOCKED")
        assert stale.status_code == 409 and "数量或金额" in stale.text
        row = client.post("/api/carton-procurement/closings/generate", json={"factory_id": "huaxing", "period": "2026-08"}).json()[0]
        for value in ("PENDING", "CONFIRMED", "LOCKED"):
            result = status(value)
            assert result.status_code == 200, result.text
            row = result.json()
        payload = {"factory_id": "huaxing", "expected_revision": row["revision"], "reason": "误操作锁账，需重新核对"}
        login_as(client, "warehouse_keeper")
        assert client.post(path + "/unlock", json=payload).status_code == 403
        login_as(client, "admin")
        for invalid_reason in ("   ", None, 123):
            assert client.post(path + "/unlock", json={**payload, "reason": invalid_reason}).status_code == 422
        assert client.post(path + "/unlock", json={**payload, "factory_id": "huadeng"}).status_code == 404
        result = client.post(path + "/unlock", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "DRAFT" and result.json()["locked_by"] == ""
        assert client.post(path + "/unlock", json=payload).status_code == 409
