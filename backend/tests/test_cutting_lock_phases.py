"""Read-capture and committed-payment replay boundaries on disposable fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from sqlalchemy.orm import Session
from test_cutting_ops import client, user, BASE
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees
from test_cutting_payments import paid_setup, body, URL
from test_cutting_materials import bridge
from test_cutting_usage import custody, consume
from test_cutting_usage import write as usage_write
from app.services import cutting_workspace as workspace, cutting_usage as usage


def test_inventory_replay_releases_locks_and_retains_one_captured_instant(custody, monkeypatch):
    p = custody
    original = usage.wh.apply_entry
    changed = False
    with Session(p.engine) as db:
        def replay(*args):
            nonlocal changed
            assert not db.in_transaction(), 'presentation must not reacquire a DB transaction'
            if not changed:
                changed = True
                # A genuine later writer can commit while this captured view
                # is replaying, but cannot partially leak into this response.
                consume(p)
            return original(*args)
        monkeypatch.setattr(usage.wh, 'apply_entry', replay)
        first = workspace.inventory(db)
        second = workspace.inventory(db)
        assert not db.in_transaction()
    assert first['data'][0]['remaining_quantity'] == '4'
    assert first['data'][0]['consumed_quantity'] == '0'
    assert second['data'][0]['remaining_quantity'] == '1.5'
    assert second['data'][0]['consumed_quantity'] == '2'
    assert 'price' not in second['data'][0]


def test_committed_payment_retry_needs_no_writer_lock(paid_setup, monkeypatch):
    p = paid_setup
    data = body(p)
    expected = ok(p.post(URL+'/save', json=data))
    def unexpected(*args, **kwargs):
        raise AssertionError('committed retry must not execute payment again')
    from app.api import cutting_operations as api
    monkeypatch.setattr(api.payments, 'execute', unexpected)
    with p.engine.connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
        writer.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            response = pool.submit(lambda: p.post(URL+'/save', json=data)).result(timeout=3)
            assert ok(response) == expected
        finally:
            writer.rollback()
    assert p.post(URL+'/save', json=dict(data, evidence='different')).status_code == 409
    p.cutting_auth['user'] = replace(p.cutting_auth['user'], id='another-actor')
    assert p.post(URL+'/save', json=data).status_code == 409
    p.cutting_auth['user'] = user('read', 'payment_read', department='accounting')
    assert p.post(URL+'/save', json=data).status_code == 403


def test_payment_basis_and_preview_release_before_json(paid_setup, monkeypatch):
    from app.api import cutting_operations as api
    p = paid_setup
    original = api.JSONResponse
    responses = []
    def encoded(*args, **kwargs):
        assert p.engine.pool.checkedout() == 0
        responses.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(api, 'JSONResponse', encoded)
    data = body(p)
    assert p.post(BASE+'/payment-preview', json=data).status_code == 200
    assert len(responses) == 2


def test_cost_snapshot_is_detached_and_later_price_changes_only_next_read(custody, monkeypatch):
    p = custody
    consume(p)
    usage_write(p, 'price', issue_id=p.issue_id, unit_cost='3', currency='HKD', price_reference='Synthetic batch evidence')
    original = usage.read
    changed = False
    with Session(p.engine) as db:
        def detached(session, line_id, **kwargs):
            nonlocal changed
            if kwargs.get('_snapshot') is None:
                return original(session, line_id, **kwargs)
            assert session is None and not db.in_transaction()
            snapshot = kwargs['_snapshot']
            assert snapshot['production'] is not None
            assert all(not hasattr(value, '_sa_instance_state') for value in snapshot['production'][2].values())
            if not changed:
                changed = True
                usage_write(p, 'price', issue_id=p.issue_id, unit_cost='4', currency='HKD', price_reference='Later synthetic price')
            return original(session, line_id, **kwargs)
        monkeypatch.setattr(usage, 'read', detached)
        first = workspace.cost_overview(db)
        second = workspace.cost_overview(db)
        assert not db.in_transaction()
    assert first['currencies']['HKD']['normal'] == '6.00'
    assert second['currencies']['HKD']['normal'] == '8.00'
