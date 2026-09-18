from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_history_identity_api import _customer, _row, _upload, _orders, BASE
from test_carton_procurement_api import _freeze_carton_time, _create_order, _workbook_bytes
from test_carton_receipt_correction_api import receipt, reverse


def histories(client):
    for name in ("Alpha", "Beta"):
        _customer(client, name)
    _upload(client, [_row("Alpha"), _row("Beta")])
    return _orders(client)


def bulk_body(rows, **changes):
    return {"factory_id": "huaxing", "reason": "重复导入需要删除", "items": [
        {"order_no": row["order_no"], "expected_revision": row["revision"]} for row in rows], **changes}


def audits(client):
    return client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]


def test_bulk_history_delete_validates_all_revisions_scope_duplicates_and_audits(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        rows = histories(client)
        original_audits = audits(client)
        payload = bulk_body(rows)
        stale = bulk_body(rows)
        stale["items"][1]["expected_revision"] += 1
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=stale).status_code == 409
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body(rows, factory_id="huadeng")).status_code == 404
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body([rows[0], rows[0]])).status_code == 422
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body(rows, reason="   x   ")).status_code == 422
        assert _orders(client) == rows
        assert audits(client) == original_audits
        response = client.post(f"{BASE}/orders/bulk-delete-history", json=payload)
        assert response.status_code == 204, response.text
        assert _orders(client) == []
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=payload).status_code == 404
        deleted = [event for event in audits(client) if event["event_type"] == "HISTORY_ORDER_DELETED"]
        assert len(deleted) == 2
        assert len({event["detail"]["operation_id"] for event in deleted}) == 1
        for event in deleted:
            detail = event["detail"]
            assert detail["reason"] == payload["reason"]
            assert detail["order"]["lines"] and event["actor_user_id"]
            assert detail["purchase_issues"][0]["document_type"] == "LEGACY_BASELINE"
            assert detail["purchase_issues"][0]["snapshot"]["lines"]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrderLine, CartonPurchaseOrderIssue
        from sqlalchemy import select
        with SessionLocal() as db:
            assert list(db.scalars(select(CartonOrderLine)).all()) == []
            assert list(db.scalars(select(CartonPurchaseOrderIssue)).all()) == []
        assert _upload(client, [_row("Alpha"), _row("Beta")])["imported_count"] == 2


@pytest.mark.parametrize("evidence", ["pending", "posted", "reversed", "movement", "ordinary"])
def test_bulk_history_delete_mixed_selection_is_atomic(monkeypatch, evidence):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        rows = histories(client)
        blocked = rows[1]
        if evidence == "ordinary":
            _customer(client, "Dickie")
            blocked = _create_order(client)
            login_as(client, "admin")
        elif evidence == "movement":
            from app.db import SessionLocal
            from app.models.carton_procurement import CartonInventoryMovement
            line = blocked["lines"][0]
            with SessionLocal() as db:
                for index, amount in enumerate((1, -1)):
                    db.add(CartonInventoryMovement(
                        id=f"MOV-ZERO-{index}", factory_id="huaxing", order_line_id=line["id"],
                        customer_code=blocked["customer_code"], customer_name=blocked["customer_name"],
                        contract_no=blocked["contract_no"], item_no=blocked["item_no"],
                        packaging_type=line["packaging_type"], paper_quality=line["paper_quality"],
                        specification=line["specification"], movement_type="ADJUSTMENT", quantity=amount,
                        unit=line["unit"], document_no="ZERO-EVIDENCE", source_type="MANUAL", source_id="",
                        source_line_id=f"ZERO-{index}", actor_user_id="admin", occurred_at=f"2026-08-05T12:00:0{index}",
                    ))
                db.commit()
        else:
            doc = receipt(client, blocked, post=evidence != "pending")
            if evidence == "reversed":
                assert reverse(client, doc).status_code == 200
        current = _orders(client)
        selected = [next(row for row in current if row["id"] == target["id"]) for target in (rows[0], blocked)]
        before = audits(client)
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body(selected)).status_code == 409
        assert _orders(client) == current
        assert audits(client) == before


def test_deleted_history_order_archives_its_append_work_items_without_orphans(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = histories(client)[0]
        response = client.post(f"{BASE}/orders/{row['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": row["revision"], "additional_quantity": 100,
        })
        assert response.status_code == 200, response.text
        updated = response.json()
        items = client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"]
        assert len(items) == 1 and items[0]["source_id"] == row["id"]
        # The old revision cannot delete an order changed by a concurrent writer.
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body([row])).status_code == 409
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body([updated])).status_code == 204
        assert client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"] == []
        event = next(event for event in audits(client) if event["event_type"] == "HISTORY_ORDER_DELETED")
        assert event["detail"]["exceptions"] == items
        assert event["detail"]["order"]["master_config_id"] == ""
        assert event["detail"]["order"]["lines"][0]["order_id"] == row["id"]


def schedule(client, kind="weekly"):
    content = _workbook_bytes(
        ["Reference", "PO.NO", "客名/国家", "产品编号", "产品名称", "数量", "装箱", "验货期（请提前准备好货物）"],
        [[f"MISSING-{i}", f"PO-{i}", "Dickie", f"ITEM-{i}", "排期产品", 1200, "1/60", "8月15日-8月18日"] for i in (1, 2)],
    )
    kwargs = {"params": {"factory_id": "huaxing"}, "files": {"file": ("schedule.xlsx", content)}}
    response = client.post(f"{BASE}/{kind}-imports", **kwargs)
    assert response.status_code == 201, response.text
    return response.json(), kwargs


