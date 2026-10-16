"""Internal closing acceptance using isolated synthetic ledgers only."""
from dataclasses import replace
from datetime import datetime, date
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import runpy
import pytest
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_cutting_cost_allocation import accounting, custody, bridge, client, flow, planned, actor
from test_cutting_usage import write, read as usage_read
from test_cutting_materials import warehouse_post, warehouse_view, send, decision
from test_cutting_reporting import send as report
from test_cutting_ops import command, BASE
from app.services import warehouse_operations as wh, cutting_planning as planning

URL = BASE + '/periods'
ACTIONS = ('period_prepare', 'period_lock', 'period_reopen', 'cost_read', 'cost_write', 'report_write', 'usage_write', 'material_receive')


@pytest.fixture
def month_client(accounting, monkeypatch, request):
    p = accounting
    migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions/20261015_0163_cutting_internal_periods.py'))
    with p.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration['upgrade']()
    monkeypatch.setattr(wh, 'business_now', lambda: datetime(2026, 12, 15, 12, tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(planning, 'business_today', lambda: date(2026, 12, 15))
    p.cutting_auth['user'] = actor(*ACTIONS)
    if getattr(request, 'param', True):
        write(p, 'price', issue_id=p.issue_id, unit_cost='3.125', currency='HKD', price_reference='原批次正式成本凭据')
    return p


def get(p, month='2026-10', suffix='', status=200, **params):
    response = p.get(f'{URL}/{month}{suffix}', params=dict(factory_id='huakang-c', **params))
    assert response.status_code == status, response.text
    return response.json()


def act(p, action, month='2026-10', status=200, **changes):
    body = command(month=month, expected_version=get(p, month)['revision']) | changes
    response = p.post(URL + '/' + action, json=body)
    assert response.status_code == status, response.text
    return response.json(), body


def draft(p, month='2026-10', status=200, **changes):
    basis = get(p, month, '/basis')
    rows = [dict(issue_id=r['issue_id'], opening_completed_quantity=r['carried_completed_quantity'] or '0', completed_quantity='1.2') for r in basis['rows']]
    return act(p, 'save', month, status, basis_token=basis['basis_token'],
               **(dict(allocations=rows,materials_complete=True, public_material_pending=False, opening_verified=True,
                       unrecorded_opening=False, exceptions_reviewed=True) | changes))


def lock(p, month='2026-10'):
    draft(p, month)
    act(p, 'submit', month)
    p.cutting_auth['user'] = replace(actor(*ACTIONS), id=uuid4().hex)
    return act(p, 'lock', month)[0]


def test_full_close_conserves_cost_and_retains_snapshot_after_reopen(month_client):
    p = month_client
    result = lock(p)
    frozen = get(p)
    cost = frozen['data']['snapshot']['costs']['HKD']
    assert frozen['state'] == 'locked'
    assert cost['period_normal'] == '6.25' and cost['period_loss'] == '1.56'
    assert cost['ending_completed'] == '3.75' and cost['ending_wip'] == '2.50'
    act(p, 'reopen')
    write(p, 'price', issue_id=p.issue_id, unit_cost='4', currency='HKD', price_reference='反结后核对新成本')
    assert get(p, event_id=result['id'])['data']['snapshot'] == frozen['data']['snapshot']
    draft(p)
    assert get(p)['data']['snapshot']['costs']['HKD']['ending_normal'] == '8.00'


def test_independent_review_permissions_and_pending_state(month_client):
    p = month_client
    draft(p)
    act(p, 'submit')
    assert '不同' in act(p, 'lock', status=409)[0]['detail']
    p.cutting_auth['user'] = replace(actor('period_lock', 'cost_read', department='production'), id='reviewer')
    act(p, 'lock', status=403)
    p.cutting_auth['user'] = replace(actor('period_lock', 'cost_read', department='accounting'), id='reviewer')
    act(p, 'lock')
    act(p, 'reopen', status=403)
    p.cutting_auth['user'] = actor('read', department='production')
    get(p, status=403)


def test_preparer_cannot_review_even_if_another_person_submits(month_client):
    p = month_client
    preparer = p.cutting_auth['user']
    draft(p)
    p.cutting_auth['user'] = replace(preparer, id='second-submitter')
    act(p, 'submit')
    p.cutting_auth['user'] = preparer
    assert '不同' in act(p, 'lock', status=409)[0]['detail']


@pytest.mark.parametrize('environment,enabled,expected', [('development', True, 200), ('production', True, 409), ('development', False, 409)])
def test_admin_acceptance_exception_is_explicit_and_development_only(month_client, monkeypatch, environment, enabled, expected):
    from app.core.config import settings
    p = month_client
    monkeypatch.setattr(settings, 'app_env', environment)
    monkeypatch.setattr(settings, 'cutting_period_admin_acceptance', enabled)
    p.cutting_auth['user'] = replace(p.cutting_auth['user'], id='user-admin', role_codes=('admin',))
    draft(p)
    act(p, 'submit')
    act(p, 'lock', status=expected)
    if expected == 200:
        assert get(p)['data']['local_admin_acceptance'] is True


@pytest.mark.parametrize('changes', [dict(materials_complete=False), dict(public_material_pending=True),
                                   dict(opening_verified=False), dict(unrecorded_opening=True)])
def test_unresolved_completeness_blocks_submission(month_client, changes):
    draft(month_client, **changes)
    act(month_client, 'submit', status=409)


def test_locked_original_dates_and_prices_cannot_be_bypassed(month_client):
    p = month_client
    lock(p)
    assert report(p, document_id=p.report_id, day='2026-11-10', sets=8).status_code == 409
    assert report(p, day='2026-10-20', sets=2).status_code == 409
    original = usage_read(p)['documents'][0]['id']
    write(p, 'void', status=409, day='2026-11-10', document_id=original)
    write(p, 'price', status=409, day='2026-11-10', issue_id=p.issue_id, unit_cost='4', currency='HKD', price_reference='不能覆盖已锁成本')
    warehouse_post(p, 'RETURN', status=409, original_id=p.issue_id, quantity='0.5', location_id='bin')
    warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='0.5', location_id='bin', business_date='2026-11-10')
    assert get(p)['data']['snapshot']['allocations'][0]['ending_custody'] == '1.5'


def test_return_reversal_checks_original_month(month_client):
    p = month_client
    returned = warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='0.5', location_id='bin')
    lock(p)
    response = warehouse_post(p, 'CORRECTION', status=409, original_id=returned['id'], business_date='2026-11-11')
    assert '锁' in response['detail']


