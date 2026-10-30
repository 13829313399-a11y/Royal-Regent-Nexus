"""Shared order folder: optional steps, immutable versions and scope boundaries."""
import json
from io import BytesIO
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client as application_client, login_as
from test_carton_item_schedule import workbook, source_row, _prepare_schedule_customer

def make_client(monkeypatch):
    """Reconstruct pre-retirement records for historical reader/service regressions.

    Production HTTP writes remain 410; test_carton_shared_library checks that
    public boundary without this test-only dependency override.
    """
    client = application_client(monkeypatch)
    from app.api.carton_materials import retired_writes
    client.app.dependency_overrides[retired_writes] = lambda: None
    return client


BASE = '/api/carton-materials'
SCOPE = dict(factory_id='huaxing', audience='sales')


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED', 'true')
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def setup(client):
    _prepare_schedule_customer(client)
    login_as(client, 'admin')
    imported = ok(client.post('/api/carton-procurement/weekly-imports', params={'factory_id': 'huaxing'},
        data={'customer_code': 'DICKIE'}, files={'file': ('schedule.xlsx', workbook([source_row()]))}), 201)
    row = imported['parse_summary']['rows'][0]
    target = dict(kind='SCHEDULE', id=imported['id'], sheet=row['source_sheet'], row=row['source_row'])
    folder = ok(client.post(BASE, params=SCOPE, json=dict(target=target, request_id=uuid4().hex)))
    return folder, target


def command(client, state, action, audience='sales', **values):
    return client.post(BASE + f"/{state['id']}/actions", params={**SCOPE, 'audience': audience},
        json=dict(revision=state['revision'], request_id=uuid4().hex, action=action, **values))


def add(client, state, text='纸箱内径 30×20×10 cm；材质A33+B', audience='sales', **values):
    return client.post(BASE + f"/{state['id']}/versions", params={**SCOPE, 'audience': audience},
        data={'metadata': json.dumps(dict(revision=state['revision'], request_id=uuid4().hex, text=text, **values))})


def test_text_only_direct_confirmation_defaults_versions_and_retry(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        same = ok(client.post(BASE, params=SCOPE, json=dict(target=target, request_id=uuid4().hex)))
        assert same['id'] == state['id'] and same['revision'] == state['revision']
        state = ok(command(client, state, 'RULE', mode='INTERNAL', save_customer_default=True, default_revision=0))
        assert state['customer_default']['mode'] == 'INTERNAL'
        state = ok(add(client, state))
        version = state['versions'][0]
        assert not version['asset_id']
        body = dict(revision=state['revision'], request_id=uuid4().hex, action='APPROVE', note='仓库已核对做箱规格', version_ids=[version['id']])
        params = {**SCOPE, 'audience': 'warehouse'}
        approved = ok(client.post(BASE + f"/{state['id']}/actions", params=params, json=body))
        assert approved['status'] == 'READY' and approved['approval']['mode'] == 'INTERNAL'
        replay = ok(client.post(BASE + f"/{state['id']}/actions", params=params, json=body))
        assert replay['revision'] == approved['revision']
        assert client.post(BASE + f"/{state['id']}/actions", params=params, json={**body, 'note': '不同内容'}).status_code == 409
        assert command(client, state, 'COMMENT', note='旧版本写入').status_code == 409
        evidence = ok(add(client, approved, text='补存客户确认邮件截图说明', role='EVIDENCE'))
        assert evidence['status'] == 'READY' and evidence['approved_version_ids'] == [version['id']]
        approved = evidence
        draft = ok(add(client, approved, text='修改高度为12cm', previous_id=version['id']))
        assert draft['status'] != 'READY' and draft['approved_version_ids'] == [version['id']]
        assert draft['versions'][-1]['id'] not in draft['approved_version_ids']
        assert client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['total'] == 0
        assert command(client, draft, 'APPROVE', note='不能确认外单', version_ids=['foreign-id']).status_code == 422
        returned = ok(command(client, draft, 'REQUEST_CHANGES', next_party='WAREHOUSE', note='请重新核对高度'))
        assert not returned['approved_version_ids']


def test_supplier_handoff_customer_confirmation_and_private_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        from test_carton_supplier_portal import setup_portal, supplier_login
        setup_portal(client)
        login_as(client, 'admin')
        choices = ok(client.get(BASE + '/options', params=SCOPE))['suppliers']
        state = ok(command(client, state, 'RULE', mode='CUSTOMER', supplier_id=choices[0]['id']))
        state = ok(add(client, state, text='客户原稿内容', role='ORIGINAL'))
        state = ok(add(client, state, text='客户邮件联系人及私人回复', role='EVIDENCE'))
        secret_id = state['versions'][-1]['id']
        state = ok(command(client, state, 'HANDOFF', next_party='SUPPLIER'))
        supplier_login(client)
        visible = ok(client.get(BASE + f"/{state['id']}", params={**SCOPE, 'audience': 'supplier'}))
        contract = ok(client.get(BASE + '/contracts/' + state['contract_folder_id'], params={**SCOPE, 'audience': 'supplier'}))
        assert [row['authority_id'] for row in contract['authorities']] == [state['id']]
        assert not contract['versions'] and not contract['approved_version_ids']
        assert all(v['role'] != 'EVIDENCE' for v in visible['versions'])
        assert '私人回复' not in json.dumps(visible, ensure_ascii=False)
        assert command(client, state, 'APPROVE', audience='supplier', note='自己确认', version_ids=[state['versions'][0]['id']]).status_code == 403
        assert command(client, state, 'RULE', audience='supplier', mode='INTERNAL').status_code == 403
        assert client.get(BASE + f"/{state['id']}/versions/{secret_id}/document", params={**SCOPE, 'audience': 'supplier'}).status_code == 404
        state = ok(add(client, state, audience='supplier', text='排版回稿，按原稿制作', role='PROOF'))
        state = ok(command(client, state, 'HANDOFF', audience='supplier', next_party='SALES'))
        assert state['status'] == 'WAITING_CUSTOMER'
        login_as(client, 'admin')
        assert command(client, state, 'APPROVE', audience='warehouse', note='代客户确认', version_ids=[state['versions'][-1]['id']]).status_code == 403
        state = ok(command(client, state, 'APPROVE', note='客户邮件已确认本次文字稿', version_ids=[state['versions'][-1]['id']]))
        assert state['approval']['mode'] == 'CUSTOMER'
        state = ok(command(client, state, 'RULE', mode='CUSTOMER', supplier_id=''))
        assert state['next_party'] == 'SALES' and state['status'] == 'PROCESSING'
        assert ok(client.get(BASE, params={**SCOPE, 'todo': True}))['total'] == 1
        supplier_login(client)
        assert client.get(BASE + f"/{state['id']}", params={**SCOPE, 'audience': 'supplier'}).status_code in {403, 404}


def test_file_access_is_folder_scoped_and_generic_routes_cannot_bypass(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        from pypdf import PdfWriter
        stream = BytesIO(); writer = PdfWriter(); writer.add_blank_page(300, 200); writer.write(stream)
        metadata = dict(revision=state['revision'], request_id=uuid4().hex, role='WORKING', title='手工单扫描件')
        state = ok(client.post(BASE + f"/{state['id']}/versions", params=SCOPE, data={'metadata': json.dumps(metadata)}, files={'file': ('scan.pdf', stream.getvalue())}))
        version = state['versions'][0]
        downloaded = client.get(BASE + f"/{state['id']}/versions/{version['id']}/document", params=SCOPE)
        assert downloaded.status_code == 200 and downloaded.content == stream.getvalue()
        assert client.get('/api/carton-mark/assets/' + version['asset_id'] + '/document', params={'factory_id': 'huaxing'}).status_code == 404
        assert version['asset_id'] not in [row['id'] for row in ok(client.get('/api/carton-mark/assets', params={'factory_id': 'huaxing'}))]
        assert client.put('/api/carton-mark/assets/' + version['asset_id'] + '/classification', params={'factory_id': 'huaxing'}, json={'revision': 1, 'status': 'READY'}).status_code in {404, 405}
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            audit_id = db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.entity_type == 'carton_material_folder'))
        assert client.get('/api/carton-procurement/audit-events/' + audit_id, params={'factory_id': 'huaxing'}).status_code == 404
        login_as(client, 'a_warehouse_keeper')
        assert client.get(BASE + f"/{state['id']}", params={**SCOPE, 'audience': 'warehouse'}).status_code == 403
        assert client.get(BASE + f"/{state['id']}/versions/{version['id']}/document", params={**SCOPE, 'audience': 'warehouse'}).status_code == 403


def test_unknown_requirement_can_handoff_and_no_customer_scope_bypass(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        state = ok(add(client, state, text='待整理资料'))
        state = ok(command(client, state, 'HANDOFF', next_party='WAREHOUSE'))
        assert state['mode'] == 'UNDECIDED'
        assert command(client, state, 'APPROVE', note='未经确定', version_ids=[state['versions'][0]['id']]).status_code == 422
        assert ok(client.get(BASE, params={**SCOPE, 'audience': 'warehouse', 'todo': True}))['total'] == 1
        login_as(client, 'huaxing_molding_a_sales')
        state = ok(add(client, state, text='业务不需要仓库权限即可补原稿', role='ORIGINAL'))
        assert state['versions'][-1]['party'] == 'SALES'
        assert client.post(BASE, params={**SCOPE, 'factory_id': 'huakang-a'}, json={'target': target, 'request_id': uuid4().hex}).status_code == 403
        from app.db import SessionLocal
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.models.carton_procurement import CartonCustomer
        from app.models.auth import AuthUser
        from sqlalchemy import select
        with SessionLocal() as db:
            customer = db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == 'huaxing', CartonCustomer.customer_code == 'DICKIE'))
            admin = db.scalar(select(AuthUser).where(AuthUser.username == 'admin'))
            db.add(CartonCustomerAssignment(factory_id='huaxing', customer_id=customer.id, user_id=admin.id)); db.commit()
        from test_molding_sample_api import grant_permission_override
        for permission in ('carton_mark:read', 'carton_mark:template_upload'):
            grant_permission_override('qc_inspector', permission, factory_id='huaxing', department='pmc-warehouse')
        login_as(client, 'qc_inspector')
        scope = {**SCOPE, 'audience': 'warehouse'}
        assert client.get(BASE + '/' + state['id'], params=scope).status_code == 403
        assert add(client, state, audience='warehouse').status_code == 403
        assert ok(client.get(BASE, params=scope))['total'] == 0


