from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from uuid import uuid4
import importlib.util
import json
from pathlib import Path
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _order_payload

BASE = "/api/carton-supplier"
PASSWORD = "SupplierOnly123!"

def setup_portal(client):
    login_as(client, "admin")
    order = _create_order(client)
    response = client.post(f"/api/carton-procurement/orders/{order['order_no']}/purchase-order-issues.xlsx",
        json={"factory_id": "huaxing", "expected_revision": order["revision"]})
    assert response.status_code == 200, response.text
    from app.db import SessionLocal
    from app.models.auth import AuthUser, EmployeeProfile
    from app.services.auth import make_password_hash
    salt, digest = make_password_hash(PASSWORD)
    with SessionLocal() as db:
        db.add(AuthUser(id="supplier-test", username="supplier-test", display_name="供应商测试", password_salt=salt,
            password_hash=digest, status="active", force_password_change=0, created_at="2026-09-21", updated_at="2026-09-21"))
        db.add(EmployeeProfile(user_id="supplier-test", primary_factory_id="huaxing",
            primary_department="pmc-warehouse", position="供应商联系人",
            confirmation_status="confirmed", created_at="2026-09-21", updated_at="2026-09-21"))
        db.commit()
    login_as(client, "admin")
    bound = client.put(BASE + "/internal/members", json={"factory_id":"huaxing", "username":"supplier-test", "expected_revision":0, "reason":"测试明确授权绑定"})
    assert bound.status_code == 200, bound.text
    supplier_login(client)
    return order

def supplier_login(client):
    result = client.post("/api/auth/login", json={"username":"supplier-test", "password":PASSWORD})
    assert result.status_code == 200, result.text
    assert not result.json()["permissions"]

def accept_all(client):
    workspace = client.get(BASE+"/workspace", params={"factory_id":"huaxing"}).json()
    order = workspace["orders"][0]
    for line in order["lines"]:
        response = client.put(BASE+f"/papers/{line['id']}/commitment", json={"factory_id":"huaxing", "issue_id":order["issue_id"], "expected_revision":0, "promised_date":"2026-09-23"})
        assert response.status_code == 200, response.text
    return order

def ship_payload(order):
    return {"factory_id":"huaxing", "request_id":str(uuid4()), "delivery_note_no":"DN-PORTAL", "delivery_date":"2026-09-21",
        "lines":[{"order_line_id":line["id"], "issue_id":order["issue_id"], "quantity":10} for line in order["lines"]]}

def receive_payload(client, shipment):
    locations = client.get("/api/carton-procurement/inventory/locations", params={"factory_id":"huaxing"}).json()
    location = next(row["id"] for row in locations if row["bin_code"] == "A-01")
    return {"factory_id":"huaxing", "request_id":str(uuid4()), "expected_revision":shipment["revision"], "acceptance_date":"2026-09-21",
        "lines":[{"shipment_line_id":line["id"], "received_quantity":8, "unit_price":2,
            "paper_quality":line["paper_quality"], "specification":line["specification"],
            "location_allocations":[{"location_id":location,"quantity":8}], "difference_reason":"本次实际短收两件"} for line in shipment["lines"]]}

