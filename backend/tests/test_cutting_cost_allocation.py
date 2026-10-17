"""Supervisor-confirmed completed material use, WIP and per-set reconciliation."""
from pathlib import Path
import runpy
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_cutting_usage import custody, bridge, client, flow, planned, actor, read, consume, write, URL, warehouse_view
from test_cutting_ops import BASE, command
from test_cutting_reporting import send as report, ok, doc
from app.services import cutting_usage as usage


@pytest.fixture
def accounting(custody):
    p = custody
    migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions/20261010_0155_cutting_production_events.py'))
    with p.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration['upgrade']()
    p.cutting_auth['user'] = actor('material_request', 'material_receive', 'usage_write', 'usage_review',
                                 'cost_read', 'cost_write', 'allocation_confirm', 'report_write', 'return_write', 'acceptance_write', 'handover_write')
    p.report_id = doc(ok(report(p, sets=10)))
    consume(p)
    return p


def allocation_body(p, quantity='1.2', **changes):
    current = read(p, True)
    group = current['cost_allocation']['groups'][0]
    return command(expected_version=current['revision'], day=usage.wh.business_now().date().isoformat(), issue_id=p.issue_id,
                   basis_token=group['basis_token'], allocations=[dict(issue_id=p.issue_id, completed_quantity=quantity)],
                   materials_complete=True, public_material_pending=False) | changes


def allocate(p, quantity='1.2', status=200, **changes):
    body = allocation_body(p, quantity, **changes)
    response = p.post(URL + '/allocate', json=body)
    assert response.status_code == status, response.text
    return response.json(), body


def test_completed_wip_and_unit_cost_conserve_original_issue_cost(accounting):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='3.125', currency='HKD', price_reference='原批次实际核定凭据')
    before = warehouse_view(p)['stock']
    result, body = allocate(p)
    assert p.post(URL + '/allocate', json=body).json() == result
    current = read(p, True)
    group = current['cost_allocation']['groups'][0]
    assert group['status'] == 'confirmed' and group['completed_sets'] == 10
    assert group['rows'][0]['wip_quantity'] == '0.8'
    assert group['costs']['HKD'] == dict(completed='3.75', wip='2.50', loss='1.56', unit_cost='0.375000')
    assert len(current['documents']) == 1  # Allocations are not physical consumption.
    evidence = current['cost_allocation']['history'][0]['basis_documents']
    assert evidence['usage'][0]['document_id'] == current['documents'][0]['id']
    assert evidence['production'][0]['document_id'] == p.report_id
    assert warehouse_view(p)['stock'] == before
    assert 'cost_allocation' not in read(p)


def test_confirmation_requires_separate_production_permission(accounting):
    p = accounting
    body = allocation_body(p)
    for permissions, department in [(('usage_review', 'cost_read'), 'production'),
                                    (('allocation_confirm', 'cost_read'), 'pmc-warehouse'),
                                    (('allocation_confirm',), 'production')]:
        p.cutting_auth['user'] = actor(*permissions, department=department)
        assert p.post(URL + '/allocate', json=body).status_code == 403
    p.cutting_auth['user'] = actor('allocation_confirm', 'cost_read', department='production')
    assert p.post(URL + '/allocate', json=body).status_code == 200


@pytest.mark.parametrize('changes,status', [
    ({'allocations': []}, 422),
    ({'allocations': [dict(issue_id='other', completed_quantity='1')]}, 422),
    ({'allocations': [dict(issue_id='duplicate', completed_quantity='0')]*2}, 422),
    ({'basis_token': 'old'}, 409),
    ({'reason': '  '}, 422),
])
def test_invalid_confirmation_is_atomic(accounting, changes, status):
    p = accounting
    before = read(p)['revision']
    allocate(p, status=status, **changes)
    assert read(p)['revision'] == before
    assert read(p, True)['cost_allocation']['history'] == []


def test_cannot_allocate_more_than_normal_use(accounting):
    allocate(accounting, quantity='2.000001', status=422)


def test_report_and_usage_corrections_require_reconfirmation(accounting):
    p = accounting
    _, old_body = allocate(p)
    ok(report(p, document_id=p.report_id, sets=8))
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['status'] == 'stale' and all(c['unit_cost'] is None for c in group['costs'].values())
    stale = old_body | dict(operation_id=uuid4().hex, expected_version=read(p)['revision'])
    assert p.post(URL + '/allocate', json=stale).status_code == 409
    allocate(p, quantity='1')
    current = read(p, True)
    history = current['cost_allocation']['history']
    assert len(history) == 2 and history[-1]['replaces_id'] == history[0]['id']
    original = current['documents'][0]
    write(p, 'correct', document_id=original['id'], issue_id=p.issue_id, consumed_quantity='2',
          loss_quantity='0.5', counted_remaining='1.5')
    assert read(p, True)['cost_allocation']['groups'][0]['status'] == 'stale'


