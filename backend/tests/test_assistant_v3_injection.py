"""Native API, factory policy and persisted V3 evidence on disposable SQLite."""
from datetime import datetime, timedelta
from decimal import Decimal
import json

import pytest
from sqlalchemy import event
from test_assistant_api import env, payload, session
from test_work_center_api import actor


def setup(env):
    from app.models.injection_scheduling import Demand, FactorySettings
    from app.services import auth
    from app.core.config import settings
    from app.services.injection_scheduling import calculations
    client, dbm, calls, patch = env
    patch.setattr(settings, 'authz_mode', 'enforce')
    instant = datetime.fromisoformat('2026-10-23T09:00:00+08:00')
    patch.setattr(calculations, 'now', lambda: instant)
    from app.api import injection_scheduling as native
    patch.setattr(native, 'now', lambda: instant)
    user = actor('alice', factory='huakang-a', department='production', permissions=('injection_scheduling:read',))
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    with dbm.SessionLocal() as db:
        settings_row = db.get(FactorySettings, 'huakang-a')
        if settings_row is None:
            settings_row = FactorySettings(factory_id='huakang-a')
            db.add(settings_row)
        settings_row.revision = 7
        for i, (state, material, slack) in enumerate([('READY', '100.10', '4'), ('WAIT_MATERIAL', '20.20', '-2'), ('PAUSED', '0.20', '8')], 1):
            db.add(Demand(id=f'SYN-I-A00{i}', factory_id='huakang-a', mold_code=f'SYN-M00{i}', order_no=f'SYN-O-{i}',
                part_name='隔离合成需求', dispatch_state=state, remaining_material_kg=Decimal(material),
                delivery_slack_hours=Decimal(slack), remaining_shots=Decimal('12.5'), delivery_due_at=instant + timedelta(days=i),
                updated_at=instant - timedelta(hours=1), extras={'private_extension': 'HIDDEN-EXTENSION'}, price_per_shot=Decimal('999.123456')))
        db.add(Demand(id='SYN-I-B001', factory_id='huakang-b', mold_code='OTHER-FACTORY', remaining_material_kg=Decimal('9000')))
        db.commit()
    return client, dbm, calls, patch, user


def query(user, **args):
    from app.services.assistant import business
    return business.query(user, 'get_injection_overview', {'factory_id': 'huakang-a', **args}, 'synthetic-injection-run')


def test_native_full_totals_paging_projection_and_readonly(env):
    client, dbm, _, _, user = setup(env)
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        result, source, actions = query(user, limit=1)
        native_response = client.post('/api/injection-scheduling/demands/query', json=dict(factory_id='huakang-a', page_size=1))
        assert native_response.status_code == 200, native_response.text
        native = native_response.json()
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for s in statements)
    assert result['total_count'] == native['total_count'] == 3
    assert result['returned_count'] == 1 and result['truncated'] and result['status'] == 'partial'
    assert result['rows'][0]['id'] == native['rows'][0]['id']
    metrics = {k: v['value'] for k, v in result['metrics'].items()}
    assert metrics['held_count'] == native['filtered_summary']['held_count'] == 2
    assert metrics['wait_material_count'] == 1
    assert metrics['forecast_late_count'] == native['filtered_summary']['late_count'] == 1
    assert metrics['remaining_material_kg'] == metrics['known_remaining_material_kg'] == '120.5'
    assert metrics['warehouse_shortage_kg'] is metrics['actual_delivery_late_count'] is None
    assert result['as_of'] == source['as_of'] == '2026-10-23T09:00:00+08:00'
    assert result['rows'][0]['updated_at'] == '2026-10-23T08:00:00+08:00'
    assert not any(s in json.dumps(result) for s in ('9000', 'HIDDEN-EXTENSION', 'price_per_shot', 'remaining_processing_amount'))
    second, _, _ = query(user, limit=2, cursor=result['next_cursor'])
    assert [r['id'] for r in second['rows']] == ['SYN-I-A002', 'SYN-I-A003']
    assert second['next_cursor'] is None and second['metrics'] == result['metrics']
    detail, _, _ = query(user, resource_id='SYN-I-A002')
    original = client.get('/api/injection-scheduling/demands/SYN-I-A002?factory_id=huakang-a')
    assert original.status_code == 200
    assert detail['scope']['coverage'] == 'selected_resources' and detail['total_count'] == 1
    assert Decimal(detail['rows'][0]['remaining_material_kg']) == Decimal(str(original.json()['demand']['remaining_material_kg']))
    assert detail['metrics']['held_count']['value'] == 1 and 'reference_summary' not in detail
    assert actions[0]['query']['factory'] == 'huakang-a'
    assert actions[1]['query'] == dict(factory='huakang-a', demand='SYN-I-A001')


