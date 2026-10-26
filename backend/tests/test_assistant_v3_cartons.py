"""Real native HTTP/SQL comparisons in a disposable DB; no model or business writes."""
import base64
from datetime import datetime, timedelta
from decimal import Decimal as D
import json

import pytest
from sqlalchemy import event
from test_assistant_api import env, session, payload
from test_work_center_api import actor

STAMP = '2026-10-23T10:00:00+08:00'
FACTORY = 'huakang-a'


def setup(env, count=2):
    from app.models import carton_procurement as m
    from app.models.carton_special_requests import SpecialRequest, SpecialLine
    from app.services import auth, carton_procurement as core
    from app.core.config import settings
    client, dbm, calls, patch = env
    patch.setattr(settings, 'authz_mode', 'enforce')
    patch.setattr(core, 'business_now', lambda: datetime.fromisoformat(STAMP))
    user = actor('alice', factory=FACTORY, department='carton', permissions=('carton_procurement:read', 'carton_procurement:order_write'))
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    with dbm.SessionLocal() as db:
        for factory in (FACTORY, 'huakang-b'):
            db.add(m.CartonSupplier(id='supplier-'+factory, factory_id=factory, supplier_code='SYN', supplier_name='Synthetic', created_at=STAMP, updated_at=STAMP))
        for code in ('C1', 'C2'):
            db.add(m.CartonCustomer(id=code, factory_id=FACTORY, customer_code=code, customer_name=code,
                created_by='alice', updated_by='alice', created_at=STAMP, updated_at=STAMP))
        db.flush()
        for ident, code, factory, quantity, status, unit in (
            ('P1', 'C1', FACTORY, 1000, 'PARTIALLY_RECEIVED', '个'),
            ('P2', 'C2', FACTORY, 20, 'CONFIRMED', '张'),
            ('CANCEL', 'C1', FACTORY, 900, 'CANCELLED', '个'),
            ('FOREIGN', 'C1', 'huakang-b', 99999, 'CONFIRMED', '个')):
            db.add(m.CartonOrder(id=ident, factory_id=factory, order_no=ident, customer_code=code, customer_name=code,
                supplier_id='supplier-'+factory, supplier_name_snapshot='Synthetic', contract_no='CON-'+ident,
                item_no='ITEM-'+ident, product_name='合成纸品', quantity_basis='EXPLICIT', product_order_quantity=None,
                order_date='2026-10-20', due_date='2026-10-22', status=status, created_by='alice', updated_by='alice',
                created_at=STAMP, updated_at=STAMP))
            db.flush()
            db.add(m.CartonOrderLine(id='L-'+ident, order_id=ident, factory_id=factory, line_no=1,
                customer_code=code, contract_no='CON-'+ident, item_no='ITEM-'+ident, packaging_type='外箱',
                paper_quality='A33', specification='1x1x1', usage_quantity=None, required_quantity=D(quantity),
                unit=unit, unit_price=D('99123.456'), note='HIDDEN_PRICE_NOTE'))
        db.flush()
        db.add(m.CartonReceipt(id='REC', factory_id=FACTORY, receipt_no='REC', delivery_note_no='DEL',
            delivery_date='2026-10-21', supplier_id='supplier-'+FACTORY, supplier_name_snapshot='Synthetic', status='POSTED',
            created_by='alice', created_at=STAMP, updated_at=STAMP))
        db.flush()
        db.add(m.CartonReceiptLine(id='RL', factory_id=FACTORY, receipt_id='REC', line_no=1, order_line_id='L-P1',
            customer_code='C1', customer_name='C1', contract_no='CON-P1', item_no='ITEM-P1', packaging_type='外箱',
            paper_quality='A33', specification='1x1x1', delivered_quantity=D(600), received_quantity=D(600),
            effective_quantity=D(600), unit='个', unit_price=D('99123.456')))
        for i in range(count):
            kind = ('SAMPLE', 'WORKSHOP_MISC', 'SUPPLIER_GIFT')[i % 3]
            db.add(SpecialRequest(id=f'S{i}', factory_id=FACTORY, supplier_id='supplier-'+FACTORY, request_no=f'S-{i:03}',
                kind=kind, title='合成请求', requester_name='申请人', customer_code='C1', customer_name='C1',
                purpose='HIDDEN_PRIVATE_PURPOSE', required_date='2026-10-24', status='SUBMITTED', revision=1,
                created_by='alice' if i == 0 else 'bob', created_at=STAMP, updated_at=STAMP))
            db.flush()
            db.add(SpecialLine(id=f'SL{i}', factory_id=FACTORY, request_id=f'S{i}', line_no=1,
                packaging_type='隔板', paper_quality='A33', specification='1x1', dimension_unit='cm',
                quantity=D(2), unit='张', unit_price=D('99123.456')))
        db.commit()
    return client, dbm, calls, patch, user


