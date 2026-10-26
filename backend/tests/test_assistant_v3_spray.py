"""Native spray commands and independent source comparisons on disposable DBs."""
from dataclasses import replace
from datetime import datetime, UTC
from decimal import Decimal
import json
from uuid import uuid4

import pytest
from sqlalchemy import event
from test_assistant_api import env, session, payload


def setup(env):
    from app.models import spray_ops as m
    from app.services import auth
    from app.core.config import settings
    from app.services.spray_ops.common import seed_factories
    from app.services.spray_ops import production
    from app.services.permission_codes import SPRAY_OPS_PERMISSION_CODES
    from test_spray_ops import user_with
    client, dbm, calls, patch = env
    patch.setattr(settings, 'spray_ops_enabled', True)
    patch.setattr(settings, 'authz_mode', 'enforce')
    # A fixed clock makes native drying/transfer rules reproducible. Quantities,
    # authorization, commands, reports and HTTP readers are not mocked.
    class ProductionClock(datetime):
        instant = datetime(2026, 9, 2, 1, tzinfo=UTC)
        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz)
    patch.setattr(production, 'datetime', ProductionClock)
    m.Base.metadata.create_all(dbm.engine, tables=[t for t in m.Base.metadata.sorted_tables if t.name.startswith('spray_ops_')])
    with dbm.SessionLocal() as db:
        seed_factories(db)
        db.commit()
    actor = user_with(*(code.split(':')[1] for code in SPRAY_OPS_PERMISSION_CODES))
    client.app.dependency_overrides[auth.get_current_user] = lambda: actor
    return client, dbm, calls, actor


def query(user=None, **args):
    from app.services.assistant.spray import query as read
    from test_spray_ops import user_with
    return read(user or user_with('read'), {'factory_id': 'huaxing', **args}, 'synthetic-spray-read')


def native(client, path, **params):
    result = client.get('/api/spray-operations/' + path, params={'factory_id': 'huaxing', **params})
    assert result.status_code == 200, result.text
    return result.json()


def fixture_order(client, quantity='200', *, factory='huaxing', steps=None, unit='件', code=None):
    from test_spray_ops import post
    code = code or uuid4().hex[:8]
    resource = post(client, 'resources', factory_id=factory, code='M-' + code, name='合成手喷机', kind='manual',
        capabilities=[dict(capability='coat', hourly_capacity='1000', evidence='合成确认')],
        calendar=[dict(start_at='2026-09-01T00:00:00Z', end_at='2026-10-01T00:00:00Z')])
    route = post(client, 'routes', factory_id=factory, code='R-' + code, label='合成工艺', revision=1, confirmed=True,
        evidence='合成确认', steps=steps or [dict(code='S1', name='单道喷油', capability='coat', prep_required=False, input_unit=unit, output_unit=unit)])
    demand = post(client, 'demands', factory_id=factory, document_no=code, counterparty='合成委托方', business_date='2026-09-01',
        source_ref='PRIVATE-SOURCE', note='PRIVATE-NOTE', lines=[dict(item_no='00017', part='左件', color='灰色', quantity=quantity, unit=unit,
        due_date='2026-10-01', route_id=route['id'], commercial_price='99.37', price_evidence='PRIVATE-PRICE')])
    line = demand['lines'][0]
    batch = post(client, 'batches', factory_id=factory, document_no='ARR-' + code, business_date='2026-09-01',
        line_id=line['id'], item_no='00017', part='左件', unit=unit, quantity=quantity, accepted=quantity)
    return dict(resource=resource, route=route, demand=demand, line=line, batch=batch, stock=batch['stock'][0])