def test_supplier_mark_templates_require_issued_order_membership_and_ready_latest_version(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkDocument, CartonMarkTemplate
        from app.models.carton_procurement import CartonOrder
        from app.models.carton_supplier_portal import SupplierMember

        def add_template(db, key, *, factory="huaxing", customer="Dickie", item=None,
                         version=1, status="核对通过", released=False, archived=False):
            template = CartonMarkTemplate(id=key, factory_id=factory,
                customer_name=customer, po=order["contract_no"],
                item=item or order["item_no"], contract_number=order["contract_no"],
                business_key_sha256=key.ljust(64, "0"), document_fingerprint=key.ljust(64, "1"),
                version=version, check_status=status, check_result_json='{"private_check":"secret"}',
                excel_sha256="a" * 64, pdf_sha256="b" * 64,
                created_by="admin", created_at=f"2026-09-21T00:00:{version:02d}",
                updated_at=f"2026-09-21T00:00:{version:02d}",
                manual_released_at="2026-09-21T01:00:00" if released else "",
                is_archived=archived)
            db.add(template)
            db.flush()
            for kind, filename, content_type, content in (
                ("source_excel", "customer.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"excel-data"),
                ("print_pdf", "print.pdf", "application/pdf", b"%PDF-1.4 test"),
            ):
                db.add(CartonMarkDocument(id=f"{key}-{kind}", template_id=key, factory_id=factory,
                    kind=kind, file_name=filename, content_type=content_type,
                    size_bytes=len(content), sha256="a" * 64, content=content,
                    created_at="2026-09-21T00:00:00"))

        with SessionLocal() as db:
            add_template(db, "match-v1")
            add_template(db, "wrong-customer", customer="Other")
            add_template(db, "wrong-item", item="OTHER-ITEM")
            add_template(db, "wrong-factory", factory="huadeng")
            db.commit()

        url = BASE + "/carton-mark/templates"
        download = BASE + "/carton-mark/templates/{}/documents/{}"
        records = client.get(url, params={"factory_id": "huaxing"})
        assert records.status_code == 200, records.text
        assert [row["id"] for row in records.json()] == ["match-v1"]
        assert "private_check" not in records.text and "created_by" not in records.text
        assert client.get(download.format("match-v1", "source_excel"), params={"factory_id": "huaxing"}).content == b"excel-data"
        assert client.get(download.format("match-v1", "print_pdf"), params={"factory_id": "huaxing"}).content == b"%PDF-1.4 test"
        preview = client.get(download.format("match-v1", "print_pdf"), params={"factory_id": "huaxing", "preview": "true"})
        assert preview.status_code == 200 and preview.headers["content-disposition"].startswith("inline;")
        for hidden in ("wrong-customer", "wrong-item", "wrong-factory"):
            assert client.get(download.format(hidden, "print_pdf"), params={"factory_id": "huaxing"}).status_code == 404
        assert client.get(url, params={"factory_id": "huadeng"}).status_code in (403, 422)
        assert client.get(download.format("match-v1", "other"), params={"factory_id": "huaxing"}).status_code == 422
        assert client.get("/api/carton-mark/templates", params={"factory_id": "huaxing"}).status_code == 403

        with SessionLocal() as db:
            add_template(db, "match-v2", version=2, status="需复核")
            db.commit()
        assert client.get(url, params={"factory_id": "huaxing"}).json() == []
        assert client.get(download.format("match-v1", "print_pdf"), params={"factory_id": "huaxing"}).status_code == 404

        with SessionLocal() as db:
            db.get(CartonMarkTemplate, "match-v2").manual_released_at = "2026-09-21T01:00:00"
            db.commit()
        assert [row["id"] for row in client.get(url, params={"factory_id": "huaxing"}).json()] == ["match-v2"]

        with SessionLocal() as db:
            db.get(CartonMarkTemplate, "match-v2").is_archived = True
            db.commit()
        assert client.get(url, params={"factory_id": "huaxing"}).json() == []

        with SessionLocal() as db:
            db.get(CartonMarkTemplate, "match-v2").is_archived = False
            db.get(CartonOrder, order["id"]).status = "CANCELLED"
            db.commit()
        assert client.get(download.format("match-v2", "print_pdf"), params={"factory_id": "huaxing"}).status_code == 404

        with SessionLocal() as db:
            db.get(CartonOrder, order["id"]).status = "PENDING_SUPPLIER"
            member = db.query(SupplierMember).filter_by(user_id="supplier-test").one()
            member.status = "INACTIVE"
            db.commit()
        assert client.get(url, params={"factory_id": "huaxing"}).status_code == 403


def test_supplier_membership_scope_and_whitelist(monkeypatch):
    with make_client(monkeypatch) as client:
        assert client.get(BASE+"/workspace", params={"factory_id":"huaxing"}).status_code == 401
        order = setup_portal(client)
        workspace = client.get(BASE+"/workspace", params={"factory_id":"huaxing"})
        assert workspace.status_code == 200
        serialized = json.dumps(workspace.json())
        for forbidden in ("unit_price", "currency", "note", "created_by", "customer_code", "location_allocations", "supplier_id"):
            assert f'"{forbidden}"' not in serialized
        assert client.get(BASE+"/workspace", params={"factory_id":"huadeng"}).status_code in (403,422)
        assert client.get(BASE+"/internal/workspace", params={"factory_id":"huaxing"}).status_code == 403
        assert client.get("/api/carton-procurement/orders",params={"factory_id":"huaxing"}).status_code == 403
        assert client.put(BASE+"/internal/members", json={"factory_id":"huaxing","username":"supplier-test","expected_revision":1,"reason":"非法自行绑定测试"}).status_code == 403
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="other-supplier",factory_id="huaxing",supplier_code="OTHER",supplier_name="其他供应商",status="ACTIVE",created_at="2026-09-21",updated_at="2026-09-21")); db.flush()
            db.get(CartonOrder,order["id"]).supplier_id="other-supplier"; db.commit()
        assert client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).status_code == 403
        assert client.put(BASE+f"/papers/{order['lines'][0]['id']}/commitment",json={"factory_id":"huaxing","issue_id":"guess","expected_revision":0,"promised_date":"2026-09-23"}).status_code == 403
        login_as(client,"warehouse_keeper")
        assert client.put(BASE+"/internal/members",json={"factory_id":"huaxing","username":"supplier-test","expected_revision":1,"reason":"仓管不可自行绑定"}).status_code == 403
        assert client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).status_code == 403


