from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_fabric_master_chase import master
from test_molding_sample_api import login_as
from test_warehouse_operations import payload, post, workspace
from warehouse_location_fixtures import make_client


ROOT = '/api/warehouse-operations/fabric/subcontract'
FACTORY = 'huakang-c'
DAY = '2026-07-18'


def test_subcontract_stock_receipts_and_audited_corrections(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        def view():
            resp = client.get(ROOT, params={'factory_id': FACTORY})
            assert resp.status_code == 200, resp.text
            return resp.json()
        def command(path, data, status=200):
            body = dict(factory_id=FACTORY, expected_revision=view()['revision'], request_id=str(uuid4()), **data)
            response = client.post(ROOT + path, json=body)
            assert response.status_code == status, response.text
            if status == 200:
                assert client.post(ROOT + path, json=body).json() == response.json()
            return response.json()
        raw = post(client, payload(client, 'RECEIPT', quantity='30'))
        product = client.post('/api/fabric-warehouse/master', json=master(code='BIND', name='捆条', data={'category':'ACCESSORY','unit':'条'})).json()
        factory = command('/processors', dict(code='JG1', name='本地测试厂', processes=['捆条', '电绣']))
        catalog = client.get(ROOT + '/processors', params={'factory_id':FACTORY})
        assert catalog.status_code == 200 and catalog.json()['processors'] == [factory]
        assert 'stock' not in catalog.json()
        plan = dict(process='捆条', processor_id=factory['id'], business_date=DAY, due_date=DAY,
                    inputs=[{'id': raw['id'], 'quantity':'30'}], outputs=[{'id':product['id'], 'quantity':'1000'}])
        command('/orders', {**plan, 'process':'电绣'}, 409)
        order = command('/orders', plan)
        assert workspace(client)['stock'][0]['quantity'] == '30'
        path = '/orders/' + order['id'] + '/actions'
        def act(kind, target, qty, status=200, **kwargs):
            return command(path, dict(kind=kind, target_id=target, quantity=qty, voucher=uuid4().hex,
                                      business_date=DAY, **kwargs), status)
        def current():
            return view()['orders'][0]
        act('SOURCE', order['id'], None)
        assert current()['source_no']
        act('SOURCE', order['id'], None, 409)
        act('SEND', raw['id'], '10')
        sent = current()['events'][-1]
        act('SIGN', sent['id'], '11', 409)
        act('SIGN', sent['id'], '10')
        act('VOID', sent['id'], None, 409, reason='有后续签收')
        act('DELIVER', product['id'], '600')
        delivery = current()['events'][-1]
        act('RECEIVE', delivery['id'], '601', 409, location_id='fabric-辅料位')
        act('RECEIVE', delivery['id'], '600', 422, location_id='fabric-A01')
        receive_body = dict(kind='RECEIVE', target_id=delivery['id'], quantity='500', voucher='回仓-1',
                            business_date=DAY, location_id='fabric-辅料位')
        received = command(path, receive_body)
        command(path, receive_body, 409)
        act('RECEIVE', delivery['id'], '100', location_id='fabric-辅料位')
        act('ISSUE', raw['id'], '1', 409, recipient='裁床', destination='裁床')
        response = act('ISSUE', received['stock_id'], '250', recipient='裁床', destination='裁床一组')
        check = current()
        assert [(r['outstanding'],r['undelivered'],r['uncounted'],r['available']) for r in check['outputs']] == [('400','400','0','350')]
        generic = payload(client, 'CORRECTION', original_id=response['stock_id'])
        post(client, generic, status=422)
        act('VOID', check['events'][-1]['id'], None, reason='领用数量录错')
        assert current()['outputs'][0]['available'] == '600'
        relocated = post(client, payload(client, 'TRANSFER', batch_id=received['stock_id'], location='辅料位', quantity='2'), status=422)
        assert relocated['detail']
        # Two clients cannot post two debits against the same observed balance.
        revision = view()['revision']
        def compete(_):
            body = dict(kind='ISSUE', target_id=received['stock_id'], quantity='400', business_date=DAY,
                        recipient='裁床', destination='裁床', voucher=uuid4().hex, factory_id=FACTORY,
                        expected_revision=revision, request_id=str(uuid4()))
            return client.post(ROOT + path, json=body).status_code
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(compete, range(2))) == [200,409]
        assert current()['outputs'][0]['available'] == '200'
        other = post(client, payload(client, 'ISSUE', batch_id=received['stock_id'], quantity='10', source_no='仓单-12'))
        assert current()['outputs'][0]['available'] == '190'
        assert current()['other_movements'][-1]['voucher'] == '仓单-12'
        returned = post(client, payload(client, 'RETURN', original_id=other['id'], quantity='4',
                                        location_id='fabric-辅料位', source_no='退单-1'))
        assert current()['outputs'][0]['available'] == '194'
        assert returned['id'] in {b['id'] for b in current()['batches']}
        month = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id':FACTORY,'month':'2026-07'}).json()
        assert {'processor-in:'+factory['id'], 'processor-out:'+factory['id']} <= {p['key'] for p in month['parties']}
        history = client.get('/api/fabric-warehouse/procurement/receipts',
                             params={'factory_id':FACTORY,'unified':'true','channel':'SUBCONTRACT'})
        assert history.status_code == 200, history.text
        assert {r['subcontract_order_id'] for r in history.json()['items']} == {order['id']}
        assert client.get(ROOT, params={'factory_id':'huakang-b'}).status_code in (403,422)
        import importlib
        router = importlib.import_module('app.api.warehouse_operations')
        monkeypatch.setattr(router, 'can', lambda actor, permission, *args: permission == 'fabric_operations:read')
        assert view()['can_operate'] is False
        command('/orders', plan, 403)
        monkeypatch.setattr(router, 'can', lambda actor, permission, *args: permission in {'fabric_warehouse:read','fabric_warehouse:import'})
        assert client.get(ROOT, params={'factory_id':FACTORY}).status_code == 403
        assert client.get(ROOT+'/processors', params={'factory_id':FACTORY}).json()['can_manage']


