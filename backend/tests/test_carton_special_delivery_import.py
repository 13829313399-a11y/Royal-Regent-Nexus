"""Supplier originals retain typed demand, frozen evidence and atomic posting."""
from io import BytesIO
import json
from decimal import Decimal
from uuid import uuid4
import pytest
from openpyxl import Workbook
from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import setup, created, create_body, command, accept, ok, BASE, FACTORY
from test_carton_supplier_portal import supplier_login, accept_all

IMPORT = '/api/carton-supplier/shipments/import-'
UNIFIED = '/api/carton-unified-deliveries'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr('test_molding_sample_api.TEST_TMP_DIR', tmp_path)


def file_for(entries):
    book = Workbook(); sheet = book.active; sheet.title = '送货明细'
    sheet.append(['送货单号', '日期', '客户', '客户单号', '客户料号', '名称', '纸质', '规格', '数量', '单价'])
    for order, note, quantity, price in entries:
        line = order['lines'][0]
        sheet.append([note, '2026-10-18', '华兴', order.get('request_no', order.get('contract_no')),
            order.get('item_no', ''), line['packaging_type'], line['paper_quality'],
            line['specification'], quantity, price])
    stream = BytesIO(); book.save(stream); book.close()
    return {'file': ('供应商原送货明细.xlsx', stream.getvalue())}


def choices(preview, free=False):
    return [dict({key: row[key] for key in ('source_sheet', 'source_row', 'order_line_id', 'issue_id', 'order_revision')},
                 source_kind='SPECIAL', special_request_id=row['special_request_id'], free_confirmed=free)
        for group in preview['groups'] for row in group['rows']
        if row.get('source_kind') == 'SPECIAL' and row['order_line_id']]


def confirm(client, upload, preview, selected=None):
    return client.post(IMPORT+'confirm', files=upload, data=dict(sha256=preview['sha256'],
        selections=json.dumps([dict(factory_id=g['factory_id'], delivery_note_no=g['delivery_note_no']) for g in preview['groups']]),
        row_selections=json.dumps(choices(preview) if selected is None else selected)))


