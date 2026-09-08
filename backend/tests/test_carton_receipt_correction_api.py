from uuid import uuid4
from decimal import Decimal
import sqlite3
import os

from test_carton_procurement_api import _create_order, _freeze_carton_time
from test_molding_sample_api import make_client, login_as


def receipt(client, order, number="DN-CORRECT", post=True):
    payload = {"factory_id": "huaxing", "delivery_note_no": number, "delivery_date": "2026-08-05",
               "lines": [{"order_line_id": line["id"], "delivered_quantity": line["required_quantity"],
                          "received_quantity": line["required_quantity"], "unit_price": line["unit_price"]}
                         for line in order["lines"]]}
    response = client.post("/api/carton-procurement/receipts", json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    if post:
        response = client.post(f"/api/carton-procurement/receipts/{result['id']}/confirm",
                               json={"factory_id": "huaxing", "expected_revision": result["revision"]})
        assert response.status_code == 200, response.text
        result = response.json()
    return result


def reverse(client, doc, **kwargs):
    return client.post(f"/api/carton-procurement/receipts/{doc['id']}/reverse", json={
        "factory_id": "huaxing", "expected_revision": doc["revision"], "reason": "送货数量录错，重新登记", **kwargs})


def movements(client):
    return client.get("/api/carton-procurement/inventory/movements", params={"factory_id": "huaxing"}).json()["items"]


def test_receipt_reversal_restores_order_and_preserves_evidence_and_allows_reentry(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        doc = receipt(client, order)
        originals = movements(client)
        response = reverse(client, doc)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "REVERSED" and result["revision"] == doc["revision"] + 1
        assert result["lines"] == doc["lines"] and result["confirmed_at"] == doc["confirmed_at"]
        refreshed = client.get("/api/carton-procurement/orders", params={"factory_id": "huaxing"}).json()["items"][0]
        assert refreshed["status"] == "PENDING_SUPPLIER"
        assert all(Decimal(line["received_quantity"]) == 0 for line in refreshed["lines"])
        all_rows = movements(client)
        assert len(all_rows) == 2 * len(originals)
        assert sum(Decimal(row["quantity"]) for row in all_rows) == 0
        assert {row["reversal_of_movement_id"] for row in all_rows if row["movement_type"] == "REVERSAL"} == {row["id"] for row in originals}
        assert client.get("/api/carton-procurement/inventory/summary", params={"factory_id": "huaxing"}).json() == []
        assert reverse(client, doc).status_code == 409
        assert len(movements(client)) == len(all_rows)
        # Confirming the old document cannot bring it back to life.
        assert client.post(f"/api/carton-procurement/receipts/{doc['id']}/confirm",
                           json={"factory_id": "huaxing", "expected_revision": result["revision"]}).status_code == 409
        replacement = receipt(client, refreshed, number="DN-CORRECT-更正-1")
        assert replacement["status"] == "POSTED"
        assert sum(Decimal(row["quantity"]) for row in movements(client)) == sum(Decimal(row["quantity"]) for row in originals)


def test_pending_void_permissions_revision_scope_and_reason(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        doc = receipt(client, order, post=False)
        assert reverse(client, doc, reason="   ").status_code == 422
        assert reverse(client, doc, expected_revision=99).status_code == 409
        login_as(client, "qc_inspector")
        assert reverse(client, doc).status_code == 403
        login_as(client, "admin")
        assert reverse(client, doc, factory_id="huadeng").status_code == 404
        result = reverse(client, doc)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "REVERSED"
        assert movements(client) == []
        replacement = receipt(client, order, number="DN-CORRECT-更正-1")
        assert replacement["status"] == "POSTED"


def test_posted_reversal_rejects_insufficient_stock_and_locked_original_month_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        doc = receipt(client, order)
        inbound = movements(client)[0]
        out = client.post("/api/carton-procurement/inventory/movements", json={"request_id": uuid4().hex,
            "factory_id": "huaxing", "order_line_id": inbound["order_line_id"], "movement_type": "OUTBOUND",
            "quantity": "1", "unit": inbound["unit"], "currency": inbound["currency"], "document_no": "OUT-CORRECT", "reason": "客户领料"})
        assert out.status_code == 201, out.text
        before = movements(client)
        response = reverse(client, doc)
        assert response.status_code == 409 and "库存不足" in response.text
        assert len(movements(client)) == len(before)
        # Isolated test database only: emulate an already locked original period, then move the correction date forward.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import app.services.carton_procurement as service
        login_as(client, "admin")
        generated = client.post("/api/carton-procurement/closings/generate", json={"factory_id": "huaxing", "period": "2026-08"})
        assert generated.status_code == 200, generated.text
        with sqlite3.connect(os.environ["DATABASE_URL"].removeprefix("sqlite:///")) as db:
            db.execute("UPDATE carton_closings SET status='LOCKED' WHERE factory_id='huaxing' AND period='2026-08'")
        monkeypatch.setattr(service, "business_now", lambda: datetime(2026, 9, 5, tzinfo=ZoneInfo("Asia/Shanghai")))
        response = reverse(client, doc)
        assert response.status_code == 409 and "2026-08" in response.text
        assert len(movements(client)) == len(before)


def test_receipt_correction_serializes_duplicate_and_confirmation_races(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import app.services.carton_procurement as service
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        doc = receipt(client, order)
        original_lock = service._lock_receipt_factory
        barrier = threading.Barrier(2)
        def racing_lock(db, factory):
            barrier.wait(timeout=10)
            return original_lock(db, factory)
        monkeypatch.setattr(service, "_lock_receipt_factory", racing_lock)
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(reverse, client, doc) for _ in range(2)]
            responses = [call.result(timeout=30) for call in calls]
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert len(movements(client)) == len(doc["lines"]) * 2
        monkeypatch.setattr(service, "_lock_receipt_factory", original_lock)
        pending = receipt(client, order, number="DN-RACE", post=False)
        barrier = threading.Barrier(2)
        monkeypatch.setattr(service, "_lock_receipt_factory", racing_lock)
        with ThreadPoolExecutor(max_workers=2) as pool:
            cancel = pool.submit(reverse, client, pending)
            confirm = pool.submit(client.post, f"/api/carton-procurement/receipts/{pending['id']}/confirm",
                                  json={"factory_id": "huaxing", "expected_revision": pending["revision"]})
            results = [cancel.result(timeout=30), confirm.result(timeout=30)]
        assert sorted(response.status_code for response in results) == [200, 409]
        history = client.get("/api/carton-procurement/receipts", params={"factory_id": "huaxing"}).json()["items"]
        final = next(row for row in history if row["id"] == pending["id"])
        new_rows = [row for row in movements(client) if row["source_id"] == pending["id"]]
        assert len(new_rows) == (len(pending["lines"]) if final["status"] == "POSTED" else 0)


def test_ad_hoc_same_key_accumulates_and_valuation_failure_rolls_back(monkeypatch):
    from test_carton_procurement_api import _ensure_dickie_customer
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _ensure_dickie_customer(client)
        _freeze_carton_time(monkeypatch)
        def adhoc(number, price, count=1):
            response = client.post("/api/carton-procurement/receipts", json={
                "factory_id": "huaxing", "delivery_note_no": number, "delivery_date": "2026-08-05",
                "lines": [{"source_type": "AD_HOC", "customer_code": "DICKIE", "contract_no": "SAMPLE",
                           "item_no": "SAMPLE", "packaging_type": "外箱", "paper_quality": "A33", "specification": "1*1*1",
                           "unit": "个", "currency": "CNY", "delivered_quantity": "10", "received_quantity": "10",
                           "unit_price": price} for _ in range(count)]})
            assert response.status_code == 201, response.text
            doc = response.json()
            response = client.post(f"/api/carton-procurement/receipts/{doc['id']}/confirm",
                                   json={"factory_id": "huaxing", "expected_revision": doc["revision"]})
            assert response.status_code == 200, response.text
            return response.json()
        def outbound(ref, qty, number):
            response = client.post("/api/carton-procurement/inventory/movements", json={"request_id": uuid4().hex,
                "factory_id": "huaxing", "reference_movement_id": ref, "movement_type": "OUTBOUND",
                "quantity": qty, "document_no": number, "reason": "客户正常领料"})
            assert response.status_code == 201, response.text
            return response.json()
        first = adhoc("ADHOC-TWO", "2", count=2)
        out = outbound(movements(client)[0]["id"], "5", "OUT-ADHOC")
        failed = reverse(client, first)
        assert failed.status_code == 409 and "库存不足" in failed.text
        assert len(movements(client)) == 3
        undone = client.post(f"/api/carton-procurement/inventory/movements/{out['id']}/reverse",
                             json={"factory_id": "huaxing", "reason": "撤销原领料以复核"})
        assert undone.status_code == 201, undone.text
        result = reverse(client, first)
        assert result.status_code == 200, result.text
        adhoc("ADHOC-CHEAP", "2")
        expensive = adhoc("ADHOC-EXPENSIVE", "4")
        inbound = next(row for row in movements(client) if row["source_id"] == expensive["id"])
        outbound(inbound["id"], "10", "OUT-VALUATION")
        before = movements(client)
        failed = reverse(client, expensive)
        assert failed.status_code == 409 and "金额无法对平" in failed.text
        assert len(movements(client)) == len(before)