def execute(client, data, quantity, *, processed=None, good=None, hold='0', scrap='0', step=0, hour=0):
    from test_spray_ops import post, publish, start
    from app.services.spray_ops import production
    production.datetime.instant = datetime(2026, 9, 2, hour+1, tzinfo=UTC)
    start_at, end_at = f'2026-09-02T{hour:02}:00:00Z', f'2026-09-02T{hour+1:02}:00:00Z'
    scenario = post(client, 'scenarios/preview', start_at=start_at, end_at=end_at, tasks=[dict(
        step_id=data['route']['steps'][step]['id'], resource_id=data['resource']['id'], start_at=start_at, end_at=end_at,
        allocations=[dict(stock_id=data['stock']['id'], quantity=quantity)])])
    task = start(client, publish(client, scenario))
    processed = processed or quantity
    quantities = dict(processed=processed, good=good if good is not None else processed, hold=hold, scrap=scrap, normal=processed, overtime='0')
    report = post(client, 'reports', document_no='REPORT-' + uuid4().hex[:8], business_date='2026-09-02', shift='合成白班',
        rows=[dict(task_id=task['id'], **quantities, reason='合成质量',
                   allocations=[dict(task_allocation_id=task['allocations'][0]['id'], **quantities)])])
    return task, report


def quantities(result):
    return {key: Decimal(value['value']) for key, value in result['metrics'].items() if ':' in key and value['value'] is not None}


def runtime_setup(env):
    from app.models.auth import AuthUser
    from app.services.assistant import runtime
    from test_assistant_v2 import migrate
    client, dbm, calls, user = setup(env)
    with dbm.SessionLocal() as db:
        db.add(AuthUser(id=user.id, username='synthetic-spray-reader', display_name='合成喷油读取',
            password_salt='unused', password_hash='unused', status='active'))
        db.commit()
    migrate(dbm)
    env[3].setattr(runtime, 'authenticate', lambda request: user)
    return client, dbm, calls, user


@pytest.mark.parametrize('kind', ['demand', 'task'])
def test_runtime_native_selection_snapshot_history_and_typed_actions(env, kind):
    from copy import deepcopy
    from app.models.assistant import AssistantMessage
    from app.services import auth
    from app.services.assistant import runtime
    from test_spray_ops import user_with
    client, dbm, calls, user = runtime_setup(env)
    data = fixture_order(client)
    task, _ = execute(client, data, '200', processed='160', good='150', scrap='10')
    ident = data['demand']['id'] if kind == 'demand' else task['id']
    route = 'spray-demands' if kind == 'demand' else 'spray-execution'
    sid = session(client)
    selected = dict(selection_id='native-spray-source',
        resources=[dict(module_id='spray-production', resource_type=kind, resource_id=ident)],
        filters=dict(factory_id='huaxing', view='tasks' if kind == 'task' else 'demands', task_scope='active'))
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2,
        intent='my_work', web_search='off', page_context=dict(module_id='spray-production', route_name=route, factory_id='huaxing'),
        context_selection=selected))
    assert 'event: run.completed' in response.text, response.text[-2500:]
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in answer['content_parts'] if p['type'] == 'business_snapshot')
    assert result['total_count'] == 1
    assert result['scope']['resource_refs'] == ['spray-production:' + kind + ':' + ident]
    expected_metric = 'reported_input:件' if kind == 'task' else 'finished:件'
    assert Decimal(result['metrics'][expected_metric]['value']) == (160 if kind == 'task' else 150)
    actions = next(p['items'] for p in answer['content_parts'] if p['type'] == 'actions')
    index = next(i for i, action in enumerate(actions) if action['type'] == 'open_record')
    resolved = client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index))
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['query'] == {'factory': 'huaxing', 'spray_' + kind: ident}
    assert resolved.json()['route_name'] == route and resolved.json()['params'] == {}
    history, _ = runtime.history(user, sid, 'future-run', [])
    assert any(m['role'] == 'system' and '历史业务快照' in m['content'] for m in history)
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code == 200
    assert len(calls) == 1  # deterministic provider replay; no real model request
    encoded = json.dumps(calls, ensure_ascii=False)
    assert 'PRIVATE-NOTE' not in encoded and 'commercial_price' not in encoded
    artifact = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(
        source_run_id=answer['run_id'], title='合成喷油来源', kind='markdown', content='合成生产事实'))
    assert artifact.status_code == 200, artifact.text
    original = deepcopy(answer['content_parts'])
    for change, expected in [
        (dict(query={'factory': 'huaxing', 'spray_' + kind: ident, 'task': ident}), 422),
        (dict(params=dict(taskId=ident)), 422),
        (dict(resource=dict(module_id='spray-production', resource_type='wrong', resource_id=ident)), 410),
        (dict(query={'factory': 'huaxing', 'spray_' + kind: 'missing'},
              resource=dict(module_id='spray-production', resource_type=kind, resource_id='missing')), 410),
        (dict(query={'factory': 'huakang-b', 'spray_' + kind: ident}), 410),
    ]:
        with dbm.SessionLocal() as db:
            parts = deepcopy(original)
            next(p['items'] for p in parts if p['type'] == 'actions')[index].update(change)
            db.get(AssistantMessage, answer['id']).content_parts = parts
            db.commit()
        denied = client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index))
        assert denied.status_code == expected, denied.text
    with dbm.SessionLocal() as db:
        db.get(AssistantMessage, answer['id']).content_parts = original
        db.commit()
    revoked = user_with()
    client.app.dependency_overrides[auth.get_current_user] = lambda: revoked
    env[3].setattr(runtime, 'authenticate', lambda request: revoked)
    hidden = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    assert hidden['unavailable'] and ident not in json.dumps(hidden['content_parts'])
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code == 410
    assert client.get(f"/api/assistant/artifacts/{artifact.json()['id']}/export").status_code == 410
    assert client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index)).status_code == 410
    assert len(calls) == 1


