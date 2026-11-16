"""Batch-confirmed procurement stays traceable without combining order quantities."""
from decimal import Decimal
from io import BytesIO
import json

import pytest
from openpyxl import load_workbook

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _order_payload
from test_carton_supplier_portal import BASE, accept_all, setup_portal, supplier_login

PROCUREMENT = "/api/carton-procurement"


def submit_batch(client, orders, **changes):
    return client.post(PROCUREMENT + "/orders/bulk-submit-supplier", json={
        "factory_id": "huaxing", "items": [
            {"order_no": order["order_no"], "expected_revision": order["revision"]}
            for order in orders
        ], **changes,
    })


def supplier_documents(client):
    response = client.get(BASE + "/documents", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def accept_orders(client, orders):
    return client.put(BASE + "/commitments/batch", json={"factory_id": "huaxing", "lines": [
        {"order_line_id": line["id"], "issue_id": order["issue_id"],
         "expected_revision": line["commitment_revision"], "promised_date": "2026-10-10"}
        for order in orders for line in order["lines"] if not line["accepted"]
    ]})


def workbook_rows(response):
    assert response.status_code == 200, response.text
    book = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    rows = list(book.active.values)
    names = book.sheetnames
    book.close()
    return names, rows


def test_confirmed_batch_is_one_supplier_document_with_atomic_initial_snapshots(monkeypatch):
    with make_client(monkeypatch) as client:
        existing = setup_portal(client)
        accept_all(client)
        login_as(client, "admin")
        drafts = [_create_order(client, submit_supplier=False) for _ in range(2)]
        response = submit_batch(client, [existing, *drafts])
        assert response.status_code == 200, response.text
        saved = response.json()
        assert len(saved) == 2
        batch = saved[0]["purchase_order_batch"]
        assert batch == saved[1]["purchase_order_batch"]
        assert batch["order_count"] == 2
        assert batch["document_no"].startswith("CG-")
        contexts = [client.get(PROCUREMENT + f"/orders/{order['order_no']}/purchase-order-context",
                               params={"factory_id": "huaxing"}).json() for order in saved]
        assert all(context["issues"][0]["purchase_order_batch"] == batch for context in contexts)
        assert all(context["pending_type"] == "NONE" for context in contexts)

        names, original_rows = workbook_rows(client.get(
            PROCUREMENT + f"/purchase-order-batches/{batch['id']}.xlsx",
            params={"factory_id": "huaxing"},
        ))
        assert names == ["合并采购单"]
        assert batch["document_no"] in original_rows[1][0]
        assert {row[3] for row in original_rows[5:9]} == {order["order_no"] for order in saved}
        assert all(row[13] > 0 for row in original_rows[5:9])
        assert client.get(PROCUREMENT + f"/purchase-order-batches/{batch['id']}.xlsx",
                          params={"factory_id": "huadeng"}).status_code == 404

        supplier_login(client)
        documents = supplier_documents(client)
        assert [row["orders"][0]["order_no"] for row in documents] == [existing["order_no"]]
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        batch_orders = [order for order in workspace["orders"] if order["id"] in {row["id"] for row in saved}]
        assert len(batch_orders) == 2
        assert all(not line["accepted"] for order in batch_orders for line in order["lines"])
        assert client.get(PROCUREMENT + f"/purchase-order-batches/{batch['id']}.xlsx",
                          params={"factory_id": "huaxing"}).status_code == 403

        selections = [{"factory_id": "huaxing", "kind": "PURCHASE", "id": batch["id"]}]
        for path in ("/documents/export.xlsx", "/documents/order-import.xlsx"):
            assert client.post(BASE + path, json={"documents": selections, "acknowledge_unaccepted": True}).status_code == 404
        accepted = accept_orders(client, batch_orders[:1])
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["order_ids"] == [batch_orders[0]["id"]]
        assert [row["orders"][0]["order_no"] for row in supplier_documents(client)] == [existing["order_no"]]
        assert client.post(BASE + "/documents/order-import.xlsx", json={"documents": selections}).status_code == 404
        accepted = accept_orders(client, batch_orders[1:])
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["order_ids"] == [batch_orders[1]["id"]]
        merged = next(row for row in supplier_documents(client) if row["id"] == batch["id"])
        assert merged["is_batch"] is True
        assert len(merged["orders"]) == 2 and len(merged["lines"]) == 4
        assert {line["order_no"] for line in merged["lines"]} == {order["order_no"] for order in saved}
        assert {line["source_document_no"] for line in merged["lines"]} == {
            context["issues"][0]["document_no"] for context in contexts}
        assert {line["unit"] for line in merged["lines"]} == {"个", "张"}
        assert merged["supplier_acceptance"]["status"] == "ACCEPTED"
        assert merged["supplier_acceptance"]["total_line_count"] == merged["supplier_acceptance"]["accepted_line_count"] == 4
        names, rows = workbook_rows(client.post(BASE + "/documents/export.xlsx", json={"documents": selections}))
        assert names == ["采购单"] and len(rows) == 5
        assert all(row[1] == batch["document_no"] for row in rows[1:])
        assert {row[4] for row in rows[1:]} == {order["order_no"] for order in saved}
        assert {row[18] for row in rows[1:]} == {source["document_no"] for source in merged["source_documents"]}
        _, imported = workbook_rows(client.post(BASE + "/documents/order-import.xlsx", json={"documents": selections}))
        assert len(imported) == 5
        assert all(row[19] == batch["document_no"] for row in imported[1:])
        assert sum(row[6] for row in imported[1:]) == sum(float(line["change_quantity"]) for line in merged["lines"])
        assert next(row for row in supplier_documents(client) if row["id"] == batch["id"])["export_count"] == 2
        assert client.post(BASE + "/documents/export.xlsx", json={"documents": [
            {**selections[0], "factory_id": "huadeng"}]}).status_code in (403, 422)
        assert client.post(BASE + "/documents/export.xlsx", json={"documents": [
            {**selections[0], "id": contexts[0]["issues"][0]["id"]}]}).status_code == 404
        assert next(row for row in supplier_documents(client) if row["id"] == batch["id"])["export_count"] == 2

        login_as(client, "admin")
        first = saved[0]
        appended = client.post(PROCUREMENT + f"/orders/{first['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": first["revision"], "additional_quantity": 120,
        })
        assert appended.status_code == 200, appended.text
        change = client.post(PROCUREMENT + f"/orders/{first['order_no']}/purchase-order-issues.xlsx", json={
            "factory_id": "huaxing", "expected_revision": appended.json()["revision"],
        })
        assert change.status_code == 200, change.text
        _, unchanged_rows = workbook_rows(client.get(
            PROCUREMENT + f"/purchase-order-batches/{batch['id']}.xlsx", params={"factory_id": "huaxing"}))
        assert unchanged_rows == original_rows
        supplier_login(client)
        documents = supplier_documents(client)
        assert next(row for row in documents if row["id"] == batch["id"])["lines"] == merged["lines"]
        assert not any(row["document_type"] == "APPEND" for row in documents)
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        changed_order = next(row for row in workspace["orders"] if row["id"] == first["id"])
        accepted = accept_orders(client, [changed_order])
        assert accepted.status_code == 200, accepted.text
        documents = supplier_documents(client)
        assert next(row for row in documents if row["id"] == batch["id"])["lines"] == merged["lines"]
        assert any(row["document_type"] == "APPEND" and not row.get("is_batch") for row in documents)


