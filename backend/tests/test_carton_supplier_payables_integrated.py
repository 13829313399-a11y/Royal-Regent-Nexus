"""Independent payable invariants through real APIs and disposable SQLite fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal as D
from threading import Barrier
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login
from test_carton_settlement_collaboration import received, workspace as goods_workspace, save, review
from test_carton_supplier_settlement_api import action as goods_action

BASE = '/api/carton-procurement'
PAY = BASE + '/payables'
SUP = '/api/carton-supplier/payables'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def freeze(monkeypatch):
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, 'business_now', lambda: datetime(2026, 11, 5, 12))
    monkeypatch.setattr(core, 'business_today', lambda: '2026-11-05')


def prepare(client, monkeypatch, *, stock=False):
    if stock:
        received(client, monkeypatch)
    else:
        setup_portal(client)
    freeze(monkeypatch)
    login_as(client, 'carton_supervisor')


def work(client, *, external=False, **values):
    response = client.get((SUP if external else PAY) + '/workspace', params={
        'factory_id': 'huaxing', 'currency': 'CNY', 'limit': 100, **values})
    assert response.status_code == 200, response.text
    return response.json()


def body(current, name, **values):
    return dict(factory_id='huaxing', currency='CNY', supplier_id=current['supplier_id'],
        request_id=uuid4().hex, expected_revision=current['revision'],
        source_fingerprint=current['source_fingerprint'], action=name,
        reason='双方核实原始凭证及本次往来金额', **values)


def act(client, name, *, external=False, expected=200, **values):
    command = body(work(client, external=external), name, **values)
    response = client.post((SUP if external else PAY) + '/actions', json=command)
    assert response.status_code == expected, response.text
    return response.json(), command


def record(current, number):
    return next(row for row in current['records']['items'] if row['document_no'] == number)


def obligation(current, kind, *, identifier=None, direction=None):
    return next(row for row in current['obligations'] if row['kind'] == kind
        and (identifier is None or row['record_id'] == identifier)
        and (direction is None or row['direction'] == direction))


def confirm_proposal(client, kind, number, **values):
    login_as(client, 'carton_supervisor')
    proposed, _ = act(client, 'PROPOSE_' + kind, document_no=number, **values)
    identifier = record(proposed, number)['id']
    supplier_login(client)
    act(client, 'REVIEW_' + kind, external=True, target_id=identifier, decision='CONFIRMED')
    login_as(client, 'carton_supervisor')
    confirmed, _ = act(client, 'CONFIRM_' + kind, target_id=identifier)
    return confirmed, record(confirmed, number)


def opening(client, amount='0', direction='PAYABLE', **values):
    return confirm_proposal(client, 'OPENING', 'OPENING-BASE', amount=amount, direction=direction,
        cutoff_date='2026-10-01', acknowledge_unknown_sources=False, **values)


def payment(client, amount, number='PAYMENT-BASE', *, acknowledge=True):
    login_as(client, 'carton_supervisor')
    current, _ = act(client, 'RECORD_PAYMENT', amount=str(amount), payment_date='2026-10-20',
        document_no=number, bank_reference='BANK-OUT-' + number)
    identifier = record(current, number)['id']
    if acknowledge:
        supplier_login(client)
        act(client, 'RECEIVE_PAYMENT', external=True, target_id=identifier, decision='CONFIRMED')
        login_as(client, 'carton_supervisor')
        current = work(client)
    return current, record(current, number)


def finish_goods(client, period='2026-09', *, document=None):
    login_as(client, 'carton_supervisor')
    current = goods_workspace(client, period)
    saved = save(client, current, doc=document)
    assert not saved['result']['issues'], saved['result']
    supplier_login(client)
    signed = review(client, saved)
    assert signed.status_code == 200, signed.text
    login_as(client, 'carton_supervisor')
    response = goods_action(client, signed.json())
    assert response.status_code == 200, response.text
    return response.json()


def physical_snapshot():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import (CartonOrder, CartonOrderLine, CartonReceipt,
        CartonReceiptLine, CartonInventoryMovement, CartonPurchaseOrderIssue)
    from app.models.carton_positions import CartonPositionEntry
    result = {}
    with SessionLocal() as db:
        for model in (CartonOrder, CartonOrderLine, CartonReceipt, CartonReceiptLine,
                      CartonInventoryMovement, CartonPurchaseOrderIssue, CartonPositionEntry):
            table = model.__table__
            result[table.name] = [dict(row) for row in db.execute(select(table).order_by(table.c.id)).mappings()]
    return result


def receipt_row():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonReceipt
    with SessionLocal() as db:
        row = db.scalar(select(CartonReceipt).where(CartonReceipt.status == 'POSTED'))
        return dict(id=row.id, revision=row.revision)


def test_cutoff_absorbs_old_goods_and_historical_drift_requires_new_bilateral_opening(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client, monkeypatch, stock=True)
        historical = finish_goods(client)
        assert D(historical['result']['net_amount']) > 30
        facts = physical_snapshot()
        current, _ = opening(client, '30')
        assert D(current['summary']['opening_signed']) == 30
        assert D(current['summary']['confirmed_settlements']) == 0
        assert D(current['summary']['balance_due_signed']) == 30
        assert physical_snapshot() == facts

        # Old economic evidence changes only after its ordinary monthly guard.
        reopening = goods_action(client, historical, 'reopen', reason='补核原历史验收日期依据')
        assert reopening.status_code == 200, reopening.text
        receipt = receipt_row()
        changed = client.post(BASE + f"/receipts/{receipt['id']}/acceptance-date", json=dict(
            factory_id='huaxing', expected_revision=receipt['revision'], acceptance_date='2026-09-25',
            reason='原签收单确认实际验收日期'))
        assert changed.status_code == 200, changed.text
        facts = physical_snapshot()
        drifted = work(client)
        assert drifted['summary']['needs_reconfirmation'] is True
        assert D(drifted['summary']['opening_signed']) == 30
        assert D(drifted['summary']['confirmed_settlements']) == 0
        paid, money = payment(client, 1)
        assert D(paid['summary']['balance_due_signed']) == 29  # Money is still recordable.
        target = obligation(paid, 'OPENING')
        act(client, 'ALLOCATE', expected=409, source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='OPENING', target_id=target['id'], amount='1')])

        proposed, _ = act(client, 'PROPOSE_OPENING', cutoff_date='2026-10-01', direction='PAYABLE',
            amount='30', document_no='OPENING-RECHECK', acknowledge_unknown_sources=False)
        identifier = proposed['opening']['id']
        assert D(proposed['summary']['opening_signed']) == 30
        supplier_login(client)
        signed, _ = act(client, 'REVIEW_OPENING', external=True, target_id=identifier, decision='CONFIRMED')
        assert signed['summary']['needs_reconfirmation'] is True
        login_as(client, 'carton_supervisor')
        updated, _ = act(client, 'CONFIRM_OPENING', target_id=identifier)
        assert updated['summary']['needs_reconfirmation'] is False
        assert D(updated['summary']['balance_due_signed']) == 29
        assert physical_snapshot() == facts
        revision = updated['revision']
        for name, values in [
            ('RECORD_PAYMENT', dict(amount='1', payment_date='2026-09-30', document_no='PRE-CUTOFF-PAY', bank_reference='PRE-CUTOFF-BANK')),
            ('PROPOSE_FEE', dict(amount='1', direction='ADD_PAYABLE', fee_date='2026-09-30', category='OTHER', document_no='PRE-CUTOFF-FEE')),
        ]:
            act(client, name, expected=409, **values)
        assert work(client)['revision'] == revision


def test_fees_payment_receipt_and_credit_offset_clear_items_without_reposting_money_or_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client, monkeypatch)
        facts = physical_snapshot()
        opening(client, '60')
        confirm_proposal(client, 'FEE', 'FREIGHT-TEN', direction='ADD_PAYABLE', amount='10',
            fee_date='2026-10-12', category='FREIGHT')
        current, credit = confirm_proposal(client, 'FEE', 'DISCOUNT-THIRTY', direction='DEDUCT_PAYABLE',
            amount='30', fee_date='2026-10-12', category='DISCOUNT')
        assert D(current['summary']['fees_signed']) == -20
        current, money = payment(client, 40, acknowledge=False)
        assert D(current['summary']['internal_paid']) == 40
        assert D(current['summary']['paid_awaiting_receipt']) == 40
        assert D(current['summary']['allocated']) == 0
        assert D(current['summary']['balance_due_signed']) == 0
        debit_opening = obligation(current, 'OPENING')
        act(client, 'ALLOCATE', expected=409, source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='OPENING', target_id=debit_opening['id'], amount='40')])
        supplier_login(client)
        act(client, 'RECEIVE_PAYMENT', external=True, target_id=money['id'], decision='CONFIRMED')
        login_as(client, 'carton_supervisor')
        current, _ = act(client, 'ALLOCATE', source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='OPENING', target_id=debit_opening['id'], amount='40')])
        debit_fee = obligation(current, 'FEE', direction='DEBIT')
        credit_fee = obligation(current, 'FEE', identifier=credit['id'], direction='CREDIT')
        current, _ = act(client, 'ALLOCATE', source_kind='CREDIT', source_id=credit_fee['id'], targets=[
            dict(target_kind='OPENING', target_id=debit_opening['id'], amount='20'),
            dict(target_kind='FEE', target_id=debit_fee['id'], amount='10')])
        assert all(D(row['remaining_amount']) == 0 for row in current['obligations'])
        assert D(current['summary']['balance_due_signed']) == 0
        assert D(current['summary']['internal_paid']) == 40
        assert D(current['summary']['unapplied_credit']) == 0
        assert D(current['summary']['unapplied_payment']) == 0
        assert physical_snapshot() == facts
        assert goods_workspace(client, '2026-10')['sources'] == []
        filtered = work(client, kind='PAYMENT', limit=1)
        assert filtered['summary'] == current['summary']
        assert filtered['obligations'] == current['obligations']
        exported = client.get(PAY + '/export', params=dict(factory_id='huaxing', currency='CNY'))
        assert exported.status_code == 200, exported.text
        assert all(number in exported.content.decode('utf-8-sig') for number in ('FREIGHT-TEN', 'DISCOUNT-THIRTY', 'PAYMENT-BASE'))
        supplier_login(client)
        assert work(client, external=True)['summary'] == current['summary']


def test_allocated_goods_reopen_requires_release_retains_last_amount_and_can_confirm_real_zero(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client, monkeypatch, stock=True)
        current, _ = confirm_proposal(client, 'OPENING', 'OPENING-SEPTEMBER', amount='0', direction='PAYABLE',
            cutoff_date='2026-09-01', acknowledge_unknown_sources=False)
        historical = finish_goods(client)
        amount = D(historical['result']['net_amount'])
        paid_amount = amount - 10
        current, money = payment(client, paid_amount)
        bill = obligation(current, 'SETTLEMENT', identifier=historical['id'])
        current, _ = act(client, 'ALLOCATE', source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='SETTLEMENT', target_id=bill['id'], amount=str(paid_amount))])
        assert goods_action(client, historical, 'reopen', reason='核实本月原单需冲销').status_code == 409
        current, _ = act(client, 'DEALLOCATE', allocation_ids=[row['id'] for row in current['allocations'] if row['status'] == 'ACTIVE'])
        assert D(current['summary']['internal_paid']) == paid_amount
        assert D(current['summary']['balance_due_signed']) == 10
        reopened = goods_action(client, historical, 'reopen', reason='核实误录原单全部冲销')
        assert reopened.status_code == 200, reopened.text
        current = work(client)
        hold = obligation(current, 'SETTLEMENT', identifier=historical['id'])
        assert hold['status'] == 'REOPENED_HOLD' and hold['can_allocate'] is False
        assert D(current['summary']['confirmed_settlements']) == amount
        assert D(current['summary']['balance_due_signed']) == 10
        act(client, 'ALLOCATE', expected=409, source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='SETTLEMENT', target_id=hold['id'], amount='1')])

        receipt = receipt_row()
        reversed_response = client.post(BASE + f"/receipts/{receipt['id']}/reverse", json=dict(
            factory_id='huaxing', expected_revision=receipt['revision'], reason='原单重复验收入账整单冲销'))
        assert reversed_response.status_code == 200, reversed_response.text
        facts = physical_snapshot()
        assert goods_workspace(client)['sources'] == []
        zero = finish_goods(client, document=reopened.json())
        assert zero['version'] == 2 and D(zero['result']['net_amount']) == 0
        current = work(client)
        assert D(current['summary']['confirmed_settlements']) == 0
        assert D(current['summary']['balance_due_signed']) == -paid_amount
        assert D(current['summary']['unapplied_payment']) == paid_amount
        assert not any(row['status'] == 'ACTIVE' for row in current['allocations'])
        assert physical_snapshot() == facts
        # This exception never creates a first-time empty monthly agreement.
        empty = save(client, goods_workspace(client, '2026-08'))
        supplier_login(client)
        assert review(client, empty).status_code == 409


def test_advance_return_reserves_only_unallocated_cash_and_concurrent_assignment_is_atomic(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client, monkeypatch)
        facts = physical_snapshot()
        opening(client, '100')
        current, money = payment(client, 100)
        supplier_login(client)
        declared, command = act(client, 'DECLARE_PAYMENT_RETURN', external=True,
            parent_payment_id=money['id'], amount='30', return_date='2026-10-25',
            document_no='ADVANCE-RETURN-30', bank_reference='BANK-IN-ADVANCE-30')
        returned = record(declared, 'ADVANCE-RETURN-30')
        assert D(declared['summary']['payment_returns_confirmed']) == 0
        source = next(row for row in declared['allocation_sources'] if row['id'] == money['id'])
        assert D(source['reserved_return_amount']) == 30 and D(source['available_amount']) == 70
        replay = client.post(SUP + '/actions', json=command)
        assert replay.status_code == 200, replay.text
        assert work(client, external=True)['revision'] == declared['revision']
        altered = {**command, 'amount': '31'}
        assert client.post(SUP + '/actions', json=altered).status_code == 409
        login_as(client, 'carton_supervisor')
        target = obligation(work(client), 'OPENING')
        act(client, 'ALLOCATE', expected=409, source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='OPENING', target_id=target['id'], amount='80')])
        current, _ = act(client, 'ALLOCATE', source_kind='PAYMENT', source_id=money['id'],
            targets=[dict(target_kind='OPENING', target_id=target['id'], amount='70')])
        current, _ = act(client, 'CONFIRM_PAYMENT_RETURN', target_id=returned['id'],
            confirmation_reference='BANK-IN-ADVANCE-30')
        assert D(current['summary']['payment_returns_confirmed']) == 30
        assert D(current['summary']['balance_due_signed']) == 30
        act(client, 'REQUEST_VOID', expected=409, target_id=money['id'], correction_reference='不得删除已实际退回的原款')
        current, _ = act(client, 'DEALLOCATE', allocation_ids=[row['id'] for row in current['allocations'] if row['status'] == 'ACTIVE'])
        race_bodies = [body(current, 'ALLOCATE', source_kind='PAYMENT', source_id=money['id'], targets=[
            dict(target_kind='OPENING', target_id=target['id'], amount='50')]) for _ in range(2)]
        barrier = Barrier(2)
        def send(command):
            barrier.wait(timeout=15)
            return client.post(PAY + '/actions', json=command)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, race_bodies))
        assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
        current = work(client)
        assert sum(D(row['amount']) for row in current['allocations'] if row['status'] == 'ACTIVE') == 50
        assert D(current['summary']['balance_due_signed']) == 30
        assert physical_snapshot() == facts
        assert goods_workspace(client, '2026-10')['sources'] == []  # Advance return is not a goods charge.


def test_unknown_cutover_requires_explicit_evidence_and_current_financial_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client, monkeypatch, stock=True)
        # Explicit historical fixture: an old posted receipt has no true date.
        # Neither opening approval nor a GET may invent or write one.
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonReceipt, CartonReceiptLine
        with SessionLocal() as db:
            db.scalar(select(CartonReceipt).where(CartonReceipt.status == 'POSTED')).acceptance_date = None
            db.commit()
        facts = physical_snapshot()
        act(client, 'PROPOSE_OPENING', expected=409, cutoff_date='2026-10-01', amount='12',
            direction='PAYABLE', document_no='UNACKNOWLEDGED-UNKNOWN', acknowledge_unknown_sources=False)
        current, _ = confirm_proposal(client, 'OPENING', 'ACKNOWLEDGED-UNKNOWN', amount='12',
            direction='PAYABLE', cutoff_date='2026-10-01', acknowledge_unknown_sources=True)
        assert D(current['summary']['balance_due_signed']) == 12
        assert current['summary']['needs_reconfirmation'] is False
        assert physical_snapshot() == facts
        # A separately scoped historical HKD unknown must not invalidate CNY.
        with SessionLocal() as db:
            old_receipt = dict(db.execute(select(CartonReceipt.__table__)).mappings().first())
            old_line = dict(db.execute(select(CartonReceiptLine.__table__)).mappings().first())
            old_receipt.update(id='legacy-hkd-unknown', receipt_no='LEGACY-HKD-UNKNOWN',
                delivery_note_no='LEGACY-HKD-UNKNOWN')
            db.add(CartonReceipt(**old_receipt)); db.flush()
            old_line.update(id='legacy-hkd-unknown-line', receipt_id='legacy-hkd-unknown',
                order_line_id=None, source_type='AD_HOC', currency='HKD')
            db.add(CartonReceiptLine(**old_line)); db.commit()
        assert work(client)['summary']['needs_reconfirmation'] is False
        facts = physical_snapshot()
        command = body(current, 'RECORD_PAYMENT', amount='1', payment_date='2026-10-20',
            document_no='UNAUTHORIZED-PAY', bank_reference='UNAUTHORIZED-BANK')
        login_as(client, 'warehouse_keeper')
        assert client.post(PAY + '/actions', json=command).status_code == 403
        supplier_login(client)
        assert client.post(SUP + '/actions', json=command).status_code == 403
        assert client.get(SUP + '/workspace', params=dict(factory_id='huadeng', currency='CNY')).status_code == 403
        login_as(client, 'carton_supervisor')
        assert work(client)['revision'] == current['revision']
        from app.services import carton_procurement as core
        original_lock = core._lock_receipt_factory
        touched = []
        def disabled_after_lock(db, factory):
            original_lock(db, factory)
            actor = db.scalar(select(AuthUser).where(AuthUser.username == 'carton_supervisor'))
            actor.status = 'disabled'
            db.flush()
            touched.append(True)
        monkeypatch.setattr(core, '_lock_receipt_factory', disabled_after_lock)
        response = client.post(PAY + '/actions', json=command)
        assert response.status_code == 403, response.text
        assert touched
        monkeypatch.setattr(core, '_lock_receipt_factory', original_lock)
        assert work(client)['revision'] == current['revision']
        assert physical_snapshot() == facts


def test_material_cash_and_advance_return_cannot_duplicate_the_same_bank_inflow_in_either_order(monkeypatch):
    from test_carton_return_collaboration import returned, detail, command as return_act
    with make_client(monkeypatch) as client:
        returned_row, _ = returned(client, monkeypatch)
        freeze(monkeypatch)
        identifier = returned_row['movement_id']
        supplier_login(client)
        material = detail(client, identifier, True)
        material, _ = return_act(client, material, 'RECEIVE', external=True,
            quantity='2', receipt_date='2026-09-30', document_no='MATERIAL-SIGNED')
        material, _ = return_act(client, material, 'PROPOSE_CREDIT', external=True,
            unit_price='3', credit_date='2026-09-30', document_no='MATERIAL-CREDIT-SIX')
        login_as(client, 'carton_supervisor')
        material = detail(client, identifier)
        return_act(client, material, 'CONFIRM_CREDIT', target_event_id=material['credit']['id'])
        opening(client)
        _, money = payment(client, 100)
        facts = physical_snapshot()

        supplier_login(client)
        material = detail(client, identifier, True)
        material, _ = return_act(client, material, 'DECLARE_REFUND', external=True,
            kind='CASH', amount='3', refund_date='2026-10-25', document_no='MATERIAL-CASH-FIRST')
        login_as(client, 'carton_supervisor')
        material = detail(client, identifier)
        return_act(client, material, 'CONFIRM_REFUND', target_event_id=material['refunds'][-1]['id'],
            confirmation_reference='BANK SHARED FIRST')
        cash_bill = finish_goods(client, '2026-10')
        assert D(cash_bill['result']['net_amount']) == 3
        supplier_login(client)
        before = work(client, external=True)
        duplicate = body(before, 'DECLARE_PAYMENT_RETURN', parent_payment_id=money['id'],
            amount='3', return_date='2026-10-25', document_no='ADVANCE-SAME-FIRST',
            bank_reference='BANK  SHARED\tFIRST')
        refused = client.post(SUP + '/actions', json=duplicate)
        assert refused.status_code == 409, refused.text
        assert work(client, external=True)['revision'] == before['revision']

        declared, _ = act(client, 'DECLARE_PAYMENT_RETURN', external=True,
            parent_payment_id=money['id'], amount='3', return_date='2026-10-26',
            document_no='ADVANCE-FIRST', bank_reference='BANK SHARED SECOND')
        advance = record(declared, 'ADVANCE-FIRST')
        login_as(client, 'carton_supervisor')
        current, _ = act(client, 'CONFIRM_PAYMENT_RETURN', target_id=advance['id'],
            confirmation_reference='BANK SHARED SECOND')
        assert D(current['summary']['balance_due_signed']) == -94  # +3 goods cash, -100 paid, +3 advance returned.
        # Open the material-cash month to exercise the bank identity guard,
        # independently of the ordinary confirmed-month guard.
        reopened = goods_action(client, cash_bill, 'reopen', reason='核实第二笔材料退款回执')
        assert reopened.status_code == 200, reopened.text
        supplier_login(client)
        material = detail(client, identifier, True)
        material, _ = return_act(client, material, 'DECLARE_REFUND', external=True,
            kind='CASH', amount='3', refund_date='2026-10-26', document_no='MATERIAL-SAME-SECOND')
        login_as(client, 'carton_supervisor')
        material = detail(client, identifier)
        return_act(client, material, 'CONFIRM_REFUND', expected=409,
            target_event_id=material['refunds'][-1]['id'], confirmation_reference=' BANK  SHARED\tSECOND ')
        assert D(work(client)['summary']['balance_due_signed']) == -94
        assert physical_snapshot() == facts
