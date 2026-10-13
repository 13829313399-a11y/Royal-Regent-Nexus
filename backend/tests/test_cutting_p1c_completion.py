"""Change handling and recovery use isolated databases, never business records."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, UTC
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.cutting_ops import CuttingCommand, CuttingOrderRevision
from app.services import cutting_orders as orders
from test_cutting_orders import flow, submitted, bound, read, post, receive, amend, batch
from test_cutting_ops import client, user, command, BASE


def reconcile(client, version, target=3, **kwargs):
    client.cutting_auth['user'] = user('read', 'requisition_reconcile', department='pmc-warehouse')
    return post(client, 'reconcile', expected_version=version, requisition_version=target,
                disposition='not_ordered', evidence='采购核实整张需求尚未下单', all_handled=True, **kwargs)


def recover(client, action, body):
    return client.post(BASE + '/orders/line-1/operations/recover', json={'action': action, 'command': body})


def test_withdraw_reconcile_edit_resubmit_preserves_history(flow):
    _, bom = submitted(flow)
    assert post(flow, 'withdraw', expected_version=3, requisition_version=3).status_code == 200
    assert read(flow)['workflow_status'] == 'reconciliation'
    assert post(flow, 'eta', expected_version=4, requisition_version=3, batches=[]).status_code == 409
    assert reconcile(flow, 4).status_code == 200
    assert read(flow)['workflow_status'] == 'awaiting_submission'
    flow.cutting_auth['user'] = user('read', 'bom_write', 'requisition_submit', department='engineering')
    assert post(flow, 'bom', expected_version=5, bom_id=bom['id'], bom_version=2, target_sets=80, quantity_basis='工程修订套数').status_code == 200
    response = post(flow, 'requisition', expected_version=6, lines=[dict(row=0, quantity='10'), dict(row=1, quantity='11')])
    assert response.status_code == 200, response.text
    assert response.json()['current']['data']['requisition']['supersedes_version'] == 3
    history = flow.get(BASE + '/orders/line-1/versions?factory_id=huakang-c').json()['data']
    assert next(r for r in history if r['version'] == 3)['data']['requisition']['lines'][0]['quantity'] == '7'
    # A stale reconciliation cannot release a subsequent withdrawal.
    assert post(flow, 'withdraw', expected_version=7, requisition_version=7).status_code == 200
    assert reconcile(flow, 8, target=3).status_code == 409


def test_repeated_source_changes_and_cancellation_preserve_pending_purchase(flow):
    submitted(flow)
    amend(flow); receive(flow)
    amend(flow, cancelled=True); receive(flow)
    row = read(flow)
    assert row['pending_purchase']['requisition']['version'] == 3
    assert row['pending_purchase']['order']['quantity'] == '100'
    assert reconcile(flow, 5).status_code == 200
    assert read(flow)['workflow_status'] == 'cancelled'
    flow.cutting_auth['user'] = user('read', 'requisition_submit', 'eta_write')
    assert post(flow, 'requisition', expected_version=6, lines=[dict(row=0, quantity='1')]).status_code == 409
    assert post(flow, 'eta', expected_version=6, requisition_version=3, batches=[]).status_code == 409


def test_commitment_evidence_cannot_be_erased_by_deleting_eta(flow):
    submitted(flow)
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()]).status_code == 200
    assert post(flow, 'eta', expected_version=4, requisition_version=3, batches=[]).status_code == 200
    assert post(flow, 'withdraw', expected_version=5, requisition_version=3).status_code == 200
    assert reconcile(flow, 6).status_code == 422
    args = dict(expected_version=6, requisition_version=3, disposition='cancelled_or_reallocated', evidence='PO001旧采购全部转用，原需求不再占用', all_handled=False)
    assert post(flow, 'reconcile', **args).status_code == 422
    args['all_handled'] = True
    assert post(flow, 'reconcile', **args).status_code == 200


def test_reconciliation_has_separate_permission_and_department(flow):
    submitted(flow); post(flow, 'withdraw', expected_version=3, requisition_version=3)
    for account in [user('read', 'eta_write', department='pmc-warehouse'), user('read', 'requisition_reconcile', department='engineering')]:
        flow.cutting_auth['user'] = account
        assert post(flow, 'reconcile', expected_version=4, requisition_version=3, disposition='not_ordered', evidence='核对未采购', all_handled=True).status_code == 403


@pytest.mark.parametrize('line', [dict(row=0, quantity='0'), dict(row=0, quantity='0', purchase_mode='no_purchase'),
    dict(row=0, quantity='1', purchase_mode='no_purchase', no_purchase_reason='客户供料')])
def test_zero_quantity_needs_explicit_no_purchase_and_reason(flow, line):
    bound(flow)
    assert post(flow, 'requisition', expected_version=2, lines=[line, dict(row=1, quantity='2')]).status_code == 422


def test_no_purchase_is_not_stock_and_cannot_receive_eta(flow):
    bound(flow)
    lines = [dict(row=i, quantity='0', purchase_mode='no_purchase', no_purchase_reason='本次由客户供料，待仓库另行确认') for i in range(2)]
    result = post(flow, 'requisition', expected_version=2, lines=lines)
    assert result.status_code == 200, result.text
    assert result.json()['workflow_status'] == 'no_purchase'
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()]).status_code == 422
    assert read(flow)['current']['data']['batches'] == []


def test_reply_status_filter_and_shanghai_date_boundary(flow, monkeypatch):
    submitted(flow)
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, 16, 0, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(orders, 'datetime', FixedDatetime)
    assert read(flow)['workflow_status'] == 'awaiting_reply'
    post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch(quantity='7')])
    row = read(flow)
    assert row['workflow_status'] == 'partial_reply' and row['expected_date_passed']
    for state, total in [('partial_reply', 1), ('complete_reply', 0), ('awaiting_receipt', 0)]:
        result = flow.get(BASE + '/orders', params=dict(factory_id='huakang-c', status=state)).json()
        assert result['total'] == total
    post(flow, 'eta', expected_version=4, requisition_version=3, batches=[batch(quantity='7'), batch(row=1, quantity='8')])
    assert read(flow)['workflow_status'] == 'complete_reply'
    assert flow.get(BASE + '/orders', params=dict(factory_id='huakang-c', status='complete_reply', page=2)).json()['data'] == []


def test_recovery_returns_original_result_after_source_change_and_write_revocation(flow):
    row = read(flow); body = command(dispatch_id=row['dispatch_id'])
    original = flow.post(BASE + '/orders/line-1/receive', json=body).json()
    amend(flow)
    flow.cutting_auth['user'] = user('read', department='production')
    result = recover(flow, 'receive', body)
    assert result.status_code == 200 and result.json() == dict(state='committed', result=original)
    assert recover(flow, 'receive', dict(body, reason='不是原请求')).status_code == 409
    flow.cutting_auth['user'] = replace(user('read'), id='other-user')
    assert recover(flow, 'receive', body).status_code == 409


def test_recovery_seals_unexecuted_command_even_when_feature_disabled(flow, monkeypatch):
    body = command(dispatch_id=read(flow)['dispatch_id'])
    from app.core.config import settings
    monkeypatch.setattr(settings, 'cutting_ops_enabled', False)
    assert recover(flow, 'receive', body).json() == {'state': 'abandoned'}
    monkeypatch.setattr(settings, 'cutting_ops_enabled', True)
    assert flow.post(BASE + '/orders/line-1/receive', json=body).status_code == 409
    assert read(flow)['current'] is None
    assert recover(flow, 'receive', body).json() == {'state': 'abandoned'}


def test_recovery_racing_original_write_has_one_permanent_outcome(flow):
    body = command(dispatch_id=read(flow)['dispatch_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(flow.post, BASE + '/orders/line-1/receive', json=body)
        resolver = pool.submit(recover, flow, 'receive', body)
        response, result = writer.result(), resolver.result()
    assert result.status_code == 200
    committed = result.json()['state'] == 'committed'
    assert response.status_code == (200 if committed else 409)
    assert (read(flow)['current'] is not None) == committed
    assert flow.post(BASE + '/orders/line-1/receive', json=body).status_code == (200 if committed else 409)


@pytest.mark.parametrize('bad_lines', [[{'row': 0, 'quantity': 'abc'}], []])
def test_lost_validation_response_can_be_fenced_then_corrected_with_a_new_id(flow, bad_lines):
    bound(flow)
    body = command(expected_version=2, lines=bad_lines)
    assert flow.post(BASE+'/orders/line-1/requisition', json=body).status_code == 422
    assert recover(flow, 'requisition', body).json() == {'state': 'abandoned'}
    corrected = dict(body, lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')])
    assert flow.post(BASE+'/orders/line-1/requisition', json=corrected).status_code == 409
    corrected['operation_id'] = uuid4().hex
    assert flow.post(BASE+'/orders/line-1/requisition', json=corrected).status_code == 200


def test_eta_racing_withdrawal_cannot_pass_pending_reconciliation(flow):
    submitted(flow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(post, flow, 'withdraw', expected_version=3, requisition_version=3)
        b = pool.submit(post, flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()])
        responses = [a.result(), b.result()]
    assert sorted(r.status_code for r in responses) == [200, 409]
    row = read(flow)
    if not row['current']['data']['purchase_reconciliation_required']:
        assert post(flow, 'withdraw', expected_version=4, requisition_version=3).status_code == 200
    assert post(flow, 'eta', expected_version=read(flow)['current']['version'], requisition_version=3, batches=[]).status_code == 409
