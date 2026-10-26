"""Native domain/API comparisons; disposable DB and offline provider only."""
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import event, select
from test_assistant_api import env, payload, session
from test_work_center_api import actor


def setup(env):
    from app.core.config import settings
    from app.models import three_d_printing as m
    from app.services import auth, three_d_printing as domain
    client, dbm, calls, patch = env
    clock = datetime.fromisoformat('2026-10-25T09:00:00+08:00')
    patch.setattr(settings, 'authz_mode', 'enforce')
    patch.setattr(domain, 'business_now', lambda: clock)
    user = actor('alice', factory='huakang-a', department='production', permissions=('three_d_printing:read',))
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    with dbm.SessionLocal() as db:
        # These are the real native bootstrap printers in this disposable DB.
        for n, age, connected, state in [(1, 0, True, 'RUNNING'), (2, 900, True, 'RUNNING'),
                (3, None, False, 'OFFLINE'), (4, 1, False, 'RUNNING'), (5, -60, True, 'IDLE'), (6, 1, True, 'PREPARE')]:
            p = db.get(m.ThreeDPrintingPrinter, f'3dprinter-huakang-a-{n}')
            assert p is not None
            p.last_seen_at = (clock-timedelta(seconds=age)).isoformat() if age is not None else ''
            p.state, p.connected = state, connected
            p.current_file = f'SYN-TASK-{n}.3mf'
            p.progress_percent, p.remaining_minutes = 40, 10
            p.status_payload_json = json.dumps({'private_connection': 'NEVER-EXPOSE-CONNECTION', 'connector': {'layer_num': 4, 'total_layers': 10}})
        db.add(m.ThreeDPrintingPrinter(id='SYN-FOREIGN', factory_id='huakang-b', machine_no=99, name='FOREIGN-DEVICE', created_at='', updated_at=''))
        db.add(m.ThreeDPrintingSite(id='SYN-SITE', factory_id='huakang-a', site_code='syn', name='Synthetic'))
        db.flush()
        db.add(m.ThreeDPrintingConnectorInstance(id='SYN-CONNECTOR', factory_id='huakang-a', site_id='SYN-SITE', connector_key='synthetic', instance_id='synthetic'))
        db.flush()
        for i in range(12):
            db.add(m.ThreeDPrintingPrinterStateEvent(id=f'SYN-E-{i:02}', factory_id='huakang-a', connector_instance_id='SYN-CONNECTOR',
                printer_id='3dprinter-huakang-a-2', machine_no=2, connection_session_id='PRIVATE-SESSION', sequence=i,
                observed_at=(clock-timedelta(minutes=15, seconds=i)).isoformat(), received_at=(clock-timedelta(seconds=12-i)).isoformat(),
                state='RUNNING', progress=i, current_file='SYN-HISTORY.3mf', raw_payload_json='{"secret":"NEVER-EXPOSE-RAW"}'))
        db.commit()
    return client, dbm, calls, patch, user, clock


def query(user, **arguments):
    from app.services.assistant import business
    return business.query(user, 'get_printer_status', {'factory_id':'huakang-a', **arguments}, 'SYN-PRINTER-RUN')