def test_supplier_account_sees_same_supplier_issued_factories_without_internal_factory_role(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        manager = login_as(client, "manager")
        assert {"carton_procurement:master_manage", "carton_procurement:order_adjust"}.issubset(manager["permissions"])
        assert client.put(BASE + "/internal/members", json={
            "factory_id": "huaxing", "username": "supplier-test", "expected_revision": 1,
            "status": "ACTIVE", "reason": "普通经理尝试开通跨厂账号"}).status_code == 403
        supplier_login(client)
        memberships = client.get(BASE + "/memberships")
        assert memberships.status_code == 200
        assert [item["factory_id"] for item in memberships.json()] == ["huaxing"]
        assert client.get(BASE + "/workspace", params={"factory_id": "huakang-a"}).status_code == 403

        login_as(client, "admin")
        customer = client.post("/api/carton-procurement/customers", json={
            "factory_id": "huakang-a", "customer_code": "DICKIE", "customer_name": "Dickie", "country_region": "德国"})
        assert customer.status_code == 201, customer.text
        payload = _order_payload()
        payload.update(factory_id="huakang-a", contract_no="SC-HUAKANG-A")
        created = client.post("/api/carton-procurement/orders", json=payload)
        assert created.status_code == 201, created.text
        order = created.json()
        submitted = client.post(f"/api/carton-procurement/orders/{order['order_no']}/submit-supplier",
            json={"factory_id": "huakang-a", "expected_revision": order["revision"]})
        assert submitted.status_code == 200, submitted.text
        issued = client.post(f"/api/carton-procurement/orders/{order['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huakang-a", "expected_revision": submitted.json()["revision"]})
        assert issued.status_code == 200, issued.text

        supplier_login(client)
        memberships = client.get(BASE + "/memberships")
        assert [item["factory_id"] for item in memberships.json()] == ["huakang-a", "huaxing"]
        scope = client.get(BASE + "/workspace", params={"factory_id": "huakang-a"})
        assert scope.status_code == 200, scope.text
        assert [item["contract_no"] for item in scope.json()["orders"]] == ["SC-HUAKANG-A"]
        assert client.get(BASE + "/carton-mark/templates", params={"factory_id": "huakang-a"}).status_code == 200
        supplier_order = scope.json()["orders"][0]
        assert supplier_order["order_date"] == order["order_date"]
        paper = supplier_order["lines"][0]
        accepted = client.put(BASE + "/commitments/batch", json={
            "factory_id": "huakang-a", "lines": [{
                "order_line_id": line["id"], "issue_id": supplier_order["issue_id"],
                "expected_revision": line["commitment_revision"], "promised_date": "2026-09-23",
            } for line in supplier_order["lines"]]})
        assert accepted.status_code == 200, accepted.text
        shipment = client.post(BASE + "/shipments", json={
            "factory_id": "huakang-a", "request_id": str(uuid4()),
            "delivery_note_no": "DN-HUAKANG-A", "delivery_date": "2026-09-23",
            "lines": [{"order_line_id": paper["id"], "issue_id": supplier_order["issue_id"], "quantity": 1}]})
        assert shipment.status_code == 201, shipment.text
        assert client.get("/api/carton-procurement/orders", params={"factory_id": "huakang-a"}).status_code == 403
        assert client.get(BASE + "/workspace", params={"factory_id": "huadeng"}).status_code == 403

        login_as(client, "admin")
        denied = client.put(BASE + "/internal/members", json={
            "factory_id": "huakang-a", "username": "supplier-test", "expected_revision": 0,
            "status": "INACTIVE", "reason": "明确停用此厂区外部访问"})
        assert denied.status_code == 200, denied.text
        supplier_login(client)
        assert [item["factory_id"] for item in client.get(BASE + "/memberships").json()] == ["huaxing"]
        assert client.get(BASE + "/workspace", params={"factory_id": "huakang-a"}).status_code == 403


