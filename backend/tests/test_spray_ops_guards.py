"""Regression cases found in the separate workflow review."""
from decimal import Decimal
from uuid import uuid4
import pytest

from test_spray_ops import client, setup_order, post, read, payload, manual_scenario, publish, start, report, approved_rule


def test_unknown_material_cost_is_resolved_by_separate_evidence_not_history_rewrite(client):
    material = post(client, 'materials', code='UNKNOWN-M', name='成本待核材料', unit='KG')
    purchase = post(client, 'purchases', document_no='UNKNOWN-PO', business_date='2026-09-01', supplier='合成', currency='CNY', tax_basis='测试', lines=[dict(material_id=material['id'], quantity='100', unit='KG', due_date='2026-09-03')])
    received = post(client, 'material-receipts', document_no='UNKNOWN-MR', business_date='2026-09-02', supplier='合成', lines=[dict(purchase_line_id=purchase['lines'][0]['id'], quantity='100', unit='KG')])
    lot = received['lots'][0]
    issue = post(client, f"material-lots/{lot['id']}/move", expected_version=lot['version'], business_date='2026-09-02', kind='issue', quantity='20', reason='成本未知但允许实物流转')
    consumed = post(client, f"material-lots/{lot['id']}/move", expected_version=issue['lot']['version'], business_date='2026-09-02', kind='consume', quantity='8', issue_id=issue['id'], reason='实际耗用')
    assert consumed['cost'] is None
    body = payload(expected_version=consumed['lot']['version'], unit_cost='9.2', evidence='原发票已核对，并非新价', business_date='2026-09-22')
    path = f"/api/spray-operations/material-lots/{lot['id']}/cost"
    result = client.post(path, json=body)
    assert result.status_code == 200, result.text
    assert client.post(path, json=body).json()['data'] == result.json()['data']
    assert read(client, f"material-movements/{consumed['id']}")['cost'] is None
    adjustment = result.json()['data']['adjustments'][0]
    assert adjustment['issue_id'] == consumed['id'] and Decimal(adjustment['cost']) == Decimal('73.6')
    summary = client.get('/api/spray-operations/finance/economics', params=dict(factory_id='huaxing', month='2026-09')).json()['data']
    assert Decimal(summary['material_cost']) == Decimal('73.6')
    assert summary['missing']['unknown_material_cost'] == 0
    latest = result.json()['data']['lot']
    rejected = client.post(path, json=payload(expected_version=latest['version'], unit_cost='12', evidence='今日新价不允许', business_date='2026-09-22'))
    assert rejected.status_code == 409 and rejected.json()['code'] == 'cost_frozen'
    returned = post(client, f"material-lots/{lot['id']}/move", expected_version=latest['version'], business_date='2026-09-22', kind='return', quantity='12', issue_id=issue['id'], reason='退原批')
    assert Decimal(returned['lot']['warehouse']) == 92


def test_expense_inclusion_can_be_confirmed_once_with_evidence(client):
    item = post(client, 'expenses', document_no='PENDING-EXP', business_date='2026-09-02', category='待核归集', kind='expense', amount='15', currency='CNY', evidence='来源记录')
    resolved = post(client, f"expenses/{item['id']}/confirm", expected_version=item['version'], business_date='2026-09-22', included=False, reason='负责人确认不纳入经营成本')
    assert resolved['included'] is False and '来源记录' in resolved['evidence']
    response = client.post(f"/api/spray-operations/expenses/{item['id']}/confirm", json=payload(expected_version=resolved['version'], business_date='2026-09-22', included=True, reason='不能覆盖已确认口径'))
    assert response.status_code == 409


def test_order_drilldown_filters_actual_ids_and_rejects_other_factory(client):
    setup = setup_order(client)
    daily = report(client, start(client, publish(client, manual_scenario(client, setup))))
    other = post(client, 'demands', document_no='OTHER', counterparty='测试委托方', business_date='2026-09-01', lines=[dict(item_no='00017', part='左件', color='灰色 V1', quantity='5', due_date='2026-10-01', route_id=setup['route']['id'], commercial_price='2.07', price_evidence='合成')])
    for collection in ['tasks', 'reports', 'stock', 'batches', 'deliveries', 'settlements']:
        response = client.get('/api/spray-operations/' + collection, params=dict(factory_id='huaxing', demand_id=other['id']))
        assert response.status_code == 200, response.text
        assert response.json()['data'] == []
    found = client.get('/api/spray-operations/reports', params=dict(factory_id='huaxing', demand_id=setup['demand']['id']))
    assert found.json()['data'][0]['id'] == daily['id']
    assert client.get('/api/spray-operations/tasks', params=dict(factory_id='huakang-a', demand_id=setup['demand']['id'])).status_code == 404