def test_superseded_unaccepted_member_does_not_strand_the_other_accepted_order(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        submitted = submit_batch(client, [_create_order(client, submit_supplier=False) for _ in range(2)])
        assert submitted.status_code == 200, submitted.text
        first, second = submitted.json()
        supplier_login(client)
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        first_order = next(order for order in workspace["orders"] if order["id"] == first["id"])
        accepted = accept_orders(client, [first_order])
        assert accepted.status_code == 200, accepted.text
        assert supplier_documents(client) == []

        login_as(client, "admin")
        changed = client.post(PROCUREMENT + f"/orders/{second['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": second["revision"], "additional_quantity": 120,
            "reason": "未接单的合并成员改量", "issue_to_supplier": True,
        })
        assert changed.status_code == 200, changed.text
        supplier_login(client)
        assert [row["id"] for row in supplier_documents(client)] == [first_order["issue_id"]]
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        second_order = next(order for order in workspace["orders"] if order["id"] == second["id"])
        accepted = accept_orders(client, [second_order])
        assert accepted.status_code == 200, accepted.text
        visible = {row["id"]: row for row in supplier_documents(client)}
        assert set(visible) == {first_order["issue_id"], second_order["issue_id"]}
        assert all(not row.get("is_batch") for row in visible.values())
        assert [float(line["change_quantity"]) for line in visible[second_order["issue_id"]]["lines"]] == [
            float(line["required_quantity"]) for line in second_order["lines"]]


