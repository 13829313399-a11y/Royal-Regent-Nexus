"""P4a live previews: synthetic evidence and isolated databases only."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from copy import deepcopy
from sqlalchemy import text
import pytest
from fastapi import HTTPException
from app.services import cutting_closing as closing
from test_cutting_cost_allocation import accounting, custody, bridge, client, flow, planned, actor, allocate
from test_cutting_usage import write, read, consume
from test_cutting_materials import warehouse_view, warehouse_post, send, decision
from test_cutting_reporting import send as report, ok
from test_cutting_ops import BASE
from test_cutting_ops import command
from test_cutting_orders import read as order_read
from app.services import warehouse_operations as wh

URL = BASE + '/orders/line-1/closing-preview'


@pytest.fixture(autouse=True)
def fixed_business_clock(monkeypatch):
    monkeypatch.setattr(wh, 'business_now', lambda: datetime(2026, 10, 15, 12, tzinfo=ZoneInfo('Asia/Shanghai')))


def preview(p, month='2026-10', costs=False, status=200):
    response = p.get(URL, params=dict(factory_id='huakang-c', month=month, with_costs=costs))
    assert response.status_code == status, response.text
    return response.json()


def test_month_bounds_leap_year_and_shanghai_cutoff():
    assert closing.period('2024-02', date(2026, 10, 15)) == ('2024-02-01', '2024-02-29', '2024-02-29')
    assert closing.period('2026-10', date(2026, 10, 15)) == ('2026-10-01', '2026-10-31', '2026-10-15')
    for month in ('0000-01', '1999-12', '2101-01', '2026-13', '2026-1', '2026-11'):
        with pytest.raises(HTTPException) as error:
            closing.period(month, date(2026, 10, 15))
        assert error.value.status_code == 422


def test_read_only_reconciliation_and_cost_permission(accounting):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='3.125', currency='HKD', price_reference='原批次成本核定')
    before, revision = warehouse_view(p), read(p)['revision']
    physical = preview(p)
    assert physical['state'] == 'preview' and physical['partial']
    assert physical['production'][0]['completed'] == 10
    row = physical['materials'][0]
    assert (row['opening_quantity'], row['received_quantity'], row['consumed_quantity'], row['loss_quantity'], row['ending_quantity']) == ('0', '4', '2', '0.5', '1.5')
    assert 'costs' not in physical and 'price' not in row and 'normal_cost' not in row
    assert 'unit_cost' not in str(physical) and 'cost_at_post' not in str(physical)
    valued = preview(p, costs=True)
    assert valued['costs'] == {'HKD': {'normal': '6.25', 'loss': '1.56'}}
    assert valued['wip_status'] == 'not_frozen'
    assert valued['current_allocation_review'][0]['status'] == 'unconfirmed'
    assert warehouse_view(p) == before and read(p)['revision'] == revision
    p.cutting_auth['user'] = actor(warehouse=False, department='production')
    preview(p)
    preview(p, costs=True, status=403)
    p.cutting_auth['user'] = actor('cost_read', warehouse=False, department='engineering')
    preview(p, costs=True, status=403)
    assert p.get(URL, params={'factory_id': 'huakang-d', 'month': '2026-10'}).status_code == 422
    assert p.get(URL+'?factory_id=huakang-c&factory_id=huakang-d&month=2026-10').status_code == 422


def test_backfilled_production_and_use_corrections_recompute_with_trace(accounting):
    p = accounting
    original = read(p)['documents'][0]['id']
    write(p, 'correct', document_id=original, issue_id=p.issue_id, consumed_quantity='1.5', loss_quantity='0.5', counted_remaining='2')
    ok(report(p, document_id=p.report_id, sets=8))
    value = preview(p)
    assert value['production'][0]['completed'] == 8
    assert value['materials'][0]['consumed_quantity'] == '1.5'
    assert len(value['usage_documents']) == 2
    old = next(d for d in value['usage_documents'] if d['document_id'] == original)
    assert not old['effective'] and old['history'][-1]['replaced_by_document_id']
    assert len(value['production_documents'][0]['history']) == 2
    assert value['generated_at'] and value['basis']['usage_revision'] == read(p)['revision']
    # A new unsubmitted correction must not alter the authoritative eight sets.
    ok(report(p, 'save', document_id=p.report_id, sets=9))
    value = preview(p)
    assert value['production'][0]['completed'] == 8
    assert 'report_draft' in {i['code'] for i in value['issues']}


def test_missing_price_zero_price_and_current_revaluation(accounting):
    p = accounting
    value = preview(p, costs=True)
    assert value['costs'] == {} and value['pending_pricing'] == 1
    assert value['materials'][0]['normal_cost'] is None
    write(p, 'price', issue_id=p.issue_id, unit_cost='0', currency='CNY', price_reference='客户供料零成本凭据')
    value = preview(p, costs=True)
    assert value['costs']['CNY'] == {'normal': '0.00', 'loss': '0.00'} and value['pending_pricing'] == 0
    allocate(p)
    assert preview(p, costs=True)['current_allocation_review'][0]['status'] == 'confirmed'
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='USD', price_reference='原批次新成本凭据')
    value = preview(p, costs=True)
    assert value['costs'] == {'USD': {'normal': '4.00', 'loss': '1.00'}}
    assert value['price_basis'] == 'current_confirmed_batch_price' and value['wip_status'] == 'not_frozen'


def test_returns_same_day_receipt_and_historical_empty_period(accounting):
    p = accounting
    warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='1', location_id='bin', business_date='2026-10-11')
    value = preview(p)
    assert value['materials'][0]['returned_quantity'] == '1' and value['materials'][0]['ending_quantity'] == '0.5'
    prior = preview(p, '2026-09')
    assert prior['materials'] == [] and all(t['completed'] == 0 for t in prior['production'])
    assert prior['through'] == '2026-09-30' and not prior['partial']
    assert any(d['kind'] == 'RETURN' for d in value['warehouse_documents'])
    # Historical selection retains related future trace, without counting it in that month.
    assert any(d['kind'] == 'RETURN' for d in prior['warehouse_documents'])


def test_schema_failure_is_not_an_empty_month(accounting):
    with accounting.engine.begin() as conn:
        conn.execute(text('DROP TRIGGER cutting_production_no_delete'))
    preview(accounting, status=503)


def test_changed_resource_marks_plan_stale_without_changing_actuals(accounting):
    p = accounting
    resource = order_read(p)['current']['data']['planning']['published']['tasks'][0]['resource']
    original_actor = p.cutting_auth['user']
    p.cutting_auth['user'] = actor('master_write')
    changed = p.put(BASE + '/masters/' + resource['id'], json=command(kind='resource', code=resource['code'],
        expected_version=resource['version'], data=dict(resource['data'], name='调整后的执行方')))
    assert changed.status_code == 200, changed.text
    p.cutting_auth['user'] = original_actor
    assert order_read(p)['planning_summary']['published_stale']
    value = preview(p)
    assert value['plan_stale']
    assert next(i for i in value['issues'] if i['code'] == 'plan_stale')['workspace'] == 'planning'
    assert value['production'][0]['completed'] == 10
    assert value['materials'][0]['consumed_quantity'] == '2'


@pytest.mark.parametrize('bridge', ['outsourced'], indirect=True)
def test_outsourced_outstanding_tasks_have_distinct_actionable_notices(accounting):
    p = accounting
    value = preview(p)
    unreturned = next(i for i in value['issues'] if i['code'] == 'outsourced_unreturned')
    assert unreturned['task_id'] == 'task-1' and '10 套' in unreturned['message']
    assert unreturned['document_id'] == ''
    ok(report(p, kind='return', sets=6))
    value = preview(p)
    assert '4 套' in next(i['message'] for i in value['issues'] if i['code'] == 'outsourced_unreturned')
    assert '6 套' in next(i['message'] for i in value['issues'] if i['code'] == 'outsourced_reconcile')
    ok(report(p, kind='return', sets=4))
    ok(report(p, kind='accept', sets=8, rejected=2))
    value = preview(p)
    assert not any(i['code'].startswith('outsourced_') for i in value['issues'])
    assert value['production'][0]['completed'] == 8 and value['production'][0]['rejected'] == 2


def test_opening_evidence_preserves_later_corrections_and_physical_context(accounting, monkeypatch):
    p = accounting
    monkeypatch.setattr(wh, 'business_now', lambda: datetime(2026, 11, 15, 12, tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr('app.services.cutting_planning.business_today', lambda: date(2026, 11, 15))
    value = preview(p, '2026-11')
    assert value['production'][0]['opening_completed'] == 10
    assert value['materials'][0]['opening_quantity'] == '1.5'
    assert value['production_documents'][0]['scope']['opening']
    use = value['usage_documents'][0]
    assert use['scope']['opening'] and not use['scope']['period']
    assert use['context']['issue_id'] == p.issue_id and use['context']['unit'] == '米'
    write(p, 'correct', document_id=use['document_id'], issue_id=p.issue_id,
          consumed_quantity='1.5', loss_quantity='0.5', counted_remaining='2')
    ok(report(p, document_id=p.report_id, day='2026-11-01', sets=8))
    value = preview(p, '2026-10')
    production_doc = value['production_documents'][0]
    assert not production_doc['scope']['period'] and production_doc['scope']['period_history']
    assert value['production'][0]['completed'] == 0
    original = next(d for d in value['usage_documents'] if d['document_id'] == use['document_id'])
    assert not original['effective'] and original['history'][-1]['action'] == 'void'
    assert original['history'][-1]['entry'] == {'day': '2026-11-15'}
    assert original['history'][-1]['replaced_by_document_id']
    assert value['materials'][0]['consumed_quantity'] == '1.5'
    assert 'unit_cost' not in str(value) and 'cost_at_post' not in str(value)
    movement = next(e for e in value['warehouse_documents'] if e['kind'] == 'CUTTING_RECEIPT')
    assert movement['context']['issue_id'] == p.issue_id and movement['scope'] == 'period'
    prior = preview(p, '2026-09')
    assert prior['production_documents'] == [] and prior['usage_documents'] == []


def physical_fixture():
    context = dict(line_id='line', task_id='task', task_name='裁剪', resource_name='车间')
    entries = {
        'request': dict(id='request', kind='REQUEST', data={'cutting_request': context}),
        'issue': dict(id='issue', kind='ISSUE', business_date='2026-09-30',
                      data=dict(original_id='request', quantity='2', item_name='蓝布', item_code='FAB', unit='米'),
                      batch_snapshot=dict(original_batch_id='root', lot='L', roll_no='R', location='库位')),
        'receipt': dict(id='receipt', kind='CUTTING_RECEIPT', business_date='2026-09-30', data=dict(original_id='issue', quantity='2')),
    }
    docs = {day: {'posted': {'data': {'entry': dict(issue_id='issue', day=day, consumed_quantity='0.005', loss_quantity='0')}}}
            for day in ('2026-09-30', '2026-10-01')}
    price = {'root': {'data': {'entry': {'unit_cost': '1', 'currency': 'CNY'}}}}
    return entries, docs, price


def test_monthly_cent_residuals_conserve_cumulative_cost_and_unit_balances():
    entries, docs, price = physical_fixture()
    september, a, _ = closing.material_rows(entries, docs, 'line', '2026-09-01', '2026-09-30', price)
    october, b, _ = closing.material_rows(entries, docs, 'line', '2026-10-01', '2026-10-31', price)
    assert a['CNY']['normal'] == '0.01' and b['CNY']['normal'] == '0.00'
    assert october[0]['opening_quantity'] == september[0]['ending_quantity'] == '1.995'
    assert october[0]['ending_quantity'] == '1.990'
    assert Decimal(a['CNY']['normal']) + Decimal(b['CNY']['normal']) == Decimal('0.01')
    # Another order and a reversed issue cannot contribute either physical quantity or money.
    entries['issue']['reversed'] = True
    assert closing.material_rows(entries, {}, 'line', '2026-10-01', '2026-10-31', price)[0] == []
    entries['issue']['reversed'] = False
    assert closing.material_rows(entries, docs, 'other', '2026-10-01', '2026-10-31', price)[0] == []


def report_doc(kind, day, sets, version, *, execution='internal', mode='sets', parts=None):
    return dict(first_post_version=version, posted=dict(data=dict(
        entry=dict(task_id='task', day=day, kind=kind, sets=sets, rejected=0, scrap=0, parts=parts or [], mode=mode, exception_reason='核对'),
        context=dict(task_name='裁剪', resource_name='执行方', execution=execution, task_target=100,
                     parts=[dict(code='A', name='左片', pieces_per_set=2), dict(code='B', name='右片', pieces_per_set=1)]))))


def test_cross_month_outsourced_acceptance_is_separate_from_claims_and_handover():
    docs = {i: report_doc(kind, day, count, i, execution='outsourced') for i, (kind, day, count) in enumerate([
        ('daily', '2026-09-30', 10), ('return', '2026-09-30', 8), ('accept', '2026-10-01', 6), ('handover', '2026-10-02', 5)])}
    row = closing.production(docs, None, '2026-10-01', '2026-10-31')[0]
    assert row['claimed'] == 0 and row['returned'] == 0
    assert row['accepted'] == row['completed'] == 6 and row['handed'] == 5
    assert row['pending_acceptance'] == 2 and row['pending_return'] == 2


def test_parts_pair_across_months_and_zero_daily_is_not_missing():
    docs = {0: report_doc('daily', '2026-09-30', 0, 1, mode='parts', parts=[dict(code='A', good=4, rejected=0, scrap=0)]),
            1: report_doc('daily', '2026-10-01', 0, 2, mode='parts', parts=[dict(code='B', good=2, rejected=0, scrap=0)]),
            2: report_doc('match', '2026-10-01', 2, 3, mode='parts')}
    plan = dict(tasks=[dict(task_id='task', days=[dict(day='2026-10-01', sets=2), dict(day='2026-10-02', sets=2), dict(day='2026-10-31', sets=2)])])
    row = closing.production(docs, plan, '2026-10-01', '2026-10-15')[0]
    assert row['opening_completed'] == 0 and row['completed'] == 2
    assert row['missing_days'] == ['2026-10-02'] and row['planned'] == 4
    assert all(p['quantity'] == 0 for p in row['loose'])
