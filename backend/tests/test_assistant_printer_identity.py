"""Current fleet compatibility through native auth, without hardware or network."""
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import event, select

from test_assistant_api import env, payload, session, verified_profile


@pytest.fixture
def fleet(env, tmp_path):
    import httpx
    from app.core.config import settings
    from app.models.auth import AuthPermission, AuthRole, AuthRolePermission, AuthUserRole, EmployeeProfile
    from app.models.three_d_printing import ThreeDPrintingPrinter, ThreeDPrintingSetting
    from app.services import auth, three_d_printing as native
    from app.services.assistant import runtime

    client, dbm, calls, patch = env
    clock = datetime.fromisoformat('2026-10-29T12:00:00+08:00')
    patch.setattr(settings, 'authz_mode', 'enforce')
    patch.setattr(settings, 'assistant_daily_token_budget', None)
    patch.setattr(settings, 'assistant_max_tool_rounds', 0)
    patch.setattr(native, 'business_now', lambda: clock)
    verified_profile(tmp_path)

    def deny_network(*args, **kwargs):
        raise AssertionError('Printer identity acceptance must not reach a network')

    async def deny_async_network(*args, **kwargs):
        deny_network()

    patch.setattr(httpx.HTTPTransport, 'handle_request', deny_network)
    patch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', deny_async_network)
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'three_d_printing:read'))
        assert permission is not None
        db.add(AuthRole(id='fleet-reader', code='fleet-reader', name='Synthetic printer reader'))
        db.flush()
        db.add(AuthRolePermission(id='fleet-read', role_id='fleet-reader', permission_id=permission.id))
        db.add(AuthUserRole(id='fleet-assignment', user_id='alice', role_id='fleet-reader',
                           factory_id='huakang-a', department='production'))
        db.add(EmployeeProfile(user_id='alice', primary_factory_id='huakang-a',
                               primary_department='production', position='Synthetic reader', identity_mode='legacy'))
        db.get(ThreeDPrintingSetting, 'huakang-a').machine_count = 16
        # Move existing physical identities first; numbers 6-8 are reused by additions.
        # Descending flushes also respect the native unique (factory, machine_no).
        for old_number in range(11, 5, -1):
            printer = db.get(ThreeDPrintingPrinter, f'3dprinter-huakang-a-{old_number}')
            printer.machine_no = old_number + 3
            printer.name = f'SYN-OLD-{old_number}-NOW-{old_number + 3}'
            db.flush()
        for number in (6, 7, 8, 15, 16):
            db.add(ThreeDPrintingPrinter(id=f'SYN-ADDED-{number}', factory_id='huakang-a',
                                        machine_no=number, name=f'SYN-NEW-{number}',
                                        created_at=clock.isoformat(), updated_at=clock.isoformat()))
        db.flush()
        for printer in db.scalars(select(ThreeDPrintingPrinter)):
            printer.last_seen_at = (clock - timedelta(seconds=3)).isoformat()
            printer.connected = True
            printer.state = 'RUNNING' if printer.machine_no in (9, 16) else 'IDLE'
            printer.current_file = f'SYN-{printer.id}.3mf'
            printer.status_payload_json = '{"private_connection":"NEVER-EXPOSE-DEVICE-CONNECTION"}'
        db.add(ThreeDPrintingPrinter(id='SYN-FOREIGN', factory_id='huakang-b', machine_no=99,
                                    name='NEVER-EXPOSE-FOREIGN-PRINTER',
                                    created_at=clock.isoformat(), updated_at=clock.isoformat()))
        db.commit()
    assert auth.get_current_user not in client.app.dependency_overrides
    assert runtime.authenticate.__module__ == 'app.services.assistant.runtime'
    return client, dbm, calls, patch, clock


def send_selected(client, printer_id):
    sid = session(client)
    body = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='three-d-printing', route_name='three-d-printing-management', factory_id='huakang-a'),
        context_selection=dict(selection_id='SYN-STABLE-IDENTITY',
            resources=[dict(module_id='three-d-printing', resource_type='printer', resource_id=printer_id)],
            filters={'factory_id': 'huakang-a'}))
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert response.status_code == 200 and 'event: run.completed' in response.text, response.text[-2000:]
    messages = client.get(f'/api/assistant/sessions/{sid}/messages')
    assert messages.status_code == 200, messages.text
    message = messages.json()['items'][-1]
    result = next(part['result'] for part in message['content_parts'] if part['type'] == 'business_snapshot')
    actions = next(part['items'] for part in message['content_parts'] if part['type'] == 'actions')
    index = next(i for i, action in enumerate(actions) if action.get('query', {}).get('printer') == printer_id)
    return sid, message, result, dict(run_id=message['run_id'], index=index)