def test_confirmed_order_is_immediately_visible_to_supplier_without_separate_issue(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        created = _create_order(client, submit_supplier=False)
        confirmed = client.post(f"/api/carton-procurement/orders/{created['order_no']}/submit-supplier",
            json={"factory_id": "huaxing", "expected_revision": created["revision"]})
        assert confirmed.status_code == 200, confirmed.text
        context = client.get(f"/api/carton-procurement/orders/{created['order_no']}/purchase-order-context",
            params={"factory_id": "huaxing"}).json()
        assert context["pending_type"] == "NONE"
        assert len(context["issues"]) == 1
        assert context["issues"][0]["document_no"].endswith("-P00")
        redownload = client.post(f"/api/carton-procurement/orders/{created['order_no']}/purchase-order-issues.xlsx",
            json={"factory_id": "huaxing", "expected_revision": confirmed.json()["revision"]})
        assert redownload.status_code == 200, redownload.text
        assert redownload.headers["x-purchase-order-issue-id"] == context["issues"][0]["id"]
        supplier_login(client)
        orders = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"]
        assert created["order_no"] in {row["order_no"] for row in orders}

def test_partial_receipt_atomicity_replay_and_remaining(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order=accept_all(client); payload=ship_payload(order)
        shipped=client.post(BASE+"/shipments",json=payload)
        assert shipped.status_code == 201, shipped.text
        shipment=shipped.json()
        assert client.post(BASE+"/shipments",json=payload).json()["id"] == shipment["id"]
        altered={**payload,"delivery_note_no":"changed"}
        assert client.post(BASE+"/shipments",json=altered).status_code == 409
        login_as(client,"warehouse_keeper")
        assert client.get("/api/carton-procurement/receipts",params={"factory_id":"huaxing"}).json()["total"] == 0
        receive=receive_payload(client,shipment)
        excess=json.loads(json.dumps(receive));excess["lines"][0]["received_quantity"]=11
        assert client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=excess).status_code == 422
        invalid=json.loads(json.dumps(receive));invalid["lines"][-1]["unit_price"]=0
        denied=client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=invalid)
        assert denied.status_code == 422,denied.text
        assert client.get("/api/carton-procurement/receipts",params={"factory_id":"huaxing"}).json()["total"] == 0
        received=client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=receive)
        assert received.status_code == 200,received.text
        replay=client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=receive)
        assert replay.status_code == 200 and replay.json()["receipt_id"] == received.json()["receipt_id"]
        receive["request_id"]=str(uuid4())
        assert client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=receive).status_code == 409
        assert client.get("/api/carton-procurement/receipts",params={"factory_id":"huaxing"}).json()["total"] == 1
        supplier_login(client)
        data=client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).json()
        assert data["orders"][0]["status"] == "PARTIALLY_RECEIVED"
        assert [float(line["received_quantity"]) for line in data["orders"][0]["lines"]] == [8,8]
        assert float(data["orders"][0]["lines"][0]["remaining_to_ship"]) == 22
        assert "unit_price" not in json.dumps(data["shipments"])
        next_delivery=ship_payload(order);next_delivery["delivery_note_no"]="DN-NEXT-PARTIAL"
        response=client.post(BASE+"/shipments",json=next_delivery)
        assert response.status_code == 201,response.text
        login_as(client,"warehouse_keeper")
        current=client.get("/api/carton-procurement/orders",params={"factory_id":"huaxing"}).json()["items"][0]
        returned=client.post(f"/api/carton-procurement/orders/{current['order_no']}/return",json={"factory_id":"huaxing","expected_revision":current["revision"],"reason":"已有在途不能先退单"})
        assert returned.status_code == 409 and "在途" in returned.text,returned.text