def test_same_native_filters_decimal_unknowns_and_revision_cursor(env):
    from app.models.injection_scheduling import Demand, FactorySettings
    from app.services.assistant.errors import AssistantError
    from app.services.injection_scheduling import calculations
    client, dbm, _, patch, user = setup(env)
    filters = {'op': 'and', 'children': [{'field': 'dispatch_state', 'op': 'ne', 'value': 'READY'},
        {'field': 'delivery_due_at', 'op': 'next_days', 'value': 4}]}
    search = {'field': 'mold_code', 'mode': 'prefix', 'text': 'SYN-'}
    sort = [{'field': 'mold_code', 'direction': 'desc'}]
    result, _, _ = query(user, filter=filters, search=search, sort=sort, limit=1)
    native = client.post('/api/injection-scheduling/demands/query', json=dict(factory_id='huakang-a', filter=filters, search=search, sort=sort, page_size=1))
    assert native.status_code == 200, native.text
    assert result['total_count'] == native.json()['total_count'] == 2
    assert result['rows'][0]['id'] == native.json()['rows'][0]['id'] == 'SYN-I-A003'
    assert result['metrics']['remaining_material_kg']['value'] == '20.4'
    with pytest.raises(AssistantError): query(user, cursor=result['next_cursor'])
    with dbm.SessionLocal() as db:
        db.get(Demand, 'SYN-I-A002').remaining_material_kg = None
        db.get(Demand, 'SYN-I-A003').remaining_material_kg = Decimal('0.00000003')
        db.get(Demand, 'SYN-I-A001').remaining_material_kg = Decimal('0.00000001')
        db.get(Demand, 'SYN-I-A002').delivery_slack_hours = None
        db.get(FactorySettings, 'huakang-a').revision += 1
        db.commit()
    with pytest.raises(AssistantError): query(user, filter=filters, search=search, sort=sort, cursor=result['next_cursor'])
    unknown, _, _ = query(user)
    assert unknown['metrics']['remaining_material_kg']['value'] is None
    assert unknown['metrics']['known_remaining_material_kg']['value'] == '0.00000004'
    assert unknown['metrics']['remaining_material_unknown_count']['value'] == 1
    assert unknown['metrics']['forecast_unknown_count']['value'] == 1
    assert unknown['metrics']['forecast_late_count']['value'] == 0
    empty, _, _ = query(user, search={'field': 'mold_code', 'mode': 'exact', 'text': 'MISSING'})
    assert empty['status'] == 'empty' and empty['total_count'] == 0
    assert empty['metrics']['remaining_material_kg']['value'] == '0'
    first, _, _ = query(user, limit=1)
    patch.setattr(calculations, 'now', lambda: datetime.fromisoformat('2026-10-23T09:06:00+08:00'))
    with pytest.raises(AssistantError): query(user, cursor=first['next_cursor'])