def test_full_fleet_and_sixteenth_printer_match_native_without_writes(fleet):
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services.assistant import business

    client, dbm, calls, _, clock = fleet
    native = client.get('/api/three-d-printing/dashboard', params={'factory_id': 'huakang-a', 'compact': True})
    assert native.status_code == 200, native.text
    native_rows = native.json()['printers']
    assert [p['machine_no'] for p in native_rows] == list(range(1, 17))
    with dbm.SessionLocal() as db:
        user = build_auth_context(db, db.get(AuthUser, 'alice'))
    statements = []

    def capture(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        first, _, _ = business.query(user, 'get_printer_status', {'factory_id': 'huakang-a', 'limit': 10}, 'SYN-FLEET')
        second, _, _ = business.query(user, 'get_printer_status',
            {'factory_id': 'huakang-a', 'limit': 10, 'cursor': first['next_cursor']}, 'SYN-FLEET')
        selected, source, actions = business.query(user, 'get_printer_status',
            {'factory_id': 'huakang-a', 'resource_id': 'SYN-ADDED-16'}, 'SYN-16')
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for s in statements)
    assert [r['id'] for r in first['rows'] + second['rows']] == [p['id'] for p in native_rows]
    assert first['total_count'] == second['total_count'] == 16
    assert (first['returned_count'], second['returned_count']) == (10, 6)
    assert second['metrics'] == first['metrics']
    assert first['metrics']['current_telemetry_count']['value'] == 16
    assert first['metrics']['reported_running_count']['value'] == 2
    assert first['metrics']['physically_stopped_count']['value'] is None
    assert selected['rows'][0]['id'] == 'SYN-ADDED-16' and selected['rows'][0]['machine_no'] == 16
    assert selected['observed_at'] == (clock - timedelta(seconds=3)).isoformat()
    assert source['resources'][0]['resource_id'] == actions[0]['query']['printer'] == 'SYN-ADDED-16'
    assert not any(x in json.dumps([first, second, selected, source, actions]) for x in
                   ('NEVER-EXPOSE-DEVICE-CONNECTION', 'NEVER-EXPOSE-FOREIGN-PRINTER'))
    assert not calls


def test_renumbered_selection_actions_and_deleted_history_never_alias_display_number(fleet):
    from app.models.three_d_printing import ThreeDPrintingPrinter

    client, dbm, calls, _, clock = fleet
    stable_id = '3dprinter-huakang-a-6'  # The original physical printer is now number 9.
    sid, message, result, action = send_selected(client, stable_id)
    assert result['rows'][0]['id'] == stable_id and result['rows'][0]['machine_no'] == 9
    assert 'SYN-ADDED-6' not in json.dumps(result)
    resolved = client.post('/api/assistant/actions/resolve', json=action)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['query'] == dict(factory='huakang-a', tab='machines', printer=stable_id)
    native = client.get(f'/api/three-d-printing/printers/{stable_id}/timeline', params={'factory_id': 'huakang-a'})
    assert native.status_code == 200 and native.json()['printer']['machine_no'] == 9

    with dbm.SessionLocal() as db:
        db.delete(db.get(ThreeDPrintingPrinter, stable_id))
        db.flush()
        db.add(ThreeDPrintingPrinter(id='SYN-REPLACEMENT-9', factory_id='huakang-a',
                                    machine_no=9, name='NEVER-EXPOSE-REPLACEMENT-PRINTER',
                                    created_at=clock.isoformat(), updated_at=clock.isoformat()))
        db.commit()
    history = client.get(f'/api/assistant/sessions/{sid}/messages')
    assert history.status_code == 200 and history.json()['items'][-1]['unavailable']
    assert client.post('/api/assistant/actions/resolve', json=action).status_code == 410
    assert client.get(f'/api/assistant/runs/{message["run_id"]}/export').status_code == 410
    assert client.get(f'/api/three-d-printing/printers/{stable_id}/timeline', params={'factory_id': 'huakang-a'}).status_code == 404
    assert not any(x in history.text for x in ('SYN-REPLACEMENT-9', 'NEVER-EXPOSE-REPLACEMENT-PRINTER'))
    assert len(calls) == 1
