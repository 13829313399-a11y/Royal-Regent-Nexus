"""Synthetic API coverage for typed special sources and the ordinary stock bridge."""
from io import BytesIO
from uuid import uuid4
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login

BASE = "/api/carton-special-requests"
SUP = "/api/carton-supplier/special-requests"
FACTORY = "huaxing"


@pytest.fixture(autouse=True)
def isolated_database_directory(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def command(row=None, **extra):
    return {"factory_id": FACTORY, "request_id": uuid4().hex, "expected_revision": row["revision"] if row else 0, **extra}


def create_body(kind="SAMPLE"):
    return command(kind=kind, title="测试样板纸箱", requester_name="需求员工", purpose="确认装箱与箱唛", required_date="2026-10-20",
        lines=[{"packaging_type": "外箱", "paper_quality": "A33+B", "specification": "20*10*8", "dimension_unit": "cm", "quantity": "100", "unit": "个", "mark_mode": "NONE"}])


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def setup(client):
    setup_portal(client)
    login_as(client, "admin")
    place = ok(client.post("/api/carton-procurement/inventory/locations", json={"factory_id": FACTORY, "warehouse": "测试仓", "bin_code": "SP"}), 201)
    return place


def accept(client, row):
    supplier_login(client)
    ok(client.post("/api/carton-supplier/changes/respond", json={"factory_id": row["factory_id"],
        "source_kind": "SPECIAL", "source_id": row["current_version_id"], "expected_revision": row["revision"],
        "action": "ACCEPT", "promised_date": row["required_date"], "request_id": uuid4().hex}))
    return ok(client.get(SUP + f"/{row['id']}", params={"factory_id": row["factory_id"]}))


def created(client, *, accept_order=True):
    login_as(client, "admin")
    row = ok(client.post(BASE, json=create_body()), 201)
    row = ok(client.post(BASE + f"/{row['id']}/send", json=command(row)))
    if accept_order:
        accept(client, row)
        login_as(client, "admin")
        row = ok(client.get(BASE + f"/{row['id']}", params={"factory_id": row["factory_id"]}))
    return row


def quote(client, row, kind="CHARGEABLE", price="2"):
    supplier_login(client)
    return ok(client.post(SUP + f"/{row['id']}/quote", json=command(row, version_id=row["current_version_id"],
        pricing_kind=kind, promised_date="2026-10-20", lines=[{"line_id": line["id"], "unit_price": "0" if kind == "FREE" else price} for line in row["lines"]])))


def approve(client, row):
    login_as(client, "admin")
    return ok(client.post(BASE + f"/{row['id']}/approve", json=command(row, quote_version_id=row["quote_version_id"])))


def ship(client, row, quantity="100", price=None):
    supplier_login(client)
    if row.get("supplier_confirmation", {}).get("status") not in {"ACCEPTED", "SUPPLIER_ORIGIN"}:
        row = accept(client, row)
    return ok(client.post(SUP + f"/{row['id']}/ship", json=command(row, version_id=row["current_version_id"],
        delivery_note_no="DN-SP-" + uuid4().hex[:12], delivery_date="2026-10-18",
        lines=[{"line_id": row["lines"][0]["id"], "quantity": quantity, "unit_price": price if price is not None else "0" if row["pricing_kind"] == "FREE" else "2", "free_confirmed": True}])))


def receive_body(row, place, quantity="61", rejected="0"):
    effective = Decimal(quantity) - Decimal(rejected)
    return command(row, acceptance_date="2026-10-18", lines=[{"shipment_line_id": row["shipments"][0]["lines"][0]["id"],
        "received_quantity": quantity, "rejected_quantity": rejected,
        "location_allocations": [{"location_id": place["id"], "quantity": str(effective)}] if effective else []}])


def receive(client, row, place, quantity="61", rejected="0"):
    login_as(client, "admin")
    payload = receive_body(row, place, quantity, rejected)
    return ok(client.post(BASE + f"/{row['id']}/shipments/{row['shipments'][0]['id']}/receive", json=payload)), payload


def test_chargeable_split_acceptance_replay_reversal_and_one_payable_source(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = created(client)
        assert row["status"] == "SENT"
        supplier_login(client)
        current = ok(client.get(SUP + f"/{row['id']}", params={"factory_id": FACTORY}))
        assert current["permissions"]["can_ship"]
        row = ship(client, row)
        assert Decimal(row["lines"][0]["remaining_to_ship"]) == 0
        row, first_payload = receive(client, row, place)
        path = BASE + f"/{row['id']}/shipments/{row['shipments'][0]['id']}/receive"
        from app.services.carton_special_requests import replay_id
        from app.schemas.carton_special_requests import Receive
        from app.services.auth import build_auth_context
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonAuditEvent
        from app.db import SessionLocal
        with SessionLocal() as db:
            replay_key = replay_id(build_auth_context(db, db.get(AuthUser, "user-admin")), Receive.model_validate(first_payload))
            from sqlalchemy import select
            assert db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == replay_key)) is not None
        assert ok(client.post(path, json=first_payload)) == row
        assert client.post(path, json={**first_payload, "acceptance_date": "2026-10-17"}).status_code == 409
        row, _ = receive(client, row, place, "39")
        assert row["status"] == "COMPLETED"
        assert len(row["shipments"][0]["receipts"]) == 2
        from app.db import SessionLocal
        from app.services.carton_supplier_settlement import sources
        from app.models.carton_special_requests import SpecialRequest
        with SessionLocal() as db:
            domain = db.get(SpecialRequest, row["id"])
            rows = sources(db, FACTORY, domain.supplier_id, "2026-10", "CNY")[0]
            assert sorted(Decimal(item["amount"]) for item in rows) == [Decimal("78"), Decimal("122")]
            assert len({item["source_key"] for item in rows}) == 2
            note = row["shipments"][0]["delivery_note_no"]
            assert {item["document_no"] for item in rows} == {note}
            assert all(item["special_request_kind"] == "SAMPLE" and item["supplier_delivery"]["original_quantity"] == "100.0000" for item in rows)
            from app.services.carton_settlement_collaboration import build
            projected = build(db, FACTORY, domain.supplier_id, "2026-10", "CNY", rows, "test")
            assert sorted(Decimal(item["amount"]) for item in projected["lines"]) == [Decimal("78"), Decimal("122")]
        receipt = row["shipments"][0]["receipts"][0]
        reversed_response = client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse", json={"factory_id": FACTORY,
            "expected_revision": receipt["revision"], "reason": "测试冲销更正"})
        assert reversed_response.status_code == 200, reversed_response.text
        current = ok(client.get(BASE + f"/{row['id']}", params={"factory_id": FACTORY}))
        assert current["status"] == "PARTIALLY_RECEIVED"
        assert Decimal(current["shipments"][0]["lines"][0]["remaining_quantity"]) > 0
        assert ok(client.post(path, json=first_payload))["revision"] < current["revision"]