def test_positive_receipts_require_complete_locations_before_any_write(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        shipment = client.post(BASE+"/shipments", json=ship_payload(order)).json()
        login_as(client, "warehouse_keeper")
        payload = receive_payload(client, shipment)
        from sqlalchemy import func, select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonInventoryMovement
        from app.models.carton_supplier_portal import SupplierShipment
        for allocations, message in [([], "必须选择"), ([{**payload["lines"][-1]["location_allocations"][0], "quantity": 7}], "之和必须等于"), ([{"location_id": "missing-location", "quantity": 8}], "仓位")]:
            invalid = json.loads(json.dumps(payload))
            invalid["lines"][-1]["location_allocations"] = allocations
            result = client.post(BASE+f"/internal/shipments/{shipment['id']}/receive", json=invalid)
            assert result.status_code in (404, 422) and message in result.text, result.text
            with SessionLocal() as db:
                assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 0
                assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 0
                assert db.get(SupplierShipment, shipment["id"]).status == "SENT"
        # Physically received but fully rejected paper has zero effective stock and needs no allocation.
        payload["lines"][-1].update(received_quantity=10, rejected_quantity=10, location_allocations=[], difference_reason="全部拒收不计入库存")
        result = client.post(BASE+f"/internal/shipments/{shipment['id']}/receive", json=payload)
        assert result.status_code == 200, result.text
        with SessionLocal() as db:
            movements = list(db.scalars(select(CartonInventoryMovement)).all())
            assert len(movements) == 1 and float(movements[0].quantity) == 8
            assert db.get(SupplierShipment, shipment["id"]).status == "RECEIVED"


@pytest.mark.parametrize("all_zero", [False, True])
def test_unreceived_papers_release_transit_without_positive_inventory(monkeypatch, all_zero):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client); order = accept_all(client)
        shipment = client.post(BASE+"/shipments", json=ship_payload(order)).json()
        login_as(client,"warehouse_keeper")
        payload = receive_payload(client, shipment)
        zeros = payload["lines"] if all_zero else payload["lines"][-1:]
        for line in zeros:
            line["received_quantity"] = 0; line["unit_price"] = 0; line["location_allocations"] = []
            line["difference_reason"] = "本纸品尚未实际送到"
        if all_zero:
            from app.db import SessionLocal
            from app.models.carton_procurement import CartonOrder
            with SessionLocal() as db:
                db.get(CartonOrder,raw["id"]).status="CANCELLED";db.commit()
        result=client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=payload)
        assert result.status_code == 200,result.text
        assert result.json()["status"] == ("NOT_RECEIVED" if all_zero else "RECEIVED")
        receipts=client.get("/api/carton-procurement/receipts",params={"factory_id":"huaxing"}).json()
        assert receipts["total"] == (0 if all_zero else 1)
        if not all_zero:
            assert len(receipts["items"][0]["lines"]) == 1
        repeated=client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=payload)
        assert repeated.status_code == 200 and repeated.json()["id"] == shipment["id"]
        supplier_login(client)
        result=client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).json()
        assert all(float(line["in_transit_quantity"]) == 0 for line in result["orders"][0]["lines"])
        assert float(result["orders"][0]["lines"][-1]["received_quantity"]) == 0