def test_original_mixed_regular_sample_misc_dispatch_receipt_and_retry(monkeypatch):
    # A real formal contract may also start with SP; its exact identity wins
    # over an unknown-special-number heuristic.
    import test_carton_procurement_api as regular_fixture
    original_payload = regular_fixture._order_payload
    monkeypatch.setattr(regular_fixture, '_order_payload',
        lambda: dict(original_payload(), contract_no='SP-FORMAL-2026'))
    with make_client(monkeypatch) as client:
        place = setup(client); sample = created(client)
        login_as(client, 'admin')
        misc = ok(client.post(BASE, json=create_body('WORKSHOP_MISC')), 201)
        misc = ok(client.post(BASE+f"/{misc['id']}/send", json=command(misc)))
        misc = accept(client, misc)
        supplier_login(client); regular = accept_all(client)
        upload = file_for([(regular, 'MIX-ORIGINAL', 2, 2.5), (sample, 'MIX-ORIGINAL', 3, 1.5), (misc, 'MIX-ORIGINAL', 4, 2)])
        preview = ok(client.post(IMPORT+'preview', files=upload))
        assert preview['groups'][0]['ready'], preview
        assert [row.get('order_kind') for row in preview['groups'][0]['rows']] == [None, 'SAMPLE', 'MISC']
        assert confirm(client, upload, preview, []).status_code == 409  # Pin reviewed versions.
        group = ok(confirm(client, upload, preview))['shipments'][0]
        assert len(group['special']) == 2 and len(group['lines']) == 3
        assert group['source_sha256'] == preview['sha256']
        assert group['source_filename'] == '供应商原送货明细.xlsx'
        assert ok(confirm(client, upload, preview))['shipments'][0]['id'] == group['id']
        assert not group['receipts']
        assert sum(Decimal(line['quantity'])*Decimal(line['delivery_unit_price']) for line in group['lines']) == Decimal('17.5')
        for detail in group['special']:
            snapshot = detail['shipments'][0]['lines'][0]['snapshot']
            assert snapshot['source_file']['sha256'] == preview['sha256']
            assert snapshot['original_source_material']['source_sheet'] == '送货明细'
        docs = ok(client.get('/api/carton-supplier/documents', params={'factory_id': FACTORY}))
        doc = next(row for row in docs if row['id'] == group['id'])
        assert {row['order_kind'] for row in doc['lines']} == {'REGULAR', 'SAMPLE', 'MISC'}
        assert doc['source_sha256'] == preview['sha256']
        login_as(client, 'warehouse_keeper')
        pending = ok(client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': FACTORY}))
        assert [row['id'] for row in pending['items']] == [group['id']]
        payload = command(acceptance_date='2026-10-18', formal=dict(expected_revision=group['formal']['revision'],
            lines=[dict(shipment_line_id=line['id'], received_quantity=line['quantity'],
                unit_price=line['delivery_unit_price'],
                location_allocations=[dict(location_id=place['id'], quantity=line['quantity'])]) for line in group['formal']['lines']]),
            special=[dict(request_id=row['id'], shipment_id=row['shipments'][0]['id'], expected_revision=row['revision'],
                lines=[dict(shipment_line_id=line['id'], received_quantity=line['quantity'],
                    location_allocations=[dict(location_id=place['id'], quantity=line['quantity'])]) for line in row['shipments'][0]['lines']])
                for row in group['special']])
        received = ok(client.post(UNIFIED+f"/{group['id']}/receive", json=payload))
        assert received['status'] == 'RECEIVED' and len(received['receipts']) == 3
        assert ok(client.post(UNIFIED+f"/{group['id']}/receive", json=payload)) == received
        assert ok(client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': FACTORY}))['total'] == 0
        supplier_login(client)
        assert ok(confirm(client, upload, preview))['shipments'][0]['status'] == 'RECEIVED'
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement
        from sqlalchemy import select
        with SessionLocal() as db:
            movements = list(db.scalars(select(CartonInventoryMovement).where(
                CartonInventoryMovement.source_id.in_([row.get('receipt_id') or row['id'] for row in received['receipts']]))))
            assert sum(row.quantity for row in movements) == 9


def test_special_original_free_missing_price_identity_and_stale_version(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client); order = created(client); supplier_login(client)
        for price, reason in [(None, '缺少单价'), (-1, '负数'), (0, '免费'), (0.1234567, '最多6位小数'), (1e13, '超出范围')]:
            preview = ok(client.post(IMPORT+'preview', files=file_for([(order, 'PRICE', 1, price)])))
            row = preview['groups'][0]['rows'][0]
            assert row['status'] == 'BLOCKED' and reason in row['reason']
        upload = file_for([(order, 'FREE', 1, 0)])
        preview = ok(client.post(IMPORT+'preview', files=upload)); selected = choices(preview, True)
        ready = ok(client.post(IMPORT+'preview', files=upload, data={'row_selections': json.dumps(selected)}))
        assert ready['groups'][0]['ready']
        group = ok(confirm(client, upload, ready, selected))['shipments'][0]
        assert group['lines'][0]['free_confirmed'] and Decimal(group['lines'][0]['delivery_unit_price']) == 0
        assert confirm(client, upload, ready, choices(preview, False)).status_code == 409
        # A stale reviewed revision cannot be silently rematched to the new state.
        paid = file_for([(order, 'STALE', 1, 2)])
        current = ok(client.post(IMPORT+'preview', files=paid)); selected = choices(current)
        selected[0]['order_revision'] -= 1
        assert confirm(client, paid, current, selected).status_code == 409
        unknown = {**order, 'request_no': 'SP-UNKNOWN'}
        for wrong in [unknown, {**order, 'lines': [{**order['lines'][0], 'specification': '99*88*77'}]}]:
            preview = ok(client.post(IMPORT+'preview', files=file_for([(wrong, 'BAD', 1, 2)])))
            assert preview['groups'][0]['rows'][0]['status'] == 'BLOCKED'
        too_many = ok(client.post(IMPORT+'preview', files=file_for([(order, 'OVER', 100, 2)])))
        assert '剩余未送' in too_many['groups'][0]['rows'][0]['reason']
        assert not too_many['groups'][0]['ready']


def test_special_original_batch_rolls_back_and_pending_order_never_becomes_unmatched(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client); good = created(client); pending = created(client, accept_order=False); supplier_login(client)
        upload = file_for([(good, 'A-GOOD', 1, 2), (pending, 'Z-NOT-ACCEPTED', 1, 2)])
        preview = ok(client.post(IMPORT+'preview', files=upload))
        assert [g['ready'] for g in preview['groups']] == [True, False]
        assert confirm(client, upload, preview).status_code == 409
        current = ok(client.get('/api/carton-supplier/unified-deliveries', params={'factory_id': FACTORY}))
        assert current['items'] == []
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialShipment
        from sqlalchemy import select, func
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(SpecialShipment)) == 0


@pytest.mark.parametrize('revoked', ['permission', 'session'])
def test_original_confirmation_rechecks_authority_after_file_parsing(monkeypatch, revoked):
    with make_client(monkeypatch) as client:
        setup(client); order = created(client); supplier_login(client)
        upload = file_for([(order, 'REVOKED', 1, 2)])
        preview = ok(client.post(IMPORT+'preview', files=upload))
        from app.services import carton_supplier_delivery_import as service
        from app.db import SessionLocal
        from app.models.auth import AuthSession, AuthUserPermissionOverride
        from app.models.carton_special_requests import SpecialShipment
        from sqlalchemy import select, update, func
        parse = service._parse_delivery_spreadsheet
        def revoke_during_parse(*args, **kwargs):
            result = parse(*args, **kwargs)
            with SessionLocal() as db:
                if revoked == 'permission':
                    db.get(AuthUserPermissionOverride, 'supplier-allow-supplier-test-carton_supplier:edit').status = 'revoked'
                else:
                    db.execute(update(AuthSession).where(AuthSession.user_id == 'supplier-test').values(status='revoked'))
                db.commit()
            return result
        monkeypatch.setattr(service, '_parse_delivery_spreadsheet', revoke_during_parse)
        assert confirm(client, upload, preview).status_code == (403 if revoked == 'permission' else 401)
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(SpecialShipment)) == 0