def test_combined_receipt_is_atomic_idempotent_and_individually_correctable(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')

        def view():
            response = client.get(ROOT, params={'factory_id': FACTORY})
            assert response.status_code == 200, response.text
            return response.json()

        def command(**fields):
            return dict(factory_id=FACTORY, expected_revision=view()['revision'], request_id=str(uuid4()), **fields)

        def submit(path, body, status=200):
            response = client.post(ROOT + path, json=body)
            assert response.status_code == status, response.text
            return response.json()

        material = client.post('/api/fabric-warehouse/master', json=master(
            code='RIBBON', name='捆条', data={'category': 'ACCESSORY', 'unit': '米'}))
        assert material.status_code == 200, material.text
        item_id = material.json()['id']
        processor = submit('/processors', command(code='P1', name='测试厂', processes=['捆条']))
        order = submit('/orders', command(process='捆条', processor_id=processor['id'], business_date=DAY,
            due_date=DAY, inputs=[], outputs=[{'id': item_id, 'quantity': '100'}]))
        path = '/orders/' + order['id'] + '/actions'
        receipt = command(kind='DELIVER_AND_RECEIVE', target_id=item_id, business_date=DAY,
            voucher='送货单-1', quantity='60', received_quantity='55', location_id='fabric-辅料位',
            lot='C01', roll_no='R1')
        before = view()
        from app.db import SessionLocal
        from app.services import fabric_procurement, fabric_subcontract

        def factory_revision():
            with SessionLocal() as db:
                return fabric_procurement.revision(db)

        original_revision = factory_revision()
        for fields, status in [
            ({'received_quantity': None}, 422),
            ({'received_quantity': '0'}, 422),
            ({'received_quantity': '61'}, 409),
            ({'location_id': 'fabric-A01'}, 422),
            ({'quantity': '101'}, 409),
            ({'expected_revision': before['revision'] - 1}, 409),
        ]:
            submit(path, {**receipt, **fields}, status)
            assert view() == before

        # Verify that even a failure after the stock movement was flushed is fully rolled back.
        append_entry = fabric_subcontract.append_entry

        def fail_receipt(db, actor, kind, facts, *args):
            if facts['kind'] == 'RECEIVE':
                assert facts['stock_id']
                raise RuntimeError('receipt journal write failed')
            return append_entry(db, actor, kind, facts, *args)

        with monkeypatch.context() as patch:
            patch.setattr(fabric_subcontract, 'append_entry', fail_receipt)
            with pytest.raises(RuntimeError, match='receipt journal write failed'):
                client.post(ROOT + path, json=receipt)
        assert view() == before
        assert factory_revision() == original_revision

        # Concurrent retries of the same request must see the same committed receipt.
        with ThreadPoolExecutor(2) as pool:
            first, retry = pool.map(lambda _: submit(path, receipt), range(2))
        assert first == retry
        after = view()
        saved = after['orders'][0]
        delivery, received = saved['events']
        assert [(e['kind'], e['quantity'], e['voucher']) for e in saved['events']] == [
            ('DELIVER', '60', '送货单-1'), ('RECEIVE', '55', '送货单-1')]
        assert received['target_id'] == first['target_id'] == delivery['id']
        assert delivery['remaining'] == '5'
        assert {batch['id'] for batch in saved['batches']} == {first['stock_id']}
        assert [(b['lot'], b['roll_no'], b['available']) for b in after['stock']] == [('C01', 'R1', '55')]
        product = saved['outputs'][0]
        assert (product['undelivered'], product['uncounted'], product['available']) == ('40', '5', '55')
        assert after['revision'] == before['revision'] + 3
        assert factory_revision() == original_revision + 1
        submit(path, {**receipt, 'received_quantity': '54'}, 409)
        fresh_id = str(uuid4())
        submit(path, {**receipt, 'request_id': fresh_id, 'expected_revision': after['revision']}, 409)
        assert view() == after

        def correct(event_id, status=200):
            return submit(path, command(kind='VOID', target_id=event_id, voucher=uuid4().hex,
                business_date=DAY, reason='测试更正'), status)

        correct(delivery['id'], 409)
        top_up = command(kind='RECEIVE', target_id=delivery['id'], quantity='5',
            location_id='fabric-辅料位', voucher='补点收', business_date=DAY)
        extra = submit(path, top_up)
        # A retry of a receipt submitted before the combined command existed uses this exact hash.
        from app.models.warehouse_operations import WarehouseOperation
        with SessionLocal() as db:
            row = db.scalars(select(WarehouseOperation).where(WarehouseOperation.request_id == top_up['request_id'])).one()
            legacy_body = {**top_up, 'lot': '', 'roll_no': '', 'recipient': '', 'destination': '', 'reason': ''}
            assert row.request_hash == fabric_subcontract.wh.digest([row.kind, order['id'], row.actor_id, legacy_body])
        topped_up = view()['orders'][0]
        assert topped_up['outputs'][0]['uncounted'] == '0'
        assert topped_up['outputs'][0]['available'] == '60'
        assert submit(path, receipt) == first
        correct(received['id'])
        assert view()['orders'][0]['outputs'][0]['available'] == '5'
        correct(delivery['id'], 409)
        correct(next(e['id'] for e in topped_up['events'] if e.get('stock_id') == extra['stock_id']))
        correct(delivery['id'])
        final = view()['orders'][0]
        assert not final['batches']
        assert final['outputs'][0]['undelivered'] == '100'
        assert {(e['kind'], e['voided']) for e in final['events']} == {
            ('RECEIVE', True), ('DELIVER', True), ('VOID', False)}