def test_native_scope_freshness_projection_and_query_is_readonly(env):
    client, dbm, _, patch, user, clock = setup(env)
    from app.services import three_d_printing as domain
    def forbidden(*args, **kwargs): raise AssertionError('assistant cannot initialize settings or dispatch commands')
    patch.setattr(domain, 'ensure_settings', forbidden)
    patch.setattr(domain, 'create_printer_command', forbidden)
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        result, source, _ = query(user, limit=2)
        detail, _, _ = query(user, resource_id='3dprinter-huakang-a-2')
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for s in statements)
    assert result['total_count'] == 11 and result['returned_count'] == 2 and result['truncated']
    assert result['metrics']['current_telemetry_count']['value'] == 2
    assert result['metrics']['reported_running_count']['value'] == 1  # PREPARE is not printing.
    assert result['metrics']['stale_count']['value'] == 8
    assert result['metrics']['unknown_current_state_count']['value'] == 9
    assert result['metrics']['physically_stopped_count']['value'] is None
    assert result['rows'][1]['current_state'] is None
    assert result['rows'][1]['observation_use'] == 'historical_only'
    assert result['freshness']['state'] == 'stale' and result['observed_at'] is None
    assert detail['as_of'] == clock.isoformat()
    assert detail['observed_at'] == detail['rows'][0]['observed_at'] == '2026-10-25T08:45:00+08:00'
    assert detail['total_count'] == 1 and detail['scope']['coverage'] == 'selected_resources'
    assert detail['rows'][0]['recent_observations_truncated'] is True
    native = client.get('/api/three-d-printing/printers/3dprinter-huakang-a-2/timeline?factory_id=huakang-a')
    assert native.status_code == 200, native.text
    assert detail['rows'][0]['state'] == native.json()['printer']['state']
    assert detail['rows'][0]['recent_observations'][0]['progress'] == native.json()['events'][0]['progress'] == 11
    assert len(detail['rows'][0]['recent_observations']) == 10
    assert not any(s in json.dumps([result,detail,source]) for s in ('FOREIGN-DEVICE','NEVER-EXPOSE','PRIVATE-SESSION','commands','credential_ref'))


def test_native_dashboard_order_more_than_page_and_changed_cursor(env):
    client, dbm, _, patch, user, clock = setup(env)
    from app.models.three_d_printing import ThreeDPrintingPrinter
    from app.services.assistant.errors import AssistantError
    from app.services import three_d_printing as domain
    with dbm.SessionLocal() as db:
        for n in range(12, 36):
            db.add(ThreeDPrintingPrinter(id=f'SYN-P-{n}',factory_id='huakang-a',machine_no=n,name=f'合成机台{n}',last_seen_at='',created_at='',updated_at=''))
        db.commit()
    native = client.get('/api/three-d-printing/dashboard?factory_id=huakang-a&compact=true')
    assert native.status_code == 200, native.text
    first, _, _ = query(user)
    second, _, _ = query(user, cursor=first['next_cursor'])
    assert [r['id'] for r in first['rows'] + second['rows']] == [p['id'] for p in native.json()['printers']]
    assert first['total_count'] == second['total_count'] == 35
    assert (first['returned_count'], second['returned_count']) == (20, 15)
    assert second['metrics'] == first['metrics']
    original = json.dumps(first, sort_keys=True)
    with dbm.SessionLocal() as db:
        db.get(ThreeDPrintingPrinter, 'SYN-P-35').current_file = 'changed.3mf'
        db.commit()
    with pytest.raises(AssistantError): query(user, cursor=first['next_cursor'])
    fresh, _, _ = query(user)
    assert fresh['scope']['filters']['source_revision'] != first['scope']['filters']['source_revision']
    assert json.dumps(first, sort_keys=True) == original
    patch.setattr(domain, 'business_now', lambda: clock+timedelta(minutes=6))
    with pytest.raises(AssistantError): query(user, cursor=fresh['next_cursor'])


def test_native_observer_exception_network_diagnostics_and_disconnect(env):
    client, dbm, _, patch, user, clock = setup(env)
    from app.models.three_d_printing import ThreeDPrintingPrinter
    from app.services import three_d_printing as domain
    # Boundary simulation is isolated. Both actual native readers and adapter
    # share the real projection; this does not claim a live network report.
    patch.setattr(domain, 'network_health_snapshot', lambda db: dict(configured=True, status='unreachable', observed_at=clock.isoformat()))
    with dbm.SessionLocal() as db:
        db.get(ThreeDPrintingPrinter,'3dprinter-huakang-a-1').status_payload_json = '{"connector":{"observation_only":true}}'
        db.commit()
    observer, _, _ = query(user, resource_id='3dprinter-huakang-a-1')
    regular, _, _ = query(user, resource_id='3dprinter-huakang-a-6')
    assert observer['rows'][0]['current_state'] == 'RUNNING' and observer['freshness']['state'] == 'fresh'
    assert regular['rows'][0]['current_state'] is None and regular['freshness']['state'] == 'stale'
    for n, result in ((1, observer), (6, regular)):
        native = client.get(f'/api/three-d-printing/printers/3dprinter-huakang-a-{n}/timeline?factory_id=huakang-a')
        assert native.status_code == 200
        assert result['rows'][0]['status_stale'] == native.json()['printer']['status_stale']
    with dbm.SessionLocal() as db:
        db.get(ThreeDPrintingPrinter,'3dprinter-huakang-a-1').connected = False
        db.commit()
    disconnected, _, _ = query(user, resource_id='3dprinter-huakang-a-1')
    assert disconnected['rows'][0]['current_state'] is None
    assert disconnected['metrics']['physically_stopped_count']['value'] is None


