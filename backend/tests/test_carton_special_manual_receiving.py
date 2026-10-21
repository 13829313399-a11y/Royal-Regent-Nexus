"""Synthetic acceptance of warehouse-recorded notes and explicit order locking."""
from decimal import Decimal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import setup, created, create_body, command, ok, BASE, SUP, FACTORY, ship
from test_carton_supplier_portal import supplier_login


def manual_body(row, place, quantity="10", price=None, note=None):
    return command(row, delivery_note_no=note or "MANUAL-" + uuid4().hex[:12],
        delivery_date="2026-10-18", acceptance_date="2026-10-18",
        lines=[{"line_id": row["lines"][0]["id"], "received_quantity": quantity,
            "unit_price": price, "location_allocations": [{"location_id": place["id"], "quantity": quantity}]}])


def editable(row):
    data = create_body()
    data.update(command(row))
    data["lines"] = [{key: value for key, value in paper.items() if key in {
        "id", "item_no", "packaging_type", "paper_quality", "specification",
        "dimension_unit", "quantity", "unit", "mark_mode"}} for paper in row["lines"]]
    return data


def test_manual_note_posts_once_with_unknown_vendor_prices_and_supplier_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = created(client)
        payload = manual_body(row, place)
        path = BASE + f"/{row['id']}/manual-receive"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post(path, json=payload), range(2)))
        row = ok(results[0])
        assert ok(results[1]) == row
        assert row["status"] == "PARTIALLY_RECEIVED"
        assert row["shipments"][0]["source_origin"] == "WAREHOUSE_MANUAL"
        assert row["shipments"][0]["lines"][0]["snapshot"]["warehouse_unit_price"] is None
        assert ok(client.post(path, json=payload)) == row
        assert client.post(path, json={**payload, "acceptance_date": "2026-10-17"}).status_code == 409
        # A different request identity cannot register the same original note.
        duplicate = manual_body(row, place, note=payload["delivery_note_no"])
        assert client.post(path, json=duplicate).status_code == 409
        row = ok(client.post(path, json=manual_body(row, place, price="0")))
        row = ok(client.post(path, json=manual_body(row, place, price="2.5")))
        from app.db import SessionLocal
        from app.models.carton_price_review import CartonPriceReview
        from app.models.carton_special_requests import SpecialShipment, SpecialReceiptLink, SpecialRequest
        from app.models.carton_procurement import CartonInventoryMovement
        from app.services.carton_supplier_settlement import sources
        with SessionLocal() as db:
            reviews = list(db.scalars(select(CartonPriceReview)))
            assert len(reviews) == 3
            assert all(value.original_unit_price is None for value in reviews)
            assert sorted(value.status for value in reviews) == ["PENDING", "PROPOSED", "PROPOSED"]
            assert db.scalar(select(func.count()).select_from(SpecialShipment)) == 3
            assert db.scalar(select(func.count()).select_from(SpecialReceiptLink)) == 3
            assert db.scalar(select(func.sum(CartonInventoryMovement.quantity)).where(
                CartonInventoryMovement.movement_type == "INBOUND")) == Decimal(30)
            payable = sources(db, FACTORY, db.get(SpecialRequest, row["id"]).supplier_id, "2026-10", "CNY")[0]
            assert len(payable) == 3 and all(value["amount"] is None for value in payable)
            assert all(value["supplier_delivery"]["original_unit_price"] is None for value in payable)
            priced_id = next(value.id for value in reviews if value.proposed_unit_price == Decimal("2.5"))
        supplier_login(client)
        external = ok(client.get(SUP + f"/{row['id']}", params={"factory_id": FACTORY}))
        assert len(external["shipments"]) == 3
        groups = ok(client.get("/api/carton-supplier/unified-deliveries", params={"factory_id": FACTORY}))
        manual = next(value for value in groups["items"] if value["id"] == row["manual_delivery_id"])
        assert manual["lines"][0]["delivery_unit_price"] is None
        from app.schemas.carton_price_review import Decide
        from app.services.carton_price_review import act
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        with SessionLocal() as db:
            user = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == "supplier-test")))
            result = act(db, user, priced_id, Decide(factory_id=FACTORY, request_id=uuid4().hex,
                expected_revision=1, decision="CONFIRM", reason="核实原单价格"), external=True)
            assert result["status"] == "CONFIRMED" and Decimal(result["effective_unit_price"]) == Decimal("2.5")


