"""Supplier originals preserve unknown prices and require complete formal identity."""
import json
import hashlib
from io import BytesIO
from decimal import Decimal
from uuid import uuid4
import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import ok, FACTORY, setup, created
from test_carton_supplier_portal import setup_portal, accept_all, supplier_login, receive_payload, BASE, _dongkang_delivery_file
from test_carton_special_delivery_import import file_for, choices, confirm, IMPORT


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr('test_molding_sample_api.TEST_TMP_DIR', tmp_path)


def complete_material_file(order, *, missing_item=False, price=None, contract=None):
    workbook = load_workbook(BytesIO(_dongkang_delivery_file(order, missing_item=missing_item, source_price=price)))
    sheet = workbook.active
    sheet.cell(1, 10).value = '名称'
    for index, line in enumerate(order['lines'], start=2):
        sheet.cell(index, 10).value = line['packaging_type']
        if contract is not None:
            sheet.cell(index, 4).value = contract
    stream = BytesIO(); workbook.save(stream); workbook.close()
    return {'file': ('送货明细.xlsx', stream.getvalue())}


def test_formal_blank_original_stays_unknown_through_import_receipt_and_feedback(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        upload = complete_material_file(order)
        preview = ok(client.post(BASE + '/shipments/import-preview', files=upload))
        group = preview['groups'][0]
        assert group['ready'], preview
        assert all(row['unit_price'] is None and not row['unit_price_provided'] for row in group['rows'])
        form = {'sha256': preview['sha256'], 'selections': json.dumps([{'factory_id': FACTORY, 'delivery_note_no': group['delivery_note_no']}])}
        shipment = ok(client.post(BASE + '/shipments/import-confirm', files=upload, data=form))['shipments'][0]
        assert ok(client.post(BASE + '/shipments/import-confirm', files=upload, data=form))['shipments'][0]['id'] == shipment['id']
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        with SessionLocal() as db:
            frozen = list(db.scalars(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id == shipment['id'])))
            snapshots = [json.loads(line.snapshot_json) for line in frozen]
            assert snapshots and all('delivery_unit_price' in item and item['delivery_unit_price'] is None for item in snapshots)
        login_as(client, 'warehouse_keeper')
        workspace = ok(client.get(BASE + '/internal/workspace', params={'factory_id': FACTORY}))
        internal = next(item for item in workspace['shipments'] if item['id'] == shipment['id'])
        assert all(line['delivery_unit_price'] is None and not line['free_confirmed'] for line in internal['lines'])
        body = receive_payload(client, shipment)
        for line in body['lines']:
            line.update(unit_price=0, zero_price_kind='PENDING', price_action='PENDING', price_reason='原送货单未填写价格')
        posted = ok(client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=body))
        assert ok(client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=body))['receipt_id'] == posted['receipt_id']
        reviews = ok(client.get('/api/carton-price-reviews/internal', params={'factory_id': FACTORY}))['items']
        for line in shipment['lines']:
            review = next(item for item in reviews if item['shipment_line_id'] == line['id'])
            assert review['status'] == 'PENDING' and review['original_unit_price'] is None and review['effective_unit_price'] is None
        feedback = ok(client.get(BASE + '/internal/workspace', params={'factory_id': FACTORY}))
        visible = next(item for item in feedback['shipments'] if item['id'] == shipment['id'])
        assert all(line['delivery_unit_price'] is None and not line['free_confirmed'] for line in visible['lines'])


