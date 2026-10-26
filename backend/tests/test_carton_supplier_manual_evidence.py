"""Original-note supplementation changes payables once, never stock or history."""
import json
from io import BytesIO
from decimal import Decimal

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import setup, create_body, command, ok, BASE, isolated_database_directory
from test_carton_supplier_portal import supplier_login, setup_portal, accept_all, _dongkang_delivery_file
from test_carton_supplier_receipt_link import manual_receipt, late_note, link_body, evidence


def workbook_for(group, price=3, quantity_change=0):
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["送货单号", "日期", "客户", "客户单号", "客户料号", "纸品类型", "纸质", "规格", "数量", "单价"])
    for index, line in enumerate(group["lines"]):
        sheet.append([group["delivery_note_no"], group["delivery_date"], "华兴", line.get("contract_no", ""),
            line.get("item_no", ""), line["packaging_type"], line["paper_quality"], line["specification"],
            float(line["quantity"]) + (quantity_change if index == 0 else 0), price])
    output = BytesIO(); workbook.save(output)
    return output.getvalue()


def import_note(client, content, *, confirm=True):
    path = "/api/carton-supplier/shipments/"
    preview = ok(client.post(path + "import-preview", files={"file": ("late.xlsx", content)}))
    group = preview["groups"][0]
    if not confirm: return group
    assert group["receipt_link_ready"], group
    data = {"sha256": preview["sha256"], "selections": json.dumps([dict(factory_id="huaxing",
        delivery_note_no=group["delivery_note_no"], registration_mode="EXISTING_RECEIPT")])}
    return client.post(path + "import-confirm", files={"file": ("late.xlsx", content)}, data=data)


