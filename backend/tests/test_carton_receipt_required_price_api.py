"""Receipt posting requires a verified positive price, while drafts stay compatible."""
import os
import sqlite3

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, confirm, ledger
from test_carton_direct_receipt_api import payload


def test_direct_price_gate_is_atomic_and_retryable(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        before = client.get(BASE + "/audit-events", params={"factory_id": "huaxing"}).json()
        for value in ("0", "-1", None):
            body["lines"][1]["unit_price"] = value
            # Missing prices must not be silently recovered from an unpriced order.
            if value is None:
                with sqlite3.connect(os.environ["DATABASE_URL"].removeprefix("sqlite:///")) as db:
                    db.execute("UPDATE carton_order_lines SET unit_price=0 WHERE id=?", (row["lines"][1]["id"],))
            response = client.post(BASE + "/receipts", json=body)
            assert response.status_code == 422, response.text
            assert ledger(client) == []
            assert client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["total"] == 0
            assert client.get(BASE + "/audit-events", params={"factory_id": "huaxing"}).json() == before
        body["lines"][1]["unit_price"] = "0.000001"
        accepted = client.post(BASE + "/receipts", json=body)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["status"] == "POSTED"
        assert len(ledger(client)) == 2
        assert client.post(BASE + "/receipts", json=body).json() == accepted.json()


def test_ad_hoc_receipt_cannot_post_without_price(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        body["lines"] = [{"source_type": "AD_HOC", "customer_code": row["customer_code"],
                          "item_no": "PRICE-GATE-SAMPLE", "packaging_type": "外箱", "paper_quality": "A33",
                          "specification": "30*20*15", "delivered_quantity": "2", "received_quantity": "2"}]
        response = client.post(BASE + "/receipts", json=body)
        assert response.status_code == 422 and "单价" in response.text, response.text
        assert ledger(client) == []
        body["lines"][0]["unit_price"] = "3"
        response = client.post(BASE + "/receipts", json=body)
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "POSTED"
        assert len(ledger(client)) == 1


def test_legacy_draft_cannot_bypass_price_gate_and_zero_effective_line_is_exempt(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        body["post_immediately"] = False
        body["lines"][1]["unit_price"] = "0"
        saved = client.post(BASE + "/receipts", json=body)
        assert saved.status_code == 201, saved.text
        receipt = saved.json()
        blocked = confirm(client, receipt)
        assert blocked.status_code == 422 and "单价" in blocked.text
        assert ledger(client) == []
        # Emulate a legacy draft whose entire unpriced line was rejected.
        with sqlite3.connect(os.environ["DATABASE_URL"].removeprefix("sqlite:///")) as db:
            db.execute("UPDATE carton_receipt_lines SET rejected_quantity=received_quantity, effective_quantity=0 WHERE receipt_id=? AND unit_price=0", (receipt["id"],))
        accepted = confirm(client, receipt)
        assert accepted.status_code == 200, accepted.text
        assert len(ledger(client)) == 1
        assert confirm(client, accepted.json()).status_code == 200