def test_spray_unbound_and_failed_selection_stop_before_query_or_provider(env):
    from app.services.assistant import business
    client, _, calls, _ = runtime_setup(env)
    def prohibited(*args, **kwargs): pytest.fail('Unverified native scope must not query a business tool')
    env[3].setattr(business, 'query', prohibited)
    for route, filters, resources in [
        ('spray-overview', {}, []),
        ('spray-execution', dict(view='tasks', scope_error='读取失败'), []),
        ('spray-demands', dict(view='demands', scope_error='读取失败'),
         [dict(module_id='spray-production', resource_type='demand', resource_id='unverified')]),
    ]:
        sid = session(client)
        response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2,
            intent='my_work', web_search='off', page_context=dict(module_id='spray-production', route_name=route, factory_id='huaxing'),
            context_selection=dict(selection_id='invalid', resources=resources, filters=dict(factory_id='huaxing', **filters))))
        assert 'event: run.failed' in response.text and 'context_unavailable' in response.text, response.text[-2500:]
    assert not calls


def test_active_tasks_filter_and_runtime_match_native_full_scope(env):
    from test_spray_ops import post, publish
    client, _, calls, _ = runtime_setup(env)
    one = fixture_order(client, code='ACTIVE')
    active, _ = execute(client, one, '200', processed='160', good='150', scrap='10')
    two = fixture_order(client, '100', code='FINISHED')
    execute(client, two, '100')
    three = fixture_order(client, '80', code='PLANNED')
    scenario = post(client, 'scenarios/preview', start_at='2026-09-02T00:00:00Z', end_at='2026-09-02T01:00:00Z', tasks=[dict(
        step_id=three['route']['steps'][0]['id'], resource_id=three['resource']['id'],
        start_at='2026-09-02T00:00:00Z', end_at='2026-09-02T01:00:00Z', allocations=[dict(stock_id=three['stock']['id'], quantity='80')])])
    planned = publish(client, scenario)
    baseline = native(client, 'tasks', task_scope='active', page_size=1)
    assert baseline['pagination']['total'] == 2
    current = query(view='tasks', task_scope='active', limit=1)[0]
    assert current['total_count'] == 2 and current['rows'][0]['id'] == baseline['data'][0]['id']
    more = query(view='tasks', task_scope='active', limit=1, cursor=current['next_cursor'])[0]
    assert {r['id'] for r in current['rows'] + more['rows']} == {active['id'], planned['id']}
    assert quantities(current) == dict(**{'scheduled_input:件': 280, 'reported_input:件': 160, 'pending_input:件': 120})
    assert quantities(more) == quantities(current)
    assert client.get('/api/spray-operations/demands', params=dict(factory_id='huaxing', task_scope='active')).status_code == 422
    sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='spray-production', route_name='spray-execution', factory_id='huaxing'),
        context_selection=dict(selection_id='active-tasks', resources=[], filters=dict(factory_id='huaxing', view='tasks', task_scope='active'))))
    assert 'event: run.completed' in response.text, response.text[-2500:]
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in answer['content_parts'] if p['type'] == 'business_snapshot')
    assert result['total_count'] == 2 and quantities(result) == quantities(current)
    assert len(calls) == 1


