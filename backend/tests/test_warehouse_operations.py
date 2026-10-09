from uuid import uuid4
import importlib
import pytest
from test_molding_sample_api import login_as
from warehouse_location_fixtures import make_client

BASE = '/api/warehouse-operations'


def workspace(client, warehouse='fabric'):
    response = client.get(f'{BASE}/{warehouse}', params={'factory_id': 'huakang-c'})
    assert response.status_code == 200, response.text
    return response.json()


def payload(client, kind, warehouse='fabric', **values):
    return {'factory_id': 'huakang-c', 'request_id': str(uuid4()), 'expected_revision': workspace(client, warehouse)['revision'],
        'kind': kind, 'business_date': '2026-07-18', 'source_no': uuid4().hex, 'source_line': '1',
        'item_code': '00012', 'item_name': '白色布', 'unit': '码', 'location': 'A01', 'lot': '00001',
        'location_id': f"{warehouse}-{values.get('location', 'A01')}", 'counterparty': '车间一', 'quantity': '10', 'purpose': '按放产单领用', 'reason': '现场确认的原始凭据',
        **values}


def post(client, body, warehouse='fabric', status=200):
    response = client.post(f'{BASE}/{warehouse}/documents', json=body)
    assert response.status_code == status, response.text
    return response.json()


def quality(client, batch, warehouse='fabric', state='QUALIFIED'):
    """Seed a historical QC document in the isolated test DB; new QC posting is closed."""
    from sqlalchemy import select
    from copy import deepcopy
    db_module = importlib.import_module('app.db')
    service = importlib.import_module('app.services.warehouse_operations')
    model = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
    user_model = importlib.import_module('app.models.auth').AuthUser
    schema = importlib.import_module('app.schemas.warehouse_operations').WarehouseDocumentRequest
    request = schema(**payload(client, 'QUALITY', warehouse, batch_id=batch, quality_status=state, responsible_person='QC张师傅')).model_dump(mode='json')
    with db_module.SessionLocal() as db:
        actor = db.scalar(select(user_model).where(user_model.username == 'admin'))
        entry = {'id': 'LEGACY-' + uuid4().hex, 'kind': 'QUALITY', 'sequence': request['expected_revision'] + 1,
            'business_date': request['business_date'], 'data': deepcopy(request), 'actor_name': actor.display_name, 'occurred_at': '2026-07-18T16:30:00+08:00'}
        stock, entries = service.projection(db, warehouse)
        service.apply_entry(stock, entries, entry, warehouse)
        row = model(id=entry['id'], factory_id='huakang-c', warehouse=warehouse, sequence=entry['sequence'], request_id=request['request_id'],
            request_hash=service.digest([warehouse, actor.id, service.request_body(schema(**request))]), kind='QUALITY', business_date=request['business_date'],
            payload_json=service.dump(entry['data']), actor_id=actor.id, actor_name=actor.display_name, occurred_at=entry['occurred_at'])
        db.add(row); db.commit()
        return service.entry_data(row), request