@pytest.mark.parametrize("kind,price", [("SAMPLE", 3), ("WORKSHOP_MISC", 3), ("SAMPLE", 0), ("WORKSHOP_MISC", None)])
def test_special_manual_original_auto_price_without_second_receipt(monkeypatch, kind, price):
    with make_client(monkeypatch) as client:
        place = setup(client)
        body = create_body(kind)
        row = ok(client.post(BASE, json=body), 201)
        row = ok(client.post(BASE + f"/{row['id']}/confirm", json=command(row)))
        response = client.post("/api/carton-unified-deliveries/warehouse-receive", json=command(
            delivery_note_no="LATE-SPECIAL", delivery_date="2026-10-18", acceptance_date="2026-10-18",
            order_revisions={}, formal_lines=[], special_requests=[dict(id=row['id'], expected_revision=row['revision'],
                lines=[dict(line_id=row['lines'][0]['id'], received_quantity='10', unit_price='2',
                    location_allocations=[{'location_id': place['id'], 'quantity': '10'}])])]))
        received = ok(response)
        group = ok(client.get('/api/carton-unified-deliveries/' + received['delivery_id'], params={'factory_id': 'huaxing'}))
        before = evidence()
        supplier_login(client)
        mismatch = import_note(client, workbook_for(group, quantity_change=1), confirm=False)
        assert not mismatch['receipt_link_ready'] and not mismatch['ready']
        from app.db import SessionLocal
        from app.models.carton_supplier_settlement import CartonSupplierSettlement
        from app.models.carton_procurement import CartonReceipt
        with SessionLocal() as db:
            receipt = db.get(CartonReceipt, received['receipts'][0]['id'])
            db.add(CartonSupplierSettlement(id='TEST-LOCK', factory_id='huaxing', supplier_id=receipt.supplier_id,
                period='2026-10', currency='CNY', version=1, revision=1, status='CONFIRMED', source_fingerprint='0'*64,
                created_at='2026-11-01', updated_at='2026-11-01', created_by='user-admin'))
            db.commit()
        content = workbook_for(group, price=price)
        assert not import_note(client, content, confirm=False)['receipt_link_ready']
        with SessionLocal() as db:
            db.get(CartonSupplierSettlement, 'TEST-LOCK').status = 'DRAFT'; db.commit()
        assert import_note(client, content).status_code == 200
        assert import_note(client, content).status_code == 200
        assert import_note(client, workbook_for(group, price=4)).status_code == 409
        after = evidence()
        assert after[:2] == before[:2]
        from app.db import SessionLocal
        from app.models.carton_price_review import CartonPriceReview
        from app.models.auth import SystemNotification
        from app.services.carton_supplier_manual_evidence import EVENT
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            review = db.scalar(select(CartonPriceReview))
            if not price:
                assert review.status != 'CONFIRMED'
                assert not list(db.scalars(select(SystemNotification).where(SystemNotification.type == 'carton_supplier_price_adopted')))
                return
            assert review.status == 'CONFIRMED' and review.proposed_unit_price == Decimal(3)
            assert len(list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == EVENT)))) == 1
            notices = list(db.scalars(select(SystemNotification).where(SystemNotification.type == 'carton_supplier_price_adopted')))
            assert len(notices) == 1 and '2' in notices[0].message and '3' in notices[0].message
            from app.models.auth import AuthUser
            from app.services.auth import build_auth_context
            from app.services.system import can_access_notification
            assert can_access_notification(db, build_auth_context(db, db.get(AuthUser, 'user-admin')), notices[0])
            assert not can_access_notification(db, build_auth_context(db, db.get(AuthUser, 'supplier-test')), notices[0])
            with monkeypatch.context() as scoped:
                from app.services import carton_price_review
                from fastapi import HTTPException
                def denied(*args, **kwargs): raise HTTPException(403, '已撤销客户权限')
                scoped.setattr(carton_price_review, 'customer_access', denied)
                assert not can_access_notification(db, build_auth_context(db, db.get(AuthUser, 'user-admin')), notices[0])
        login_as(client, 'admin')
        monthly = ok(client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-10'}))
        adopted = [source for source in monthly['sources'] if source.get('supplier_price_update')]
        assert len(adopted) == 1 and Decimal(adopted[0]['amount']) == 30
        assert Decimal(adopted[0]['supplier_price_update']['amount_difference']) == 10
        collaborative = next(source for source in monthly['collaboration']['sources'] if source['source_key'] == adopted[0]['source_key'])
        assert Decimal(collaborative['supplier_delivery']['original_unit_price']) == 3
        assert Decimal(collaborative['supplier_delivery']['price_difference']) == 0
        assert not collaborative['issues']


def test_legacy_link_adopts_supplier_price_and_preserves_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        receipt = manual_receipt(client, order)
        before = evidence()
        shipment, _, _ = late_note(client, order, content=_dongkang_delivery_file(order, source_price=3))
        login_as(client, 'admin')
        result = client.post(f"/api/carton-supplier/internal/shipments/{shipment['id']}/link-receipt", json=link_body(shipment, receipt))
        assert result.status_code == 200, result.text
        after = evidence()
        assert after[:2] == before[:2]
        assert all(Decimal(row['unit_price']) == 3 for row in after[2])
        assert all(row['supplier_price_update'] for row in after[2])


def test_mixed_manual_note_adopts_all_three_types_atomically(monkeypatch):
    import test_carton_warehouse_receiving as mixed
    original = mixed.create_body
    def unique_body(kind='SAMPLE'):
        body = original(kind)
        body['lines'][0]['item_no'] = 'SAMPLE-ITEM' if kind == 'SAMPLE' else 'MISC-ITEM'
        return body
    monkeypatch.setattr(mixed, 'create_body', unique_body)
    with make_client(monkeypatch) as client:
        place = setup(client)
        payload, _, _ = mixed.batch(client, place)
        received = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload))
        group = ok(client.get('/api/carton-unified-deliveries/' + received['delivery_id'], params={'factory_id': 'huaxing'}))
        before = evidence()
        supplier_login(client)
        content = workbook_for(group)
        result = import_note(client, content)
        assert result.status_code == 200, result.text
        assert evidence()[:2] == before[:2]
        from app.db import SessionLocal
        from app.models.carton_price_review import CartonPriceReview
        with SessionLocal() as db:
            reviews = list(db.scalars(select(CartonPriceReview)))
            assert len(reviews) == 3
            assert all(row.status == 'CONFIRMED' and row.proposed_unit_price == 3 for row in reviews)


def test_all_rejected_manual_original_still_protects_acceptance_month(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        row = ok(client.post(BASE, json=create_body()), 201)
        row = ok(client.post(BASE + f"/{row['id']}/confirm", json=command(row)))
        received = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=command(
            delivery_note_no='ALL-REJECTED', delivery_date='2026-09-30', acceptance_date='2026-10-01',
            order_revisions={}, formal_lines=[], special_requests=[dict(id=row['id'], expected_revision=row['revision'],
                lines=[dict(line_id=row['lines'][0]['id'], received_quantity='10', rejected_quantity='10',
                    unit_price='2', location_allocations=[])])])) )
        group = ok(client.get('/api/carton-unified-deliveries/' + received['delivery_id'], params={'factory_id': 'huaxing'}))
        from app.db import SessionLocal
        from app.models.carton_supplier_settlement import CartonSupplierSettlement
        from app.models.carton_procurement import CartonReceipt
        with SessionLocal() as db:
            receipt = db.get(CartonReceipt, received['receipts'][0]['id'])
            db.add(CartonSupplierSettlement(id='CLOSED-ACCEPTANCE', factory_id='huaxing', supplier_id=receipt.supplier_id,
                period='2026-10', currency='CNY', version=1, revision=1, status='CONFIRMED', source_fingerprint='0'*64,
                created_at='2026-11-01', updated_at='2026-11-01', created_by='user-admin'))
            db.commit()
        supplier_login(client)
        preview = import_note(client, workbook_for(group), confirm=False)
        assert not preview['receipt_link_ready'] and any('月份已确认' in issue for issue in preview['issues'])