def test_month_close_uses_known_original_currency_cost_not_cny_assumption(client):
    setup = setup_order(client)
    task = start(client, publish(client, manual_scenario(client, setup)))
    employee = post(client, 'employees', code='E1', name='合成员工')
    q = dict(processed='1000', good='1000', normal='1000')
    daily = post(client, 'reports', document_no='HKD-DAILY', business_date='2026-09-02', shift='合成', rows=[dict(task_id=task['id'], **q, allocations=[dict(task_allocation_id=task['allocations'][0]['id'], **q)], labor=[dict(employee_id=employee['id'], hours='8')])])
    wage = approved_rule(client, 'wage', dict(method='team_piece', basis='processed', rate='0.82', currency='CNY'))
    trial = post(client, 'payroll/trial', document_no='PAY', business_date='2026-09-02', rule_id=wage['id'])
    post(client, f"payroll/{trial['id']}/confirm", expected_version=trial['version'])
    price = approved_rule(client, 'operation_price', dict(price='2.07', currency='HKD'), step_id=setup['route']['steps'][0]['id'])
    post(client, 'valuations', expected_version=daily['version'], report_id=daily['id'], rule_id=price['id'], business_date='2026-09-02')
    material = post(client, 'materials', code='M', name='合成材料', unit='KG')
    purchase = post(client, 'purchases', document_no='PO', business_date='2026-09-01', supplier='合成', currency='HKD', tax_basis='测试', lines=[dict(material_id=material['id'], quantity='10', unit='KG', price='5', due_date='2026-09-03')])
    received = post(client, 'material-receipts', document_no='MR', business_date='2026-09-02', supplier='合成', lines=[dict(purchase_line_id=purchase['lines'][0]['id'], quantity='10', unit='KG')])
    lot = received['lots'][0]
    issue = post(client, f"material-lots/{lot['id']}/move", expected_version=lot['version'], business_date='2026-09-02', kind='issue', quantity='2', reason='测试领料')
    post(client, f"material-lots/{lot['id']}/move", expected_version=issue['lot']['version'], business_date='2026-09-02', kind='consume', quantity='1', issue_id=issue['id'], reason='测试耗用')
    post(client, 'expenses', document_no='EXP', business_date='2026-09-02', category='合成核对', kind='memo', amount='0', currency='CNY', included=False, evidence='明确核对：本期无另计费用')
    finished = next(item for item in read(client, 'stock') if item['state'] == 'finished')
    delivery = post(client, 'deliveries', document_no='SEND-CLOSE', counterparty='测试委托方', business_date='2026-09-02', lines=[dict(stock_id=finished['id'], quantity='1000')])
    accepted = post(client, f"deliveries/{delivery['id']}/accept", expected_version=delivery['version'], business_date='2026-09-02', lines=[dict(delivery_line_id=delivery['lines'][0]['id'], accepted='1000')])
    settlement = post(client, 'settlements', document_no='SET-CLOSE', counterparty='测试委托方', month='2026-09', currency='CNY', business_date='2026-09-02', lines=[dict(delivery_line_id=accepted['lines'][0]['id'], quantity='600')])
    delivery_line = read(client, 'delivery-lines')[0]
    returned = post(client, 'returns', expected_version=delivery_line['version'], business_date='2026-09-02', delivery_line_id=delivery_line['id'], quantity='450', reason='合成退货核对')
    pending = client.get('/api/spray-operations/periods/preview', params=dict(factory_id='huaxing', month='2026-09')).json()['data']
    assert 'credit_pending' in {item['code'] for item in pending['blockers']}
    credit = post(client, 'credits', return_id=returned['id'], settlement_line_id=settlement['lines'][0]['id'], quantity='50', business_date='2026-09-02', reason='超出未结余量部分按原价贷项')
    assert Decimal(credit['amount']) == Decimal('103.50')
    assert Decimal(settlement['total_amount']) == Decimal('1242.00')
    preview = client.get('/api/spray-operations/periods/preview', params=dict(factory_id='huaxing', month='2026-09')).json()['data']
    assert preview['blockers'] == []
    summary = client.get('/api/spray-operations/finance/economics', params=dict(factory_id='huaxing', month='2026-09', currency='CNY')).json()['data']
    assert summary['surplus'] is None and summary['is_partial']
    assert summary['operating_value'] is None and summary['material_cost'] is None
    period = post(client, 'periods/close', month='2026-09', business_date='2026-10-01', reason='合成混币各自冻结', fingerprint=preview['fingerprint'])
    assert period['status'] == 'closed'