def query(user, **args):
    from app.services.assistant.cartons import query as read
    return read(user, {'factory_id': FACTORY, **args}, 'synthetic-carton-run')


def value(result, key):
    return D(result['metrics'][key]['value'])


def test_native_combined_http_full_totals_selected_and_read_only(env):
    client, dbm, calls, _, user = setup(env, count=55)
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        result, source, actions = query(user, limit=50)
        native = client.get('/api/carton-unified-orders', params=dict(factory_id=FACTORY, limit=200)).json()
        detail, _, _ = query(user, resource_id='PURCHASE:P1')
        original = client.post('/api/carton-unified-orders/selected', json=dict(factory_id=FACTORY, items=[dict(kind='PURCHASE', id='P1')])).json()
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for s in statements)
    assert result['total_count'] == native['total'] == 58
    assert result['returned_count'] == 50 and result['truncated'] and result['next_cursor']
    assert value(result, 'remaining_quantity[个]') == 400
    assert value(result, 'required_quantity[个]') == 1900
    assert value(result, 'received_quantity[个]') == 600
    assert value(result, 'remaining_quantity[张]') == 130
    assert result['metrics']['overdue_count']['value'] == native['statistics']['overdue'] == 2
    assert result['metrics']['available_quantity']['value'] is None
    expected = [x['kind']+':'+(x['order']['order_no'] if x['kind']=='PURCHASE' else x['special']['id']) for x in native['items']]
    assert [x['id'] for x in result['rows']] == expected[:50]
    second, _, _ = query(user, limit=50, cursor=result['next_cursor'])
    assert [x['id'] for x in second['rows']] == expected[50:]
    assert second['metrics'] == result['metrics'] and second['next_cursor'] is None
    assert D(detail['rows'][0]['lines'][0]['remaining_quantity']) == D(original[0]['order']['lines'][0]['remaining_quantity']) == 400
    assert detail['scope']['coverage'] == 'selected_resources'
    assert source['as_of'] == STAMP and source['authorization_fingerprint']
    raw = json.dumps(result, ensure_ascii=False)
    assert all(v not in raw for v in ('unit_price', '99123.456', 'HIDDEN_PRIVATE_PURPOSE', 'HIDDEN_PRICE_NOTE', 'FOREIGN', '99999'))
    assert len(actions) == len(result['allowed_actions']) == 50 and not calls
    assert actions[0]['query']['carton_record'] == result['rows'][0]['id']