def test_missing_formal_item_blocks_preview_and_confirm_without_blocking_complete_unmatched(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        broken = complete_material_file(order, missing_item=True, price=2)
        preview = ok(client.post(BASE + '/shipments/import-preview', files=broken))
        group = preview['groups'][0]; first = group['rows'][0]
        assert not group['ready'] and first['status'] == 'BLOCKED' and '货号' in first['reason']
        form = {'sha256': preview['sha256'], 'selections': json.dumps([{'factory_id': FACTORY, 'delivery_note_no': group['delivery_note_no']}])}
        rejected = client.post(BASE + '/shipments/import-confirm', files=broken, data=form)
        assert rejected.status_code == 409, rejected.text
        assert ok(client.get(BASE + '/workspace', params={'factory_id': FACTORY}))['shipments'] == []
        unknown_broken = complete_material_file(order, missing_item=True, price=2, contract='UNKNOWN-FORMAL')
        unknown_result = ok(client.post(BASE + '/shipments/import-preview', files=unknown_broken))
        assert unknown_result['groups'][0]['rows'][0]['status'] == 'BLOCKED'
        assert '货号' in unknown_result['groups'][0]['rows'][0]['reason']
        workbook = load_workbook(BytesIO(complete_material_file(order, price=2)['file'][1]))
        sheet = workbook.active
        for index in range(2, sheet.max_row + 1):
            sheet.cell(index, 4).value = 'COMPLETE-UNKNOWN'
            sheet.cell(index, 5).value = 'ITEM-UNKNOWN'
        stream = BytesIO(); workbook.save(stream); workbook.close()
        unmatched = {'file': ('完整未匹配.xlsx', stream.getvalue())}
        result = ok(client.post(BASE + '/shipments/import-preview', files=unmatched))
        assert result['groups'][0]['ready']
        assert all(row['status'] == 'AD_HOC_REVIEW' for row in result['groups'][0]['rows'])
        selection = {'sha256': result['sha256'], 'selections': json.dumps([{'factory_id': FACTORY, 'delivery_note_no': result['groups'][0]['delivery_note_no']}])}
        saved = ok(client.post(BASE + '/shipments/import-confirm', files=unmatched, data=selection))['shipments'][0]
        assert all(line['source_type'] == 'AD_HOC_REVIEW' for line in saved['lines'])


def test_formal_zero_is_not_free_without_supplier_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        for free in (False, True):
            payload = {'factory_id': FACTORY, 'request_id': uuid4().hex,
                'delivery_note_no': f'ZERO-{free}', 'delivery_date': '2026-09-24',
                'lines': [{'order_line_id': order['lines'][0]['id'], 'issue_id': order['issue_id'],
                    'quantity': 1, 'unit_price': '0', 'free_confirmed': free}]}
            response = client.post(BASE + '/shipments', json=payload)
            if not free:
                assert response.status_code == 422, response.text
                continue
            shipment = ok(response, 201)
            login_as(client, 'warehouse_keeper')
            workspace = ok(client.get(BASE + '/internal/workspace', params={'factory_id': FACTORY}))
            sent = next(row for row in workspace['shipments'] if row['id'] == shipment['id'])
            line = sent['lines'][0]
            assert Decimal(line['delivery_unit_price']) == 0
            assert line['free_confirmed'] is free
            supplier_login(client)


def test_late_blank_original_does_not_confirm_warehouse_recorded_price(monkeypatch):
    from test_carton_warehouse_receiving import batch
    from test_carton_supplier_manual_evidence import workbook_for, import_note
    with make_client(monkeypatch) as client:
        place = setup(client); payload, _, _ = batch(client, place)
        payload['formal_lines'][0]['unit_price'] = None
        payload['special_requests'] = []
        saved = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload))
        group = ok(client.get('/api/carton-unified-deliveries/' + saved['delivery_id'], params={'factory_id': FACTORY}))
        reviews = ok(client.get('/api/carton-price-reviews/internal', params={'factory_id': FACTORY}))['items']
        before = {row['id']: (row['status'], row['original_unit_price'], row['effective_unit_price']) for row in reviews}
        assert len(before) == 1 and all(value == ('PENDING', None, None) for value in before.values())
        supplier_login(client)
        content = workbook_for(group, price=None)
        preview = import_note(client, content, confirm=False)
        assert preview['receipt_link_ready'], (preview['issues'], [(row.get('status'), row.get('reason')) for row in preview['rows']])
        assert import_note(client, content).status_code == 200
        assert import_note(client, content).status_code == 200
        login_as(client, 'warehouse_keeper')
        reviews = ok(client.get('/api/carton-price-reviews/internal', params={'factory_id': FACTORY}))['items']
        after = {row['id']: (row['status'], row['original_unit_price'], row['effective_unit_price']) for row in reviews}
        assert after == before


def test_excel_zero_without_free_is_preserved_and_received_pending(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        upload = complete_material_file(order, price=0)
        preview = ok(client.post(BASE + '/shipments/import-preview', files=upload))
        group = preview['groups'][0]
        assert group['ready'] and all(row['unit_price_provided'] and Decimal(str(row['unit_price'])) == 0 for row in group['rows'])
        form = {'sha256': preview['sha256'], 'selections': json.dumps([{'factory_id': FACTORY, 'delivery_note_no': group['delivery_note_no']}])}
        shipment = ok(client.post(BASE + '/shipments/import-confirm', files=upload, data=form))['shipments'][0]
        login_as(client, 'warehouse_keeper')
        internal = next(row for row in ok(client.get(BASE + '/internal/workspace', params={'factory_id': FACTORY}))['shipments'] if row['id'] == shipment['id'])
        assert all(Decimal(line['delivery_unit_price']) == 0 and not line['free_confirmed'] for line in internal['lines'])
        body = receive_payload(client, shipment)
        for line in body['lines']:
            line.update(unit_price=0, zero_price_kind='PENDING', price_action='PENDING', price_reason='零价未确认免费')
        ok(client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=body))
        reviews = ok(client.get('/api/carton-price-reviews/internal', params={'factory_id': FACTORY}))['items']
        relevant = [row for row in reviews if row.get('shipment_id') == shipment['id']]
        assert len(relevant) == len(shipment['lines']) and all(row['status'] == 'PENDING' for row in relevant)