@pytest.mark.parametrize("kind", ["weekly", "inspection"])
def test_schedule_undo_keeps_audit_retires_all_results_and_exceptions_once(monkeypatch, kind):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        _create_order(client)
        login_as(client, "admin")
        original_orders = _orders(client)
        batch, upload = schedule(client, kind)
        exceptions = client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["items"]
        assert len(exceptions) == 2
        # An already handled work item is still covered by the whole-batch undo.
        changed = client.patch(f"{BASE}/exceptions/{exceptions[0]['id']}", json={
            "factory_id": "huaxing", "expected_revision": exceptions[0]["revision"], "status": "IN_PROGRESS",
        })
        assert changed.status_code == 200
        body = {"factory_id": "huaxing", "reason": "错误排期整批撤销"}
        path = f"{BASE}/imports/{batch['id']}/undo"
        assert client.post(path, json={**body, "factory_id": "huadeng"}).status_code == 404
        assert client.post(path, json={**body, "reason": "  x  "}).status_code == 422
        assert client.post(path, json={**body, "row_id": "1"}).status_code == 422
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "REJECTED"
        assert response.json()["parse_summary"] == batch["parse_summary"]
        assert client.post(path, json=body).status_code == 409
        assert client.post(f"{BASE}/{kind}-imports", **upload).status_code == 409
        assert client.get(f"{BASE}/exceptions", params={"factory_id": "huaxing"}).json()["total"] == 0
        assert client.get(f"{BASE}/imports/{batch['id']}", params={"factory_id": "huaxing"}).json()["status"] == "REJECTED"
        assert _orders(client) == original_orders
        assert client.get(f"{BASE}/inventory/movements", params={"factory_id": "huaxing"}).json()["items"] == []
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonException
        with SessionLocal() as db:
            for original in exceptions:
                saved = db.get(CartonException, original["id"])
                assert saved.status == "CLOSED"
                assert "整批撤销" in saved.resolution_note
                assert client.patch(f"{BASE}/exceptions/{saved.id}", json={
                    "factory_id": "huaxing", "expected_revision": saved.revision, "status": "OPEN",
                }).status_code == 409
        undo_events = [event for event in audits(client) if event["event_type"] == "SCHEDULE_IMPORT_UNDONE"]
        assert len(undo_events) == 1
        event = undo_events[0]
        assert event["actor_user_id"] and event["detail"]["batch_id"] == batch["id"]
        assert event["detail"]["row_count"] == event["detail"]["exception_count"] == 2
        assert event["detail"]["filename"] == "schedule.xlsx"
        assert event["detail"]["reason"] == body["reason"]
        assert len(event["detail"]["exceptions"]) == 2
        assert event["detail"]["batch"]["parse_summary"] == batch["parse_summary"]
        if kind == "weekly":
            from test_carton_history_delete_and_exception_bulk import create_exceptions
            delivery_rows = create_exceptions(client)
            response = client.post(f"{BASE}/imports/{delivery_rows[0]['source_id']}/undo", json=body)
            assert response.status_code == 409


@pytest.mark.parametrize("scope", ["missing", "foreign", "denied"])
def test_bulk_delete_and_undo_require_their_factory_scoped_write_permission(monkeypatch, scope):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        rows = histories(client)
        batch, _ = schedule(client)
        from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
        permissions = frozenset({"carton_procurement:order_write", "carton_procurement:import"})
        grants = () if scope == "missing" else (AuthGrantContext("role", "Role", "huadeng" if scope == "foreign" else "huaxing", "carton", permissions),)
        overrides = tuple(AuthOverrideContext(p, p, "deny", "huaxing", "carton") for p in permissions) if scope == "denied" else ()
        actor = AuthContext("operator", "operator", "Operator", (), (), permissions,
                            ("huaxing",), ("carton",), grants=grants, overrides=overrides)
        client.app.dependency_overrides[get_current_user] = lambda: actor
        assert client.post(f"{BASE}/orders/bulk-delete-history", json=bulk_body(rows)).status_code == 403
        assert client.post(f"{BASE}/imports/{batch['id']}/undo", json={"factory_id": "huaxing", "reason": "错误排期整批撤销"}).status_code == 403
        client.app.dependency_overrides.clear()
        assert _orders(client) == rows
        assert not any(event["event_type"] in {"SCHEDULE_IMPORT_UNDONE", "HISTORY_ORDER_DELETED"} for event in audits(client))


@pytest.mark.parametrize("operation", ["undo", "delete"])
def test_concurrent_destructive_actions_execute_once(monkeypatch, operation):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        if operation == "undo":
            batch, _ = schedule(client)
            path = f"{BASE}/imports/{batch['id']}/undo"
            payload = {"factory_id": "huaxing", "reason": "错误排期整批撤销"}
        else:
            path, payload = f"{BASE}/orders/bulk-delete-history", bulk_body(histories(client))
        from app.services import carton_procurement as service
        original_lock = service.lock_transaction
        barrier = Barrier(2)

        def synchronized_lock(*args, **kwargs):
            barrier.wait(timeout=10)
            return original_lock(*args, **kwargs)

        monkeypatch.setattr(service, "lock_transaction", synchronized_lock)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(path, json=payload), (1, 2)))
        monkeypatch.setattr(service, "lock_transaction", original_lock)
        assert sorted(response.status_code for response in responses) == ([200, 409] if operation == "undo" else [204, 404]), [r.text for r in responses]