def test_native_responsibilities_applicant_readonly_and_selected_limits(env):
    from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment
    from app.models.carton_procurement import CartonOrder
    from app.models.carton_special_requests import SpecialVersion
    from app.services import auth
    from app.services.assistant.errors import AssistantError
    client, dbm, _, _, user = setup(env, count=3)
    before, source, _ = query(user, limit=1)
    with dbm.SessionLocal() as db:
        db.add(Assignment(customer_id='C2', user_id='bob', factory_id=FACTORY)); db.commit()
    own, changed, _ = query(user)
    all_rows, _, _ = query(user, responsibility_scope='ALL')
    native = client.get('/api/carton-unified-orders', params=dict(factory_id=FACTORY, responsibility_scope='OWN')).json()
    assert own['total_count'] == native['total'] == 5 and all_rows['total_count'] == 6
    assert source['responsibility_fingerprint'] != changed['responsibility_fingerprint']
    with pytest.raises(AssistantError): query(user, cursor=before['next_cursor'])
    with pytest.raises(AssistantError): query(user, resource_id='PURCHASE:P2')
    applicant = actor('alice', factory=FACTORY, department='carton', permissions=('carton_procurement:special_request_submit',))
    client.app.dependency_overrides[auth.get_current_user] = lambda: applicant
    result, _, _ = query(applicant, responsibility_scope='ALL')
    native = client.get('/api/carton-unified-orders', params=dict(factory_id=FACTORY, responsibility_scope='ALL')).json()
    assert result['total_count'] == native['total'] == 1 and result['rows'][0]['id'] == 'SAMPLE:S0'
    for args in ({'resource_id':'PURCHASE:P1'}, {'resource_id':'WORKSHOP_MISC:S1'}, {'view':'inventory'}):
        with pytest.raises(AssistantError): query(applicant, **args)
    readonly = actor('alice', factory=FACTORY, department='carton', permissions=('carton_procurement:read',))
    result, _, _ = query(readonly)
    assert {row['id'] for row in result['rows']} == {'PURCHASE:P1', 'PURCHASE:CANCEL', 'SAMPLE:S0'}
    with dbm.SessionLocal() as db:
        db.get(CartonOrder, 'P1').deleted_at = STAMP; db.commit()
    with pytest.raises(AssistantError): query(user, resource_id='PURCHASE:P1')
    with dbm.SessionLocal() as db:
        db.add(SpecialVersion(id='DELETED-S0', factory_id=FACTORY, request_id='S0', revision=2,
            action='DELETED', actor_id='alice', actor_name='合成', created_at=STAMP, snapshot_json='{}'))
        db.commit()
    with pytest.raises(AssistantError): query(user, resource_id='SAMPLE:S0')
    supplier = actor('alice', factory=FACTORY, department='carton', permissions=('carton_supplier:read',))
    with pytest.raises(AssistantError): query(supplier)


def test_strict_parameters_snapshot_bound_cursor_and_registered_types(env):
    from app.models.carton_procurement import CartonOrderLine
    from app.services.assistant.errors import AssistantError
    from app.services.assistant import registry
    from app.services import carton_procurement as core
    _, dbm, _, patch, user = setup(env)
    first, _, _ = query(user, limit=1)
    for args in ({'factory_id':'huakang-b'}, {'factory_id':'authorized'}, {'resource_id':'PURCHASE:FOREIGN'},
        {'resource_id':'WORKSHOP_MISC:S0'}, {'resource_id':'P1'}, {'resource_id':'PURCHASE:P1','search':'P1'},
        {'resource_id':'INVENTORY:any'}, {'sql':'SELECT *'}, {'limit':True}, {'limit':0},
        {'resource_id':'SAMPLE:'+'x'*97}, {'resource_id':'PURCHASE: P1'},
        {'date_from':'2026-02-30'}, {'date_from':'2026-10-24','date_to':'2026-10-23'},
        {'view':'inventory','responsibility_scope':'ALL'}, {'view':'orders','customer_code':'C1'},
        {'search':'P1','cursor':first['next_cursor']}, {'cursor':'not-base64'},
        {'cursor':base64.urlsafe_b64encode(b'null').decode()}, {'cursor':base64.urlsafe_b64encode(b'[]').decode()}):
        with pytest.raises(AssistantError): query(user, **args)
    with dbm.SessionLocal() as db:
        db.get(CartonOrderLine, 'L-P1').required_quantity = 1100; db.commit()
    with pytest.raises(AssistantError): query(user, cursor=first['next_cursor'])
    current, _, _ = query(user, limit=1)
    patch.setattr(core, 'business_now', lambda: datetime.fromisoformat(STAMP)+timedelta(seconds=301))
    with pytest.raises(AssistantError): query(user, cursor=current['next_cursor'])
    empty, _, _ = query(user, search='missing-synthetic-item')
    assert empty['status'] == 'empty' and empty['total_count'] == 0
    assert registry.resolve('carton-procurement') == 'get_carton_overview'
    assert registry.resolve('carton-procurement', 'inventory') == 'get_carton_overview'