def test_concurrent_shipments_reserve_capacity_and_replay(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client);order=accept_all(client);payload=ship_payload(order)
        payload["lines"]=payload["lines"][:1];payload["lines"][0]["quantity"]=20
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services.carton_supplier_portal import create_shipment
        from app.schemas.carton_supplier_portal import ShipmentCreate
        barrier=Barrier(2)
        def execute(body):
            with SessionLocal() as db:
                user=build_auth_context(db,db.get(AuthUser,"supplier-test"));barrier.wait()
                try:return create_shipment(db,user,ShipmentCreate(**body))["id"]
                except Exception as exc:db.rollback();return getattr(exc,"status_code",str(exc))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(execute,payload) for _ in range(2)]
            results=[future.result(timeout=30) for future in futures]
        assert results[0] == results[1] and isinstance(results[0],str),results
        second={**payload,"request_id":str(uuid4()),"delivery_note_no":"SECOND"}
        assert client.post(BASE+"/shipments",json=second).status_code == 409
        second["lines"][0]["quantity"]=10
        assert client.post(BASE+"/shipments",json=second).status_code == 201

def test_cross_entry_transit_blocks_reduction_cancellation_and_manual_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        raw=setup_portal(client);order=accept_all(client)
        shipment=client.post(BASE+"/shipments",json=ship_payload(order)).json()
        login_as(client,"warehouse_keeper")
        for action,payload in [("reduce", {"reduction_quantity":3600}), ("cancel", {})]:
            result=client.post(f"/api/carton-procurement/orders/{raw['order_no']}/{action}",json={"factory_id":"huaxing","expected_revision":raw["revision"],"reason":"测试跨入口需求保护",**payload})
            assert result.status_code == 409 and "在途" in result.text,result.text
        bulk=client.post("/api/carton-procurement/orders/bulk-cancel",json={"factory_id":"huaxing","reason":"测试批量取消跨入口", "items":[{"order_no":raw["order_no"],"expected_revision":raw["revision"]}]})
        assert bulk.status_code == 409 and "在途" in bulk.text,bulk.text
        for note in (shipment["delivery_note_no"],"DIFFERENT-NOTE"):
            response=client.post("/api/carton-procurement/receipts",json={"factory_id":"huaxing","delivery_note_no":note,"delivery_date":"2026-09-21", "lines":[{"order_line_id":raw["lines"][0]["id"],"delivered_quantity":1,"received_quantity":1,"unit_price":2}]})
            assert response.status_code == 409 and "供应商" in response.text,response.text
        receive=receive_payload(client,shipment)
        for line in receive["lines"]:
            line.update(received_quantity=0,unit_price=0,location_allocations=[],difference_reason="供应商误报尚未送达")
        assert client.post(BASE+f"/internal/shipments/{shipment['id']}/receive",json=receive).status_code == 200
        reduced=client.post(f"/api/carton-procurement/orders/{raw['order_no']}/reduce",json={"factory_id":"huaxing","expected_revision":raw["revision"],"reason":"未发货允许全量退单","reduction_quantity":3600})
        assert reduced.status_code == 200 and reduced.json()["status"] == "CANCELLED",reduced.text