def test_fabric_receipt_release_partial_issue_allocations_return_and_transfer(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        receipt = post(client, payload(client, 'RECEIPT', quantity='10.3'))
        request = post(client, payload(client, 'REQUEST', quantity='5.3'))
        quality(client, receipt['id'], state='HOLD')
        issue = payload(client, 'ISSUE', batch_id=receipt['id'], original_id=request['id'], quantity='3.2',
            allocations=[{'production_no': 'FC001', 'quantity': '1.1'}, {'production_no': 'FC002', 'quantity': '2.1'}])
        post(client, issue, status=409)
        quality(client, receipt['id'])
        issue.update(expected_revision=workspace(client)['revision'])
        first = post(client, issue)
        assert post(client, issue) == first
        post(client, {**issue, 'quantity': '4'}, status=409)
        view = workspace(client)
        assert next(row for row in view['stock'] if row['id'] == receipt['id'])['quantity'] == '7.1'
        assert next(row for row in view['documents'] if row['id'] == request['id'])['issued_quantity'] == '3.2'
        post(client, payload(client, 'ISSUE', batch_id=receipt['id'], original_id=request['id'], quantity='3',
            allocations=[{'production_no': 'FC003', 'quantity': '3'}]), status=409)
        returned = post(client, payload(client, 'RETURN', original_id=first['id'], quantity='1.2', location='退料位'))
        returned_batch = next(row for row in workspace(client)['stock'] if row['id'] == returned['id'])
        assert returned_batch['quality_status'] == 'PENDING_INSPECTION' and returned_batch['quantity'] == '1.2'
        post(client, payload(client, 'RETURN', original_id=first['id'], quantity='2.1'), status=409)
        transfer = post(client, payload(client, 'TRANSFER', batch_id=receipt['id'], quantity='2.1', location='A02'))
        stock = {row['id']: row for row in workspace(client)['stock']}
        assert stock[receipt['id']]['quantity'] == '5.0' and stock[transfer['id']]['quantity'] == '2.1'
        assert stock[transfer['id']]['quality_status'] == 'QUALIFIED'
        assert stock[returned['id']]['available_quantity'] == '1.2'


def test_semi_processing_separate_units_rounds_packaging_and_rework(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        receipt = post(client, payload(client, 'RECEIPT', 'semi', process_state='车缝完成', unit='件', quantity='10'), 'semi')
        quality(client, receipt['id'], 'semi')
        task = post(client, payload(client, 'TASK', 'semi', item_code='P002', item_name='冲棉成品', process_state='冲棉完成', unit='对', quantity='5'), 'semi')
        sent = post(client, payload(client, 'PROCESS_SEND', 'semi', batch_id=receipt['id'], task_id=task['id'], quantity='10'), 'semi')
        assert next(row for row in workspace(client, 'semi')['stock'] if row['id'] == receipt['id'])['quantity'] == '0'
        returned = post(client, payload(client, 'PROCESS_RETURN', 'semi', original_id=sent['id'], quantity='2', consumed_quantity='4', lot='NEW-0002'), 'semi')
        view = workspace(client, 'semi')
        batch = next(row for row in view['stock'] if row['id'] == returned['id'])
        assert batch['unit'] == '对' and batch['item_code'] == 'P002' and batch['process_state'] == '冲棉完成'
        assert batch['lot'] == 'NEW-0002' and returned['data']['unit'] == '对'
        current_send = next(row for row in view['documents'] if row['id'] == sent['id'])
        assert current_send['consumed_quantity'] == '4' and current_send['returned_quantity'] == '2'
        post(client, payload(client, 'PROCESS_RETURN', 'semi', original_id=sent['id'], quantity='4', consumed_quantity='6'), 'semi', 409)
        quality(client, returned['id'], 'semi')
        package = post(client, payload(client, 'PACK_SEND', 'semi', batch_id=returned['id'], quantity='2', counterparty='包装一组'), 'semi')
        post(client, payload(client, 'PACK_RECEIVE', 'semi', original_id=package['id'], quantity='1', responsible_person='包装李师傅'), 'semi')
        post(client, payload(client, 'RETURN', 'semi', original_id=package['id'], quantity='1'), 'semi')
        post(client, payload(client, 'PACK_RECEIVE', 'semi', original_id=package['id'], quantity='1', responsible_person='包装李师傅'), 'semi', 409)
        post(client, payload(client, 'CORRECTION', 'semi', original_id=package['id']), 'semi', 409)
        assert workspace(client)['documents'] == []


def test_reversal_keeps_original_and_blocks_dependencies_and_stale_requests(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        body = payload(client, 'RECEIPT')
        receipt = post(client, body)
        post(client, {**body, 'request_id': str(uuid4()), 'expected_revision': workspace(client)['revision']}, status=409)
        post(client, payload(client, 'CORRECTION', original_id=receipt['id']))
        view = workspace(client)
        assert next(row for row in view['documents'] if row['id'] == receipt['id'])['reversed']
        assert view['stock'][0]['quantity'] == '0'
        post(client, payload(client, 'CORRECTION', original_id=receipt['id']), status=409)
        other = post(client, payload(client, 'RECEIPT', source_no='NEW'))
        stale = payload(client, 'TRANSFER', batch_id=other['id'], quantity='1', location='A02')
        quality(client, other['id'])
        post(client, stale, status=409)
        post(client, payload(client, 'CORRECTION', original_id=other['id']), status=409)


def test_existing_source_receipts_remain_read_only_and_are_available_to_new_ledger(monkeypatch):
    from test_fabric_procurement import book, row, stored
    from test_fabric_procurement_tracking import save
    from test_fabric_receiving import request, receive
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        save(client, book([row()]))
        source = stored(client)['items'][0]
        original = receive(client, source, request(source, receipt_date='2026-07-18')).json()
        stock = workspace(client)['stock']
        assert len(stock) == 2 and {s['quantity'] for s in stock} == {'20.1', '29.9'}
        quality(client, stock[0]['id'])
        req = post(client, payload(client, 'REQUEST', item_code=stock[0]['item_code'], item_name=stock[0]['item_name'], unit=stock[0]['unit'], quantity='1'))
        post(client, payload(client, 'ISSUE', batch_id=stock[0]['id'], original_id=req['id'], quantity='1', allocations=[{'production_no': 'FC001', 'quantity': '1'}]))
        replay = receive(client, source, request(source, receipt_date='2026-07-18'))
        assert replay.status_code == 409
        assert stored(client)['items'][0]['warehouse_received_quantity'] == '50.0'
        api = client.get('/api/fabric-warehouse/procurement/receipts', params={'factory_id': 'huakang-c'}).json()
        assert api['items'][0]['batches'] == original['batches']


def test_factory_authority_and_missing_schema(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        assert client.get(BASE + '/semi', params={'factory_id': 'huakang-a'}).status_code == 422
        body = payload(client, 'RECEIPT')
        api_module = importlib.import_module('app.api.warehouse_operations')
        monkeypatch.setattr(api_module, 'can', lambda actor, permission, factory, department: permission.endswith(':read'))
        post(client, body, status=403)
        assert workspace(client)['documents'] == []
        monkeypatch.setattr(api_module, 'can', lambda *args: False)
        assert client.get(BASE + '/fabric', params={'factory_id': 'huakang-c'}).status_code == 403
        monkeypatch.setattr(api_module, 'can', lambda *args: True)
        db_module = importlib.import_module('app.db')
        model = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
        model.__table__.drop(db_module.engine)
        assert client.get(BASE + '/semi', params={'factory_id': 'huakang-c'}).status_code == 503


@pytest.mark.parametrize('warehouse', ['fabric', 'semi'])
def test_optional_notes_keep_critical_fields_and_stock_lineage(monkeypatch, warehouse):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')

        def make(kind, **values):
            return payload(client, kind, warehouse, process_state='车缝完成', reason='', **values)

        def linked(kind, **values):
            return make(kind, source_no='', **values)

        for kind in ['RECEIPT', 'REQUEST'] + (['TASK'] if warehouse == 'semi' else []):
            post(client, linked(kind), warehouse, 422)
        receipt = post(client, make('RECEIPT'), warehouse)
        request = post(client, make('REQUEST', purpose='', quantity='5'), warehouse)
        assert request['data']['purpose'] == ''
        post(client, linked('QUALITY', batch_id=receipt['id'], quality_status='QUALIFIED', responsible_person='张师傅'), warehouse, 409)
        moved = post(client, linked('TRANSFER', batch_id=receipt['id'], location='A02', quantity='1'), warehouse)
        post(client, linked('CORRECTION', original_id=moved['id']), warehouse, 422)
        correction = linked('CORRECTION', original_id=moved['id'])
        correction['reason'] = '录错'
        post(client, correction, warehouse)
        issue = post(client, linked('ISSUE', batch_id=receipt['id'], original_id=request['id'], quantity='3',
            allocations=[{'production_no': 'FC01', 'quantity': '3'}]), warehouse)
        returned = post(client, linked('RETURN', original_id=issue['id'], quantity='1'), warehouse)
        stock = {row['id']: row for row in workspace(client, warehouse)['stock']}
        assert stock[receipt['id']]['quantity'] == '7'
        assert stock[returned['id']]['quantity'] == '1' and stock[returned['id']]['available_quantity'] == '1'
        assert stock[returned['id']]['source_document'] == returned['id']
        assert returned['data']['original_id'] == issue['id']
        assert returned['data']['reason'] == ''

        if warehouse == 'semi':
            post(client, make('TASK', purpose=''), warehouse, 422)
            task = post(client, make('TASK', quantity='1', purpose='冲棉'), warehouse)
            sent = post(client, linked('PROCESS_SEND', task_id=task['id'], batch_id=receipt['id'], quantity='2'), warehouse)
            back = post(client, linked('PROCESS_RETURN', original_id=sent['id'], quantity='1', consumed_quantity='2'), warehouse)
            quality(client, back['id'], warehouse)
            packed = post(client, linked('PACK_SEND', batch_id=back['id'], quantity='1'), warehouse)
            post(client, linked('PACK_RECEIVE', original_id=packed['id'], quantity='1'), warehouse, 422)
            received = post(client, linked('PACK_RECEIVE', original_id=packed['id'], quantity='1', responsible_person='李师傅'), warehouse)
            assert received['data']['reason'] == ''
            assert next(row for row in workspace(client, warehouse)['documents'] if row['id'] == packed['id'])['received_quantity'] == '1'


def test_normalized_quantities_replacement_and_batch_chronology(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        body = payload(client, 'RECEIPT', quantity='1,000')
        original = post(client, body)
        assert original['data']['quantity'] == '1000'
        post(client, payload(client, 'CORRECTION', original_id=original['id']))
        new_body = {**body, 'request_id': str(uuid4()), 'expected_revision': workspace(client)['revision'], 'quantity': '900'}
        replacement = post(client, new_body)
        assert replacement['data']['replaces_id'] == original['id']
        assert post(client, body) == original
        quality(client, replacement['id'])
        request = post(client, payload(client, 'REQUEST', quantity='1,000'))
        post(client, payload(client, 'ISSUE', business_date='2026-07-17', batch_id=replacement['id'], original_id=request['id'], quantity='1',
            allocations=[{'production_no': 'FC01', 'quantity': '1'}]), status=409)
        issued = post(client, payload(client, 'ISSUE', batch_id=replacement['id'], original_id=request['id'], quantity='1',
            allocations=[{'production_no': 'FC01', 'quantity': '1'}]))
        assert issued['data']['item_code'] == replacement['data']['item_code']
        returned = post(client, payload(client, 'RETURN', original_id=issued['id'], quantity='1', item_code='FORGED', unit='错误单位'))
        assert returned['data']['item_code'] == '00012' and returned['data']['unit'] == '码'


@pytest.mark.parametrize('warehouse', ['fabric', 'semi'])
def test_direct_issue_transfer_reversal_and_legacy_quality_boundary(monkeypatch, warehouse):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        receipt = post(client, payload(client, 'RECEIPT', warehouse, process_state='车缝完成'), warehouse)
        assert workspace(client, warehouse)['stock'][0]['available_quantity'] == '10'
        direct = payload(client, 'ISSUE', warehouse, batch_id=receipt['id'], quantity='3', source_no='', reason='', purpose='')
        post(client, {**direct, 'counterparty': ''}, warehouse, 422)
        post(client, {**direct, 'quantity': '11'}, warehouse, 409)
        post(client, {**direct, 'allocations': [{'production_no': 'FC1', 'quantity': '2'}]}, warehouse, 422)
        issued = post(client, direct, warehouse)
        assert post(client, direct, warehouse) == issued
        assert issued['data']['original_id'] == '' and issued['data']['allocations'] == []
        assert issued['data']['item_code'] == receipt['data']['item_code']
        assert workspace(client, warehouse)['stock'][0]['quantity'] == '7'
        post(client, payload(client, 'CORRECTION', warehouse, original_id=issued['id']), warehouse)
        assert workspace(client, warehouse)['stock'][0]['quantity'] == '10'
        moved = post(client, payload(client, 'TRANSFER', warehouse, batch_id=receipt['id'], location='A02', quantity='4', source_no='', reason=''), warehouse)
        stock = {row['id']: row for row in workspace(client, warehouse)['stock']}
        assert stock[receipt['id']]['quantity'] == '6' and stock[moved['id']]['quantity'] == '4'
        assert stock[moved['id']]['quality_status'] == 'PENDING_INSPECTION'
        post(client, payload(client, 'TRANSFER', warehouse, batch_id=moved['id'], location='A02', quantity='1'), warehouse, 422)
        issued_again = post(client, payload(client, 'ISSUE', warehouse, batch_id=moved['id'], quantity='1'), warehouse)
        post(client, payload(client, 'RETURN', warehouse, original_id=issued_again['id'], quantity='1'), warehouse)
        post(client, payload(client, 'CORRECTION', warehouse, original_id=issued_again['id']), warehouse, 409)
        historical, request = quality(client, receipt['id'], warehouse, 'HOLD')
        assert post(client, request, warehouse) == historical
        post(client, {**request, 'reason': 'changed'}, warehouse, 409)
        post(client, payload(client, 'QUALITY', warehouse, batch_id=receipt['id'], quality_status='QUALIFIED', responsible_person='QC'), warehouse, 409)
        post(client, payload(client, 'ISSUE', warehouse, batch_id=receipt['id'], quantity='1'), warehouse, 409)
        blocked_move = post(client, payload(client, 'TRANSFER', warehouse, batch_id=receipt['id'], location='隔离区', quantity='1'), warehouse)
        stock = {row['id']: row for row in workspace(client, warehouse)['stock']}
        assert stock[blocked_move['id']]['quality_status'] == 'HOLD' and stock[blocked_move['id']]['available_quantity'] == '0'
        quality(client, receipt['id'], warehouse, 'REJECTED')
        post(client, payload(client, 'ISSUE', warehouse, batch_id=receipt['id'], quantity='1'), warehouse, 409)
        assert any(row['id'] == historical['id'] for row in workspace(client, warehouse)['documents'])


def test_concurrent_issues_use_one_factory_lock_and_do_not_overspend(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        receipt = post(client, payload(client, 'RECEIPT'))
        quality(client, receipt['id'])
        request = post(client, payload(client, 'REQUEST', quantity='20'))
        body = payload(client, 'ISSUE', batch_id=receipt['id'], original_id=request['id'], quantity='7', allocations=[{'production_no': 'FC01', 'quantity': '7'}])
        barrier = Barrier(2)
        def submit(identifier):
            barrier.wait(timeout=10)
            return client.post(BASE + '/fabric/documents', json={**body, 'request_id': identifier}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [str(uuid4()), str(uuid4())]))
        assert sorted(results) == [200, 409]
        assert workspace(client)['stock'][0]['quantity'] == '3'


def test_forward_migration_preserves_existing_data_and_refuses_evidence_loss(monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from pathlib import Path
    from sqlalchemy import text, inspect
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        db_module = importlib.import_module('app.db')
        model = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
        model.__table__.drop(db_module.engine)
        path = Path(__file__).parents[1] / 'alembic/versions/20261009_0150_warehouse_operations.py'
        spec = importlib.util.spec_from_file_location('warehouse_migration_test', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with db_module.engine.begin() as connection:
            users_before = connection.scalar(text('SELECT COUNT(*) FROM auth_users'))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            assert connection.scalar(text('SELECT COUNT(*) FROM auth_users')) == users_before
            assert 'warehouse_operations_documents' in inspect(connection).get_table_names()
        post(client, payload(client, 'RECEIPT'))
        with db_module.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                with pytest.raises(RuntimeError, match='禁止删除降级'):
                    migration.downgrade()