def test_optional_title_and_purpose_and_delivery_price_validation(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        body = create_body()
        del body["title"]; del body["purpose"]
        row = ok(client.post(BASE, json=body), 201)
        assert row["title"] == "" and row["purpose"] == ""
        row = ok(client.post(BASE + f"/{row['id']}/send", json=command(row)))
        row = accept(client, row)
        supplier_login(client)
        payload = command(row, version_id=row["current_version_id"], delivery_note_no="SP-PRICE-VALIDATION",
            delivery_date="2026-10-18", lines=[{"line_id": row["lines"][0]["id"], "quantity": "10"}])
        assert client.post(SUP + f"/{row['id']}/ship", json=payload).status_code == 422
        for price in ("-1", "0.1234567"):
            invalid = {**payload, "lines": [{**payload["lines"][0], "unit_price": price}]}
            assert client.post(SUP + f"/{row['id']}/ship", json=invalid).status_code == 422
        payload["lines"][0]["unit_price"] = "0"
        assert client.post(SUP + f"/{row['id']}/ship", json=payload).status_code == 422
        payload["lines"][0]["free_confirmed"] = True
        result = ok(client.post(SUP + f"/{row['id']}/ship", json=payload))
        assert result["kind"] == "SAMPLE"
        assert result["shipments"][0]["lines"][0]["snapshot"]["pricing_kind"] == "FREE"
        assert ok(client.post(SUP + f"/{row['id']}/ship", json=payload)) == result


def test_each_delivery_freezes_its_own_price_without_quotation(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = ship(client, created(client), quantity="40", price="1.5")
        row = ship(client, row, quantity="60", price="2.25")
        assert [Decimal(item["lines"][0]["snapshot"]["unit_price"]) for item in row["shipments"]] == [Decimal("1.5"), Decimal("2.25")]
        row, _ = receive(client, row, place, quantity="40")
        login_as(client, "admin")
        second = row["shipments"][1]
        body = receive_body(dict(row, shipments=[second]), place, quantity="60")
        row = ok(client.post(BASE + f"/{row['id']}/shipments/{second['id']}/receive", json=body))
        assert row["status"] == "COMPLETED"
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialRequest
        from app.services.carton_supplier_settlement import sources
        with SessionLocal() as db:
            domain = db.get(SpecialRequest, row["id"])
            payable = sources(db, FACTORY, domain.supplier_id, "2026-10", "CNY")[0]
            assert sorted(Decimal(item["amount"]) for item in payable) == [Decimal("60"), Decimal("135")]


def test_supplier_gift_rejects_a_charge_at_delivery(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client); supplier_login(client)
        row = ok(client.post(SUP + "/gifts", json=create_body("SUPPLIER_GIFT")), 201)
        payload = command(row, version_id=row["current_version_id"], delivery_note_no="SP-GIFT-PRICE", delivery_date="2026-10-18",
            lines=[{"line_id": row["lines"][0]["id"], "quantity": "1", "unit_price": "1"}])
        response = client.post(SUP + f"/{row['id']}/ship", json=payload)
        assert response.status_code == 422 and "必须免费" in response.text


def test_partial_multiline_delivery_does_not_make_unpriced_lines_free(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        from test_carton_supplier_portal import revoke_supplier_permission
        body = create_body()
        body["lines"].append({**body["lines"][0], "packaging_type": "平卡"})
        row = ok(client.post(BASE, json=body), 201)
        row = ok(client.post(BASE + f"/{row['id']}/send", json=command(row)))
        row = accept(client, row)
        revoke_supplier_permission("carton_supplier:approve")
        from app.db import SessionLocal
        from app.models.auth import SystemNotification
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            notices = list(db.scalars(select(SystemNotification).where(SystemNotification.target_user_id == "supplier-test", SystemNotification.type == "carton_special_request")))
            assert any(json.loads(notice.payload_json)["required_permission"] == "carton_supplier:read" for notice in notices)
        row = ship(client, row, quantity="10", price="2")
        assert row["pricing_kind"] == "CHARGEABLE" and not row["quote_version_id"]
        payload = command(row, version_id=row["current_version_id"], delivery_note_no="SP-UNPRICED-LINE", delivery_date="2026-10-18",
            lines=[{"line_id": row["lines"][1]["id"], "quantity": "1"}])
        response = client.post(SUP + f"/{row['id']}/ship", json=payload)
        assert response.status_code == 422 and "填写本次送货单价" in response.text


def test_free_gift_no_customer_zero_payable_and_rejecting_all_posts_no_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        supplier_login(client)
        row = ok(client.post(SUP + "/gifts", json=create_body("SUPPLIER_GIFT")), 201)
        assert row["pricing_kind"] == "FREE" and row["customer_code"] == ""
        row = ship(client, row, "10")
        row, _ = receive(client, row, place, "10", "10")
        assert Decimal(row["lines"][0]["received_quantity"]) == 0
        assert Decimal(row["shipments"][0]["lines"][0]["gross_received_quantity"]) == 10
        assert Decimal(row["lines"][0]["remaining_to_ship"]) == 100
        row = ship(client, row, "100")
        # Receive the new shipment; helper uses first shipment, so explicitly select it.
        login_as(client, "admin")
        selected = dict(row, shipments=[row["shipments"][-1]])
        body = receive_body(selected, place, "100")
        row = ok(client.post(BASE + f"/{row['id']}/shipments/{selected['shipments'][0]['id']}/receive", json=body))
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialRequest
        from app.services.carton_supplier_settlement import sources
        with SessionLocal() as db:
            domain = db.get(SpecialRequest, row["id"])
            values = sources(db, FACTORY, domain.supplier_id, "2026-10", "CNY")[0]
            assert len(values) == 1 and Decimal(values[0]["amount"]) == 0 and not values[0]["issues"]


def test_material_change_keeps_old_delivery_price_and_allows_original_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = ship(client, created(client), price="2")
        procurement_state = (row['status'], row['revision'], row['current_version_id'], row['quote_version_id'], row['promised_date'])
        login_as(client, "admin")
        from pypdf import PdfWriter
        output = BytesIO(); writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.write(output)
        row = ok(client.post(BASE + f"/{row['id']}/attachments", data={**command(row), "role": "CONFIRMED"},
            files={"file": ("mark.pdf", output.getvalue(), "application/pdf")}), 201)
        assert (row['status'], row['revision'], row['current_version_id'], row['quote_version_id'], row['promised_date']) == procurement_state
        assert row['attachments'][-1]['role'] == 'DRAFT'
        row, _ = receive(client, row, place)
        receipt_line = row["shipments"][0]["receipts"][0]["lines"][0]
        assert Decimal(receipt_line["unit_price"]) == 2
        assert Decimal(row["shipments"][0]["lines"][0]["snapshot"]["unit_price"]) == 2


def test_public_ad_hoc_and_forged_special_source_cannot_create_payable(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        payload = {"factory_id": FACTORY, "delivery_note_no": "UNKNOWN", "delivery_date": "2026-10-18", "acceptance_date": "2026-10-18",
            "lines": [{"source_type": "AD_HOC", "special_source_line_id": "forged", "packaging_type": "外箱", "paper_quality": "A33+B",
            "specification": "10*10*10", "delivered_quantity": "1", "received_quantity": "1", "unit_price": "1"}]}
        response = client.post("/api/carton-procurement/receipts", json=payload)
        assert response.status_code == 422 and "原需求" in response.text


def test_submit_permission_is_scoped_to_own_requests_and_notifications_recheck_access(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        from test_molding_sample_api import ensure_test_user
        from test_carton_supplier_portal import grant_supplier_permissions, revoke_supplier_permission
        ensure_test_user("engineer"); ensure_test_user("engineer_peer")
        grant_supplier_permissions("user-engineer", permissions=("carton_procurement:special_request_submit",))
        grant_supplier_permissions("user-engineer-peer", permissions=("carton_procurement:special_request_submit",))
        login_as(client, "engineer")
        row = ok(client.post(BASE, json=create_body()), 201)
        assert row["permissions"]["can_edit"] and not row["permissions"]["can_send"]
        assert client.post(BASE+f"/{row['id']}/send", json=command(row)).status_code == 403
        assert ok(client.get(BASE, params={"factory_id": FACTORY}))["total"] == 1
        login_as(client, "engineer_peer")
        assert ok(client.get(BASE, params={"factory_id": FACTORY}))["total"] == 0
        assert client.get(BASE+f"/{row['id']}", params={"factory_id": FACTORY}).status_code == 403
        assert client.get(BASE+f"/{row['id']}", params={"factory_id": "huakang-a"}).status_code in {403, 404}
        login_as(client, "admin")
        row = ok(client.post(BASE+f"/{row['id']}/send", json=command(row)))
        supplier_login(client)
        from app.db import SessionLocal
        from app.models.auth import SystemNotification, AuthUser
        from app.services.auth import build_auth_context
        from app.services.system import can_access_notification
        from sqlalchemy import select
        with SessionLocal() as db:
            notice = db.scalar(select(SystemNotification).where(SystemNotification.type == "carton_special_request", SystemNotification.target_user_id == "supplier-test"))
            assert notice and can_access_notification(db, build_auth_context(db, db.get(AuthUser, "supplier-test")), notice)
        revoke_supplier_permission()
        with SessionLocal() as db:
            notice = db.get(SystemNotification, notice.id)
            assert not can_access_notification(db, build_auth_context(db, db.get(AuthUser, "supplier-test")), notice)


def test_reversal_cannot_overreceive_after_replacement_and_history_units_stay_stable(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = quote(client, created(client), kind="FREE")
        row = ship(client, row, "100")
        row, _ = receive(client, row, place, "100", "20")
        # No in-transit quantity remains; reference identity must be retained on edit.
        change = create_body()
        change.update(command(row)); change["lines"] = [{key: value for key, value in row["lines"][0].items()
            if key in {"id", "item_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "quantity", "unit"}}]
        change["lines"][0]["unit"] = "箱"
        change["reason"] = "核对历史计数单位"
        assert client.post(BASE+f"/{row['id']}/adjust", json=change).status_code == 422
        row = ship(client, row, "20")
        login_as(client, "admin")
        receipt = row["shipments"][0]["receipts"][0]
        ok(client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse", json={"factory_id":FACTORY, "expected_revision":receipt["revision"], "reason":"测试补送后原单冲销"}))
        row = ok(client.get(BASE+f"/{row['id']}", params={"factory_id":FACTORY}))
        row, _ = receive(client, row, place, "100")
        selected = dict(row, shipments=[row["shipments"][-1]])
        response = client.post(BASE+f"/{row['id']}/shipments/{selected['shipments'][0]['id']}/receive", json=receive_body(selected, place, "20"))
        assert response.status_code == 409 and "需求" in response.text


def test_gift_cannot_be_repriced_and_same_second_files_stay_independent_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client); supplier_login(client)
        row = ok(client.post(SUP + "/gifts", json=create_body("SUPPLIER_GIFT")), 201)
        procurement_state = (row['revision'], row['current_version_id'], row['quote_version_id'])
        pricing_state = (row['promised_date'], [(x['id'], x['unit_price']) for x in row['lines']])
        login_as(client, "admin")
        from pypdf import PdfWriter
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, "now_text", lambda: "2026-10-19T10:00:00+08:00")
        for width in (100, 200):
            writer = PdfWriter(); writer.add_blank_page(width=width, height=100); output=BytesIO(); writer.write(output)
            row = ok(client.post(BASE+f"/{row['id']}/attachments", data={**command(row), "role":"CONFIRMED"},
                files={"file":("same.pdf",output.getvalue(),"application/pdf")}),201)
        assert not row['history'][-1]['snapshot']['material_manifest']
        assert (row['revision'], row['current_version_id'], row['quote_version_id']) == procurement_state
        assert len({x['id'] for x in row['attachments']}) == 2
        assert len({x['sha256'] for x in row['attachments']}) == 2
        assert len({x['version'] for x in row['attachments']}) == 2
        assert all(x['role'] == 'DRAFT' for x in row['attachments'])
        supplier_login(client)
        response = client.post(SUP+f"/{row['id']}/quote", json=command(row, version_id=row["current_version_id"],
            pricing_kind="CHARGEABLE", promised_date="2026-10-20", lines=[{"line_id":row["lines"][0]["id"],"unit_price":"1"}]))
        # Uploading evidence retains READY/FREE, so quotation stays unavailable.
        assert response.status_code == 409 and "需求当前阶段不允许此操作" in response.text
        unchanged = ok(client.get(SUP+f"/{row['id']}", params={"factory_id": FACTORY}))
        assert unchanged['status'] == 'READY' and unchanged['pricing_kind'] == 'FREE'
        assert (unchanged['revision'], unchanged['current_version_id'], unchanged['quote_version_id']) == procurement_state
        assert (unchanged['promised_date'], [(x['id'], x['unit_price']) for x in unchanged['lines']]) == pricing_state
        assert len({x['version'] for x in unchanged['attachments']}) == 2
        from app.db import SessionLocal
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        with SessionLocal() as db:
            with pytest.raises(IntegrityError):
                db.execute(text("UPDATE carton_special_versions SET actor_name='changed' WHERE id=:id"), {"id":row["history"][0]["id"]})
            db.rollback()


def test_concurrent_identical_receiving_replays_one_stock_and_price_source(monkeypatch):
    with make_client(monkeypatch) as client:
        place=setup(client)
        row=ship(client, quote(client, created(client), kind="FREE"))
        login_as(client,"admin")
        body=receive_body(row,place,"100")
        path=BASE+f"/{row['id']}/shipments/{row['shipments'][0]['id']}/receive"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:client.post(path,json=body),range(2)))
        assert [response.status_code for response in results] == [200,200], [response.text for response in results]
        assert results[0].json()==results[1].json()
        assert len(results[0].json()["shipments"][0]["receipts"]) == 1


def test_legacy_manual_reentry_preserves_root_quantity_and_single_successor(monkeypatch):
    with make_client(monkeypatch) as client:
        place=setup(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonReceiptLine, CartonCustomer
        from app.services.carton_supplier_portal import fixed_supplier
        from sqlalchemy import select
        with SessionLocal() as db:
            vendor=fixed_supplier(db,FACTORY)
            customer=db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id==FACTORY))
            doc=CartonReceipt(id="historical-manual",factory_id=FACTORY,receipt_no="OLD-RC",delivery_note_no="OLD-DN",delivery_date="2026-10-17",
                acceptance_date="2026-10-17",supplier_id=vendor.id,supplier_name_snapshot=vendor.supplier_name,status="REVERSED",note="historical source",
                revision=3,created_by="user-admin",created_by_name="admin",confirmed_by="user-admin",confirmed_by_name="admin",
                created_at="2026-10-17T10:00:00+08:00",updated_at="2026-10-18T10:00:00+08:00",confirmed_at="2026-10-17T10:00:00+08:00")
            db.add(doc);db.flush()
            db.add(CartonReceiptLine(id="historical-manual-line",factory_id=FACTORY,receipt_id=doc.id,line_no=1,order_line_id=None,source_type="AD_HOC",
                customer_code=customer.customer_code,customer_name=customer.customer_name,contract_no="OLD-SAMPLE",item_no="OLD-ITEM",packaging_type="外箱",
                paper_quality="A33+B",specification="10*10*10",delivered_quantity=Decimal(10),received_quantity=Decimal(10),effective_quantity=Decimal(10),
                damaged_quantity=Decimal(0),rejected_quantity=Decimal(0),unusable_quantity=Decimal(0),unit="个",unit_price=Decimal(1),currency="CNY",location="",feedback_note=""))
            db.commit()
            supplier_id=vendor.id; customer_code=customer.customer_code
        original={"factory_id":FACTORY,"request_id":uuid4().hex,"post_immediately":True,"legacy_correction_receipt_id":"historical-manual",
            "delivery_note_no":"OLD-DN","delivery_date":"2026-10-17","acceptance_date":"2026-10-17","supplier_id":supplier_id,
            "lines":[{"source_type":"AD_HOC","customer_code":customer_code,"contract_no":"OLD-SAMPLE","item_no":"OLD-ITEM", "packaging_type":"外箱",
                "paper_quality":"A33+B","specification":"10*10*10","dimension_unit":"cm","unit":"个","unit_price":"1", "delivered_quantity":"10",
                "received_quantity":"10","location_allocations":[{"location_id":place["id"],"quantity":"10"}]}]}
        forbidden={**original,"request_id":uuid4().hex,"lines":[{**original["lines"][0],"delivered_quantity":"1000000"}]}
        assert client.post("/api/carton-procurement/receipts",json=forbidden).status_code==422
        first=ok(client.post("/api/carton-procurement/receipts",json=original),201)
        assert ok(client.post("/api/carton-procurement/receipts",json=original),201)["id"]==first["id"]
        ok(client.post(f"/api/carton-procurement/receipts/{first['id']}/reverse",json={"factory_id":FACTORY,"expected_revision":first["revision"],"reason":"测试旧单更正链"}))
        assert client.post("/api/carton-procurement/receipts",json={**original,"request_id":uuid4().hex}).status_code==409
        second=ok(client.post("/api/carton-procurement/receipts",json={**original,"request_id":uuid4().hex,"legacy_correction_receipt_id":first["id"]}),201)
        assert second["id"]!=first["id"]
        assert client.post("/api/carton-procurement/receipts",json={**original,"request_id":uuid4().hex,"legacy_correction_receipt_id":first["id"]}).status_code==409


def test_gift_only_factory_supplier_month_end_and_confirmed_period_guards(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        factory="huakang-b"
        login_as(client,"admin")
        place=ok(client.post("/api/carton-procurement/inventory/locations",json={"factory_id":factory,"warehouse":"赠送测试仓","bin_code":"GIFT"}),201)
        supplier_login(client)
        body=create_body("SUPPLIER_GIFT");body["factory_id"]=factory
        row=ok(client.post(SUP+"/gifts",json=body),201)
        assert factory in {item["factory_id"] for item in ok(client.get("/api/carton-supplier/memberships"))}
        row=ok(client.post(SUP+f"/{row['id']}/ship",json={**command(row),"factory_id":factory,"version_id":row["current_version_id"],
            "delivery_note_no":"GIFT-ONLY-FACTORY","delivery_date":"2026-10-18","lines":[{"line_id":row["lines"][0]["id"],"quantity":"10"}]}))
        login_as(client,"admin")
        acceptance=receive_body(row,place,"10");acceptance["factory_id"]=factory
        row=ok(client.post(BASE+f"/{row['id']}/shipments/{row['shipments'][0]['id']}/receive",json=acceptance))
        work=ok(client.get("/api/carton-procurement/supplier-settlements/workspace",params={"factory_id":factory,"period":"2026-10"}))
        collaboration=work["collaboration"]
        assert len(collaboration["sources"])==1 and Decimal(collaboration["lines"][0]["amount"])==0
        saved=ok(client.post("/api/carton-procurement/supplier-settlements",json={"origin":"COLLABORATION","factory_id":factory,
            "supplier_id":work["supplier_id"],"period":"2026-10","currency":"CNY","source_fingerprint":collaboration["source_fingerprint"],
            "statement_no":"GIFT-MONTH-001","same_price_basis":True,"tax_basis":"INCLUSIVE","lines":collaboration["lines"]}))
        from datetime import datetime
        from app.services import carton_procurement as core
        monkeypatch.setattr(core,"business_now",lambda:datetime(2026,11,5,12,0,0))
        supplier_login(client)
        supplier_view=ok(client.get("/api/carton-supplier/settlements/workspace",params={"factory_id":factory,"period":"2026-10"}))
        assert supplier_view["documents"][0]["id"]==saved["id"]
        reviewed=ok(client.post(f"/api/carton-supplier/settlements/{saved['id']}/review",json={"factory_id":factory,
            "expected_revision":saved["revision"],"decision":"CONFIRMED"}))
        login_as(client,"admin")
        closed=ok(client.post(f"/api/carton-procurement/supplier-settlements/{saved['id']}/confirm",json={"factory_id":factory,"expected_revision":reviewed["revision"]}))
        assert closed["status"]=="CONFIRMED" and Decimal(closed["result"]["net_amount"])==0
        receipt=row["shipments"][0]["receipts"][0]
        assert client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse",json={"factory_id":factory,
            "expected_revision":receipt["revision"],"reason":"已月结应阻止冲销"}).status_code==409
