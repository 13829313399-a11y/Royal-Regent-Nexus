"""Versioned actual return dates never rewrite stock or old evidence."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_transaction_guards_api import BASE, outbound, ledger, draft, confirm
from test_carton_return_dates import setup, save_and_confirm
from test_carton_supplier_settlement_api import view, action


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def current_state(identifier):
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonInventoryMovement
    from app.services.carton_return_dates import state
    with SessionLocal() as db:
        return state(db, db.get(CartonInventoryMovement, identifier))


def command(evidence, day='2026-10-01', **extra):
    return dict(factory_id='huaxing', request_id=uuid4().hex,
        expected_evidence_revision=evidence['revision'], expected_evidence_fingerprint=evidence['fingerprint'],
        return_date=day, reason='退货交接单日期填错，经手人核实更正', **extra)


def create_return(client, row):
    response = client.post(BASE + '/inventory/movements', json=outbound(row, 2, issue_kind='RETURN', return_date='2026-09-30'))
    assert response.status_code == 201, response.text
    login_as(client, 'carton_supervisor')
    return response.json()['id']


def stock_facts(client):
    return [{key: row[key] for key in ('id', 'occurred_at', 'quantity', 'unit_price', 'balance', 'unit', 'currency', 'source_type')}
            for row in ledger(client)]


def test_correction_versions_replay_and_aba_keep_initial_evidence_and_stock_immutable(monkeypatch):
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch); identifier = create_return(client, row)
        initial = current_state(identifier)
        before = stock_facts(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
        from app.services import carton_return_dates as dates
        with SessionLocal() as db:
            original = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == initial['event_id'])).detail_json
        url = BASE + f'/inventory/movements/{identifier}/return-date/corrections'
        payload = command(initial)
        corrected = client.post(url, json=payload)
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()['date_evidence']['revision'] == 2
        assert corrected.json()['return_date'] == '2026-10-01'
        assert corrected.json()['posting_date'] == '2026-10-05'
        assert client.post(url, json=payload).json() == corrected.json()
        assert client.post(url, json={**payload, 'return_date': '2026-10-02'}).status_code == 409
        assert client.post(url, json=command(initial, '2026-10-02')).status_code == 409
        latest = current_state(identifier)
        assert latest['fingerprint'] != initial['fingerprint']
        assert client.post(url, json=command(latest, latest['return_date'])).status_code == 422
        assert client.post(url, json=command(latest, '2026-10-06')).status_code == 422
        moved = next(source for source in view(client)['sources'] if source['source_key'] == 'RETURN:' + identifier)
        assert moved['acceptance_date'] == '2026-10-01'
        back = client.post(url, json=command(latest, '2026-09-30'))
        assert back.status_code == 200, back.text
        assert back.json()['date_evidence']['revision'] == 3
        assert back.json()['date_evidence']['fingerprint'] not in {initial['fingerprint'], latest['fingerprint']}
        assert stock_facts(client) == before
        with SessionLocal() as db:
            assert db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == initial['event_id'])).detail_json == original
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == identifier,
                CartonAuditEvent.event_type == dates.CORRECTION_EVENT).order_by(CartonAuditEvent.sequence)))
            assert len(events) == 2
            assert json.loads(events[0].detail_json)['previous_event_id'] == initial['event_id']
            assert json.loads(events[1].detail_json)['previous_event_id'] == events[0].id
            assert len(dates.history(db, db.get(CartonInventoryMovement, identifier))) == 3


def test_date_round_trip_never_restores_an_old_monthly_source_fingerprint(monkeypatch):
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch); identifier = create_return(client, row)
        initial = view(client, '2026-09')['source_fingerprint']
        url = BASE + f'/inventory/movements/{identifier}/return-date/corrections'
        moved = client.post(url, json=command(current_state(identifier), '2026-10-01'))
        assert moved.status_code == 200, moved.text
        restored = client.post(url, json=command(current_state(identifier), '2026-09-30'))
        assert restored.status_code == 200, restored.text
        current = view(client, '2026-09')
        assert current['source_fingerprint'] != initial
        source = next(item for item in current['sources'] if item['source_key'] == 'RETURN:' + identifier)
        assert source['return_date_revision'] == 3
        assert source['return_date_evidence_fingerprint'] == current_state(identifier)['fingerprint']


def test_correction_protects_both_supplier_months_and_reversed_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch)
        # Existing actual-dated returns are not enrolled retroactively. Keep
        # this fixture on that supported path; the collaborative journey tests
        # cover the additional receipt/credit gates for newly enrolled returns.
        from app.services import carton_return_collaboration
        monkeypatch.setattr(carton_return_collaboration, 'open_return', lambda *args: None)
        identifier = create_return(client, row)
        initial = current_state(identifier)
        url = BASE + f'/inventory/movements/{identifier}/return-date/corrections'
        body = command(initial)
        receipt = draft(client, row, 1, acceptance_date='2026-10-02', lines=[dict(
            order_line_id=row['lines'][1]['id'], delivered_quantity='1', received_quantity='1', unit_price='2')])
        assert receipt.status_code == 201, receipt.text
        assert confirm(client, receipt.json()).status_code == 200
        september = save_and_confirm(client, monkeypatch, '2026-09')
        before = stock_facts(client)
        assert client.post(url, json=body).status_code == 409
        assert action(client, september, 'reopen', reason='原退货日期核实后重新核对').status_code == 200
        october = save_and_confirm(client, monkeypatch, '2026-10')
        assert client.post(url, json=body).status_code == 409
        assert action(client, october, 'reopen', reason='核对退货正确归属日期').status_code == 200
        login_as(client, 'warehouse_keeper')
        assert client.post(url, json=body).status_code == 403
        login_as(client, 'carton_supervisor')
        accepted = client.post(url, json=body)
        assert accepted.status_code == 200, accepted.text
        assert stock_facts(client) == before
        reversed_source = client.post(BASE + f'/inventory/movements/{identifier}/reverse', json=dict(factory_id='huaxing', reason='核实退货数量后冲销记录'))
        assert reversed_source.status_code == 201, reversed_source.text
        assert client.post(url, json=command(current_state(identifier), '2026-10-02')).status_code == 409
        assert client.post(url, json=body).json() == accepted.json()  # Successful retry remains a frozen original result.


def test_concurrent_corrections_of_one_date_version_have_one_winner(monkeypatch):
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch); identifier = create_return(client, row)
        initial = current_state(identifier); barrier = Barrier(2)
        url = BASE + f'/inventory/movements/{identifier}/return-date/corrections'
        bodies = [command(initial, '2026-10-01'), command(initial, '2026-10-02')]
        before = stock_facts(client)
        def send(body):
            barrier.wait(timeout=15)
            return client.post(url, json=body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send, body) for body in bodies]
            responses = [future.result(timeout=60) for future in futures]
        assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
        assert current_state(identifier)['revision'] == 2
        assert stock_facts(client) == before


@pytest.mark.parametrize('status', ['active', 'disabled'])
def test_correction_refreshes_permissions_after_iam_then_factory_lock(monkeypatch, status):
    from fastapi import HTTPException
    from app.services import carton_special_requests as special, carton_return_dates as dates, identity_policy
    from app.services.auth import AuthContext, AuthGrantContext
    def actor(permissions):
        grant = AuthGrantContext('R', 'Supervisor', 'huaxing', 'carton', frozenset('carton_procurement:' + item for item in permissions))
        return AuthContext('U1', 'supervisor', '主管', (), (), grant.permissions, ('huaxing',), ('carton',), grants=(grant,))
    old, fresh = actor(['closing_manage', 'order_adjust']), actor(['closing_manage'])
    order = []
    monkeypatch.setattr(identity_policy, 'lock_mutation', lambda db: order.append('IAM'))
    monkeypatch.setattr(special.core, '_lock_receipt_factory', lambda db, factory: order.append('factory'))
    monkeypatch.setattr(special, 'build_auth_context', lambda db, row: order.append('context') or fresh)
    db = SimpleNamespace(get=lambda model, identifier: order.append('actor') or SimpleNamespace(id='U1', status=status))
    with pytest.raises(HTTPException) as error:
        dates.correct(db, 'M1', SimpleNamespace(factory_id='huaxing'), old)
    assert error.value.status_code == 403
    assert order[:3] == ['IAM', 'factory', 'actor']
    assert ('context' in order) is (status == 'active')