def test_pending_price_public_use_and_incomplete_scope_do_not_fake_unit_cost(accounting):
    p = accounting
    allocate(p)
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['pending_pricing'] == 1 and group['status'] == 'pending'
    write(p, 'price', issue_id=p.issue_id, unit_cost='0', currency='CNY', price_reference='客户供料零价凭据')
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['status'] == 'confirmed' and group['costs']['CNY']['unit_cost'] == '0.000000'
    allocate(p, materials_complete=False)
    assert read(p, True)['cost_allocation']['groups'][0]['costs']['CNY']['unit_cost'] is None
    allocate(p, public_material_pending=True)
    assert read(p, True)['cost_allocation']['groups'][0]['costs']['CNY']['unit_cost'] is None


def test_zero_completed_sets_keep_normal_use_in_wip(accounting):
    p = accounting
    ok(report(p, document_id=p.report_id, sets=0))
    allocate(p, quantity='1', status=422)
    allocate(p, quantity='0')
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['completed_sets'] == 0 and group['rows'][0]['wip_quantity'] == '2'
    assert group['status'] == 'pending'


def test_unknown_confirmation_can_be_fenced_and_cannot_arrive_late(accounting):
    p = accounting
    body = allocation_body(p)
    response = p.post(BASE + '/orders/line-1/usage-operations/recover', json={'action': 'allocate', 'command': body})
    assert response.status_code == 200 and response.json()['state'] == 'abandoned'
    assert p.post(URL + '/allocate', json=body).status_code == 409
    assert read(p, True)['cost_allocation']['history'] == []


@pytest.mark.parametrize('bridge', ['outsourced'], indirect=True)
def test_external_denominator_uses_accepted_sets_not_claimed_or_received(accounting):
    p = accounting
    assert read(p, True)['cost_allocation']['groups'][0]['completed_sets'] == 0
    ok(report(p, kind='return', sets=8))
    allocate(p, status=422)
    ok(report(p, kind='accept', sets=6, rejected=2))
    write(p, 'price', issue_id=p.issue_id, unit_cost='3', currency='CNY', price_reference='原批次确认成本依据')
    allocate(p)
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['completed_sets'] == 6 and group['costs']['CNY']['unit_cost'] == '0.600000'


def test_price_revision_revalues_current_costs_but_keeps_confirmation_snapshot(accounting):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='0.0025', currency='HKD', price_reference='原批次含小数成本依据')
    allocate(p, quantity='1')
    first = read(p, True)['cost_allocation']
    assert first['groups'][0]['costs']['HKD']['completed'] == '0.00'
    assert first['groups'][0]['costs']['HKD']['wip'] == '0.01'  # No lost rounding cent.
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='确认币种及实际成本更正')
    current = read(p, True)['cost_allocation']
    assert current['groups'][0]['status'] == 'confirmed'
    assert set(current['groups'][0]['costs']) == {'CNY'}
    assert current['history'] == first['history']


def test_new_issue_requires_complete_reconfirmation_and_keeps_currencies_separate(accounting):
    from test_cutting_materials import warehouse_post, ledger, send, decision
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='人民币批次确认成本')
    allocate(p)
    request = ledger(p)['requests'][0]
    batch = warehouse_post(p, 'RECEIPT', quantity='2', source_no='other-batch', source_line='1', item_code='FAB-01',
                           item_name='蓝布', unit='米', location_id='bin', lot='LOT-2', counterparty='测试供方')
    issued = warehouse_post(p, 'ISSUE', original_id=request['id'], batch_id=batch['id'], quantity='1', counterparty='R01')
    send(p, 'receive', decision(p, issued, quantity='1'))
    write(p, 'post', issue_id=issued['id'], consumed_quantity='1', loss_quantity='0', counted_remaining='0')
    write(p, 'price', issue_id=issued['id'], unit_cost='4', currency='HKD', price_reference='港币批次确认成本')
    assert read(p, True)['cost_allocation']['groups'][0]['status'] == 'stale'
    allocate(p, status=422)  # Cannot omit the new issue.
    allocate(p, allocations=[dict(issue_id=p.issue_id, completed_quantity='1'), dict(issue_id=issued['id'], completed_quantity='0.5')])
    costs = read(p, True)['cost_allocation']['groups'][0]['costs']
    assert costs['CNY']['unit_cost'] == '0.200000' and costs['HKD']['unit_cost'] == '0.200000'


def test_cost_confirmation_does_not_block_legitimate_unused_material_return(accounting):
    from test_cutting_materials import warehouse_post
    p = accounting
    allocate(p)
    warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='1', location_id='bin', business_date='2026-10-11')
    # The consumed quantity did not change, so this allocation remains valid (price still pending).
    current = read(p, True)
    assert current['issues'][0]['remaining_quantity'] == '0.5'
    assert current['cost_allocation']['groups'][0]['status'] == 'pending'


def test_handover_is_not_the_cost_denominator_and_does_not_invalidate_allocation(accounting):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='核对原批次成本依据')
    allocate(p)
    ok(report(p, kind='handover', sets=7))
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['completed_sets'] == 10 and group['status'] == 'confirmed'
    assert group['costs']['CNY']['unit_cost'] == '0.240000'