@pytest.mark.parametrize('invalid', ['abc', '1,234', '', None])
def test_bad_decimal_is_correctable_validation_error(client, invalid):
    response = client.post('/api/spray-operations/expenses', json=payload(document_no='BAD-NUMBER', business_date='2026-09-22', category='合成测试', kind='expense', amount=invalid, currency='CNY', included=True, evidence='无业务影响'))
    assert response.status_code == 422
    assert response.json()['code'] == 'validation_error'
    assert read(client, 'expenses') == []


def test_auto_plan_splits_across_shifts_and_publishes_conserved_quantity(client):
    setup = setup_order(client, quantity="1500")
    post(client, f"resources/{setup['resource']['id']}/calendar", expected_version=1, calendar=[
        dict(start_at="2026-09-02T00:00:00Z", end_at="2026-09-02T01:00:00Z"),
        dict(start_at="2026-09-03T00:00:00Z", end_at="2026-09-03T01:00:00Z"),
    ])
    plan = post(client, "scenarios/preview", start_at="2026-09-02T00:00:00Z", end_at="2026-09-04T00:00:00Z")
    assert [Decimal(t['allocations'][0]['quantity']) for t in plan['snapshot']['tasks']] == [1000, 500]
    assert not plan['snapshot']['unplanned']
    publish(client, plan)
    assert Decimal(read(client, 'stock')[0]['reserved']) == 1500


def test_partial_acceptance_keeps_earlier_month_eligibility(client):
    setup = setup_order(client)
    report(client, start(client, publish(client, manual_scenario(client, setup))), good='1000', hold='0', scrap='0')
    stock = next(s for s in read(client, 'stock') if s['state'] == 'finished')
    delivery = post(client, 'deliveries', document_no='SPLIT-DATE', counterparty='测试委托方', business_date='2026-09-02', lines=[dict(stock_id=stock['id'], quantity='1000')])
    line_id = delivery['lines'][0]['id']
    for date, qty in [('2026-09-03', '600'), ('2026-10-01', '400')]:
        delivery = post(client, f"deliveries/{delivery['id']}/accept", expected_version=delivery['version'], business_date=date, lines=[dict(delivery_line_id=line_id, accepted=qty)])
    assert len(delivery['lines'][0]['acceptances']) == 2
    blocked = client.post('/api/spray-operations/settlements', json=payload(document_no='TOO-MUCH', counterparty='测试委托方', business_date='2026-09-30', month='2026-09', currency='CNY', lines=[dict(delivery_line_id=line_id, quantity='601')]))
    assert blocked.status_code == 409
    settled = post(client, 'settlements', document_no='SEPTEMBER', counterparty='测试委托方', business_date='2026-09-30', month='2026-09', currency='CNY', lines=[dict(delivery_line_id=line_id, quantity='600')])
    assert Decimal(settled['total_amount']) == Decimal('1242')
    assert Decimal(read(client, 'deliveries')[0]['lines'][0]['settled']) == 600


def test_opening_cutover_never_replays_or_counts_as_inbound(client):
    setup = setup_order(client)
    # This independent order has no historical movements. The existing setup's
    # September movements remain later than the August cutover.
    post(client, 'history-policy', mode='opening', cutoff='2026-08-31', evidence='合成期初清点')
    demand = post(client, 'demands', document_no='OPEN-DEMAND', counterparty='测试方', business_date='2026-08-30', lines=[dict(item_no='00018', part='右', color='灰', quantity='500', due_date='2026-10-01', route_id=setup['route']['id'])])
    opened = post(client, 'openings', document_no='OPEN-01', line_id=demand['lines'][0]['id'], business_date='2026-08-31', quantity='400', unit='件', state='finished', completed_step_ids=[setup['route']['steps'][0]['id']], evidence='合成盘点签认')
    assert opened['stock']['state'] == 'finished'
    actual = client.get('/api/spray-operations/demands/'+demand['id'], params=dict(factory_id='huaxing')).json()['data']['lines'][0]
    assert Decimal(actual['received']) == 0
    assert Decimal(actual['opening_balance']) == 400
    blocked = client.post('/api/spray-operations/batches', json=payload(document_no='REPLAY', business_date='2026-08-31', line_id=demand['lines'][0]['id'], item_no='00018', part='右', quantity='1', accepted='1'))
    assert blocked.status_code == 409 and blocked.json()['code'] == 'opening_replay_conflict'
    assert read(client, 'reports') == []