def test_month_sequence_opening_rollforward_and_reverse_order(month_client):
    p = month_client
    lock(p)
    get(p, '2026-12', '/basis', status=409)
    second = get(p, '2026-11', '/basis')
    assert second['rows'][0]['carried_completed_quantity'] == '1.2'
    lock(p, '2026-11')
    assert get(p, '2026-11')['data']['snapshot']['costs']['HKD']['opening_wip'] == '2.50'
    act(p, 'reopen', status=409)
    act(p, 'reopen', '2026-11')
    act(p, 'reopen')
    assert get(p)['first_month'] == '2026-10'
    assert get(p)['pending_reclose'] == ['2026-10', '2026-11']
    get(p, '2026-11', '/basis', status=409)
    get(p, '2026-09', '/basis', status=409)
    lock(p)
    assert get(p, '2026-11', '/basis')['rows'][0]['carried_completed_quantity'] == '1.2'
    lock(p, '2026-11')
    assert get(p)['pending_reclose'] == []


def test_legacy_hole_requires_reverse_order_repair(month_client, monkeypatch):
    from app.services import cutting_periods
    p = month_client
    lock(p);lock(p,'2026-11');act(p,'reopen','2026-11');act(p,'reopen')
    # Simulate the old release's already-created hole without mutating history.
    original = cutting_periods.sequence
    monkeypatch.setattr(cutting_periods,'sequence',lambda events:dict(original(events),next_month=None))
    lock(p,'2026-11')
    monkeypatch.setattr(cutting_periods,'sequence',original)
    assert get(p)['sequence_repair'] is True
    get(p,'2026-10','/basis',status=409)
    act(p,'reopen','2026-11')
    lock(p)
    assert get(p)['next_month'] == '2026-11'


