"""Factory-wide receiving keeps mixed originals intact and order ownership separate."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_customer_packaging import customer, assign
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import supplier_login
from test_carton_special_requests import setup, create_body, command, accept, ok, BASE, FACTORY
from test_carton_unified_deliveries import dispatch_body, receive_body, INTERNAL, EXTERNAL

CORE = "/api/carton-procurement"
SCOPE = {"factory_id": FACTORY}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def mixed_note(client):
    """Three sources, two customers owned by others, one original supplier note."""
    place = setup(client)
    other = customer(client, "OTHER", "另一客户")
    second = ok(client.post(CORE + "/orders", json={**_order_payload(),
        "customer_code": "OTHER", "contract_no": "FACTORY-RECEIVE-OTHER"}), 201)
    _submit_order(client, second)
    special = ok(client.post(BASE, json={**create_body(), "customer_code": "OTHER"}), 201)
    special = ok(client.post(BASE + f"/{special['id']}/send", json=command(special)))
    special = accept(client, special)
    portal = ok(client.get("/api/carton-supplier/workspace", params=SCOPE))
    for order in portal["orders"]:
        for line in order["lines"]:
            ok(client.put(f"/api/carton-supplier/papers/{line['id']}/commitment", json={**SCOPE,
                "issue_id": order["issue_id"], "expected_revision": 0, "promised_date": "2026-10-20"}))
    payload = dispatch_body(special)
    payload["delivery_note_no"] = "QA-MULTI-CUSTOMER-" + uuid4().hex[:8]
    payload["formal_lines"] = [{"order_line_id": line["id"], "issue_id": order["issue_id"],
        "quantity": "2", "unit_price": "2"} for order in portal["orders"] for line in order["lines"]]
    group = ok(client.post(EXTERNAL, json=payload), 201)
    login_as(client, "admin")
    ensure_test_user("warehouse_keeper"); ensure_test_user("carton_warehouse"); ensure_test_user("carton_supervisor")
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    with SessionLocal() as db:
        ids = dict(db.execute(select(AuthUser.username, AuthUser.id)).all())
    customers = ok(client.get(CORE + "/customers", params=SCOPE))["items"]
    for row in customers:
        if row["customer_code"] in {"DICKIE", "OTHER"}:
            assign(client, row, [ids["carton_warehouse" if row["customer_code"] == "DICKIE" else "carton_supervisor"]])
    login_as(client, "warehouse_keeper")
    return group, place, portal["orders"], special


def test_mixed_customers_partial_receive_retry_and_order_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        group, place, orders, special = mixed_note(client)
        scope = ok(client.get(CORE + "/customer-responsibilities", params={**SCOPE, "summary": True}))
        assert set(scope["blocked_customer_codes"]) == {"DICKIE", "OTHER"}
        assert not scope["unrestricted"]
        assert ok(client.get(CORE + "/orders", params=SCOPE))["total"] == 0
        assert client.post(CORE + "/orders", json=_order_payload()).status_code == 403
        assert client.post(BASE + f"/{special['id']}/cancel", json=command(special)).status_code == 403
        assert ok(client.get(BASE, params=SCOPE))["items"] == []
        assert client.get(BASE + f"/{special['id']}", params=SCOPE).status_code == 403
        detail = ok(client.get(BASE + f"/{special['id']}", params={**SCOPE, "receiving": True}))
        assert detail["permissions"]["can_receive"] and detail["permissions"]["can_manual_receive"]
        assert not any(value for key, value in detail["permissions"].items() if key not in {"can_receive", "can_manual_receive"})
        receiving = ok(client.get(BASE, params={**SCOPE, "receiving": True}))
        flags = next(row for row in receiving["items"] if row["id"] == special["id"])["permissions"]
        assert flags["can_receive"] and flags["can_manual_receive"]
        assert not any(value for key, value in flags.items() if key not in {"can_receive", "can_manual_receive"})
        workspace = ok(client.get(INTERNAL, params=SCOPE))
        assert workspace["total"] == 1
        assert workspace["items"][0]["id"] == group["id"] and workspace["items"][0]["can_operate"]
        assert len(workspace["items"][0]["lines"]) == len(group["lines"])
        internal = ok(client.get("/api/carton-supplier/internal/workspace", params=SCOPE))
        assert len(internal["orders"]) == 2 and internal["shipments"][0]["can_operate"]
        assert ok(client.get("/api/carton-supplier/internal/shipments/pending", params=SCOPE))["total"] == 1
        body = receive_body(group, place, "4")
        received = ok(client.post(INTERNAL + f"/{group['id']}/receive", json=body))
        assert received["status"] == "SENT"
        assert ok(client.post(INTERNAL + f"/{group['id']}/receive", json=body)) == received
        stale = {**body, "request_id": uuid4().hex}
        assert client.post(INTERNAL + f"/{group['id']}/receive", json=stale).status_code == 409
        continuation = receive_body(received, place, "6"); continuation["formal"] = None
        final = ok(client.post(INTERNAL + f"/{group['id']}/receive", json=continuation))
        assert final["status"] == "RECEIVED"
        assert ok(client.get("/api/carton-supplier/internal/shipments/pending", params=SCOPE))["total"] == 0
        history = ok(client.get(CORE + "/receipt-history", params=SCOPE))
        assert history["total"] == 3
        for receipt in history["items"]:
            assert client.get(CORE + f"/receipts/{receipt['id']}", params=SCOPE).status_code == 200
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonReceiptLine, CartonInventoryMovement
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 3
            expected = Decimal(2 * len(group["formal"]["lines"]) + 10)
            assert db.scalar(select(func.sum(CartonReceiptLine.effective_quantity))) == expected
            assert db.scalar(select(func.sum(CartonInventoryMovement.quantity))) == expected
        # Receipt scope must not turn into permanent order/customer delegation.
        assert ok(client.get(CORE + "/customer-responsibilities", params={**SCOPE, "summary": True})) == scope
        assert client.post(CORE + "/orders", json=_order_payload()).status_code == 403


def test_receiving_still_requires_factory_job_and_current_explicit_grants(monkeypatch):
    with make_client(monkeypatch) as client:
        group, place, _, special = mixed_note(client)
        body = receive_body(group, place)
        login_as(client, "a_warehouse_keeper")
        assert client.get(INTERNAL, params=SCOPE).status_code == 403
        assert client.get(BASE + f"/{special['id']}", params={**SCOPE, "receiving": True}).status_code == 403
        assert client.post(INTERNAL + f"/{group['id']}/receive", json=body).status_code == 403
        supplier_login(client)
        assert client.get(BASE + f"/{special['id']}", params={**SCOPE, "receiving": True}).status_code == 403
        assert client.post(INTERNAL + f"/{group['id']}/receive", json=body).status_code == 403
        assert client.get(BASE + f"/{special['id']}", params={**SCOPE, "receiving": True}).status_code == 403
        login_as(client, "warehouse_keeper")
        from app.db import SessionLocal
        from app.models.auth import AuthUser, AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            actor = db.scalar(select(AuthUser).where(AuthUser.username == "warehouse_keeper"))
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == "carton_procurement:receipt_write"))
            db.add(AuthUserPermissionOverride(id="deny-factory-receipt", user_id=actor.id,
                permission_id=permission.id, effect="deny", factory_id=FACTORY, department="*", status="active", reason="测试收料撤权"))
            db.commit()
        assert client.post(INTERNAL + f"/{group['id']}/receive", json=body).status_code == 403
        login_as(client, "admin")
        unchanged = ok(client.get(INTERNAL + f"/{group['id']}", params=SCOPE))
        assert not unchanged["receipts"]
        assert all(Decimal(line.get("received_quantity", "0")) == 0 for line in unchanged["lines"])


def test_manual_receive_other_customer_keeps_order_actions_restricted(monkeypatch):
    from test_carton_special_manual_receiving import manual_body
    with make_client(monkeypatch) as client:
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        place = setup(client)
        other = customer(client, "OTHER", "另一客户")
        special = ok(client.post(BASE, json={**create_body(), "customer_code": "OTHER"}), 201)
        special = ok(client.post(BASE + f"/{special['id']}/confirm", json=command(special)))
        ensure_test_user("warehouse_keeper")
        with SessionLocal() as db:
            admin_id = db.scalar(select(AuthUser.id).where(AuthUser.username == "admin"))
        assign(client, other, [admin_id])
        def assignment_ids():
            with SessionLocal() as db:
                return set(db.scalars(select(CartonCustomerAssignment.user_id).where(
                    CartonCustomerAssignment.factory_id == FACTORY,
                    CartonCustomerAssignment.customer_id == other['id'])))
        before = assignment_ids()
        assert before == {admin_id}
        login_as(client, "warehouse_keeper")
        payload = manual_body(special, place, quantity="4")
        result = ok(client.post(BASE + f"/{special['id']}/manual-receive", json=payload))
        assert assignment_ids() == before == {admin_id}
        assert ok(client.post(BASE + f"/{special['id']}/manual-receive", json=payload)) == result
        assert client.post(BASE + f"/{special['id']}/manual-receive", json={**payload, "request_id": uuid4().hex}).status_code == 409
        assert client.post(BASE + f"/{special['id']}/cancel", json=command(result)).status_code == 403
        login_as(client, "admin")
        from app.models.carton_procurement import CartonReceiptLine
        with SessionLocal() as db:
            line_id = db.scalar(select(CartonReceiptLine.id).where(CartonReceiptLine.customer_code == "OTHER"))
        source = ok(client.get(CORE + f"/price-corrections/{line_id}", params=SCOPE))
        login_as(client, "warehouse_keeper")
        correction = dict(factory_id=FACTORY, request_id=uuid4().hex, expected_revision=source["revision"],
            source_fingerprint=source["source_fingerprint"], action="PROPOSE", reason="测试非负责客户不得改价",
            proposed_unit_price="3", document_no="UNAUTHORIZED", document_date="2026-10-18")
        assert client.post(CORE + f"/price-corrections/{source['receipt_line_id']}/actions", json=correction).status_code == 403