def test_labor_revision_preserves_old_trial_but_invalidates_confirmation(client):
    setup = setup_order(client)
    daily = report(client, start(client, publish(client, manual_scenario(client, setup))))
    employee = post(client, 'employees', code='TRIAL-E', name='测试员工')
    def labor(hours, version):
        return post(client, f"reports/{daily['id']}/labor", expected_version=version, business_date='2026-09-02', row_id=daily['rows'][0]['id'], reason='纸质核实', labor=[dict(employee_id=employee['id'], hours=hours)])
    amended = labor('8', daily['version'])
    rule = approved_rule(client, 'wage', dict(method='hourly', basis='processed', rate='10', currency='CNY'))
    trial = post(client, 'payroll/trial', document_no='BEFORE', business_date='2026-09-02', rule_id=rule['id'])
    changed = labor('7', amended['version'])
    assert Decimal(changed['rows'][0]['labor'][0]['hours']) == 7
    stale = client.post(f"/api/spray-operations/payroll/{trial['id']}/confirm", json=payload(expected_version=trial['version']))
    assert stale.status_code == 409 and stale.json()['code'] == 'stale_payroll'
    assert sum(Decimal(row['payroll_amount']) for row in read(client, 'payroll')[0]['lines']) == 80


def test_draft_can_be_corrected_before_stock_effects_and_confirmed_once(client):
    setup = setup_order(client)
    task = start(client, publish(client, manual_scenario(client, setup)))
    draft = report(client, task, qty='100', good='100', hold='0', scrap='0', confirm=False)
    quantities = dict(processed='200', good='200', hold='0', scrap='0', normal='200', overtime='0')
    fields = dict(document_no=draft['document_no'], business_date=draft['business_date'], shift=draft['shift'], reason='原纸单二次核对', rows=[dict(task_id=task['id'], **quantities, allocations=[dict(task_allocation_id=task['allocations'][0]['id'], **quantities)])])
    amended = post(client, f"reports/{draft['id']}/amend", expected_version=draft['version'], **fields)
    assert Decimal(amended['previous_draft']['rows'][0]['processed']) == 100
    assert Decimal(read(client, 'stock')[0]['quantity']) == 1000
    confirmed = post(client, f"reports/{draft['id']}/confirm", expected_version=amended['version'])
    assert sum(Decimal(s['quantity']) for s in read(client, 'stock') if s['state'] == 'finished') == 200
    blocked = client.post(f"/api/spray-operations/reports/{draft['id']}/amend", json=payload(expected_version=confirmed['version'], **fields))
    assert blocked.status_code == 409 and blocked.json()['code'] == 'report_frozen'
    journey = client.get('/api/spray-operations/demands/'+setup['demand']['id'], params=dict(factory_id='huaxing')).json()['data']['journey']
    assert Decimal(journey[0]['processed']) == 200


def test_running_overrun_and_pause_never_release_capacity(client):
    setup = setup_order(client)
    task = start(client, publish(client, manual_scenario(client, setup, qty="500")))
    paused = post(client, f"tasks/{task['id']}/pause", expected_version=task['version'], business_date="2026-09-02", reason="合成停机")
    scenario = post(client, "scenarios/preview", start_at="2026-09-03T00:00:00Z", end_at="2026-09-04T00:00:00Z")
    assert scenario['snapshot']['tasks'] == []
    resumed = post(client, f"tasks/{task['id']}/resume", expected_version=paused['version'], business_date="2026-09-03", reason="已修复")
    assert resumed['status'] == 'started'
    assert Decimal(read(client, 'stock')[0]['reserved']) == 500


def test_confirm_draft_and_attach_route_before_scheduling(client):
    setup = setup_order(client)
    draft = post(client, 'demands', document_no='DRAFT-02', counterparty='测试方', business_date='2026-09-02', confirm=False, lines=[dict(item_no='0002',part='左',color='灰',quantity='100',due_date='2026-10-01')])
    amended = post(client, f"demands/{draft['id']}/amend", expected_version=draft['version'], business_date='2026-09-02', line_id=draft['lines'][0]['id'],quantity='100',due_date='2026-10-01',priority=3,route_id=setup['route']['id'],reason='工艺核实')
    confirmed = post(client, f"demands/{draft['id']}/confirm", expected_version=amended['version'])
    assert confirmed['status'] == 'confirmed'
    assert confirmed['lines'][0]['route_id'] == setup['route']['id']