def test_create_retries_defaults_and_shared_identity_are_exact(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        request = dict(target=target, request_id=uuid4().hex)
        assert ok(client.post(BASE, params=SCOPE, json=request))['revision'] == state['revision']
        assert ok(client.post(BASE, params=SCOPE, json=request))['id'] == state['id']
        assert client.post(BASE, params=SCOPE, json={**request, 'target': {**target, 'row': target['row'] + 1}}).status_code == 409
        state = ok(command(client, state, 'RULE', mode='INTERNAL', save_customer_default=True, default_revision=0))
        imported = ok(client.post('/api/carton-procurement/weekly-imports', params={'factory_id': 'huaxing'},
            data={'customer_code': 'DICKIE'}, files={'file': ('new.xlsx', workbook([source_row(contract='NEW-2')]))}), 201)
        row = imported['parse_summary']['rows'][0]
        newer = ok(client.post(BASE, params=SCOPE, json=dict(request_id=uuid4().hex,
            target=dict(kind='SCHEDULE', id=imported['id'], sheet=row['source_sheet'], row=row['source_row']))))
        assert newer['mode'] == 'INTERNAL'
        newer = ok(command(client, newer, 'RULE', mode='CUSTOMER', save_customer_default=True, default_revision=1))
        assert ok(client.get(BASE + '/' + state['id'], params=SCOPE))['mode'] == 'INTERNAL'
        from test_carton_procurement_api import _order_payload
        payload = dict(_order_payload(), contract_no=state['contract_no'], item_no=state['item_no'], customer_po=state['po'])
        purchase = ok(client.post('/api/carton-procurement/orders', json=payload), 201)
        linked = ok(client.post(BASE, params={**SCOPE, 'audience': 'warehouse'},
            json=dict(request_id=uuid4().hex, target=dict(kind='PURCHASE', id=purchase['order_no']))))
        assert linked['id'] == state['id']
        assert ok(client.get(BASE + '/candidates', params={**SCOPE, 'audience': 'warehouse'}))['items']
        # Ledger facts use the same effective reference as the imported schedule.
        from app.db import SessionLocal
        from app.models.customer_order_ledger import OrderLedgerLine
        with SessionLocal() as db:
            db.add(OrderLedgerLine(id='ledger-material', factory_id='huaxing', customer_code='dickie', customer_name='Dickie',
                identity_key='material-identity', reference_no=state['po'], product_no=state['item_no'], quantity=360, shipped_quantity=0,
                data={'contract_no': state['contract_no'], 'reference_no': state['po']}, created_at='2026-10-28', updated_at='2026-10-28'))
            db.commit()
        linked = ok(client.post(BASE, params=SCOPE, json=dict(request_id=uuid4().hex, target=dict(kind='LEDGER', id='ledger-material'))))
        assert linked['id'] == state['id']


def test_duplicate_schedule_and_legacy_purchase_identity_are_not_merged(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        imported = ok(client.post('/api/carton-procurement/weekly-imports', params={'factory_id': 'huaxing'},
            data={'customer_code': 'DICKIE'}, files={'file': ('duplicate.xlsx', workbook([source_row(), source_row()]))}), 201)
        row = imported['parse_summary']['rows'][0]
        duplicate = dict(kind='SCHEDULE', id=imported['id'], sheet=row['source_sheet'], row=row['source_row'])
        assert client.post(BASE, params=SCOPE, json=dict(request_id=uuid4().hex, target=duplicate)).status_code == 422
        assert ok(client.post(BASE + '/statuses', params=SCOPE, json={'targets': [duplicate]}))['items'][0]['label'] == '资料归属待核对'
        from test_carton_procurement_api import _order_payload
        payload = dict(_order_payload(), contract_no='LEGACY-EMPTY-PO', customer_po='')
        first = ok(client.post('/api/carton-procurement/orders', json=payload), 201)
        ok(client.post('/api/carton-procurement/orders', json=payload), 201)
        response = client.post(BASE, params={**SCOPE, 'audience': 'warehouse'},
            json=dict(request_id=uuid4().hex, target=dict(kind='PURCHASE', id=first['id'])))
        assert response.status_code == 422 and '拆单归属' in response.text


def test_statuses_recheck_folder_recipient_and_generic_audit_options(monkeypatch):
    with make_client(monkeypatch) as client:
        from test_carton_supplier_portal import setup_portal, supplier_login
        purchase = setup_portal(client)
        login_as(client, 'admin')
        scope = {**SCOPE, 'audience': 'warehouse'}
        target = dict(kind='PURCHASE', id=purchase['id'])
        state = ok(client.post(BASE, params=scope, json=dict(request_id=uuid4().hex, target=target)))
        state = ok(command(client, state, 'RULE', audience='warehouse', mode='INTERNAL', supplier_id=''))
        from app.db import SessionLocal
        from app.services import carton_procurement as core
        with SessionLocal() as db:
            assert 'CARTON_MATERIAL_CHANGED' not in core.audit_query_options(db, 'huaxing')['event_types']
        supplier_login(client)
        result = ok(client.post(BASE + '/statuses', params={**SCOPE, 'audience': 'supplier'}, json={'targets': [target]}))['items'][0]
        assert not result['folder_id'] and not result['handler'] and not result['ready']


def test_file_save_rechecks_session_after_worker_returns(monkeypatch):
    with make_client(monkeypatch) as client:
        state, target = setup(client)
        from app.api import carton_materials as api
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_mark import CartonMarkAsset
        from sqlalchemy import select, func
        async def worker(function, *args, **kwargs):
            result = dict(file_name='scan.pdf', content=b'%PDF-test', kind='pdf', content_type='application/pdf', sha256='hash')
            with SessionLocal() as db:
                user = db.scalar(select(AuthUser).where(AuthUser.username == 'admin'))
                user.status = 'inactive'; db.commit()
            return result
        monkeypatch.setattr(api, 'run_order_job', worker)
        response = client.post(BASE + f"/{state['id']}/versions", params=SCOPE,
            data={'metadata': json.dumps(dict(revision=state['revision'], request_id=uuid4().hex))}, files={'file': ('scan.pdf', b'%PDF-test')})
        assert response.status_code in {401, 403}, response.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset).where(CartonMarkAsset.recognition_source == 'materials_folder')) == 0