@pytest.mark.parametrize("batch_was_opened", [False, True], ids=["unopened", "opened-without-download"])
def test_append_uses_only_a_previously_opened_batch_as_its_quantity_baseline(monkeypatch, batch_was_opened):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        submitted = submit_batch(client, [_create_order(client, submit_supplier=False) for _ in range(2)])
        assert submitted.status_code == 200, submitted.text
        first, second = submitted.json()
        batch_id = first["purchase_order_batch"]["id"]
        factory = {"factory_id": "huaxing"}

        def workspace_order(order_id):
            response = client.get(BASE + "/workspace", params=factory)
            assert response.status_code == 200, response.text
            return next(row for row in response.json()["orders"] if row["id"] == order_id)

        def download(path, document_id, **options):
            return client.post(BASE + f"/documents/{path}.xlsx", json={"documents": [
                {**factory, "kind": "PURCHASE", "id": document_id},
            ], **options})

        supplier_login(client)
        original = workspace_order(first["id"])
        other = workspace_order(second["id"])
        accepted = accept_orders(client, [original])
        assert accepted.status_code == 200, accepted.text
        assert supplier_documents(client) == []
        if batch_was_opened:
            accepted = accept_orders(client, [other])
            assert accepted.status_code == 200, accepted.text
            opened, = supplier_documents(client)
            assert opened["id"] == batch_id and opened["export_count"] == 0

        login_as(client, "admin")
        changed = client.post(PROCUREMENT + f"/orders/{first['order_no']}/append", json={
            **factory, "expected_revision": first["revision"], "additional_quantity": 120,
            "reason": "追加合并采购成员的纸品需求", "issue_to_supplier": True,
        })
        assert changed.status_code == 200, changed.text

        supplier_login(client)
        updated = workspace_order(first["id"])
        accepted = accept_orders(client, [updated])
        assert accepted.status_code == 200, accepted.text
        visible = {row["id"]: row for row in supplier_documents(client)}
        assert set(visible) == ({batch_id, updated["issue_id"]} if batch_was_opened else {updated["issue_id"]})
        latest = visible[updated["issue_id"]]
        expected = {"外箱": 1, "滑板纸": 120} if batch_was_opened else {"外箱": 31, "滑板纸": 3720}
        assert {line["packaging_type"]: Decimal(line["change_quantity"]) for line in latest["lines"]} == expected
        _, rows = workbook_rows(download("export", latest["id"]))
        assert {row[11]: Decimal(row[15]) for row in rows[1:]} == expected
        _, rows = workbook_rows(download("order-import", latest["id"]))
        assert {row[8]: Decimal(str(row[6])) for row in rows[1:]} == expected

        if not batch_was_opened:
            accepted = accept_orders(client, [workspace_order(second["id"])])
            assert accepted.status_code == 200, accepted.text
            visible = {row["id"]: row for row in supplier_documents(client)}
            assert set(visible) == {other["issue_id"], latest["id"]}
            assert download("export", batch_id).status_code == 404
            assert download("order-import", original["issue_id"]).status_code == 404
        else:
            visible = {row["id"]: row for row in supplier_documents(client)}
            history = visible[batch_id]
            assert history["lines"] == opened["lines"] and history["export_count"] == 0
            acceptance = history["supplier_acceptance"]
            assert acceptance["status"] == "HISTORICAL" and "已接齐" in acceptance["label"]
            assert acceptance["accepted_line_count"] == acceptance["total_line_count"] == 4
            assert download("order-import", batch_id).status_code == 409
            _, original_rows = workbook_rows(download("order-import", batch_id, acknowledge_unaccepted=True))
            assert [row[6] for row in original_rows[1:]] == [30, 3600, 30, 3600]
        assert visible[latest["id"]]["export_count"] == 2
        assert visible[latest["id"]]["order_import_export_count"] == 1


def test_stale_batch_rolls_back_and_retry_does_not_create_another_batch(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        drafts = [_create_order(client, submit_supplier=False) for _ in range(2)]
        stale = [drafts[0], {**drafts[1], "revision": drafts[1]["revision"] + 1}]
        assert submit_batch(client, stale).status_code == 409
        listed = client.get(PROCUREMENT + "/orders", params={"factory_id": "huaxing", "limit": 100})
        assert listed.status_code == 200, listed.text
        states = {order["order_no"]: order for order in listed.json()["items"]}
        for order in drafts:
            assert states[order["order_no"]]["status"] == "CONFIRMED"
            context = client.get(PROCUREMENT + f"/orders/{order['order_no']}/purchase-order-context",
                                 params={"factory_id": "huaxing"}).json()
            assert context["issues"] == []
        saved = submit_batch(client, drafts)
        assert saved.status_code == 200, saved.text
        batch = saved.json()[0]["purchase_order_batch"]
        repeated = submit_batch(client, drafts)
        assert repeated.status_code == 200 and repeated.json() == []
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent, CartonPurchaseOrderIssue
        from sqlalchemy import select
        with SessionLocal() as db:
            issues = list(db.scalars(select(CartonPurchaseOrderIssue)).all())
            assert len(issues) == 2
            assert all(json.loads(issue.snapshot_json)["purchase_batch"]["id"] == batch["id"] for issue in issues)
            events = list(db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.event_type == "PURCHASE_ORDER_BATCH_ISSUED")).all())
            assert len(events) == 1


