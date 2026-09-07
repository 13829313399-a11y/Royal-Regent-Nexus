from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import os
import sqlite3

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order, _freeze_carton_time

BASE = "/api/carton-procurement"


def order(client):
    _ensure_dickie_customer(client)
    payload = _order_payload()
    payload["product_order_quantity"] = "100"
    payload["lines"][0]["usage_quantity"] = "10"  # 10 cartons + 100 sheets
    response = client.post(f"{BASE}/orders", json=payload)
    assert response.status_code == 201, response.text
    return _submit_order(client, response.json())


def draft(client, row, qty, **overrides):
    payload = {"factory_id": "huaxing", "delivery_note_no": uuid4().hex, "delivery_date": "2026-08-05",
               "lines": [{"order_line_id": row["lines"][0]["id"], "delivered_quantity": str(qty),
                          "received_quantity": str(qty), "unit_price": "2"}]}
    payload.update(overrides)
    return client.post(f"{BASE}/receipts", json=payload)


def confirm(client, receipt):
    return client.post(f"{BASE}/receipts/{receipt['id']}/confirm", json={
        "factory_id": "huaxing", "expected_revision": receipt["revision"]})


def ledger(client):
    return client.get(f"{BASE}/inventory/movements", params={"factory_id": "huaxing"}).json()["items"]


def outbound(row, qty=2, **overrides):
    return {"factory_id": "huaxing", "request_id": uuid4().hex, "movement_type": "OUTBOUND",
            "order_line_id": row["lines"][0]["id"], "quantity": qty,
            "document_no": "OUT-SAME-DOCUMENT", "reason": "客户要货", **overrides}


def test_single_outbound_retry_replays_even_after_depletion_and_rejects_key_reuse(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        assert confirm(client, draft(client, row, 10).json()).status_code == 200
        payload = outbound(row, 6)
        no_key = {key: value for key, value in payload.items() if key != "request_id"}
        assert client.post(f"{BASE}/inventory/movements", json=no_key).status_code == 422
        first = client.post(f"{BASE}/inventory/movements", json=payload)
        assert first.status_code == 201, first.text
        # The retry must return the original result even though 6 now exceeds current stock 4.
        retry = client.post(f"{BASE}/inventory/movements", json={**payload, "quantity": "6.0000"})
        assert retry.status_code == 201 and retry.json() == first.json()
        conflict = client.post(f"{BASE}/inventory/movements", json={**payload, "quantity": 3})
        assert conflict.status_code == 409
        # A separate legitimate operation can share the source document number.
        second = client.post(f"{BASE}/inventory/movements", json=outbound(row, 4))
        assert second.status_code == 201, second.text
        assert client.post(f"{BASE}/inventory/movements", json=payload).json() == first.json()
        movements = ledger(client)
        assert len([item for item in movements if item["movement_type"] == "OUTBOUND"]) == 2
        assert sum(Decimal(item["quantity"]) for item in movements) == 0


def test_concurrent_outbound_retry_has_one_effect(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        assert confirm(client, draft(client, row, 10).json()).status_code == 200
        payload = outbound(row, 6)
        barrier = Barrier(2)
        def send():
            barrier.wait(timeout=10)
            return client.post(f"{BASE}/inventory/movements", json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send) for _ in range(2)]
            responses = [future.result(timeout=30) for future in futures]
        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json() == responses[1].json()
        assert sum(Decimal(item["quantity"]) for item in ledger(client)) == 4


def test_bulk_outbound_failed_attempt_is_atomic_and_success_is_replayable(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        receipt = draft(client, row, 10, lines=[{
            "order_line_id": line["id"], "delivered_quantity": line["required_quantity"],
            "received_quantity": line["required_quantity"], "unit_price": "2"} for line in row["lines"]]).json()
        assert confirm(client, receipt).status_code == 200
        payload = {"factory_id": "huaxing", "request_id": uuid4().hex, "document_no": "BULK",
                   "items": [{"order_line_id": row["lines"][0]["id"], "quantity": 6},
                             {"order_line_id": row["lines"][1]["id"], "quantity": 101}]}
        assert client.post(f"{BASE}/inventory/movements/bulk", json=payload).status_code == 409
        assert len(ledger(client)) == 2
        payload["items"][1]["quantity"] = 100
        first = client.post(f"{BASE}/inventory/movements/bulk", json=payload)
        assert first.status_code == 201, first.text
        repeat = client.post(f"{BASE}/inventory/movements/bulk", json=payload)
        assert repeat.status_code == 201 and repeat.json() == first.json()
        assert len(ledger(client)) == 4
        payload["items"][0]["quantity"] = 2
        assert client.post(f"{BASE}/inventory/movements/bulk", json=payload).status_code == 409


def test_receipt_drafts_reserve_remaining_quantity_and_void_releases_it(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        first = draft(client, row, 6)
        assert first.status_code == 201
        assert draft(client, row, 6).status_code == 409
        second = draft(client, row, 4)
        assert second.status_code == 201
        assert len(ledger(client)) == 0
        assert confirm(client, first.json()).status_code == 200
        assert draft(client, row, 1).status_code == 409
        voided = client.post(f"{BASE}/receipts/{second.json()['id']}/reverse", json={
            "factory_id": "huaxing", "expected_revision": second.json()["revision"], "reason": "作废重复登记收料"})
        assert voided.status_code == 200, voided.text
        replacement = draft(client, row, 4)
        assert replacement.status_code == 201
        assert confirm(client, replacement.json()).status_code == 200
        assert confirm(client, replacement.json()).status_code == 200
        assert sum(Decimal(item["quantity"]) for item in ledger(client)) == 10
        assert draft(client, row, 1).status_code == 409


def test_confirmation_blocks_legacy_overbooked_drafts_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        first = draft(client, row, 4).json()
        second = draft(client, row, 4).json()
        # Model an already-saved overbooked draft from before the validation existed.
        with sqlite3.connect(os.environ["DATABASE_URL"].removeprefix("sqlite:///")) as db:
            db.execute("UPDATE carton_receipt_lines SET delivered_quantity=7, received_quantity=7, effective_quantity=7 WHERE receipt_id=?", (second["id"],))
        failed = confirm(client, first)
        assert failed.status_code == 409 and "累计收料超过订单需求" in failed.text
        assert ledger(client) == []
        assert confirm(client, second).status_code == 409
        voided = client.post(f"{BASE}/receipts/{second['id']}/reverse", json={
            "factory_id": "huaxing", "expected_revision": second["revision"], "reason": "处理历史多余收料单"})
        assert voided.status_code == 200
        assert confirm(client, first).status_code == 200
        assert sum(Decimal(item["quantity"]) for item in ledger(client)) == 4


def test_concurrent_receipt_drafts_cannot_over_reserve_and_defects_use_effective_quantity(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        barrier = Barrier(2)
        def save():
            barrier.wait(timeout=10)
            return draft(client, row, 6)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save) for _ in range(2)]
            responses = [future.result(timeout=30) for future in futures]
        assert sorted(response.status_code for response in responses) == [201, 409]
        first = next(response.json() for response in responses if response.status_code == 201)
        assert confirm(client, first).status_code == 200
        # Six delivered with two unusable cartons reserves only four, reaching exactly ten.
        final = draft(client, row, 6, lines=[{"order_line_id": row["lines"][0]["id"],
                      "delivered_quantity": "6", "received_quantity": "6", "damaged_quantity": "2"}])
        assert final.status_code == 201, final.text
        assert confirm(client, final.json()).status_code == 200
        assert sum(Decimal(item["quantity"]) for item in ledger(client)) == 10