def test_biz008_physical_fixture_full_scope_native_details_pagination_and_no_writes(env):
    from app.services.assistant import spray
    from test_spray_ops import user_with
    client, dbm, calls, _ = setup(env)
    one = fixture_order(client, code='SYN-S001')
    fixture_order(client, '100', code='SYN-S002')
    task, report = execute(client, one, '200', processed='160', good='150', scrap='10')
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        result, source, actions = query(limit=1)
        values = quantities(result)
        assert {key: values[key + ':件'] for key in ('planned', 'finished', 'scrap', 'in_process')} == dict(planned=300, finished=150, scrap=10, in_process=140)
        assert values['white:件'] == 140 and values['wip:件'] == 0
        assert values['rework_current:件'] == values['rework_processed:件'] == 0
        assert values['arrival_rejected:件'] == values['handover_rejected:件'] == 0
        assert result['metrics']['material_shortage']['value'] is None
        assert result['metrics']['settled_amount']['value'] is None
        assert result['total_count'] == 2 and result['returned_count'] == 1 and result['truncated']
        assert result['status'] == 'partial' and result['observed_at'] is None
        assert result['rows'][0]['journey_total'] is None and not result['rows'][0]['journey_included']
        assert result['timezone'] == 'Asia/Shanghai'
        next_page, _, _ = query(limit=1, cursor=result['next_cursor'])
        assert next_page['metrics'] == result['metrics'] and not next_page['truncated']
        assert [row['id'] for row in result['rows'] + next_page['rows']] == [row['id'] for row in native(client, 'demands')['data']]
        selected, selected_source, selected_actions = query(resource_id=one['demand']['id'])
        row = selected['rows'][0]
        original = native(client, 'demands/' + one['demand']['id'])['data']
        assert {key: row[key] for key in spray.DEMAND_FIELDS} == {key: original[key] for key in spray.DEMAND_FIELDS}
        assert row['lines'] == [{key: line[key] for key in spray.LINE_FIELDS} for line in original['lines']]
        assert row['journey'] == original['journey']
        assert quantities(selected)['in_process:件'] == 40
        stocks = native(client, 'stock')['data']
        for state in ('white', 'wip', 'hold', 'finished'):
            assert values[state + ':件'] == sum(Decimal(s['quantity']) for s in stocks if s['state'] == state)
        movements = native(client, 'movements')['data']
        assert values['scrap:件'] == sum(Decimal(m['quantity']) for m in movements if m['kind'] == 'production_scrap')
        stage, _, task_actions = query(view='tasks', resource_id=task['id'])
        native_task = native(client, 'tasks/' + task['id'])['data']
        assert native_task['step']['input_unit'] == native_task['step']['output_unit'] == '件'
        assert native_task['resource']['id'] == one['resource']['id']
        assert native_task['allocations'][0]['demand_id'] == one['demand']['id']
        assert native_task['reports'][0]['report_id'] == report['id'] and native_task['reports_total'] == 1
        assert {key: stage['rows'][0][key] for key in spray.TASK_FIELDS} == {key: native_task[key] for key in spray.TASK_FIELDS}
        assert stage['rows'][0]['reports'][0]['report_id'] == report['id']
        assert stage['rows'][0]['reports'][0]['good'] == report['rows'][0]['good']
        assert quantities(stage) == {'scheduled_input:件': 200, 'reported_input:件': 160, 'pending_input:件': 40}
        assert any(v['field'] == 'final_output' for v in stage['unknown_fields'])
        assert query(view='tasks')[0]['rows'][0]['reports_total'] is None
        assert selected_actions[0]['query'] == dict(factory='huaxing', spray_demand=one['demand']['id'])
        assert task_actions[0]['query'] == dict(factory='huaxing', spray_task=task['id'])
        with dbm.SessionLocal() as db: assert spray.visible(db, user_with('read'), selected_source)
        encoded = json.dumps([result, selected, stage, source], ensure_ascii=False)
        for private in ('PRIVATE-SOURCE', 'PRIVATE-NOTE', 'PRIVATE-PRICE', '99.37', 'commercial_price', 'price_evidence', 'labor'):
            assert private not in encoded
        assert not any(s.lstrip().split(None, 1)[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'REPLACE'} for s in statements)
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not calls