def test_separate_confirmations_at_the_same_time_do_not_merge(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        from app.services import carton_procurement as service
        monkeypatch.setattr(service, "now_text", lambda: "2026-09-29T12:00:00+08:00")
        first = [_create_order(client, submit_supplier=False) for _ in range(2)]
        second = [_create_order(client, submit_supplier=False) for _ in range(2)]
        one = submit_batch(client, first).json()[0]["purchase_order_batch"]
        two = submit_batch(client, second).json()[0]["purchase_order_batch"]
        assert one["generated_at"] == two["generated_at"]
        assert one["id"] != two["id"] and one["document_no"] != two["document_no"]
        supplier_login(client)
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        response = accept_orders(client, workspace["orders"])
        assert response.status_code == 200, response.text
        batches = [row for row in supplier_documents(client) if row.get("is_batch")]
        assert {row["id"] for row in batches} == {one["id"], two["id"]}
        assert all(len(row["orders"]) == 2 for row in batches)


def test_confirmation_does_not_merge_different_suppliers(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        first = _create_order(client, submit_supplier=False)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="OTHER-SUPPLIER", factory_id="huaxing", supplier_code="OTHER",
                                 supplier_name="另一供应商", status="ACTIVE", created_at="2026-09-29", updated_at="2026-09-29"))
            db.commit()
        other = client.post(PROCUREMENT + "/orders", json={**_order_payload(), "supplier_id": "OTHER-SUPPLIER"})
        assert other.status_code == 201, other.text
        response = submit_batch(client, [first, other.json()])
        assert response.status_code == 200, response.text
        assert all(order["purchase_order_batch"] is None for order in response.json())


def test_issued_batch_blocks_member_deletion_and_survives_cancelled_tombstone(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        response = submit_batch(client, [_create_order(client, submit_supplier=False) for _ in range(2)])
        assert response.status_code == 200, response.text
        saved = response.json()
        batch = saved[0]["purchase_order_batch"]
        path = PROCUREMENT + f"/purchase-order-batches/{batch['id']}.xlsx"
        params = {"factory_id": "huaxing"}
        _, original_rows = workbook_rows(client.get(path, params=params))
        for order in saved:
            assert not order["can_delete"]
            rejected = client.post(PROCUREMENT + f"/orders/{order['order_no']}/delete", json={
                **params, "expected_revision": order["revision"], "reason": "合并订单误删测试",
            })
            assert rejected.status_code == 409, rejected.text
            assert "合并采购单" in rejected.json()["detail"]
            assert workbook_rows(client.get(path, params=params))[1] == original_rows
        rejected = client.post(PROCUREMENT + "/orders/bulk-delete", json={
            **params, "reason": "合并订单批量误删测试", "items": [
                {"order_no": order["order_no"], "expected_revision": order["revision"]} for order in saved
            ],
        })
        assert rejected.status_code == 409, rejected.text
        anchor_order = saved[0]
        supplier_login(client)
        workspace = client.get(BASE + "/workspace", params=params).json()
        accepted = accept_orders(client, [order for order in workspace["orders"]
                                          if order["id"] in {item["id"] for item in saved}])
        assert accepted.status_code == 200, accepted.text
        login_as(client, "admin")
        cancelled = client.post(PROCUREMENT + f"/orders/{anchor_order['order_no']}/reduce", json={
            **params, "expected_revision": anchor_order["revision"],
            "reduction_quantity": anchor_order["product_order_quantity"], "reason": "客户退回本张订单",
            "issue_to_supplier": True,
        })
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        supplier_login(client)
        workspace = client.get(BASE + "/workspace", params=params).json()
        stopped = next(order for order in workspace["orders"] if order["id"] == anchor_order["id"])
        notice = stopped["cancellation_notice"]
        acknowledged = client.post(BASE + f"/orders/{stopped['id']}/cancellation-ack", json={
            **params, "issue_id": notice["issue_id"], "expected_order_revision": stopped["revision"],
        })
        assert acknowledged.status_code == 200, acknowledged.text
        login_as(client, "admin")
        removed = client.post(PROCUREMENT + f"/orders/{anchor_order['order_no']}/delete", json={
            **params, "expected_revision": acknowledged.json()["revision"], "reason": "取消后从台账移除",
        })
        assert removed.status_code == 204, removed.text
        assert workbook_rows(client.get(path, params=params))[1] == original_rows
        supplier_login(client)
        documents = supplier_documents(client)
        retained = next(row for row in documents if row["id"] == batch["id"])
        assert retained["is_batch"] and len(retained["orders"]) == 2
        assert {row["order_no"] for row in retained["orders"]} == {order["order_no"] for order in saved}