def test_changed_evidence_requires_new_preparation_and_operation_replay(month_client):
    p = month_client
    result, body = draft(p)
    assert p.post(URL + '/save', json=body).json() == result
    write(p, 'price', issue_id=p.issue_id, unit_cost='4', currency='HKD', price_reference='提交前发生价格更新')
    act(p, 'submit', status=409)
    draft(p)
    act(p, 'submit')
    act(p, 'return')
    assert get(p)['state'] == 'returned'
    fresh = command(month='2026-10', expected_version=get(p)['revision'])
    recovered = p.post(BASE + '/period-operations/recover', json=dict(action='submit', command=fresh))
    assert recovered.json()['state'] == 'abandoned'
    assert p.post(URL + '/submit', json=fresh).status_code == 409


def test_migration_immutability_and_partial_schema_fail_closed(month_client):
    p = month_client
    lock(p)
    with p.engine.begin() as db:
        with pytest.raises(Exception):
            db.execute(text("UPDATE cutting_ops_period_events SET reason='overwritten'"))
    with p.engine.begin() as db:
        db.execute(text('DROP TRIGGER cutting_period_no_delete'))
    get(p, status=503)
    assert report(p, day='2026-11-10', sets=1).status_code == 503


def test_current_month_cannot_prepare_and_no_migration_is_explicit(accounting):
    assert accounting.get(URL + '/2026-09', params={'factory_id':'huakang-c'}).status_code == 503


def test_current_month_and_overallocation_are_rejected(month_client):
    p=month_client
    get(p,'2026-12','/basis',status=409)
    get(p,'2027-01','/basis',status=422)
    draft(p,status=422,allocations=[dict(issue_id=p.issue_id,opening_completed_quantity='0',completed_quantity='3')])


def test_first_month_opening_and_zero_completion_validation(month_client):
    p=month_client
    # November's first closing must explicitly classify the October opening use.
    draft(p,'2026-11',allocations=[dict(issue_id=p.issue_id,opening_completed_quantity='1',completed_quantity='1.2')])
    value=get(p,'2026-11')['data']['snapshot']['costs']['HKD']
    assert value['opening_wip']=='3.12' and value['period_normal']=='0.00'
    assert value['period_completed']=='0.62' and value['ending_wip']=='2.50'
    draft(p,status=422,allocations=[dict(issue_id=p.issue_id,opening_completed_quantity='1',completed_quantity='1.2')])


def test_lock_and_source_change_serialize(month_client):
    from test_cutting_usage_concurrency import race
    p=month_client
    draft(p);act(p,'submit')
    p.cutting_auth['user']=replace(actor(*ACTIONS),id='reviewer')
    body=command(month='2026-10',expected_version=get(p)['revision'])
    results=race(lambda:p.post(URL+'/lock',json=body),lambda:report(p,document_id=p.report_id,sets=8))
    assert sorted(r.status_code for r in results)==[200,409]
    if get(p)['state']=='locked':
        assert get(p)['data']['snapshot']['orders'][0]['production'][0]['completed']==10


def test_missing_and_zero_cost_are_distinct(month_client):
    p=month_client
    write(p,'price',issue_id=p.issue_id,unit_cost='0',currency='CNY',price_reference='客户供料零成本凭据')
    lock(p)
    assert get(p)['data']['snapshot']['costs']['CNY']['ending_wip']=='0.00'


@pytest.mark.parametrize('month_client',[False],indirect=True)
def test_missing_price_blocks_close(month_client):
    draft(month_client)
    assert 'price' in {r['code'] for r in get(month_client)['data']['snapshot']['blockers']}
    act(month_client,'submit',status=409)


def test_unrelated_stock_and_later_same_order_facts_do_not_invalidate_month(month_client):
    p = month_client
    draft(p)
    saved = get(p)['data']['basis_token']
    warehouse_post(p, 'RECEIPT', quantity='20', source_no='later-stock', source_line='1', item_code='FAB-01',
                   item_name='蓝布', unit='米', location_id='bin', lot='LOT-2', counterparty='供方', business_date='2026-11-01')
    assert get(p, suffix='/basis')['basis_token'] == saved
    warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='0.5', location_id='bin', business_date='2026-11-02')
    assert report(p, day='2026-11-03', sets=2).status_code == 200
    write(p, 'post', issue_id=p.issue_id, day='2026-11-03', consumed_quantity='0.2', loss_quantity='0', counted_remaining='0.8')
    assert get(p, suffix='/basis')['basis_token'] == saved
    act(p, 'submit')
    p.cutting_auth['user'] = replace(actor(*ACTIONS), id='reviewer')
    act(p, 'lock')
    frozen = get(p)['data']['snapshot']
    assert frozen['allocations'][0]['ending_custody'] == '1.5'
    assert frozen['orders'][0]['production'][0]['completed'] == 10
    assert 'period_wip_unconfirmed' not in {item['code'] for item in frozen['notices']}