def _slice1_module(name):
    """Load the explicitly isolated experiment; never import it into app code."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'outputs' / 'carton-materials-slice1-20261028' / (name + '.py')
    spec = importlib.util.spec_from_file_location('carton_slice1_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_slice1_query_results_and_bounded_status_batch(tmp_path):
    probe = _slice1_module('query_probe')
    stats = probe.build(tmp_path / 'synthetic.sqlite3', 3, 20, 50, 20, 3)
    with probe.connect(tmp_path / 'synthetic.sqlite3') as db:
        for operation in ('contract_list', 'line_status_100', 'by_version', 'by_source'):
            values = [probe.query(db, strategy, operation, stats)[0]
                      for strategy in ('audit_scan', 'audit_keyed', 'audit_json_sql', 'projection')]
            assert all(value == values[0] for value in values[1:])
            if operation == 'contract_list':
                assert values[0]['total'] == 3
                assert all(row[1:] == (20, 7) for row in values[0]['items'])
            elif operation == 'by_version':
                assert values[0]['total'] == 3
            elif operation == 'by_source':
                assert values[0]['total'] == 60
        states, reads = probe.query(db, 'audit_keyed', 'line_status_100', stats)
        assert len(states) == 60  # 100 requested keys; 40 are deliberately missing.
        assert len(reads.sql) == 1  # One indexed batch, never one factory scan per row.
        assert reads.scope == 60 * 3
        for strategy in ('audit_keyed', 'audit_json_sql', 'projection'):
            assert probe.reference_write(db, strategy, stats)['rolled_back']
        # Latest inactive relation must hide its earlier active revisions.
        identifier = 'R000000-00'
        state = json.loads(db.execute("SELECT detail_json FROM carton_audit_events WHERE entity_type='reference' AND entity_id=? ORDER BY sequence DESC LIMIT 1", (identifier,)).fetchone()[0])
        state.update(active=0, revision=4)
        db.execute('INSERT INTO carton_audit_events(id,factory_id,entity_type,entity_id,detail_json) VALUES(?,?,?,?,?)',
                   ('TOMBSTONE', probe.FACTORY, 'reference', identifier, probe.dump(state)))
        db.execute('UPDATE bench_reference_current SET active=0 WHERE reference_id=?', (identifier,))
        for kind, key in (('reverse_version', 'V000000-00'), ('reverse_source', 'O000000-00')):
            index = json.loads(db.execute('SELECT detail_json FROM carton_audit_events WHERE entity_type=? AND entity_id=? ORDER BY sequence DESC LIMIT 1', (kind, key)).fetchone()[0])
            for reference in index['targets']:
                if reference['reference_id'] == identifier:
                    reference['active'] = 0
            db.execute('INSERT INTO carton_audit_events(id,factory_id,entity_type,entity_id,detail_json) VALUES(?,?,?,?,?)',
                       ('TOMBSTONE-' + kind, probe.FACTORY, kind, key, probe.dump(index)))
        db.commit()
        for operation, total in (('by_version', 2), ('by_source', 59)):
            values = [probe.query(db, strategy, operation, stats)[0]
                      for strategy in ('audit_scan', 'audit_keyed', 'audit_json_sql', 'projection')]
            assert all(value == values[0] for value in values[1:])
            assert values[0]['total'] == total


def test_slice1_actual_service_batch_transaction_feasibility(monkeypatch):
    import os
    from pathlib import Path
    probe = _slice1_module('transaction_probe')
    with make_client(monkeypatch) as client:
        state, _ = setup(client)
        login_as(client, 'huaxing_molding_a_sales')
        # The archived slice-1 probe deliberately seeds old-format authorities.
        # Register their contract aliases during fixture setup, not inside the
        # measured business transaction; its original event-count oracle remains meaningful.
        from app.services import carton_materials as service
        from app.services.carton_materials_resolver import Resolver,customer_for
        original_append = service.append
        def registered_seed(db, actor, factory, identifier, value, action, request_id, fingerprint, entity=service.ENTITY):
            original_append(db, actor, factory, identifier, value, action, request_id, fingerprint, entity)
            if action == 'SEED' and entity == service.ENTITY:
                db.flush()
                resolver=Resolver(db,factory,'sales',actor)
                root=resolver.root(value,customer_for(db,factory,value),actor,request_id,persist=True)
                resolver.member(root,value['id'],actor,request_id)
        monkeypatch.setattr(service, 'append', registered_seed)
        state = {key:value for key,value in state.items() if key not in
                 {'customer_id','contract_folder_id','scope_kind','schema_version','authority_id','mapping_status'}}
        result = probe.exercise(state)
    destination = os.environ.get('CARTON_SLICE1_EVIDENCE_DIR')
    if destination:
        root = Path(__file__).resolve().parents[2] / 'outputs'
        target = Path(destination).resolve()
        assert target.is_relative_to(root.resolve()), 'Evidence must stay in outputs/'
        target.mkdir(parents=True, exist_ok=True)
        (target / 'transactions.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def _customer_id():
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonCustomer
    from sqlalchemy import select
    with SessionLocal() as db:
        return db.scalar(select(CartonCustomer.id).where(CartonCustomer.factory_id == 'huaxing', CartonCustomer.customer_code == 'DICKIE'))


def _manual_contract(client, contract, request_id=None, **fields):
    return client.post(BASE + '/contracts', params=SCOPE,
        json=dict(contract=dict(customer_id=_customer_id(), contract_no=contract, **fields), request_id=request_id or uuid4().hex))


def _seed_legacy(base, contract, item='L-1', po='LP-1'):
    """Immutable old-format original + approval, including downloadable bytes."""
    import copy
    import hashlib
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.models.carton_mark import CartonMarkAsset
    from app.services.auth import build_auth_context
    from app.services import carton_materials as service
    from sqlalchemy import select
    state = copy.deepcopy(base)
    for key in ('customer_id','contract_folder_id','scope_kind','schema_version','authority_id','mapping_status',
                'can_write','customer_default','status_label','current_handler'):
        state.pop(key, None)
    state.update(contract_no=contract,item_no=item,po=po,revision=1,status='READY',mode='INTERNAL')
    state['id'] = service.legacy_folder_id('huaxing',state)
    content = b'%PDF-1.4 synthetic immutable legacy source'
    asset_id, version_id = 'old-asset-' + uuid4().hex, 'old-version-' + uuid4().hex
    state['versions'] = [dict(id=version_id, number=1, title='原旧稿', text='旧文字必须原样保留', role='WORKING',
        previous_id='', asset_id=asset_id, file_name='legacy.pdf', sha256=hashlib.sha256(content).hexdigest(),
        by='旧经办人', party='SALES', at='2026-10-01T00:00:00Z')]
    state['approved_version_ids'] = [version_id]
    state['approval'] = dict(by='旧审核人',at='2026-10-02T00:00:00Z',mode='INTERNAL',note='旧确认依据')
    state['timeline'] = [dict(action='APPROVE',by='旧审核人',at='2026-10-02T00:00:00Z',note='旧确认依据')]
    with SessionLocal() as db:
        actor = build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
        db.add(CartonMarkAsset(id=asset_id,factory_id='huaxing',file_name='legacy.pdf',kind='pdf',content=content,
            content_type='application/pdf',size_bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),
            recognition_source='materials_folder',candidates_json=json.dumps([state['id']]),
            created_by=actor.id,created_by_name=actor.display_name,created_at=service.now(),updated_at=service.now()))
        service.append(db,actor,'huaxing',state['id'],state,'LEGACY_FIXTURE',uuid4().hex,'synthetic')
        db.commit()
    return state, content


def _audit_total():
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonAuditEvent
    from sqlalchemy import select,func
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(CartonAuditEvent))


def test_slice2_contract_identity_multiple_items_and_blank_item(monkeypatch):
    with make_client(monkeypatch) as client:
        first, _ = setup(client)
        assert first['contract_folder_id'].startswith('CMF2-')
        imported = ok(client.post('/api/carton-procurement/weekly-imports',params={'factory_id':'huaxing'},
            data={'customer_code':'DICKIE'},files={'file':('other.xlsx',workbook([source_row(item='ITEM-OTHER')]))}),201)
        row = imported['parse_summary']['rows'][0]
        target = dict(kind='SCHEDULE',id=imported['id'],sheet=row['source_sheet'],row=row['source_row'])
        second = ok(client.post(BASE,params=SCOPE,json=dict(target=target,request_id=uuid4().hex)))
        assert first['id'] != second['id'] and first['contract_folder_id'] == second['contract_folder_id']
        listing = ok(client.get(BASE+'/contracts',params=SCOPE))
        assert listing['total'] == 1 and listing['items'][0]['id'] == first['contract_folder_id']
        contract = ok(client.get(BASE+'/contracts/'+first['contract_folder_id'],params=SCOPE))
        assert contract['order_count'] == 2
        assert {a['authority_id'] for a in contract['authorities'] if a['scope_kind']=='ORDER'} == {first['id'],second['id']}
        assert all(a['targets'] for a in contract['authorities'] if a['scope_kind']=='ORDER')
        assert contract['approved_version_ids'] == [] and not contract['can_write']
        manual = ok(_manual_contract(client,'０００Ａ  Ｂ'))
        assert manual['id'].startswith('CMF2-') and manual['id'] == manual['contract_folder_id']
        assert manual['item_no'] == manual['po'] == '' and manual['contract_no'] == '０００Ａ  Ｂ'
        same = ok(_manual_contract(client,'000a b',item_no='optional-item',po='optional-po'))
        assert same['id'] == manual['id'] and same['contract_no'] == '０００Ａ  Ｂ'
        saved = ok(add(client,manual,text='无货号的手工文字'))
        assert saved['versions'][0]['text'] == '无货号的手工文字'
        before = _audit_total()
        assert _manual_contract(client,'   ').status_code == 422
        assert _audit_total() == before
        denied = client.post(BASE+'/contracts',params={**SCOPE,'factory_id':'huakang-a'},
            json=dict(contract=dict(customer_id=_customer_id(),contract_no='000A B'),request_id=uuid4().hex))
        assert denied.status_code == 404 and _audit_total() == before


def test_slice2_legacy_contract_mapping_and_old_url_preserve_originals(monkeypatch):
    with make_client(monkeypatch) as client:
        base, _ = setup(client)
        old, content = _seed_legacy(base,'LEGACY-0007')
        before = _audit_total()
        visible = ok(client.get(BASE+'/'+old['id'],params=SCOPE))
        root = visible['contract_folder_id']
        assert visible['versions'] == old['versions'] and visible['approval'] == old['approval']
        listing = ok(client.get(BASE+'/contracts',params=SCOPE))
        assert any(row['id']==root and not row['registered'] for row in listing['items'])
        assert ok(client.get(BASE+'/contracts/'+root,params=SCOPE))['kind'] == 'LEGACY_MAP'
        assert _audit_total() == before  # GETs never migrate or register old folders.
        from test_carton_procurement_api import _order_payload
        order = ok(client.post('/api/carton-procurement/orders',json={**_order_payload(),
            'contract_no':old['contract_no'],'item_no':old['item_no'],'customer_po':old['po']}),201)
        linked = ok(client.post(BASE,params={**SCOPE,'audience':'warehouse'},
            json=dict(target=dict(kind='PURCHASE',id=order['id']),request_id=uuid4().hex)))
        assert linked['id'] == old['id'] and linked['contract_folder_id'] == root
        assert linked['versions'] == old['versions'] and linked['timeline'] == old['timeline']
        root_view = ok(client.get(BASE+'/contracts/'+root,params=SCOPE))
        assert root_view['kind'] == 'LEGACY_MAP' and [a['authority_id'] for a in root_view['authorities']] == [old['id']]
        assert not root_view['versions'] and not root_view['approved_version_ids']
        changed = ok(command(client,linked,'COMMENT',note='仍写回原旧夹'))
        assert changed['id'] == old['id'] and changed['revision'] == 2
        assert changed['approval'] == old['approval'] and changed['versions'] == old['versions']
        downloaded = client.get(BASE+f"/{old['id']}/versions/{old['versions'][0]['id']}/document",params=SCOPE)
        assert downloaded.status_code == 200 and downloaded.content == content
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from app.services import carton_materials as service
        from sqlalchemy import select
        with SessionLocal() as db:
            assert service.get(db,'huaxing',old['id'])['versions'] == old['versions']
            for audit in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id==root)):
                if audit.entity_type == service.ENTITY:
                    pytest.fail('A legacy contract must not gain a parallel native folder')
            metadata = db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.entity_id==root))
        assert client.get('/api/carton-procurement/audit-events/'+metadata,params={'factory_id':'huaxing'}).status_code == 404


def test_slice2_ambiguous_legacy_requires_explicit_single_order_mapping(monkeypatch):
    with make_client(monkeypatch) as client:
        base, _ = setup(client)
        old, _ = _seed_legacy(base,'LEGACY-DUPLICATE',po='')
        from test_carton_procurement_api import _order_payload
        payload = {**_order_payload(),'contract_no':old['contract_no'],'item_no':old['item_no'],'customer_po':''}
        first = ok(client.post('/api/carton-procurement/orders',json=payload),201)
        second = ok(client.post('/api/carton-procurement/orders',json=payload),201)
        targets = [dict(kind='PURCHASE',id=o['id']) for o in (first,second)]
        before = _audit_total()
        for target in targets:
            assert client.post(BASE,params={**SCOPE,'audience':'warehouse'},json=dict(target=target,request_id=uuid4().hex)).status_code == 422
        assert _audit_total() == before
        historical = ok(client.get(BASE+'/'+old['id'],params=SCOPE))
        assert not historical['can_write'] and historical['versions'] == old['versions']
        statuses = ok(client.post(BASE+'/statuses',params={**SCOPE,'audience':'warehouse'},json={'targets':targets}))['items']
        assert all(not row['ready'] and not row['folder_id'] for row in statuses)
        assert command(client,old,'COMMENT',note='不能绕过归属').status_code == 422
        root = ok(_manual_contract(client,old['contract_no']))
        assert root['kind'] == 'LEGACY_MAP'
        body = dict(folder_id=old['id'],revision=1,target=targets[0],request_id=uuid4().hex)
        url = BASE+'/contracts/'+root['id']+'/mappings'
        ok(client.post(url,params={**SCOPE,'audience':'warehouse'},json=body))
        before = _audit_total()
        ok(client.post(url,params={**SCOPE,'audience':'warehouse'},json=body))
        assert _audit_total() == before
        assert client.post(url,params={**SCOPE,'audience':'warehouse'},json={**body,'request_id':uuid4().hex,'target':targets[1]}).status_code == 409
        assert _audit_total() == before
        statuses = ok(client.post(BASE+'/statuses',params={**SCOPE,'audience':'warehouse'},json={'targets':targets}))['items']
        assert statuses[0]['ready'] and statuses[0]['folder_id']==old['id']
        assert not statuses[1]['ready'] and not statuses[1]['folder_id']
        changed = ok(command(client,old,'COMMENT',note='人工确认归属后写回'))
        assert changed['id']==old['id'] and changed['approval']==old['approval']


def test_slice2_switch_blocks_all_write_entrypoints_but_keeps_reads(monkeypatch):
    with make_client(monkeypatch) as client:
        state,target = setup(client)
        old,content = _seed_legacy(state,'LEGACY-SWITCH')
        assert ok(client.get(BASE+'/capabilities',params=SCOPE))['writes_enabled']
        monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
        before = _audit_total()
        assert not ok(client.get(BASE+'/capabilities',params=SCOPE))['writes_enabled']
        for folder in (state,old):
            assert not ok(client.get(BASE+'/'+folder['id'],params=SCOPE))['can_write']
            assert command(client,folder,'COMMENT',note='开关关闭').status_code == 403
            assert add(client,folder).status_code == 403
        assert client.post(BASE,params=SCOPE,json=dict(target=target,request_id=uuid4().hex)).status_code == 403
        assert _manual_contract(client,'DISABLED-NEW').status_code == 403
        root_id = ok(client.get(BASE+'/'+old['id'],params=SCOPE))['contract_folder_id']
        assert client.post(BASE+'/contracts/'+root_id+'/mappings',params=SCOPE,
            json=dict(target=target,folder_id=old['id'],revision=1,request_id=uuid4().hex)).status_code == 403
        assert _audit_total() == before
        assert client.get(BASE+f"/{old['id']}/versions/{old['versions'][0]['id']}/document",params=SCOPE).content == content
        assert ok(client.post(BASE+'/statuses',params=SCOPE,json={'targets':[target]}))['items'][0]['folder_id']==state['id']
        monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','true')
        assert ok(command(client,state,'COMMENT',note='重新开启后保存'))['revision']==state['revision']+1


def test_slice2_concurrent_contract_creates_are_serialized_and_idempotent(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    with make_client(monkeypatch) as client:
        setup(client)
        customer = _customer_id()
        requests = ['same-concurrent-request','same-concurrent-request',uuid4().hex,uuid4().hex]
        barrier = Barrier(4)
        def create(request_id):
            peer = TestClient(client.app)
            peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=15)
                return peer.post(BASE+'/contracts',params=SCOPE,
                    json=dict(contract=dict(customer_id=customer,contract_no='000-CONCURRENT'),request_id=request_id))
            finally: peer.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(create,requests))
        values = [ok(response) for response in responses]
        assert len({value['id'] for value in values})==1
        identifier = values[0]['id']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from app.services import carton_materials as service
        from sqlalchemy import select
        with SessionLocal() as db:
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id==identifier)))
            assert sum(e.entity_type==service.ENTITY for e in events)==1
            assert sum(json.loads(e.detail_json)['action']=='REGISTER_CONTRACT' for e in events)==1
        before = _audit_total()
        different = client.post(BASE+'/contracts',params=SCOPE,
            json=dict(contract=dict(customer_id=customer,contract_no='OTHER-CONTRACT'),request_id=requests[0]))
        assert different.status_code==409 and _audit_total()==before


def test_slice2_authority_selector_and_changed_source_cannot_bypass_mapping(monkeypatch):
    with make_client(monkeypatch) as client:
        first,_=setup(client)
        other=ok(_manual_contract(client,'UNRELATED-CONTRACT'))
        body=dict(authority_id=first['id'],revision=first['revision'],request_id=uuid4().hex,action='COMMENT',note='选择具体订单')
        before=_audit_total()
        for identifier in (other['id'],first['id'], 'CMF2-nonexistent'):
            selected=other['id'] if identifier==first['id'] else first['id']
            assert client.post(BASE+'/'+identifier+'/actions',params=SCOPE,json={**body,'authority_id':selected}).status_code==404
        assert _audit_total()==before
        changed=ok(client.post(BASE+'/'+first['contract_folder_id']+'/actions',params=SCOPE,json=body))
        assert changed['id']==first['id'] and changed['revision']==first['revision']+1
        assert ok(client.get(BASE+'/'+other['id'],params=SCOPE))['revision']==other['revision']
        old,_=_seed_legacy(first,'SOURCE-IDENTITY')
        from test_carton_procurement_api import _order_payload
        order=ok(client.post('/api/carton-procurement/orders',json={**_order_payload(),
            'contract_no':old['contract_no'],'item_no':old['item_no'],'customer_po':old['po']}),201)
        scope={**SCOPE,'audience':'warehouse'}
        request=dict(target=dict(kind='PURCHASE',id=order['id']),request_id=uuid4().hex)
        linked=ok(client.post(BASE,params=scope,json=request))
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            db.get(CartonOrder,order['id']).customer_po='CHANGED-PO'
            db.commit()
        before=_audit_total()
        assert client.post(BASE,params=scope,json=request).status_code==409
        assert client.post(BASE,params=scope,json={**request,'request_id':uuid4().hex}).status_code==409
        assert command(client,linked,'COMMENT',note='旧URL也必须拦截').status_code==409
        assert add(client,linked,text='不可绕过').status_code==409
        history=ok(client.get(BASE+'/'+old['id'],params=SCOPE))
        assert history['versions']==old['versions'] and history['approval']==old['approval']
        assert not history['can_write'] and history['mapping_status']=='REVIEW'
        status=ok(client.post(BASE+'/statuses',params=scope,json={'targets':[request['target']]}))['items'][0]
        assert not status['ready'] and not status['folder_id']
        summary=ok(client.get(BASE+'/contracts/'+linked['contract_folder_id'],params=SCOPE))
        assert summary['authorities'][0]['mapping_status']=='REVIEW'
        assert _audit_total()==before


def test_slice2_stable_customer_key_and_gate_rechecked_after_worker(monkeypatch):
    with make_client(monkeypatch) as client:
        first,_=setup(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        from app.models.carton_mark import CartonMarkAsset
        from sqlalchemy import select,func
        customer_id=_customer_id()
        with SessionLocal() as db:
            customer=db.get(CartonCustomer,customer_id)
            customer.customer_name='改名后客户'
            second=CartonCustomer(id='synthetic-other-customer',factory_id='huaxing',customer_code='OTHER-CUSTOMER',
                customer_name='不同稳定客户',created_by=customer.created_by,updated_by=customer.updated_by,
                created_at=customer.created_at,updated_at=customer.updated_at)
            db.add(second); db.flush(); second_id=second.id; db.commit()
        assert ok(_manual_contract(client,first['contract_no']))['id']==first['contract_folder_id']
        other=ok(client.post(BASE+'/contracts',params=SCOPE,json=dict(
            contract=dict(customer_id=second_id,contract_no=first['contract_no']),request_id=uuid4().hex)))
        assert other['id']!=first['contract_folder_id']
        from app.api import carton_materials as api
        async def worker(function,*args,**kwargs):
            monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
            return dict(file_name='scan.pdf',content=b'%PDF-test',kind='pdf',content_type='application/pdf',sha256='hash')
        monkeypatch.setattr(api,'run_order_job',worker)
        before=_audit_total()
        response=client.post(BASE+'/'+first['id']+'/versions',params=SCOPE,
            data={'metadata':json.dumps(dict(revision=first['revision'],request_id=uuid4().hex))},files={'file':('scan.pdf',b'%PDF-test')})
        assert response.status_code==403 and _audit_total()==before
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset).where(CartonMarkAsset.recognition_source=='materials_folder'))==0


def test_slice2_old_url_cannot_bypass_duplicate_schedule_or_parallel_authority(monkeypatch):
    with make_client(monkeypatch) as client:
        base,_=setup(client)
        parallel,_=_seed_legacy(base,base['contract_no'],base['item_no'],base['po'])
        before=_audit_total()
        assert command(client,parallel,'COMMENT',note='双权威不能从旧链接写入').status_code==409
        assert not ok(client.get(BASE+'/'+parallel['id'],params=SCOPE))['can_write']
        assert _audit_total()==before
        old,_=_seed_legacy(base,'LEGACY-SCHEDULE-DUP',item='DUP-ITEM',po='DUP-PO')
        row=source_row(contract=old['contract_no'],item=old['item_no'])
        row[3]=old['po']
        ok(client.post('/api/carton-procurement/weekly-imports',params={'factory_id':'huaxing'},data={'customer_code':'DICKIE'},
            files={'file':('duplicate.xlsx',workbook([row,row]))}),201)
        before=_audit_total()
        history=ok(client.get(BASE+'/'+old['id'],params=SCOPE))
        assert history['mapping_status']=='REVIEW' and not history['can_write']
        assert command(client,old,'COMMENT',note='旧排期重复也必须核对').status_code==422
        assert _audit_total()==before


def test_slice2_status_100_uses_bounded_indexed_reads_and_never_registers(monkeypatch):
    import copy
    import os
    from pathlib import Path
    from sqlalchemy import select,event
    with make_client(monkeypatch) as client:
        base,_ = setup(client)
        from app.db import SessionLocal,engine
        from app.models.customer_order_ledger import OrderLedgerLine
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services import carton_materials as service
        from app.services import carton_materials_resolver as resolver
        targets=[]
        customer_id=_customer_id()
        with SessionLocal() as db:
            actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            for i in range(100):
                identifier=f'status-ledger-{i:03d}'
                db.add(OrderLedgerLine(id=identifier,factory_id='huaxing',customer_code='dickie',customer_name='Dickie',
                    identity_key='status-identity-'+str(i),reference_no='P-'+str(i),product_no='I-'+str(i),quantity=1,shipped_quantity=0,
                    data={'contract_no':'STATUS-BATCH','reference_no':'P-'+str(i)},created_at='2026-10-28',updated_at='2026-10-28'))
                state=copy.deepcopy(base)
                state.update(contract_no='STATUS-BATCH',item_no='I-'+str(i),po='P-'+str(i))
                root=resolver.contract_id('huaxing',customer_id,'STATUS-BATCH')
                state['contract_folder_id']=root
                state['id']=resolver.context_id(root,state)
                service.append(db,actor,'huaxing',state['id'],state,'STATUS_FIXTURE',uuid4().hex,'synthetic')
                targets.append(dict(kind='LEDGER',id=identifier))
            db.commit()
        def forbidden(*args,**kwargs): raise AssertionError('A row-status read must not scan all folders or discover legacy contracts')
        compatibility_lookup=service.folders
        monkeypatch.setattr(service,'folders',forbidden)
        monkeypatch.setattr(resolver,'legacy_rows',forbidden)
        statements=[]
        def trace(conn,cursor,sql,params,context,executemany):
            if 'carton_audit_events' in sql and sql.lstrip().startswith('SELECT'): statements.append((sql,params))
        before=_audit_total()
        event.listen(engine,'before_cursor_execute',trace)
        try: result=ok(client.post(BASE+'/statuses',params=SCOPE,json={'targets':targets}))
        finally: event.remove(engine,'before_cursor_execute',trace)
        assert len(result['items'])==100 and all(row['folder_id'].startswith('CMO-') for row in result['items'])
        assert _audit_total()==before
        assert len(statements)<=4
        assert all('entity_id IN' in sql for sql,_ in statements)
        evidence=[]
        with engine.connect() as connection:
            for sql,params in statements:
                plan=connection.exec_driver_sql('EXPLAIN QUERY PLAN '+sql,params).all()
                assert any('ix_carton_audit_entity' in str(row) for row in plan)
                evidence.append(dict(sql=sql,parameters=list(params),plan=[list(row) for row in plan]))
        compatibility=[]
        def trace_compatibility(conn,cursor,sql,params,context,executemany):
            if 'carton_audit_events' in sql and sql.lstrip().startswith('SELECT'): compatibility.append(sql)
        event.listen(engine,'before_cursor_execute',trace_compatibility)
        try:
            with SessionLocal() as db:
                lookup=compatibility_lookup(db,'huaxing')
                assert base['id'] in lookup and lookup[base['id']]['id']==base['id']
        finally: event.remove(engine,'before_cursor_execute',trace_compatibility)
        assert len(compatibility)==1 and 'entity_id IN' in compatibility[0]
        output=os.environ.get('CARTON_SLICE2_EVIDENCE_DIR')
        if output:
            path=Path(output).resolve()
            assert path.is_relative_to(Path(__file__).resolve().parents[2]/'outputs')
            path.mkdir(parents=True,exist_ok=True)
            (path/'row-status-query.json').write_text(json.dumps(dict(requested=100,audit_queries=len(statements),queries=evidence,
                compatibility_key_queries=len(compatibility)),ensure_ascii=False,indent=2),encoding='utf-8')


def _slice3_contexts(client,count=3):
    """Real ledger adapters and API-created contexts; synthetic test DB only."""
    _prepare_schedule_customer(client)
    login_as(client,'admin')
    from app.db import SessionLocal
    from app.models.customer_order_ledger import OrderLedgerLine
    ids=['share-ledger-'+str(i) for i in range(count)]
    with SessionLocal() as db:
        for i,identifier in enumerate(ids):
            db.add(OrderLedgerLine(id=identifier,factory_id='huaxing',customer_code='dickie',customer_name='Dickie',
                identity_key=identifier,reference_no='PO-'+str(i),product_no='ITEM-'+str(i),quantity=1,shipped_quantity=0,
                data={'contract_no':'SHARE-'+str(i),'reference_no':'PO-'+str(i)},created_at='2026-10-28',updated_at='2026-10-28'))
        db.commit()
    values=[]
    for identifier in ids:
        value=ok(client.post(BASE,params=SCOPE,json=dict(target=dict(kind='LEDGER',id=identifier),request_id=uuid4().hex)))
        values.append(ok(command(client,value,'RULE',mode='INTERNAL')))
    return values


def _current(client,state,audience='sales'):
    return ok(client.get(BASE+'/'+state['id'],params={**SCOPE,'audience':audience}))


def _ref_body(source,version,targets,request_id=None):
    return dict(source_context_id=source['id'],version_id=version,
        targets=[dict(context_id=t['id'],revision=t['revision']) for t in targets],request_id=request_id or uuid4().hex)


def _synthetic_pdf():
    from pypdf import PdfWriter
    stream=BytesIO(); writer=PdfWriter(); writer.add_blank_page(300,200); writer.write(stream)
    return stream.getvalue()


def _slice3_counts():
    from app.db import SessionLocal
    from app.models.carton_materials import CartonMaterialReference
    from app.models.carton_mark import CartonMarkAsset
    from sqlalchemy import select,func
    with SessionLocal() as db:
        return (_audit_total(),db.scalar(select(func.count()).select_from(CartonMaterialReference)),
                db.scalar(select(func.count()).select_from(CartonMarkAsset).where(CartonMarkAsset.recognition_source=='materials_folder')))


def test_slice3a_upload_many_one_file_and_independent_confirmations(monkeypatch):
    with make_client(monkeypatch) as client:
        a,b,c=_slice3_contexts(client)
        content=_synthetic_pdf()
        body=dict(revision=a['revision'],request_id=uuid4().hex,text='原稿文字',targets=[
            dict(context_id=t['id'],revision=t['revision']) for t in (b,c)])
        url=BASE+'/'+a['id']+'/versions-and-references'
        before=_slice3_counts()
        assert client.post(url,params=SCOPE,data={'metadata':json.dumps({**body,'targets':[]})},files={'file':('original.pdf',content)}).status_code==422
        assert _slice3_counts()==before
        result=ok(client.post(url,params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',content)}))
        version=result['version_id']
        assert len(set(result['reference_ids']))==2
        before=_slice3_counts()
        assert ok(client.post(url,params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',content)}))==result
        assert _slice3_counts()==before and before[1:]==(2,1)
        a,b,c=[_current(client,t) for t in (a,b,c)]
        assert all(t['versions'][0]['id']==version for t in (a,b,c))
        assert not b['approval'] and not c['approved_version_ids']
        a=ok(command(client,a,'APPROVE',note='仅确认 A',version_ids=[version]))
        assert not _current(client,b)['approval']
        b=ok(command(client,b,'APPROVE',note='B 自己核对',version_ids=[version]))
        a=ok(add(client,a,text='A 的新稿不传播',previous_id=version))
        b=_current(client,b)
        assert b['status']=='READY' and b['approved_version_ids']==[version] and len(b['versions'])==1
        assert client.get(BASE+f"/{b['id']}/versions/{version}/document",params=SCOPE).content==content
        new_version=a['versions'][-1]['id']
        ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,new_version,[c])))
        assert _current(client,c)['versions'][-1]['id']==new_version
        assert _current(client,b)['approved_version_ids']==[version]
        from app.db import SessionLocal
        from app.services import carton_materials as service
        with SessionLocal() as db:
            pointer=service.get(db,'huaxing',b['id'])['versions'][0]
            assert pointer['is_reference'] and 'text' not in pointer and 'asset_id' not in pointer
        assert ok(client.get(BASE+'/capabilities',params=SCOPE))['batch_approval'] is True


def test_slice3a_concurrent_text_adoption_detach_and_reuse(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    with make_client(monkeypatch) as client:
        a,b,_=_slice3_contexts(client)
        a=ok(add(client,a,text='纯文字不可变版本'))
        version=a['versions'][-1]['id']; barrier=Barrier(4)
        body=_ref_body(a,version,[b],request_id='shared-text-concurrent')
        def adopt(index):
            peer=TestClient(client.app); peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=15)
                return peer.post(BASE+'/references',params=SCOPE,json={**body,'request_id':body['request_id'] if index<2 else uuid4().hex})
            finally: peer.close()
        with ThreadPoolExecutor(max_workers=4) as pool: results=[ok(r) for r in pool.map(adopt,range(4))]
        ref=results[0]['reference_ids'][0]
        assert all(r['reference_ids']==[ref] for r in results) and _slice3_counts()[1:]==(1,0)
        before=_slice3_counts()
        ok(client.post(BASE+'/references',params=SCOPE,json=body))
        assert _slice3_counts()==before
        assert client.post(BASE+'/references',params=SCOPE,json={**body,'version_id':'changed'}).status_code in {404,409}
        assert _slice3_counts()==before
        b=_current(client,b)
        assert b['revision']==3 and b['versions'][0]['text']=='纯文字不可变版本'
        assert not b['approval']
        b=ok(command(client,b,'APPROVE',note='B 单独确认',version_ids=[version]))
        removal=dict(revision=b['revision'],reference_revision=1,request_id=uuid4().hex)
        endpoint=BASE+f"/{b['id']}/references/{ref}/deactivate"
        ok(client.post(endpoint,params=SCOPE,json=removal))
        before=_slice3_counts()
        ok(client.post(endpoint,params=SCOPE,json=removal))
        assert _slice3_counts()==before
        b=_current(client,b)
        assert b['versions']==[] and not b['approval']
        assert client.get(BASE+f"/{b['id']}/versions/{version}/document",params=SCOPE).status_code==404
        assert command(client,b,'APPROVE',note='已解除不可确认',version_ids=[version]).status_code==422
        result=ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])))
        assert result['reference_ids']==[ref] and _slice3_counts()[1]==1
        b=_current(client,b)
        assert b['versions'][0]['reference_revision']==3 and not b['approval']
        monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
        before=_slice3_counts()
        assert client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])).status_code==403
        assert client.post(endpoint,params=SCOPE,json={**removal,'request_id':uuid4().hex}).status_code==403
        assert _current(client,b)['versions'][0]['text']=='纯文字不可变版本' and _slice3_counts()==before


def test_slice3a_upload_and_projection_roll_back_together(monkeypatch):
    import hashlib
    from fastapi import HTTPException
    with make_client(monkeypatch) as client:
        a,b,c=_slice3_contexts(client)
        from app.api import carton_materials as api
        from app.services import carton_material_references as references
        async def worker(function,*args,**kwargs):
            content=b'%PDF-synthetic-worker-result'
            return dict(file_name='original.pdf',content=content,kind='pdf',content_type='application/pdf',sha256=hashlib.sha256(content).hexdigest())
        monkeypatch.setattr(api,'run_order_job',worker)
        before=_slice3_counts()
        body=dict(revision=a['revision'],request_id=uuid4().hex,targets=[
            dict(context_id=b['id'],revision=b['revision']),dict(context_id=c['id'],revision=1)])
        url=BASE+'/'+a['id']+'/versions-and-references'
        assert client.post(url,params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',b'%PDF-test')}).status_code==409
        assert _slice3_counts()==before and _current(client,a)['versions']==[] and _current(client,b)['versions']==[]
        original=references.write_projection; writes=0
        def fail_after_projection(*args,**kwargs):
            nonlocal writes
            original(*args,**kwargs); writes+=1
            if writes==2: raise HTTPException(409,'故障注入：第二条投影写入后失败')
        monkeypatch.setattr(references,'write_projection',fail_after_projection)
        body.update(request_id=uuid4().hex,targets=[dict(context_id=t['id'],revision=t['revision']) for t in (b,c)])
        assert client.post(url,params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',b'%PDF-test')}).status_code==409
        assert writes==2 and _slice3_counts()==before
        assert all(_current(client,t)['versions']==[] for t in (a,b,c))
        monkeypatch.setattr(references,'write_projection',original)
        ok(client.post(url,params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',b'%PDF-test')}))
        assert _slice3_counts()[1:]==(2,1)


def test_slice3a_supplier_target_survives_source_archive_and_hides_lineage(monkeypatch):
    with make_client(monkeypatch) as client:
        a,b,c=_slice3_contexts(client)
        from test_carton_supplier_portal import setup_portal,supplier_login
        setup_portal(client); login_as(client,'admin')
        supplier=ok(client.get(BASE+'/options',params=SCOPE))['suppliers'][0]['id']
        b=ok(command(client,b,'RULE',mode='INTERNAL',supplier_id=supplier))
        c=ok(command(client,c,'RULE',mode='INTERNAL',supplier_id=supplier))
        content=_synthetic_pdf()
        a=ok(client.post(BASE+'/'+a['id']+'/versions',params=SCOPE,
            data={'metadata':json.dumps(dict(revision=a['revision'],request_id=uuid4().hex))},files={'file':('original.pdf',content)}))
        version=a['versions'][-1]['id']
        result=ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])))
        b=_current(client,b)
        a=ok(add(client,a,text='客户私密邮件',role='EVIDENCE'))
        secret=a['versions'][-1]['id']
        secret_result=ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,secret,[b])))
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_mark import CartonMarkAsset
        from app.services.auth import build_auth_context
        from app.services import carton_materials as service
        from sqlalchemy import select
        with SessionLocal() as db:
            actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            db.get(CartonMarkAsset,a['versions'][0]['asset_id']).is_archived=True
            hidden=service.get(db,'huaxing',a['id']); hidden['hidden']=True; hidden['revision']+=1
            service.append(db,actor,'huaxing',a['id'],hidden,'SYNTHETIC_HIDE',uuid4().hex,'fixture')
            foreign=service.get(db,'huaxing',c['id']); foreign['supplier_id']='OTHER-SUPPLIER'; foreign['revision']+=1
            service.append(db,actor,'huaxing',c['id'],foreign,'SYNTHETIC_OTHER_RECIPIENT',uuid4().hex,'fixture')
            db.commit()
        assert client.get(BASE+f"/{a['id']}/versions/{version}/document",params=SCOPE).status_code==404
        supplier_login(client)
        scope={**SCOPE,'audience':'supplier'}
        assert client.get(BASE+'/'+a['id'],params=scope).status_code==404
        visible=ok(client.get(BASE+'/'+b['id'],params=scope))
        shared=next(v for v in visible['versions'] if v['id']==version)
        assert not shared['source_visible'] and 'source' not in shared and 'by' not in shared and 'previous_id' not in shared
        assert secret not in [v['id'] for v in visible['versions']]
        assert client.get(BASE+f"/{b['id']}/versions/{version}/document",params=scope).content==content
        assert client.get(BASE+f"/{b['id']}/versions/{secret}/document",params=scope).status_code==404
        assert client.post(BASE+f"/{b['id']}/references/{secret_result['reference_ids'][0]}/deactivate",params=scope,
            json=dict(revision=visible['revision'],reference_revision=1,request_id=uuid4().hex)).status_code==404
        assert client.get(BASE+f"/{c['id']}/versions/{version}/document",params=scope).status_code==404
        before=_slice3_counts()
        assert client.post(BASE+'/references',params=scope,json=_ref_body(b,version,[c])).status_code==404
        assert client.post(BASE+'/references',params=scope,json=_ref_body(a,version,[b])).status_code==404
        assert client.post(BASE+'/references',params=scope,json=_ref_body(b,secret,[c])).status_code==404
        assert _slice3_counts()==before
        assert client.get('/api/carton-procurement/audit-events/'+_reference_audit_id(result['reference_ids'][0]),params={'factory_id':'huaxing'}).status_code in {403,404}
        monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
        assert client.get(BASE+f"/{b['id']}/versions/{version}/document",params=scope).content==content
        with SessionLocal() as db:
            db.get(CartonMarkAsset,a['versions'][0]['asset_id']).content=b'tampered-synthetic-bytes'
            db.commit()
        assert client.get(BASE+f"/{b['id']}/versions/{version}/document",params=scope).status_code==404


def _reference_audit_id(reference_id):
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonAuditEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        return db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.entity_id==reference_id))


def test_slice3a_customer_factory_permissions_and_worker_revalidation(monkeypatch):
    import copy
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        a,b,_=_slice3_contexts(client)
        a=ok(add(client,a,text='不得跨客户'))
        version=a['versions'][-1]['id']
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonCustomer
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.services.auth import build_auth_context
        from app.services import carton_materials as service
        from app.services.carton_materials_resolver import contract_id,context_id
        with SessionLocal() as db:
            customer=db.get(CartonCustomer,_customer_id())
            other=CartonCustomer(id='other-share-customer',factory_id='huaxing',customer_code='OTHER-SHARE',customer_name='另一客户',
                created_by=customer.created_by,updated_by=customer.updated_by,created_at=customer.created_at,updated_at=customer.updated_at)
            db.add(other)
            actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            foreign=copy.deepcopy(service.get(db,'huaxing',b['id']))
            foreign.update(customer_id=other.id,customer_code=other.customer_code,customer_name=other.customer_name)
            foreign['contract_folder_id']=contract_id('huaxing',other.id,foreign['contract_no'])
            foreign['id']=context_id(foreign['contract_folder_id'],foreign)
            service.append(db,actor,'huaxing',foreign['id'],foreign,'SYNTHETIC_CUSTOMER_BOUNDARY',uuid4().hex,'fixture')
            db.add(CartonCustomerAssignment(factory_id='huaxing',customer_id=customer.id,user_id=actor.id))
            db.commit()
        before=_slice3_counts()
        assert client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[foreign])).status_code==422
        assert client.post(BASE+'/references',params={**SCOPE,'factory_id':'huakang-a'},json=_ref_body(a,version,[b])).status_code in {403,404}
        assert _slice3_counts()==before
        from test_molding_sample_api import grant_permission_override
        for permission in ('carton_mark:read','carton_mark:template_upload'):
            grant_permission_override('qc_inspector',permission,factory_id='huaxing',department='pmc-warehouse')
        login_as(client,'qc_inspector')
        assert client.post(BASE+'/references',params={**SCOPE,'audience':'warehouse'},json=_ref_body(a,version,[b])).status_code==403
        assert _slice3_counts()==before
        login_as(client,'admin')
        from app.api import carton_materials as api
        async def worker(function,*args,**kwargs):
            monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
            return dict(file_name='original.pdf',content=b'%PDF-test',kind='pdf',content_type='application/pdf',sha256='hash')
        monkeypatch.setattr(api,'run_order_job',worker)
        body=dict(revision=a['revision'],request_id=uuid4().hex,targets=[dict(context_id=b['id'],revision=b['revision'])])
        response=client.post(BASE+'/'+a['id']+'/versions-and-references',params=SCOPE,data={'metadata':json.dumps(body)},files={'file':('original.pdf',b'%PDF-test')})
        assert response.status_code==403 and _slice3_counts()==before


def test_slice3a_projection_rebuild_cli_repeat_and_conflict_fail_closed(monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    from fastapi import HTTPException
    from sqlalchemy import delete,select
    with make_client(monkeypatch) as client:
        a,b,_=_slice3_contexts(client)
        a=ok(add(client,a,text='重建仍是同一不可变文字'))
        version=a['versions'][-1]['id']
        result=ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])))
        reference=result['reference_ids'][0]
        b=_current(client,b)
        ok(client.post(BASE+f"/{b['id']}/references/{reference}/deactivate",params=SCOPE,json=dict(
            revision=b['revision'],reference_revision=1,request_id=uuid4().hex)))
        b=_current(client,b)
        ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])))
        from app.db import SessionLocal,engine
        from app.models.carton_materials import CartonMaterialReference as Reference
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services import carton_material_references as references,carton_materials as service
        def snapshot():
            with SessionLocal() as db:
                row=db.get(Reference,('huaxing',reference))
                return {key:getattr(row,key) for key in references.FIELDS}
        expected=snapshot(); before=_audit_total()
        with SessionLocal() as db:
            db.execute(delete(Reference).where(Reference.factory_id=='huaxing')); db.commit()
        assert _current(client,b)['versions']==[]
        commandline=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/rebuild_carton_material_references.py'),
            '--database-url',engine.url.render_as_string(hide_password=False),'--factory','huaxing']
        dry=subprocess.run(commandline,capture_output=True,text=True,timeout=60,check=True)
        summary=json.loads(dry.stdout)
        assert summary==dict(factory_id='huaxing',events=3,rows=1,skipped=0,conflicts=0,applied=False)
        rebuilt=json.loads(subprocess.run(commandline+['--apply'],capture_output=True,text=True,timeout=60,check=True).stdout)
        assert rebuilt['applied'] and snapshot()==expected and _audit_total()==before
        subprocess.run(commandline+['--apply'],capture_output=True,text=True,timeout=60,check=True)
        assert snapshot()==expected and _current(client,b)['versions'][0]['text']=='重建仍是同一不可变文字'
        with SessionLocal() as db:
            actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            event=db.scalar(select(service.CartonAuditEvent).where(service.CartonAuditEvent.entity_id==reference).order_by(service.CartonAuditEvent.sequence))
            bad=json.loads(event.detail_json)['state']; bad['revision']=99
            service.append(db,actor,'huaxing',reference,bad,'REFERENCE_LINK',uuid4().hex,'synthetic-conflict',service.REQUESTS)
            db.commit()
        with SessionLocal() as db:
            report=references.rebuild(db,'huaxing')
            assert report['conflicts']==1 and report['skipped']==0
            with pytest.raises(HTTPException) as error: references.rebuild(db,'huaxing',apply=True)
            assert error.value.status_code==409
            db.rollback()
        assert snapshot()==expected
        _slice3_evidence('rebuild.json',dict(dry_run=summary,applied=rebuilt,conflicting=report,projection=expected))


def _slice3_evidence(name,value):
    import os
    from pathlib import Path
    destination=os.environ.get('CARTON_SLICE3_EVIDENCE_DIR')
    if not destination: return
    path=Path(destination).resolve()
    assert path.is_relative_to(Path(__file__).resolve().parents[2]/'outputs')
    path.mkdir(parents=True,exist_ok=True)
    (path/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def test_slice3a_migration_sqlite_postgresql_ddl_and_no_legacy_backfill(tmp_path):
    import importlib.util
    from pathlib import Path
    from io import StringIO
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine,inspect,text
    path=Path(__file__).parents[1]/'alembic/versions/20261028_0185_carton_material_references.py'
    spec=importlib.util.spec_from_file_location('reference_migration',path)
    migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.sqlite3'))
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE legacy_original (id TEXT PRIMARY KEY, approval TEXT)')
        connection.exec_driver_sql("INSERT INTO legacy_original VALUES ('CMF-original','immutable approval')")
        migration.op=Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        inspector=inspect(connection)
        columns={c['name'] for c in inspector.get_columns('carton_material_references')}
        assert columns=={'factory_id','customer_id','reference_id','version_id','source_context_id','source_order_key',
            'target_context_id','target_order_key','contract_id','active','revision','origin_event_sequence','last_event_sequence'}
        assert set(inspector.get_table_names())=={'legacy_original','carton_material_references'}
        assert connection.scalar(text('SELECT count(*) FROM carton_material_references'))==0
        assert connection.scalar(text('SELECT approval FROM legacy_original'))=='immutable approval'
        assert inspector.get_pk_constraint('carton_material_references')['constrained_columns']==['factory_id','reference_id']
        assert len(inspector.get_indexes('carton_material_references'))==2
        with pytest.raises(RuntimeError,match='disable writes'): migration.downgrade()
    for dialect in ('sqlite','postgresql'):
        buffer=StringIO()
        migration.op=Operations(MigrationContext.configure(dialect_name=dialect,opts={'as_sql':True,'output_buffer':buffer}))
        migration.upgrade()
        ddl=buffer.getvalue()
        assert ddl.count('CREATE TABLE ')==1 and 'PRIMARY KEY (factory_id, reference_id)' in ddl
        assert 'UNIQUE (factory_id, target_context_id, version_id)' in ddl
        _slice3_evidence(dialect+'-ddl.json',dict(dialect=dialect,ddl=ddl,runtime_verified=dialect=='sqlite'))


def test_slice3a_reverse_and_download_queries_use_projection_indexes(monkeypatch):
    import copy
    from sqlalchemy import event,select,insert
    with make_client(monkeypatch) as client:
        a,b,_=_slice3_contexts(client)
        from app.db import SessionLocal,engine
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonAuditEvent
        from app.models.carton_materials import CartonMaterialReference as Reference
        from app.services.auth import build_auth_context
        from app.services import carton_materials as service
        from app.services.carton_materials_resolver import context_id
        from app.services.carton_material_references import FIELDS
        targets=[b]
        with SessionLocal() as db:
            actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            template=service.get(db,'huaxing',b['id'])
            for i in range(99):
                value=copy.deepcopy(template); value.update(item_no='PERF-'+str(i),po='P-'+str(i))
                value['id']=context_id(value['contract_folder_id'],value)
                service.append(db,actor,'huaxing',value['id'],value,'SYNTHETIC_PERF_TARGET',uuid4().hex,'fixture')
                targets.append(value)
            db.commit()
        content=_synthetic_pdf()
        body=dict(revision=a['revision'],request_id=uuid4().hex,targets=[dict(context_id=t['id'],revision=t['revision']) for t in targets])
        response=ok(client.post(BASE+'/'+a['id']+'/versions-and-references',params=SCOPE,
            data={'metadata':json.dumps(body)},files={'file':('original.pdf',content)}))
        version=response['version_id']
        with SessionLocal() as db:
            example=db.scalar(select(Reference).where(Reference.version_id==version))
            template={key:getattr(example,key) for key in FIELDS}
            rows=[]; history=[]
            for i in range(5000):
                rows.append({**template,'reference_id':'noise-ref-'+str(i),'version_id':'noise-version',
                    'source_context_id':'noise-source','source_order_key':'noise-source','target_context_id':'noise-target-'+str(i),
                    'target_order_key':'noise-target-'+str(i)})
                history.append(dict(id='noise-audit-'+str(i),factory_id='huaxing',event_type=service.EVENT,
                    entity_type=service.REQUESTS,entity_id='CMREF-noise-'+str(i),detail_json='{}',actor_user_id=actor.id,
                    actor_name='synthetic',created_at=service.now()))
            db.execute(insert(Reference),rows); db.execute(insert(CartonAuditEvent),history); db.commit()
        statements=[]; audit_sql=[]
        def trace(conn,cursor,sql,params,context,executemany):
            if not sql.lstrip().startswith('SELECT'): return
            if 'carton_material_references' in sql: statements.append((sql,params))
            if 'carton_audit_events' in sql: audit_sql.append(sql)
        event.listen(engine,'before_cursor_execute',trace)
        try:
            by_version=ok(client.get(BASE+'/references',params={**SCOPE,'source_context_id':a['id'],'version_id':version,'limit':100}))
            by_source=ok(client.get(BASE+'/references',params={**SCOPE,'source_context_id':a['id'],'limit':100}))
            download=client.get(BASE+f"/{b['id']}/versions/{version}/document",params=SCOPE)
        finally: event.remove(engine,'before_cursor_execute',trace)
        assert len(by_version['items'])==len(by_source['items'])==100
        assert download.status_code==200 and download.content==content
        assert len(statements)==3
        assert not any(' LIKE ' in sql for sql in audit_sql)  # No reference-history replay.
        evidence=[]
        with engine.connect() as connection:
            for index,(sql,params) in enumerate(statements):
                plan=connection.exec_driver_sql('EXPLAIN QUERY PLAN '+sql,params).all()
                expected=('ix_carton_material_ref_version','ix_carton_material_ref_source','sqlite_autoindex_carton_material_references_2')[index]
                assert any(expected in str(row) for row in plan),plan
                returned=len(connection.exec_driver_sql(sql,params).all())
                assert returned==(100,100,1)[index]
                evidence.append(dict(operation=('by_version','by_source','target_download')[index],sql=sql,
                    parameters=list(params),plan=[list(row) for row in plan],returned_rows=returned))
        _slice3_evidence('projection-queries.json',dict(projection_rows=5100,unrelated_reference_history=5000,
            selected_targets=100,queries=evidence,audit_queries_are_point_or_exact_context=True))


def test_slice3a_existing_store_requires_explicit_reference_migration(monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    with make_client(monkeypatch) as client:
        a,b,_=_slice3_contexts(client)
        a=ok(add(client,a,text='旧库读取保留'))
        version=a['versions'][0]['id']
        from app.db import engine,init_db
        # This engine is the helper's newly-created isolated SQLite test store.
        with engine.begin() as connection: connection.exec_driver_sql('DROP TABLE carton_material_references')
        init_db()
        assert not inspect(engine).has_table('carton_material_references')
        assert _current(client,a)['versions'][0]['text']=='旧库读取保留'
        assert not ok(client.get(BASE+'/capabilities',params=SCOPE))['reference_projection_ready']
        before=_audit_total()
        assert client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])).status_code==503
        assert _audit_total()==before
        path=Path(__file__).parents[1]/'alembic/versions/20261028_0185_carton_material_references.py'
        spec=importlib.util.spec_from_file_location('explicit_reference_migration',path)
        migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with engine.begin() as connection:
            migration.op=Operations(MigrationContext.configure(connection)); migration.upgrade()
        assert ok(client.get(BASE+'/capabilities',params=SCOPE))['reference_projection_ready']
        ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,version,[b])))


BATCH_URL=BASE+'/batch-approvals'


def _slice3b_dataset(client,count=100):
    """Real reference API + synthetic isolated native target authorities."""
    import copy
    from sqlalchemy import select
    a,b,template,untouched=_slice3_contexts(client,4)
    a=ok(add(client,a,text='批次引用甲稿'))
    b=ok(add(client,b,text='批次引用乙稿'))
    versions=[a['versions'][0]['id'],b['versions'][0]['id']]
    a=ok(command(client,a,'APPROVE',note='仅来源自己确认',version_ids=[versions[0]]))
    legacy,_=_seed_legacy(a,'BATCH-LEGACY-UNCHANGED')
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services import carton_materials as service
    from app.services.carton_materials_resolver import context_id
    targets=[template]
    with SessionLocal() as db:
        actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
        base=service.get(db,'huaxing',template['id'])
        for index in range(1,count):
            state=copy.deepcopy(base)
            state.update(item_no='BATCH-ITEM-'+str(index),po='BATCH-PO-'+str(index),
                         mode='CUSTOMER' if index%3==1 else 'INTERNAL')
            state['id']=context_id(state['contract_folder_id'],state)
            service.append(db,actor,'huaxing',state['id'],state,'SYNTHETIC_BATCH_TARGET',uuid4().hex,'fixture')
            targets.append(state)
        db.commit()
    ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(a,versions[0],targets)))
    with SessionLocal() as db: targets=[service.get(db,'huaxing',t['id']) for t in targets]
    ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(b,versions[1],targets)))
    with SessionLocal() as db: targets=[service.get(db,'huaxing',t['id']) for t in targets]
    return dict(targets=sorted(targets,key=lambda t:t['id']),versions=versions,sources=[a,b],untouched=[untouched,legacy])


def _slice3b_body(dataset,request_id=None):
    from app.db import SessionLocal
    from app.services import carton_materials as service
    with SessionLocal() as db:
        states=[service.get(db,'huaxing',row['id']) for row in dataset['targets']]
    return dict(request_id=request_id or uuid4().hex,targets=[dict(context_id=state['id'],revision=state['revision'],
        version_ids=list(dataset['versions']) if index%5==0 else [dataset['versions'][index%2]],
        note=f'第 {index+1} 单独立确认依据') for index,state in enumerate(states)])


def _slice3b_snapshot(dataset):
    from app.db import SessionLocal
    from app.models.carton_materials import CartonMaterialReference
    from app.services.carton_material_references import FIELDS
    from app.services import carton_materials as service
    from sqlalchemy import select
    with SessionLocal() as db:
        states=[service.get(db,'huaxing',row['id']) for row in dataset['targets']]
        untouched=[service.get(db,'huaxing',row['id']) for row in dataset['sources']+dataset['untouched']]
        rows=[{key:getattr(row,key) for key in FIELDS} for row in db.scalars(select(CartonMaterialReference).order_by(
            CartonMaterialReference.factory_id,CartonMaterialReference.reference_id))]
    return dict(states_hash=service.digest(states),untouched_hash=service.digest(untouched),projection_hash=service.digest(rows),
                revisions=[state['revision'] for state in states],ready=sum(state['status']=='READY' for state in states),
                counts=list(_slice3_counts()))


def _slice3b_attempt(dataset,label,invoke):
    import time
    from fastapi import HTTPException
    from sqlalchemy import event
    from app.db import engine
    before=_slice3b_snapshot(dataset); commits=[]; inserts=[]; auth_inserts=[]; business_started=False
    def committed(connection):
        nonlocal business_started
        commits.append(business_started); business_started=False
    def rolled_back(connection):
        nonlocal business_started
        business_started=False
    def trace(conn,cursor,sql,params,context,executemany):
        nonlocal business_started
        if sql.lstrip().startswith('INSERT INTO carton_audit_events'): inserts.append(True); business_started=True
        if sql.lstrip().startswith('INSERT INTO auth_audit_logs'): auth_inserts.append(True)
    event.listen(engine,'commit',committed); event.listen(engine,'rollback',rolled_back); event.listen(engine,'before_cursor_execute',trace)
    start=time.perf_counter()
    try:
        response=invoke()
        if hasattr(response,'status_code'): status=response.status_code; result=response.json()
        else: status=200; result=response
    except HTTPException as error: status=error.status_code; result={'detail':error.detail}
    finally:
        elapsed=(time.perf_counter()-start)*1000
        event.remove(engine,'commit',committed); event.remove(engine,'rollback',rolled_back); event.remove(engine,'before_cursor_execute',trace)
    after=_slice3b_snapshot(dataset)
    evidence=dict(case=label,status=status,real_commits=len(commits),business_commits=sum(commits),
        authorization_only_commits=sum(not value for value in commits),attempted_authorization_audits=len(auth_inserts),
        attempted_audit_inserts=len(inserts),
        changed_orders=sum(x!=y for x,y in zip(before['revisions'],after['revisions'])),
        carton_audit_delta=after['counts'][0]-before['counts'][0],identical_durable_snapshot=before==after,
        target_states_unchanged=before['states_hash']==after['states_hash'],
        untouched_unchanged=before['untouched_hash']==after['untouched_hash'],
        projection_unchanged=before['projection_hash']==after['projection_hash'],elapsed_ms=round(elapsed,3),before=before,after=after)
    assert evidence['untouched_unchanged'] and evidence['projection_unchanged']
    return evidence,result


def _slice3b_evidence(name,data):
    import os
    from pathlib import Path
    destination=os.environ.get('CARTON_SLICE3B_EVIDENCE_DIR')
    if not destination: return
    target=Path(destination).resolve()
    assert target.is_relative_to(Path(__file__).resolve().parents[2]/'outputs')
    target.mkdir(parents=True,exist_ok=True)
    (target/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def test_slice3b_100_success_receipt_and_new_request_do_not_reset_targets(monkeypatch):
    import copy
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        body=_slice3b_body(data)
        cases=[]
        evidence,result=_slice3b_attempt(data,'100_success',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        cases.append(evidence)
        assert evidence['status']==200 and evidence['real_commits']==1 and evidence['changed_orders']==100
        assert evidence['carton_audit_delta']==evidence['attempted_audit_inserts']==101 and evidence['after']['ready']==100
        assert result['count']==result['changed_count']==100 and not result['unchanged_count']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from app.services import carton_materials as service
        from app.services.carton_materials_batch import KIND
        with SessionLocal() as db:
            receipt=db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id==result['batch_receipt_id']))
            frozen=json.loads(receipt.detail_json)
            assert receipt.entity_type==service.REQUESTS and frozen['state']['kind']==KIND
            assert frozen['state']['actor_id']==result['actor_id']
            assert frozen['state']['result']==result
            for item,target in zip(result['items'],sorted(body['targets'],key=lambda t:t['context_id'])):
                state=service.get(db,'huaxing',item['context_id'])
                event=db.get(CartonAuditEvent,item['event_sequence']); payload=json.loads(event.detail_json)
                assert event.entity_id==state['id'] and payload['batch_receipt_id']==result['batch_receipt_id']
                assert state['approved_version_ids']==sorted(target['version_ids']) and state['approval']['note']==target['note']
                assert state['approval']['mode']==state['mode'] and payload['action']=='APPROVE'
            assert service.get(db,'huaxing',data['untouched'][-1]['id'])['approval']['note']=='旧确认依据'
        assert client.get('/api/carton-procurement/audit-events/'+receipt.id,params={'factory_id':'huaxing'}).status_code==404
        evidence,replayed=_slice3b_attempt(data,'same_request_retry',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        cases.append(evidence)
        assert replayed==result and evidence['identical_durable_snapshot'] and evidence['real_commits']==0
        reordered=copy.deepcopy(body); reordered['targets'].reverse()
        for target in reordered['targets']: target['version_ids'].reverse(); target['note']=' '+target['note']+' '
        evidence,replayed=_slice3b_attempt(data,'same_semantic_content_reordered',lambda:client.post(BATCH_URL,params=SCOPE,json=reordered))
        cases.append(evidence)
        assert replayed==result and evidence['identical_durable_snapshot'] and evidence['real_commits']==0
        changed=copy.deepcopy(body); changed['targets'][0]['note']='不同内容'
        evidence,_=_slice3b_attempt(data,'same_request_changed_note',lambda:client.post(BATCH_URL,params=SCOPE,json=changed))
        cases.append(evidence)
        assert evidence['status']==409 and evidence['identical_durable_snapshot'] and not evidence['real_commits']
        new=copy.deepcopy(body); new['request_id']=uuid4().hex
        for target in new['targets']: target['note']='不得覆盖原确认依据'
        evidence,no_change=_slice3b_attempt(data,'new_request_same_bundle',lambda:client.post(BATCH_URL,params=SCOPE,json=new))
        cases.append(evidence)
        assert no_change['changed_count']==0 and no_change['unchanged_count']==100
        assert evidence['target_states_unchanged'] and evidence['carton_audit_delta']==1
        target=_current(client,data['targets'][0])
        target=ok(add(client,target,text='目标后续新草稿仍需处理'))
        assert target['status']=='PROCESSING'
        new['request_id']=uuid4().hex
        evidence,no_change=_slice3b_attempt(data,'new_request_keeps_later_draft_processing',lambda:client.post(BATCH_URL,params=SCOPE,json=new))
        cases.append(evidence)
        assert no_change['changed_count']==0 and evidence['target_states_unchanged']
        assert _current(client,target)['status']=='PROCESSING'
        evidence,replayed=_slice3b_attempt(data,'historical_receipt_does_not_reapply',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        cases.append(evidence)
        assert replayed==result and evidence['identical_durable_snapshot'] and not evidence['real_commits']
        assert ok(client.get(BASE+'/capabilities',params=SCOPE))['batch_approval'] is True
        _slice3b_evidence('batch-100.json',dict(request=body,result=result,scenarios=cases))


def test_slice3b_all_validation_failures_leave_100_orders_unchanged(monkeypatch):
    import copy
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        cases=[]
        def rejected(label,body,status):
            evidence,_=_slice3b_attempt(data,label,lambda:client.post(BATCH_URL,params=SCOPE,json=body))
            cases.append(evidence)
            assert evidence['status']==status and evidence['identical_durable_snapshot']
            assert evidence['real_commits']==evidence['attempted_audit_inserts']==0
        body=_slice3b_body(data); body['targets'][-1]['revision']=999
        rejected('last_revision_conflict',body,409)
        body=_slice3b_body(data); body['targets'][-1]['version_ids']=['CMV-not-this-target']
        rejected('last_version_not_owned',body,422)
        body=_slice3b_body(data); body['targets'][-1]['note']='   '
        rejected('last_blank_basis',body,422)
        body=_slice3b_body(data); body['targets'][-1]['version_ids']*=2
        rejected('last_duplicate_version',body,422)
        body=_slice3b_body(data); body['targets'].append(copy.deepcopy(body['targets'][0]))
        rejected('over_100_targets',body,422)
        body=_slice3b_body(data); body['targets'][-1]=copy.deepcopy(body['targets'][0])
        rejected('duplicate_context',body,422)
        body=_slice3b_body(data); body['version_ids']=list(data['versions'])
        rejected('global_versions_forbidden',body,422)
        last=ok(add(client,_current(client,data['targets'][-1]),text='本单原件并非引用'))
        body=_slice3b_body(data); body['targets'][-1]['version_ids']=[last['versions'][-1]['id']]
        rejected('local_original_is_not_batch_reference',body,422)
        from app.db import SessionLocal
        from app.services.carton_material_references import lookup
        with SessionLocal() as db:
            row=lookup(db,'huaxing',last['id'],data['versions'][0]); reference=row.reference_id; revision=row.revision
        ok(client.post(BASE+f"/{last['id']}/references/{reference}/deactivate",params=SCOPE,json=dict(
            revision=last['revision'],reference_revision=revision,request_id=uuid4().hex)))
        body=_slice3b_body(data); body['targets'][-1]['version_ids']=[data['versions'][0]]
        rejected('last_reference_unlinked',body,422)
        body=_slice3b_body(data); legacy=data['untouched'][-1]
        body['targets'][-1]=dict(context_id=legacy['id'],revision=legacy['revision'],version_ids=[legacy['versions'][0]['id']],note='旧确认不扩散')
        rejected('legacy_local_confirmation_not_adopted',body,422)
        _slice3b_evidence('batch-validation-failures.json',cases)


def test_slice3b_failure_after_50_flushes_rolls_back_and_retries(monkeypatch):
    from fastapi import HTTPException
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        body=_slice3b_body(data)
        from app.services import carton_materials as service
        original=service.apply_approval; calls=0
        def fault(*args,**kwargs):
            nonlocal calls
            value=original(*args,**kwargs); calls+=1
            if calls==50: raise HTTPException(409,'故障注入：50 单实际 flush 后中止')
            return value
        def forbidden(*args,**kwargs): raise AssertionError('Batch must never call committing change()')
        monkeypatch.setattr(service,'change',forbidden)
        monkeypatch.setattr(service,'apply_approval',fault)
        failed,_=_slice3b_attempt(data,'failure_after_50_actual_flushes',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        assert failed['status']==409 and calls==50 and failed['identical_durable_snapshot'] and failed['real_commits']==0
        assert failed['attempted_audit_inserts']==50
        monkeypatch.setattr(service,'apply_approval',original)
        success,result=_slice3b_attempt(data,'retry_after_full_rollback',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        assert success['status']==200 and result['changed_count']==100 and success['real_commits']==1
        assert success['carton_audit_delta']==101 and success['changed_orders']==100
        _slice3b_evidence('batch-rollback.json',[failed,success])


def test_slice3b_revoked_cached_actor_and_replay_cannot_bypass_current_authority(monkeypatch):
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        login_as(client,'huaxing_molding_a_sales')
        body=_slice3b_body(data)
        from app.db import SessionLocal
        from app.models.auth import AuthUser,AuthUserPermissionOverride
        from app.services.auth import build_auth_context
        from app.schemas.carton_materials import BatchApproval
        from app.services.carton_materials_batch import approve
        from test_molding_sample_api import grant_permission_override
        with SessionLocal() as db:
            cached=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='huaxing_molding_a_sales')))
        def permissions(effect):
            for code in ('customer_order:write','customer_order:export'):
                grant_permission_override('huaxing_molding_a_sales',code,factory_id='huaxing',department='sales-business',effect='deny')
            with SessionLocal() as db:
                rows=list(db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id==cached.id,
                    AuthUserPermissionOverride.effect=='deny',AuthUserPermissionOverride.factory_id=='huaxing',
                    AuthUserPermissionOverride.department=='sales-business')))
                assert len(rows)==2
                for row in rows:
                    row.status='active' if effect=='deny' else 'revoked'
                    row.revoked_at='' if effect=='deny' else '2026-10-28T00:00:00'
                db.commit()
        permissions('deny')
        def stale_caller():
            with SessionLocal() as db:
                return approve(db,cached,'huaxing','sales',BatchApproval.model_validate(body),
                    lambda:build_auth_context(db,db.get(AuthUser,cached.id,populate_existing=True)))
        rejected,_=_slice3b_attempt(data,'cached_actor_permissions_revoked',stale_caller)
        assert rejected['status']==403 and rejected['identical_durable_snapshot'] and rejected['business_commits']==0
        assert not rejected['attempted_audit_inserts']
        permissions('allow')
        success,result=_slice3b_attempt(data,'same_request_after_authority_restored',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        assert success['status']==200 and result['changed_count']==100 and success['real_commits']==1
        assert result['actor_id']==cached.id
        permissions('deny')
        replay,_=_slice3b_attempt(data,'historical_receipt_after_permission_revocation',lambda:client.post(BATCH_URL,params=SCOPE,json=body))
        assert replay['status'] in {401,403} and replay['identical_durable_snapshot'] and not replay['business_commits']
        _slice3b_evidence('batch-revoked-authority.json',[rejected,success,replay])


def test_slice3b_each_customer_scope_customer_mode_supplier_and_switch(monkeypatch):
    import copy
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonCustomer
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.services.auth import build_auth_context
        from app.services import carton_materials as service
        from app.services.carton_materials_resolver import contract_id,context_id
        from test_molding_sample_api import grant_permission_override
        for code in ('carton_mark:read','carton_mark:template_upload'):
            grant_permission_override('qc_inspector',code,factory_id='huaxing',department='pmc-warehouse')
        with SessionLocal() as db:
            customer=db.get(CartonCustomer,_customer_id())
            admin=db.scalar(select(AuthUser).where(AuthUser.username=='admin'))
            warehouse=db.scalar(select(AuthUser).where(AuthUser.username=='qc_inspector'))
            other=CartonCustomer(id='batch-other-customer',factory_id='huaxing',customer_code='BATCH-OTHER',customer_name='其他责任客户',
                created_by=customer.created_by,updated_by=customer.updated_by,created_at=customer.created_at,updated_at=customer.updated_at)
            db.add(other)
            db.flush()  # Persist the new composite customer FK before responsibility rows.
            db.add(CartonCustomerAssignment(factory_id='huaxing',customer_id=customer.id,user_id=warehouse.id))
            db.add(CartonCustomerAssignment(factory_id='huaxing',customer_id=other.id,user_id=admin.id))
            actor=build_auth_context(db,admin)
            template=service.get(db,'huaxing',data['targets'][0]['id'])
            foreign=[]
            for suffix in ('SOURCE','TARGET'):
                value=copy.deepcopy(template)
                value.update(customer_id=other.id,customer_code=other.customer_code,customer_name=other.customer_name,
                    contract_no='BATCH-OTHER-'+suffix,mode='INTERNAL',versions=[],approval=None,approved_version_ids=[],revision=1,timeline=[])
                value['contract_folder_id']=contract_id('huaxing',other.id,value['contract_no'])
                value['id']=context_id(value['contract_folder_id'],value)
                if suffix=='SOURCE':
                    value['versions']=[dict(id='CMV-'+uuid4().hex,number=1,title='其他客户原稿',text='其他客户文字',role='WORKING',
                        asset_id='',sha256=service.digest('其他客户文字'),file_name='',previous_id='',by=admin.display_name,party='SALES',at=service.now())]
                service.append(db,actor,'huaxing',value['id'],value,'SYNTHETIC_OTHER_CUSTOMER',uuid4().hex,'fixture')
                foreign.append(value)
            db.commit()
        linked=ok(client.post(BASE+'/references',params=SCOPE,json=_ref_body(foreign[0],foreign[0]['versions'][0]['id'],[foreign[1]])))
        foreign[1]=_current(client,foreign[1])
        body=_slice3b_body(data)
        body['targets'][-1]=dict(context_id=foreign[1]['id'],revision=foreign[1]['revision'],version_ids=[linked['version_id']],note='这一单无责任权限')
        # Include the denied target in the durable observer, rather than observing only the authorized 99.
        observed=copy.deepcopy(data); observed['targets'][-1]=foreign[1]
        login_as(client,'qc_inspector')
        assert _current(client,data['targets'][0],audience='warehouse')['id']==data['targets'][0]['id']
        denied,result=_slice3b_attempt(observed,'99_permitted_one_other_customer_denied',
            lambda:client.post(BATCH_URL,params={**SCOPE,'audience':'warehouse'},json=body))
        assert denied['status']==403 and '客户' in result['detail']
        assert denied['identical_durable_snapshot'] and denied['real_commits']==denied['attempted_audit_inserts']==0
        # A permitted warehouse customer still cannot register CUSTOMER-mode approval.
        customer_target=next(t for t in data['targets'] if t['mode']=='CUSTOMER')
        customer_body=_slice3b_body(data)
        customer_body['targets']=[t for t in customer_body['targets'] if t['context_id']==customer_target['id']]
        mode,_=_slice3b_attempt(data,'warehouse_cannot_confirm_customer_mode',
            lambda:client.post(BATCH_URL,params={**SCOPE,'audience':'warehouse'},json=customer_body))
        assert mode['status']==403 and mode['identical_durable_snapshot'] and not mode['real_commits']
        login_as(client,'admin')
        from test_carton_supplier_portal import setup_portal,supplier_login
        setup_portal(client); supplier_login(client)
        supplier,_=_slice3b_attempt(data,'supplier_cannot_batch_approve',
            lambda:client.post(BATCH_URL,params={**SCOPE,'audience':'supplier'},json=_slice3b_body(data)))
        assert supplier['status']==403 and supplier['identical_durable_snapshot'] and not supplier['real_commits']
        login_as(client,'admin')
        monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','false')
        disabled,_=_slice3b_attempt(data,'write_switch_off',lambda:client.post(BATCH_URL,params=SCOPE,json=_slice3b_body(data)))
        assert disabled['status']==403 and disabled['identical_durable_snapshot'] and not disabled['real_commits']
        assert _current(client,data['targets'][0])['versions']
        capability=ok(client.get(BASE+'/capabilities',params=SCOPE))
        assert capability['batch_approval'] and not capability['writes_enabled']
        _slice3b_evidence('batch-scope-and-switch.json',[denied,mode,supplier,disabled])


def test_slice3b_concurrent_requests_confirm_each_target_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    with make_client(monkeypatch) as client:
        data=_slice3b_dataset(client)
        body=_slice3b_body(data,request_id='concurrent-batch-approval')
        requests=[body['request_id'],body['request_id'],uuid4().hex,uuid4().hex]
        barrier=Barrier(4)
        def one(request_id):
            peer=TestClient(client.app); peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=30)
                return ok(peer.post(BATCH_URL,params=SCOPE,json={**body,'request_id':request_id}))
            finally: peer.close()
        def run():
            with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(one,requests))
        evidence,results=_slice3b_attempt(data,'four_concurrent_batches',run)
        assert results[0]==results[1] and len({r['batch_receipt_id'] for r in results})==3
        assert evidence['changed_orders']==100 and evidence['carton_audit_delta']==103 and evidence['after']['ready']==100
        assert evidence['real_commits']==3
        _slice3b_evidence('batch-concurrent.json',evidence)