NEGATIVE_CASES = [({'factory_id': 'huakang-b'}, 'business_forbidden'),
    ({'factory_id': 'authorized'}, 'factory_unavailable'), ({'resource_id': 'SYN-I-B001'}, 'source_unavailable'),
    ({'limit': True}, 'tool_invalid'), ({'sql': 'select *'}, 'tool_invalid'),
    ({'filter': {'field': 'arbitrary_column', 'op': 'eq', 'value': 1}}, 'tool_invalid'),
    ({'filter': {'field': 'remaining_shots', 'op': 'gt', 'value': None}}, 'tool_invalid'),
    ({'sort': [{'field': 'id', 'direction': 'random'}]}, 'tool_invalid'),
    ({'resource_id': 'SYN-I-A001', 'search': {'text': 'x'}}, 'tool_invalid'),
    ({'search': {'text': 'x' * 4001}}, 'tool_invalid'), ({'cursor': 'invalid'}, 'cursor_invalid')]
def test_strict_scope_arguments_and_foreign_fact_absence(env):
    from app.services.assistant.errors import AssistantError
    _, _, _, _, user = setup(env)
    for args, code in NEGATIVE_CASES:
        with pytest.raises(AssistantError) as error: query(user, **args)
        assert error.value.detail['code'] == code
        assert not any(s in json.dumps(error.value.detail) for s in ('9000', 'SYN-I-B001', 'HIDDEN-EXTENSION'))


def test_runtime_freezes_native_query_and_persists_v3_snapshot(env):
    from app.services.assistant import runtime
    client, dbm, calls, patch, user = setup(env)
    patch.setattr(runtime, 'authenticate', lambda request: user)
    sid = session(client)
    filters = {'field': 'dispatch_state', 'op': 'eq', 'value': 'WAIT_MATERIAL'}
    body = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='injection-scheduling', route_name='injection-scheduling', factory_id='huakang-a'),
        context_selection=dict(selection_id='injection-filters', resources=[], filters={'factory_id': 'huakang-a', 'filter_json': json.dumps(filters)}))
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert 'event: run.completed' in response.text, response.text[-2000:]
    msg = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in msg['content_parts'] if p['type'] == 'business_snapshot')
    assert result['total_count'] == 1 and result['metrics']['remaining_material_kg']['value'] == '20.2'
    assert result['tool_call_id'] == 'prequery-0'
    assert len(calls) == 1
    supplied = next(m['content'] for m in calls[0]['messages'] if m['role'] == 'system' and m['content'].startswith('已受权业务快照'))
    assert json.loads(supplied.split('：', 1)[1]) == result
    assert 'SYN-I-B001' not in supplied
    actions = next(p['items'] for p in msg['content_parts'] if p['type'] == 'actions')
    index = next(i for i, action in enumerate(actions) if action.get('query', {}).get('demand') == 'SYN-I-A002')
    action_payload = dict(run_id=msg['run_id'], index=index)
    resolved = client.post('/api/assistant/actions/resolve', json=action_payload)
    assert resolved.status_code == 200 and resolved.json()['query'] == dict(factory='huakang-a', demand='SYN-I-A002')
    from app.models.injection_scheduling import Demand
    with dbm.SessionLocal() as db:
        db.delete(db.get(Demand, 'SYN-I-A002'))
        db.commit()
    assert client.post('/api/assistant/actions/resolve', json=action_payload).status_code == 410
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']


def test_full_default_page_fits_existing_context_budget(env):
    from app.core.config import settings
    from app.models.injection_scheduling import Demand
    from app.services.assistant import runtime
    client, dbm, calls, patch, user = setup(env)
    patch.setattr(runtime, 'authenticate', lambda request: user)
    patch.setattr(settings, 'assistant_context_character_budget', 24000)
    with dbm.SessionLocal() as db:
        for i in range(4, 22):
            db.add(Demand(id=f'SYN-I-A{i:03}', factory_id='huakang-a', mold_code=f'SYN-M{i:03}',
                part_name='隔离合成需求', remaining_material_kg=Decimal('0.1'), remaining_shots=Decimal('10')))
        db.commit()
    body = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='injection-scheduling', route_name='injection-scheduling', factory_id='huakang-a'))
    sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert 'event: run.completed' in response.text, response.text[-2000:]
    message = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in message['content_parts'] if p['type'] == 'business_snapshot')
    assert result['total_count'] == 21 and result['returned_count'] == 20 and result['next_cursor']
    assert runtime.context_size(calls[0]['messages']) < 24000