def test_mixed_special_formal_and_unmatched_original_keeps_blank_prices(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client); special = created(client); supplier_login(client); formal = accept_all(client)
        unknown = dict(formal, contract_no='UNKNOWN-FORMAL', item_no='UNKNOWN-ITEM')
        upload = file_for([(formal, 'MIX-UNKNOWN', 1, None), (special, 'MIX-UNKNOWN', 1, 2), (unknown, 'MIX-UNKNOWN', 1, None)])
        preview = ok(client.post(IMPORT + 'preview', files=upload))
        group = preview['groups'][0]
        assert group['ready'], preview
        assert [row['unit_price'] for row in group['rows']] == [None, 2, None]
        selected = choices(preview)
        result = ok(confirm(client, upload, preview, selected))['shipments'][0]
        assert len(result['lines']) == 3
        assert [line['delivery_unit_price'] for line in result['lines']].count(None) == 2
        assert ok(confirm(client, upload, preview, selected))['shipments'][0]['id'] == result['id']


@pytest.mark.parametrize('unknown_special_prefix', [False, True])
def test_historical_manual_missing_item_cannot_attach_but_saved_file_replays(monkeypatch, unknown_special_prefix):
    from test_carton_warehouse_receiving import batch
    from test_carton_supplier_manual_evidence import workbook_for, import_note
    with make_client(monkeypatch) as client:
        place = setup(client); payload, _, _ = batch(client, place); payload['special_requests'] = []
        saved = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload))
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        from app.models.carton_procurement import CartonReceiptLine
        with SessionLocal() as db:
            source = db.scalar(select(SupplierShipmentLine))
            snapshot = json.loads(source.snapshot_json); snapshot['item_no'] = ''
            if unknown_special_prefix: snapshot['contract_no'] = 'SP-UNKNOWN-HISTORICAL'
            source.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
            paper = db.scalar(select(CartonReceiptLine)); paper.item_no = ''
            if unknown_special_prefix: paper.contract_no = 'SP-UNKNOWN-HISTORICAL'
            db.commit()
        group = ok(client.get('/api/carton-unified-deliveries/' + saved['delivery_id'], params={'factory_id': FACTORY}))
        assert group['lines'][0]['item_no'] == ''
        content = workbook_for(group, price=2)
        supplier_login(client)
        preview = ok(client.post(BASE + '/shipments/import-preview', files={'file': ('late.xlsx', content)}))
        entry = preview['groups'][0]
        assert not entry['ready'] and not entry['receipt_link_ready']
        assert entry['rows'][0]['status'] == 'BLOCKED' and '货号' in entry['rows'][0]['reason']
        data = {'sha256': preview['sha256'], 'selections': json.dumps([{'factory_id': FACTORY,
            'delivery_note_no': group['delivery_note_no'], 'registration_mode': 'EXISTING_RECEIPT'}])}
        denied = client.post(BASE + '/shipments/import-confirm', files={'file': ('late.xlsx', content)}, data=data)
        assert denied.status_code == 409, denied.text
        # Model a pre-upgrade attachment: a saved identical file remains replayable.
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services.carton_procurement import _audit
        from app.services.carton_supplier_manual_evidence import DOCUMENT_EVENT
        with SessionLocal() as db:
            admin = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == 'admin')))
            _audit(db, admin, FACTORY, DOCUMENT_EVENT, 'carton_unified_delivery', group['id'],
                {'evidence': {'filename': 'late.xlsx', 'sha256': hashlib.sha256(content).hexdigest()}, 'rows': []})
            db.commit()
        replay = client.post(BASE + '/shipments/import-confirm', files={'file': ('late.xlsx', content)}, data=data)
        assert replay.status_code == 200, replay.text
        assert replay.json()['shipments'][0]['id'] == group['id']
        changed = client.post(BASE + '/shipments/import-confirm', files={'file': ('other.xlsx', content)}, data=data)
        assert changed.status_code == 409, changed.text
