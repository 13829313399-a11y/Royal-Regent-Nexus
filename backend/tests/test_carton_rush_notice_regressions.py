import json
from types import SimpleNamespace

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login

BASE = '/api/carton-procurement'
PORTAL = '/api/carton-supplier'


def test_rush_ack_binds_same_second_marking_and_retries_current_version(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, 'now_text', lambda: '2026-10-22T10:00:00+08:00')
        login_as(client, 'admin')
        marking = {'factory_id': 'huaxing', 'rush': True, 'reason': '优先安排'}
        assert client.post(BASE + f"/orders/{order['order_no']}/rush", json=marking).status_code == 200
        supplier_login(client)
        old_page = client.get(PORTAL + '/workspace', params={'factory_id': 'huaxing'}).json()['orders'][0]
        login_as(client, 'admin')
        assert client.post(BASE + f"/orders/{order['order_no']}/rush", json={
            'factory_id': 'huaxing', 'rush': False}).status_code == 200
        assert client.post(BASE + f"/orders/{order['order_no']}/rush", json=marking).status_code == 200
        supplier_login(client)
        fresh = client.get(PORTAL + '/workspace', params={'factory_id': 'huaxing'}).json()['orders'][0]
        assert old_page['rush_at'] == fresh['rush_at']
        assert old_page['rush_version'] != fresh['rush_version']
        url = PORTAL + f"/orders/{order['id']}/rush-ack"
        assert client.post(url, json={'factory_id': 'huaxing'}).status_code == 409
        stale = client.post(url, json={'factory_id': 'huaxing', 'expected_rush_version': old_page['rush_version']})
        assert stale.status_code == 409, stale.text
        assert client.post(url, json={'factory_id': 'huakang-a', 'expected_rush_version': fresh['rush_version']}).status_code in (403, 404)
        payload = {'factory_id': 'huaxing', 'expected_rush_version': fresh['rush_version']}
        first = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        second = client.post(url, json=payload)
        assert second.status_code == 200, second.text
        assert second.json()['rush_ack_at'] == first.json()['rush_ack_at']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            events = list(db.scalars(select(CartonAuditEvent).where(
                CartonAuditEvent.entity_id == order['id'], CartonAuditEvent.event_type == 'SUPPLIER_RUSH_ACKNOWLEDGED')))
            assert len(events) == 1
            assert json.loads(events[0].detail_json)['rush_version'] == fresh['rush_version']


def test_pending_promise_paging_skips_acks_without_history_cutoffs(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            def event(identifier, kind, entity, detail, entity_type='carton_order'):
                return CartonAuditEvent(id=identifier, factory_id='huaxing', event_type=kind,
                    entity_type=entity_type, entity_id=entity, detail_json=json.dumps(detail),
                    actor_user_id='supplier-test', actor_name='regression', created_at='2026-10-22T10:00:00+08:00')
            for index in range(22):
                db.add(event(f'NOTICE-{index:03}', 'SUPPLIER_PAPER_ACCEPTED', order['id'], {
                    'line_id': order['lines'][0]['id'], 'promise_updated': True,
                    'previous_promised_date': '2026-09-01', 'promised_date': f'2026-09-{index + 2:02}'}))
            db.add(event('ACK-OLD', 'SUPPLIER_PROMISE_ACKNOWLEDGED', 'CHANGE:NOTICE-000', {}, 'carton_promise_notice'))
            for index in range(501):
                db.add(event(f'ACK-{index}', 'SUPPLIER_PROMISE_ACKNOWLEDGED', f'CHANGE:OTHER-{index}', {}, 'carton_promise_notice'))
            for index in range(301):
                db.add(event(f'INITIAL-{index}', 'SUPPLIER_PAPER_ACCEPTED', order['id'], {'promise_updated': False}))
            db.commit()
        params = {'factory_id': 'huaxing', 'limit': 20}
        first = client.get(BASE + '/supplier-promise-changes', params=params).json()
        assert first['change_total'] == first['total'] == 21 and first['has_more']
        assert len(first['changes']) == 20
        assert 'CHANGE:NOTICE-000' in first['acknowledged']
        second = client.get(BASE + '/supplier-promise-changes', params={**params, 'offset': 20}).json()
        assert [row['id'] for row in second['changes']] == ['NOTICE-001']
        assert not second['has_more']
        for row in first['changes']:
            result = client.post(BASE + '/promise-notices/ack', json={'factory_id': 'huaxing', 'key': row['key']})
            assert result.status_code == 200, result.text
        remaining = client.get(BASE + '/supplier-promise-changes', params=params).json()
        assert remaining['total'] == 1
        assert [row['id'] for row in remaining['changes']] == ['NOTICE-001']
        assert client.post(BASE + '/promise-notices/ack', json={
            'factory_id': 'huaxing', 'key': remaining['changes'][0]['key']}).status_code == 200
        assert client.get(BASE + '/supplier-promise-changes', params=params).json()['total'] == 0
        assert client.get(BASE + '/supplier-promise-changes', params={**params, 'offset': -1}).status_code == 422


def test_late_promises_filter_acknowledged_before_paging(monkeypatch):
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    orders = [SimpleNamespace(id=str(i), order_no=str(i), customer_name='customer') for i in range(23)]
    acknowledged = [f'LATE:{i}:2026-10-30' for i in range(20)]
    monkeypatch.setattr(core, 'promise_notice_acks', lambda db, factory: acknowledged)
    monkeypatch.setattr(core, 'supplier_promise_changes', lambda *args, **kwargs: [])
    monkeypatch.setattr(core, 'list_orders', lambda *args, **kwargs: (23, orders))
    monkeypatch.setattr(core, 'get_order_lines', lambda *args: [])
    monkeypatch.setattr(portal, 'acceptance_summary', lambda *args: {'delivery_differences': [
        {'difference_days': 3, 'promised_date': '2026-10-30', 'packaging_type': 'carton'}]})
    result = core.supplier_promise_notices(None, 'huaxing', 2)
    assert result['total'] == result['late_total'] == 3
    assert [row['order_no'] for row in result['late']] == ['20', '21']
    assert result['has_more']
    assert [row['order_no'] for row in core.supplier_promise_notices(None, 'huaxing', 2, 2)['late']] == ['22']