def test_labor_can_be_completed_without_repeating_production(client):
    setup = setup_order(client)
    daily = report(client, start(client, publish(client, manual_scenario(client, setup))))
    employee = post(client, 'employees',code='E-1',name='合成工人')
    updated = post(client, f"reports/{daily['id']}/labor", expected_version=daily['version'],business_date='2026-09-02',row_id=daily['rows'][0]['id'],reason='纸质签认工时',labor=[dict(employee_id=employee['id'],hours='8')])
    assert updated['rows'][0]['labor'][0]['hours'] == '8.000000'
    assert Decimal(read(client,'tasks')[0]['reported']) == 1000
    assert sum(Decimal(s['quantity']) for s in read(client,'stock')) == 950


def test_close_blocks_missing_material_evidence(client):
    setup=setup_order(client)
    report(client,start(client,publish(client,manual_scenario(client,setup))))
    preview=client.get('/api/spray-operations/periods/preview',params=dict(factory_id='huaxing',month='2026-09')).json()['data']
    assert 'material_coverage' in {b['code'] for b in preview['blockers']}


def test_return_rework_requires_explicit_start_and_can_be_scheduled(client):
    setup=setup_order(client)
    report(client,start(client,publish(client,manual_scenario(client,setup))),good='1000',hold='0',scrap='0')
    stock=next(s for s in read(client,'stock') if s['state']=='finished')
    delivery=post(client,'deliveries',document_no='SEND',counterparty='测试委托方',business_date='2026-09-22',lines=[dict(stock_id=stock['id'],quantity='100')])
    delivery=post(client,f"deliveries/{delivery['id']}/accept",expected_version=delivery['version'],business_date='2026-09-22',lines=[dict(delivery_line_id=delivery['lines'][0]['id'],accepted='100')])
    post(client,'returns',expected_version=delivery['lines'][0]['version'],business_date='2026-09-22',delivery_line_id=delivery['lines'][0]['id'],quantity='10',reason='客户退货')
    held=next(s for s in read(client,'stock') if s['state']=='hold')
    body=payload(expected_version=held['version'],business_date='2026-09-22',rework='10',reason='复检返工')
    rejected=client.post(f"/api/spray-operations/stock/{held['id']}/quality",json=body)
    assert rejected.status_code == 409
    result=post(client,f"stock/{held['id']}/quality",expected_version=held['version'],business_date='2026-09-22',rework='10',reason='返工起点已确认',rework_step_id=setup['route']['steps'][0]['id'])
    assert result['outputs'][0]['state'] == 'white'


def test_conditional_plan_only_reserves_capacity_until_real_batch_match(client):
    setup=setup_order(client,quantity='50000',second_batch=True)
    forecast=post(client,'forecasts',line_id=setup['line']['id'],step_id=setup['route']['steps'][0]['id'],resource_id=setup['resource']['id'],start_at='2026-09-23T00:00:00Z',end_at='2026-09-24T00:00:00Z',expected_ready_at='2026-09-22T00:00:00Z',quantity='10000',condition='预计第二批来料，仍需现场核对')
    assert Decimal(read(client,'stock')[0]['reserved'])==0
    assert read(client,'tasks')==[]
    response=client.post(f"/api/spray-operations/forecasts/{forecast['id']}/convert",json=payload(expected_version=forecast['version'],allocations=[dict(stock_id=setup['stock']['id'],quantity='10000')]))
    assert response.status_code==409
    assert read(client,'forecasts')[0]['status']=='conditional'
    cancelled=post(client,f"forecasts/{forecast['id']}/cancel",expected_version=forecast['version'],business_date='2026-09-22',reason='来料推迟')
    assert cancelled['status']=='cancelled'
    feasible=post(client,'forecasts',line_id=setup['line']['id'],step_id=setup['route']['steps'][0]['id'],resource_id=setup['resource']['id'],start_at='2026-09-23T00:00:00Z',end_at='2026-09-24T00:00:00Z',expected_ready_at='2026-09-22T00:00:00Z',quantity='5000',condition='实物已齐备，待核对兑现')
    converted=post(client,f"forecasts/{feasible['id']}/convert",expected_version=feasible['version'],allocations=[dict(stock_id=setup['stock']['id'],quantity='5000')])
    assert converted['task']['status']=='planned'
    assert Decimal(read(client,'stock')[0]['reserved'])==5000