def test_multistep_reports_do_not_become_finished_and_reversal_removes_scrap(env):
    from test_spray_ops import post
    client, _, calls, _ = setup(env)
    data = fixture_order(client, '100', steps=[
        dict(code='S1', name='底色', capability='coat', prep_required=False),
        dict(code='S2', name='面色', capability='coat', prep_required=False, predecessors=['S1'])])
    first, first_report = execute(client, data, '100')
    totals = quantities(query()[0])
    assert totals['finished:件'] == 0 and totals['wip:件'] == 100
    stock = next(s for s in native(client, 'stock')['data'] if s['state'] == 'wip')
    second, second_report = execute(client, {**data, 'stock': stock}, '100', good='90', scrap='10', step=1, hour=2)
    totals = quantities(query()[0])
    assert totals['finished:件'] == 90 and totals['scrap:件'] == 10 and totals['planned:件'] == 100
    stage = query(view='tasks')[0]
    assert quantities(stage)['reported_input:件'] == 200
    post(client, 'reports/' + second_report['id'] + '/reverse', expected_version=second_report['version'], business_date='2026-09-02', reason='合成纠错')
    totals = quantities(query()[0])
    assert totals['finished:件'] == totals['scrap:件'] == 0 and totals['wip:件'] == 100
    selected = query(view='tasks', resource_id=second['id'])[0]
    assert selected['rows'][0]['reports'] == [] and quantities(selected)['reported_input:件'] == 0
    assert not calls


def test_quality_rework_is_not_bad_quantity_and_reported_rework_is_separate(env):
    from test_spray_ops import post
    client, _, calls, _ = setup(env)
    data = fixture_order(client, '100')
    execute(client, data, '100', good='80', hold='15', scrap='5')
    totals = quantities(query()[0])
    assert totals['finished:件'] == 80 and totals['hold:件'] == 15
    assert totals['rework_processed:件'] == totals['rework_current:件'] == 0
    hold = next(s for s in native(client, 'stock')['data'] if s['state'] == 'hold')
    post(client, 'stock/' + hold['id'] + '/quality', expected_version=hold['version'], business_date='2026-09-02',
         good='0', rework='10', scrap='5', reason='合成复检', rework_step_id=data['route']['steps'][0]['id'])
    totals = quantities(query()[0])
    assert totals['scrap:件'] == 10 and totals['rework_current:件'] == 10 and totals['rework_processed:件'] == 0
    stock = next(s for s in native(client, 'stock')['data'] if s['state'] == 'white' and Decimal(s['quantity']) > 0)
    execute(client, {**data, 'stock': stock}, '10', hour=2)
    totals = quantities(query()[0])
    assert totals['planned:件'] == 100 and totals['finished:件'] == 90
    assert totals['rework_current:件'] == 0 and totals['rework_processed:件'] == 10
    assert not calls