@pytest.mark.parametrize('change', ['report', 'same_quantity_correction', 'return', 'opening'])
def test_month_relevant_evidence_still_requires_repreparation(month_client, change):
    p = month_client
    month = '2026-11' if change == 'opening' else '2026-10'
    draft(p, month)
    if change in {'report', 'opening'}:
        assert report(p, day='2026-10-20', sets=2).status_code == 200
    elif change == 'same_quantity_correction':
        original = usage_read(p)['documents'][0]['id']
        write(p, 'correct', document_id=original, issue_id=p.issue_id, consumed_quantity='2',
              loss_quantity='0.5', counted_remaining='1.5')
    else:
        warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='0.5', location_id='bin')
    assert '依据' in act(p, 'submit', month, status=409)[0]['detail']


def test_future_only_plan_revision_does_not_invalidate_but_month_plan_does(month_client):
    from test_cutting_planning import task, save, publish
    from test_cutting_orders import read as order_read
    p = month_client
    p.cutting_auth['user'] = actor(*ACTIONS, 'plan_write', 'plan_publish')
    current = order_read(p)['current']['data']['planning']['published']['tasks'][0]
    resource = dict(id=current['resource_id'], version=current['resource_version'])
    tasks = [task(resource, target_sets=40, days=[dict(day='2026-10-15', sets=40)]),
             task(resource, task_id='future', target_sets=10, days=[dict(day='2026-11-03', sets=10)])]
    assert save(p, tasks).status_code == 200
    assert publish(p).status_code == 200
    draft(p)
    saved = get(p)['data']['basis_token']
    tasks[1]['days'] = [dict(day='2026-11-05', sets=10)]
    assert save(p, tasks).status_code == 200
    assert publish(p).status_code == 200
    assert get(p, suffix='/basis')['basis_token'] == saved
    tasks[0]['days'] = [dict(day='2026-10-16', sets=40)]
    assert save(p, tasks).status_code == 200
    assert publish(p).status_code == 200
    act(p, 'submit', status=409)


def test_review_compares_previous_preparation_not_identical_submit_or_lock(month_client):
    p = month_client
    first, _ = draft(p)
    assert get(p)['comparison'] is None
    second, _ = draft(p, allocations=[dict(issue_id=p.issue_id, opening_completed_quantity='0', completed_quantity='1.5')])
    act(p, 'submit')
    p.cutting_auth['user'] = replace(actor(*ACTIONS), id='reviewer')
    act(p, 'lock')
    review = get(p)['comparison']
    assert review['previous_id'] == first['id']
    assert review['rows'][0]['quantity_delta']['completed_quantity'] == '0.3'
    assert review['costs']['HKD']['ending_completed'] == '0.94'
    assert review['costs']['HKD']['ending_wip'] == '-0.94'
    assert get(p, event_id=first['id'])['comparison'] is None
    assert get(p, event_id=second['id'])['comparison'] == review


@pytest.mark.parametrize('month_client', [False], indirect=True)
def test_review_missing_price_and_currency_change_never_fake_zero_row_cost(month_client):
    p = month_client
    draft(p)
    write(p, 'price', issue_id=p.issue_id, unit_cost='3.125', currency='HKD', price_reference='本次确认价格凭据')
    draft(p)
    review = get(p)['comparison']
    assert review['partial_pricing'] and review['rows'][0]['amount_delta'] is None
    write(p, 'price', issue_id=p.issue_id, unit_cost='4', currency='CNY', price_reference='更正计价币种凭据')
    draft(p)
    review = get(p)['comparison']
    assert review['rows'][0]['amount_delta'] is None
    assert review['costs']['HKD']['ending_normal'] == '-6.25'
    assert review['costs']['CNY']['ending_normal'] == '8.00'