def test_supplier_cannot_reuse_an_existing_receipt_delivery_note(monkeypatch):
    with make_client(monkeypatch) as client:
        raw=setup_portal(client);order=accept_all(client)
        login_as(client,"warehouse_keeper")
        existing=client.post("/api/carton-procurement/receipts",json={"factory_id":"huaxing","delivery_note_no":"DN-PORTAL","delivery_date":"2026-09-21","lines":[{"order_line_id":raw["lines"][0]["id"],"delivered_quantity":1,"received_quantity":1,"unit_price":2}]})
        assert existing.status_code == 201,existing.text
        supplier_login(client)
        response=client.post(BASE+"/shipments",json=ship_payload(order))
        assert response.status_code == 409 and "已有收料记录" in response.text,response.text


def test_state_changes_unissued_versions_and_unbound_revocation(monkeypatch):
    with make_client(monkeypatch) as client:
        raw=setup_portal(client);order=accept_all(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder,CartonOrderLine
        with SessionLocal() as db:
            db.get(CartonOrderLine,order["lines"][0]["id"]).required_quantity+=1;db.commit()
        data=client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).json()["orders"][0]
        assert data["awaiting_issue"] and not data["lines"][0]["accepted"]
        assert float(data["lines"][0]["required_quantity"]) == 30
        assert client.post(BASE+"/shipments",json=ship_payload(order)).status_code == 409
        with SessionLocal() as db:
            db.get(CartonOrder,raw["id"]).status="CANCELLED";db.commit()
        assert client.put(BASE+f"/papers/{order['lines'][0]['id']}/commitment",json={"factory_id":"huaxing","issue_id":order["issue_id"],"expected_revision":1,"promised_date":"2026-09-24"}).status_code == 409
        login_as(client,"admin")
        assert client.put(BASE+"/internal/members",json={"factory_id":"huaxing","username":"supplier-test","expected_revision":1,"status":"INACTIVE","reason":"停用供应商测试绑定"}).status_code == 200
        supplier_login(client)
        assert client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).status_code == 403

def test_replacement_sources_cannot_be_misclassified_as_ordinary_supplier_delivery(monkeypatch):
    with make_client(monkeypatch) as client:
        raw=setup_portal(client);order=accept_all(client)
        import app.services.carton_supplier_portal as portal
        monkeypatch.setattr(portal,"blocked_replacement_lines",lambda db,factory,ids:{order["lines"][0]["id"]})
        result=client.get(BASE+"/workspace",params={"factory_id":"huaxing"}).json()["orders"][0]
        assert "补单" in result["lines"][0]["shipping_blocked_reason"]
        response=client.post(BASE+"/shipments",json=ship_payload(order))
        assert response.status_code == 409 and "补单" in response.text
        login_as(client,"admin")
        binding=client.put(BASE+"/internal/members",json={"factory_id":"huaxing","username":"warehouse_keeper","expected_revision":0,"reason":"不可混用内部权限账号"})
        assert binding.status_code == 409 and "独立供应商账号" in binding.text


def test_supplier_access_stops_when_bound_account_receives_an_internal_role(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        from app.db import SessionLocal
        from app.models.auth import AuthRole, AuthUserRole
        from sqlalchemy import select

        with SessionLocal() as db:
            role = db.scalar(select(AuthRole).where(AuthRole.code == "warehouse_keeper"))
            assert role is not None
            db.add(AuthUserRole(id="supplier-now-internal", user_id="supplier-test", role_id=role.id,
                                factory_id="huaxing", department="pmc-warehouse"))
            db.commit()

        assert client.get(BASE + "/memberships").json() == []
        assert client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).status_code == 403
        assert client.get(BASE + "/carton-mark/templates", params={"factory_id": "huaxing"}).status_code == 403

        with SessionLocal() as db:
            db.delete(db.get(AuthUserRole, "supplier-now-internal"))
            db.commit()
        assert [item["factory_id"] for item in client.get(BASE + "/memberships").json()] == ["huaxing"]