def test_invalid_optional_telemetry_is_unknown_without_leaking_nested_payload(env):
    _, dbm, _, _, user, _ = setup(env)
    from app.models.three_d_printing import ThreeDPrintingPrinter
    with dbm.SessionLocal() as db:
        printer = db.get(ThreeDPrintingPrinter, '3dprinter-huakang-a-1')
        printer.status_payload_json = json.dumps({'connector': {
            'nozzle_target': {'private': 'NEVER-EXPOSE-NESTED'},
            'bed_target': True, 'layer_num': float('nan'), 'total_layers': 10,
        }})
        db.commit()
    result, source, _ = query(user, resource_id='3dprinter-huakang-a-1')
    row = result['rows'][0]
    assert row['nozzle_target'] is row['bed_target'] is row['layer_num'] is None
    assert row['total_layers'] == 10
    assert set(row['unavailable_fields']) == {'nozzle_target', 'bed_target', 'layer_num'}
    assert 'telemetry_fields' in source['unknown_fields']
    encoded = json.dumps(result, allow_nan=False)
    assert 'NEVER-EXPOSE-NESTED' not in encoded


def test_slow_native_aggregation_does_not_keep_expired_telemetry_current(env):
    client, dbm, _, patch, _, clock = setup(env)
    from app.models.three_d_printing import ThreeDPrintingProductionRecord
    from app.services import three_d_printing as domain
    with dbm.SessionLocal() as db:
        db.add(ThreeDPrintingProductionRecord(id='SYN-SLOW-RECORD', factory_id='huakang-a',
            business_date=clock.date().isoformat(), machine_no=1, status='done',
            duration_hours=2, quantity=3, created_at=clock.isoformat(), updated_at=clock.isoformat()))
        db.commit()
    original = domain.frozen_totals
    def delayed_totals(record):
        patch.setattr(domain, 'business_now', lambda: clock+timedelta(seconds=31))
        return original(record)
    patch.setattr(domain, 'frozen_totals', delayed_totals)
    response = client.get('/api/three-d-printing/dashboard?factory_id=huakang-a&compact=true')
    assert response.status_code == 200, response.text
    result = response.json()
    printer = next(p for p in result['printers'] if p['machine_no'] == 1)
    assert printer['status_stale'] and not printer['connected'] and printer['state'] == 'STALE'
    assert printer['last_seen_at'] == clock.isoformat()
    assert len(result['summary']['machineHours']) == 11
    assert result['summary']['machineHours'][0] == {'machine_no': 1, 'hours': 6}


def test_strict_permissions_scope_empty_and_invalid_arguments(env):
    _, dbm, _, _, user, _ = setup(env)
    from app.models.three_d_printing import ThreeDPrintingPrinter, ThreeDPrintingPrinterStateEvent
    from app.services.assistant.errors import AssistantError
    for arguments in ({'factory_id':'huakang-b'}, {'factory_id':'authorized'}, {'resource_id':'SYN-FOREIGN'},
            {'resource_id':'missing'}, {'limit':True}, {'limit':51}, {'cursor':'not-base64'}, {'filter':{}},
            {'resource_id':'3dprinter-huakang-a-1', 'cursor':'ignored'}, {'resource_id':''}):
        with pytest.raises(AssistantError): query(user, **arguments)
    for no_read in (None, actor('alice',permissions=()), actor('alice',factory='huakang-b',permissions=('three_d_printing:read',))):
        with pytest.raises(AssistantError): query(no_read)
    with dbm.SessionLocal() as db:
        for event_row in db.scalars(select(ThreeDPrintingPrinterStateEvent)):
            db.delete(event_row)
        db.flush()
        for printer in db.scalars(select(ThreeDPrintingPrinter).where(ThreeDPrintingPrinter.factory_id=='huakang-a')):
            db.delete(printer)
        db.commit()
    empty, _, _ = query(user)
    assert empty['status'] == 'empty' and empty['total_count'] == 0
    assert empty['metrics']['reported_running_count']['value'] == 0
    assert empty['metrics']['physically_stopped_count']['value'] is None


