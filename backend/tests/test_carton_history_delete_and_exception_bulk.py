import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_history_identity_api import _customer, _row, _upload, _orders, BASE
from test_carton_procurement_api import _freeze_carton_time, _create_order, _workbook_bytes
from test_carton_receipt_correction_api import receipt, reverse


def historical(client):
    _customer(client, "Alpha")
    _upload(client, [_row("Alpha")])
    return _orders(client)[0]


def delete(client, order, **overrides):
    return client.post(f"{BASE}/orders/{order['order_no']}/delete-history", json={
        "factory_id": "huaxing", "expected_revision": order["revision"],
        "reason": "历史订单重复录入", **overrides})


def test_history_delete_preserves_audit_master_and_allows_reimport(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = historical(client)
        assert row["status"] == "PENDING_SUPPLIER" and row["can_delete_history"]
        customers = client.get(f"{BASE}/customers", params={"factory_id": "huaxing"}).json()
        assert delete(client, row, expected_revision=row["revision"] + 1).status_code == 409
        assert delete(client, row, factory_id="huadeng").status_code == 404
        assert delete(client, row).status_code == 204
        assert _orders(client) == []
        assert delete(client, row).status_code == 404
        assert client.get(f"{BASE}/customers", params={"factory_id": "huaxing"}).json() == customers
        audits = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        event = next(row for row in audits if row["event_type"] == "HISTORY_ORDER_DELETED")
        assert event["detail"]["order"]["lines"] and event["detail"]["purchase_issues"]
        assert _upload(client, [_row("Alpha")])["imported_count"] == 1


@pytest.mark.parametrize("mode", ["pending", "posted", "reversed"])
def test_history_with_any_receipt_evidence_cannot_be_deleted(monkeypatch, mode):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = historical(client)
        doc = receipt(client, row, post=mode != "pending")
        if mode == "reversed":
            assert reverse(client, doc).status_code == 200
        current = _orders(client)[0]
        assert not current["can_delete_history"]
        assert delete(client, current).status_code == 409


def test_normal_order_cannot_use_history_delete(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        row = _create_order(client)
        login_as(client, "admin")
        assert not row["can_delete_history"]
        assert delete(client, row).status_code == 409


def create_exceptions(client):
    content = _workbook_bytes(["日期", "入库单号", "PO", "货号", "外箱", "纸质", "长", "宽", "高", "单价"], [
        ["2026-08-05", "DN-EX", "SC-MISSING-1", "ITEM-1", 10, "A33+B外箱", 30, 20, 10, 2],
        ["2026-08-05", "DN-EX", "SC-MISSING-2", "ITEM-2", 10, "A33+B外箱", 30, 20, 10, 2],
    ])
    response = client.post(f"{BASE}/receipt-imports", params={"factory_id": "huaxing"},
        files={"file": ("exceptions.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 201, response.text
    rows = client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"]
    assert len(rows) == 2
    return rows


def test_bulk_exceptions_atomic_revisions_scope_and_resolution(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        rows = create_exceptions(client)
        body = {"factory_id": "huaxing", "status": "IN_PROGRESS", "items": [
            {"id": row["id"], "expected_revision": row["revision"]} for row in rows]}
        audits_before = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        stale = {**body, "items": [body["items"][0], {**body["items"][1], "expected_revision": 99}]}
        assert client.post(f"{BASE}/exceptions/bulk-update", json=stale).status_code == 409
        assert client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"] == rows
        assert client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"] == audits_before
        assert client.post(f"{BASE}/exceptions/bulk-update", json={**body, "factory_id": "huadeng"}).status_code == 404
        updated = client.post(f"{BASE}/exceptions/bulk-update", json=body)
        assert updated.status_code == 200, updated.text
        assert all(row["status"] == "IN_PROGRESS" and row["revision"] == 2 for row in updated.json())
        saved = client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"]
        assert all(row["status"] == "IN_PROGRESS" and row["revision"] == 2 for row in saved)
        audits_after = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        assert len(audits_after) == len(audits_before) + 2
        assert client.post(f"{BASE}/exceptions/bulk-update", json=body).status_code == 409
        body.update(status="RESOLVED", resolution_note="", items=[
            {"id": row["id"], "expected_revision": row["revision"]} for row in updated.json()])
        assert client.post(f"{BASE}/exceptions/bulk-update", json=body).status_code == 200
        for row in client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"]:
            closed = client.patch(f"{BASE}/exceptions/{row['id']}", json={"factory_id": "huaxing", "expected_revision": row["revision"], "status": "CLOSED"})
            assert closed.status_code == 200 and closed.json()["resolution_note"] == ""
