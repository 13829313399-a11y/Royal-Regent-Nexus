from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, draft, confirm, ledger
from test_carton_receipt_correction_api import reverse


def payload(row):
    return {"factory_id": "huaxing", "post_immediately": True, "request_id": uuid4().hex,
            "delivery_note_no": uuid4().hex, "delivery_date": "2026-08-05",
            "lines": [{"order_line_id": line["id"], "delivered_quantity": line["required_quantity"],
                       "received_quantity": line["required_quantity"], "unit_price": "2"}
                      for line in row["lines"]]}


def test_direct_receipt_posts_once_completes_order_and_replays_after_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        missing = {k: v for k, v in body.items() if k != "request_id"}
        assert client.post(f"{BASE}/receipts", json=missing).status_code == 422
        first = client.post(f"{BASE}/receipts", json=body)
        assert first.status_code == 201, first.text
        posted = first.json()
        assert posted["status"] == "POSTED" and posted["confirmed_at"]
        assert len(ledger(client)) == 2
        assert client.get(f"{BASE}/orders", params={"factory_id": "huaxing"}).json()["items"][0]["status"] == "COMPLETED"
        assert client.post(f"{BASE}/receipts", json=body).json() == posted
        assert client.post(f"{BASE}/receipts", json={**body, "note": "changed"}).status_code == 409
        assert len(ledger(client)) == 2
        assert reverse(client, posted).status_code == 200
        replay = client.post(f"{BASE}/receipts", json=body)
        assert replay.status_code == 201 and replay.json()["status"] == "REVERSED"
        assert len(ledger(client)) == 4


def test_direct_receipt_failure_rolls_back_header_lines_stock_audit_and_capacity(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        import app.services.carton_procurement as service
        original = service._ensure_period_open
        calls = []
        def fail_second(*args):
            calls.append(1)
            if len(calls) == 2:
                raise HTTPException(409, "测试第二条入库锁账失败")
            return original(*args)
        before_audit = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()
        monkeypatch.setattr(service, "_ensure_period_open", fail_second)
        failed = client.post(f"{BASE}/receipts", json=body)
        assert failed.status_code == 409, failed.text
        assert len(calls) == 2
        assert ledger(client) == []
        assert client.get(f"{BASE}/receipts", params={"factory_id": "huaxing"}).json()["total"] == 0
        assert client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json() == before_audit
        monkeypatch.setattr(service, "_ensure_period_open", original)
        retried = client.post(f"{BASE}/receipts", json=body)
        assert retried.status_code == 201 and retried.json()["status"] == "POSTED", retried.text


def test_direct_receipt_concurrent_retry_posts_only_one_document(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        barrier = Barrier(2)
        def send():
            barrier.wait(timeout=10)
            return client.post(f"{BASE}/receipts", json=body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [f.result(timeout=30) for f in [pool.submit(send), pool.submit(send)]]
        assert [r.status_code for r in responses] == [201, 201]
        assert responses[0].json() == responses[1].json()
        assert len(ledger(client)) == 2


def test_direct_receipt_respects_legacy_pending_capacity(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        pending = draft(client, row, 10).json()
        body = payload(row)
        blocked = client.post(f"{BASE}/receipts", json=body)
        assert blocked.status_code == 409 and "待确认" in blocked.text
        assert ledger(client) == []
        assert confirm(client, pending).status_code == 200
        assert len(ledger(client)) == 1