def test_runtime_persists_actual_observation_and_revalidates_deleted_source(env):
    client, dbm, calls, patch, user, clock = setup(env)
    from app.services.assistant import runtime
    from app.models.three_d_printing import ThreeDPrintingPrinter
    patch.setattr(runtime, 'authenticate', lambda request: user)
    body = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='three-d-printing', route_name='three-d-printing-management', factory_id='huakang-a'),
        context_selection=dict(selection_id='SYN-PRINTER', resources=[dict(module_id='three-d-printing', resource_type='printer', resource_id='3dprinter-huakang-a-5')], filters={'factory_id':'huakang-a'}))
    sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert 'event: run.completed' in response.text, response.text[-2000:]
    message = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in message['content_parts'] if p['type']=='business_snapshot')
    supplied = next(m['content'] for m in calls[0]['messages'] if m['role']=='system' and m['content'].startswith('已受权业务快照'))
    assert json.loads(supplied.split('：',1)[1]) == result
    assert result['observed_at'] == (clock+timedelta(seconds=60)).isoformat()
    assert result['rows'][0]['current_state'] is None
    actions = next(part['items'] for part in message['content_parts'] if part['type'] == 'actions')
    index = next(i for i, action in enumerate(actions) if action.get('query', {}).get('printer') == '3dprinter-huakang-a-5')
    action_payload = dict(run_id=message['run_id'], index=index)
    action = client.post('/api/assistant/actions/resolve', json=action_payload)
    assert action.status_code == 200, action.text
    assert action.json()['query'] == dict(factory='huakang-a', tab='machines', printer='3dprinter-huakang-a-5')
    assert result['allowed_actions'][0]['resource_ref'] == 'three-d-printing:printer:3dprinter-huakang-a-5'
    with dbm.SessionLocal() as db:
        db.delete(db.get(ThreeDPrintingPrinter, '3dprinter-huakang-a-5')); db.commit()
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']
    assert client.get(f'/api/assistant/runs/{message["run_id"]}/export').status_code == 410
    assert client.post('/api/assistant/actions/resolve', json=action_payload).status_code == 410
    redacted = client.get(f'/api/assistant/sessions/{sid}/export')
    assert redacted.status_code == 200 and '当前不可查看' in redacted.text
    assert '自由回答' not in redacted.text and 'SYN-TASK' not in redacted.text


def test_full_default_page_fits_current_model_context(env):
    client, dbm, calls, patch, user, _ = setup(env)
    from app.services.assistant import runtime
    from app.core.config import settings
    from app.models.three_d_printing import ThreeDPrintingPrinter
    patch.setattr(runtime, 'authenticate', lambda request: user)
    patch.setattr(settings, 'assistant_context_character_budget', 24000)
    with dbm.SessionLocal() as db:
        for n in range(12, 23):
            db.add(ThreeDPrintingPrinter(id=f'SYN-P-{n}',factory_id='huakang-a',machine_no=n,name=f'合成机台{n}',last_seen_at='',created_at='',updated_at=''))
        db.commit()
    sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='three-d-printing',route_name='three-d-printing-management',factory_id='huakang-a')))
    assert 'event: run.completed' in response.text, response.text[-2000:]
    result = next(p['result'] for p in client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['content_parts'] if p['type']=='business_snapshot')
    assert result['total_count'] == 22 and result['returned_count'] == 20 and result['next_cursor']
    assert runtime.context_size(calls[0]['messages']) < 24000