def test_all_native_filter_modes_and_bounded_detail_keep_full_metrics(env):
    from app.models.carton_procurement import CartonOrderLine
    client, dbm, _, _, user = setup(env, count=3)
    for filters in ({'kind':'SAMPLE'}, {'kind':'WORKSHOP_MISC'}, {'kind':'SUPPLIER_GIFT'}, {'kind':'PURCHASE'},
        {'search':'S-001'}, {'customer_name':'C2'}, {'status_filter':'CANCELLED'},
        {'date_from':'2026-10-23','date_to':'2026-10-23'}, {'due_filter':'OVERDUE'},
        {'due_filter':'DUE_SOON'}, {'collaboration_filter':'NOT_ISSUED'}, {'sort':'DUE_DESC'}, {'sort':'ORDER_DESC'}):
        result, _, _ = query(user, **filters)
        native_filters = {({'date_from':'order_from','date_to':'order_to'}.get(k,k)):v for k,v in filters.items()}
        response = client.get('/api/carton-unified-orders', params={'factory_id':FACTORY, **native_filters})
        assert response.status_code == 200, response.text
        native = response.json()
        assert result['total_count'] == native['total'], filters
        expected = [x['kind']+':'+(x['order']['order_no'] if x['kind']=='PURCHASE' else x['special']['id']) for x in native['items']]
        assert [row['id'] for row in result['rows']] == expected, filters
    with dbm.SessionLocal() as db:
        for i in range(2, 53):
            db.add(CartonOrderLine(id=f'EXTRA-{i}', order_id='P1', factory_id=FACTORY, line_no=i,
                customer_code='C1', contract_no='CON-P1', item_no='ITEM-P1', packaging_type='外箱',
                paper_quality='A33', specification='1x1x1', usage_quantity=None, required_quantity=D(1), unit='个'))
        db.commit()
    result, _, _ = query(user, resource_id='PURCHASE:P1')
    row = result['rows'][0]
    assert row['line_count']==52 and len(row['lines'])==50 and row['lines_truncated']
    assert value(result, 'remaining_quantity[个]')==451
    assert any(u['field']=='rows' for u in result['unknown_fields'])


