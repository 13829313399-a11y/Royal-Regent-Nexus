"""Actual return month is independent of stock posting and carrying cost."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_transaction_guards_api import BASE, order, draft, confirm, outbound, ledger
from test_carton_supplier_settlement_api import view, payload, action


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def setup(client, monkeypatch):
    login_as(client, 'admin')
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, 'business_now', lambda: datetime(2026, 10, 5, 12))
    row = order(client)
    received = draft(client, row, 10, acceptance_date='2026-09-20', lines=[dict(order_line_id=line['id'],
        delivered_quantity='10', received_quantity='10', unit_price='2') for line in row['lines']])
    assert received.status_code == 201, received.text
    posted = confirm(client, received.json())
    assert posted.status_code == 200, posted.text
    return row


def confirm_collaborative_returns(client, sources):
    """Finish real supplier receipt/credit evidence before reconciling new returns."""
    from app.db import SessionLocal
    from app.models.auth import AuthUser, AuthUserAuthorizationRevision, EmployeeProfile
    from app.services.auth import make_password_hash
    from test_carton_supplier_portal import PASSWORD, grant_supplier_permissions, supplier_login
    returns = [source for source in sources if source.get('return_agreement')]
    if not returns:
        return
    with SessionLocal() as db:
        exists = db.get(AuthUser, 'supplier-test') is not None
        if not exists:
            salt, digest = make_password_hash(PASSWORD)
            db.add(AuthUser(id='supplier-test', username='supplier-test', display_name='供应商测试',
                password_salt=salt, password_hash=digest, status='active', force_password_change=0,
                created_at='2026-09-21', updated_at='2026-09-21'))
            db.add(AuthUserAuthorizationRevision(user_id='supplier-test', revision=1, updated_at='2026-09-21'))
            db.add(EmployeeProfile(user_id='supplier-test', primary_factory_id='huaxing',
                primary_department='pmc-warehouse', position='供应商联系人', confirmation_status='confirmed',
                created_at='2026-09-21', updated_at='2026-09-21'))
            db.commit()
    if not exists:
        grant_supplier_permissions()

    def detail(identifier, external=False):
        base = '/api/carton-supplier' if external else BASE
        response = client.get(base + f'/returns/{identifier}', params={'factory_id': 'huaxing'})
        assert response.status_code == 200, response.text
        return response.json()

    def act(row, name, external=False, **values):
        base = '/api/carton-supplier' if external else BASE
        body = dict(factory_id='huaxing', request_id=uuid4().hex, expected_revision=row['revision'],
            source_fingerprint=row['source_fingerprint'], action=name, reason='核实真实交接及独立贷项凭证', **values)
        response = client.post(base + f"/returns/{row['movement_id']}/actions", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    for source in returns:
        supplier_login(client)
        row = detail(source['source_key'].removeprefix('RETURN:'), external=True)
        if not row['credit']:
            row = act(row, 'RECEIVE', external=True, quantity=row['remaining_quantity'],
                receipt_date='2026-10-05', document_no='SIGN-' + row['movement_id'])
            row = act(row, 'PROPOSE_CREDIT', external=True, unit_price='3',
                credit_date='2026-10-05', document_no='CREDIT-' + row['movement_id'])
            login_as(client, 'carton_supervisor')
            row = detail(row['movement_id'])
            act(row, 'CONFIRM_CREDIT', target_event_id=row['credit']['id'])
    login_as(client, 'carton_supervisor')


def save_and_confirm(client, monkeypatch, period):
    login_as(client, 'carton_supervisor')
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, 'business_now', lambda: datetime(2026, 11, 5, 12))
    work = view(client, period)
    confirm_collaborative_returns(client, work['sources'])
    work = view(client, period)
    body = payload(work)
    for line, source in zip(body['lines'], work['sources']):
        if source['kind'] == 'RETURN':
            qty = Decimal(source['quantity'])
            agreement = source.get('return_agreement') or {}
            price = Decimal(source['unit_price']) if agreement else Decimal(3)
            line.update(unit_price=str(price), amount=str(qty * price), approved_return_unit_price=str(price),
                        credit_document_no=agreement.get('credit_document_no', 'CREDIT-' + line['id']),
                        credit_date=agreement.get('credit_date', '2026-10-05'), note='主管核实原退货贷项凭证')
    saved = client.post(BASE + '/supplier-settlements', json=body)
    assert saved.status_code == 200, saved.text
    result = action(client, saved.json())
    assert result.status_code == 200, result.text
    return result.json()


def test_all_return_entries_use_actual_month_without_backdating_stock_or_inventing_credit(monkeypatch):
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch)
        command = outbound(row, 2, issue_kind='RETURN', document_no='RET-ACTUAL')
        command.pop('return_date', None)
        assert client.post(BASE + '/inventory/movements', json=command).status_code == 422
        assert client.post(BASE + '/inventory/movements', json={**command, 'return_date': '2026-10-06'}).status_code == 422
        assert client.post(BASE + '/inventory/movements', json={**command, 'return_date': '2026-02-30'}).status_code == 422
        command['return_date'] = '2026-09-30'
        single = client.post(BASE + '/inventory/movements', json=command)
        assert single.status_code == 201, single.text
        assert single.json()['return_date'] == '2026-09-30'
        assert single.json()['occurred_at'].startswith('2026-10-05') and Decimal(single.json()['unit_price']) == 2
        assert client.post(BASE + '/inventory/movements', json=command).json() == single.json()
        assert client.post(BASE + '/inventory/movements', json={**command, 'return_date': '2026-09-29'}).status_code == 409
        bulk = dict(factory_id='huaxing', request_id=uuid4().hex, issue_kind='RETURN', document_no='RET-BULK',
                    reason='供应商核实退回纸品', items=[dict(order_line_id=line['id'], quantity=index + 1)
                        for index, line in enumerate(row['lines'])])
        assert client.post(BASE + '/inventory/movements/bulk', json=bulk).status_code == 422
        bulk['return_date'] = '2026-09-30'
        sent = client.post(BASE + '/inventory/movements/bulk', json=bulk)
        assert sent.status_code == 201, sent.text
        assert all(item['return_date'] == '2026-09-30' for item in sent.json())
        assert client.post(BASE + '/inventory/movements/bulk', json=bulk).json() == sent.json()
        # A pre-date bulk receipt can still be replayed after later date evidence exists.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from app.schemas.carton_procurement import CartonInventoryBulkCreate
        from sqlalchemy import select
        legacy_bulk = {key: value for key, value in bulk.items() if key != 'return_date'}
        old_body = CartonInventoryBulkCreate(**legacy_bulk).model_dump(exclude={'request_id', 'return_date'})
        for item in old_body['items']:
            item['quantity'] = format(item['quantity'].quantize(Decimal('.0001')), 'f')
        old_hash = hashlib.sha256(json.dumps(['bulk', old_body], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        with SessionLocal() as db:
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'INVENTORY_BULK_OUTBOUND_CREATED'))
            detail = json.loads(event.detail_json); detail['request']['fingerprint'] = old_hash
            for item in detail['request']['result']:
                for field in ('return_date', 'return_date_basis', 'return_posting_date', 'issue_kind'):
                    item.pop(field, None)
            event.detail_json = json.dumps(detail); db.commit()
        before_retry = ledger(client)
        replay = client.post(BASE + '/inventory/movements/bulk', json=legacy_bulk)
        assert replay.status_code == 201, replay.text
        assert [item['id'] for item in replay.json()] == [item['id'] for item in sent.json()]
        assert len(ledger(client)) == len(before_retry)
        current = client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['items'][0]
        whole = dict(factory_id='huaxing', expected_revision=current['revision'], reason='全部余货退回供应商')
        assert client.post(BASE + f"/orders/{row['order_no']}/return", json=whole).status_code == 422
        whole['return_date'] = '2026-09-30'
        returned = client.post(BASE + f"/orders/{row['order_no']}/return", json=whole)
        assert returned.status_code == 200, returned.text
        september = view(client, '2026-09')
        returns = [source for source in september['sources'] if source['kind'] == 'RETURN']
        assert len(returns) == 5 and all(source['date_basis'] == 'RETURN_ACTUAL' for source in returns)
        assert all(source['acceptance_date'] == '2026-09-30' and source['posting_date'] == '2026-10-05' for source in returns)
        assert all(source['unit_price'] is None and source['amount'] is None for source in returns)
        assert not any(source['kind'] == 'RETURN' for source in view(client)['sources'])
        history = client.get(BASE + '/inventory/movement-history', params={'factory_id': 'huaxing'}).json()['items']
        assert all(item['return_date'] == '2026-09-30' for item in history if item['issue_kind'] == 'RETURN')
        save_and_confirm(client, monkeypatch, '2026-09')
        reverse = client.post(BASE + f"/inventory/movements/{single.json()['id']}/reverse", json=dict(factory_id='huaxing', reason='更正原退货交接记录'))
        assert reverse.status_code == 409 and '有效签收、贷项或退款证据' in reverse.text


def test_legacy_return_keeps_fingerprint_and_retry_until_supervisor_verifies_both_open_months(monkeypatch):
    from sqlalchemy import select, delete
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch)
        command = outbound(row, 2, issue_kind='RETURN', document_no='LEGACY-RETURN')
        command.pop('return_date', None)
        made = client.post(BASE + '/inventory/movements', json={**command, 'return_date': '2026-10-02'})
        assert made.status_code == 201, made.text
        movement_id = made.json()['id']
        # Persist the pre-upgrade request shape and date-less source evidence.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
        from app.schemas.carton_procurement import CartonInventoryMovementCreate
        from app.services.carton_return_dates import EVENT
        from app.services.carton_return_collaboration import OPEN
        body = CartonInventoryMovementCreate(**command).model_dump(exclude={'request_id', 'return_date'})
        body['quantity'] = format(body['quantity'].quantize(Decimal('.0001')), 'f')
        old_fingerprint = hashlib.sha256(json.dumps(['single', body], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        with SessionLocal() as db:
            # Pre-upgrade history has neither actual-date nor collaboration
            # enrollment evidence; reads must not enroll those rows implicitly.
            db.execute(delete(CartonAuditEvent).where(CartonAuditEvent.event_type.in_([EVENT, OPEN]), CartonAuditEvent.entity_id == movement_id))
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == movement_id,
                CartonAuditEvent.event_type == 'INVENTORY_MOVEMENT_CREATED'))
            detail = json.loads(event.detail_json); detail['request']['fingerprint'] = old_fingerprint
            for field in ('return_date', 'return_date_basis', 'return_posting_date', 'issue_kind'):
                detail['request']['result'][0].pop(field, None)
            event.detail_json = json.dumps(detail)
            db.commit()
        previous_ledger = ledger(client)
        replay = client.post(BASE + '/inventory/movements', json=command)
        assert replay.status_code == 201 and replay.json()['id'] == movement_id
        assert len(ledger(client)) == len(previous_ledger)
        work = view(client)
        legacy = next(source for source in work['sources'] if source['kind'] == 'RETURN')
        assert legacy['date_basis'] == 'RETURN_POSTING' and 'return_date' not in legacy and 'posting_date' not in legacy
        baseline_fingerprint = work['source_fingerprint']
        confirmed = save_and_confirm(client, monkeypatch, '2026-10')
        assert view(client)['source_fingerprint'] == baseline_fingerprint
        assert view(client)['documents'][0]['stale'] is False
        # A new September return does not mutate the confirmed October source snapshot.
        fresh = client.post(BASE + '/inventory/movements', json=outbound(row, 1, issue_kind='RETURN', return_date='2026-09-30'))
        assert fresh.status_code == 201, fresh.text
        assert view(client)['documents'][0]['stale'] is False
        verify = dict(factory_id='huaxing', expected_posting_date='2026-10-05', expected_date_basis='RETURN_POSTING',
                      return_date='2026-09-30', reason='原退货交接单及经手人已核实')
        url = BASE + f'/inventory/movements/{movement_id}/return-date'
        assert client.post(url, json=verify).status_code == 409  # Original month confirmed.
        reopened = action(client, confirmed, 'reopen', reason='补充真实退货交接日期')
        assert reopened.status_code == 200, reopened.text
        september = save_and_confirm(client, monkeypatch, '2026-09')
        assert client.post(url, json=verify).status_code == 409  # Destination month confirmed.
        assert action(client, september, 'reopen', reason='核实历史退货所属月份').status_code == 200
        login_as(client, 'warehouse_keeper')
        assert client.post(url, json=verify).status_code == 403
        login_as(client, 'carton_supervisor')
        assert client.post(url, json={**verify, 'expected_posting_date': '2026-10-04'}).status_code == 409
        before = ledger(client)
        saved = client.post(url, json=verify)
        assert saved.status_code == 200, saved.text
        assert client.post(url, json=verify).status_code == 409  # Actual evidence cannot be silently overwritten.
        assert ledger(client)[-1]['occurred_at'] == before[-1]['occurred_at']
        assert len(ledger(client)) == len(before)
        assert not any(source['kind'] == 'RETURN' for source in view(client)['sources'])
        actual = next(source for source in view(client, '2026-09')['sources'] if source['source_key'] == 'RETURN:' + movement_id)
        assert actual['date_basis'] == 'RETURN_ACTUAL' and actual['posting_date'] == '2026-10-05'
        assert view(client)['documents'][0]['stale'] is True
        # Reversal uses the original actual month, while the opposite stock movement posts now.
        reversed_result = client.post(BASE + f'/inventory/movements/{movement_id}/reverse', json=dict(factory_id='huaxing', reason='核实原退货数量后冲销'))
        assert reversed_result.status_code == 201, reversed_result.text
        assert reversed_result.json()['return_date'] == '2026-09-30'
        assert not any(source['source_key'] == 'RETURN:' + movement_id for source in view(client, '2026-09')['sources'])


def test_return_and_reversal_keep_the_current_inventory_posting_lock_independent_of_actual_month(monkeypatch):
    from sqlalchemy import update
    with make_client(monkeypatch) as client:
        row = setup(client, monkeypatch)
        made = client.post(BASE + '/inventory/movements', json=outbound(row, 1, issue_kind='RETURN', return_date='2026-09-30'))
        assert made.status_code == 201, made.text
        generated = client.post(BASE + '/closings/generate', json=dict(factory_id='huaxing', period='2026-10'))
        assert generated.status_code == 200, generated.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonClosing
        with SessionLocal() as db:
            db.execute(update(CartonClosing).where(CartonClosing.factory_id == 'huaxing', CartonClosing.period == '2026-10').values(status='LOCKED'))
            db.commit()
        before = ledger(client)
        single = client.post(BASE + '/inventory/movements', json=outbound(row, 1, issue_kind='RETURN', return_date='2026-09-30'))
        assert single.status_code == 409 and '2026-10' in single.text
        bulk = client.post(BASE + '/inventory/movements/bulk', json=dict(factory_id='huaxing', request_id=uuid4().hex,
            issue_kind='RETURN', return_date='2026-09-30', document_no='LOCKED-RET', reason='核实实际退货',
            items=[dict(order_line_id=line['id'], quantity=1) for line in row['lines']]))
        assert bulk.status_code == 409 and '2026-10' in bulk.text
        reverse = client.post(BASE + f"/inventory/movements/{made.json()['id']}/reverse", json=dict(factory_id='huaxing', reason='核实原退货后冲销'))
        assert reverse.status_code == 409 and '2026-10' in reverse.text
        assert ledger(client) == before


@pytest.mark.parametrize('status', ['active', 'disabled'])
def test_legacy_date_verification_rechecks_the_actor_after_iam_then_factory_lock(monkeypatch, status):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.services import carton_special_requests as special, carton_supplier_settlement as settlement
    from app.services import identity_policy
    from app.services.auth import AuthContext, AuthGrantContext
    def actor(permissions):
        grant = AuthGrantContext('R', 'Supervisor', 'huaxing', 'carton', frozenset('carton_procurement:' + item for item in permissions))
        return AuthContext('U1', 'supervisor', '主管', (), (), grant.permissions, ('huaxing',), ('carton',), grants=(grant,))
    original = actor(['closing_manage', 'order_adjust'])
    refreshed = actor(['closing_manage'])  # Adjustment permission revoked while the request waited.
    sequence = []
    monkeypatch.setattr(identity_policy, 'lock_mutation', lambda db: sequence.append('IAM'))
    monkeypatch.setattr(special.core, '_lock_receipt_factory', lambda db, factory: sequence.append('factory'))
    monkeypatch.setattr(special, 'build_auth_context', lambda db, row: sequence.append('context') or refreshed)
    db = SimpleNamespace(get=lambda model, identifier: sequence.append('actor') or SimpleNamespace(id='U1', status=status))
    assert special.allowed(original, 'huaxing', 'order_adjust')
    with pytest.raises(HTTPException) as error:
        settlement.set_return_date(db, 'M1', SimpleNamespace(factory_id='huaxing'), original)
    assert error.value.status_code == 403
    assert sequence[:3] == ['IAM', 'factory', 'actor']
    assert ('context' in sequence) is (status == 'active')
