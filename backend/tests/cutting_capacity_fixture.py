"""Production-chain samples created through authenticated APIs, no row cloning."""
from copy import deepcopy
import httpx

from test_cutting_p5b_acceptance import (
    BASE, login, ok, actual_plan, report, reports, material_send, request_body,
    material_decision, warehouse_post, plan_save, publish, post, batch,
    consume, allocate, write, period_read, draft, act, order_read,
)


class OrderClient:
    """Adapt legacy single-order test helpers to an explicit source line."""
    def __init__(self, client, line_id):
        self.client, self.line_id = client, line_id

    def __getattr__(self, name):
        return getattr(self.client, name)

    def get(self, url, **kwargs):
        if url == BASE + '/orders?factory_id=huakang-c':
            response = self.client.get(BASE + '/orders/' + self.line_id,
                                       params={'factory_id': 'huakang-c'})
            assert response.status_code == 200, response.text
            return httpx.Response(200, json={'data': [response.json()]}, request=response.request)
        return self.client.get(url.replace('/orders/line-1', '/orders/' + self.line_id), **kwargs)

    def post(self, url, **kwargs):
        return self.client.post(url.replace('/orders/line-1', '/orders/' + self.line_id), **kwargs)


def expand_chains(p, count):
    """Existing closed line-1 + count-1 new chains; aggregate month reclosed by API."""
    login(p, 'reviewer')
    act(p, 'reopen')
    original = ok(p.get(BASE+'/orders/line-1', params={'factory_id': 'huakang-c'}))
    source = original['current']['data']
    tasks = [dict(task_id=t['task_id'], name=t['name'], resource_id=t['resource_id'],
                  resource_version=t['resource_version'], target_sets=25,
                  materials=[dict(row=0, expected_date='2026-10-12')],
                  readiness_basis='合成样本经主管核对', days=[dict(day='2026-10-15', sets=25)])
             for t in source['planning']['published']['tasks']]
    login(p, 'warehouse')
    stock = warehouse_post(p, 'RECEIPT', quantity=str(count*10), source_no='HTTP-EXPANSION',
                           source_line='1', item_code='FAB-01', item_name='蓝布', unit='米',
                           location_id='bin', lot='HTTP-LOT', counterparty='合成供方')
    internal_issues = [p.issue_id]
    for i in range(1, count):
        scoped = OrderClient(p, f'http-capacity-{i}')
        scoped.stock_id = stock['id']
        login(p, 'clerk')
        current = order_read(scoped)
        row = ok(post(scoped, 'receive', dispatch_id=current['dispatch_id']))
        login(p, 'engineering')
        row = ok(post(scoped, 'bom', expected_version=row['current']['version'],
                      bom_id=source['bom']['id'], bom_version=source['bom']['version'],
                      target_sets=50, quantity_basis='100件，每套2件'))
        row = ok(post(scoped, 'requisition', expected_version=row['current']['version'],
                      lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')]))
        login(p, 'procurement')
        ok(post(scoped, 'eta', expected_version=row['current']['version'],
                requisition_version=row['current']['data']['requisition']['version'],
                batches=[dict(batch(quantity='7'), expected_date='2026-10-12')]))
        login(p, 'supervisor')
        ok(plan_save(scoped, deepcopy(tasks)))
        ok(publish(scoped))
        receipts = {}
        for task_id, quantity in [('task-1', '4'), ('external', '2')]:
            login(p, 'clerk')
            request = material_send(scoped, 'request', request_body(scoped) |
                                    dict(task_id=task_id, quantity=quantity))
            login(p, 'warehouse')
            issued = warehouse_post(p, 'ISSUE', original_id=request['id'], batch_id=stock['id'],
                                    quantity=quantity, counterparty='R01' if task_id == 'task-1' else 'R02')
            login(p, 'clerk')
            receipt = material_send(scoped, 'receive', material_decision(scoped, issued, quantity=quantity))
            receipts[task_id] = [receipt['id']]
            if task_id == 'task-1':
                scoped.issue_id = issued['id']
                internal_issues.append(issued['id'])
        actual_plan(scoped, receipts)
        login(p, 'clerk')
        ok(report(scoped, sets=10, exception_reason=''))
        ok(report(scoped, kind='handover', sets=8))
        ok(report(scoped, task_id='external', sets=20, exception_reason=''))
        ok(report(scoped, task_id='external', kind='return', sets=18))
        login(p, 'supervisor')
        ok(report(scoped, task_id='external', kind='accept', sets=15, rejected=2))
        login(p, 'clerk')
        ok(report(scoped, task_id='external', kind='handover', sets=14))
        assert reports(scoped)['summary']['completed'] == 25
        consume(scoped)
        if i == 1:
            login(p, 'procurement')
            write(scoped, 'price', issue_id=scoped.issue_id, unit_cost='4', currency='HKD',
                  price_reference='合成批次正式计价依据')
        login(p, 'supervisor')
        allocate(scoped)
        if i % 10 == 0:
            print(f'created production chains: {i+1}/{count}', flush=True)
    login(p, 'supervisor')
    basis = period_read(p, suffix='/basis')
    draft(p, allocations=[dict(issue_id=r['issue_id'], opening_completed_quantity='0',
           completed_quantity='1.2' if r['issue_id'] in internal_issues else '0') for r in basis['rows']])
    act(p, 'submit')
    login(p, 'reviewer')
    act(p, 'lock')
    assert period_read(p)['data']['snapshot']['costs']['HKD']['period_normal'] == f'{8*count:.2f}'
    return internal_issues