def test_handover_acceptance_rejection_and_returns_do_not_inflate_stock_or_settlement(env):
    from test_spray_ops import post
    client, _, calls, _ = setup(env)
    data = fixture_order(client, '100')
    execute(client, data, '100')
    stock = next(s for s in native(client, 'stock')['data'] if s['state'] == 'finished')
    draft = post(client, 'deliveries', document_no='DRAFT', counterparty='合成委托方', business_date='2026-09-02',
        dispatch=False, lines=[dict(stock_id=stock['id'], quantity='20')])
    assert quantities(query()[0])['dispatched:件'] == 0
    delivery = post(client, 'deliveries', document_no='SENT', counterparty='合成委托方', business_date='2026-09-02',
        lines=[dict(stock_id=stock['id'], quantity='70')])
    totals = quantities(query()[0])
    assert totals['finished:件'] == 30 and totals['in_transit:件'] == 70
    accepted = post(client, 'deliveries/' + delivery['id'] + '/accept', expected_version=delivery['version'], business_date='2026-09-03',
        lines=[dict(delivery_line_id=delivery['lines'][0]['id'], accepted='50', rejected='10', reason='合成拒收')])
    post(client, 'returns', delivery_line_id=accepted['lines'][0]['id'], expected_version=accepted['lines'][0]['version'],
        business_date='2026-09-04', quantity='5', reason='合成退货')
    result = query()[0]
    totals = quantities(result)
    assert {key: totals[key + ':件'] for key in ('finished', 'hold', 'dispatched', 'handover_accepted', 'handover_rejected', 'returned', 'in_transit', 'net_accepted')} == dict(
        finished=30, hold=15, dispatched=70, handover_accepted=50, handover_rejected=10, returned=5, in_transit=10, net_accepted=45)
    assert totals['rework_current:件'] == 15 and totals['rework_processed:件'] == 0
    assert result['metrics']['settled_amount']['value'] is None
    original = native(client, 'deliveries/' + delivery['id'])['data']['lines'][0]
    assert totals['net_accepted:件'] == Decimal(original['accepted']) - Decimal(original['returned'])
    assert not calls


def test_units_decimal_and_confirmed_conversion_never_mix(env):
    client, _, calls, _ = setup(env)
    data = fixture_order(client, '10', steps=[dict(code='S1', name='合成换算', capability='coat', prep_required=False,
        input_unit='件', output_unit='套', output_ratio='0.5')])
    fixture_order(client, '2.125', unit='kg')
    task, _ = execute(client, data, '10')
    totals = quantities(query()[0])
    assert totals['planned:件'] == 10 and totals['finished:件'] == 0
    assert totals['finished:套'] == 5 and totals['planned:kg'] == totals['white:kg'] == Decimal('2.125')
    assert 'planned' not in query()[0]['metrics']
    journey = query(resource_id=data['demand']['id'])[0]['rows'][0]['journey'][0]
    original = native(client, 'demands/' + data['demand']['id'])['data']['journey'][0]
    assert journey == original and Decimal(journey['good']) == 5 and journey['output_unit'] == '套'
    stage = query(view='tasks', resource_id=task['id'])[0]
    assert Decimal(stage['rows'][0]['reports'][0]['good']) == 10
    assert stage['rows'][0]['step']['input_unit'] == '件' and Decimal(stage['rows'][0]['step']['output_ratio']) == Decimal('0.5')
    assert '不再乘比例' in stage['definitions']['spray.stage.v1']
    assert not calls


@pytest.mark.parametrize('mode', ['legacy', 'shadow', 'enforce'])
def test_four_factories_canonical_scope_permissions_and_native_financial_projection(env, mode):
    from app.core.config import settings
    from app.services import auth
    from app.models import spray_ops as m
    from app.services.assistant.errors import AssistantError
    from test_spray_ops import user_with
    client, _, calls, full = setup(env)
    env[3].setattr(settings, 'authz_mode', mode)
    data = {factory: fixture_order(client, str((i+1)*10), factory=factory) for i, factory in enumerate(m.FACTORIES)}
    for i, factory in enumerate(m.FACTORIES):
        reader = user_with('read', factory=factory)
        result, _, _ = query(reader, factory_id=factory)
        assert result['total_count'] == 1 and quantities(result)['planned:件'] == (i+1)*10
        for other in m.FACTORIES:
            if other != factory:
                with pytest.raises(AssistantError) as error: query(reader, factory_id=other)
                assert error.value.status_code == 403
                with pytest.raises(AssistantError) as error: query(full, factory_id=other, resource_id=data[factory]['demand']['id'])
                assert error.value.status_code == 404
    reader = user_with('read', factory='huaxing')
    client.app.dependency_overrides[auth.get_current_user] = lambda: reader
    native_read = native(client, 'demands/' + data['huaxing']['demand']['id'])
    assert 'commercial_price' not in native_read['data']['lines'][0]
    assert client.get('/api/spray-operations/finance/economics', params={'factory_id': 'huaxing', 'month': '2026-09'}).status_code == 403
    assert client.get('/api/spray-operations/payroll', params={'factory_id': 'huaxing'}).status_code == 403
    client.app.dependency_overrides[auth.get_current_user] = lambda: full
    assert native(client, 'demands/' + data['huaxing']['demand']['id'])['data']['lines'][0]['commercial_price'] == '99.370000'
    assert 'commercial_price' not in json.dumps(query(full)[0])
    assert not calls