def test_attachment_formats_version_scope_and_download(monkeypatch):
    with make_client(monkeypatch) as client:
        raw=setup_portal(client)
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);buffer=BytesIO();writer.write(buffer);content=buffer.getvalue()
        url=BASE+f"/internal/orders/{raw['id']}/attachments"
        assert client.post(url,data={"factory_id":"huaxing"},files={"file":("drawing.pdf",content)}).status_code == 403
        login_as(client,"admin")
        for filename,data in (("evil.html",b"<html>"),("fake.pdf",b"not pdf"),("../x.pdf",content),("fake.docx",b"not office"),("huge.pdf",b"x"*(10*1024*1024+1))):
            response=client.post(url,data={"factory_id":"huaxing"},files={"file":(filename,data)})
            assert response.status_code == 422,(filename,response.text)
        result=client.post(url,data={"factory_id":"huaxing"},files={"file":("drawing.pdf",content)})
        assert result.status_code == 201,result.text
        attachment=result.json();assert attachment["version"] == 1
        assert client.post(url,data={"factory_id":"huaxing"},files={"file":("drawing.pdf",content)}).json()["id"] == attachment["id"]
        writer.add_blank_page(width=100,height=100);next_buffer=BytesIO();writer.write(next_buffer)
        next_version=client.post(url,data={"factory_id":"huaxing"},files={"file":("drawing.pdf",next_buffer.getvalue())})
        assert next_version.status_code == 201 and next_version.json()["version"] == 2
        assert next_version.json()["sha256"] != attachment["sha256"]
        supplier_login(client)
        download=client.get(BASE+f"/attachments/{attachment['id']}",params={"factory_id":"huaxing"})
        assert download.status_code == 200 and download.content == content
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["x-content-type-options"] == "nosniff"
        assert client.get(BASE+f"/attachments/{attachment['id']}",params={"factory_id":"huadeng"}).status_code in (403,422)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder,CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="attachment-other",factory_id="huaxing",supplier_code="OTHER",supplier_name="其他供应商",status="ACTIVE",created_at="2026-09-21",updated_at="2026-09-21"));db.flush()
            db.get(CartonOrder,raw["id"]).supplier_id="attachment-other";db.commit()
        assert client.get(BASE+f"/attachments/{attachment['id']}",params={"factory_id":"huaxing"}).status_code == 403
        with SessionLocal() as db:
            db.get(CartonOrder,raw["id"]).supplier_id=raw["supplier_id"]
            db.get(CartonOrder,raw["id"]).status="CONFIRMED";db.commit()
        assert client.get(BASE+f"/attachments/{attachment['id']}",params={"factory_id":"huaxing"}).status_code == 403

def test_portal_migration_in_isolated_database(monkeypatch,tmp_path):
    with make_client(monkeypatch):
        from app.db import Base
        from app.services.carton_supplier_portal import TABLES
        from sqlalchemy import create_engine,inspect,text
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        engine=create_engine(f"sqlite:///{tmp_path/'migration.db'}")
        Base.metadata.create_all(engine,tables=[table for name,table in Base.metadata.tables.items() if name not in TABLES])
        path=Path(__file__).parents[1]/"alembic/versions/20260921_0118_carton_supplier_portal.py"
        spec=importlib.util.spec_from_file_location("portal_migration",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert module.down_revision == "20260917_0117"
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE evidence_test (id INTEGER PRIMARY KEY, value TEXT)"));conn.execute(text("INSERT INTO evidence_test VALUES (1,'preserve')"))
            with Operations.context(MigrationContext.configure(conn)):module.upgrade()
            assert set(TABLES).issubset(inspect(conn).get_table_names())
            assert conn.execute(text("SELECT value FROM evidence_test")).scalar() == "preserve"
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        engine.dispose()