def test_inventory_native_periods_current_positions_units_and_no_write(env):
    from app.models.carton_procurement import CartonInventoryMovement as Movement
    from app.models.carton_positions import CartonLocation, CartonPositionEntry
    from app.services.carton_positions import inventory_key
    client, dbm, _, _, user = setup(env, count=0)
    with dbm.SessionLocal() as db:
        db.add(CartonLocation(id='LOC', factory_id=FACTORY, warehouse='合成仓', bin_code='A01')); db.flush()
        for ident, qty, at, unit in [('opening',10,'2026-10-19T08:00:00+08:00','个'),
            ('in',5,'2026-10-20T08:00:00+08:00','个'), ('out',-3,'2026-10-21T08:00:00+08:00','个'),
            ('later',7,'2026-10-22T08:00:00+08:00','个'), ('sheets',100,'2026-10-20T08:00:00+08:00','张')]:
            row = Movement(id=ident, factory_id=FACTORY, order_line_id=None, customer_code='C1', customer_name='C1',
                contract_no='MANUAL', item_no='STOCK', packaging_type='外箱', paper_quality='A33', specification='1x1x1',
                movement_type='INBOUND' if qty>0 else 'OUTBOUND', quantity=D(qty), unit=unit, unit_price=D('99123.456'),
                currency='CNY', location='合成仓/A01', document_no=ident, source_type='MANUAL', source_id=ident,
                source_line_id=ident, reason='PRIVATE-REASON', actor_user_id='alice', actor_name='合成', occurred_at=at)
            db.add(row); db.flush()
            db.add(CartonPositionEntry(factory_id=FACTORY, inventory_key=inventory_key(row), location_id='LOC',
                movement_id=ident, quantity=D(qty), occurred_at=at))
        db.commit()
    statements=[]
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        result, _, _ = query(user, view='inventory', date_from='2026-10-20', date_to='2026-10-21', limit=1)
        native = client.get('/api/carton-procurement/inventory/report', params=dict(factory_id=FACTORY,
            date_from='2026-10-20', date_to='2026-10-21')).json()
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE')) for s in statements)
    assert result['total_count'] == len(native['order_rows'])
    for key, expected in [('opening',10), ('inbound',5), ('outbound',3), ('ending',12)]:
        assert value(result, key+'_quantity[个]') == expected
        assert sum(D(r[key+'_quantity']) for r in native['order_rows'] if r['unit']=='个') == expected
    assert value(result, 'ending_quantity[张]') == 100
    assert result['metrics']['available_quantity']['value'] is None
    assert result['scope']['filters']['view']=='inventory' and 'responsibility_scope' not in result['scope']['filters']
    full, _, _ = query(user, view='inventory', date_from='2026-10-20', date_to='2026-10-21')
    stock = next(r for r in full['rows'] if r['contract_no']=='MANUAL' and r['unit']=='个')
    assert D(stock['ending_quantity']) == 12 and D(stock['current_positions'][0]['quantity']) == 19
    assert stock['last_movement_at'] == '2026-10-21T08:00:00+08:00'
    selected, _, _ = query(user, view='inventory', resource_id=stock['id'], date_from='2026-10-20', date_to='2026-10-21')
    assert selected['total_count']==1 and selected['rows'][0]==stock
    raw=json.dumps(full)
    assert all(s not in raw for s in ('unit_price','99123.456','PRIVATE-REASON'))


def test_historical_aggregate_rechecks_off_page_rows_and_native_all_authority(env):
    from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment
    from app.models.carton_special_requests import SpecialRequest
    from app.services.assistant import cartons
    _, dbm, _, _, user = setup(env, count=3)
    _, own, _ = query(user, limit=1)
    assert len(own['resources']) == 6
    with dbm.SessionLocal() as db:
        assert cartons.visible(db, user, own)
        db.add(Assignment(customer_id='C2', user_id='bob', factory_id=FACTORY)); db.commit()
        assert not cartons.visible(db, user, own)
    _, all_source, _ = query(user, responsibility_scope='ALL', limit=1)
    with dbm.SessionLocal() as db:
        assert cartons.visible(db, user, all_source)  # ALL includes C2, selected does not.
        assert cartons.selected_record(db, user, FACTORY, 'PURCHASE:P2') is None
        assert cartons.selected_record(db, user, FACTORY, 'PURCHASE:P1')['id'] == 'PURCHASE:P1'
    reader = actor('alice', factory=FACTORY, department='carton', permissions=('carton_procurement:read',))
    _, source, _ = query(reader, limit=1)
    assert any(r['resource_id']=='SAMPLE:S0' for r in source['resources'][1:])
    with dbm.SessionLocal() as db:
        assert cartons.visible(db, reader, source)
        # Creator changes without any IAM or assignment mutation. It is beyond
        # page one, but its quantity still contributed to the stored total.
        db.get(SpecialRequest, 'S0').created_by = 'bob'; db.commit()
        assert not cartons.visible(db, reader, source)