def test_native_filters_cursor_scope_revision_and_evidence_recheck(env):
    from app.services.assistant import spray
    from app.services.assistant.errors import AssistantError
    from test_spray_ops import user_with, post
    client, dbm, calls, _ = setup(env)
    one = fixture_order(client, '10', code='SYN_%')
    fixture_order(client, '20', code='SYN-X')
    result, _, _ = query(q='_%', date_from='2026-09-01', date_to='2026-09-01', status='confirmed')
    assert result['total_count'] == 1 and quantities(result)['planned:件'] == 10
    original = native(client, 'demands', search='_%', from_date='2026-09-01', to_date='2026-09-01', status='confirmed')
    assert result['rows'][0]['id'] == original['data'][0]['id']
    reader = user_with('read')
    page, source, _ = query(reader, limit=1)
    for changed in ({'q':'SYN'}, {'view':'tasks'}, {'factory_id':'huakang-a'}):
        with pytest.raises(AssistantError) as error: query(reader, cursor=page['next_cursor'], **changed)
        assert error.value.detail['code'] == 'cursor_invalid'
    with pytest.raises(AssistantError) as error: query(replace(reader, authorization_version=3), cursor=page['next_cursor'])
    assert error.value.detail['code'] == 'cursor_invalid'
    with dbm.SessionLocal() as db:
        assert spray.visible(db, reader, source)
        assert not spray.visible(db, replace(reader, authorization_version=3), source)
        assert not spray.visible(db, reader, {**source, 'resources':[dict(module_id=spray.MODULE, resource_type='task', resource_id=one['demand']['id'])]})
        assert not spray.visible(db, reader, {**source, 'resources':[dict(module_id=spray.MODULE, resource_type='demand', resource_id='missing')]})
        with pytest.raises(AssistantError): spray.visible(db, user_with(), source)
    post(client, 'employees', code='REVISION', name='合成版本更新')
    with pytest.raises(AssistantError) as error: query(cursor=page['next_cursor'])
    assert error.value.detail['code'] == 'cursor_invalid'
    assert not calls


def test_empty_invalid_missing_disabled_and_unmigrated_are_not_successful_zeroes(env):
    from app.core.config import settings
    from app.models import spray_ops as m
    from app.services.assistant.errors import AssistantError
    client, dbm, calls, _ = setup(env)
    result, _, _ = query()
    assert result['status'] == 'empty' and result['total_count'] == 0 and result['metrics']['records']['value'] == 0
    for args in ({'factory_id':'group'}, {'factory_id':'huakang-c'}, {'resource_id':'missing'}, {'view':'tasks', 'demand_id':'missing'},
        {'limit':True}, {'limit':51}, {'view':'tasks','date_from':'2026-09-01'}, {'view':'tasks','q':'ignored'},
        {'resource_id':'x','status':'confirmed'}, {'date_from':'bad'}, {'date_from':'2026-09-02','date_to':'2026-09-01'},
        {'cursor':'bad'}, {'resource_id':' x'}, {'view':'finance'}):
        with pytest.raises(AssistantError) as error: query(**args)
        assert error.value.status_code in (404, 422)
    env[3].setattr(settings, 'spray_ops_enabled', False)
    with pytest.raises(AssistantError) as error: query()
    assert error.value.detail['code'] == 'module_disabled'
    env[3].setattr(settings, 'spray_ops_enabled', True)
    with dbm.SessionLocal() as db:
        db.delete(db.get(m.SprayOpsFactory, 'huaxing')); db.commit()
    with pytest.raises(AssistantError) as error: query()
    assert error.value.detail['code'] == 'schema_not_ready'
    with dbm.engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE spray_ops_factories')
    with pytest.raises(AssistantError) as error: query()
    assert error.value.detail['code'] == 'schema_not_ready'
    assert not calls


