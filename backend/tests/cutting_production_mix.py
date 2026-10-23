"""Client-side checks for synthetic full-app handover/usage writes.

No application patching or database writes live here. All commands use the
caller's authenticated HTTP client against its separately guarded fixture.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4


D = Decimal


def quantity(value):
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


class ProductionMix:
    def __init__(self, read, inventory, costs, count):
        assert 1 <= count <= 40
        self.inventory = {r['issue_id']: r for r in inventory}
        self.costs = {r['line_id']: r for r in costs}
        candidates = sorted((r for r in inventory if r['context']['execution'] == 'internal'
            and r['line_id'].startswith('http-capacity-')
            and int(r['line_id'].rsplit('-', 1)[1]) >= 3),
            key=lambda r: int(r['line_id'].rsplit('-', 1)[1]))
        assert len(candidates) >= count*2
        self.targets = [candidates[:count], candidates[count:count*2]]
        self.handover_baseline = {}
        self.handover_documents = {}
        self.usage_documents = {}
        self.records = [[], []]
        for row in self.targets[0]:
            line = row['line_id']
            value = read('/orders/'+line+'/reports')
            assert value['summary']['completed']-value['summary']['actual_delivery'] >= 2
            self.handover_baseline[line] = value['summary']
            self.handover_documents[line] = uuid4().hex
        for row in self.targets[1]:
            assert D(row['remaining_quantity']) >= D('.2')
            value = read('/orders/'+row['line_id']+'/usage', with_costs=True)
            issue = next(r for r in value['issues'] if r['issue_id'] == row['issue_id'])
            assert issue['price']['data']['entry']['unit_cost'] == '4'
            assert issue['price']['data']['entry']['currency'] == 'HKD'

    def write(self, index, cycle, get, post):
        row = self.targets[index][cycle % len(self.targets[index])]
        line, issue = row['line_id'], row['issue_id']
        # Revisit each target with a different value; repeating requests alone
        # must never create another fact. The API still enforces its own guards.
        turn = cycle // len(self.targets[index])
        if index == 0:
            path = '/orders/'+line+'/reports'
            current = get('handover_basis', path, history_page=1)
            task = next(t for t in current['tasks'] if t['task_id'] == 'task-1')
            sets = 1+turn % 2
            body = dict(factory_id='huakang-c', operation_id=uuid4().hex,
                expected_version=current['version'], reason='Synthetic P5c rotating handover',
                document_id=self.handover_documents[line], entry=dict(task_id='task-1',
                plan_version=task['plan_version'], day='2026-12-14', mode='sets', kind='handover',
                sets=sets, rejected=0, scrap=0, parts=[], evidence='Synthetic P5c rotation', exception_reason=''))
            post('handover', path+'/post', body)
            self.records[0].append(dict(line_id=line, document_id=body['document_id'],
                operation_id=body['operation_id'], sets=sets, command=deepcopy(body)))
        else:
            path = '/orders/'+line+'/usage'
            current = get('usage_basis', path)
            consumed = D('.1')*(1+turn % 2)
            previous = self.usage_documents.get(issue)
            body = dict(factory_id='huakang-c', operation_id=uuid4().hex,
                expected_version=current['revision'], reason='Synthetic P5c rotating usage',
                issue_id=issue, day='2026-12-14', consumed_quantity=str(consumed),
                loss_quantity='0', counted_remaining=str(D(row['remaining_quantity'])-consumed))
            if previous:
                body['document_id'] = previous
            result = post('usage', path+('/correct' if previous else '/post'), body)
            self.usage_documents[issue] = result['document_id']
            self.records[1].append(dict(line_id=line, issue_id=issue, document_id=result['document_id'],
                replaces=previous, operation_id=body['operation_id'], consumed=str(consumed),
                command=deepcopy(body), receipt=deepcopy(result)))

    def validate_live(self, name, value, expected):
        if name == 'inventory':
            assert value['total'] == len(self.inventory) and set(value['units']) == set(expected[name][1])
            base, now = expected[name][1]['米'], value['units']['米']
            delta = D(now['consumed_quantity'])-D(base['consumed_quantity'])
            assert 0 <= delta <= D('.2')*len(self.targets[1])
            for key in ['received_quantity', 'returned_quantity', 'loss_quantity', 'unsigned_quantity']:
                assert D(now[key]) == D(base[key])
            assert D(now['remaining_quantity']) == D(base['remaining_quantity'])-delta
            selected = {r['issue_id'] for r in self.targets[1]}
            for row in value['data']:
                before = self.inventory[row['issue_id']]
                change = D(row['consumed_quantity'])-D(before['consumed_quantity'])
                assert change in ({D(0), D('.1'), D('.2')} if row['issue_id'] in selected else {D(0)})
                assert D(row['remaining_quantity']) == D(before['remaining_quantity'])-change
                for key in ['received_quantity', 'returned_quantity', 'loss_quantity']:
                    assert row[key] == before[key]
        elif name == 'costs':
            assert value['total'] == len(self.costs) and value['pending_pricing'] == expected[name][2]
            assert set(value['currencies']) == {'HKD'} == set(expected[name][1])
            before, now = expected[name][1]['HKD'], value['currencies']['HKD']
            delta = D(now['normal'])-D(before['normal'])
            assert 0 <= delta <= D('.8')*len(self.targets[1])
            assert now['loss'] == before['loss']
            if delta:
                assert now['completed'] is None and now['wip'] is None
            selected = {r['line_id'] for r in self.targets[1]}
            for row in value['data']:
                before = self.costs[row['line_id']]
                delta = D(row['normal']['HKD'])-D(before['normal']['HKD'])
                assert delta in ({D(0), D('.4'), D('.8')} if row['line_id'] in selected else {D(0)})
                assert row['loss'] == before['loss']
                if delta:
                    assert row['completed']['HKD'] is None and row['wip']['HKD'] is None
        else:
            raise ValueError('Only live inventory/costs are mutable in this profile')

    def reconcile(self, read, inventory, costs, seconds):
        handovers, usages = self.records
        assert handovers and usages
        touched = [set(r['line_id'] for r in records) for records in self.records]
        if seconds >= 120:
            assert all(touched[i] == {r['line_id'] for r in targets} for i, targets in enumerate(self.targets)), 'Incomplete rotating production coverage'
        grouped = defaultdict(list)
        for record in handovers:
            grouped[record['line_id']].append(record)
        for line, records in grouped.items():
            value = read('/orders/'+line+'/reports')
            assert value['summary']['completed'] == self.handover_baseline[line]['completed']
            assert value['summary']['actual_delivery'] == self.handover_baseline[line]['actual_delivery']+records[-1]['sets']
            document = next(r for r in value['documents'] if r['document_id'] == records[-1]['document_id'])
            assert len(document['history']) == len(records)
        grouped = defaultdict(list)
        for record in usages:
            grouped[record['issue_id']].append(record)
        last = {}
        for issue, records in grouped.items():
            last[issue] = D(records[-1]['consumed'])
            value = read('/orders/'+records[-1]['line_id']+'/usage', with_costs=True)
            documents = {r['id']: r for r in value['documents']}
            for i, record in enumerate(records):
                document = documents[record['document_id']]
                assert document['voided'] == (i < len(records)-1)
                assert document['replaces_document_id'] == record['replaces']
                assert document['replaced_by_document_id'] == (records[i+1]['document_id'] if i < len(records)-1 else None)
        assert len(inventory) == len(self.inventory) == len({r['issue_id'] for r in inventory})
        for row in inventory:
            before = self.inventory[row['issue_id']]
            expected = dict(before)
            change = last.get(row['issue_id'], D(0))
            expected['consumed_quantity'] = quantity(D(before['consumed_quantity'])+change) if change else before['consumed_quantity']
            expected['remaining_quantity'] = quantity(D(before['remaining_quantity'])-change) if change else before['remaining_quantity']
            assert row == expected
        assert len(costs) == len(self.costs) == len({r['line_id'] for r in costs})
        deltas = {self.inventory[issue]['line_id']: quantity*4 for issue, quantity in last.items()}
        for row in costs:
            before = self.costs[row['line_id']]
            if row['line_id'] not in deltas:
                assert row == before
            else:
                assert D(row['normal']['HKD']) == D(before['normal']['HKD'])+deltas[row['line_id']]
                assert row['loss'] == before['loss']
                assert row['completed']['HKD'] is None and row['wip']['HKD'] is None and row['allocation_pending'] >= 1
        return dict(handover_posts=len(handovers), usage_posts=len(usages),
            handover_orders=len(touched[0]), usage_orders=len(touched[1]),
            planned_orders_per_kind=len(self.targets[0]), normal_use_delta=str(sum(last.values(), D(0))),
            normal_cost_delta_hkd=str(sum(deltas.values(), D(0))), all_target_orders_exercised=all(
                touched[i] == {r['line_id'] for r in targets} for i, targets in enumerate(self.targets)))

    def verify_persisted(self, db):
        handovers, usages = self.records
        def count(table, documents):
            ids = sorted(set(documents))
            return db.execute('SELECT count(*) FROM '+table+' WHERE document_id IN ('+','.join('?' for _ in ids)+')', ids).fetchone()[0]
        actual = count('cutting_ops_production_events', (r['document_id'] for r in handovers))
        assert actual == len(handovers)
        actual = count('cutting_ops_material_events', (r['document_id'] for r in usages))
        assert actual == len(usages)*2-len(self.usage_documents)
        return dict(production_events=len(handovers), material_events=actual)


def reconcile_totals(inventory_view, inventory, cost_view, costs):
    """Full pagination and aggregate headers must describe the same instant."""
    assert len(inventory)==inventory_view['total']==len({r['issue_id'] for r in inventory})
    assert set(inventory_view['units'])=={r['context']['unit'] for r in inventory}
    for unit, fields in inventory_view['units'].items():
        for key, value in fields.items():
            assert sum((D(r[key]) for r in inventory if r['context']['unit']==unit),D(0))==D(value)
    assert len(costs)==cost_view['total']==len({r['line_id'] for r in costs})
    assert sum(r['pending_pricing'] for r in costs)==cost_view['pending_pricing']
    assert set(cost_view['currencies'])=={currency for row in costs for currency in row['normal']}
    for currency, fields in cost_view['currencies'].items():
        for key, value in fields.items():
            parts=[r[key].get(currency,'0') for r in costs]
            if any(v is None for v in parts):
                assert value is None
            else:
                assert value is not None and sum((D(v) for v in parts),D(0))==D(value)