def test_runtime_source_actions_export_and_off_page_scope_revocation(env):
    from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment
    from app.services.assistant import runtime
    client, dbm, calls, patch, user = setup(env)
    patch.setattr(runtime, 'authenticate', lambda request: user)
    sid = session(client)
    body = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='carton-procurement', route_name='carton-procurement', factory_id=FACTORY),
        context_selection=dict(selection_id='carton-filtered', resources=[], filters={'factory_id':FACTORY,'kind':'PURCHASE','limit':1}))
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert 'event: run.completed' in response.text, response.text[-1800:]
    message = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in message['content_parts'] if p['type']=='business_snapshot')
    assert result['total_count']==3 and result['returned_count']==1 and value(result,'remaining_quantity[个]')==400
    actions = next(p['items'] for p in message['content_parts'] if p['type']=='actions')
    index = next(i for i,a in enumerate(actions) if a.get('query',{}).get('carton_record')=='PURCHASE:P1')
    action = {'run_id':message['run_id'],'index':index}
    resolved=client.post('/api/assistant/actions/resolve',json=action)
    assert resolved.status_code==200 and resolved.json()['query']==dict(factory=FACTORY,tab='orders',carton_record='PURCHASE:P1')
    assert client.get(f"/api/assistant/runs/{message['run_id']}/export").status_code==200
    assert len(calls)==1
    supplied=next(m['content'] for m in calls[0]['messages'] if m['role']=='system' and m['content'].startswith('已受权业务快照'))
    assert 'HIDDEN_PRICE_NOTE' not in supplied and '99123.456' not in supplied and 'FOREIGN' not in supplied
    with dbm.SessionLocal() as db:
        db.add(Assignment(customer_id='C2',user_id='bob',factory_id=FACTORY));db.commit()
    assert client.post('/api/assistant/actions/resolve',json=action).status_code==410
    assert client.get(f"/api/assistant/runs/{message['run_id']}/export").status_code==410
    hidden=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    assert hidden['unavailable'] and not any(p['type']=='business_snapshot' for p in hidden['content_parts'])
    history,_=runtime.history(user,sid,'future-run',[])
    assert not any('PURCHASE:P1' in m.get('content','') for m in history)
    rejected=payload(protocol_version=2,intent='my_work',web_search='off',page_context=body['page_context'],
        context_selection=dict(selection_id='unavailable',resources=[],filters={'factory_id':FACTORY,'scope_error':'not ready'}))
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=rejected)
    assert 'context_unavailable' in response.text and len(calls)==1


def test_inventory_selected_runtime_retains_period_and_reauthorizes_native_route(env):
    from app.services.assistant import runtime
    client, _, calls, patch, user=setup(env,count=0)
    patch.setattr(runtime,'authenticate',lambda request:user)
    report,_,_=query(user,view='inventory',date_from='2026-10-20',date_to='2026-10-21')
    ident=report['rows'][0]['id']
    sid=session(client)
    body=payload(protocol_version=2,intent='my_work',web_search='off',
        page_context=dict(module_id='carton-procurement',route_name='carton-procurement',factory_id=FACTORY),
        context_selection=dict(selection_id='inventory',resources=[dict(module_id='carton-procurement',resource_type='inventory',resource_id=ident)],
            filters=dict(factory_id=FACTORY,date_from='2026-10-20',date_to='2026-10-21')))
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=body)
    assert 'event: run.completed' in response.text,response.text[-1800:]
    message=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result=next(p['result'] for p in message['content_parts'] if p['type']=='business_snapshot')
    assert result['scope']['filters']['date_from']=='2026-10-20' and result['total_count']==1
    actions=next(p['items'] for p in message['content_parts'] if p['type']=='actions')
    index=next(i for i,a in enumerate(actions) if a.get('query',{}).get('carton_record')==ident)
    resolved=client.post('/api/assistant/actions/resolve',json={'run_id':message['run_id'],'index':index})
    assert resolved.status_code==200 and resolved.json()['query']==dict(factory=FACTORY,tab='inventory-summary',carton_record=ident,
        carton_from='2026-10-20',carton_to='2026-10-21')
    assert len(calls)==1