def test_merged_task_keeps_whole_task_scope_but_demands_own_physical_contributions(env):
    from test_spray_ops import post, publish, start
    client, _, calls, _ = setup(env)
    one = fixture_order(client, '200')
    second = post(client, 'demands', document_no='MERGED-2', counterparty='合成委托方', business_date='2026-09-01',
        lines=[dict(item_no='00017', part='左件', color='灰色', quantity='100', due_date='2026-10-01', route_id=one['route']['id'])])
    batch = post(client, 'batches', document_no='MERGED-ARR', business_date='2026-09-01', line_id=second['lines'][0]['id'],
        item_no='00017', part='左件', quantity='100', accepted='100')
    scenario = post(client, 'scenarios/preview', start_at='2026-09-02T00:00:00Z', end_at='2026-09-02T01:00:00Z', tasks=[dict(
        step_id=one['route']['steps'][0]['id'], resource_id=one['resource']['id'], start_at='2026-09-02T00:00:00Z', end_at='2026-09-02T01:00:00Z',
        allocations=[dict(stock_id=one['stock']['id'], quantity='200'), dict(stock_id=batch['stock'][0]['id'], quantity='100')])])
    task = start(client, publish(client, scenario))
    allocations = []
    for item in task['allocations']:
        first = item['line_id'] == one['line']['id']
        allocations.append(dict(task_allocation_id=item['id'], processed='200' if first else '100',
            good='150' if first else '100', hold='50' if first else '0', scrap='0', normal='200' if first else '100', overtime='0'))
    post(client, 'reports', document_no='MERGED-REPORT', business_date='2026-09-02', shift='合成', rows=[dict(
        task_id=task['id'], processed='300', good='250', hold='50', scrap='0', normal='300', overtime='0', reason='合成', allocations=allocations)])
    stage = query(view='tasks', demand_id=one['demand']['id'])[0]
    assert stage['total_count'] == 1 and quantities(stage)['reported_input:件'] == 300
    assert len(stage['rows'][0]['allocations']) == 2
    assert stage['rows'][0]['id'] == native(client, 'tasks', demand_id=one['demand']['id'])['data'][0]['id']
    assert stage['scope']['filters']['demand_id'] == one['demand']['id']
    for ident, expected in ((one['demand']['id'], 150), (second['id'], 100)):
        selected = query(resource_id=ident)[0]
        assert quantities(selected)['finished:件'] == expected
        assert Decimal(selected['rows'][0]['journey'][0]['good']) == expected
    assert not calls


def test_bounded_details_do_not_limit_full_scope_quantities_and_drafts_do_not_change_stock(env):
    from test_spray_ops import post
    client, _, calls, _ = setup(env)
    data = fixture_order(client, '10')
    demand = post(client, 'demands', document_no='MANY-LINES', counterparty='合成', business_date='2026-09-01', confirm=False,
        lines=[dict(item_no=f'SYN-{i}', part='件', color='白色', quantity='2', due_date='2026-10-01', route_id=data['route']['id']) for i in range(26)])
    result = query(resource_id=demand['id'])[0]
    assert result['rows'][0]['lines_total'] == 26 and len(result['rows'][0]['lines']) == 25
    assert result['rows'][0]['detail_truncated'] and result['status'] == 'partial'
    assert quantities(result)['planned:件'] == 52 and quantities(result)['finished:件'] == 0
    assert quantities(query(status='confirmed')[0])['planned:件'] == 10
    assert quantities(query()[0])['planned:件'] == 62
    assert any(field['field'] == 'rows' for field in result['unknown_fields'])
    assert not calls