def test_locked_adjustment_and_pending_original_note_block_parallel_receipts(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = ok(client.post(BASE, json=create_body()), 201)
        assert row["permissions"]["can_edit"] and row["permissions"]["can_confirm"]
        assert client.post(BASE + f"/{row['id']}/manual-receive", json=manual_body(row, place)).status_code == 409
        row = ok(client.post(BASE + f"/{row['id']}/confirm", json=command(row)))
        assert not row["permissions"]["can_edit"] and row["permissions"]["can_adjust"]
        assert client.put(BASE + f"/{row['id']}", json=editable(row)).status_code == 409
        adjustment = dict(editable(row), reason="调整实际需要数量")
        adjustment["lines"][0]["quantity"] = "120"
        row = ok(client.post(BASE + f"/{row['id']}/adjust", json=adjustment))
        assert row["history"] and row["history"][-1]["action"] == "ADJUSTED", row
        assert row["messages"][-1]["body"] == "订单调整：调整实际需要数量"
        row = ok(client.post(BASE + f"/{row['id']}/manual-receive", json=manual_body(row, place, price="2")))
        adjustment = dict(editable(row), reason="部分收料后调整")
        adjustment["lines"][0]["quantity"] = "110"
        row = ok(client.post(BASE + f"/{row['id']}/adjust", json=adjustment))
        assert row["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(row["lines"][0]["received_quantity"]) == 10
        row = ship(client, row, quantity="10")
        login_as(client, "admin")
        response = client.post(BASE + f"/{row['id']}/manual-receive", json=manual_body(row, place))
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "EXISTING_DELIVERY_PENDING"
        assert response.json()["detail"]["shipment_ids"]
        adjustment = dict(editable(row), reason="禁止在途修改需求")
        assert client.post(BASE + f"/{row['id']}/adjust", json=adjustment).status_code == 409


def test_manual_receipt_accepts_pending_marks_but_rejects_scope_overreceipt_and_reversed_original(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = created(client)
        path = BASE + f"/{row['id']}/manual-receive"
        assert client.post(path, json=manual_body(row, place, quantity="101")).status_code == 409
        payload = manual_body(row, place)
        assert client.post(path, json={**payload, "factory_id": "huakang-b"}).status_code == 404
        supplier_login(client)
        assert client.post(path, json=payload).status_code == 403
        login_as(client, "admin")
        # Warehouse accepts the physical goods without inventing confirmed marks.
        row = ok(client.post(BASE + f"/{row['id']}/lines/{row['lines'][0]['id']}/mark",
            json=command(row, mark_mode="PENDING")))
        row = ok(client.post(path, json=manual_body(row, place)))
        assert row['lines'][0]['mark_mode'] == 'PENDING' and not row['lines'][0]['mark_ready']
        assert row['shipments'][0]['lines'][0]['snapshot']['mark_mode'] == 'PENDING'
        delivery_id = row["manual_delivery_id"]
        receipt = row["shipments"][0]["receipts"][0]
        ok(client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse",
            json={"factory_id": FACTORY, "expected_revision": receipt["revision"], "reason": "核实原单重新收料"}))
        row = ok(client.get(BASE + f"/{row['id']}", params={"factory_id": FACTORY}))
        response = client.post(path, json=manual_body(row, place))
        assert response.status_code == 409
        assert response.json()["detail"]["delivery_ids"] == [delivery_id]


def test_warehouse_can_reject_unconfirmed_miscellaneous_goods_without_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        from app.models.carton_procurement import CartonInventoryMovement
        with SessionLocal() as db:
            db.add(CartonMasterRecord(id='misc-receipt-workshop', factory_id=FACTORY,
                kind='WORKSHOP', identity='misc-receipt', code='验收车间', data_json='{}', status='ACTIVE'))
            db.commit()
        body = create_body('WORKSHOP_MISC')
        body['workshop_id'] = 'misc-receipt-workshop'
        body['lines'][0]['mark_mode'] = 'PENDING'
        row = ok(client.post(BASE, json=body), 201)
        row = ok(client.post(BASE + f"/{row['id']}/confirm", json=command(row)))
        payload = manual_body(row, place)
        payload['lines'][0].update(rejected_quantity='10', location_allocations=[])
        row = ok(client.post(BASE + f"/{row['id']}/manual-receive", json=payload))
        assert not row['lines'][0]['mark_ready']
        receipt = row['shipments'][0]['receipts'][0]
        assert Decimal(receipt['lines'][0]['rejected_quantity']) == 10
        assert Decimal(receipt['lines'][0]['effective_quantity']) == 0
        with SessionLocal() as db:
            assert (db.scalar(select(func.sum(CartonInventoryMovement.quantity)).where(
                CartonInventoryMovement.movement_type == 'INBOUND')) or Decimal(0)) == 0


def test_manual_receipt_requires_inventory_and_customer_responsibility(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        place = setup(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.models.auth import AuthUser
        from test_carton_supplier_portal import grant_supplier_permissions, PASSWORD
        with SessionLocal() as db:
            customer = db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == FACTORY))
            customer_code, customer_id = customer.customer_code, customer.id
            admin_id = db.scalar(select(AuthUser.id).where(AuthUser.username == "admin"))
        body = create_body()
        body["customer_code"] = customer_code
        row = ok(client.post(BASE, json=body), 201)
        row = ok(client.post(BASE + f"/{row['id']}/confirm", json=command(row)))
        permissions = ("carton_procurement:read", "carton_procurement:receipt_write")
        grant_supplier_permissions(permissions=permissions)
        ok(client.post("/api/auth/login", json={"username": "supplier-test", "password": PASSWORD}))
        path = BASE + f"/{row['id']}/manual-receive"
        payload = manual_body(row, place)
        assert client.post(path, json=payload).status_code == 403
        grant_supplier_permissions(permissions=("carton_procurement:inventory_write",))
        ok(client.post("/api/auth/login", json={"username": "supplier-test", "password": PASSWORD}))
        with SessionLocal() as db:
            db.add(CartonCustomerAssignment(factory_id=FACTORY, customer_id=customer_id, user_id=admin_id))
            db.commit()
        assert client.post(path, json=payload).status_code == 403
        for scope in ("OWN", "ALL"):
            workspace = ok(client.get(BASE, params={"factory_id": FACTORY, "responsibility_scope": scope}))
            assert not any(value["id"] == row["id"] for value in workspace["items"])
